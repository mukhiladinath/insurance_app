"""
persist_pending_clarification.py — Freeze the current plan and save a pending clarification.

When the planner cannot proceed due to missing critical information, this node:
  1. Creates a pending_clarifications document with the frozen plan, frozen step
     results (any steps that completed before the block), and a resume_token.
  2. Expires any prior pending clarifications for this client.
  3. Sets the run status to "awaiting_clarification" in agent_runs.
  4. Populates ui_actions so the frontend highlights the missing fields.

State reads:  client_id, workspace_id, run_id, conversation_id,
              clarification_question, missing_fields, tool_plan, step_results,
              factfind_snapshot, ai_context_overrides
State writes: (writes to MongoDB; sets no state fields — resume_token is returned
              via the API response directly from the clarification doc)
"""

import logging

from app.agents.workspace_state import WorkspaceState
from app.db.mongo import get_db
from app.db.repositories.pending_clarification_repository import PendingClarificationRepository

logger = logging.getLogger(__name__)


async def persist_pending_clarification(state: WorkspaceState) -> dict:
    """
    Freeze the plan and create a pending clarification record.

    Returns state updates:
      - ui_actions: highlight missing fields in the frontend
      - (resume_token is stored in the clarification doc; service layer reads it)
    """
    client_id = state.get("client_id", "")
    workspace_id = state.get("workspace_id", "")
    run_id = state.get("run_id", "")
    conversation_id = state.get("conversation_id", "")
    question = state.get("clarification_question", "")
    missing_fields = state.get("missing_fields", [])
    tool_plan = state.get("tool_plan", [])
    step_results = state.get("step_results", [])

    # Snapshot the inputs used so far
    frozen_inputs_snapshot = {
        "factfind_snapshot": state.get("factfind_snapshot", {}),
        "ai_context_overrides": state.get("ai_context_overrides", {}),
    }

    try:
        db = get_db()
        repo = PendingClarificationRepository(db)

        # Expire any existing pending clarification for this client
        await repo.expire_old(client_id)

        # Create the new pending clarification
        clarification_doc = await repo.create(
            client_id=client_id,
            workspace_id=workspace_id,
            run_id=run_id,
            conversation_id=conversation_id,
            question=question,
            missing_fields=missing_fields,
            frozen_plan=tool_plan,
            frozen_step_results=step_results,
            frozen_inputs_snapshot=frozen_inputs_snapshot,
        )

        resume_token = clarification_doc.get("resume_token", "")
        logger.info(
            "persist_pending_clarification: token=%s for client=%s",
            resume_token, client_id,
        )

        # Build UI actions to highlight missing fields in the factfind panel
        missing_field_paths = [f.get("field_path", "") for f in missing_fields if f.get("field_path")]
        ui_actions = []
        if missing_field_paths:
            ui_actions.append({
                "type": "highlight_missing_fields",
                "payload": {"field_paths": missing_field_paths},
            })

        return {
            "ui_actions": ui_actions,
            # Store resume_token in state so the service layer can return it in the response
            "pending_resume_token": resume_token,
        }

    except Exception as exc:
        logger.exception("persist_pending_clarification error: %s", exc)
        return {
            "errors": state.get("errors", []) + [f"Clarification persist error: {exc}"],
        }
