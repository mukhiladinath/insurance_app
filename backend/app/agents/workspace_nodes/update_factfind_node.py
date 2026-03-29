"""
update_factfind_node.py — Handle explicit factfind update requests from the AI bar.

When active_mode = "update_factfind" or "edit_ai_context", the user is asking
to change a specific value (e.g. "Update John's income to $180,000").

This node:
  1. Uses the LLM to extract the field path and new value from the message.
  2. Validates the value (basic type/range checks).
  3. Patches the factfind via factfind_repository.
  4. Returns a confirmation response.

State reads:  user_message, factfind_snapshot, client_id, active_mode,
              ai_context_overrides, workspace_id
State writes: factfind_snapshot (patched), final_response, ui_actions
"""

import json
import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.workspace_state import WorkspaceState
from app.core.llm import get_chat_model
from app.db.mongo import get_db
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
You are an insurance data extraction assistant. The user has asked to update a \
specific client fact-find field or AI context value.

Extract the field path and new value from their message.

Valid factfind field paths (use section.field_name format):
  personal: age, date_of_birth, gender, smoker, occupation, occupation_class,
            residency_status, state, dependants
  financial: annual_gross_income, monthly_income, monthly_expenses, super_balance,
             investment_assets, other_assets, mortgage_balance, other_debts
  insurance: existing_life_cover, existing_tpd_cover, existing_ip_cover,
             existing_trauma_cover, current_insurer, fund_type,
             ip_waiting_period_days, ip_benefit_period
  health: health_conditions, medications, family_history, height_cm, weight_kg
  goals: primary_goal, retirement_age, risk_tolerance

Valid AI context override paths:
  assumptions.risk_profile, assumptions.inflation_rate, assumptions.investment_return
  scratchpad (list of strings)

Return ONLY valid JSON:
{{
  "target": "factfind" | "ai_context",
  "changes": {{
    "field_path": value
  }}
}}
"""

_EXTRACT_HUMAN = """\
## CURRENT KNOWN VALUES
{current_values}

## USER REQUEST
{user_message}

Extract the field(s) to update.
"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


async def update_factfind_node(state: WorkspaceState) -> dict:
    """
    Parse and apply a factfind / AI context update from the AI bar.

    Reads:  user_message, factfind_snapshot, client_id, active_mode,
            ai_context_overrides, workspace_id
    Writes: factfind_snapshot (updated), final_response, ui_actions
    """
    user_message = state.get("user_message", "")
    factfind_snapshot = dict(state.get("factfind_snapshot", {}))
    client_id = state.get("client_id", "")
    workspace_id = state.get("workspace_id", "")
    active_mode = state.get("active_mode", "update_factfind")

    current_values_str = (
        "\n".join(f"  {k}: {v}" for k, v in factfind_snapshot.items())
        if factfind_snapshot else "(none)"
    )

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM),
            HumanMessage(content=_EXTRACT_HUMAN.format(
                current_values=current_values_str,
                user_message=user_message,
            )),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _extract_json(raw)
        target = parsed.get("target", "factfind")
        changes: dict = parsed.get("changes", {})
    except Exception as exc:
        logger.exception("update_factfind_node: LLM extraction failed: %s", exc)
        changes = {}
        target = "factfind"

    if not changes:
        return {
            "final_response": "I couldn't determine which field to update. Please be more specific, e.g. 'Set the client's age to 42' or 'Update annual income to $180,000'.",
        }

    db = get_db()
    updated_items: list[str] = []

    if target == "factfind":
        try:
            repo = FactfindRepository(db)
            await repo.patch_fields(
                client_id=client_id,
                changes=changes,
                source="ai_extracted",
                source_ref=state.get("run_id", ""),
                changed_by="agent",
            )
            factfind_snapshot.update(changes)
            updated_items = list(changes.keys())
        except Exception as exc:
            logger.exception("update_factfind_node: patch failed: %s", exc)
            return {"errors": state.get("errors", []) + [f"Factfind update error: {exc}"]}

    elif target == "ai_context" and workspace_id:
        try:
            ws_repo = WorkspaceRepository(db)
            await ws_repo.patch_ai_context_overrides(client_id, changes)
            updated_items = list(changes.keys())
        except Exception as exc:
            logger.exception("update_factfind_node: AI context patch failed: %s", exc)
            return {"errors": state.get("errors", []) + [f"AI context update error: {exc}"]}

    if not updated_items:
        return {"final_response": "No changes were applied."}

    # Build confirmation response
    lines = ["I've updated the following:"]
    for field_path, value in changes.items():
        label = field_path.replace(".", " › ").replace("_", " ").title()
        lines.append(f"- **{label}**: {value}")

    final_response = "\n".join(lines)

    ui_actions = [{"type": "refresh_factfind_panel", "payload": {}}]
    if target == "ai_context":
        ui_actions = [{"type": "refresh_ai_context", "payload": {}}]

    logger.info(
        "update_factfind_node: updated %s for client=%s: %s",
        target, client_id, updated_items,
    )

    return {
        "factfind_snapshot": factfind_snapshot,
        "final_response": final_response,
        "ui_actions": ui_actions,
    }
