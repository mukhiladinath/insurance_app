"""
distill_advisory_node.py — Post-run advisory conclusion extraction.

After execute_steps completes, this node:

  1. For each COMPLETED tool step, extracts a structured advisory conclusion
     using deterministic field extraction (no LLM cost for most tools).
  2. Writes each conclusion to the agent_workspace.advisory_notes MongoDB
     document for this conversation (one entry per tool, overwritten on re-run).
  3. Optionally writes agent working notes (scratch_pad entries) when the
     summarize node has flagged observations.

WHY
---
Without this node, once a conversation ends its analytical conclusions are
lost — only raw client facts (age, income, etc.) survive in memory. Next session
the agent would need to re-run all tools to know "we decided to REPLACE the TPD
policy". This node makes those decisions persistent and instantly retrievable.

Advisory note schema (one per tool_name):
  {
    verdict:        str    — top-level outcome e.g. "REPLACE" / "RETAIN" / "PERMITTED"
    recommendation: str    — one-sentence recommendation
    key_numbers:    dict   — important figures from the output
    key_findings:   str    — 2-3 sentence summary of the reasoning
    analysed_at:    str    — ISO timestamp
    agent_run_id:   str
  }

State reads:  step_results, plan_steps, conversation_id, agent_run_id
State writes: (nothing — writes directly to MongoDB)
"""

import logging
from datetime import timezone, datetime
from typing import Any

from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.advisory_notes_repository import AdvisoryNotesRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Deterministic extractors per tool
# Each extractor receives the raw tool output dict and returns an advisory note.
# ---------------------------------------------------------------------------

def _extract_life_in_super(output: dict) -> dict:
    legal = output.get("legal_status", "UNKNOWN")
    placement = (output.get("placement_assessment") or {}).get("recommendation", "UNKNOWN")
    coverage = output.get("coverage_needs") or {}
    sum_insured = coverage.get("recommended_sum_insured") or coverage.get("life_cover_need")
    actions = output.get("member_actions") or []
    high_priority = [a["action"] for a in actions if a.get("priority") == "HIGH"]

    return {
        "verdict": legal,
        "recommendation": f"Placement: {placement}",
        "key_numbers": {
            "recommended_sum_insured": sum_insured,
            "legal_status": legal,
        },
        "key_findings": (
            f"Legal status: {legal}. Placement recommendation: {placement}. "
            + (f"High-priority actions: {'; '.join(high_priority[:2])}" if high_priority else "")
        ).strip(),
    }


def _extract_life_tpd(output: dict) -> dict:
    rec = output.get("recommendation") or {}
    rec_type = rec.get("type", "UNKNOWN")
    life_need = output.get("life_need") or {}
    tpd_need = output.get("tpd_need") or {}

    return {
        "verdict": rec_type,
        "recommendation": rec.get("summary", rec_type),
        "key_numbers": {
            "recommended_life_sum": life_need.get("recommended_sum"),
            "recommended_tpd_sum": tpd_need.get("recommended_sum"),
            "existing_life_cover": output.get("existing_life_cover"),
            "existing_tpd_cover": output.get("existing_tpd_cover"),
        },
        "key_findings": rec.get("rationale", ""),
    }


def _extract_income_protection(output: dict) -> dict:
    rec = output.get("recommendation") or {}
    return {
        "verdict": rec.get("type", "UNKNOWN"),
        "recommendation": rec.get("summary", ""),
        "key_numbers": {
            "monthly_benefit_need": output.get("monthly_benefit_need"),
            "replacement_ratio": output.get("replacement_ratio"),
            "recommended_waiting_period": rec.get("waiting_period"),
            "recommended_benefit_period": rec.get("benefit_period"),
        },
        "key_findings": rec.get("rationale", ""),
    }


def _extract_ip_in_super(output: dict) -> dict:
    rec = output.get("recommendation") or {}
    return {
        "verdict": rec.get("type", "UNKNOWN"),
        "recommendation": rec.get("summary", ""),
        "key_numbers": {
            "benefit_need": output.get("benefit_need"),
            "sis_compliant": output.get("sis_compliant"),
        },
        "key_findings": rec.get("rationale", ""),
    }


