"""
overseer_service.py — Orchestrator for the Overseer Agent.

Call flow:
  1. Run deterministic pre-checks (overseer_rules).
     If a rule fires → return immediately (no LLM cost).

  2. If no rule fired → invoke LLM with a structured JSON prompt.
     Parse the LLM response into OverseerVerdict.

  3. On any LLM failure (exception, bad JSON, validation error)
     → fall back to proceed_with_caution (fail-safe, never blocks the pipeline).

  4. Log every invocation via overseer_logging.

Retry enforcement:
  The service itself does NOT enforce the one-retry limit.
  The caller (overseer_quality_gate node) is responsible for capping retries
  and downgrading retry_* verdicts to proceed_with_caution when the limit
  is exhausted.
"""

from __future__ import annotations

import json
import logging

from app.core.llm import get_chat_model_fresh
from app.services.overseer.overseer_models import (
    MissingField,
    OverseerRequest,
    OverseerVerdict,
)
from app.services.overseer.overseer_logging import log_verdict, timed
from app.services.overseer.overseer_prompt import (
    OVERSEER_SYSTEM_PROMPT,
    build_overseer_user_prompt,
)
from app.services.overseer.overseer_rules import run_deterministic_rules

logger = logging.getLogger(__name__)

# Valid LLM-returnable statuses (retry_* are deterministic-only)
_LLM_VALID_STATUSES = {"proceed", "proceed_with_caution", "ask_user", "reset_context"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _parse_llm_response(raw: str) -> OverseerVerdict:
    """
    Parse the raw LLM string into OverseerVerdict.
    Raises ValueError on any structural problem.
    """
    # Strip possible markdown code fences
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Remove first and last fence lines
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    data = json.loads(text)

    status = data.get("status", "")
    if status not in _LLM_VALID_STATUSES:
        raise ValueError(f"LLM returned invalid status: {status!r}")

    return OverseerVerdict(
        status=status,  # type: ignore[arg-type]
        reason=data.get("reason", "LLM evaluation complete."),
        caution_notes=data.get("caution_notes", []),
        suggested_question=data.get("suggested_question"),
        overseer_source="llm",
    )


def _fallback_verdict(reason: str) -> OverseerVerdict:
    return OverseerVerdict(
        status="proceed_with_caution",
        reason=reason,
        caution_notes=["Overseer evaluation unavailable; proceeding with caution."],
        overseer_source="fallback",
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def run_overseer(req: OverseerRequest) -> OverseerVerdict:
    """
    Evaluate a tool execution turn and return a typed verdict.

    This is the single public entry point.  It is async because the LLM
    path is async; the deterministic path completes synchronously.
    """
    with timed() as elapsed:
        verdict = await _evaluate(req)

    log_verdict(
        tool_name=req.tool_name,
        intent=req.intent,
        verdict=verdict,
        retry_count=req.retry_count,
        latency_ms=elapsed.get("ms"),
    )
    return verdict


async def _evaluate(req: OverseerRequest) -> OverseerVerdict:
    # ------------------------------------------------------------------
    # Step 1: deterministic rules (no LLM, always fast)
    # ------------------------------------------------------------------
    deterministic = run_deterministic_rules(req)
    if deterministic is not None:
        return deterministic

    # ------------------------------------------------------------------
    # Step 2: LLM evaluation
    # ------------------------------------------------------------------
    try:
        llm = get_chat_model_fresh(temperature=0.0)

        user_prompt = build_overseer_user_prompt(
            tool_name=req.tool_name,
            tool_result=req.tool_result or {},
            extracted_tool_input=req.extracted_tool_input or {},
            intent=req.intent,
            user_message=req.user_message,
        )

        messages = [
            {"role": "system", "content": OVERSEER_SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt},
        ]

        response = await llm.ainvoke(messages)
        raw_content = response.content if hasattr(response, "content") else str(response)

        verdict = _parse_llm_response(raw_content)
        return verdict

    except Exception as exc:
        logger.warning("overseer LLM evaluation failed: %s", exc)
        return _fallback_verdict(f"Overseer LLM unavailable ({type(exc).__name__}); proceeding with caution.")
