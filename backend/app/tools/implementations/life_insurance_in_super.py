"""
life_insurance_in_super.py — Purchase/Retain Life Insurance In Super tool.

Python port of the TypeScript engine in:
  frontend/lib/tools/purchaseRetainLifeInsuranceInSuper/

Statutory basis:
  Superannuation Industry (Supervision) Act 1993 (Cth) — Part 6, Division 4
  Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth)

This tool is deterministic: same input → same output. No LLM calls.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolValidationError

# =========================================================================
# CONSTANTS
# =========================================================================

ENGINE_VERSION = "1.0.0"
INACTIVITY_THRESHOLD_MONTHS = 16
LOW_BALANCE_THRESHOLD_AUD = 6_000
UNDER_25_AGE_THRESHOLD = 25
DEFAULT_GROWTH_RATE = 0.07
DEFAULT_YEARS_TO_RETIREMENT = 20
PYS_COMMENCEMENT_DATE = datetime(2019, 7, 1, tzinfo=timezone.utc)
LOW_BALANCE_GRANDFATHERING_DATE = datetime(2019, 11, 1, tzinfo=timezone.utc)
LEGACY_COVER_CUTOFF_YEAR = 2014

PERMITTED_COVER_TYPES = {"DEATH_COVER", "TERMINAL_ILLNESS", "TOTAL_AND_PERMANENT_DISABILITY", "INCOME_PROTECTION"}
NON_PERMITTED_COVER_TYPES = {"TRAUMA", "ACCIDENTAL_DEATH"}

# =========================================================================
# PURE HELPERS
# =========================================================================

def _months_between(start: datetime, end: datetime) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _compute_age(dob: datetime, ref: datetime) -> int:
    age = ref.year - dob.year
    if (ref.month, ref.day) < (dob.month, dob.day):
        age -= 1
    return age


def _future_value_annuity(pmt: float, n: float, r: float) -> float:
    if r == 0:
        return pmt * n
    return pmt * (((1 + r) ** n - 1) / r)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _round2(v: float) -> float:
    return round(v, 2)


def _safe_parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except ValueError:
        return None


# =========================================================================
# NORMALIZE INPUT
# =========================================================================

def _normalize(raw: dict) -> dict:
    eval_date_raw = raw.get("evaluationDate")
    evaluation_date = _safe_parse_date(eval_date_raw) or datetime.now(timezone.utc)

    member = raw.get("member") or {}
    fund = raw.get("fund") or {}
    product = raw.get("product") or {}
    elections = raw.get("elections") or {}
    employer_exc = raw.get("employerException") or {}
    advice_ctx = raw.get("adviceContext") or {}

    dob = _safe_parse_date(member.get("dateOfBirth"))
    age = member.get("age")
    if age is None and dob:
        age = _compute_age(dob, evaluation_date)

    return {
        # Member
        "age": age,
        "date_of_birth": dob,
        "employment_status": member.get("employmentStatus", "UNKNOWN"),
        "occupation": member.get("occupation"),
        "annual_income": member.get("annualIncome"),
        "marginal_tax_rate": member.get("marginalTaxRate"),
        "has_dependants": member.get("hasDependants"),
        "beneficiary_type_expected": member.get("beneficiaryTypeExpected", "UNKNOWN"),
        "cashflow_pressure": member.get("cashflowPressure"),
        "retirement_priority_high": member.get("retirementPriorityHigh"),
        "existing_insurance_needs_estimate": member.get("existingInsuranceNeedsEstimate"),
        "health_or_underwriting_complexity": member.get("healthOrUnderwritingComplexity"),
        "wants_inside_super": member.get("wantsInsideSuper"),
        "wants_affordability": member.get("wantsAffordability"),
        "wants_estate_control": member.get("wantsEstateControl"),
        # Fund
        "fund_type": fund.get("fundType"),
        "fund_member_count": fund.get("fundMemberCount"),
        "is_defined_benefit_member": fund.get("isDefinedBenefitMember", False),
        "is_adf_or_commonwealth": fund.get("isADFOrCommonwealthExceptionCase", False),
        "has_dangerous_occupation_election": fund.get("hasDangerousOccupationElection", False),
        "dangerous_occupation_election_in_force": fund.get("dangerousOccupationElectionInForce", False),
        "trustee_allows_opt_in_online": fund.get("trusteeAllowsOptInOnline", False),
        "successor_fund_transfer_occurred": fund.get("successorFundTransferOccurred", False),
        # Product
        "product_start_date": _safe_parse_date(product.get("productStartDate")),
        "account_balance": product.get("accountBalance"),
        "had_balance_ge6000_after_2019_11_01": product.get("hadBalanceGe6000OnOrAfter2019_11_01"),
        "last_amount_received_date": _safe_parse_date(product.get("lastAmountReceivedDate")),
        "received_amount_in_last_16_months": product.get("receivedAmountInLast16Months"),
        "cover_types_present": product.get("coverTypesPresent", []),
        "cover_commenced_before_2014": product.get("coverCommencedBefore2014", False),
        "fixed_term_cover": product.get("fixedTermCover", False),
        "fully_paid_or_non_premium": product.get("fullyPaidOrNonPremiumPaying", False),
        "legacy_non_standard_flag": product.get("legacyNonStandardFeatureFlag", False),
        # Elections
        "opted_in_to_retain": elections.get("optedInToRetainInsurance", False),
        "opt_in_election_date": _safe_parse_date(elections.get("optInElectionDate")),
        "opted_out": elections.get("optedOutOfInsurance", False),
        "opt_out_date": _safe_parse_date(elections.get("optOutDate")),
        "prior_election_via_successor": elections.get("priorElectionCarriedViaSuccessorTransfer", False),
        "equivalent_rights_confirmed": elections.get("equivalentRightsConfirmed", False),
        # Employer exception
        "employer_notified_trustee": employer_exc.get("employerHasNotifiedTrusteeInWriting", False),
        "employer_contributions_exceed_sg": employer_exc.get("employerContributionsExceedSGMinimumByInsuranceFeeAmount", False),
        # Advice context
        "contribution_cap_pressure": advice_ctx.get("contributionCapPressure"),
        "concessional_contributions_high": advice_ctx.get("concessionalContributionsAlreadyHigh"),
        "super_balance_adequacy": advice_ctx.get("superBalanceAdequacy"),
        "preferred_beneficiary_category": advice_ctx.get("preferredBeneficiaryCategory"),
        "need_policy_flexibility": advice_ctx.get("needForPolicyFlexibility"),
        "need_own_occupation_definitions": advice_ctx.get("needForOwnOccupationStyleDefinitions"),
        "need_policy_ownership_outside_trustee": advice_ctx.get("needForPolicyOwnershipOutsideTrusteeControl"),
        "estimated_annual_premium": advice_ctx.get("estimatedAnnualPremium"),
        "years_to_retirement": advice_ctx.get("yearsToRetirement"),
        "assumed_growth_rate": advice_ctx.get("assumedGrowthRate"),
        "monthly_surplus": advice_ctx.get("currentMonthlySurplusAfterExpenses"),
        # Meta
        "evaluation_date": evaluation_date,
    }


# =========================================================================
# VALIDATION
# =========================================================================

def _validate(raw: dict) -> dict:
    errors = []
    warnings = []
    questions = []

    member = raw.get("member") or {}
    product = raw.get("product") or {}

    has_age = member.get("age") is not None or member.get("dateOfBirth") is not None
    if not has_age:
        errors.append({"field": "member.age", "message": "Member age or date of birth is required.", "category": "LEGAL"})
        questions.append({"id": "Q-001", "question": "What is the member's age or date of birth?", "category": "LEGAL", "blocking": True})

    # Fund type is useful for under-25 MySuper checks but is NOT blocking for the
    # broader adequacy and placement analysis — demote to a non-blocking warning.
    fund = raw.get("fund") or {}
    if not fund.get("fundType"):
        warnings.append({"field": "fund.fundType", "message": "Fund type not provided — under-25 MySuper trigger check will be skipped."})

    # Cover types: helpful but not blocking — default life cover is the common case.
    if not product.get("coverTypesPresent"):
        warnings.append({"field": "product.coverTypesPresent", "message": "No cover types provided — assuming default Death cover for permissibility check."})

    # Advice-quality questions (non-blocking) — focused on needs analysis gaps
    if member.get("annualIncome") is None:
        questions.append({"id": "Q-010", "question": "What level of income replacement would John want to provide for his family (e.g. 10–15 years of income)?", "category": "NEEDS_ANALYSIS", "blocking": False})

    advice_ctx = raw.get("adviceContext") or {}
    if advice_ctx.get("yearsToRetirement") is None and member.get("age") is None:
        questions.append({"id": "Q-011", "question": "How many years until John plans to retire?", "category": "NEEDS_ANALYSIS", "blocking": False})

    questions.append({"id": "Q-012", "question": "Does John have any significant liquid assets or savings outside super that could offset the insurance need?", "category": "NEEDS_ANALYSIS", "blocking": False})
    questions.append({"id": "Q-013", "question": "Is John open to holding part of his life insurance outside super for greater flexibility (split strategy)?", "category": "STRATEGY", "blocking": False})

    is_valid = len(errors) == 0
    return {"isValid": is_valid, "errors": errors, "warnings": warnings, "missingInfoQuestions": questions}


# =========================================================================
# SWITCH-OFF TRIGGER EVALUATIONS
# =========================================================================

def _eval_inactivity(inp: dict) -> dict:
    triggered = False
    last_date = inp["last_amount_received_date"]
    received_flag = inp["received_amount_in_last_16_months"]
    months_inactive = 0

    if last_date:
        months_inactive = _months_between(last_date, inp["evaluation_date"])
        triggered = months_inactive >= INACTIVITY_THRESHOLD_MONTHS
        basis = f"Computed {months_inactive} months since last amount received."
    elif received_flag is not None:
        triggered = not received_flag
        basis = f"Caller-supplied flag: receivedAmountInLast16Months={received_flag}."
    else:
        basis = "Inactivity cannot be assessed — no date or flag provided."

    return {
        "trigger": "INACTIVITY_16_MONTHS",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": f"Inactivity rule {'triggered' if triggered else 'not triggered'}: {basis}",
        "supporting_facts": {
            "last_amount_received_date": last_date.isoformat() if last_date else None,
            "months_inactive": months_inactive if last_date else None,
            "threshold": INACTIVITY_THRESHOLD_MONTHS,
        },
    }


def _eval_low_balance(inp: dict) -> dict:
    raw_balance = inp["account_balance"]
    # If balance was not provided, do NOT trigger — assume balance is adequate.
    # Triggering on missing data would produce false alerts (e.g. a member with $180k
    # balance where the balance simply wasn't extracted).
    if raw_balance is None:
        return {
            "trigger": "LOW_BALANCE_UNDER_6000",
            "triggered": False,
            "overridden_by_exception": False,
            "overridden_by_election": False,
            "effectively_active": False,
            "reason": "Low-balance check skipped — super balance not provided.",
            "supporting_facts": {"account_balance": None, "threshold": LOW_BALANCE_THRESHOLD_AUD},
        }

    balance = raw_balance
    below = balance < LOW_BALANCE_THRESHOLD_AUD
    grandfathered = inp["had_balance_ge6000_after_2019_11_01"] is True
    product_start = inp["product_start_date"]
    post_pys = (product_start is None) or (inp["evaluation_date"] >= PYS_COMMENCEMENT_DATE)
    triggered = below and not grandfathered and post_pys

    return {
        "trigger": "LOW_BALANCE_UNDER_6000",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": (
            f"Low-balance switch-off triggered: balance ${balance:,.0f} is below ${LOW_BALANCE_THRESHOLD_AUD:,} and grandfathering does not apply."
            if triggered else
            f"Low-balance rule not triggered (balance=${balance:,.0f}, grandfathered={grandfathered})."
        ),
        "supporting_facts": {
            "account_balance": balance,
            "threshold": LOW_BALANCE_THRESHOLD_AUD,
            "below_threshold": below,
            "is_grandfathered": grandfathered,
        },
    }


def _eval_under_25(inp: dict) -> dict:
    age = inp["age"]
    is_under_25 = age is not None and age < UNDER_25_AGE_THRESHOLD
    is_mysuper = inp["fund_type"] == "mysuper"
    triggered = is_under_25 and is_mysuper and not inp["opted_in_to_retain"]

    return {
        "trigger": "UNDER_25_NO_ELECTION",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": (
            f"Under-25 rule triggered: member is age {age} on a MySuper product and has not lodged an opt-in direction."
            if triggered else
            f"Under-25 rule not triggered (age={age}, fund={inp['fund_type']}, opted_in={inp['opted_in_to_retain']})."
        ),
        "supporting_facts": {"age": age, "fund_type": inp["fund_type"], "is_mysuper": is_mysuper},
    }


# =========================================================================
# EXCEPTION EVALUATION
# =========================================================================

def _eval_exceptions(inp: dict) -> list[dict]:
    exceptions = []

    # Small fund carve-out (< 5 members exempt from PYS default insurance rules)
    count = inp["fund_member_count"]
    small_fund_applies = count is not None and count < 5
    exceptions.append({
        "applied": small_fund_applies,
        "type": "SMALL_FUND_CARVE_OUT",
        "reason": f"Fund has {count} members — small fund carve-out applies." if small_fund_applies else "Small fund carve-out does not apply.",
        "supporting_facts": {"fund_member_count": count},
    })

    # Defined benefit
    exceptions.append({
        "applied": inp["is_defined_benefit_member"],
        "type": "DEFINED_BENEFIT",
        "reason": "Member is in a defined benefit fund — PYS switch-off rules do not apply." if inp["is_defined_benefit_member"] else "Not a defined benefit member.",
        "supporting_facts": {"is_defined_benefit_member": inp["is_defined_benefit_member"]},
    })

    # ADF / Commonwealth
    exceptions.append({
        "applied": inp["is_adf_or_commonwealth"],
        "type": "ADF_COMMONWEALTH",
        "reason": "ADF / Commonwealth exception applies." if inp["is_adf_or_commonwealth"] else "ADF exception does not apply.",
        "supporting_facts": {"is_adf_or_commonwealth": inp["is_adf_or_commonwealth"]},
    })

    # Employer sponsored
    employer_applies = inp["employer_notified_trustee"] and inp["employer_contributions_exceed_sg"]
    exceptions.append({
        "applied": employer_applies,
        "type": "EMPLOYER_SPONSORED_CONTRIBUTION",
        "reason": "Employer-sponsored exception applies (SIS s68AAA(4A))." if employer_applies else "Employer-sponsored exception does not apply.",
        "supporting_facts": {
            "employer_notified": inp["employer_notified_trustee"],
            "contributions_exceed_sg": inp["employer_contributions_exceed_sg"],
        },
    })

    # Dangerous occupation
    exceptions.append({
        "applied": inp["has_dangerous_occupation_election"] and inp["dangerous_occupation_election_in_force"],
        "type": "DANGEROUS_OCCUPATION",
        "reason": "Dangerous occupation election is in force." if (inp["has_dangerous_occupation_election"] and inp["dangerous_occupation_election_in_force"]) else "Dangerous occupation exception does not apply.",
        "supporting_facts": {
            "has_election": inp["has_dangerous_occupation_election"],
            "in_force": inp["dangerous_occupation_election_in_force"],
        },
    })

    # Successor fund transfer
    successor_applies = inp["prior_election_via_successor"] and inp["equivalent_rights_confirmed"]
    exceptions.append({
        "applied": successor_applies,
        "type": "SUCCESSOR_FUND_TRANSFER",
        "reason": "Successor fund transfer with confirmed equivalent rights — prior election carried." if successor_applies else "Successor fund exception does not apply.",
        "supporting_facts": {
            "prior_election": inp["prior_election_via_successor"],
            "rights_confirmed": inp["equivalent_rights_confirmed"],
        },
    })

    return exceptions


# =========================================================================
# LEGAL STATUS RESOLUTION
# =========================================================================

def _resolve_legal_status(inp: dict, validation: dict) -> dict:
    rule_trace = []
    reasons = []

    if not validation["isValid"]:
        return {
            "status": "NEEDS_MORE_INFO",
            "permissibility": "UNKNOWN",
            "reasons": ["Validation failed — legal status cannot be fully determined until all mandatory facts are provided."] + [e["message"] for e in validation["errors"]],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
            "rule_trace": rule_trace,
        }

    # Permissibility check
    cover_types = set(inp["cover_types_present"])
    is_legacy = inp["legacy_non_standard_flag"] or inp["cover_commenced_before_2014"] or (inp["product_start_date"] is not None and inp["product_start_date"].year < LEGACY_COVER_CUTOFF_YEAR)

    not_permitted = cover_types & NON_PERMITTED_COVER_TYPES
    if not_permitted and not is_legacy:
        return {
            "status": "NOT_ALLOWED_IN_SUPER",
            "permissibility": "NOT_PERMITTED",
            "reasons": [f"Cover types {not_permitted} are not permitted insured events under SIS Act s67A."],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
            "rule_trace": rule_trace,
        }

    if is_legacy and (inp["fixed_term_cover"] or inp["fully_paid_or_non_premium"] or inp["legacy_non_standard_flag"]):
        return {
            "status": "COMPLEX_RIGHTS_CHECK_REQUIRED",
            "permissibility": "TRANSITIONAL_REVIEW_REQUIRED",
            "reasons": ["Legacy cover with non-standard features requires manual review."],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
            "rule_trace": rule_trace,
        }

    # Opt-out election
    if inp["opted_out"]:
        return {
            "status": "MUST_BE_SWITCHED_OFF",
            "permissibility": "PERMITTED",
            "reasons": ["Member has elected to opt out of insurance inside super."],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
            "rule_trace": rule_trace,
        }

    # Evaluate triggers
    inactivity = _eval_inactivity(inp)
    low_balance = _eval_low_balance(inp)
    under_25 = _eval_under_25(inp)

    # Evaluate exceptions
    exceptions = _eval_exceptions(inp)
    any_exception = any(e["applied"] for e in exceptions)

    # Election override
    has_opt_in = inp["opted_in_to_retain"] and inp["opt_in_election_date"] is not None
    has_portability = inp["prior_election_via_successor"] and inp["equivalent_rights_confirmed"]
    election_overrides = has_opt_in or has_portability

    all_trigger_exception_types = {"SMALL_FUND_CARVE_OUT", "DEFINED_BENEFIT", "ADF_COMMONWEALTH", "SUCCESSOR_FUND_TRANSFER"}
    inactivity_balance_exception_types = {"EMPLOYER_SPONSORED_CONTRIBUTION", "DANGEROUS_OCCUPATION"}

    def apply_overrides(trig: dict, trigger_key: str) -> dict:
        if not trig["triggered"]:
            return trig
        override_exc = any(
            e["applied"] and (
                e["type"] in all_trigger_exception_types or
                (e["type"] in inactivity_balance_exception_types and trigger_key != "UNDER_25_NO_ELECTION")
            )
            for e in exceptions
        )
        effectively_active = not override_exc and not election_overrides
        return {**trig, "overridden_by_exception": override_exc, "overridden_by_election": election_overrides, "effectively_active": effectively_active}

    final_inactivity = apply_overrides(inactivity, "INACTIVITY_16_MONTHS")
    final_low_balance = apply_overrides(low_balance, "LOW_BALANCE_UNDER_6000")
    final_under_25 = apply_overrides(under_25, "UNDER_25_NO_ELECTION")
    switch_offs = [final_inactivity, final_low_balance, final_under_25]

    # Successor fund unresolved
    if inp["successor_fund_transfer_occurred"] and not inp["equivalent_rights_confirmed"] and not any_exception:
        return {
            "status": "COMPLEX_RIGHTS_CHECK_REQUIRED",
            "permissibility": "PERMITTED",
            "reasons": ["Successor fund transfer occurred but equivalent rights have not been confirmed."],
            "switch_off_evaluations": switch_offs,
            "exceptions_applied": exceptions,
            "rule_trace": rule_trace,
        }

    hard_active = final_inactivity["effectively_active"] or final_low_balance["effectively_active"]
    soft_active = final_under_25["effectively_active"]

    if hard_active:
        status = "MUST_BE_SWITCHED_OFF"
        reasons.append(final_inactivity["reason"] if final_inactivity["effectively_active"] else final_low_balance["reason"])
    elif soft_active:
        status = "ALLOWED_BUT_OPT_IN_REQUIRED"
        reasons.append(final_under_25["reason"])
        reasons.append("Member may lodge a written direction with the trustee to opt in.")
    else:
        status = "ALLOWED_AND_ACTIVE"
        reasons.append("No active switch-off triggers. Cover is legally permissible and may continue.")
        if any_exception:
            reasons.append(f"Statutory exceptions applied: {[e['type'] for e in exceptions if e['applied']]}.")
        if has_opt_in:
            reasons.append("Member has a valid opt-in election on file.")

    return {
        "status": status,
        "permissibility": "PERMITTED",
        "reasons": reasons,
        "switch_off_evaluations": switch_offs,
        "exceptions_applied": exceptions,
        "rule_trace": rule_trace,
    }


# =========================================================================
# COVERAGE NEEDS ANALYSIS
# =========================================================================

INCOME_MULTIPLE_LOW  = 10
INCOME_MULTIPLE_HIGH = 15
FINAL_EXPENSES_BUFFER = 30_000  # estate/funeral/legal costs


def _calc_coverage_needs(inp: dict, mortgage_balance: float | None = None) -> dict:
    """
    Income-multiple + debt-clearance needs analysis.
    Returns a needs estimate with shortfall classification.
    """
    income = inp["annual_income"]
    existing_cover = inp["existing_insurance_needs_estimate"] or 0

    if income is None:
        return {
            "needs_analysis_available": False,
            "reason": "Annual income not provided — income multiple calculation unavailable.",
        }

    income_low  = income * INCOME_MULTIPLE_LOW
    income_high = income * INCOME_MULTIPLE_HIGH
    debt        = mortgage_balance or 0
    total_low   = income_low  + debt + FINAL_EXPENSES_BUFFER
    total_high  = income_high + debt + FINAL_EXPENSES_BUFFER
    shortfall   = max(0, total_low - existing_cover)

    if existing_cover == 0:
        shortfall_level = "UNKNOWN_EXISTING"
    elif shortfall <= 0:
        shortfall_level = "NONE"
    elif shortfall <= 200_000:
        shortfall_level = "MINOR"
    elif shortfall <= 500_000:
        shortfall_level = "MODERATE"
    elif shortfall <= 1_000_000:
        shortfall_level = "SIGNIFICANT"
    else:
        shortfall_level = "CRITICAL"

    return {
        "needs_analysis_available": True,
        "annual_income": income,
        "income_multiple_range": f"{INCOME_MULTIPLE_LOW}x – {INCOME_MULTIPLE_HIGH}x",
        "income_replacement_need_low":  round(income_low,  2),
        "income_replacement_need_high": round(income_high, 2),
        "debt_clearance_need": round(debt, 2),
        "final_expenses_buffer": FINAL_EXPENSES_BUFFER,
        "total_need_low":  round(total_low,  2),
        "total_need_high": round(total_high, 2),
        "existing_cover": existing_cover,
        "shortfall_estimate": round(shortfall, 2),
        "shortfall_level": shortfall_level,
        "recommendation_summary": (
            f"Based on income of ${income:,.0f} p.a., the estimated life insurance need is "
            f"${total_low:,.0f} – ${total_high:,.0f} "
            f"(including ${debt:,.0f} debt clearance and ${FINAL_EXPENSES_BUFFER:,.0f} final expenses). "
            f"Current cover of ${existing_cover:,.0f} represents a shortfall of approximately "
            f"${shortfall:,.0f} — classified as {shortfall_level}."
            if existing_cover > 0 else
            f"Based on income of ${income:,.0f} p.a., the estimated life insurance need is "
            f"${total_low:,.0f} – ${total_high:,.0f} "
            f"(including ${debt:,.0f} debt clearance and ${FINAL_EXPENSES_BUFFER:,.0f} final expenses). "
            "Existing cover amount not provided — full shortfall cannot be calculated."
        ),
    }


# =========================================================================
# CALCULATIONS
# =========================================================================

def _calc_retirement_drag(inp: dict) -> dict | None:
    premium = inp["estimated_annual_premium"]
    if premium is None:
        return None
    years = inp["years_to_retirement"] or DEFAULT_YEARS_TO_RETIREMENT
    rate = inp["assumed_growth_rate"] or DEFAULT_GROWTH_RATE
    drag = _future_value_annuity(premium, years, rate)
    return {
        "annual_premium": premium,
        "years_to_retirement": years,
        "assumed_growth_rate": rate,
        "estimated_total_drag": round(drag, 2),
        "explanation": (
            f"At {rate * 100:.1f}% p.a., paying ${premium:,.0f} p.a. for {years} years "
            f"represents an estimated retirement balance reduction of ${drag:,.0f}. "
            "This is an opportunity cost indicator only."
        ),
    }


def _calc_beneficiary_tax_risk(inp: dict) -> dict:
    bene = inp["preferred_beneficiary_category"] or inp["beneficiary_type_expected"]

    if bene in (None, "UNKNOWN"):
        return {
            "risk_level": "MEDIUM",
            "expected_beneficiary_category": "UNKNOWN",
            "estimated_taxable_component": "UNKNOWN",
            "explanation": "Beneficiary category unknown — tax risk cannot be fully assessed.",
        }
    if bene == "DEPENDANT_SPOUSE_OR_CHILD":
        return {"risk_level": "LOW", "expected_beneficiary_category": bene, "estimated_taxable_component": "LIKELY_LOW", "explanation": "Dependant spouse/child beneficiary — death benefits are generally tax-free."}
    if bene == "FINANCIAL_DEPENDANT":
        return {"risk_level": "LOW", "expected_beneficiary_category": bene, "estimated_taxable_component": "LIKELY_LOW", "explanation": "Financial dependant beneficiary — tax-free if dependency can be established."}
    if bene == "LEGAL_PERSONAL_REPRESENTATIVE":
        return {"risk_level": "HIGH", "expected_beneficiary_category": bene, "estimated_taxable_component": "LIKELY_HIGH", "explanation": "Estate beneficiary — tax exposure depends on who ultimately inherits. HIGH risk if non-dependant adults receive the estate."}
    return {
        "risk_level": "CRITICAL",
        "expected_beneficiary_category": bene,
        "estimated_taxable_component": "LIKELY_HIGH",
        "explanation": "Non-dependant adult beneficiary — taxable component taxed at 17% (15% + 2% Medicare levy) inside super. Consider outside-super ownership.",
    }


def _calc_placement_scores(inp: dict) -> dict:
    # Default: inside-super premium funding has moderate cashflow benefit even without
    # explicit pressure — most clients with mortgages and dependants benefit from
    # keeping premiums out of their take-home cash flow.
    cashflow_benefit = 50
    if inp["cashflow_pressure"]:
        cashflow_benefit = 85
    elif inp["wants_affordability"]:
        cashflow_benefit = 75
    elif inp["has_dependants"]:
        # Dependants increase the financial burden and thus the value of super-funded premiums
        cashflow_benefit = max(cashflow_benefit, 60)

    tax_benefit = 40
    mtr = inp["marginal_tax_rate"]
    if mtr is not None:
        if mtr >= 0.45:
            tax_benefit = 90
        elif mtr >= 0.37:
            tax_benefit = 80
        elif mtr >= 0.325:
            tax_benefit = 65
        elif mtr >= 0.19:
            tax_benefit = 45
        else:
            tax_benefit = 25
    if inp["concessional_contributions_high"]:
        tax_benefit = max(20, tax_benefit - 30)

    convenience_benefit = 40
    if inp["wants_inside_super"]:
        convenience_benefit = 75
    if inp["trustee_allows_opt_in_online"]:
        convenience_benefit = min(convenience_benefit + 15, 80)

    structural_benefit = 55 if inp["has_dangerous_occupation_election"] else 20

    retirement_penalty = 40
    if inp["retirement_priority_high"]:
        retirement_penalty = 85
    ytr = inp["years_to_retirement"]
    if ytr is not None:
        if ytr <= 5:
            retirement_penalty = max(retirement_penalty, 90)
        elif ytr <= 10:
            retirement_penalty = max(retirement_penalty, 80)
        elif ytr <= 20:
            retirement_penalty = max(retirement_penalty, 60)
    if inp["super_balance_adequacy"] == "low":
        retirement_penalty = max(retirement_penalty, 70)

    bene = inp["preferred_beneficiary_category"] or inp["beneficiary_type_expected"]
    tax_risk_penalty = 20
    if bene == "NON_DEPENDANT_ADULT":
        tax_risk_penalty = 90
    elif bene == "LEGAL_PERSONAL_REPRESENTATIVE":
        tax_risk_penalty = 75
    elif bene == "FINANCIAL_DEPENDANT":
        tax_risk_penalty = 35
    elif bene == "DEPENDANT_SPOUSE_OR_CHILD":
        tax_risk_penalty = 15
    if inp["wants_estate_control"]:
        tax_risk_penalty = max(tax_risk_penalty, 65)
    if inp["has_dependants"] is False:
        tax_risk_penalty = max(tax_risk_penalty, 55)

    flex_penalty = 20
    if inp["need_policy_flexibility"]:
        flex_penalty = 75
    if inp["need_own_occupation_definitions"]:
        flex_penalty = 85
    if inp["need_policy_ownership_outside_trustee"]:
        flex_penalty = 90
    if inp["health_or_underwriting_complexity"]:
        flex_penalty = max(flex_penalty, 65)

    cap_penalty = 20
    if inp["contribution_cap_pressure"]:
        cap_penalty = 80
    if inp["concessional_contributions_high"]:
        cap_penalty = max(cap_penalty, 75)

    return {
        "cashflow_benefit": _clamp(cashflow_benefit, 0, 100),
        "tax_funding_benefit": _clamp(tax_benefit, 0, 100),
        "convenience_benefit": _clamp(convenience_benefit, 0, 100),
        "structural_protection_benefit": _clamp(structural_benefit, 0, 100),
        "retirement_erosion_penalty": _clamp(retirement_penalty, 0, 100),
        "beneficiary_tax_risk_penalty": _clamp(tax_risk_penalty, 0, 100),
        "flexibility_control_penalty": _clamp(flex_penalty, 0, 100),
        "contribution_cap_pressure_penalty": _clamp(cap_penalty, 0, 100),
    }


def _eval_placement(inp: dict, legal_status: str, scores: dict) -> dict:
    benefit_total = (
        scores["cashflow_benefit"] * 0.30 +
        scores["tax_funding_benefit"] * 0.30 +
        scores["convenience_benefit"] * 0.20 +
        scores["structural_protection_benefit"] * 0.20
    )
    penalty_total = (
        scores["retirement_erosion_penalty"] * 0.30 +
        scores["beneficiary_tax_risk_penalty"] * 0.25 +
        scores["flexibility_control_penalty"] * 0.25 +
        scores["contribution_cap_pressure_penalty"] * 0.20
    )
    inside_score = _clamp(benefit_total - (penalty_total * 0.5), 0, 100)
    outside_score = _clamp(100 - inside_score, 0, 100)

    if inside_score >= 60:
        recommendation = "INSIDE_SUPER"
    elif outside_score >= 60:
        recommendation = "OUTSIDE_SUPER"
    elif abs(inside_score - outside_score) < 10:
        recommendation = "SPLIT_STRATEGY"
    else:
        recommendation = "INSUFFICIENT_INFO"

    reasoning = []
    risks = []
    if scores["cashflow_benefit"] >= 70:
        reasoning.append("Cash flow pressure makes inside-super premium funding materially beneficial.")
    if scores["tax_funding_benefit"] >= 70:
        reasoning.append("High marginal tax rate creates meaningful funding advantage inside super.")
    if scores["retirement_erosion_penalty"] >= 70:
        risks.append("Retirement drag is significant — inside-super premiums will reduce retirement balance compound growth.")
    if scores["beneficiary_tax_risk_penalty"] >= 70:
        risks.append("Non-dependant beneficiary structure creates 17% tax risk on death benefits inside super.")
    if scores["flexibility_control_penalty"] >= 70:
        risks.append("Required policy flexibility or definition quality is not achievable inside super.")

    return {
        "recommendation": recommendation,
        "inside_super_score": round(inside_score, 1),
        "outside_super_score": round(outside_score, 1),
        "benefit_breakdown": {k: v for k, v in scores.items() if "benefit" in k},
        "penalty_breakdown": {k: v for k, v in scores.items() if "penalty" in k},
        "reasoning": reasoning,
        "risks": risks,
    }


# =========================================================================
# MEMBER ACTIONS
# =========================================================================

def _generate_member_actions(inp: dict, legal_status: str) -> list[dict]:
    actions = []

    if legal_status == "ALLOWED_BUT_OPT_IN_REQUIRED":
        actions.append({
            "action_id": "ACT-001",
            "priority": "HIGH",
            "action": "Lodge a written opt-in direction with the super fund trustee to retain insurance inside super.",
            "rationale": "The under-25 rule (SIS s68AAA(3)) prevents default insurance for members under 25. A written opt-in direction is required.",
        })

    if inp["has_dangerous_occupation_election"] and not inp["dangerous_occupation_election_in_force"]:
        actions.append({
            "action_id": "ACT-002",
            "priority": "HIGH",
            "action": "Verify and reinstate the dangerous occupation election with the trustee.",
            "rationale": "Election exists but is not currently in force — reinstatement required.",
        })

    if inp["employer_notified_trustee"] and not inp["employer_contributions_exceed_sg"]:
        actions.append({
            "action_id": "ACT-003",
            "priority": "HIGH",
            "action": "Confirm employer contributions exceed SG minimum by the insurance fee amount.",
            "rationale": "SIS s68AAA(4A) requires both conditions to be satisfied for the employer exception.",
        })

    bene = inp["preferred_beneficiary_category"] or inp["beneficiary_type_expected"]
    if bene in ("NON_DEPENDANT_ADULT", "LEGAL_PERSONAL_REPRESENTATIVE"):
        actions.append({
            "action_id": "ACT-005",
            "priority": "HIGH",
            "action": "Review beneficiary nomination and estate planning. Consider outside-super ownership to reduce tax exposure.",
            "rationale": "Non-dependant beneficiaries face 17% tax on death benefits inside super.",
        })

    if inp["need_policy_flexibility"] or inp["need_own_occupation_definitions"] or inp["need_policy_ownership_outside_trustee"]:
        actions.append({
            "action_id": "ACT-006",
            "priority": "MEDIUM",
            "action": "Consider standalone cover outside super for required policy flexibility or definition quality.",
            "rationale": "Inside-super cover is controlled by the trustee and subject to standardised SIS definitions.",
        })

    if inp["successor_fund_transfer_occurred"] and not inp["equivalent_rights_confirmed"]:
        actions.append({
            "action_id": "ACT-007",
            "priority": "HIGH",
            "action": "Obtain written confirmation from successor fund trustee that equivalent rights have been transferred.",
            "rationale": "Without confirmed equivalent rights, insurance continuity cannot be relied upon.",
        })

    if legal_status == "MUST_BE_SWITCHED_OFF":
        actions.append({
            "action_id": "ACT-008",
            "priority": "HIGH",
            "action": "A switch-off trigger has fired. Review statutory exceptions and arrange replacement cover before switch-off takes effect.",
            "rationale": "Insurance ceasing without replacement could leave the member unprotected.",
        })

    return actions


# =========================================================================
# TOOL CLASS
# =========================================================================

class LifeInsuranceInSuperTool(BaseTool):
    name = "purchase_retain_life_insurance_in_super"
    version = "1.0.0"
    description = (
        "Evaluates whether life insurance inside superannuation is legally permissible "
        "and strategically appropriate for a member under the Protecting Your Super (PYS) "
        "legislative framework (SIS Act s68AAA). Determines legal status, switch-off triggers, "
        "exceptions, placement recommendation, and required member actions."
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "member": {"type": "object", "description": "Member demographic and preference data"},
                "fund": {"type": "object", "description": "Super fund type and characteristics"},
                "product": {"type": "object", "description": "Insurance product details"},
                "elections": {"type": "object", "description": "Member opt-in / opt-out elections"},
                "employerException": {"type": "object", "description": "Employer exception conditions"},
                "adviceContext": {"type": "object", "description": "Strategic advice context"},
                "evaluationDate": {"type": "string", "description": "ISO 8601 evaluation date"},
            },
        }

    def execute(self, input_data: dict) -> dict:
        # 1. Normalize
        inp = _normalize(input_data)

        # 2. Validate
        validation = _validate(input_data)

        # 3. Resolve legal status
        legal = _resolve_legal_status(inp, validation)

        # 4. Coverage needs analysis (income multiple + debt clearance gap)
        financial = input_data.get("financialPosition") or {}
        mortgage = financial.get("mortgageBalance") or inp.get("monthly_surplus")  # best-effort
        # Also check adviceContext for mortgage if not in financialPosition
        advice_ctx_raw = input_data.get("adviceContext") or {}
        if mortgage is None:
            mortgage = advice_ctx_raw.get("mortgageBalance")
        coverage_needs = _calc_coverage_needs(inp, mortgage_balance=mortgage)

        # 5. Calculations
        retirement_drag = _calc_retirement_drag(inp)
        beneficiary_tax_risk = _calc_beneficiary_tax_risk(inp)
        placement_scores = _calc_placement_scores(inp)
        placement = _eval_placement(inp, legal["status"], placement_scores)

        # 6. Member actions
        member_actions = _generate_member_actions(inp, legal["status"])

        # 7. Advice mode
        if not validation["isValid"]:
            advice_mode = "NEEDS_MORE_INFO"
        elif any([
            inp["annual_income"], inp["marginal_tax_rate"], inp["estimated_annual_premium"],
            inp["years_to_retirement"], inp["beneficiary_type_expected"] != "UNKNOWN",
        ]):
            advice_mode = "PERSONAL_ADVICE_READY"
        else:
            advice_mode = "GENERAL_GUIDANCE"

        return {
            "validation": validation,
            "legal_status": legal["status"],
            "legal_reasons": legal["reasons"],
            "switch_off_triggers": legal["switch_off_evaluations"],
            "exceptions_applied": legal["exceptions_applied"],
            "coverage_needs_analysis": coverage_needs,
            "member_actions": member_actions,
            "retirement_drag_estimate": retirement_drag,
            "beneficiary_tax_risk": beneficiary_tax_risk,
            "placement_assessment": placement,
            "placement_scores": placement_scores,
            "health": input_data.get("health"),  # pass through for underwriting assessment
            "advice_mode": advice_mode,
            "missing_info_questions": validation["missingInfoQuestions"],
            "engine_version": ENGINE_VERSION,
            "evaluated_at": inp["evaluation_date"].isoformat(),
        }