def _extract_trauma(output: dict) -> dict:
    rec = output.get("recommendation") or {}
    return {
        "verdict": rec.get("type", "UNKNOWN"),
        "recommendation": rec.get("summary", ""),
        "key_numbers": {
            "recommended_sum_insured": output.get("recommended_sum_insured"),
        },
        "key_findings": rec.get("rationale", ""),
    }


def _extract_tpd_assessment(output: dict) -> dict:
    return {
        "verdict": output.get("adequacy_verdict", "UNKNOWN"),
        "recommendation": output.get("recommendation", ""),
        "key_numbers": {
            "existing_tpd_sum": output.get("existing_tpd_sum_insured"),
            "shortfall": (output.get("gap_analysis") or {}).get("shortfall"),
        },
        "key_findings": output.get("analysis_summary", ""),
    }


def _extract_tpd_in_super(output: dict) -> dict:
    rec = output.get("recommendation") or {}
    return {
        "verdict": output.get("legal_status", "UNKNOWN"),
        "recommendation": rec.get("summary", ""),
        "key_numbers": {
            "recommended_sum_insured": output.get("recommended_sum_insured"),
            "sis_compliant": output.get("sis_compliant"),
        },
        "key_findings": rec.get("rationale", ""),
    }


def _generic_extract(output: dict) -> dict:
    """Fallback extractor for unknown tools."""
    return {
        "verdict": output.get("recommendation", output.get("verdict", "COMPLETED")),
        "recommendation": str(output.get("recommendation", "")),
        "key_numbers": {},
        "key_findings": "Tool completed successfully. See data card for details.",
    }


_EXTRACTORS = {
    "purchase_retain_life_insurance_in_super": _extract_life_in_super,
    "purchase_retain_life_tpd_policy":         _extract_life_tpd,
    "purchase_retain_income_protection_policy": _extract_income_protection,
    "purchase_retain_ip_in_super":             _extract_ip_in_super,
    "purchase_retain_trauma_ci_policy":        _extract_trauma,
    "tpd_policy_assessment":                   _extract_tpd_assessment,
    "purchase_retain_tpd_in_super":            _extract_tpd_in_super,
}


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def distill_advisory(state: AgentState) -> dict:
    """
    Extract and persist advisory conclusions from completed step results.

    Reads:  step_results, conversation_id, agent_run_id
    Writes: advisory_notes to MongoDB (no state changes — side-effect only)
    """
    step_results: list[dict] = state.get("step_results", [])
    conversation_id = state.get("conversation_id", "")
    agent_run_id = state.get("agent_run_id", "")

    if not step_results or not conversation_id:
        return {}

    now = datetime.now(timezone.utc).isoformat()

    try:
        db = get_db()
        repo = AdvisoryNotesRepository(db)

        written = 0
        for result in step_results:
            if result.get("status") != "completed":
                continue
            tool_name = result.get("tool_name", "")
            if tool_name in ("direct_response", ""):
                continue

            output = result.get("output") or {}
            extractor = _EXTRACTORS.get(tool_name, _generic_extract)

            try:
                note = extractor(output)
            except Exception as exc:
                logger.warning("distill_advisory: extractor failed for %s: %s", tool_name, exc)
                note = _generic_extract(output)

            note["analysed_at"] = now
            note["agent_run_id"] = agent_run_id

            await repo.upsert_advisory_note(
                conversation_id=conversation_id,
                tool_name=tool_name,
                note=note,
            )
            written += 1
            logger.info(
                "distill_advisory: wrote note for %s (verdict=%s)",
                tool_name, note.get("verdict"),
            )

        if written:
            logger.info(
                "distill_advisory: persisted %d advisory note(s) for conv=%s",
                written, conversation_id,
            )

    except Exception as exc:
        logger.exception("distill_advisory: unexpected error: %s", exc)
        # Non-fatal — the main response is already saved

    return {}  # No state mutations — this node is a pure side-effect
