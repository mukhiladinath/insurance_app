"""
load_pending_clarification.py — Resume a blocked run by loading its frozen state.

When the user submits a clarification answer (resume_token + clarification_answer),
this node:
  1. Loads the pending_clarification document by resume_token.
  2. Restores the frozen plan, step results, and factfind snapshot into state.
  3. The next node (merge_clarification_answer) will patch the missing field.
  4. The plan node re-evaluates; if the answer satisfies all missing fields, execution proceeds.

State reads:  resume_token
State writes: tool_plan, step_results (cached), factfind_snapshot (frozen),
              missing_fields, _pending_clarification_doc
"""

import logging

from app.agents.workspace_state import WorkspaceState
from app.db.mongo import get_db
from app.db.repositories.pending_clarification_repository import PendingClarificationRepository

logger = logging.getLogger(__name__)


async def load_pending_clarification(state: WorkspaceState) -> dict:
    """
    Load the frozen run state from a pending clarification record.

    Reads:  resume_token
    Writes: tool_plan, cached_step_results, factfind_snapshot (from frozen snapshot),
            missing_fields, _pending_clarification_doc (for merge node to use)
    """
    resume_token = state.get("resume_token")
    if not resume_token:
        logger.error("load_pending_clarification: no resume_token in state")
        return {"errors": state.get("errors", []) + ["resume_token missing for clarification resume"]}

    try:
        db = get_db()
        repo = PendingClarificationRepository(db)
        doc = await repo.get_by_token(resume_token)

        if not doc:
            logger.warning("load_pending_clarification: token=%s not found", resume_token)
            return {
                "errors": state.get("errors", []) + [f"No pending clarification for token {resume_token}"],
                "clarification_needed": False,
                "tool_plan": [],
            }

        if doc.get("status") != "pending":
            logger.warning(
                "load_pending_clarification: token=%s status=%s (not pending)",
                resume_token, doc.get("status"),
            )
            return {
                "errors": state.get("errors", []) + [f"Clarification {resume_token} is already {doc.get('status')}"],
            }

        frozen_plan = doc.get("frozen_plan", [])
        frozen_steps = doc.get("frozen_step_results", [])
        frozen_snapshot = doc.get("frozen_inputs_snapshot", {})

        # Restore cached step results (steps that completed before the block)
        cached = {r["step_id"]: r for r in frozen_steps if r.get("status") == "completed"}

        logger.info(
            "load_pending_clarification: loaded token=%s plan=%d steps, cached=%d completed steps",
            resume_token, len(frozen_plan), len(cached),
        )

        return {
            "tool_plan": frozen_plan,
            "cached_step_results": cached,
            "factfind_snapshot": frozen_snapshot.get("factfind_snapshot", state.get("factfind_snapshot", {})),
            "ai_context_overrides": frozen_snapshot.get("ai_context_overrides", state.get("ai_context_overrides", {})),
            "missing_fields": doc.get("missing_fields", []),
            "_pending_clarification_doc": doc,  # passed to merge node
        }

    except Exception as exc:
        logger.exception("load_pending_clarification error: %s", exc)
        return {"errors": state.get("errors", []) + [f"Clarification load error: {exc}"]}
