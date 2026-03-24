"""
tpd_in_super.py — Purchase/Retain TPD Insurance In Super tool.

Statutory and regulatory basis:
  Superannuation Industry (Supervision) Act 1993 (Cth) — ss 68A, 68AAA–68AAC
  SIS Regulation 4.07C  (Automatic Acceptance Limit — AAL)
  SIS Regulation 4.07D  (Own-occupation TPD banned inside super post-1 Jul 2014)
  Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth)
  Treasury Laws Amendment (Putting Members' Interests First) Act 2019 (Cth)
  ITAA 1997 — TPD benefit inside super: taxable component taxed at ~22% (under 60)
  Corporations Regulations 2001 — notice obligations (reg 7.9.07H etc.)

Business logic covers:
  - PYS/PMIF switch-off triggers: inactivity (16 months), low balance ($6 000), under-25
  - Exceptions: small fund (<5 members), defined benefit, ADF/Commonwealth
  - Notice schedule: 9, 12 and 15 months inactivity → required trustee notices
  - TPD definition assessment: own-occ banned post-Jul 2014 (SIS Reg 4.07D)
  - Coverage needs analysis: lump sum replacement model
  - Placement scoring: inside super (any-occ, AAL ~$100k, premium from balance)
    vs retail (own-occ available, tax-free benefit, full underwriting)
  - Split strategy recommendation
  - Underwriting: BMI / health / AAL check
  - Retirement drag: annual premium × future-value-annuity formula
  - Beneficiary tax risk: dependant vs non-dependant
  - Member action list

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

# PYS / PMIF thresholds
INACTIVITY_THRESHOLD_MONTHS = 16
LOW_BALANCE_THRESHOLD_AUD   = 6_000
UNDER_25_AGE_THRESHOLD      = 25

# Regulatory dates
PYS_COMMENCEMENT_DATE       = datetime(2019, 7,  1, tzinfo=timezone.utc)
SIS_REG_407D_CUTOFF_DATE    = datetime(2014, 7,  1, tzinfo=timezone.utc)  # own-occ TPD banned after this

# Underwriting / AAL
AUTO_ACCEPTANCE_LIMIT_AUD   = 100_000   # SIS Reg 4.07C — AAL for group TPD inside super

# Tax rates (ITAA 1997)
TPD_TAX_RATE_UNDER_60       = 0.22     # 20% + 2% Medicare levy on taxable component
TPD_TAX_RATE_OVER_60        = 0.00     # tax-free to member aged 60+
TAXABLE_COMPONENT_DEFAULT   = 0.85     # default taxable component fraction
NON_DEPENDANT_BENEFIT_TAX   = 0.17    # 15% + 2% Medicare on taxable component to non-dependant

# Claims approval rates (source: ASIC Rep 633 / industry data)
CLAIMS_APPROVAL_ANY_OCC     = 0.80
CLAIMS_APPROVAL_OWN_OCC     = 0.88
CLAIMS_APPROVAL_ADL         = 0.40

# Notice schedule: months of inactivity that trigger trustee notices
NOTICE_TRIGGER_MONTHS       = [9, 12, 15]

# TPD needs analysis defaults
REHAB_COSTS_DEFAULT_AUD     = 75_000
HOME_MODIFICATION_DEFAULT_AUD = 30_000
REPLACEMENT_RATIO_LOW       = 0.70
REPLACEMENT_RATIO_HIGH      = 1.00

# Retirement drag
DEFAULT_GROWTH_RATE         = 0.07
DEFAULT_YEARS_TO_RETIREMENT = 20


# =========================================================================
# PURE HELPERS
# =========================================================================

def _safe_parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    except ValueError:
        return None


def _compute_age(dob: datetime, ref: datetime) -> int:
    age = ref.year - dob.year
    if (ref.month, ref.day) < (dob.month, dob.day):
        age -= 1
    return age


def _months_between(start: datetime, end: datetime) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


def _future_value_annuity(pmt: float, n: float, r: float) -> float:
    if r == 0:
        return pmt * n
    return pmt * (((1 + r) ** n - 1) / r)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# =========================================================================
# NORMALIZE INPUT
# =========================================================================

def _normalize(raw: dict) -> dict:
    eval_date = _safe_parse_date(raw.get("evaluationDate")) or datetime.now(timezone.utc)

    m   = raw.get("member")       or {}
    f   = raw.get("fund")         or {}
    ec  = raw.get("existingCover") or {}
    pc  = raw.get("proposedCover") or {}
    el  = raw.get("elections")     or {}
    fp  = raw.get("financialPosition") or {}
    h   = raw.get("health")        or {}
    ac  = raw.get("adviceContext") or {}

    dob = _safe_parse_date(m.get("dateOfBirth"))
    age = m.get("age")
    if age is None and dob:
        age = _compute_age(dob, eval_date)

    # Inactivity: prefer explicit months field, fall back to flag
    account_inactive_months = f.get("accountInactiveMonths")
    received_flag           = f.get("receivedAmountInLast16Months")

    return {
        "evaluation_date": eval_date,

        # --- Member ---
        "age":                  age,
        "date_of_birth":        dob,
        "annual_gross_income":  m.get("annualGrossIncome"),
        "marginal_tax_rate":    m.get("marginalTaxRate"),
        "employment_status":    m.get("employmentStatus", "UNKNOWN"),
        "weekly_hours_worked":  m.get("weeklyHoursWorked"),
        "occupation":           m.get("occupation"),
        "occupation_class":     m.get("occupationClass", "UNKNOWN"),
        "has_dependants":       m.get("hasDependants"),
        "number_of_dependants": m.get("numberOfDependants"),

        # --- Fund ---
        "fund_type":            f.get("fundType"),
        "fund_name":            f.get("fundName"),
        "account_balance":      f.get("accountBalance"),
        "received_amount_in_last_16_months": received_flag,
        "account_inactive_months": account_inactive_months,
        "fund_member_count":    f.get("memberCount"),
        "is_defined_benefit":   f.get("isDefinedBenefitMember", False),
        "is_adf_or_commonwealth": f.get("isADFOrCommonwealth", False),

        # --- Existing TPD cover ---
        "has_existing_tpd":     ec.get("hasExistingTPDCover", False),
        "existing_tpd_sum":     ec.get("tpdSumInsured"),
        "existing_tpd_definition": ec.get("tpdDefinition", "UNKNOWN"),
        "existing_annual_premium": ec.get("annualPremium"),
        "cover_is_inside_super": ec.get("coverIsInsideSuper", False),
        "policy_inception_date": _safe_parse_date(ec.get("policyInceptionDate")),
        "had_balance_ge6000_after_20191101": ec.get("hadBalanceGe6000After20191101"),

        # --- Proposed cover ---
        "proposed_tpd_sum":     pc.get("tpdSumInsured"),
        "proposed_annual_premium": pc.get("annualPremium"),

        # --- Elections ---
        "opted_in_to_retain":   el.get("optedInToRetainInsurance", False),
        "opted_out":            el.get("optedOutOfInsurance", False),
        "election_date":        _safe_parse_date(el.get("electionDate")),

        # --- Financial position ---
        "mortgage_balance":     fp.get("mortgageBalance"),
        "other_debts":          fp.get("otherDebts"),
        "liquid_assets":        fp.get("liquidAssets"),
        "monthly_expenses":     fp.get("monthlyExpenses"),

        # --- Health ---
        "height_cm":            h.get("heightCm"),
        "weight_kg":            h.get("weightKg"),
        "existing_conditions":  h.get("existingMedicalConditions", []),
        "current_medications":  h.get("currentMedications", []),
        "is_smoker":            h.get("isSmoker", False),

        # --- Advice context ---
        "years_to_retirement":  ac.get("yearsToRetirement"),
        "wants_affordability":  ac.get("wantsAffordability", False),
        "wants_own_occupation": ac.get("wantsOwnOccupation", False),
        "consider_retail_top_up": ac.get("considerRetailTopUp", False),
        "assumed_growth_rate":  ac.get("assumedGrowthRate"),
    }


# =========================================================================
# VALIDATION
# =========================================================================

def _validate(raw: dict, inp: dict) -> dict:
    errors    = []
    warnings  = []
    questions = []

    m = raw.get("member") or {}
    f = raw.get("fund")   or {}

    # Blocking
    if inp["age"] is None:
        errors.append({"field": "member.age", "message": "Member age or date of birth is required.", "category": "LEGAL"})
        questions.append({"id": "TPDS-Q-001", "question": "What is the member's age or date of birth?", "category": "LEGAL", "blocking": True})

    if not f.get("fundType"):
        warnings.append({"field": "fund.fundType", "message": "Fund type not provided — under-25 MySuper trigger check will be skipped."})

    # Non-blocking enrichment questions
    if inp["annual_gross_income"] is None:
        warnings.append({"field": "member.annualGrossIncome", "message": "Annual gross income not provided — TPD lump sum need cannot be calculated."})
        questions.append({"id": "TPDS-Q-002", "question": "What is the member's annual gross income? This is needed to calculate their TPD lump sum replacement need.", "category": "NEEDS_ANALYSIS", "blocking": False})

    if inp["account_balance"] is None:
        warnings.append({"field": "fund.accountBalance", "message": "Super account balance not provided — low-balance switch-off check and retirement drag cannot be assessed."})
        questions.append({"id": "TPDS-Q-003", "question": "What is the current super account balance?", "category": "LEGAL", "blocking": False})

    if inp["account_inactive_months"] is None and inp["received_amount_in_last_16_months"] is None:
        warnings.append({"field": "fund.accountInactiveMonths", "message": "Account inactivity not provided — PYS inactivity trigger check will be skipped."})
        questions.append({"id": "TPDS-Q-004", "question": "How many months has the account been inactive (no contributions received)?", "category": "LEGAL", "blocking": False})

    if inp["years_to_retirement"] is None:
        questions.append({"id": "TPDS-Q-005", "question": "How many years until the member plans to retire? (Used for TPD lump sum need and retirement drag.)", "category": "RETIREMENT", "blocking": False})

    if inp["mortgage_balance"] is None:
        questions.append({"id": "TPDS-Q-006", "question": "What is the outstanding mortgage balance? (Included in TPD lump sum need calculation.)", "category": "NEEDS_ANALYSIS", "blocking": False})

    if inp["proposed_tpd_sum"] is None and inp["existing_tpd_sum"] is None:
        questions.append({"id": "TPDS-Q-007", "question": "What TPD sum insured is being considered (proposed cover amount)?", "category": "COVERAGE", "blocking": False})

    if inp["proposed_annual_premium"] is None and inp["existing_annual_premium"] is None:
        questions.append({"id": "TPDS-Q-008", "question": "What is the annual TPD premium? (Required for retirement drag analysis.)", "category": "AFFORDABILITY", "blocking": False})

    is_valid = len(errors) == 0
    return {"isValid": is_valid, "errors": errors, "warnings": warnings, "missingInfoQuestions": questions}


# =========================================================================
# PYS SWITCH-OFF TRIGGER EVALUATIONS
# =========================================================================

def _eval_inactivity(inp: dict) -> dict:
    triggered       = False
    months_inactive = 0
    inactive_months = inp["account_inactive_months"]
    received_flag   = inp["received_amount_in_last_16_months"]

    if inactive_months is not None:
        months_inactive = inactive_months
        triggered = months_inactive >= INACTIVITY_THRESHOLD_MONTHS
        basis = f"Caller supplied accountInactiveMonths={inactive_months}."
    elif received_flag is not None:
        triggered = not received_flag
        basis = f"Caller-supplied flag: receivedAmountInLast16Months={received_flag}."
        months_inactive = INACTIVITY_THRESHOLD_MONTHS if triggered else 0
    else:
        basis = "Inactivity cannot be assessed — no inactivity months or flag provided."

    return {
        "trigger": "INACTIVITY_16_MONTHS",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": f"Inactivity rule {'triggered' if triggered else 'not triggered'}: {basis}",
        "supporting_facts": {
            "account_inactive_months": inactive_months,
            "months_inactive_used": months_inactive if inactive_months is not None else None,
            "threshold": INACTIVITY_THRESHOLD_MONTHS,
        },
    }


def _eval_low_balance(inp: dict) -> dict:
    balance = inp["account_balance"]
    # IMPORTANT: if balance is None, do NOT trigger — never default None → 0
    if balance is None:
        return {
            "trigger": "LOW_BALANCE_UNDER_6000",
            "triggered": False,
            "overridden_by_exception": False,
            "overridden_by_election": False,
            "effectively_active": False,
            "reason": "Account balance not provided — low-balance check skipped. Confirm balance to complete assessment.",
            "supporting_facts": {"account_balance": None, "threshold": LOW_BALANCE_THRESHOLD_AUD},
        }

    below         = balance < LOW_BALANCE_THRESHOLD_AUD
    grandfathered = inp["had_balance_ge6000_after_20191101"] is True
    post_pys      = inp["evaluation_date"] >= PYS_COMMENCEMENT_DATE
    triggered     = below and not grandfathered and post_pys

    return {
        "trigger": "LOW_BALANCE_UNDER_6000",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": (
            f"Low-balance switch-off triggered: balance ${balance:,.0f} is below "
            f"${LOW_BALANCE_THRESHOLD_AUD:,} and grandfathering does not apply."
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
    age        = inp["age"]
    is_u25     = age is not None and age < UNDER_25_AGE_THRESHOLD
    is_mysuper = (inp["fund_type"] or "").lower() == "mysuper"
    triggered  = is_u25 and is_mysuper and not inp["opted_in_to_retain"]

    return {
        "trigger": "UNDER_25_NO_ELECTION",
        "triggered": triggered,
        "overridden_by_exception": False,
        "overridden_by_election": False,
        "effectively_active": triggered,
        "reason": (
            f"Under-25 rule triggered: member aged {age} on a MySuper product with no opt-in direction lodged."
            if triggered else
            f"Under-25 rule not triggered (age={age}, fund={inp['fund_type']}, opted_in={inp['opted_in_to_retain']})."
        ),
        "supporting_facts": {"age": age, "fund_type": inp["fund_type"], "is_mysuper": is_mysuper},
    }


# =========================================================================
# EXCEPTIONS
# =========================================================================

def _eval_exceptions(inp: dict) -> list[dict]:
    exceptions = []

    # Small fund carve-out (< 5 members exempt from PYS default insurance rules)
    count = inp["fund_member_count"]
    small_fund = count is not None and count < 5
    exceptions.append({
        "applied": small_fund,
        "type": "SMALL_FUND_CARVE_OUT",
        "reason": f"Fund has {count} members — small fund carve-out applies." if small_fund else "Small fund carve-out does not apply.",
        "supporting_facts": {"fund_member_count": count},
    })

    # Defined benefit
    exceptions.append({
        "applied": inp["is_defined_benefit"],
        "type": "DEFINED_BENEFIT",
        "reason": "Member is in a defined benefit fund — PYS switch-off rules do not apply." if inp["is_defined_benefit"] else "Not a defined benefit member.",
        "supporting_facts": {"is_defined_benefit_member": inp["is_defined_benefit"]},
    })

    # ADF / Commonwealth
    exceptions.append({
        "applied": inp["is_adf_or_commonwealth"],
        "type": "ADF_COMMONWEALTH",
        "reason": "ADF / Commonwealth fund exception applies." if inp["is_adf_or_commonwealth"] else "ADF exception does not apply.",
        "supporting_facts": {"is_adf_or_commonwealth": inp["is_adf_or_commonwealth"]},
    })

    return exceptions


# =========================================================================
# LEGAL STATUS RESOLUTION
# =========================================================================

def _eval_legal_status(
    inactivity: dict,
    low_balance: dict,
    under_25: dict,
    exceptions: list[dict],
    inp: dict,
) -> dict:
    any_exception = any(e["applied"] for e in exceptions)
    has_opt_in    = inp["opted_in_to_retain"] and inp["election_date"] is not None

    # Opt-out: member has elected to cancel cover
    if inp["opted_out"]:
        return {
            "status": "OPTED_OUT",
            "permissibility": "PERMITTED_BUT_MEMBER_DECLINED",
            "reasons": ["Member has elected to opt out of TPD insurance inside super."],
            "switch_off_evaluations": [inactivity, low_balance, under_25],
            "exceptions_applied": exceptions,
        }

    ALL_TRIGGER_EXCEPTIONS    = {"SMALL_FUND_CARVE_OUT", "DEFINED_BENEFIT", "ADF_COMMONWEALTH"}

    def apply_overrides(trig: dict) -> dict:
        if not trig["triggered"]:
            return trig
        exc_override       = any(e["applied"] and e["type"] in ALL_TRIGGER_EXCEPTIONS for e in exceptions)
        effectively_active = not exc_override and not has_opt_in
        return {**trig, "overridden_by_exception": exc_override, "overridden_by_election": has_opt_in, "effectively_active": effectively_active}

    final_inactivity  = apply_overrides(inactivity)
    final_low_balance = apply_overrides(low_balance)
    final_under_25    = apply_overrides(under_25)
    switch_offs       = [final_inactivity, final_low_balance, final_under_25]

    hard_active = final_inactivity["effectively_active"] or final_low_balance["effectively_active"]
    soft_active = final_under_25["effectively_active"]

    reasons = []
    if hard_active:
        status = "MUST_BE_SWITCHED_OFF"
        reasons.append(
            final_inactivity["reason"] if final_inactivity["effectively_active"] else final_low_balance["reason"]
        )
        reasons.append("TPD cover inside super must cease unless the member lodges an opt-in election (SIS ss68AAA–68AAC).")
    elif soft_active:
        status = "ALLOWED_BUT_OPT_IN_REQUIRED"
        reasons.append(final_under_25["reason"])
        reasons.append("Member must lodge a written opt-in direction with the trustee to retain TPD cover inside super.")
    else:
        status = "ALLOWED_AND_ACTIVE"
        reasons.append("No active PYS switch-off triggers. TPD cover is legally permissible and may continue.")
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
    }


# =========================================================================
# NOTICE SCHEDULE
# =========================================================================

def _eval_notice_schedule(inp: dict) -> dict:
    inactive_months = inp["account_inactive_months"]

    if inactive_months is None:
        # Try to infer from the flag
        if inp["received_amount_in_last_16_months"] is False:
            inactive_months = INACTIVITY_THRESHOLD_MONTHS  # at least 16 months
        else:
            return {
                "notices_required": [],
                "note": "Inactivity months not provided — notice schedule cannot be assessed.",
            }

    notices = []
    if inactive_months >= 9:
        notices.append({
            "notice_type": "FIRST_NOTICE",
            "trigger_months": 9,
            "months_before_cessation": 7,
            "status": "DUE" if inactive_months < 12 else "OVERDUE",
            "description": "First notice: account has been inactive for 9 months (7 months before the 16-month cessation point).",
        })
    if inactive_months >= 12:
        notices.append({
            "notice_type": "SECOND_NOTICE",
            "trigger_months": 12,
            "months_before_cessation": 4,
            "status": "DUE" if inactive_months < 15 else "OVERDUE",
            "description": "Second notice: account has been inactive for 12 months (4 months before cessation).",
        })
    if inactive_months >= 15:
        notices.append({
            "notice_type": "FINAL_NOTICE",
            "trigger_months": 15,
            "months_before_cessation": 1,
            "status": "DUE" if inactive_months < 16 else "OVERDUE",
            "description": "Final notice: account has been inactive for 15 months (1 month before cessation). Member must act immediately.",
        })

    if inp["opted_in_to_retain"] and inp["election_date"]:
        notices.append({
            "notice_type": "RIGHT_TO_CEASE_NOTICE",
            "trigger_months": None,
            "months_before_cessation": None,
            "status": "DUE_WITHIN_2_WEEKS",
            "description": (
                "After member opt-in election: trustee must issue a right-to-cease notice within 2 weeks, "
                "then at intervals of ≤15 months (Corporations Regulations)."
            ),
        })

    return {
        "account_inactive_months": inactive_months,
        "cessation_threshold_months": INACTIVITY_THRESHOLD_MONTHS,
        "notices_required": notices,
        "months_until_cessation": max(0, INACTIVITY_THRESHOLD_MONTHS - inactive_months),
        "note": (
            f"Account has been inactive for {inactive_months} months. "
            f"{'TPD cover will cease at 16 months unless member opts in.' if inactive_months < 16 else 'TPD cover cessation threshold has been reached.'}"
        ),
    }


# =========================================================================
# TPD DEFINITION ASSESSMENT
# =========================================================================

def _eval_tpd_definition(inp: dict) -> dict:
    """
    Inside super: own-occupation TPD is BANNED for new policies post-1 Jul 2014
    (SIS Reg 4.07D). Only any-occupation or ADL definitions are permissible.

    Check whether existing policy inception pre-dates the cutoff (grandfathered own-occ).
    """
    existing_def     = inp["existing_tpd_definition"]
    inception        = inp["policy_inception_date"]
    cover_in_super   = inp["cover_is_inside_super"]
    wants_own_occ    = inp["wants_own_occupation"]

    # Is existing cover grandfathered (pre-Jul 2014 own-occ inside super)?
    is_grandfathered = (
        cover_in_super and
        existing_def == "OWN_OCCUPATION" and
        inception is not None and
        inception < SIS_REG_407D_CUTOFF_DATE
    )

    # Definition quality assessment
    if existing_def == "OWN_OCCUPATION":
        if is_grandfathered:
            quality = "GRANDFATHERED_OWN_OCC"
            quality_note = (
                "Own-occupation TPD cover is grandfathered (policy commenced before 1 July 2014). "
                "This is a HIGH-VALUE definition — preserve it. Do NOT cancel or replace this policy "
                "as new inside-super TPD cannot use own-occ (SIS Reg 4.07D)."
            )
            claims_rate = CLAIMS_APPROVAL_OWN_OCC
            rank = 1
        else:
            quality = "NON_COMPLIANT_IN_SUPER"
            quality_note = (
                "Own-occupation TPD is BANNED inside super for new policies post-1 July 2014 "
                "(SIS Reg 4.07D). This policy requires review — an own-occ definition inside super "
                "for a post-Jul 2014 policy may not be enforceable."
            )
            claims_rate = CLAIMS_APPROVAL_OWN_OCC
            rank = 1  # best definition quality but non-compliant placement
    elif existing_def == "ANY_OCCUPATION":
        quality = "STANDARD_IN_SUPER"
        quality_note = (
            "Any-occupation TPD is the standard permissible definition inside super. "
            f"Claims approval rate is approximately {int(CLAIMS_APPROVAL_ANY_OCC * 100)}% — "
            "lower than own-occupation retail (~88%) due to the stricter any-occupation test."
        )
        claims_rate = CLAIMS_APPROVAL_ANY_OCC
        rank = 2
    elif existing_def == "ADL":
        quality = "WEAK_DEFINITION"
        quality_note = (
            "Activities of Daily Living (ADL) is the weakest TPD definition. "
            f"Claims approval rate is approximately {int(CLAIMS_APPROVAL_ADL * 100)}% — "
            "significantly below any-occupation (~80%) and own-occupation (~88%). "
            "Consider upgrading to any-occupation or obtaining retail own-occupation top-up cover."
        )
        claims_rate = CLAIMS_APPROVAL_ADL
        rank = 3
    else:
        quality = "UNKNOWN"
        quality_note = "TPD definition not specified — cannot assess definition quality."
        claims_rate = None
        rank = None

    # Proposed cover inside super must use any-occupation
    inside_super_definition_constraint = (
        "Inside super: only any-occupation (or ADL) TPD definitions are permissible post-1 July 2014 "
        "(SIS Reg 4.07D). Own-occupation TPD is not available for new policies inside superannuation."
    )

    recommendation = None
    if wants_own_occ:
        recommendation = (
            "Client wants own-occupation TPD. This is ONLY available via retail (outside super). "
            "Recommended strategy: any-occupation group TPD inside super (up to AAL of $100k, cost-efficient) "
            "+ own-occupation retail TPD top-up outside super for definition quality."
        )
    elif existing_def in ("ANY_OCCUPATION", None, "UNKNOWN"):
        recommendation = (
            "Any-occupation TPD inside super is appropriate and cost-efficient up to the AAL (~$100k). "
            "For cover above the AAL, underwriting is required. Consider a split: inside super + retail top-up."
        )

    return {
        "existing_definition": existing_def,
        "definition_quality": quality,
        "definition_rank": rank,
        "claims_approval_rate": claims_rate,
        "is_grandfathered_own_occ": is_grandfathered,
        "policy_inception_date": inception.isoformat() if inception else None,
        "sis_reg_407d_cutoff": SIS_REG_407D_CUTOFF_DATE.date().isoformat(),
        "quality_note": quality_note,
        "inside_super_definition_constraint": inside_super_definition_constraint,
        "recommendation": recommendation,
    }


# =========================================================================
# COVERAGE NEEDS ANALYSIS
# =========================================================================

def _eval_coverage_needs(inp: dict) -> dict:
    income = inp["annual_gross_income"]
    if income is None:
        return {
            "needs_analysis_available": False,
            "reason": "Annual gross income not provided — TPD lump sum need cannot be calculated.",
        }

    years_to_retirement = inp["years_to_retirement"] or DEFAULT_YEARS_TO_RETIREMENT
    mortgage            = inp["mortgage_balance"] or 0
    other_debts         = inp["other_debts"] or 0
    liquid_assets       = inp["liquid_assets"] or 0
    existing_cover      = inp["existing_tpd_sum"] or 0

    # Lump sum income replacement (70%–100% of income × years to retirement)
    income_need_low  = income * years_to_retirement * REPLACEMENT_RATIO_LOW
    income_need_high = income * years_to_retirement * REPLACEMENT_RATIO_HIGH

    # Add debt clearance, rehab costs and home modifications
    total_need_low  = income_need_low  + mortgage + other_debts + REHAB_COSTS_DEFAULT_AUD + HOME_MODIFICATION_DEFAULT_AUD
    total_need_high = income_need_high + mortgage + other_debts + REHAB_COSTS_DEFAULT_AUD + HOME_MODIFICATION_DEFAULT_AUD

    # Reduce by existing cover and liquid assets
    tpd_need_low  = max(0.0, total_need_low  - existing_cover - liquid_assets)
    tpd_need_high = max(0.0, total_need_high - existing_cover - liquid_assets)

    shortfall = max(0.0, tpd_need_low - existing_cover) if existing_cover else tpd_need_low

    if existing_cover == 0:
        shortfall_level = "UNKNOWN_EXISTING"
    elif shortfall <= 0:
        shortfall_level = "NONE"
    elif shortfall <= 100_000:
        shortfall_level = "MINOR"
    elif shortfall <= 300_000:
        shortfall_level = "MODERATE"
    elif shortfall <= 700_000:
        shortfall_level = "SIGNIFICANT"
    else:
        shortfall_level = "CRITICAL"

    recommendation_summary = (
        f"Based on income of ${income:,.0f} p.a. and {years_to_retirement} years to retirement, "
        f"the estimated TPD lump sum need is ${tpd_need_low:,.0f} – ${tpd_need_high:,.0f} "
        f"(includes ${mortgage + other_debts:,.0f} debt clearance, "
        f"${REHAB_COSTS_DEFAULT_AUD:,.0f} rehab/medical costs, "
        f"${HOME_MODIFICATION_DEFAULT_AUD:,.0f} home modification budget). "
        f"Net of ${liquid_assets:,.0f} liquid assets and ${existing_cover:,.0f} existing TPD cover. "
        f"Estimated shortfall: ${shortfall:,.0f} — classified as {shortfall_level}."
        if existing_cover > 0 or liquid_assets > 0 else
        f"Based on income of ${income:,.0f} p.a. and {years_to_retirement} years to retirement, "
        f"the estimated TPD lump sum need is ${tpd_need_low:,.0f} – ${tpd_need_high:,.0f}. "
        "Existing cover and liquid assets not provided — full shortfall cannot be calculated."
    )

    return {
        "needs_analysis_available": True,
        "annual_gross_income": income,
        "years_to_retirement": years_to_retirement,
        "income_replacement_low": round(income_need_low, 2),
        "income_replacement_high": round(income_need_high, 2),
        "replacement_ratio_range": f"{int(REPLACEMENT_RATIO_LOW * 100)}%–{int(REPLACEMENT_RATIO_HIGH * 100)}%",
        "debt_clearance": round(mortgage + other_debts, 2),
        "rehab_costs_assumed": REHAB_COSTS_DEFAULT_AUD,
        "home_modification_assumed": HOME_MODIFICATION_DEFAULT_AUD,
        "total_gross_need_low": round(total_need_low, 2),
        "total_gross_need_high": round(total_need_high, 2),
        "liquid_assets_offset": round(liquid_assets, 2),
        "existing_tpd_cover": existing_cover,
        "tpd_need_low": round(tpd_need_low, 2),
        "tpd_need_high": round(tpd_need_high, 2),
        "shortfall_estimate": round(shortfall, 2),
        "shortfall_level": shortfall_level,
        "recommendation_summary": recommendation_summary,
    }


# =========================================================================
# PLACEMENT ASSESSMENT — INSIDE SUPER vs RETAIL
# =========================================================================

def _eval_placement(inp: dict, legal_status: str) -> dict:
    """
    Score TPD placement on 5 dimensions:
      1. Definition quality  — inside super scores LOWER (any-occ only)
      2. Tax efficiency      — inside super scores HIGHER if under 60 + high MTR
      3. Affordability       — inside super scores HIGHER (premium from super balance)
      4. Flexibility         — retail scores HIGHER (own control, own-occ available)
      5. Claims certainty    — retail scores HIGHER (own-occ ~88% vs any-occ ~80%)
    """
    age = inp["age"] or 0
    mtr = inp["marginal_tax_rate"]

    # 1. Definition quality — inside super
    #    Any-occ inside super is weaker than retail own-occ → penalty for inside super
    if inp["wants_own_occupation"]:
        definition_penalty = 85   # strong preference for own-occ → big penalty for inside super
    elif inp["existing_tpd_definition"] == "ADL":
        definition_penalty = 70   # ADL is weakest — should upgrade, can't get own-occ in super
    else:
        definition_penalty = 30   # any-occ in super is acceptable

    # 2. Tax efficiency — inside super benefit is taxed ~22% for under-60 members
    #    Higher tax penalty for inside super when member is under 60 and high MTR
    if age >= 60:
        tax_penalty = 10  # over 60: TPD benefit from super is tax-free → no penalty
    else:
        tax_penalty = 55  # default: ~22% tax on TPD benefit inside super is a real cost
        if mtr is not None:
            if mtr >= 0.45:
                tax_penalty = 30   # at top MTR, super tax (22%) is lower than marginal — inside super better
            elif mtr >= 0.37:
                tax_penalty = 40
            elif mtr >= 0.325:
                tax_penalty = 50
            else:
                tax_penalty = 65   # low MTR: retail benefit tax-free → outside super better

    # 3. Affordability — inside super (premium from balance, no cashflow impact)
    affordability_benefit = 50  # default: moderate benefit
    if inp["wants_affordability"]:
        affordability_benefit = 80
    balance = inp["account_balance"]
    if balance is not None and balance > 50_000:
        affordability_benefit = max(affordability_benefit, 65)

    # 4. Flexibility — retail
    #    Inside super: trustee controls the policy → flexibility penalty
    flexibility_penalty = 30
    if inp["wants_own_occupation"]:
        flexibility_penalty = 80
    if inp["consider_retail_top_up"]:
        flexibility_penalty = max(flexibility_penalty, 55)

    # 5. Claims certainty — inside super any-occ ~80% vs retail own-occ ~88%
    claims_certainty_penalty = 20   # inside super modest penalty
    if inp["wants_own_occupation"]:
        claims_certainty_penalty = 55  # meaningful gap in approval rates

    # Aggregate
    inside_benefit = (
        affordability_benefit * 0.40 +
        (100 - tax_penalty) * 0.35 +
        (100 - flexibility_penalty) * 0.125 +
        (100 - claims_certainty_penalty) * 0.125
    )
    inside_penalty = (
        definition_penalty * 0.40 +
        tax_penalty * 0.25 +
        flexibility_penalty * 0.20 +
        claims_certainty_penalty * 0.15
    )
    inside_score  = _clamp(inside_benefit - inside_penalty * 0.4, 0, 100)
    retail_score  = _clamp(100 - inside_score, 0, 100)

    # Override if legally must switch off
    if legal_status in ("MUST_BE_SWITCHED_OFF", "OPTED_OUT"):
        recommendation = "RETAIL"
    elif inside_score >= 58:
        recommendation = "INSIDE_SUPER"
    elif retail_score >= 58:
        recommendation = "RETAIL"
    elif abs(inside_score - retail_score) < 8:
        recommendation = "SPLIT_STRATEGY"
    else:
        recommendation = "SPLIT_STRATEGY"  # default to split when uncertain

    reasoning = []
    risks = []

    if affordability_benefit >= 70:
        reasoning.append(
            "Paying TPD premiums from the super balance is cost-efficient and avoids cashflow impact — "
            "inside super scores highly on affordability."
        )
    if age >= 60:
        reasoning.append(
            "Member is aged 60+ — TPD benefits from super are tax-free (ITAA 1997). "
            "Tax advantage strongly favours inside super."
        )
    if inp["wants_own_occupation"]:
        risks.append(
            "Client wants own-occupation TPD definition — this is ONLY available via retail outside super. "
            "Inside super is restricted to any-occupation post-1 July 2014 (SIS Reg 4.07D). "
            "Recommend split: any-occ inside super (up to AAL $100k) + own-occ retail top-up."
        )
    if definition_penalty >= 70:
        risks.append(
            "Any-occupation TPD definition inside super has a lower claims approval rate (~80%) "
            "compared to own-occupation retail (~88%). For clients requiring high definition quality, "
            "a retail top-up is recommended."
        )
    if age < 60 and (mtr is None or (mtr is not None and mtr <= 0.19)):
        risks.append(
            "TPD benefit paid from super is taxed at ~22% (for members under 60). "
            "At low marginal tax rates, after-tax benefit from retail (tax-free) may be significantly higher."
        )

    if recommendation == "SPLIT_STRATEGY":
        reasoning.append(
            "Recommended split strategy: any-occupation TPD inside super up to the AAL (~$100k, "
            "group cover, no underwriting, cost-efficient) + own-occupation TPD retail top-up "
            "outside super for definition quality and full benefit certainty."
        )

    return {
        "recommendation": recommendation,
        "inside_super_score": round(inside_score, 1),
        "retail_score": round(retail_score, 1),
        "dimension_scores": {
            "definition_quality_penalty": round(definition_penalty, 1),
            "tax_efficiency_penalty": round(tax_penalty, 1),
            "affordability_benefit": round(affordability_benefit, 1),
            "flexibility_penalty": round(flexibility_penalty, 1),
            "claims_certainty_penalty": round(claims_certainty_penalty, 1),
        },
        "reasoning": reasoning,
        "risks": risks,
        "inside_super_constraints": [
            "Any-occupation definition only (own-occ banned post-1 Jul 2014 per SIS Reg 4.07D)",
            f"Automatic Acceptance Limit: ${AUTO_ACCEPTANCE_LIMIT_AUD:,} — above this, full underwriting required",
            "SIS permanent incapacity condition of release must be met to pay benefit",
            f"Benefit taxed at {int(TPD_TAX_RATE_UNDER_60 * 100)}% for members under 60 (~22% = 20% + Medicare levy)",
            "Trustee controls the policy — member cannot assign or directly manage",
        ],
        "retail_advantages": [
            "Own-occupation definition available — claims approval rate ~88%",
            "Benefit paid tax-free (not from super, no SIS condition of release)",
            "Full underwriting — certainty about exclusions from day 1",
            "Member controls the policy — can assign, convert or transfer freely",
        ],
    }


# =========================================================================
# UNDERWRITING ASSESSMENT
# =========================================================================

def _eval_underwriting(inp: dict) -> dict:
    height_cm  = inp["height_cm"]
    weight_kg  = inp["weight_kg"]
    conditions = inp["existing_conditions"] or []
    smoker     = inp["is_smoker"]

    bmi = None
    bmi_category = None
    if height_cm and weight_kg:
        bmi = round(weight_kg / ((height_cm / 100) ** 2), 1)
        if bmi < 18.5:
            bmi_category = "UNDERWEIGHT"
        elif bmi < 25:
            bmi_category = "HEALTHY"
        elif bmi < 30:
            bmi_category = "OVERWEIGHT"
        elif bmi < 35:
            bmi_category = "OBESE_CLASS_I"
        else:
            bmi_category = "OBESE_CLASS_II_PLUS"

    proposed_sum = inp["proposed_tpd_sum"] or inp["existing_tpd_sum"] or 0
    above_aal    = proposed_sum > AUTO_ACCEPTANCE_LIMIT_AUD

    risk_flags = []
    if bmi is not None and bmi >= 30:
        risk_flags.append(f"BMI {bmi} (≥30) — likely loading or exclusion under fund underwriting guidelines.")
    if smoker:
        risk_flags.append("Smoker status — additional premium loading expected for group TPD.")
    if conditions:
        risk_flags.append(f"Existing medical conditions noted: {', '.join(conditions)}. Exclusions or loadings may apply.")
    if above_aal:
        risk_flags.append(
            f"Proposed cover (${proposed_sum:,.0f}) exceeds the AAL (${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}). "
            "Full underwriting required for the excess above the AAL (SIS Reg 4.07C). "
            "Clean health profile is important for excess approval."
        )

    overall_risk = "LOW" if not risk_flags else ("MEDIUM" if len(risk_flags) == 1 else "HIGH")

    return {
        "bmi": bmi,
        "bmi_category": bmi_category,
        "is_smoker": smoker,
        "existing_conditions": conditions,
        "proposed_sum_insured": proposed_sum,
        "auto_acceptance_limit": AUTO_ACCEPTANCE_LIMIT_AUD,
        "above_aal": above_aal,
        "risk_flags": risk_flags,
        "overall_risk": overall_risk,
        "aal_note": (
            f"Cover of ${proposed_sum:,.0f} is within the AAL (${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}) — "
            "no underwriting required for group TPD inside super."
            if not above_aal and proposed_sum > 0 else
            f"Cover exceeds the AAL — underwriting required for amounts above ${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}."
            if above_aal else
            f"Sum insured not specified — AAL check deferred. AAL for group TPD inside super is ${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}."
        ),
    }


# =========================================================================
# BENEFICIARY TAX RISK
# =========================================================================

def _eval_beneficiary_tax(inp: dict) -> dict:
    age           = inp["age"] or 0
    has_dependants = inp["has_dependants"]
    num_dependants = inp["number_of_dependants"] or 0

    # TPD benefit to member: taxed at ~22% if under 60 (not a death benefit)
    member_tax_note = (
        f"TPD benefit paid to the member (aged {age}) inside super: "
        f"{'tax-free (aged 60+)' if age >= 60 else f'taxed at approximately {int(TPD_TAX_RATE_UNDER_60 * 100)}% on the taxable component (~22% = 20% tax + 2% Medicare levy). This applies to the taxable component (default ~{int(TAXABLE_COMPONENT_DEFAULT * 100)}% of benefit).'}"
        " The benefit is characterised as a 'disability superannuation benefit' under ITAA 1997 "
        "and must meet the SIS permanent incapacity condition of release."
    )

    # Death after TPD claim: if member dies before receiving the benefit, it is paid as a death benefit
    death_tax_note = (
        "If the TPD claimant dies before the benefit is paid, the amount is treated as a death benefit. "
        "Dependants receive it tax-free; non-dependant adults pay 17% on the taxable component "
        "(15% + 2% Medicare levy)."
    )

    if has_dependants is True or num_dependants > 0:
        risk_level = "LOW"
        beneficiary_note = (
            "Member has dependants — TPD benefit is paid directly to the member (not via beneficiary nomination) "
            "and is subject to the member's own tax treatment (see above). "
            "Dependants may receive any residual super balance tax-free on member's death."
        )
    elif has_dependants is False:
        risk_level = "MEDIUM"
        beneficiary_note = (
            "No dependants indicated. Member receives TPD benefit directly (subject to tax treatment above). "
            "If member has no tax dependants, estate planning should be reviewed — "
            "non-dependant beneficiaries of any residual super balance will pay 17% tax on the taxable component."
        )
    else:
        risk_level = "UNKNOWN"
        beneficiary_note = "Dependant status not provided — cannot assess beneficiary tax risk."

    return {
        "risk_level": risk_level,
        "member_tax_note": member_tax_note,
        "death_tax_note": death_tax_note,
        "beneficiary_note": beneficiary_note,
        "tax_rate_under_60": TPD_TAX_RATE_UNDER_60,
        "tax_rate_over_60": TPD_TAX_RATE_OVER_60,
        "taxable_component_default": TAXABLE_COMPONENT_DEFAULT,
        "sis_condition_of_release_note": (
            "SIS Act permanent incapacity condition: the trustee and insurer must independently be satisfied "
            "that the member is permanently incapacitated (unlikely to ever engage in gainful employment "
            "for which they are reasonably qualified by education, training or experience). "
            "This condition is assessed independently of the TPD policy definition."
        ),
    }


# =========================================================================
# RETIREMENT DRAG
# =========================================================================

def _eval_retirement_drag(inp: dict) -> dict | None:
    premium = inp["proposed_annual_premium"] or inp["existing_annual_premium"]
    if not premium:
        return None

    years = inp["years_to_retirement"] or DEFAULT_YEARS_TO_RETIREMENT
    rate  = inp["assumed_growth_rate"]  or DEFAULT_GROWTH_RATE
    drag  = _future_value_annuity(premium, years, rate)

    return {
        "annual_premium": premium,
        "years_to_retirement": years,
        "assumed_growth_rate": rate,
        "estimated_total_drag": round(drag, 2),
        "explanation": (
            f"Paying ${premium:,.0f} p.a. in TPD premiums from super over {years} years "
            f"reduces the projected retirement balance by approximately ${drag:,.0f} "
            f"(at {rate * 100:.1f}% p.a. compound growth). "
            "This is an opportunity cost indicator only — not a reason alone to cancel essential disability cover."
        ),
    }


# =========================================================================
# MEMBER ACTIONS
# =========================================================================

def _eval_member_actions(
    inp: dict,
    legal_status: str,
    switch_offs: list[dict],
    coverage_needs: dict,
    placement: dict,
) -> list[dict]:
    actions = []
    priority = 1

    # Critical: switch-off has fired → must arrange replacement first
    if legal_status == "MUST_BE_SWITCHED_OFF":
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "CRITICAL",
            "action": (
                "A PYS switch-off trigger has fired — arrange replacement TPD cover BEFORE the fund removes "
                "the existing policy. Consider retail own-occupation TPD outside super immediately."
            ),
            "rationale": "Losing TPD cover without replacement leaves the member unprotected against permanent disability.",
        })
        priority += 1

    # High: under-25 opt-in required
    if legal_status == "ALLOWED_BUT_OPT_IN_REQUIRED":
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "HIGH",
            "action": (
                "Lodge a written opt-in election with the super fund trustee to retain TPD cover. "
                "Without this, the under-25 rule will cause the cover to be removed (SIS s68AAA(3))."
            ),
            "rationale": "Default TPD cover is not available to members under 25 without an opt-in election.",
        })
        priority += 1

    # High: inactivity approaching 16 months
    inactive_months = inp["account_inactive_months"]
    if inactive_months is not None and 9 <= inactive_months < 16:
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "HIGH",
            "action": (
                f"Account has been inactive for {inactive_months} months — "
                f"TPD cover will cease at 16 months. Lodge an opt-in election immediately "
                "or arrange a contribution to reset the inactivity clock."
            ),
            "rationale": f"Only {16 - inactive_months} months remain before the PYS inactivity switch-off is triggered.",
        })
        priority += 1

    # High: definition non-compliant (own-occ in super post-Jul 2014)
    definition = inp["existing_tpd_definition"]
    inception  = inp["policy_inception_date"]
    cover_in_super = inp["cover_is_inside_super"]
    is_post_2014_own_occ = (
        cover_in_super and
        definition == "OWN_OCCUPATION" and
        inception is not None and
        inception >= SIS_REG_407D_CUTOFF_DATE
    )
    if is_post_2014_own_occ:
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "HIGH",
            "action": (
                "Existing TPD cover appears to use an own-occupation definition inside super "
                "for a policy commenced post-1 July 2014. This may not comply with SIS Reg 4.07D. "
                "Seek legal/compliance review and arrange replacement with an any-occupation definition."
            ),
            "rationale": "Own-occupation TPD is banned inside super for new policies post-1 July 2014.",
        })
        priority += 1

    # Medium: shortfall identified
    shortfall = coverage_needs.get("shortfall_estimate") if coverage_needs.get("needs_analysis_available") else None
    shortfall_level = coverage_needs.get("shortfall_level")
    if shortfall_level in ("MODERATE", "SIGNIFICANT", "CRITICAL"):
        tpd_need_low  = coverage_needs.get("tpd_need_low", 0)
        tpd_need_high = coverage_needs.get("tpd_need_high", 0)
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "HIGH" if shortfall_level == "CRITICAL" else "MEDIUM",
            "action": (
                f"TPD cover shortfall is {shortfall_level} (estimated ${shortfall:,.0f} shortfall). "
                f"Consider increasing cover to ${tpd_need_low:,.0f}–${tpd_need_high:,.0f}. "
                "Inside super: increase group cover up to the AAL ($100k) without underwriting. "
                "For amounts above the AAL, arrange retail TPD top-up."
            ),
            "rationale": f"Estimated TPD lump sum need of ${tpd_need_low:,.0f} exceeds current cover.",
        })
        priority += 1

    # Medium: wants own-occ — recommend split strategy
    if inp["wants_own_occupation"]:
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "MEDIUM",
            "action": (
                "Implement split strategy: (1) retain/establish any-occupation TPD inside super "
                f"up to the AAL (${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}, no underwriting); "
                "(2) apply for own-occupation TPD retail policy outside super for definition quality "
                "and a tax-free benefit."
            ),
            "rationale": (
                "Own-occupation TPD is not available inside super. A split strategy captures the cost efficiency "
                "of group cover inside super while achieving definition quality via retail."
            ),
        })
        priority += 1

    # Medium: placement is split or retail
    placement_rec = placement.get("recommendation")
    if placement_rec == "RETAIL" and legal_status == "ALLOWED_AND_ACTIVE":
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "MEDIUM",
            "action": (
                "Placement assessment favours retail TPD outside super. "
                "Obtain retail own-occupation TPD quotes and compare total cost vs definition quality benefit."
            ),
            "rationale": placement.get("risks", ["Retail TPD provides superior definition quality and tax treatment."])[0],
        })
        priority += 1

    # Low: AAL — proposed cover above $100k requires underwriting
    proposed_sum = inp["proposed_tpd_sum"] or 0
    if proposed_sum > AUTO_ACCEPTANCE_LIMIT_AUD:
        actions.append({
            "action_id": f"ACT-{priority:03d}",
            "priority": "LOW",
            "action": (
                f"Proposed TPD cover (${proposed_sum:,.0f}) exceeds the Automatic Acceptance Limit "
                f"(${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f}). Full underwriting is required by the fund insurer "
                "for the amount above the AAL. Prepare health evidence in advance."
            ),
            "rationale": "SIS Reg 4.07C — group cover above the AAL requires full medical underwriting.",
        })
        priority += 1

    return actions


# =========================================================================
# TOOL CLASS
# =========================================================================

class TPDInSuperTool(BaseTool):
    name = "purchase_retain_tpd_in_super"
    version = ENGINE_VERSION
    description = (
        "Evaluates whether TPD insurance inside superannuation is legally permissible and strategically "
        "appropriate under the Protecting Your Super (PYS) framework. Assesses PYS switch-off triggers, "
        "TPD definition compliance (SIS Reg 4.07D — own-occupation banned post-Jul 2014), coverage needs, "
        "placement recommendation (inside super / retail / split), underwriting, retirement drag, "
        "beneficiary tax risk, and required trustee notice schedule."
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "member": {"type": "object", "description": "Member demographics and preferences"},
                "fund": {"type": "object", "description": "Super fund details and inactivity data"},
                "existingCover": {"type": "object", "description": "Existing TPD cover details"},
                "proposedCover": {"type": "object", "description": "Proposed new TPD cover"},
                "elections": {"type": "object", "description": "Opt-in / opt-out election details"},
                "financialPosition": {"type": "object", "description": "Debts, liquid assets, expenses"},
                "health": {"type": "object", "description": "Health profile for underwriting assessment"},
                "adviceContext": {"type": "object", "description": "Retirement horizon and strategic preferences"},
                "evaluationDate": {"type": "string", "description": "ISO 8601 evaluation date"},
            },
        }

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        # 1. Normalize
        inp = _normalize(input_data)

        # 2. Validate
        validation = _validate(input_data, inp)

        # 3. Switch-off triggers
        inactivity  = _eval_inactivity(inp)
        low_balance = _eval_low_balance(inp)
        under_25    = _eval_under_25(inp)
        exceptions  = _eval_exceptions(inp)

        # 4. Legal status
        legal = _eval_legal_status(inactivity, low_balance, under_25, exceptions, inp)
        legal_status_str = legal["status"]

        # 5. Notice schedule
        notice_schedule = _eval_notice_schedule(inp)

        # 6. TPD definition assessment
        definition_assessment = _eval_tpd_definition(inp)

        # 7. Coverage needs analysis
        coverage_needs = _eval_coverage_needs(inp)

        # 8. Placement assessment
        placement = _eval_placement(inp, legal_status_str)

        # 9. Underwriting assessment
        underwriting = _eval_underwriting(inp)

        # 10. Beneficiary tax risk
        beneficiary_tax = _eval_beneficiary_tax(inp)

        # 11. Retirement drag
        retirement_drag = _eval_retirement_drag(inp)

        # 12. Member actions
        member_actions = _eval_member_actions(
            inp,
            legal_status_str,
            legal["switch_off_evaluations"],
            coverage_needs,
            placement,
        )

        # 13. Advice mode
        has_income    = inp["annual_gross_income"] is not None
        has_premium   = (inp["proposed_annual_premium"] or inp["existing_annual_premium"]) is not None
        has_mtr       = inp["marginal_tax_rate"] is not None
        has_ytr       = inp["years_to_retirement"] is not None

        if not validation["isValid"]:
            advice_mode = "NEEDS_MORE_INFO"
        elif has_income and (has_premium or has_mtr or has_ytr):
            advice_mode = "FULL_ANALYSIS"
        elif has_income or has_premium:
            advice_mode = "PARTIAL_ANALYSIS"
        else:
            advice_mode = "GENERAL_GUIDANCE"

        return {
            "validation": validation,
            "legal_status": legal_status_str,
            "legal_reasons": legal["reasons"],
            "switch_off_triggers": legal["switch_off_evaluations"],
            "exceptions_applied": legal["exceptions_applied"],
            "notice_schedule": notice_schedule,
            "tpd_definition_assessment": definition_assessment,
            "coverage_needs_analysis": coverage_needs,
            "placement_assessment": placement,
            "underwriting_assessment": underwriting,
            "beneficiary_tax_risk": beneficiary_tax,
            "retirement_drag_estimate": retirement_drag,
            "member_actions": member_actions,
            "health": input_data.get("health"),
            "advice_mode": advice_mode,
            "missing_info_questions": validation["missingInfoQuestions"],
            "engine_version": ENGINE_VERSION,
            "evaluated_at": inp["evaluation_date"].isoformat(),
        }
