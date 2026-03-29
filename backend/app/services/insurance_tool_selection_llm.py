"""
insurance_tool_selection_llm.py — LLM picks which insurance engine(s) apply to a narrative.

Used for:
  - Automated workflow (fact-find goals & objectives)
  - Manual orchestrator planning (hints injected into planner context)

Registry tool_ids match build_tool_input_from_memory / app.tools.registry.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage

from app.core.llm import get_chat_model

logger = logging.getLogger(__name__)

INSURANCE_ENGINE_REGISTRY_IDS: tuple[str, ...] = (
    "purchase_retain_life_tpd_policy",
    "purchase_retain_life_insurance_in_super",
    "purchase_retain_income_protection_policy",
    "purchase_retain_ip_in_super",
    "tpd_policy_assessment",
    "purchase_retain_trauma_ci_policy",
    "purchase_retain_tpd_in_super",
)

# Planner / frontend orchestrator tool_id (see planner_service + orchestrator-handlers)
REGISTRY_TO_PLANNER_TOOL_ID: dict[str, str] = {
    "purchase_retain_life_tpd_policy": "life_tpd_policy",
    "purchase_retain_life_insurance_in_super": "life_insurance_in_super",
    "purchase_retain_income_protection_policy": "income_protection_policy",
    "purchase_retain_ip_in_super": "ip_in_super",
    "tpd_policy_assessment": "tpd_policy_assessment",
    "purchase_retain_trauma_ci_policy": "trauma_critical_illness",
    "purchase_retain_tpd_in_super": "tpd_in_super",
}

TOOL_SHORT_LABELS: dict[str, str] = {
    "purchase_retain_life_tpd_policy": "Life & TPD (retail)",
    "purchase_retain_life_insurance_in_super": "Life insurance in super",
    "purchase_retain_income_protection_policy": "Income protection (retail)",
    "purchase_retain_ip_in_super": "Income protection in super",
    "tpd_policy_assessment": "TPD policy assessment",
    "purchase_retain_trauma_ci_policy": "Trauma / critical illness",
    "purchase_retain_tpd_in_super": "TPD in super",
}

_INSURANCE_TOOL_ORDER = list(INSURANCE_ENGINE_REGISTRY_IDS)

_SELECTION_SYSTEM = """You are an expert insurance paraplanner. Given text from an adviser or a client's goals/objectives, \
decide which **deterministic insurance engines** should run.

## Valid engine IDs (use EXACTLY these strings in JSON)

- purchase_retain_life_tpd_policy — retail combined life + TPD
- purchase_retain_life_insurance_in_super — life cover inside superannuation
- purchase_retain_income_protection_policy — retail income protection / salary continuance
- purchase_retain_ip_in_super — income protection inside super
- tpd_policy_assessment — standalone TPD policy review/assessment
- purchase_retain_trauma_ci_policy — trauma / critical illness
- purchase_retain_tpd_in_super — TPD inside superannuation

## Rules

1. Return ONLY valid JSON: {"tool_ids": ["...", ...]} with no markdown fences.
2. Include an engine only if the text clearly relates to that cover type or asks for that analysis.
3. If the text is unrelated to personal risk insurance (e.g. only general advice), return {"tool_ids": []}.
4. Prefer the smallest relevant set; include multiple when the text clearly needs several covers.
5. "Life insurance in super" → purchase_retain_life_insurance_in_super (not retail life+TPD unless TPD/life retail also mentioned).
6. "TPD in super" → purchase_retain_tpd_in_super; generic "TPD" without super → tpd_policy_assessment or purchase_retain_life_tpd_policy if bundled life+TPD is implied.
"""


def _parse_tool_ids_json(raw: str) -> list[str]:
    text = re.sub(r"```(?:json)?", "", raw).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return []
        try:
            data = json.loads(m.group())
        except json.JSONDecodeError:
            return []
    if not isinstance(data, dict):
        return []
    ids = data.get("tool_ids")
    if not isinstance(ids, list):
        return []
    valid = set(INSURANCE_ENGINE_REGISTRY_IDS)
    out: list[str] = []
    for x in ids:
        if isinstance(x, str) and x in valid and x not in out:
            out.append(x)
    return out


def order_registry_tools(ids: list[str]) -> list[str]:
    return [t for t in _INSURANCE_TOOL_ORDER if t in set(ids)]


async def llm_select_insurance_engine_tools(
    narrative: str,
    *,
    purpose: Literal["objectives", "adviser_instruction"] = "adviser_instruction",
) -> list[str]:
    """
    LLM-select zero or more insurance engine registry IDs.
    Returns [] on empty narrative, parse failure, or LLM error.
    """
    text = (narrative or "").strip()
    if not text:
        return []

    purpose_line = (
        "The text is the client's **goals and objectives** from a fact find."
        if purpose == "objectives"
        else "The text is an **adviser's instruction** to an orchestrator."
    )

    human = f"""{purpose_line}

## Text

{text[:8000]}

Return JSON: {{"tool_ids": ["..."]}}"""

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke(
            [
                SystemMessage(content=_SELECTION_SYSTEM),
                HumanMessage(content=human),
            ]
        )
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_tool_ids_json(raw)
        return order_registry_tools(parsed)
    except Exception as exc:
        logger.warning("llm_select_insurance_engine_tools failed: %s", exc)
        return []


def registry_ids_to_planner_hint(registry_ids: list[str]) -> str:
    """Human-readable block appended to planner user prompt."""
    if not registry_ids:
        return ""
    ordered = order_registry_tools(registry_ids)
    lines = [
        "INSURANCE ENGINE SUGGESTION (from a dedicated LLM — use as guidance; you choose the final plan):",
    ]
    for rid in ordered:
        pid = REGISTRY_TO_PLANNER_TOOL_ID.get(rid)
        label = TOOL_SHORT_LABELS.get(rid, rid)
        if pid:
            lines.append(f"- {label} → use planner tool_id \"{pid}\"")
        else:
            lines.append(f"- {label} → engine `{rid}`")
    lines.append(
        "When the instruction asks for these analyses, include the corresponding step(s) with the correct clientId."
    )
    return "\n".join(lines)


def build_summarizer_tool_results(
    runs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Shape for planner_service.summarize_results."""
    out: list[dict[str, Any]] = []
    for r in runs:
        out.append(
            {
                "tool_id": r.get("tool_id", "unknown"),
                "parameters": {},
                "result": r.get("payload"),
                "status": "completed" if not r.get("error") else "failed",
                "label": r.get("label", ""),
            }
        )
    return out
