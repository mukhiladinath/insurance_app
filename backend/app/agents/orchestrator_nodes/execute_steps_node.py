"""
execute_steps_node.py — Orchestrator node: run each step in the plan sequentially.

For each PlanStep in state.plan_steps:
  1. Resolve {{step_N.field}} chain references in inputs from prior step outputs.
  2. Skip steps with tool_name == "direct_response".
  3. Execute the registered tool.
  4. Record a StepResult (completed | failed | skipped).
  5. Build a DataCard from successful results for frontend rendering.

If a step fails and later steps depend on it, those dependent steps are skipped
(status="skipped", error="dependency failed").

State reads:  plan_steps, (all prior step context available for chaining)
State writes: step_results, data_cards
"""

import json
import logging
import re
from typing import Any

from app.agents.state import AgentState
from app.tools.registry import get_tool

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Input chaining: resolve {{step_N.field.path}} references
# ---------------------------------------------------------------------------

def _get_nested(obj: Any, path: str) -> Any:
    """Walk dot-separated path into a nested dict/list structure."""
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
    """
    Replace {{step_N.field.path}} tokens in a string value.

    If the entire string is a single reference, return the native type from
    the referenced output (int, float, etc.).  Otherwise, do string substitution.
    """
    if not isinstance(value, str):
        return value

    PATTERN = r"\{\{step_(\d+)\.([a-zA-Z0-9_.]+)\}\}"
    matches = re.findall(PATTERN, value)
    if not matches:
        return value

    # Full-string single reference → return native type
    if re.fullmatch(PATTERN, value.strip()):
        step_n, field_path = matches[0]
        step_idx = int(step_n) - 1
        if step_idx < len(completed_results):
            output = completed_results[step_idx].get("output") or {}
            return _get_nested(output, field_path)
        return None

    # Partial string with one or more references → string substitution
    result = value
    for step_n, field_path in matches:
        step_idx = int(step_n) - 1
        ref_value = None
        if step_idx < len(completed_results):
            output = completed_results[step_idx].get("output") or {}
            ref_value = _get_nested(output, field_path)
        result = result.replace(
            f"{{{{step_{step_n}.{field_path}}}}}",
            str(ref_value) if ref_value is not None else "",
        )
    return result


def _resolve_inputs(inputs: Any, completed_results: list[dict]) -> Any:
    """Recursively resolve chain references in the inputs structure."""
    if isinstance(inputs, dict):
        return {k: _resolve_inputs(v, completed_results) for k, v in inputs.items()}
    if isinstance(inputs, list):
        return [_resolve_inputs(item, completed_results) for item in inputs]
    if isinstance(inputs, str):
        return _interpolate_value(inputs, completed_results)
    return inputs


# ---------------------------------------------------------------------------
# Data card builder
# ---------------------------------------------------------------------------

_CARD_META: dict[str, dict] = {
    "purchase_retain_life_insurance_in_super": {
        "type": "life_in_super_analysis",
        "title": "Life Insurance in Super",
        "display_hint": "summary_with_actions",
    },
    "purchase_retain_life_tpd_policy": {
        "type": "life_tpd_recommendation",
        "title": "Life & TPD Policy Analysis",
        "display_hint": "recommendation_card",
    },
    "purchase_retain_income_protection_policy": {
        "type": "ip_recommendation",
        "title": "Income Protection Analysis",
        "display_hint": "recommendation_card",
    },
    "purchase_retain_ip_in_super": {
        "type": "ip_in_super_analysis",
        "title": "Income Protection in Super",
        "display_hint": "summary_with_actions",
    },
    "purchase_retain_trauma_ci_policy": {
        "type": "trauma_recommendation",
        "title": "Trauma / Critical Illness Analysis",
        "display_hint": "recommendation_card",
    },
    "tpd_policy_assessment": {
        "type": "tpd_assessment",
        "title": "TPD Policy Assessment",
        "display_hint": "gap_analysis_card",
    },
    "purchase_retain_tpd_in_super": {
        "type": "tpd_in_super_analysis",
        "title": "TPD in Super Analysis",
        "display_hint": "summary_with_actions",
    },
}


def _build_data_card(tool_name: str, step_id: str, output: dict) -> dict:
    meta = _CARD_META.get(tool_name, {
        "type": "generic_tool_result",
        "title": tool_name.replace("_", " ").title(),
        "display_hint": "table",
    })
    return {
        **meta,
        "step_id": step_id,
        "tool_name": tool_name,
        "data": output,
    }


# ---------------------------------------------------------------------------
# Dependency check
# ---------------------------------------------------------------------------

def _has_failed_dependency(step: dict, results_by_id: dict[str, dict]) -> bool:
    """Return True if any step this step depends on has failed."""
    for dep_id in step.get("depends_on", []):
        dep = results_by_id.get(dep_id)
        if dep and dep["status"] == "failed":
            return True
    return False


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def execute_steps(state: AgentState) -> dict:
    """
    Execute each step in the plan sequentially.

    Reads:  plan_steps
    Writes: step_results, data_cards
    """
    plan_steps: list[dict] = state.get("plan_steps", [])
    completed_results: list[dict] = []   # ordered, for chaining
    results_by_id: dict[str, dict] = {}  # for dependency lookup

    for step in plan_steps:
        step_id = step["step_id"]
        tool_name = step["tool_name"]
        description = step.get("description", "")

        logger.info("execute_steps: running %s (%s)", step_id, tool_name)

        # ---- Direct response steps are informational — skip tool execution ----
        if tool_name == "direct_response":
            result: dict = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "skipped",
                "output": None,
                "data_card": None,
                "error": None,
            }
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        # ---- Check dependency failures ----
        if _has_failed_dependency(step, results_by_id):
            result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "skipped",
                "output": None,
                "data_card": None,
                "error": "Skipped: a required dependency step failed.",
            }
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        # ---- Resolve chain references in inputs ----
        raw_inputs = step.get("inputs", {})
        resolved_inputs = _resolve_inputs(raw_inputs, completed_results)

        # ---- Look up and execute tool ----
        tool = get_tool(tool_name)
        if not tool:
            result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "failed",
                "output": None,
                "data_card": None,
                "error": f"Tool '{tool_name}' is not registered.",
            }
            logger.warning("execute_steps: unknown tool '%s' in step %s", tool_name, step_id)
            completed_results.append(result)
            results_by_id[step_id] = result
            continue

        try:
            output = tool.execute(resolved_inputs)
            data_card = _build_data_card(tool_name, step_id, output)
            result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "completed",
                "output": output,
                "data_card": data_card,
                "error": None,
            }
            logger.info("execute_steps: %s completed successfully", step_id)
        except Exception as exc:
            logger.exception("execute_steps: %s raised %s", step_id, exc)
            result = {
                "step_id": step_id,
                "tool_name": tool_name,
                "description": description,
                "status": "failed",
                "output": None,
                "data_card": None,
                "error": str(exc),
            }

        completed_results.append(result)
        results_by_id[step_id] = result

    # Collect data cards from all successful steps
    data_cards = [r["data_card"] for r in completed_results if r.get("data_card")]

    return {
        "step_results": completed_results,
        "data_cards": data_cards,
    }
