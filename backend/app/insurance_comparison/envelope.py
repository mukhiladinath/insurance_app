"""Build optional comparison_envelope for persisted step_results."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.insurance_comparison.registry import normalize_tool_output


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_comparison_envelope(
    tool_name: str,
    raw_output: dict[str, Any] | None,
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str | None = None,
) -> dict[str, Any] | None:
    if not raw_output or tool_name in ("direct_response", ""):
        return None
    gen = generated_at or _iso_now()
    normalized = normalize_tool_output(
        tool_name,
        raw_output,
        tool_run_id=tool_run_id,
        client_id=client_id,
        generated_at=gen,
    )
    if not normalized:
        return None
    facts = normalized.get("comparisonFacts") or []
    assumptions = list(normalized.get("assumptions") or [])
    warnings = list(normalized.get("warnings") or [])
    return {
        "rawOutput": dict(raw_output),
        "normalizedOutput": normalized,
        "comparisonFacts": facts,
        "assumptions": assumptions,
        "warnings": warnings,
        "auditTrace": [
            {"step": "normalize", "toolName": tool_name, "toolRunId": tool_run_id, "generatedAt": gen},
        ],
    }


def enrich_step_results_with_envelopes(
    step_results: list[dict[str, Any]],
    *,
    client_id: str,
    saved_run_id: str,
) -> list[dict[str, Any]]:
    """Return a new list with comparison_envelope attached where supported."""
    out: list[dict[str, Any]] = []
    for r in step_results:
        row = dict(r)
        if row.get("status") not in ("completed", "cached"):
            out.append(row)
            continue
        tn = row.get("tool_name") or ""
        step_id = row.get("step_id") or ""
        tool_run_id = f"{saved_run_id}:{step_id}"
        raw = row.get("output")
        if not isinstance(raw, dict):
            out.append(row)
            continue
        gen = raw.get("evaluated_at") or _iso_now()
        env = build_comparison_envelope(
            tn,
            raw,
            tool_run_id=tool_run_id,
            client_id=client_id,
            generated_at=str(gen) if gen else _iso_now(),
        )
        if env:
            norm = env.get("normalizedOutput") or {}
            if isinstance(norm, dict):
                norm["toolRunId"] = tool_run_id
                norm["clientId"] = client_id
                env["normalizedOutput"] = norm
            row["comparison_envelope"] = env
        out.append(row)
    return out
