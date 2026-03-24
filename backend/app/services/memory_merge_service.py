"""
memory_merge_service.py — Deterministic merge engine for client memory.

Merge rules (in priority order):
  1. correction  — field in delta._meta.corrections: overwrite, confidence=1.0, status="confirmed"
  2. uncertain   — field in delta._meta.uncertain_fields: write/update, confidence=0.6, status="tentative"
  3. revoke      — field in delta._meta.revoked_fields: set None/clear, status="cleared"
  4. plain update — field present in delta but not in any _meta list: overwrite, confidence=1.0, status="confirmed"
  5. no mention  — field absent from delta: LEAVE UNTOUCHED (critical — prevents data loss)

List fields use set-union semantics: new items are appended, existing are preserved.
Revoke of a list field clears it entirely.

Extractor failure: caller must NOT call merge; existing memory is returned unchanged.

Also provides: build_tool_input_from_memory(tool_name, memory) — maps canonical memory
to the per-tool nested input schema used by the existing tool implementations.
"""

import copy
import logging
from typing import Any

from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)

# Fields that use list / set-union semantics
_LIST_FIELDS: set[str] = {
    "health.medical_conditions",
    "health.current_medications",
    "health.hazardous_activities",
    "insurance.cover_types",
    "insurance.trauma_covered_conditions",
}

# Confidence levels
_CONFIDENCE_CONFIRMED = 1.0
_CONFIDENCE_UNCERTAIN = 0.6


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_nested(d: dict, section: str, field: str, value: Any) -> None:
    """Write d[section][field] = value, creating section dict if needed."""
    if section not in d:
        d[section] = {}
    d[section][field] = value


def _get_nested(d: dict, section: str, field: str) -> Any:
    return d.get(section, {}).get(field)


def _union_list(existing: list | None, incoming: list | None) -> list:
    """Return the ordered union of two lists (existing order preserved, new appended)."""
    existing = existing or []
    incoming = incoming or []
    seen = set(str(x) for x in existing)
    result = list(existing)
    for item in incoming:
        if str(item) not in seen:
            result.append(item)
            seen.add(str(item))
    return result


# ---------------------------------------------------------------------------
# Core merge engine
# ---------------------------------------------------------------------------

