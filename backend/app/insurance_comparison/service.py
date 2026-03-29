"""Orchestration: load saved steps, normalize, compare, save."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.client_analysis_output_repository import ClientAnalysisOutputRepository
from app.db.repositories.insurance_comparison_repository import InsuranceComparisonRepository
from app.db.repositories.saved_tool_run_repository import SavedToolRunRepository
from app.insurance_comparison.engine import compare_normalized
from app.insurance_comparison.narrative import attach_narrative
from app.insurance_comparison.registry import has_normalizer, normalize_tool_output
from app.insurance_comparison.scoring import compare_weighted_scores

# Orchestrator (frontend) short tool_id → backend registry tool_name
ORCHESTRATOR_TO_BACKEND_TOOL: dict[str, str] = {
    "life_insurance_in_super": "purchase_retain_life_insurance_in_super",
    "life_tpd_policy": "purchase_retain_life_tpd_policy",
    "income_protection_policy": "purchase_retain_income_protection_policy",
    "ip_in_super": "purchase_retain_ip_in_super",
    "trauma_critical_illness": "purchase_retain_trauma_ci_policy",
    "tpd_policy_assessment": "tpd_policy_assessment",
    "tpd_in_super": "purchase_retain_tpd_in_super",
}


def _resolve_backend_tool_name(stored_tool_id: str) -> str | None:
    """Orchestrator short id, or already-canonical backend tool name (e.g. objectives automation)."""
    if stored_tool_id in ORCHESTRATOR_TO_BACKEND_TOOL:
        return ORCHESTRATOR_TO_BACKEND_TOOL[stored_tool_id]
    if has_normalizer(stored_tool_id):
        return stored_tool_id
    return None


def parse_saved_run_step_ref(tool_run_id: str) -> tuple[str, str]:
    parts = tool_run_id.split(":", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(status_code=400, detail="Invalid toolRunId — expected '{savedRunId}:{stepId}'.")
    return parts[0], parts[1]


def parse_analysis_output_ref(tool_run_id: str) -> tuple[str, int] | None:
    """
    If tool_run_id is analysisoutput:{mongoId}:{index}, return (output_id, index).
    Otherwise return None.
    """
    if not tool_run_id.startswith("analysisoutput:"):
        return None
    rest = tool_run_id.removeprefix("analysisoutput:")
    if rest.startswith(":"):
        rest = rest[1:]
    head, sep, tail = rest.rpartition(":")
    if not sep or not head:
        raise HTTPException(
            status_code=400,
            detail="Invalid toolRunId — expected 'analysisoutput:{analysisOutputId}:{stepIndex}'.",
        )
    try:
        idx = int(tail)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid analysis output step index.",
        ) from exc
    return head, idx


def _iso(ts: Any) -> str:
    if isinstance(ts, datetime):
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.isoformat()
    return str(ts or datetime.now(timezone.utc).isoformat())


async def resolve_normalized_output(
    db: AsyncIOMotorDatabase,
    *,
    client_id: str,
    tool_run_id: str,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    """
    Load step from saved_tool_runs OR structured row from client_analysis_outputs;
    return (normalized_output, backend_tool_name, source_meta).
    """
    ao = parse_analysis_output_ref(tool_run_id)
    if ao is not None:
        out_id, idx = ao
        repo = ClientAnalysisOutputRepository(db)
        doc = await repo.get(out_id, client_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Saved analysis output not found for this client.")
        rows = doc.get("structured_step_results") or []
        if idx < 0 or idx >= len(rows):
            raise HTTPException(status_code=404, detail="Analysis step index out of range.")
        row = rows[idx]
        if row.get("status") != "completed":
            raise HTTPException(status_code=400, detail="That analysis step did not complete — cannot compare.")
        raw = row.get("output")
        if not isinstance(raw, dict):
            raise HTTPException(status_code=400, detail="No structured tool output stored for this saved analysis.")
        orch = row.get("tool_id") or ""
        tool_name = _resolve_backend_tool_name(orch)
        if not tool_name:
            raise HTTPException(
                status_code=422,
                detail="Comparison is not yet supported for this tool output because normalized comparison facts are unavailable.",
            )
        gen = raw.get("evaluated_at") or _iso(doc.get("created_at"))
        if not has_normalizer(tool_name):
            raise HTTPException(
                status_code=422,
                detail="Comparison is not yet supported for this tool output because normalized comparison facts are unavailable.",
            )
        norm = normalize_tool_output(
            tool_name,
            raw,
            tool_run_id=tool_run_id,
            client_id=client_id,
            generated_at=str(gen),
        )
        if not norm:
            raise HTTPException(
                status_code=422,
                detail="Comparison is not yet supported for this tool output because normalized comparison facts are unavailable.",
            )
        meta = {
            "analysisOutputId": out_id,
            "stepIndex": idx,
            "instruction": doc.get("instruction"),
            "toolName": tool_name,
            "source": "client_analysis_outputs",
        }
        return norm, tool_name, meta

    saved_id, step_id = parse_saved_run_step_ref(tool_run_id)
    repo = SavedToolRunRepository(db)
    run = await repo.get_by_id(saved_id)
    if not run or run.get("client_id") != client_id:
        raise HTTPException(status_code=404, detail="Saved tool run not found for this client.")

    step = None
    for r in run.get("step_results") or []:
        if r.get("step_id") == step_id:
            step = r
            break
    if not step:
        raise HTTPException(status_code=404, detail="Step not found on saved run.")
    if step.get("status") not in ("completed", "cached"):
        raise HTTPException(status_code=400, detail="Step did not complete successfully — cannot compare.")

    tool_name = step.get("tool_name") or ""
    raw = step.get("output")
    if not isinstance(raw, dict):
        raise HTTPException(status_code=400, detail="Step has no structured output to compare.")

    env = step.get("comparison_envelope") or {}
    norm = None
    if isinstance(env, dict):
        norm = env.get("normalizedOutput")

    gen = raw.get("evaluated_at") or _iso(run.get("saved_at"))
    if not isinstance(norm, dict):
        if not has_normalizer(tool_name):
            raise HTTPException(
                status_code=422,
                detail="Comparison is not yet supported for this tool output because normalized comparison facts are unavailable.",
            )
        norm = normalize_tool_output(
            tool_name,
            raw,
            tool_run_id=tool_run_id,
            client_id=client_id,
            generated_at=str(gen),
        )
        if not norm:
            raise HTTPException(
                status_code=422,
                detail="Comparison is not yet supported for this tool output because normalized comparison facts are unavailable.",
            )

    meta = {
        "savedRunId": saved_id,
        "stepId": step_id,
        "savedRunName": run.get("name"),
        "toolName": tool_name,
        "source": "saved_tool_runs",
    }
    return norm, tool_name, meta


async def list_compare_eligible_steps(db: AsyncIOMotorDatabase, client_id: str, limit: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []

    srepo = SavedToolRunRepository(db)
    runs = await srepo.list_by_client(client_id, limit=limit)
    for run in runs:
        sid = run.get("id")
        for step in run.get("step_results") or []:
            if step.get("status") not in ("completed", "cached"):
                continue
            tn = step.get("tool_name") or ""
            if tn in ("direct_response", ""):
                continue
            stid = step.get("step_id") or ""
            tool_run_id = f"{sid}:{stid}"
            env = step.get("comparison_envelope") or {}
            has_norm = bool(isinstance(env, dict) and env.get("normalizedOutput"))
            label = f"Workspace save: {run.get('name', 'Run')} — {tn.replace('_', ' ')}"
            items.append({
                "toolRunId": tool_run_id,
                "savedRunId": sid,
                "stepId": stid,
                "toolName": tn,
                "savedRunName": run.get("name", ""),
                "savedAt": _iso(run.get("saved_at")),
                "label": label,
                "hasNormalizedEnvelope": has_norm,
                "sourceKind": "workspace_save",
            })

    arepo = ClientAnalysisOutputRepository(db)
    outputs = await arepo.list_for_client(client_id, limit=limit)
    for doc in outputs:
        srs = doc.get("structured_step_results") or []
        if not srs:
            continue
        oid = doc.get("id")
        for i, row in enumerate(srs):
            if row.get("status") != "completed":
                continue
            orch = row.get("tool_id") or ""
            bt = _resolve_backend_tool_name(orch)
            if not bt:
                continue
            if not isinstance(row.get("output"), dict):
                continue
            tool_run_id = f"analysisoutput:{oid}:{i}"
            instr = (doc.get("instruction") or "Analysis")[:60]
            label = f"Saved analysis: {instr} — {orch.replace('_', ' ')}"
            items.append({
                "toolRunId": tool_run_id,
                "savedRunId": oid,
                "stepId": str(i),
                "toolName": bt,
                "savedRunName": instr,
                "savedAt": _iso(doc.get("created_at")),
                "label": label,
                "hasNormalizedEnvelope": False,
                "sourceKind": "saved_analysis",
            })

    items.sort(key=lambda x: str(x.get("savedAt") or ""), reverse=True)
    return items[:limit]


async def run_compare(
    db: AsyncIOMotorDatabase,
    *,
    client_id: str,
    left_tool_run_id: str,
    right_tool_run_id: str,
    weights: dict[str, float] | None = None,
    fact_find_version: str | int | None = None,
) -> dict[str, Any]:
    left_norm, left_tool, left_meta = await resolve_normalized_output(
        db, client_id=client_id, tool_run_id=left_tool_run_id
    )
    right_norm, right_tool, right_meta = await resolve_normalized_output(
        db, client_id=client_id, tool_run_id=right_tool_run_id
    )

    result = compare_normalized(left_norm, right_norm, left_tool_name=left_tool, right_tool_name=right_tool)
    score_bundle = compare_weighted_scores(left_norm, right_norm, weights=weights)
    result["scoreBreakdown"] = score_bundle.get("scoreBreakdown", [])
    result["weightedTotals"] = score_bundle.get("weightedTotals", {})
    result["scoreExplanation"] = score_bundle.get("scoreExplanation", "")
    result["sourceRefs"] = {
        "left": left_meta,
        "right": right_meta,
        "factFindVersion": fact_find_version,
    }
    result = attach_narrative(result)
    return result


async def save_comparison_record(
    db: AsyncIOMotorDatabase,
    *,
    client_id: str,
    left_tool_run_id: str,
    right_tool_run_id: str,
    comparison_type: str,
    comparison_result: dict[str, Any],
    fact_find_version: str | int | None,
    created_by: str,
) -> dict:
    left_tool = (comparison_result.get("sourceRefs") or {}).get("left", {}).get("toolName", "")
    right_tool = (comparison_result.get("sourceRefs") or {}).get("right", {}).get("toolName", "")
    mode = comparison_result.get("comparisonMode", "partial")
    repo = InsuranceComparisonRepository(db)
    return await repo.create(
        client_id=client_id,
        left_tool_run_id=left_tool_run_id,
        right_tool_run_id=right_tool_run_id,
        left_tool_name=left_tool,
        right_tool_name=right_tool,
        comparison_type=comparison_type,
        comparison_mode=mode,
        comparison_result=comparison_result,
        fact_find_version=fact_find_version,
        created_by=created_by,
    )
