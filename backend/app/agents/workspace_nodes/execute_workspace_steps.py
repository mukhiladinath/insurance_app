"""
execute_workspace_steps.py — Execute tool steps with cache reuse and patch support.

Extends the logic from orchestrator_nodes/execute_steps_node.py with:
  - cached_step_results: skip steps whose output is already valid (from a prior run)
  - invalidated_steps: force re-execution of steps affected by patched inputs
  - status="cached" for reused steps
  - dependency_graph invalidation propagation

State reads:  tool_plan, cached_step_results, invalidated_steps
State writes: step_results, data_cards
"""

import logging
import re
from typing import Any

from app.agents.workspace_state import WorkspaceState
from app.tools.registry import get_tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Input chaining (same logic as execute_steps_node.py)
# ---------------------------------------------------------------------------

def _get_nested(obj: Any, path: str) -> Any:
    parts = path.split(".")
    current = obj
    for part in parts:
        if current is None:
            return None
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _interpolate_value(value: Any, completed_results: list[dict]) -> Any:
    if not isinstance(value, str):
        return value
    PATTERN = r"\{\{step_(\d+)\.([a-zA-Z0-9_.]+)\}\}"
    matches = re.findall(PATTERN, value)
    if not matches:
        return value
    if re.fullmatch(PATTERN, value.strip()):
        step_n, field_path = matches[0]
        step_idx = int(step_n) - 1
        if step_idx < len(completed_results):
            return _get_nested(completed_results[step_idx].get("output") or {}, field_path)
        return None
    result = value
    for step_n, field_path in matches:
        step_idx = int(step_n) - 1
        ref_value = None
        if step_idx < len(completed_results):
            ref_value = _get_nested(completed_results[step_idx].get("output") or {}, field_path)
        result = result.replace(f"{{{{step_{step_n}.{field_path}}}}}", str(ref_value) if ref_value is not None else "")
    return result


def _resolve_inputs(inputs: Any, completed_results: list[dict]) -> Any:
    if isinstance(inputs, dict):
        return {k: _resolve_inputs(v, completed_results) for k, v in inputs.items()}
    if isinstance(inputs, list):
        return [_resolve_inputs(item, completed_results) for item in inputs]
    if isinstance(inputs, str):
        return _interpolate_value(inputs, completed_results)
    return inputs


# ---------------------------------------------------------------------------
# Data card builder (same as execute_steps_node.py)
# ---------------------------------------------------------------------------

_CARD_META: dict[str, dict] = {
    "purchase_retain_life_insurance_in_super": {"type": "life_in_super_analysis", "title": "Life Insurance in Super", "display_hint": "summary_with_actions"},
    "purchase_retain_life_tpd_policy": {"type": "life_tpd_recommendation", "title": "Life & TPD Policy Analysis", "display_hint": "recommendation_card"},
    "purchase_retain_income_protection_policy": {"type": "ip_recommendation", "title": "Income Protection Analysis", "display_hint": "recommendation_card"},
    "purchase_retain_ip_in_super": {"type": "ip_in_super_analysis", "title": "Income Protection in Super", "display_hint": "summary_with_actions"},
    "purchase_retain_trauma_ci_policy": {"type": "trauma_recommendation", "title": "Trauma / Critical Illness Analysis", "display_hint": "recommendation_card"},
    "tpd_policy_assessment": {"type": "tpd_assessment", "title": "TPD Policy Assessment", "display_hint": "gap_analysis_card"},
    "purchase_retain_tpd_in_super": {"type": "tpd_in_super_analysis", "title": "TPD in Super Analysis", "display_hint": "summary_with_actions"},
}


def _build_data_card(tool_name: str, step_id: str, output: dict) -> dict:
    meta = _CARD_META.get(tool_name, {
        "type": "generic_tool_result",
        "title": tool_name.replace("_", " ").title(),
        "display_hint": "table",
    })
    return {**meta, "step_id": step_id, "tool_name": tool_name, "data": output}


def _has_failed_dependency(step: dict, results_by_id: dict[str, dict]) -> bool:
    for dep_id in step.get("depends_on", []):
        dep = results_by_id.get(dep_id)
        if dep and dep["status"] in ("failed", "skipped"):
            return True
    return False


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def execute_workspace_steps(state: WorkspaceState) -> dict:
    """
    Execute plan steps with cache reuse for unchanged steps.

    Reads:  tool_plan, cached_step_results, invalidated_steps
    Writes: step_results, data_cards
    """
    tool_plan: list[dict] = state.get("tool_plan", [])
    cached: dict = state.get("cached_step_results", {})
    invalidated: list[str] = state.get("invalidated_steps", [])
    client_id = state.get("client_id", "")

    completed_results: list[dict] = []
    results_by_id: dict[str, dict] = {}

    for step in tool_plan:
        step_id = step["step_id"]
        tool_name = step["tool_name"]
        description = step.get("description", "")

        # ---- Direct response: skip tool execution ----
        if tool_name == "direct_response":
            result: dict = {
                "step_id": step_id, "tool_name": tool_name, "description": description,
                "status": "skipped", "output": None, "data_card": None, "error": None,
                "cache_source_run_id": None,
            }
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        # ---- Use cached result if valid (not invalidated) ----
        if step_id in cached and step_id not in invalidated:
            cached_result = cached[step_id]
            result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "cached",
                "output": cached_result.get("output"),
                "data_card": cached_result.get("data_card") or (
                    _build_data_card(tool_name, step_id, cached_result.get("output", {}))
                    if cached_result.get("output") else None
                ),
                "error": None,
                "cache_source_run_id": cached_result.get("run_id"),
            }
            logger.info("execute_workspace_steps: %s reused from cache", step_id)
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        # ---- Check dependency failures ----
        if _has_failed_dependency(step, results_by_id):
            result = {
                "step_id": step_id, "tool_name": tool_name, "description": description,
                "status": "skipped", "output": None, "data_card": None,
                "error": "Skipped: a required dependency step failed.",
                "cache_source_run_id": None,
            }
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        # ---- Resolve chain references ----
        raw_inputs = step.get("inputs", {})
        resolved_inputs = _resolve_inputs(raw_inputs, completed_results)

        # ---- Execute ----
        tool = get_tool(tool_name)
        if not tool:
            result = {
                "step_id": step_id, "tool_name": tool_name, "description": description,
                "status": "failed", "output": None, "data_card": None,
                "error": f"Tool '{tool_name}' is not registered.",
                "cache_source_run_id": None,
            }
            logger.warning("execute_workspace_steps: unknown tool '%s'", tool_name)
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        try:
            output = tool.execute(resolved_inputs)
            data_card = _build_data_card(tool_name, step_id, output)
            result = {
                "step_id": step_id, "tool_name": tool_name, "description": description,
                "status": "completed", "output": output, "data_card": data_card,
                "error": None, "cache_source_run_id": None,
            }
            logger.info("execute_workspace_steps: %s completed (client=%s)", step_id, client_id)
        except Exception as exc:
            logger.exception("execute_workspace_steps: %s raised %s", step_id, exc)
            result = {
                "step_id": step_id, "tool_name": tool_name, "description": description,
                "status": "failed", "output": None, "data_card": None,
                "error": str(exc), "cache_source_run_id": None,
            }

        completed_results.append(result)
        results_by_id[step_id] = result

    data_cards = [r["data_card"] for r in completed_results if r.get("data_card")]

    return {"step_results": completed_results, "data_cards": data_cards}