def merge_delta(
    current_memory: dict,
    delta: dict,
    source_message_id: str,
) -> tuple[dict, list[dict]]:
    """
    Apply delta to current_memory using deterministic merge rules.

    Returns:
        updated_memory  : deep copy of memory with all changes applied
        memory_events   : list of event dicts ready for MemoryEventRepository.create_many()
    """
    memory = copy.deepcopy(current_memory)
    client_facts = memory.setdefault("client_facts", {
        "personal": {}, "financial": {}, "insurance": {}, "health": {}, "goals": {}
    })
    field_meta = memory.setdefault("field_meta", {})
    events: list[dict] = []
    now = utc_now()

    # Parse _meta annotations
    meta = delta.get("_meta") or {}
    corrections_set: set[str] = {
        c["field_path"] for c in meta.get("corrections", []) if "field_path" in c
    }
    uncertain_set: set[str] = {
        u["field_path"] for u in meta.get("uncertain_fields", []) if "field_path" in u
    }
    revoked_set: set[str] = set(meta.get("revoked_fields", []))

    # Build evidence lookup
    corrections_evidence: dict[str, str] = {
        c["field_path"]: c.get("evidence", "") for c in meta.get("corrections", [])
    }
    uncertain_evidence: dict[str, str] = {
        u["field_path"]: u.get("evidence", "") for u in meta.get("uncertain_fields", [])
    }

    # --- Process revocations first ---
    for field_path in revoked_set:
        parts = field_path.split(".", 1)
        if len(parts) != 2:
            continue
        section, field = parts
        old_value = _get_nested(client_facts, section, field)
        _set_nested(client_facts, section, field, None)
        field_meta[field_path] = {
            "source_message_id": source_message_id,
            "updated_at": now,
            "confidence": _CONFIDENCE_CONFIRMED,
            "status": "cleared",
            "evidence_text": "explicitly revoked by user",
        }
        events.append({
            "conversation_id": memory["conversation_id"],
            "source_message_id": source_message_id,
            "event_type": "revoke",
            "field_path": field_path,
            "old_value": old_value,
            "new_value": None,
            "confidence": _CONFIDENCE_CONFIRMED,
            "evidence_text": "explicitly revoked",
        })

    # --- Process field updates ---
    for section in ("personal", "financial", "insurance", "health", "goals"):
        incoming_section = delta.get(section)
        if not isinstance(incoming_section, dict):
            continue

        for field, new_value in incoming_section.items():
            if new_value is None:
                continue  # skip nulls from partial extraction

            field_path = f"{section}.{field}"
            old_value = _get_nested(client_facts, section, field)
            is_list = field_path in _LIST_FIELDS

            # Determine event type and confidence
            if field_path in corrections_set:
                event_type = "correction"
                confidence = _CONFIDENCE_CONFIRMED
                evidence = corrections_evidence.get(field_path, "")
                status = "confirmed"
            elif field_path in uncertain_set:
                event_type = "uncertain"
                confidence = _CONFIDENCE_UNCERTAIN
                evidence = uncertain_evidence.get(field_path, "")
                status = "tentative"
            elif old_value is None:
                event_type = "new_fact"
                confidence = _CONFIDENCE_CONFIRMED
                evidence = ""
                status = "confirmed"
            elif old_value == new_value if not is_list else False:
                # Same value — update metadata freshness but no event needed
                if field_path in field_meta:
                    field_meta[field_path]["updated_at"] = now
                continue
            else:
                event_type = "update"
                confidence = _CONFIDENCE_CONFIRMED
                evidence = ""
                status = "confirmed"

            # Apply the value
            if is_list:
                merged_list = _union_list(
                    old_value if isinstance(old_value, list) else [],
                    new_value if isinstance(new_value, list) else [new_value],
                )
                _set_nested(client_facts, section, field, merged_list)
                final_value = merged_list
            else:
                _set_nested(client_facts, section, field, new_value)
                final_value = new_value

            # Update field metadata
            field_meta[field_path] = {
                "source_message_id": source_message_id,
                "updated_at": now,
                "confidence": confidence,
                "status": status,
                "evidence_text": evidence,
            }

            # Only emit an event if the value actually changed
            value_changed = (old_value != final_value) if not is_list else (set(str(x) for x in (old_value or [])) != set(str(x) for x in final_value))
            if value_changed:
                events.append({
                    "conversation_id": memory["conversation_id"],
                    "source_message_id": source_message_id,
                    "event_type": event_type,
                    "field_path": field_path,
                    "old_value": old_value,
                    "new_value": final_value,
                    "confidence": confidence,
                    "evidence_text": evidence,
                })

    memory["client_facts"] = client_facts
    memory["field_meta"] = field_meta
    return memory, events


# ---------------------------------------------------------------------------
# Deep merge utility (used by classify_intent to blend memory + fresh extraction)
# ---------------------------------------------------------------------------

def deep_merge(base: dict, overrides: dict) -> dict:
    """
    Recursively merge two dicts. overrides takes precedence over base.
    None values in overrides do NOT overwrite base values (they are skipped).
    Empty dicts in overrides do not clear base nested dicts.
    """
    result = dict(base)
    for key, override_val in overrides.items():
        if override_val is None:
            continue
        if isinstance(override_val, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], override_val)
        elif isinstance(override_val, list):
            # Prefer the override list if non-empty; otherwise keep base
            if override_val:
                result[key] = override_val
        else:
            result[key] = override_val
    return result


# ---------------------------------------------------------------------------
# Tool input builder: canonical memory → per-tool nested input schema
# ---------------------------------------------------------------------------

