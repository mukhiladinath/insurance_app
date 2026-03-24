"""
memory_extractor.py — LLM-based delta fact extraction from a single chat turn.

Strategy:
  - Receives the current user message + up to 2 prior messages for context.
  - Receives a compact summary of already-known client facts.
  - Instructs the LLM to extract ONLY new or changed facts.
  - The LLM must NOT re-extract facts already in the summary unless they are
    being corrected, revised, or are being accompanied by a revocation phrase.
  - Returns a delta dict compatible with memory_merge_service.merge_delta().

Correction detection (tag field in _meta.corrections):
  Look for: "actually", "correction", "I meant", "not X", "sorry, it's", "no wait",
            "let me correct", "I was wrong", "revising"

Uncertainty detection (tag field in _meta.uncertain_fields):
  Look for: "around", "approximately", "about", "roughly", "I think", "maybe",
            "probably", "not sure", "estimate", "ballpark"

Revocation detection (add to _meta.revoked_fields):
  Look for: "ignore", "disregard", "forget what I said about", "remove the",
            "don't include", "scratch that", "take out"

On any exception: return {} so merge_delta is never called with bad input.
Extractor failure MUST NOT clear existing memory.
"""

import json
import logging
from typing import Any

from app.core.llm import get_chat_model_fresh
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical field schema exposed to the LLM extractor
# ---------------------------------------------------------------------------

_EXTRACTION_SYSTEM_PROMPT = """\
You are a precise data extraction assistant for an insurance advisory AI.

Your task: given the CURRENT USER MESSAGE (with optional context), extract ONLY client facts
that are EXPLICITLY stated in the current message and are either NEW or CHANGED compared to
what is already known (shown in Known Facts).

STRICT RULES:
1. Extract ONLY facts EXPLICITLY stated — never infer, derive, or guess.
2. If a fact in Known Facts is NOT mentioned in the current message, do NOT include it.
3. Monetary values must be plain numbers: 300000 (not "$300,000", not "300k").
4. If a fact IS in Known Facts and the current message repeats it unchanged, skip it.
5. For corrections ("actually X", "I meant X", "not Y it's X"): include in _meta.corrections.
6. For uncertain values ("around X", "approximately X", "I think X"): include in _meta.uncertain_fields.
7. For explicit revocations ("ignore X", "disregard X", "forget X"): include in _meta.revoked_fields.
8. Return ONLY a valid JSON object. No markdown fences, no explanation.
9. Omit any section entirely if no fields in that section appear in the message.
10. A field value of null means "not mentioned" — OMIT it instead.

Return this JSON structure (omit empty sections):
{
  "personal": {
    "age": <integer>,
    "date_of_birth": <"YYYY-MM-DD">,
    "gender": <"male"|"female"|"other">,
    "marital_status": <"single"|"married"|"de_facto"|"divorced"|"widowed">,
    "dependants": <integer — number of financial dependants>,
    "has_dependants": <true|false>,
    "occupation": <string>,
    "occupation_class": <"CLASS_1_WHITE_COLLAR"|"CLASS_2_LIGHT_BLUE"|"CLASS_3_BLUE_COLLAR"|"CLASS_4_HAZARDOUS">,
    "employment_status": <"EMPLOYED_FULL_TIME"|"EMPLOYED_PART_TIME"|"SELF_EMPLOYED"|"UNEMPLOYED">,
    "is_smoker": <true|false>,
    "weekly_hours_worked": <number>,
    "employment_ceased_date": <"YYYY-MM-DD">
  },
  "financial": {
    "annual_gross_income": <AUD number>,
    "annual_net_income": <AUD number>,
    "marginal_tax_rate": <decimal 0.0-1.0, e.g. 0.37 for 37%>,
    "super_balance": <AUD number>,
    "fund_type": <"mysuper"|"choice"|"smsf"|"defined_benefit">,
    "fund_name": <string>,
    "is_mysuper": <true|false>,
    "mortgage_balance": <AUD number>,
    "liquid_assets": <AUD number>,
    "total_liabilities": <AUD number>,
    "monthly_expenses": <AUD number>,
    "monthly_surplus": <AUD number>,
    "years_to_retirement": <number>,
    "received_contributions_last_16m": <true|false>,
    "account_inactive_months": <integer>
  },
  "insurance": {
    "has_existing_policy": <true|false>,
    "life_sum_insured": <AUD number>,
    "tpd_sum_insured": <AUD number>,
    "ip_monthly_benefit": <AUD number>,
    "ip_waiting_period_weeks": <integer: 2|4|8|13|26|52>,
    "ip_waiting_period_days": <integer: 30|60|90>,
    "ip_benefit_period_months": <integer: 0 means to-age-65, or 12|24|60>,
    "ip_occupation_definition": <"OWN_OCCUPATION"|"ANY_OCCUPATION"|"ACTIVITIES_OF_DAILY_LIVING">,
    "ip_has_step_down": <true|false>,
    "ip_has_indexation": <true|false>,
    "ip_has_premium_waiver": <true|false>,
    "ip_portability_available": <true|false>,
    "ip_employer_sick_pay_weeks": <integer>,
    "trauma_sum_insured": <AUD number>,
    "annual_premium": <AUD number>,
    "insurer_name": <string>,
    "tpd_definition": <"OWN_OCCUPATION"|"MODIFIED_OWN_OCCUPATION"|"ANY_OCCUPATION"|"ACTIVITIES_OF_DAILY_LIVING">,
    "in_super": <true|false — is cover held inside superannuation?>,
    "is_grandfathered": <true|false>,
    "policy_lapsed": <true|false>,
    "months_since_lapse": <integer>,
    "policy_age_years": <number>,
    "cover_types": [<"DEATH_COVER"|"TOTAL_AND_PERMANENT_DISABILITY"|"INCOME_PROTECTION">],
    "opted_in_to_retain": <true|false>,
    "opted_out_of_insurance": <true|false>,
    "has_opted_in": <true|false>,
    "trauma_waiting_period_days": <integer>,
    "trauma_survival_period_days": <integer>,
    "trauma_covered_conditions": [<string>],
    "trauma_has_advancement": <true|false>
  },
  "health": {
    "height_m": <float — metres e.g. 1.75>,
    "height_cm": <float — centimetres e.g. 175>,
    "weight_kg": <float>,
    "medical_conditions": [<string>],
    "current_medications": [<string>],
    "hazardous_activities": [<string>]
  },
  "goals": {
    "wants_replacement": <true|false>,
    "wants_retention": <true|false>,
    "affordability_is_concern": <true|false>,
    "wants_own_occupation": <true|false>,
    "wants_long_benefit_period": <true|false>,
    "wants_indexation": <true|false>,
    "cashflow_pressure": <true|false>,
    "retirement_priority_high": <true|false>,
    "contribution_cap_pressure": <true|false>,
    "wants_advancement_benefit": <true|false>,
    "wants_multi_claim_rider": <true|false>
  },
  "_meta": {
    "corrections": [
      {"field_path": "<section.field>", "evidence": "<exact phrase from message>"}
    ],
    "uncertain_fields": [
      {"field_path": "<section.field>", "evidence": "<exact phrase from message>"}
    ],
    "revoked_fields": ["<section.field>"]
  }
}"""


