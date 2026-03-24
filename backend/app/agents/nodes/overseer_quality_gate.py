"""
overseer_quality_gate.py — LangGraph node: run the Overseer Agent.

Sits between execute_tool and compose_response.

Responsibilities:
  - Build an OverseerRequest from current state.
  - Call run_overseer() to get a typed verdict.
  - Enforce the one-retry-per-turn maximum:
      If verdict is retry_* and retry_count >= 1, downgrade to proceed_with_caution.
  - Write verdict fields back into state for downstream nodes (compose_response, router).

State keys written:
  overseer_status       : str   — verdict status code
  overseer_reason       : str   — one-line reason
  overseer_caution_notes: list  — optional caveats
  overseer_question     : str|None — clarifying question (ask_user path)
  overseer_retry_count  : int   — incremented if a retry is triggered
  overseer_missing_fields: list[dict] — serialised MissingField list
"""

from __future__ import annotations

import logging

from app.agents.state import AgentState
from app.services.overseer import run_overseer, OverseerRequest

logger = logging.getLogger(__name__)

_MAX_RETRIES = 1  # maximum overseer-directed retries per turn


async def overseer_quality_gate(state: AgentState) -> dict:
    """
    Evaluate the tool execution result and return a verdict into state.
    """
    tool_name    = state.get("selected_tool") or ""
    tool_result  = state.get("tool_result")
    tool_error   = state.get("tool_error")
    tool_input   = state.get("extracted_tool_input")
    intent       = state.get("intent", "")
    user_message = state.get("user_message", "")
    messages     = state.get("recent_messages", [])
    retry_count  = state.get("overseer_retry_count", 0)

    req = OverseerRequest(
        tool_name=tool_name,
        tool_result=tool_result,
        tool_error=tool_error,
        extracted_tool_input=tool_input,
        intent=intent,
        user_message=user_message,
        recent_messages=messages,
        retry_count=retry_count,
    )

    try:
        verdict = await run_overseer(req)
    except Exception as exc:
        # Hard fail-safe: if run_overseer itself explodes, proceed with caution
        logger.exception("overseer_quality_gate: unexpected error: %s", exc)
        return {
            "overseer_status":        "proceed_with_caution",
            "overseer_reason":        f"Overseer agent error ({type(exc).__name__}); proceeding with caution.",
            "overseer_caution_notes": ["Overseer unavailable."],
            "overseer_question":      None,
            "overseer_retry_count":   retry_count,
            "overseer_missing_fields": [],
        }

    # ------------------------------------------------------------------
    # Enforce one-retry maximum
    # ------------------------------------------------------------------
    if verdict.status in ("retry_extraction", "retry_tool") and retry_count >= _MAX_RETRIES:
        logger.warning(
            "overseer_quality_gate: retry limit reached (count=%d); "
            "downgrading '%s' to 'proceed_with_caution'",
            retry_count,
            verdict.status,
        )
        verdict = verdict.model_copy(update={
            "status": "proceed_with_caution",
            "reason": f"Retry limit reached after {retry_count} attempt(s). {verdict.reason}",
            "overseer_source": verdict.overseer_source,
        })

    # Increment retry counter if this verdict is a retry instruction
    new_retry_count = retry_count + 1 if verdict.status in ("retry_extraction", "retry_tool") else retry_count

    logger.info(
        "overseer_quality_gate: status=%s source=%s reason=%r",
        verdict.status,
        verdict.overseer_source,
        verdict.reason,
    )

    return {
        "overseer_status":         verdict.status,
        "overseer_reason":         verdict.reason,
        "overseer_caution_notes":  verdict.caution_notes,
        "overseer_question":       verdict.suggested_question,
        "overseer_retry_count":    new_retry_count,
        "overseer_missing_fields": [m.model_dump() for m in verdict.missing_fields],
    }
