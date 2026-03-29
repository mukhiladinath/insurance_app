"""
objectives_automation_service.py — Run insurance engines from fact-find goals text.

Uses an LLM to select engines (with regex fallback), executes each tool, then
persists **one** merged client_analysis_outputs row (source=automated) via the
shared summarizer.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.client_analysis_output_repository import ClientAnalysisOutputRepository
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.services.insurance_tool_selection_llm import (
    build_summarizer_tool_results,
    llm_select_insurance_engine_tools,
    order_registry_tools,
)
from app.services.memory_canonical_hints import load_memory_canonical_hints, merge_memory_then_factfind
from app.services.memory_merge_service import build_tool_input_from_memory
from app.services.planner_service import summarize_results
from app.tools.registry import get_tool, tool_exists

logger = logging.getLogger(__name__)

_FACTFIND_SECTIONS = ["personal", "financial", "insurance", "health", "goals"]

# Stable execution order (user sees consistent sequencing)
_INSURANCE_TOOL_ORDER = [
    "purchase_retain_life_tpd_policy",
    "purchase_retain_life_insurance_in_super",
    "purchase_retain_income_protection_policy",
    "purchase_retain_ip_in_super",
    "tpd_policy_assessment",
    "purchase_retain_trauma_ci_policy",
    "purchase_retain_tpd_in_super",
]

TOOL_DISPLAY_LABELS: dict[str, str] = {
    "purchase_retain_life_tpd_policy": "Life & TPD policy",
    "purchase_retain_life_insurance_in_super": "Life insurance in super",
    "purchase_retain_income_protection_policy": "Income protection",
    "purchase_retain_ip_in_super": "IP in super",
    "tpd_policy_assessment": "TPD policy assessment",
    "purchase_retain_trauma_ci_policy": "Trauma / critical illness",
    "purchase_retain_tpd_in_super": "TPD in super",
}

# (tool_id, regex) — first match wins per tool; scan all rules
OBJECTIVE_TOOL_RULES: list[tuple[str, re.Pattern]] = [
    (
        "purchase_retain_life_insurance_in_super",
        re.compile(
            r"\b(life\s+insurance\s+in\s+super|super(?:annuation)?\s+life|life\s+cover\s+in\s+super|insurance\s+through\s+super)\b",
            re.I,
        ),
    ),
    (
        "purchase_retain_ip_in_super",
        re.compile(
            r"\b(ip\s+in\s+super|income\s+protection\s+in\s+super|salary\s+continuance\s+in\s+super)\b",
            re.I,
        ),
    ),
    (
        "purchase_retain_income_protection_policy",
        re.compile(
            r"\b(income\s+protection|ip\s+cover|salary\s+continuance|disability\s+income)\b",
            re.I,
        ),
    ),
    (
        "purchase_retain_trauma_ci_policy",
        re.compile(
            r"\b(trauma|critical\s+illness|\bci\b|cancer\s+cover|specified\s+events?)\b",
            re.I,
        ),
    ),
    (
        "purchase_retain_tpd_in_super",
        re.compile(r"\b(tpd\s+in\s+super|total\s+and\s+permanent\s+disability\s+in\s+super)\b", re.I),
    ),
    (
        "tpd_policy_assessment",
        re.compile(
            r"\b(tpd|total\s+and\s+permanent\s+disability|permanent\s+disability)\b",
            re.I,
        ),
    ),
    (
        "purchase_retain_life_tpd_policy",
        re.compile(
            r"\b(life\s+and\s+tpd|life\s*&\s*tpd|life\s*\+\s*tpd|combined\s+life|death\s+and\s+tpd|life\s+cover|death\s+cover|life\s+insurance)\b",
            re.I,
        ),
    ),
]


def infer_tool_ids_from_objectives_heuristic(text: str) -> list[str]:
    """Regex fallback when the LLM returns no tools."""
    if not text or not str(text).strip():
        return []
    s = str(text).strip()
    matched: set[str] = set()
    for tool_id, pattern in OBJECTIVE_TOOL_RULES:
        if tool_id in matched:
            continue
        if pattern.search(s):
            matched.add(tool_id)
    return [t for t in _INSURANCE_TOOL_ORDER if t in matched]


async def infer_tool_ids_from_objectives(text: str) -> list[str]:
    """LLM selection first; fall back to keyword heuristics."""
    llm_ids = await llm_select_insurance_engine_tools(text, purpose="objectives")
    if llm_ids:
        return order_registry_tools(llm_ids)
    return infer_tool_ids_from_objectives_heuristic(text)


def _objectives_fingerprint(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


async def _canonical_facts_from_factfind(db: AsyncIOMotorDatabase, client_id: str) -> dict[str, dict[str, Any]]:
    repo = FactfindRepository(db)
    factfind = await repo.get_or_create(client_id)
    sections = factfind.get("sections", {})
    canonical: dict[str, dict[str, Any]] = {s: {} for s in _FACTFIND_SECTIONS}
    for section in _FACTFIND_SECTIONS:
        for field, field_data in sections.get(section, {}).items():
            if isinstance(field_data, dict):
                v = field_data.get("value")
                if v is not None:
                    canonical[section][field] = v
    memory_hints = await load_memory_canonical_hints(client_id)
    return merge_memory_then_factfind(memory_hints, canonical)


async def run_objectives_automation(
    db: AsyncIOMotorDatabase,
    client_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Read goals_and_objectives from factfind; infer tools; execute each; save outputs.

    Skips if fingerprint matches workspace (unless force=True).
    """
    fact_repo = FactfindRepository(db)
    ws_repo = WorkspaceRepository(db)
    out_repo = ClientAnalysisOutputRepository(db)

    factfind = await fact_repo.get_or_create(client_id)
    sections = factfind.get("sections", {})
    goals_block = sections.get("goals", {})
    raw = goals_block.get("goals_and_objectives")
    objectives_text = ""
    if isinstance(raw, dict):
        objectives_text = str(raw.get("value") or "").strip()
    elif isinstance(raw, str):
        objectives_text = raw.strip()
    elif raw is not None:
        objectives_text = str(raw).strip()

    if not objectives_text:
        return {
            "skipped": True,
            "reason": "goals_and_objectives is empty",
            "tools_run": [],
            "outputs_created": 0,
        }

    fp = _objectives_fingerprint(objectives_text)
    workspace = await ws_repo.get_by_client(client_id)
    if workspace is None:
        from app.db.repositories.client_repository import ClientRepository

        client = await ClientRepository(db).get_by_id(client_id)
        uid = (client or {}).get("user_id") or ""
        workspace = await ws_repo.get_or_create(client_id, uid)

    prev_fp = workspace.get("objectives_automation_fingerprint")
    if not force and prev_fp == fp:
        return {
            "skipped": True,
            "reason": "objectives unchanged since last automated run (use force=true to re-run)",
            "tools_run": [],
            "outputs_created": 0,
        }

    tool_ids = await infer_tool_ids_from_objectives(objectives_text)
    if not tool_ids:
        await ws_repo.set_objectives_automation_fingerprint(client_id, fp)
        return {
            "skipped": False,
            "reason": "No insurance tools selected (LLM + heuristics); refine goals text or wording",
            "tools_run": [],
            "outputs_created": 0,
        }

    canonical = await _canonical_facts_from_factfind(db, client_id)
    memory = {"client_facts": canonical}

    runs: list[dict[str, Any]] = []
    for tool_id in tool_ids:
        if not tool_exists(tool_id):
            logger.warning("objectives_automation: unknown tool %s", tool_id)
            continue
        tool = get_tool(tool_id)
        assert tool is not None
        tool_input = build_tool_input_from_memory(tool_id, memory)
        label = TOOL_DISPLAY_LABELS.get(tool_id, tool_id)
        try:
            payload = tool.safe_execute(tool_input)
            runs.append({"tool_id": tool_id, "label": label, "payload": payload})
        except Exception as exc:
            logger.exception("objectives_automation: tool %s failed: %s", tool_id, exc)
            runs.append(
                {
                    "tool_id": tool_id,
                    "label": label,
                    "payload": {"_execution_error": True, "message": str(exc), "tool_id": tool_id},
                    "error": True,
                }
            )

    if not runs:
        await ws_repo.set_objectives_automation_fingerprint(client_id, fp)
        return {
            "skipped": False,
            "reason": "No tools could be executed",
            "tools_run": tool_ids,
            "outputs_created": 0,
        }

    summarizer_input = (
        "The client stated the following goals and objectives. Summarise the insurance engine "
        "results for the adviser in clear prose (bullet points welcome). "
        "Note any data gaps or warnings. Do not dump raw JSON in the summary.\n\n"
        f"## Goals & objectives\n\n{objectives_text[:4000]}"
    )
    tool_results = build_summarizer_tool_results(runs)
    summary = await summarize_results(summarizer_input, tool_results, messages=None)

    step_labels = [r["label"] for r in runs]
    appendix_lines = ["\n\n---\n\n### Structured engine outputs (JSON)\n\n"]
    for r in runs:
        tid = r["tool_id"]
        try:
            blob = json.dumps(r.get("payload"), indent=2, default=str)
        except TypeError:
            blob = str(r.get("payload"))
        if len(blob) > 24_000:
            blob = blob[:24_000] + "\n… (truncated)"
        appendix_lines.append(f"#### `{tid}`\n\n```json\n{blob}\n```\n\n")
    content = f"## Automated analysis (from goals & objectives)\n\n{summary}" + "".join(appendix_lines)

    structured = [
        {"tool_id": r["tool_id"], "status": "completed", "output": r.get("payload") if isinstance(r.get("payload"), dict) else None}
        for r in runs
        if isinstance(r.get("payload"), dict)
    ]
    await out_repo.create(
        client_id=client_id,
        instruction="Automated: goals & objectives (merged insurance engines)",
        tool_ids=[r["tool_id"] for r in runs],
        step_labels=step_labels,
        content=content,
        source="automated",
        structured_step_results=structured,
    )

    await ws_repo.set_objectives_automation_fingerprint(client_id, fp)
    return {
        "skipped": False,
        "reason": "",
        "tools_run": [r["tool_id"] for r in runs],
        "outputs_created": 1,
    }