def _v(d: dict, *keys) -> Any:
    """Safe nested get; returns None if any key is absent or d is not a dict."""
    for k in keys:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def build_tool_input_from_memory(tool_name: str, memory: dict) -> dict:
    """
    Map the canonical client_facts in memory to the nested input schema expected
    by the named tool. Returns a (possibly partial) dict — only fields for which
    we have stored values are included. Missing fields are simply absent.

    This output is used as a BASELINE that the fresh LLM extraction overrides.
    """
    facts = memory.get("client_facts") or {}
    p = facts.get("personal") or {}      # personal
    f = facts.get("financial") or {}     # financial
    ins = facts.get("insurance") or {}   # insurance
    h = facts.get("health") or {}        # health
    g = facts.get("goals") or {}         # goals

    def _financial_annual_income() -> Any:
        """
        Backward-compatible income accessor.
        Some extractors store `annual_income` while newer flows use
        `annual_gross_income`; prefer the gross key when present.
        """
        return f.get("annual_gross_income", f.get("annual_income"))

    def _compact(d: dict) -> dict:
        """Remove keys with None values from a flat dict."""
        return {k: v for k, v in d.items() if v is not None}

    def _compact_nested(d: dict) -> dict:
        """Remove None-valued keys at all levels; drop empty sub-dicts."""
        result = {}
        for k, v in d.items():
            if isinstance(v, dict):
                sub = _compact_nested(v)
                if sub:
                    result[k] = sub
            elif v is not None:
                result[k] = v
        return result

    if tool_name == "purchase_retain_life_tpd_policy":
        raw = {
            "client": {
                "age": p.get("age"),
                "annualGrossIncome": _financial_annual_income(),
                "numberOfDependants": p.get("dependants"),
                "dateOfBirth": p.get("date_of_birth"),
            },
            "existingPolicy": {
                "hasExistingPolicy": ins.get("has_existing_policy"),
                "lifeSumInsured": ins.get("life_sum_insured"),
                "tpdSumInsured": ins.get("tpd_sum_insured"),
                "annualPremium": ins.get("annual_premium"),
                "insurerName": ins.get("insurer_name"),
                "tpdDefinition": ins.get("tpd_definition"),
            },
            "financialPosition": {
                "totalLiabilities": f.get("total_liabilities"),
                "liquidAssets": f.get("liquid_assets"),
            },
            "health": {
                "height": h.get("height_m"),
                "weight": h.get("weight_kg"),
                "isSmoker": p.get("is_smoker"),
                "conditions": h.get("medical_conditions") or None,
            },
        }
        return _compact_nested(raw)

    if tool_name == "purchase_retain_life_insurance_in_super":
        raw = {
            "member": {
                "age": p.get("age"),
                "annualIncome": _financial_annual_income(),
                "marginalTaxRate": f.get("marginal_tax_rate"),
                "employmentStatus": p.get("employment_status"),
                "hasDependants": p.get("has_dependants"),
                "cashflowPressure": g.get("cashflow_pressure"),
                "wantsAffordability": g.get("affordability_is_concern"),
                "wantsInsideSuper": ins.get("in_super"),
                "existingInsuranceNeedsEstimate": ins.get("life_sum_insured"),
            },
            "fund": {
                "fundType": f.get("fund_type"),
                "fundName": f.get("fund_name"),
                "isMySuperProduct": f.get("is_mysuper"),
                "accountBalance": f.get("super_balance"),
                "receivedAmountInLast16Months": f.get("received_contributions_last_16m"),
            },
            "existingCover": {
                "hasExistingLifeCover": ins.get("has_existing_policy"),
                "lifeSumInsured": ins.get("life_sum_insured"),
                "annualPremium": ins.get("annual_premium"),
                "accountInactiveMonths": f.get("account_inactive_months"),
                "hasOptedIn": ins.get("has_opted_in"),
                "coverTypesPresent": ins.get("cover_types") or None,
            },
            "health": {
                "heightCm": h.get("height_cm"),
                "weightKg": h.get("weight_kg"),
                "existingMedicalConditions": h.get("medical_conditions") or None,
                "currentMedications": h.get("current_medications") or None,
                "isSmoker": p.get("is_smoker"),
            },
            "adviceContext": {
                "yearsToRetirement": f.get("years_to_retirement"),
                "estimatedAnnualPremium": ins.get("annual_premium"),
                "currentMonthlySurplusAfterExpenses": f.get("monthly_surplus"),
            },
        }
        return _compact_nested(raw)

    if tool_name == "purchase_retain_income_protection_policy":
        raw = {
            "client": {
                "age": p.get("age"),
                "annualGrossIncome": _financial_annual_income(),
                "annualNetIncome": f.get("annual_net_income"),
                "occupationClass": p.get("occupation_class"),
                "occupation": p.get("occupation"),
                "isSmoker": p.get("is_smoker"),
                "dateOfBirth": p.get("date_of_birth"),
            },
            "existingPolicy": {
                "hasExistingPolicy": ins.get("has_existing_policy"),
                "insurerName": ins.get("insurer_name"),
                "waitingPeriodWeeks": ins.get("ip_waiting_period_weeks"),
                "benefitPeriodMonths": ins.get("ip_benefit_period_months"),
                "monthlyBenefit": ins.get("ip_monthly_benefit"),
                "annualPremium": ins.get("annual_premium"),
                "occupationDefinition": ins.get("ip_occupation_definition"),
                "stepDownApplies": ins.get("ip_has_step_down"),
                "hasIndexation": ins.get("ip_has_indexation"),
                "hasPremiumWaiver": ins.get("ip_has_premium_waiver"),
            },
            "goals": {
                "wantsReplacement": g.get("wants_replacement"),
                "wantsRetention": g.get("wants_retention"),
                "affordabilityIsConcern": g.get("affordability_is_concern"),
                "employerSickPayWeeks": ins.get("ip_employer_sick_pay_weeks"),
                "wantsOwnOccupationDefinition": g.get("wants_own_occupation"),
                "wantsLongBenefitPeriod": g.get("wants_long_benefit_period"),
                "wantsIndexation": g.get("wants_indexation"),
            },
            "financialPosition": {
                "monthlyExpenses": f.get("monthly_expenses"),
                "liquidAssets": f.get("liquid_assets"),
                "mortgageBalance": f.get("mortgage_balance"),
            },
        }
        return _compact_nested(raw)

    if tool_name == "purchase_retain_ip_in_super":
        raw = {
            "member": {
                "age": p.get("age"),
                "employmentStatus": p.get("employment_status"),
                "weeklyHoursWorked": p.get("weekly_hours_worked"),
                "annualGrossIncome": _financial_annual_income(),
                "marginalTaxRate": f.get("marginal_tax_rate"),
                "employmentCeasedDate": p.get("employment_ceased_date"),
                "wantsInsideSuper": ins.get("in_super"),
            },
            "fund": {
                "fundType": f.get("fund_type"),
                "accountBalance": f.get("super_balance"),
                "receivedAmountInLast16Months": f.get("received_contributions_last_16m"),
            },
            "existingCover": {
                "hasExistingIPCover": ins.get("has_existing_policy"),
                "monthlyBenefit": ins.get("ip_monthly_benefit"),
                "waitingPeriodDays": ins.get("ip_waiting_period_days"),
                "benefitPeriodMonths": ins.get("ip_benefit_period_months"),
                "annualPremium": ins.get("annual_premium"),
                "occupationDefinition": ins.get("ip_occupation_definition"),
                "portabilityClauseAvailable": ins.get("ip_portability_available"),
            },
            "elections": {
                "optedInToRetainInsurance": ins.get("opted_in_to_retain"),
                "optedOutOfInsurance": ins.get("opted_out_of_insurance"),
            },
            "adviceContext": {
                "yearsToRetirement": f.get("years_to_retirement"),
                "needForOwnOccupationDefinition": g.get("wants_own_occupation"),
                "retirementPriorityHigh": g.get("retirement_priority_high"),
                "contributionCapPressure": g.get("contribution_cap_pressure"),
            },
        }
        return _compact_nested(raw)

    if tool_name == "tpd_policy_assessment":
        raw = {
            "client": {
                "age": p.get("age"),
                "annualGrossIncome": _financial_annual_income(),
                "occupationClass": p.get("occupation_class"),
                "occupation": p.get("occupation"),
                "isSmoker": p.get("is_smoker"),
                "yearsToRetirement": f.get("years_to_retirement"),
            },
            "existingPolicy": {
                "hasExistingPolicy": ins.get("has_existing_policy"),
                "insurerName": ins.get("insurer_name"),
                "tpdSumInsured": ins.get("tpd_sum_insured"),
                "annualPremium": ins.get("annual_premium"),
                "tpdDefinition": ins.get("tpd_definition"),
                "inSuper": ins.get("in_super"),
                "isGrandfathered": ins.get("is_grandfathered"),
                "policyLapsed": ins.get("policy_lapsed"),
                "monthsSinceLapse": ins.get("months_since_lapse"),
                "policyAgeYears": ins.get("policy_age_years"),
                "accountInactiveMonths": f.get("account_inactive_months"),
                "hasOptedIn": ins.get("has_opted_in"),
            },
            "health": {
                "existingMedicalConditions": h.get("medical_conditions") or None,
                "hazardousActivities": h.get("hazardous_activities") or None,
                "isSmoker": p.get("is_smoker"),
            },
            "financialPosition": {
                "mortgageBalance": f.get("mortgage_balance"),
                "liquidAssets": f.get("liquid_assets"),
                "monthlyExpenses": f.get("monthly_expenses"),
            },
            "goals": {
                "wantsReplacement": g.get("wants_replacement"),
                "wantsRetention": g.get("wants_retention"),
                "wantsOwnOccupation": g.get("wants_own_occupation"),
                "affordabilityIsConcern": g.get("affordability_is_concern"),
            },
        }
        return _compact_nested(raw)

    if tool_name == "purchase_retain_trauma_ci_policy":
        raw = {
            "client": {
                "age": p.get("age"),
                "annualGrossIncome": _financial_annual_income(),
                "isSmoker": p.get("is_smoker"),
                "occupationClass": p.get("occupation_class"),
                "occupation": p.get("occupation"),
                "dateOfBirth": p.get("date_of_birth"),
            },
            "existingPolicy": {
                "hasExistingPolicy": ins.get("has_existing_policy"),
                "insurerName": ins.get("insurer_name"),
                "sumInsured": ins.get("trauma_sum_insured"),
                "annualPremium": ins.get("annual_premium"),
                "hasAdvancementBenefit": ins.get("trauma_has_advancement"),
            },
            "health": {
                "height": h.get("height_m"),
                "weight": h.get("weight_kg"),
                "conditions": h.get("medical_conditions") or None,
            },
            "financialPosition": {
                "totalLiabilities": f.get("total_liabilities"),
                "liquidAssets": f.get("liquid_assets"),
                "mortgageBalance": f.get("mortgage_balance"),
                "monthlyExpenses": f.get("monthly_expenses"),
            },
            "goals": {
                "wantsReplacement": g.get("wants_replacement"),
                "wantsRetention": g.get("wants_retention"),
                "affordabilityIsConcern": g.get("affordability_is_concern"),
                "wantsAdvancementBenefit": g.get("wants_advancement_benefit"),
                "wantsMultiClaimRider": g.get("wants_multi_claim_rider"),
            },
        }
        return _compact_nested(raw)

    if tool_name == "purchase_retain_tpd_in_super":
        raw = {
            "member": {
                "age": p.get("age"),
                "annualGrossIncome": _financial_annual_income(),
                "marginalTaxRate": f.get("marginal_tax_rate"),
                "employmentStatus": p.get("employment_status"),
                "weeklyHoursWorked": p.get("weekly_hours_worked"),
                "occupation": p.get("occupation"),
                "occupationClass": p.get("occupation_class"),
                "hasDependants": p.get("has_dependants"),
                "numberOfDependants": p.get("dependants"),
                "dateOfBirth": p.get("date_of_birth"),
            },
            "fund": {
                "fundType": f.get("fund_type"),
                "accountBalance": f.get("super_balance"),
                "receivedAmountInLast16Months": f.get("received_contributions_last_16m"),
                "accountInactiveMonths": f.get("account_inactive_months"),
                "hasOptedIn": ins.get("has_opted_in"),
            },
            "existingCover": {
                "hasExistingTPDCover": ins.get("has_existing_policy"),
                "tpdSumInsured": ins.get("tpd_sum_insured"),
                "annualPremium": ins.get("annual_premium"),
                "coverIsInsideSuper": ins.get("in_super"),
                "coverTypesPresent": ins.get("cover_types") or None,
            },
            "health": {
                "existingMedicalConditions": h.get("medical_conditions") or None,
                "hazardousActivities": h.get("hazardous_activities") or None,
                "isSmoker": p.get("is_smoker"),
            },
            "financialPosition": {
                "mortgageBalance": f.get("mortgage_balance"),
                "liquidAssets": f.get("liquid_assets"),
            },
            "adviceContext": {
                "yearsToRetirement": f.get("years_to_retirement"),
                "retirementDragConcern": g.get("retirement_priority_high"),
            },
        }
        return _compact_nested(raw)

    # Unknown tool: return empty (safe fallback)
    logger.warning("build_tool_input_from_memory: unknown tool '%s', returning empty", tool_name)
    return {}