def _summarise_known_facts(memory: dict) -> str:
    """
    Produce a compact text summary of the currently known facts for injection
    into the extractor prompt. Keeps the prompt short to avoid token waste.
    """
    facts = memory.get("client_facts") or {}
    lines: list[str] = []

    section_map = {
        "personal": {
            "age": "age",
            "gender": "gender",
            "marital_status": "marital_status",
            "dependants": "dependants",
            "occupation": "occupation",
            "employment_status": "employment_status",
            "is_smoker": "is_smoker",
        },
        "financial": {
            "annual_gross_income": "annual_gross_income",
            "super_balance": "super_balance",
            "fund_name": "fund_name",
            "fund_type": "fund_type",
            "mortgage_balance": "mortgage_balance",
            "liquid_assets": "liquid_assets",
            "marginal_tax_rate": "marginal_tax_rate",
            "years_to_retirement": "years_to_retirement",
        },
        "insurance": {
            "has_existing_policy": "has_existing_policy",
            "insurer_name": "insurer_name",
            "life_sum_insured": "life_sum_insured",
            "tpd_sum_insured": "tpd_sum_insured",
            "ip_monthly_benefit": "ip_monthly_benefit",
            "annual_premium": "annual_premium",
            "tpd_definition": "tpd_definition",
            "in_super": "in_super",
        },
        "health": {
            "weight_kg": "weight_kg",
            "height_m": "height_m",
            "medical_conditions": "medical_conditions",
        },
        "goals": {
            "wants_replacement": "wants_replacement",
            "wants_retention": "wants_retention",
            "affordability_is_concern": "affordability_is_concern",
        },
    }

    for section, field_map in section_map.items():
        section_data = facts.get(section) or {}
        for field in field_map:
            val = section_data.get(field)
            if val is not None:
                lines.append(f"  {section}.{field}: {val}")

    if not lines:
        return "  (none yet)"
    return "\n".join(lines)


async def extract_delta(
    user_message: str,
    context_messages: list[dict],
    current_memory: dict,
) -> dict:
    """
    Extract a memory delta from the current user message.

    Args:
        user_message:      The raw text of the current user message.
        context_messages:  Last 1-2 messages before the user message (for context).
                           Each is a {role, content} dict.
        current_memory:    The full conversation_memory document (may be empty).

    Returns:
        Delta dict with optional sections: personal, financial, insurance, health,
        goals, _meta. Empty dict {} on any failure.
    """
    known_facts_summary = _summarise_known_facts(current_memory)

    context_str = ""
    if context_messages:
        context_str = "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in context_messages[-2:]
        )
        context_str = f"\nRecent context (for understanding only — do NOT re-extract from here):\n{context_str}\n"

    user_content = (
        f"Known facts (skip unless changing):\n{known_facts_summary}\n"
        f"{context_str}\n"
        f"Current message to extract from:\nUSER: {user_message}\n\n"
        "Return extracted JSON delta:"
    )

    model = get_chat_model_fresh(temperature=0.0)

    try:
        response = await model.ainvoke([
            SystemMessage(content=_EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        raw = response.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            parts = raw.split("```", 2)
            raw = parts[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()

        delta = json.loads(raw)
        if not isinstance(delta, dict):
            logger.warning("extract_delta: LLM returned non-dict — ignoring")
            return {}

        logger.debug("extract_delta: extracted sections %s", list(delta.keys()))
        return delta

    except json.JSONDecodeError as exc:
        logger.warning("extract_delta: JSON parse error: %s", exc)
        return {}
    except Exception as exc:
        logger.warning("extract_delta: unexpected error: %s", exc)
        return {}
