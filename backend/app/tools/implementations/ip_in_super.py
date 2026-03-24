"""
ip_in_super.py — Purchase/Retain Income Protection Insurance In Super tool.

Statutory and regulatory basis:
  Superannuation Industry (Supervision) Act 1993 (Cth) — ss 68A, 68AAA–68AAC
  SIS Regulation 6.15  (IP only if gainfully employed)
  SIS Regulation 4.09  (SMSF — trustee must consider insurance)
  Treasury Laws Amendment (Protecting Your Super Package) Act 2019
  Treasury Laws Amendment (Putting Members' Interests First) Act 2019
  APRA Prudential Standard SPS 250 (Insurance in Superannuation, effective 1 Jul 2022)
  APRA Reporting Standard SRS 251 (Insurance)
  ITAA 1997 — premiums inside super: NOT deductible; benefits: assessable income

Business logic covers:
  - Purchase (new IP cover inside super) vs Retain (existing cover, portability)
  - SIS Act work/employment eligibility test (Reg 6.15)
  - PYS/PMIF switch-off triggers: inactivity (16 months), low balance ($6,000), under-25
  - SPS 250 Insurance Management Framework trustee obligations
  - Portability window (30 days default after leaving employment)
  - Cessation triggers: age 65, not gainfully employed, account inactivity
  - Tax comparison: inside super (non-deductible premium, taxable benefit) vs
    outside super (deductible premium, taxable benefit)
  - Retirement drag from IP premiums eroding super balance
  - Claims workflow: waiting period, temporary incapacity test, benefit is NOT
    a preserved super benefit and is paid directly (taxed at marginal rate)
  - Election management: opt-in / opt-out, successor fund transfer continuity

This tool is deterministic: same input → same output. No LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolValidationError

# =========================================================================
# CONSTANTS
# =========================================================================

ENGINE_VERSION = "1.0.0"

# PYS / PMIF thresholds
INACTIVITY_THRESHOLD_MONTHS    = 16
LOW_BALANCE_THRESHOLD_AUD      = 6_000
UNDER_25_AGE_THRESHOLD         = 25

# IP-specific eligibility
MIN_ELIGIBLE_AGE               = 18
MAX_ELIGIBLE_AGE               = 65          # SIS Reg 6.15 — gainful employment test ends at 65
MIN_WEEKLY_HOURS_WORK_TEST     = 20          # Gainful employment threshold for default IP
DEFAULT_PORTABILITY_WINDOW_DAYS = 30         # After leaving employment/fund, cover may continue

# Superannuation benefit tax rates (ITAA 1997)
CONTRIBUTIONS_TAX_RATE         = 0.15        # 15% on concessional contributions
NON_DEPENDANT_BENEFIT_TAX_RATE = 0.17        # 15% + 2% Medicare on taxable component to non-dependant
IP_BENEFIT_TAX_RATE_NOTE       = "IP benefits paid from super are treated as ordinary assessable income (NOT a super benefit) and taxed at the member's marginal tax rate. PAYG withholding applies."

# Retirement drag
DEFAULT_GROWTH_RATE            = 0.07
DEFAULT_YEARS_TO_RETIREMENT    = 20

# Maximum replacement ratio (APRA IDII sustainability — also applies inside super)
MAX_REPLACEMENT_RATIO          = 0.75        # SIS group IP commonly up to 75–85%

# Standard waiting period options (days)
WAITING_PERIOD_OPTIONS_DAYS    = [30, 60, 90]

# SPS 250 effective date
SPS_250_EFFECTIVE_DATE         = datetime(2022, 7, 1, tzinfo=timezone.utc)
PYS_COMMENCEMENT_DATE          = datetime(2019, 7, 1, tzinfo=timezone.utc)

# =========================================================================
# HELPERS
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


def _days_between(start: datetime, end: datetime) -> int:
    return (end - start).days


def _future_value_annuity(pmt: float, n: float, r: float) -> float:
    if r == 0:
        return pmt * n
    return pmt * (((1 + r) ** n - 1) / r)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# =========================================================================
# NORMALIZE
# =========================================================================

def _normalize(raw: dict) -> dict:
    eval_date = _safe_parse_date(raw.get("evaluationDate")) or datetime.now(timezone.utc)

    m   = raw.get("member") or {}
    f   = raw.get("fund") or {}
    ep  = raw.get("existingCover") or {}
    np_ = raw.get("newCoverProposal") or {}
    el  = raw.get("elections") or {}
    emp = raw.get("employerException") or {}
    cl  = raw.get("claimContext") or {}
    ac  = raw.get("adviceContext") or {}

    dob = _safe_parse_date(m.get("dateOfBirth"))
    age = m.get("age")
    if age is None and dob:
        age = _compute_age(dob, eval_date)

    last_amount_date = _safe_parse_date(f.get("lastAmountReceivedDate"))
    employment_ceased_date = _safe_parse_date(m.get("employmentCeasedDate"))

    return {
        "evaluation_date": eval_date,

        # --- Member ---
        "age":                      age,
        "date_of_birth":            dob,
        "employment_status":        m.get("employmentStatus", "UNKNOWN"),
        "weekly_hours_worked":      m.get("weeklyHoursWorked"),
        "annual_gross_income":      m.get("annualGrossIncome"),
        "marginal_tax_rate":        m.get("marginalTaxRate"),
        "occupation":               m.get("occupation"),
        "occupation_class":         m.get("occupationClass", "UNKNOWN"),
        "is_smoker":                m.get("isSmoker", False),
        "employment_ceased_date":   employment_ceased_date,
        "has_dependants":           m.get("hasDependants"),
        "cashflow_pressure":        m.get("cashflowPressure", False),
        "wants_inside_super":       m.get("wantsInsideSuper"),
        "wants_affordability":      m.get("wantsAffordability", False),

        # --- Fund ---
        "fund_type":                f.get("fundType"),          # "mysuper", "choice", "smsf", "defined_benefit"
        "fund_member_count":        f.get("fundMemberCount"),
        "is_defined_benefit":       f.get("isDefinedBenefitFund", False),
        "is_adf_or_commonwealth":   f.get("isADFOrCommonwealthFund", False),
        "account_balance":          f.get("accountBalance"),
        "last_amount_received_date": last_amount_date,
        "received_amount_in_last_16_months": f.get("receivedAmountInLast16Months"),
        "had_balance_ge6000_after_2019_11_01": f.get("hadBalanceGe6000OnOrAfter2019_11_01"),
        "successor_fund_transfer":  f.get("successorFundTransferOccurred", False),
        "trustee_allows_opt_in_online": f.get("trusteeAllowsOptInOnline", False),

        # --- Existing IP cover (inside super) ---
        "has_existing_cover":       ep.get("hasExistingIPCover", False),
        "existing_insurer":         ep.get("insurerName"),
        "existing_cover_commenced": _safe_parse_date(ep.get("coverCommencedDate")),
        "existing_monthly_benefit": ep.get("monthlyBenefit"),
        "existing_waiting_days":    ep.get("waitingPeriodDays"),
        "existing_benefit_period_months": ep.get("benefitPeriodMonths"),
        "existing_annual_premium":  ep.get("annualPremium"),
        "existing_occupation_def":  ep.get("occupationDefinition", "UNKNOWN"),
        "existing_step_down_applies": ep.get("stepDownApplies", False),
        "existing_has_indexation":  ep.get("hasIndexation", False),
        "existing_portability_available": ep.get("portabilityClauseAvailable", False),
        "existing_portability_window_days": ep.get("portabilityWindowDays", DEFAULT_PORTABILITY_WINDOW_DAYS),
        "existing_has_loadings":    ep.get("hasLoadings", False),
        "existing_has_exclusions":  ep.get("hasExclusions", False),
        "existing_exclusion_details": ep.get("exclusionDetails"),
        "existing_grandfathered":   ep.get("hasGrandfatheredTerms", False),

        # --- New cover proposal (if purchasing) ---
        "proposing_new_cover":      bool(np_.get("monthlyBenefit") or np_.get("annualPremium")),
        "proposed_monthly_benefit": np_.get("monthlyBenefit"),
        "proposed_waiting_days":    np_.get("waitingPeriodDays"),
        "proposed_benefit_period_months": np_.get("benefitPeriodMonths"),
        "proposed_annual_premium":  np_.get("annualPremium"),
        "proposed_occupation_def":  np_.get("occupationDefinition", "UNKNOWN"),
        "proposed_replacement_ratio": np_.get("replacementRatio"),

        # --- Elections ---
        "opted_in_to_retain":       el.get("optedInToRetainInsurance", False),
        "opt_in_date":              _safe_parse_date(el.get("optInElectionDate")),
        "opted_out":                el.get("optedOutOfInsurance", False),
        "opt_out_date":             _safe_parse_date(el.get("optOutDate")),
        "prior_election_via_successor": el.get("priorElectionCarriedViaSuccessorTransfer", False),
        "equivalent_rights_confirmed":  el.get("equivalentRightsConfirmed", False),

        # --- Employer exception ---
        "employer_notified_trustee": emp.get("employerHasNotifiedTrusteeInWriting", False),
        "employer_contributions_exceed_sg": emp.get("employerContributionsExceedSGByInsuranceFee", False),
        "dangerous_occupation_election": emp.get("dangerousOccupationElectionInForce", False),

        # --- Claim context (if assessing a live/pending claim) ---
        "claim_in_progress":        cl.get("claimInProgress", False),
        "disability_onset_date":    _safe_parse_date(cl.get("disabilityOnsetDate")),
        "medical_evidence_provided": cl.get("medicalEvidenceProvided", False),
        "income_evidence_provided": cl.get("incomeEvidenceProvided", False),
        "employer_statement_provided": cl.get("employerStatementProvided", False),

        # --- Advice context ---
        "years_to_retirement":      ac.get("yearsToRetirement"),
        "assumed_growth_rate":      ac.get("assumedGrowthRate"),
        "monthly_expenses":         ac.get("monthlyExpenses"),
        "concessional_contributions_high": ac.get("concessionalContributionsAlreadyHigh", False),
        "contribution_cap_pressure": ac.get("contributionCapPressure", False),
        "need_own_occupation_def":  ac.get("needForOwnOccupationDefinition", False),
        "need_policy_flexibility":  ac.get("needForPolicyFlexibility", False),
        "retirement_priority_high": ac.get("retirementPriorityHigh", False),
        "super_balance_adequacy":   ac.get("superBalanceAdequacy"),
    }


# =========================================================================
# VALIDATION
# =========================================================================

def _validate(raw: dict, inp: dict) -> dict:
    errors   = []
    warnings = []
    questions = []

    m = raw.get("member") or {}
    f = raw.get("fund") or {}

    if inp["age"] is None:
        errors.append({"field": "member.age", "message": "Member age or date of birth is required.", "category": "LEGAL"})
        questions.append({"id": "IPQ-S-001", "question": "What is the member's age or date of birth?", "category": "LEGAL", "blocking": True})

    if not f.get("fundType"):
        errors.append({"field": "fund.fundType", "message": "Fund type is required (mysuper, choice, smsf, defined_benefit).", "category": "LEGAL"})
        questions.append({"id": "IPQ-S-002", "question": "What type of super fund does the member hold (MySuper, Choice, SMSF, defined benefit)?", "category": "LEGAL", "blocking": True})

    if inp["employment_status"] == "UNKNOWN":
        warnings.append({"field": "member.employmentStatus", "message": "Employment status not provided — SIS Reg 6.15 work test cannot be verified."})
        questions.append({"id": "IPQ-S-003", "question": "What is the member's current employment status (employed full-time, part-time, self-employed, unemployed)?", "category": "ELIGIBILITY", "blocking": True})

    if inp["annual_gross_income"] is None:
        warnings.append({"field": "member.annualGrossIncome", "message": "Income not provided — benefit replacement ratio and affordability cannot be calculated."})
        questions.append({"id": "IPQ-S-004", "question": "What is the member's annual gross income (pre-tax)?", "category": "BENEFIT_DESIGN", "blocking": False})

    if inp["account_balance"] is None:
        warnings.append({"field": "fund.accountBalance", "message": "Super account balance not provided — low-balance switch-off check and retirement drag cannot be assessed."})
        questions.append({"id": "IPQ-S-005", "question": "What is the current super account balance?", "category": "LEGAL", "blocking": False})

    ep = raw.get("existingCover") or {}
    if ep.get("hasExistingIPCover") and ep.get("monthlyBenefit") is None:
        warnings.append({"field": "existingCover.monthlyBenefit", "message": "Existing monthly benefit not provided — cover assessment will be incomplete."})
        questions.append({"id": "IPQ-S-006", "question": "What is the existing IP cover monthly benefit amount?", "category": "EXISTING_COVER", "blocking": False})

    ac = raw.get("adviceContext") or {}
    if ac.get("yearsToRetirement") is None:
        questions.append({"id": "IPQ-S-007", "question": "How many years until the member plans to retire? (Used for retirement drag analysis.)", "category": "RETIREMENT", "blocking": False})

    is_valid = len(errors) == 0
    return {"isValid": is_valid, "errors": errors, "warnings": warnings, "missingInfoQuestions": questions}


# =========================================================================
# SIS REG 6.15 — WORK TEST / EMPLOYMENT ELIGIBILITY
# =========================================================================

def _eval_work_test(inp: dict) -> dict:
    """
    SIS Reg 6.15: IP (temporary incapacity) cover inside super is only permissible
    while the member has an insurable interest — i.e. is gainfully employed
    (works ≥ 20 hours/week on average).
    """
    status  = inp["employment_status"]
    hours   = inp["weekly_hours_worked"]
    age     = inp["age"] or 0

    passes   = False
    reasons  = []
    warnings = []

    if age >= MAX_ELIGIBLE_AGE:
        reasons.append(f"Member is age {age} — IP cover ceases at age {MAX_ELIGIBLE_AGE} (gainful employment test no longer satisfied for IP purposes).")
        return {"passes": False, "reasons": reasons, "warnings": warnings, "employment_status": status}

    if age < MIN_ELIGIBLE_AGE:
        reasons.append(f"Member is age {age} — below minimum eligible age of {MIN_ELIGIBLE_AGE}.")
        return {"passes": False, "reasons": reasons, "warnings": warnings, "employment_status": status}

    if status in ("EMPLOYED_FULL_TIME", "SELF_EMPLOYED"):
        passes = True
        reasons.append(f"Member is {status} — gainful employment satisfied.")
    elif status == "EMPLOYED_PART_TIME":
        if hours is not None:
            if hours >= MIN_WEEKLY_HOURS_WORK_TEST:
                passes = True
                reasons.append(f"Member works {hours} hours/week (≥{MIN_WEEKLY_HOURS_WORK_TEST}) — gainful employment satisfied.")
            else:
                reasons.append(f"Member works {hours} hours/week — below the {MIN_WEEKLY_HOURS_WORK_TEST}-hour threshold for gainful employment (SIS Reg 6.15). IP cover may not be permissible.")
        else:
            passes = True   # assume passes; flag for manual check
            warnings.append(f"Part-time employment confirmed but weekly hours not provided — trustees should verify hours meet the {MIN_WEEKLY_HOURS_WORK_TEST}-hour threshold under SIS Reg 6.15.")
    elif status == "UNEMPLOYED":
        reasons.append("Member is unemployed — gainful employment test fails. IP cover inside super cannot be maintained (SIS Reg 6.15).")
    elif status == "ON_CLAIM":
        passes = True   # already on IP claim — cover was in force at onset
        reasons.append("Member is currently on an IP claim — cover was in force at disability onset. Ongoing eligibility determined by the insurer under the policy terms, not re-assessed here.")
    else:
        warnings.append("Employment status unknown — work test cannot be verified. Obtain employment evidence before issuing or retaining IP cover.")
        passes = True   # partial — flag for review

    return {"passes": passes, "reasons": reasons, "warnings": warnings, "employment_status": status}


# =========================================================================
# PYS SWITCH-OFF TRIGGER EVALUATIONS
# =========================================================================

def _eval_inactivity(inp: dict) -> dict:
    triggered    = False
    months_inactive = 0
    last_date    = inp["last_amount_received_date"]
    received_flag = inp["received_amount_in_last_16_months"]

    if last_date:
        months_inactive = _months_between(last_date, inp["evaluation_date"])
        triggered = months_inactive >= INACTIVITY_THRESHOLD_MONTHS
        basis = f"Computed {months_inactive} months since last amount received."
    elif received_flag is not None:
        triggered = not received_flag
        basis = f"Caller-supplied flag: receivedAmountInLast16Months={received_flag}."
    else:
        basis = "Inactivity cannot be fully assessed — no date or flag provided."

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
    balance = inp["account_balance"]
    # If balance was not provided, skip the check entirely rather than defaulting to 0
    # (which would incorrectly trigger the switch-off for every client with unknown balance)
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
    grandfathered = inp["had_balance_ge6000_after_2019_11_01"] is True
    post_pys      = inp["evaluation_date"] >= PYS_COMMENCEMENT_DATE
    triggered     = below and not grandfathered and post_pys

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
    age       = inp["age"]
    is_u25    = age is not None and age < UNDER_25_AGE_THRESHOLD
    is_mysuper = (inp["fund_type"] or "").lower() == "mysuper"
    triggered = is_u25 and is_mysuper and not inp["opted_in_to_retain"]

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

    count = inp["fund_member_count"]
    small_fund = count is not None and count < 5
    exceptions.append({
        "applied": small_fund,
        "type": "SMALL_FUND_CARVE_OUT",
        "reason": f"Fund has {count} members — small fund carve-out applies." if small_fund else "Small fund carve-out does not apply.",
    })

    exceptions.append({
        "applied": inp["is_defined_benefit"],
        "type": "DEFINED_BENEFIT",
        "reason": "Member is in a defined benefit fund — PYS switch-off rules do not apply to this fund type." if inp["is_defined_benefit"] else "Not a defined benefit fund.",
    })

    exceptions.append({
        "applied": inp["is_adf_or_commonwealth"],
        "type": "ADF_COMMONWEALTH",
        "reason": "ADF / Commonwealth fund exception applies." if inp["is_adf_or_commonwealth"] else "ADF exception does not apply.",
    })

    employer_applies = inp["employer_notified_trustee"] and inp["employer_contributions_exceed_sg"]
    exceptions.append({
        "applied": employer_applies,
        "type": "EMPLOYER_SPONSORED_CONTRIBUTION",
        "reason": "Employer-sponsored exception applies (SIS s68AAA(4A))." if employer_applies else "Employer-sponsored exception does not apply.",
    })

    exceptions.append({
        "applied": inp["dangerous_occupation_election"],
        "type": "DANGEROUS_OCCUPATION",
        "reason": "Dangerous occupation election is in force." if inp["dangerous_occupation_election"] else "Dangerous occupation election not in force.",
    })

    successor_applies = inp["prior_election_via_successor"] and inp["equivalent_rights_confirmed"]
    exceptions.append({
        "applied": successor_applies,
        "type": "SUCCESSOR_FUND_TRANSFER",
        "reason": "Successor fund transfer — prior election confirmed as carried." if successor_applies else "Successor fund exception does not apply.",
    })

    return exceptions


# =========================================================================
# PORTABILITY ASSESSMENT (Retain scenario)
# =========================================================================

def _eval_portability(inp: dict) -> dict:
    """
    If the member has left employment or the fund, assess whether existing
    IP cover can be retained within a portability window.
    """
    if not inp["has_existing_cover"]:
        return {"applies": False, "status": "NO_EXISTING_COVER", "notes": []}

    employment_ceased = inp["employment_ceased_date"]
    portability_available = inp["existing_portability_available"]
    window_days = inp["existing_portability_window_days"] or DEFAULT_PORTABILITY_WINDOW_DAYS

    if not employment_ceased:
        return {
            "applies": False,
            "status": "STILL_EMPLOYED",
            "notes": ["Member has not left employment — portability is not yet relevant. Existing cover continues while gainfully employed."],
        }

    days_since_ceased = _days_between(employment_ceased, inp["evaluation_date"])

    if not portability_available:
        return {
            "applies": False,
            "status": "NO_PORTABILITY_CLAUSE",
            "days_since_employment_ceased": days_since_ceased,
            "notes": [
                "The existing policy does not have a portability clause. Cover ceases when the member leaves employment/fund.",
                "Options: (a) purchase new cover in the new fund, (b) apply for personal IP cover outside super.",
            ],
        }

    if days_since_ceased > window_days:
        return {
            "applies": False,
            "status": "PORTABILITY_WINDOW_EXPIRED",
            "days_since_employment_ceased": days_since_ceased,
            "portability_window_days": window_days,
            "notes": [
                f"Portability window of {window_days} days has expired ({days_since_ceased} days since employment ceased).",
                "Cover cannot be ported — a new application with fresh underwriting will be required.",
            ],
        }

    days_remaining = window_days - days_since_ceased
    return {
        "applies": True,
        "status": "WITHIN_PORTABILITY_WINDOW",
        "days_since_employment_ceased": days_since_ceased,
        "portability_window_days": window_days,
        "days_remaining_in_window": days_remaining,
        "notes": [
            f"Member is within the portability window ({days_remaining} days remaining).",
            "Cover can be retained by continuing premium payments — no new underwriting required.",
            f"If cover is not ported within {days_remaining} days, it will lapse and re-application will be needed.",
        ],
    }


# =========================================================================
# CESSATION TRIGGERS
# =========================================================================

def _eval_cessation_triggers(inp: dict, work_test: dict) -> dict:
    """
    IP inside super ceases at: age 65, not gainfully employed, account inactivity.
    """
    triggers = []

    if inp["age"] is not None and inp["age"] >= MAX_ELIGIBLE_AGE:
        triggers.append({
            "trigger": "AGE_65",
            "fired": True,
            "reason": f"Member has reached age {inp['age']} — IP cover inside super ceases at age {MAX_ELIGIBLE_AGE}.",
        })

    if not work_test["passes"] and inp["employment_status"] not in ("ON_CLAIM", "UNKNOWN"):
        triggers.append({
            "trigger": "NOT_GAINFULLY_EMPLOYED",
            "fired": True,
            "reason": f"Work test fails ({inp['employment_status']}) — IP cover inside super cannot be maintained under SIS Reg 6.15.",
        })

    if inp["opted_out"]:
        triggers.append({
            "trigger": "MEMBER_OPT_OUT",
            "fired": True,
            "reason": "Member has elected to opt out of insurance inside super.",
        })

    any_fired = any(t["fired"] for t in triggers)
    return {
        "any_cessation_trigger_fired": any_fired,
        "triggers": triggers,
        "cessation_note": (
            "One or more cessation triggers have fired — IP cover must cease or be reviewed immediately."
            if any_fired else
            "No cessation triggers fired."
        ),
    }


# =========================================================================
# LEGAL STATUS RESOLUTION
# =========================================================================

def _resolve_legal_status(inp: dict, validation: dict, work_test: dict) -> dict:
    if not validation["isValid"]:
        return {
            "status": "NEEDS_MORE_INFO",
            "permissibility": "UNKNOWN",
            "reasons": ["Validation failed — mandatory fields missing."] + [e["message"] for e in validation["errors"]],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
        }

    # Work test is foundational for IP in super
    if not work_test["passes"] and inp["employment_status"] not in ("UNKNOWN", "ON_CLAIM"):
        return {
            "status": "NOT_ELIGIBLE_WORK_TEST",
            "permissibility": "NOT_PERMITTED",
            "reasons": work_test["reasons"],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
        }

    # Opt-out election
    if inp["opted_out"]:
        return {
            "status": "OPTED_OUT",
            "permissibility": "PERMITTED_BUT_MEMBER_DECLINED",
            "reasons": ["Member has elected to opt out of insurance inside super."],
            "switch_off_evaluations": [],
            "exceptions_applied": [],
        }

    # PYS switch-off triggers
    inactivity  = _eval_inactivity(inp)
    low_balance = _eval_low_balance(inp)
    under_25    = _eval_under_25(inp)
    exceptions  = _eval_exceptions(inp)
    any_exception = any(e["applied"] for e in exceptions)

    has_opt_in = inp["opted_in_to_retain"] and inp["opt_in_date"] is not None
    successor_ok = inp["prior_election_via_successor"] and inp["equivalent_rights_confirmed"]
    election_overrides = has_opt_in or successor_ok

    ALL_TRIGGER_EXCEPTION_TYPES = {"SMALL_FUND_CARVE_OUT", "DEFINED_BENEFIT", "ADF_COMMONWEALTH", "SUCCESSOR_FUND_TRANSFER"}
    PARTIAL_EXCEPTION_TYPES     = {"EMPLOYER_SPONSORED_CONTRIBUTION", "DANGEROUS_OCCUPATION"}

    def apply_overrides(trig: dict, trigger_key: str) -> dict:
        if not trig["triggered"]:
            return trig
        exc_override = any(
            e["applied"] and (
                e["type"] in ALL_TRIGGER_EXCEPTION_TYPES or
                (e["type"] in PARTIAL_EXCEPTION_TYPES and trigger_key != "UNDER_25_NO_ELECTION")
            )
            for e in exceptions
        )
        effectively_active = not exc_override and not election_overrides
        return {**trig, "overridden_by_exception": exc_override, "overridden_by_election": election_overrides, "effectively_active": effectively_active}

    final_inactivity  = apply_overrides(inactivity,  "INACTIVITY_16_MONTHS")
    final_low_balance = apply_overrides(low_balance,  "LOW_BALANCE_UNDER_6000")
    final_under_25    = apply_overrides(under_25,     "UNDER_25_NO_ELECTION")
    switch_offs       = [final_inactivity, final_low_balance, final_under_25]

    # Successor fund unresolved
    if inp["successor_fund_transfer"] and not inp["equivalent_rights_confirmed"] and not any_exception:
        return {
            "status": "COMPLEX_RIGHTS_CHECK_REQUIRED",
            "permissibility": "PERMITTED",
            "reasons": ["Successor fund transfer occurred but equivalent rights are unconfirmed — manual review required."],
            "switch_off_evaluations": switch_offs,
            "exceptions_applied": exceptions,
        }

    hard_active = final_inactivity["effectively_active"] or final_low_balance["effectively_active"]
    soft_active = final_under_25["effectively_active"]

    reasons = []
    if hard_active:
        status = "MUST_BE_SWITCHED_OFF"
        reasons.append(final_inactivity["reason"] if final_inactivity["effectively_active"] else final_low_balance["reason"])
        reasons.append("IP cover inside super must cease unless the member lodges an opt-in election (SIS ss68AAA–68AAC).")
    elif soft_active:
        status = "ALLOWED_BUT_OPT_IN_REQUIRED"
        reasons.append(final_under_25["reason"])
        reasons.append("Member must lodge a written direction with the trustee to opt in to retain IP cover.")
    else:
        status = "ALLOWED_AND_ACTIVE"
        reasons.append("No active PYS switch-off triggers. IP cover is legally permissible and may continue.")
        if any_exception:
            reasons.append(f"Statutory exceptions applied: {[e['type'] for e in exceptions if e['applied']]}.")
        if has_opt_in:
            reasons.append("Member has a valid opt-in election on file.")
        if work_test["warnings"]:
            reasons += work_test["warnings"]

    return {
        "status": status,
        "permissibility": "PERMITTED",
        "reasons": reasons,
        "switch_off_evaluations": switch_offs,
        "exceptions_applied": exceptions,
    }


# =========================================================================
# TAX COMPARISON — INSIDE VS OUTSIDE SUPER
# =========================================================================

def _calc_tax_comparison(inp: dict) -> dict:
    """
    Inside super: premiums NOT deductible (paid from after-contributions-tax money).
    Outside super: premiums ARE deductible as a work-related expense.
    Benefits in BOTH cases: taxable as ordinary income at marginal rate.

    Source: ITAA 1997; ATO — IP benefits from super are NOT a super benefit.
    """
    annual_premium = inp["existing_annual_premium"] or inp["proposed_annual_premium"]
    mtr = inp["marginal_tax_rate"]

    notes = [
        IP_BENEFIT_TAX_RATE_NOTE,
        "IP benefits paid from within a super fund are treated as ordinary assessable income — NOT as a superannuation benefit. They are NOT subject to the 15% super tax rate and NOT tax-free to dependants.",
        "PAYG withholding applies to IP benefit payments in the same way as salary/wages.",
    ]

    inside_vs_outside = {
        "inside_super_premium_deductible": False,
        "outside_super_premium_deductible": True,
        "benefit_tax_treatment": "MARGINAL_RATE_BOTH",
        "notes": notes,
    }

    if annual_premium and mtr:
        deductibility_saving_pa = round(annual_premium * mtr, 2)
        contributions_tax_cost  = round(annual_premium * CONTRIBUTIONS_TAX_RATE, 2)
        net_cost_inside  = annual_premium  # no deduction, but may use pre-tax contributions
        net_cost_outside = round(annual_premium * (1 - mtr), 2)

        inside_vs_outside.update({
            "annual_premium":                 annual_premium,
            "marginal_tax_rate":              mtr,
            "outside_super_deductibility_saving_pa": deductibility_saving_pa,
            "inside_super_contributions_tax_pa": contributions_tax_cost,
            "net_effective_cost_inside_super":   net_cost_inside,
            "net_effective_cost_outside_super":  net_cost_outside,
            "cost_differential_pa":              round(net_cost_inside - net_cost_outside, 2),
            "tax_favours_outside": net_cost_outside < net_cost_inside,
            "tax_summary": (
                f"Outside super is more tax-efficient by ${net_cost_inside - net_cost_outside:,.0f} pa "
                f"(premium deduction saves ${deductibility_saving_pa:,.0f} pa at {mtr*100:.0f}% MTR). "
                "However, inside super may still be preferred if cash flow is constrained."
                if net_cost_outside < net_cost_inside else
                "Inside super is cost-comparable or preferred given the marginal tax rate and contributions structure."
            ),
        })

    return inside_vs_outside


# =========================================================================
# RETIREMENT DRAG
# =========================================================================

def _calc_retirement_drag(inp: dict) -> dict | None:
    premium = inp["existing_annual_premium"] or inp["proposed_annual_premium"]
    if not premium:
        return None
    years = inp["years_to_retirement"] or DEFAULT_YEARS_TO_RETIREMENT
    rate  = inp["assumed_growth_rate"] or DEFAULT_GROWTH_RATE
    drag  = _future_value_annuity(premium, years, rate)

    return {
        "annual_premium":            premium,
        "years_to_retirement":       years,
        "assumed_growth_rate":       rate,
        "estimated_balance_reduction": round(drag, 2),
        "explanation": (
            f"Paying ${premium:,.0f} pa in IP premiums from super over {years} years "
            f"reduces the projected retirement balance by approximately ${drag:,.0f} "
            f"(at {rate*100:.1f}% pa compound growth). This is an opportunity cost indicator only, "
            "not a reason alone to cancel essential income protection cover."
        ),
    }


# =========================================================================
# BENEFIT NEED INSIDE SUPER
# =========================================================================

def _calc_benefit_need(inp: dict) -> dict:
    """
    Calculate the income replacement need.
    Group IP inside super typically replaces up to 75-85% of gross income.
    """
    gross = inp["annual_gross_income"] or 0
    if gross == 0:
        return {"status": "INCOME_NOT_PROVIDED", "assumptions": ["Annual gross income not provided — benefit need cannot be calculated."]}

    monthly_gross = gross / 12
    max_monthly   = monthly_gross * MAX_REPLACEMENT_RATIO
    existing_mb   = inp["existing_monthly_benefit"] or 0
    proposed_mb   = inp["proposed_monthly_benefit"] or 0
    active_mb     = proposed_mb if inp["proposing_new_cover"] else existing_mb

    gap = max(0.0, max_monthly - active_mb)

    return {
        "annual_gross_income":        gross,
        "monthly_gross_income":       round(monthly_gross, 2),
        "max_monthly_benefit":        round(max_monthly, 2),
        "max_replacement_ratio":      MAX_REPLACEMENT_RATIO,
        "active_monthly_benefit":     round(active_mb, 2),
        "monthly_shortfall":          round(gap, 2),
        "replacement_ratio_note":     f"Group IP inside super typically covers up to {int(MAX_REPLACEMENT_RATIO*100)}% of gross income. Benefit replaces salary if unable to work.",
        "replacement_ratio_compliance": (
            "WITHIN_LIMIT" if active_mb <= max_monthly
            else f"EXCEEDS_LIMIT — monthly benefit ${active_mb:,.0f} exceeds {int(MAX_REPLACEMENT_RATIO*100)}% of monthly gross income ${max_monthly:,.0f}."
        ),
    }


# =========================================================================
# CLAIM CONTEXT ASSESSMENT
# =========================================================================

def _eval_claim(inp: dict) -> dict | None:
    """
    If a claim is in progress, evaluate the evidence requirements and
    confirm the benefit payment rules (IP is NOT a preserved benefit).
    """
    if not inp["claim_in_progress"]:
        return None

    issues   = []
    actions  = []
    onset    = inp["disability_onset_date"]
    waiting  = inp["existing_waiting_days"] or 30

    waiting_complete = False
    if onset:
        days_disabled = _days_between(onset, inp["evaluation_date"])
        waiting_complete = days_disabled >= waiting
        if not waiting_complete:
            remaining = waiting - days_disabled
            issues.append(f"Waiting period of {waiting} days has not yet elapsed — {remaining} days remaining before benefit becomes payable.")
        else:
            actions.append(f"Waiting period ({waiting} days) has elapsed — benefits can commence payment.")
    else:
        issues.append("Disability onset date not provided — waiting period cannot be assessed.")

    if not inp["medical_evidence_provided"]:
        actions.append("REQUIRED: Obtain medical evidence (GP and specialist reports confirming inability to work).")
    if not inp["income_evidence_provided"]:
        actions.append("REQUIRED: Obtain income evidence (payslips, tax returns, or ATO income statement).")
    if not inp["employer_statement_provided"]:
        actions.append("REQUIRED: Obtain employer statement confirming absence from work.")

    return {
        "claim_in_progress":      True,
        "disability_onset_date":  onset.isoformat() if onset else None,
        "waiting_period_days":    waiting,
        "waiting_period_complete": waiting_complete,
        "benefit_tax_note":       IP_BENEFIT_TAX_RATE_NOTE,
        "not_a_super_benefit_note": (
            "IP benefits paid from super are NOT preserved super benefits and do NOT require "
            "a condition of release. They are paid directly to the member as taxable income."
        ),
        "evidence_checklist": {
            "medical_evidence":   inp["medical_evidence_provided"],
            "income_evidence":    inp["income_evidence_provided"],
            "employer_statement": inp["employer_statement_provided"],
        },
        "outstanding_actions": actions,
        "outstanding_issues":  issues,
    }


# =========================================================================
# PLACEMENT ASSESSMENT — INSIDE VS OUTSIDE SUPER
# =========================================================================

def _calc_placement_scores(inp: dict) -> dict:
    cashflow_benefit = 30
    if inp["cashflow_pressure"]:
        cashflow_benefit = 80
    elif inp["wants_affordability"]:
        cashflow_benefit = 65

    tax_benefit = 40
    mtr = inp["marginal_tax_rate"]
    if mtr is not None:
        # Inside super: no deduction means LOWER tax benefit vs outside
        # So high MTR actually FAVOURS outside super for IP
        if mtr >= 0.45:
            tax_benefit = 20   # outside is clearly better at top rate
        elif mtr >= 0.37:
            tax_benefit = 30
        elif mtr >= 0.325:
            tax_benefit = 50
        elif mtr >= 0.19:
            tax_benefit = 60
        else:
            tax_benefit = 70   # low MTR: deductibility benefit outside is small → inside fine
    if inp["concessional_contributions_high"]:
        tax_benefit = max(15, tax_benefit - 20)

    convenience_benefit = 40
    if inp["wants_inside_super"]:
        convenience_benefit = 70
    if inp["trustee_allows_opt_in_online"]:
        convenience_benefit = min(convenience_benefit + 10, 75)

    # Penalties for inside super
    retirement_penalty = 40
    if inp["retirement_priority_high"]:
        retirement_penalty = 80
    ytr = inp["years_to_retirement"]
    if ytr is not None:
        if ytr <= 5:
            retirement_penalty = max(retirement_penalty, 90)
        elif ytr <= 10:
            retirement_penalty = max(retirement_penalty, 75)
        elif ytr <= 20:
            retirement_penalty = max(retirement_penalty, 55)
    if inp["super_balance_adequacy"] == "low":
        retirement_penalty = max(retirement_penalty, 65)

    definition_penalty = 20
    if inp["need_own_occupation_def"]:
        definition_penalty = 85   # own-occupation defs harder to get inside super
    if inp["need_policy_flexibility"]:
        definition_penalty = max(definition_penalty, 70)

    cap_penalty = 20
    if inp["contribution_cap_pressure"]:
        cap_penalty = 75

    return {
        "cashflow_benefit":              _clamp(cashflow_benefit, 0, 100),
        "tax_efficiency_benefit":        _clamp(tax_benefit, 0, 100),
        "convenience_benefit":           _clamp(convenience_benefit, 0, 100),
        "retirement_erosion_penalty":    _clamp(retirement_penalty, 0, 100),
        "definition_quality_penalty":    _clamp(definition_penalty, 0, 100),
        "contribution_cap_penalty":      _clamp(cap_penalty, 0, 100),
    }


def _eval_placement(inp: dict, legal_status: str, scores: dict) -> dict:
    benefit_total = (
        scores["cashflow_benefit"]       * 0.40 +
        scores["tax_efficiency_benefit"] * 0.35 +
        scores["convenience_benefit"]    * 0.25
    )
    penalty_total = (
        scores["retirement_erosion_penalty"]  * 0.40 +
        scores["definition_quality_penalty"]  * 0.35 +
        scores["contribution_cap_penalty"]    * 0.25
    )
    inside_score  = _clamp(benefit_total - (penalty_total * 0.5), 0, 100)
    outside_score = _clamp(100 - inside_score, 0, 100)

    if legal_status in ("MUST_BE_SWITCHED_OFF", "NOT_ELIGIBLE_WORK_TEST", "OPTED_OUT"):
        recommendation = "OUTSIDE_SUPER"
    elif inside_score >= 60:
        recommendation = "INSIDE_SUPER"
    elif outside_score >= 60:
        recommendation = "OUTSIDE_SUPER"
    elif abs(inside_score - outside_score) < 10:
        recommendation = "SPLIT_STRATEGY"
    else:
        recommendation = "INSUFFICIENT_INFO"

    reasoning = []
    risks     = []

    if scores["cashflow_benefit"] >= 65:
        reasoning.append("Cash flow pressure makes inside-super IP funding beneficial — premium deducted automatically from balance.")
    if scores["tax_efficiency_benefit"] <= 30:
        reasoning.append("High marginal tax rate means outside-super IP is more tax-efficient (premiums are deductible).")
    if scores["retirement_erosion_penalty"] >= 70:
        risks.append("IP premiums from super reduce the compound growth of the retirement balance — consider outside super if retirement adequacy is a concern.")
    if scores["definition_quality_penalty"] >= 70:
        risks.append("Own-occupation definitions and flexible policy terms are harder to obtain via group super IP — consider standalone IP outside super.")

    return {
        "recommendation":    recommendation,
        "inside_score":      round(inside_score, 1),
        "outside_score":     round(outside_score, 1),
        "benefit_breakdown": {k: v for k, v in scores.items() if "benefit" in k},
        "penalty_breakdown": {k: v for k, v in scores.items() if "penalty" in k},
        "reasoning":         reasoning,
        "risks":             risks,
    }


# =========================================================================
# COMPLIANCE FLAGS — SPS 250 / SIS / TRUSTEE DUTIES
# =========================================================================

def _build_compliance_flags(inp: dict, work_test: dict, cessation: dict) -> list[dict]:
    flags = []

    # SPS 250 Insurance Management Framework
    flags.append({
        "code":     "IP-SUPER-SPS250-001",
        "domain":   "TRUSTEE_GOVERNANCE",
        "severity": "INFO",
        "message":  "SPS 250 (effective 1 Jul 2022) requires the trustee to maintain an Insurance Management Framework covering: IP product design and target market, underwriting standards, insurer selection and monitoring, ongoing member outcome monitoring, and actuarial certification of premiums. Ensure the fund's IMF documents IP cover appropriately.",
    })

    # SIS Reg 4.09 — SMSF
    if (inp["fund_type"] or "").lower() == "smsf":
        flags.append({
            "code":     "IP-SUPER-REG409-001",
            "domain":   "TRUSTEE_GOVERNANCE",
            "severity": "WARNING",
            "message":  "SIS Reg 4.09: SMSF trustees must consider and document each member's insurance needs as part of the fund's investment strategy. Failure to document this consideration may result in personal penalties ($19,800 per trustee). Ensure the investment strategy is reviewed and signed annually.",
        })

    # Work test compliance
    if work_test["warnings"]:
        flags.append({
            "code":     "IP-SUPER-WORKTST-001",
            "domain":   "ELIGIBILITY",
            "severity": "WARNING",
            "message":  f"SIS Reg 6.15 work test: {'; '.join(work_test['warnings'])}. IP cover should not be issued or retained without confirming gainful employment.",
        })

    # Inactivity opt-in notification
    flags.append({
        "code":     "IP-SUPER-PYS-001",
        "domain":   "MEMBER_COMMUNICATIONS",
        "severity": "INFO",
        "message":  "Protecting Your Super (2019): Trustees must notify members when IP cover is about to cease due to account inactivity (16 months). Notification must include instructions on how to lodge an opt-in election to retain cover. Check that communication templates and trigger logic are configured correctly.",
    })

    # Successor fund transfer — elections must transfer
    if inp["successor_fund_transfer"]:
        flags.append({
            "code":     "IP-SUPER-SFT-001",
            "domain":   "MEMBER_ELECTIONS",
            "severity": "WARNING",
            "message":  "Successor fund transfer occurred. SIS Act requires that any insurance opt-in elections (ss68AAA–68AAC) transfer with the member to the new fund. Obtain written confirmation from the successor trustee that equivalent rights have been preserved.",
        })

    # Cessation compliance
    for t in cessation.get("triggers", []):
        if t["fired"]:
            flags.append({
                "code":     f"IP-SUPER-CESS-{t['trigger']}",
                "domain":   "CESSATION",
                "severity": "WARNING",
                "message":  t["reason"],
            })

    # AML/CTF
    flags.append({
        "code":     "IP-SUPER-AML-001",
        "domain":   "AML_CFT",
        "severity": "INFO",
        "message":  "AUSTRAC AML/CTF requirements apply to super funds as reporting entities. Verify member identity (KYC/AML check) before issuing new IP cover and at claim time. AUSTRAC guidance for life insurers (transitional guidance to 31 Mar 2026) covers super fund IP activities.",
    })

    # SRS 251 reporting
    flags.append({
        "code":     "IP-SUPER-SRS251-001",
        "domain":   "REPORTING",
        "severity": "INFO",
        "message":  "APRA SRS 251: Trustees must report IP cover data including Insurance Cover Cost (annual premium per $1,000 cover), total sum insured, claim incidence, and waiting/benefit period breakdowns. Ensure the policy admin system captures these metrics by Insurance Table ID.",
    })

    return flags


# =========================================================================
# MEMBER ACTIONS
# =========================================================================

def _generate_member_actions(inp: dict, legal_status: str, work_test: dict,
                              portability: dict, cessation: dict) -> list[dict]:
    actions = []
    priority = 1

    if legal_status == "MUST_BE_SWITCHED_OFF":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "CRITICAL",
            "action": "PYS switch-off trigger has fired. Arrange replacement IP cover BEFORE the fund removes existing cover. Consider standalone IP outside super.",
            "rationale": "Insurance ceasing without replacement leaves the member without income protection.",
        })
        priority += 1

    if legal_status == "ALLOWED_BUT_OPT_IN_REQUIRED":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": "Lodge a written opt-in direction with the super fund trustee to retain IP cover (under-25 rule — SIS s68AAA(3)).",
            "rationale": "IP cover cannot be held by default for members under 25 on MySuper without an opt-in direction.",
        })
        priority += 1

    if not work_test["passes"] and inp["employment_status"] not in ("ON_CLAIM", "UNKNOWN"):
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": "Work test fails — IP cover inside super cannot be maintained. Transition to personal IP policy outside super before cover ceases.",
            "rationale": "SIS Reg 6.15 requires gainful employment for IP inside super. Outside-super IP has no work test requirement.",
        })
        priority += 1

    if portability.get("status") == "WITHIN_PORTABILITY_WINDOW":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": f"Port existing IP cover before the portability window expires ({portability['days_remaining_in_window']} days remaining). Contact the insurer/fund to elect continuation.",
            "rationale": "Failure to port within the window will lapse the policy — re-application requires fresh underwriting and may result in exclusions.",
        })
        priority += 1

    if portability.get("status") == "PORTABILITY_WINDOW_EXPIRED":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": "Portability window has expired. Member must apply for new IP cover (fresh underwriting). Compare inside-super group IP vs standalone policy outside super.",
            "rationale": "Existing cover cannot be ported — new application required.",
        })
        priority += 1

    if inp["successor_fund_transfer"] and not inp["equivalent_rights_confirmed"]:
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": "Obtain written confirmation from the successor fund trustee that insurance elections and equivalent cover rights have transferred.",
            "rationale": "Without confirmed equivalent rights, insurance continuity and prior elections cannot be relied upon.",
        })
        priority += 1

    if inp["need_own_occupation_def"] and legal_status == "ALLOWED_AND_ACTIVE":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "MEDIUM",
            "action": "Consider supplementing inside-super group IP with a standalone IP policy outside super that provides an own-occupation definition for the full benefit period.",
            "rationale": "Group IP inside super typically uses a stepped definition (own-occupation → any-occupation after 2 years). Own-occupation for the full term is more reliably obtained outside super.",
        })
        priority += 1

    if (inp["fund_type"] or "").lower() == "smsf":
        actions.append({
            "action_id": f"ACT-{priority:03d}", "priority": "HIGH",
            "action": "As an SMSF trustee, document the consideration of IP insurance in the fund's investment strategy (SIS Reg 4.09). Review and re-sign the investment strategy annually. Failure to document may result in ATO penalties.",
            "rationale": "SIS Reg 4.09 requires the investment strategy to address each member's insurance needs. Personal trustee penalties apply for non-compliance.",
        })
        priority += 1

    return actions


# =========================================================================
# RECOMMENDATION ENGINE
# =========================================================================

def _recommend(inp: dict, legal_status: str, work_test: dict,
               portability: dict, benefit_need: dict,
               tax_comparison: dict, placement: dict) -> dict:
    reasons = []
    risks   = []

    # Cannot proceed if mandatory data missing
    if legal_status == "NEEDS_MORE_INFO":
        return {
            "type":    "NEEDS_MORE_INFO",
            "summary": "Insufficient information — provide age, fund type and employment status to proceed.",
            "reasons": [], "risks": [],
        }

    # Work test fails and not on claim → must move outside
    if not work_test["passes"] and inp["employment_status"] not in ("UNKNOWN", "ON_CLAIM"):
        return {
            "type":    "MOVE_OUTSIDE_SUPER",
            "summary": "IP cover inside super cannot be maintained — work test fails. Transition to personal IP outside super.",
            "reasons": work_test["reasons"],
            "risks":   ["Cover inside super will cease — arrange replacement before cancellation to avoid a gap."],
        }

    # PYS forced switch-off
    if legal_status == "MUST_BE_SWITCHED_OFF":
        return {
            "type":    "SWITCH_OFF_AND_REPLACE",
            "summary": "PYS switch-off trigger has fired. Cover must cease — arrange replacement IP cover before switch-off takes effect.",
            "reasons": [f"PYS/PMIF legal status: {legal_status}"],
            "risks":   ["Gap in cover if replacement not arranged before switch-off date."],
        }

    # Opted out
    if legal_status == "OPTED_OUT":
        return {
            "type":    "RETAIN_OPTED_OUT_STATUS",
            "summary": "Member has opted out of insurance inside super. If income protection is needed, a standalone policy outside super should be considered.",
            "reasons": ["Member election to opt out is on file."],
            "risks":   ["Member has no IP cover — disability income risk is unmanaged."],
        }

    # Under-25 / opt-in required
    if legal_status == "ALLOWED_BUT_OPT_IN_REQUIRED":
        reasons.append("Member is under 25 and must actively elect to retain IP cover.")
        return {
            "type":    "OPT_IN_REQUIRED",
            "summary": "Member must lodge a written opt-in direction to obtain IP cover inside super (PYS under-25 rule).",
            "reasons": reasons,
            "risks":   ["Default IP cover is not available to members under 25 without an opt-in election."],
        }

    # Portability scenario
    if portability.get("applies"):
        reasons.append(f"Within portability window ({portability['days_remaining_in_window']} days remaining) — existing cover can be retained without re-underwriting.")
        return {
            "type":    "PORT_EXISTING_COVER",
            "summary": "Retain existing IP cover via portability — act within the window to avoid lapse and re-underwriting.",
            "reasons": reasons,
            "risks":   ["Cover will lapse if portability election is not made before the window expires."],
        }

    if portability.get("status") == "PORTABILITY_WINDOW_EXPIRED":
        reasons.append("Portability window has expired — fresh application required.")
        return {
            "type":    "PURCHASE_NEW_COVER",
            "summary": "Portability window has expired. New IP cover application (with fresh underwriting) is required.",
            "reasons": reasons,
            "risks":   ["Pre-existing conditions may lead to exclusions under new underwriting."],
        }

    # Existing cover — assess retain or supplement
    has_existing = inp["has_existing_cover"]
    is_proposing = inp["proposing_new_cover"]

    if has_existing and not is_proposing:
        shortfall = benefit_need.get("monthly_shortfall", 0) if isinstance(benefit_need, dict) else 0
        if shortfall > 0:
            reasons.append(f"Existing IP cover has a monthly shortfall of ${shortfall:,.0f} — supplementary cover should be considered.")
            rec_type = "SUPPLEMENT_EXISTING_COVER"
        else:
            reasons.append("Existing IP cover inside super appears to meet the replacement ratio requirement.")
            rec_type = "RETAIN_EXISTING_COVER"
        reasons += placement.get("reasoning", [])[:2]
        risks   += placement.get("risks", [])[:2]
        if tax_comparison.get("tax_favours_outside"):
            risks.append(tax_comparison.get("tax_summary", ""))
        return {"type": rec_type, "summary": reasons[0] if reasons else "Retain existing cover.", "reasons": reasons, "risks": risks}

    if not has_existing and is_proposing:
        reasons.append("No existing IP cover in super — new cover should be purchased subject to underwriting and SIS eligibility.")
        reasons += placement.get("reasoning", [])[:2]
        risks   += placement.get("risks", [])[:2]
        if tax_comparison.get("tax_favours_outside"):
            risks.append(f"Tax note: {tax_comparison.get('tax_summary', '')} — compare with outside-super IP before committing.")
        return {
            "type":    "PURCHASE_NEW_COVER",
            "summary": reasons[0],
            "reasons": reasons,
            "risks":   risks,
        }

    if has_existing and is_proposing:
        # Replace or supplement
        reasons.append("Reviewing replacement or supplementation of existing IP cover inside super.")
        reasons += placement.get("reasoning", [])[:2]
        risks   += placement.get("risks", [])[:2]
        return {
            "type":    "REVIEW_REPLACEMENT",
            "summary": "Existing and proposed cover both present — compare terms carefully before replacing.",
            "reasons": reasons,
            "risks":   risks,
        }

    return {
        "type":    "NEEDS_MORE_INFO",
        "summary": "Insufficient information to generate a recommendation — provide cover details.",
        "reasons": [], "risks": [],
    }


# =========================================================================
# TOOL CLASS
# =========================================================================

class IPInSuperTool(BaseTool):
    name        = "purchase_retain_ip_in_super"
    version     = ENGINE_VERSION
    description = (
        "Evaluates whether Income Protection (IP / salary continuance) insurance inside "
        "superannuation is legally permissible and strategically appropriate for a member. "
        "Applies SIS Act work test (Reg 6.15), Protecting Your Super / Putting Members' "
        "Interests First switch-off triggers (inactivity, low balance, under-25), SPS 250 "
        "trustee obligations, portability window assessment, cessation triggers (age 65, "
        "not employed), and inside-vs-outside-super tax comparison (IP premiums non-deductible "
        "inside super; benefits always assessable income at marginal rate). Covers purchase "
        "(new group IP cover) and retain (existing cover, portability, elections) scenarios. "
        "Returns legal status, placement recommendation, compliance flags (SPS 250, Reg 4.09, "
        "AML/CTF, SRS 251), retirement drag, and required member actions."
    )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "evaluationDate": {"type": "string", "format": "date-time", "description": "ISO 8601 evaluation date. Defaults to now."},
                "member": {
                    "type": "object",
                    "description": "Member demographic and employment data.",
                    "properties": {
                        "age":                  {"type": "integer"},
                        "dateOfBirth":          {"type": "string", "format": "date"},
                        "employmentStatus":     {"type": "string", "enum": ["EMPLOYED_FULL_TIME", "EMPLOYED_PART_TIME", "SELF_EMPLOYED", "UNEMPLOYED", "ON_CLAIM", "UNKNOWN"]},
                        "weeklyHoursWorked":    {"type": "number",  "description": "Average weekly hours worked — needed for part-time work test (SIS Reg 6.15, ≥20 hrs)."},
                        "annualGrossIncome":    {"type": "number",  "description": "Annual gross income AUD."},
                        "marginalTaxRate":      {"type": "number",  "description": "Marginal income tax rate (e.g. 0.37 for 37%)."},
                        "occupation":           {"type": "string"},
                        "occupationClass":      {"type": "string",  "enum": ["CLASS_1_WHITE_COLLAR", "CLASS_2_LIGHT_BLUE", "CLASS_3_BLUE_COLLAR", "CLASS_4_HAZARDOUS", "UNKNOWN"]},
                        "isSmoker":             {"type": "boolean"},
                        "employmentCeasedDate": {"type": "string",  "format": "date", "description": "Date member left employment — triggers portability window."},
                        "hasDependants":        {"type": "boolean"},
                        "cashflowPressure":     {"type": "boolean"},
                        "wantsInsideSuper":     {"type": "boolean"},
                        "wantsAffordability":   {"type": "boolean"},
                    },
                },
                "fund": {
                    "type": "object",
                    "description": "Super fund characteristics.",
                    "properties": {
                        "fundType":                     {"type": "string",  "enum": ["mysuper", "choice", "smsf", "defined_benefit"], "description": "Super fund type."},
                        "fundMemberCount":              {"type": "integer", "description": "Number of members (for small fund carve-out check)."},
                        "isDefinedBenefitFund":         {"type": "boolean"},
                        "isADFOrCommonwealthFund":      {"type": "boolean"},
                        "accountBalance":               {"type": "number",  "description": "Member's super account balance AUD."},
                        "lastAmountReceivedDate":       {"type": "string",  "format": "date", "description": "Date of last contribution or rollover."},
                        "receivedAmountInLast16Months": {"type": "boolean", "description": "Set if lastAmountReceivedDate unavailable."},
                        "hadBalanceGe6000OnOrAfter2019_11_01": {"type": "boolean"},
                        "successorFundTransferOccurred": {"type": "boolean"},
                        "trusteeAllowsOptInOnline":     {"type": "boolean"},
                    },
                },
                "existingCover": {
                    "type": "object",
                    "description": "Details of existing IP cover inside the super fund.",
                    "properties": {
                        "hasExistingIPCover":        {"type": "boolean"},
                        "insurerName":               {"type": "string"},
                        "coverCommencedDate":        {"type": "string",  "format": "date"},
                        "monthlyBenefit":            {"type": "number",  "description": "AUD monthly benefit."},
                        "waitingPeriodDays":         {"type": "integer", "enum": [30, 60, 90]},
                        "benefitPeriodMonths":       {"type": "integer", "description": "0 = to age 65."},
                        "annualPremium":             {"type": "number"},
                        "occupationDefinition":      {"type": "string",  "enum": ["OWN_OCCUPATION", "ANY_OCCUPATION", "ACTIVITIES_OF_DAILY_LIVING", "UNKNOWN"]},
                        "stepDownApplies":           {"type": "boolean"},
                        "hasIndexation":             {"type": "boolean"},
                        "portabilityClauseAvailable":{"type": "boolean"},
                        "portabilityWindowDays":     {"type": "integer", "description": "Days after leaving employment cover can be ported. Default 30."},
                        "hasLoadings":               {"type": "boolean"},
                        "hasExclusions":             {"type": "boolean"},
                        "exclusionDetails":          {"type": "string"},
                        "hasGrandfatheredTerms":     {"type": "boolean"},
                    },
                },
                "newCoverProposal": {
                    "type": "object",
                    "description": "Proposed new IP cover (if purchasing).",
                    "properties": {
                        "monthlyBenefit":        {"type": "number"},
                        "waitingPeriodDays":     {"type": "integer", "enum": [30, 60, 90]},
                        "benefitPeriodMonths":   {"type": "integer"},
                        "annualPremium":         {"type": "number"},
                        "occupationDefinition":  {"type": "string"},
                        "replacementRatio":      {"type": "number", "description": "Fraction of gross income replaced (e.g. 0.75)."},
                    },
                },
                "elections": {
                    "type": "object",
                    "description": "Member opt-in / opt-out elections.",
                    "properties": {
                        "optedInToRetainInsurance":              {"type": "boolean"},
                        "optInElectionDate":                     {"type": "string", "format": "date"},
                        "optedOutOfInsurance":                   {"type": "boolean"},
                        "optOutDate":                            {"type": "string", "format": "date"},
                        "priorElectionCarriedViaSuccessorTransfer": {"type": "boolean"},
                        "equivalentRightsConfirmed":             {"type": "boolean"},
                    },
                },
                "employerException": {
                    "type": "object",
                    "properties": {
                        "employerHasNotifiedTrusteeInWriting":    {"type": "boolean"},
                        "employerContributionsExceedSGByInsuranceFee": {"type": "boolean"},
                        "dangerousOccupationElectionInForce":    {"type": "boolean"},
                    },
                },
                "claimContext": {
                    "type": "object",
                    "description": "Only populate if a claim is currently in progress.",
                    "properties": {
                        "claimInProgress":           {"type": "boolean"},
                        "disabilityOnsetDate":       {"type": "string", "format": "date"},
                        "medicalEvidenceProvided":   {"type": "boolean"},
                        "incomeEvidenceProvided":    {"type": "boolean"},
                        "employerStatementProvided": {"type": "boolean"},
                    },
                },
                "adviceContext": {
                    "type": "object",
                    "properties": {
                        "yearsToRetirement":                     {"type": "number"},
                        "assumedGrowthRate":                     {"type": "number", "description": "e.g. 0.07 for 7% pa."},
                        "monthlyExpenses":                       {"type": "number"},
                        "concessionalContributionsAlreadyHigh":  {"type": "boolean"},
                        "contributionCapPressure":               {"type": "boolean"},
                        "needForOwnOccupationDefinition":        {"type": "boolean"},
                        "needForPolicyFlexibility":              {"type": "boolean"},
                        "retirementPriorityHigh":                {"type": "boolean"},
                        "superBalanceAdequacy":                  {"type": "string", "enum": ["low", "adequate", "high"]},
                    },
                },
            },
        }

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(input_data, dict):
            raise ToolValidationError("Input must be a JSON object.")

        # 1. Normalise
        inp = _normalize(input_data)

        # 2. Validate
        validation = _validate(input_data, inp)
        missing_questions = validation.get("missingInfoQuestions", [])
        blocking = [q for q in missing_questions if q.get("blocking")]

        # 3. Work test
        work_test = _eval_work_test(inp)

        # 4. Legal status (PYS triggers, exceptions, elections)
        legal = _resolve_legal_status(inp, validation, work_test)

        # 5. Portability
        portability = _eval_portability(inp)

        # 6. Cessation triggers
        cessation = _eval_cessation_triggers(inp, work_test)

        # 7. Tax comparison
        tax_comparison = _calc_tax_comparison(inp)

        # 8. Retirement drag
        retirement_drag = _calc_retirement_drag(inp)

        # 9. Benefit need
        benefit_need = _calc_benefit_need(inp)

        # 10. Claim context (if applicable)
        claim_context = _eval_claim(inp)

        # 11. Placement
        placement_scores = _calc_placement_scores(inp)
        placement = _eval_placement(inp, legal["status"], placement_scores)

        # 12. Compliance flags
        compliance_flags = _build_compliance_flags(inp, work_test, cessation)

        # 13. Member actions
        member_actions = _generate_member_actions(inp, legal["status"], work_test, portability, cessation)

        # 14. Recommendation
        recommendation = _recommend(inp, legal["status"], work_test, portability,
                                    benefit_need, tax_comparison, placement)

        # 15. Advice mode
        advice_mode = "NEEDS_MORE_INFO" if blocking else (
            "PERSONAL_ADVICE_READY"
            if any([inp["annual_gross_income"], inp["marginal_tax_rate"], inp["years_to_retirement"]])
            else "GENERAL_GUIDANCE"
        )

        return {
            "recommendation":           recommendation,
            "legal_status":             legal["status"],
            "legal_permissibility":     legal["permissibility"],
            "legal_reasons":            legal["reasons"],
            "switch_off_evaluations":   legal["switch_off_evaluations"],
            "exceptions_applied":       legal["exceptions_applied"],
            "work_test":                work_test,
            "portability":              portability,
            "cessation":                cessation,
            "benefit_need":             benefit_need,
            "tax_comparison":           tax_comparison,
            "retirement_drag":          retirement_drag,
            "placement_assessment":     placement,
            "placement_scores":         placement_scores,
            "claim_context":            claim_context,
            "compliance_flags":         compliance_flags,
            "member_actions":           member_actions,
            "advice_mode":              advice_mode,
            "validation":               validation,
            "missing_info_questions":   missing_questions,
            "engine_version":           ENGINE_VERSION,
            "evaluated_at":             inp["evaluation_date"].isoformat(),
        }
