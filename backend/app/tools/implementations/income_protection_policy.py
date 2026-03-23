"""
income_protection_policy.py — Purchase/Retain Income Protection Policy tool.

Implements the regulatory rules and product mechanics for income protection /
disability income insurance as documented in the deep research report:
  - Waiting periods, benefit periods, benefit levels, offsets
  - Indexation (RPI/CPI, caps)
  - Premium grace / lapse / waiver mechanics
  - Occupation definition step-down (own → any after 24 months)
  - Sustainability: replacement ratio caps, benefit period segmentation
  - Compliance flags: Australian DDO/Consumer Duty, ASIC IDII guidelines
  - Missing-info questions (blocking vs optional)

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

# Replacement ratio cap — APRA/ASIC IDII sustainability measure
MAX_REPLACEMENT_RATIO = 0.70  # 70% of pre-disability income

# Benefit period options (months; 0 = to-age-65 sentinel)
BENEFIT_PERIOD_OPTIONS = [12, 24, 60, 0]  # 0 = to age 65

# Waiting period options (weeks)
WAITING_PERIOD_OPTIONS_WEEKS = [2, 4, 8, 13, 26, 52]

# Grace period before lapse (days) — per UK/AU market norms (L&G, Aviva)
PREMIUM_GRACE_PERIOD_DAYS = 60

# Occupation definition step-down threshold (months on claim)
OWN_OCC_STEP_DOWN_MONTHS = 24

# Standard indexation cap on benefit increase (per annum, fraction)
INDEXATION_CAP = 0.05  # 5% pa

# Indexation premium multiplier — L&G uses RPI × 1.5, capped
INDEXATION_PREMIUM_MULTIPLIER = 1.5

# Affordability thresholds (premium as fraction of gross income)
AFFORDABILITY_BANDS = {
    "COMFORTABLE": 0.03,   # ≤ 3% of gross income
    "MANAGEABLE":  0.05,   # ≤ 5%
    "STRETCHED":   0.08,   # ≤ 8%
}

# Occupation risk class → underwriting risk level
OCCUPATION_RISK_MAP = {
    "CLASS_1_WHITE_COLLAR":    "LOW",
    "CLASS_2_LIGHT_BLUE":      "MEDIUM",
    "CLASS_3_BLUE_COLLAR":     "HIGH",
    "CLASS_4_HAZARDOUS":       "CRITICAL",
    "UNKNOWN":                 "MEDIUM",
}

# Waiting period → incidence adjustment factor (empirical evidence: longer EP → lower incidence)
# Source: US group LTD study 2015-2022
WAITING_PERIOD_INCIDENCE_FACTOR = {
    2:   1.25,   # 2-week EP — highest incidence
    4:   1.10,
    8:   1.00,   # baseline
    13:  0.88,
    26:  0.72,
    52:  0.55,
}

# Offset types
OFFSETS_THAT_REDUCE_BENEFIT = [
    "WORKERS_COMPENSATION", "EMPLOYER_SICK_PAY", "CENTRELINK",
    "OTHER_INCOME_PROTECTION", "SUPERANNUATION_IP",
]

# Shortfall severity buckets
SHORTFALL_THRESHOLDS = {
    "NONE":         0,
    "MINOR":        10_000,
    "MODERATE":     30_000,
    "SIGNIFICANT":  60_000,
}

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


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _classify_shortfall(net: float) -> str:
    if net <= SHORTFALL_THRESHOLDS["NONE"]:
        return "NONE"
    if net <= SHORTFALL_THRESHOLDS["MINOR"]:
        return "MINOR"
    if net <= SHORTFALL_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    if net <= SHORTFALL_THRESHOLDS["SIGNIFICANT"]:
        return "SIGNIFICANT"
    return "CRITICAL"


def _classify_affordability(annual_premium: float | None, gross_income: float | None) -> str:
    if annual_premium is None or gross_income is None or gross_income <= 0:
        return "UNKNOWN"
    ratio = annual_premium / gross_income
    if ratio <= AFFORDABILITY_BANDS["COMFORTABLE"]:
        return "COMFORTABLE"
    if ratio <= AFFORDABILITY_BANDS["MANAGEABLE"]:
        return "MANAGEABLE"
    if ratio <= AFFORDABILITY_BANDS["STRETCHED"]:
        return "STRETCHED"
    return "UNAFFORDABLE"


# =========================================================================
# NORMALIZE
# =========================================================================

def _normalize(raw: dict) -> dict:
    eval_date = _safe_parse_date(raw.get("evaluationDate")) or datetime.now(timezone.utc)

    c  = raw.get("client") or {}
    ep = raw.get("existingPolicy") or {}
    np_ = raw.get("proposedPolicy") or {}
    h  = raw.get("health") or {}
    g  = raw.get("goals") or {}
    fp = raw.get("financialPosition") or {}

    dob = _safe_parse_date(c.get("dateOfBirth"))
    age = c.get("age")
    if age is None and dob:
        age = _compute_age(dob, eval_date)

    return {
        "evaluation_date": eval_date,

        # --- Client ---
        "age":                    age,
        "date_of_birth":          dob,
        "occupation_class":       c.get("occupationClass", "UNKNOWN"),
        "occupation_description": c.get("occupation"),
        "employment_type":        c.get("employmentType", "UNKNOWN"),
        "annual_gross_income":    c.get("annualGrossIncome"),
        "annual_net_income":      c.get("annualNetIncome"),
        "is_smoker":              c.get("isSmoker", False),
        "residency":              c.get("residency", "AUSTRALIA"),

        # --- Existing policy ---
        "has_existing_policy":         ep.get("hasExistingPolicy", False),
        "existing_insurer":            ep.get("insurerName"),
        "existing_waiting_weeks":      ep.get("waitingPeriodWeeks"),
        "existing_benefit_period_months": ep.get("benefitPeriodMonths"),
        "existing_monthly_benefit":    ep.get("monthlyBenefit"),
        "existing_annual_premium":     ep.get("annualPremium"),
        "existing_occupation_def":     ep.get("occupationDefinition", "UNKNOWN"),
        "existing_step_down_applies":  ep.get("stepDownApplies", False),
        "existing_has_indexation":     ep.get("hasIndexation", False),
        "existing_indexation_type":    ep.get("indexationType"),
        "existing_has_waiver":         ep.get("hasPremiumWaiver", False),
        "existing_has_partial_cover":  ep.get("hasPartialDisabilityCover", False),
        "existing_has_rehab_benefit":  ep.get("hasRehabBenefit", False),
        "existing_super_contributions_benefit": ep.get("hasSuperContributionsBenefit", False),
        "existing_offsets":            ep.get("offsets", []),
        "existing_has_loadings":       ep.get("hasLoadings", False),
        "existing_loading_details":    ep.get("loadingDetails"),
        "existing_has_exclusions":     ep.get("hasExclusions", False),
        "existing_exclusion_details":  ep.get("exclusionDetails"),
        "existing_commencement_date":  _safe_parse_date(ep.get("commencementDate")),

        # --- Proposed policy ---
        "proposed_insurer":            np_.get("insurerName"),
        "proposed_waiting_weeks":      np_.get("waitingPeriodWeeks"),
        "proposed_benefit_period_months": np_.get("benefitPeriodMonths"),
        "proposed_monthly_benefit":    np_.get("monthlyBenefit"),
        "proposed_annual_premium":     np_.get("annualPremium"),
        "proposed_occupation_def":     np_.get("occupationDefinition", "UNKNOWN"),
        "proposed_has_indexation":     np_.get("hasIndexation", False),
        "proposed_indexation_type":    np_.get("indexationType"),
        "proposed_has_waiver":         np_.get("hasPremiumWaiver", False),
        "proposed_has_partial_cover":  np_.get("hasPartialDisabilityCover", False),
        "proposed_has_rehab_benefit":  np_.get("hasRehabBenefit", False),
        "proposed_super_contributions_benefit": np_.get("hasSuperContributionsBenefit", False),
        "proposed_offsets":            np_.get("offsets", []),
        "proposed_expected_loadings":  np_.get("expectedLoadings"),
        "proposed_expected_exclusions": np_.get("expectedExclusions"),

        # --- Health ---
        "medical_conditions":          h.get("existingMedicalConditions", []),
        "medications":                 h.get("currentMedications", []),
        "pending_investigations":      h.get("pendingInvestigations", False),
        "family_history":              h.get("familyHistoryConditions", []),
        "hazardous_activities":        h.get("hazardousActivities", []),

        # --- Goals ---
        "wants_replacement":           g.get("wantsReplacement"),
        "wants_retention":             g.get("wantsRetention"),
        "affordability_concern":       g.get("affordabilityIsConcern", False),
        "wants_own_occupation_def":    g.get("wantsOwnOccupationDefinition", False),
        "wants_long_benefit_period":   g.get("wantsLongBenefitPeriod", False),
        "wants_indexation":            g.get("wantsIndexation", False),
        "prioritises_premium_waiver":  g.get("prioritisesPremiumWaiver", False),
        "wants_super_contributions":   g.get("wantsSuperContributionsBenefit", False),
        "employer_sick_pay_weeks":     g.get("employerSickPayWeeks", 0),

        # --- Financial position ---
        "liquid_assets":               fp.get("liquidAssets"),
        "mortgage_balance":            fp.get("mortgageBalance"),
        "monthly_expenses":            fp.get("monthlyExpenses"),
    }


# =========================================================================
# VALIDATION
# =========================================================================

def _validate(raw: dict, inp: dict) -> dict:
    errors   = []
    warnings = []
    questions = []

    c = raw.get("client") or {}

    if inp["age"] is None:
        errors.append({"field": "client.age", "message": "Client age or date of birth is required.", "category": "CLIENT_PROFILE"})
        questions.append({"id": "IPQ-001", "question": "What is the client's current age?", "category": "CLIENT_PROFILE", "blocking": True})

    if inp["annual_gross_income"] is None:
        errors.append({"field": "client.annualGrossIncome", "message": "Annual gross income required to calculate replacement ratio and affordability.", "category": "CLIENT_PROFILE"})
        questions.append({"id": "IPQ-002", "question": "What is the client's annual gross income before tax?", "category": "CLIENT_PROFILE", "blocking": True})

    if inp["occupation_class"] == "UNKNOWN" and not inp["occupation_description"]:
        warnings.append({"field": "client.occupationClass", "message": "Occupation class not provided — underwriting risk defaults to MEDIUM."})
        questions.append({"id": "IPQ-003", "question": "What is the client's occupation class (white collar, light blue collar, blue collar, hazardous)?", "category": "CLIENT_PROFILE", "blocking": False})

    ep = raw.get("existingPolicy") or {}
    if ep.get("hasExistingPolicy"):
        if ep.get("monthlyBenefit") is None:
            warnings.append({"field": "existingPolicy.monthlyBenefit", "message": "Existing monthly benefit not provided — policy comparison will be incomplete."})
            questions.append({"id": "IPQ-004", "question": "What is the existing policy's monthly benefit amount?", "category": "EXISTING_POLICY", "blocking": False})
        if ep.get("waitingPeriodWeeks") is None:
            warnings.append({"field": "existingPolicy.waitingPeriodWeeks", "message": "Existing waiting period not provided — comparison will be incomplete."})
            questions.append({"id": "IPQ-005", "question": "What is the waiting/deferred period of the existing policy (in weeks)?", "category": "EXISTING_POLICY", "blocking": False})

    if not ep.get("hasExistingPolicy") and not raw.get("proposedPolicy"):
        questions.append({"id": "IPQ-006", "question": "Is the client applying for a new income protection policy, or reviewing an existing one?", "category": "INTENT", "blocking": True})

    if not raw.get("health"):
        warnings.append({"field": "health", "message": "No health information provided — underwriting risk assessment will be incomplete."})
        questions.append({"id": "IPQ-007", "question": "Please provide health information: pre-existing conditions, medications, pending investigations, and hazardous activities.", "category": "HEALTH", "blocking": False})

    if inp["monthly_expenses"] is None:
        questions.append({"id": "IPQ-008", "question": "What are the client's current monthly living expenses? (Used for income replacement gap analysis.)", "category": "FINANCIAL", "blocking": False})

    is_valid = len(errors) == 0
    return {"isValid": is_valid, "errors": errors, "warnings": warnings, "missingInfoQuestions": questions}


# =========================================================================
# BENEFIT NEED ANALYSIS
# =========================================================================

def _calc_benefit_need(inp: dict) -> dict:
    """
    Calculate the income replacement need.
    Caps benefit at MAX_REPLACEMENT_RATIO (70%) per APRA IDII sustainability measures.
    """
    assumptions = []
    gross = inp["annual_gross_income"] or 0
    net   = inp["annual_net_income"] or (gross * 0.68)  # rough net estimate
    if inp["annual_net_income"] is None:
        assumptions.append("Net income not provided — estimated at 68% of gross as a proxy.")

    monthly_net = net / 12

    # Maximum monthly benefit (70% of gross / 12)
    max_monthly = gross * MAX_REPLACEMENT_RATIO / 12

    # Target replacement: pre-disability monthly net income
    target_monthly = min(monthly_net, max_monthly)

    # Monthly expenses offset
    monthly_expenses = inp["monthly_expenses"]
    if monthly_expenses:
        # Actual need capped to expenses if lower than 70% target
        recommended_monthly = min(target_monthly, monthly_expenses * 1.10)
        assumptions.append("Monthly benefit capped to 110% of stated monthly expenses.")
    else:
        recommended_monthly = target_monthly

    # Existing IP cover held (reduces need)
    existing_monthly = inp["existing_monthly_benefit"] or 0

    # Offset income sources that reduce benefit payable
    # (e.g. employer sick pay during waiting period, other IP covers)
    offset_sources = inp["existing_offsets"]
    offset_note = ""
    if offset_sources:
        offset_note = f"Offsets apply: {', '.join(offset_sources)}. Benefit will be reduced at claim time."
        assumptions.append(offset_note)

    gap_monthly    = max(0.0, recommended_monthly - existing_monthly)
    shortfall_ann  = gap_monthly * 12
    shortfall_level = _classify_shortfall(shortfall_ann)

    return {
        "gross_annual_income":         gross,
        "net_monthly_income_estimate": round(monthly_net, 2),
        "max_monthly_benefit_allowed": round(max_monthly, 2),
        "recommended_monthly_benefit": round(recommended_monthly, 2),
        "existing_monthly_benefit":    round(existing_monthly, 2),
        "monthly_gap":                 round(gap_monthly, 2),
        "annual_gap":                  round(shortfall_ann, 2),
        "shortfall_level":             shortfall_level,
        "replacement_ratio_cap":       f"{int(MAX_REPLACEMENT_RATIO * 100)}% (APRA IDII sustainability measure)",
        "offset_sources":              offset_sources,
        "assumptions":                 assumptions,
    }


# =========================================================================
# WAITING PERIOD ANALYSIS
# =========================================================================

def _assess_waiting_period(inp: dict) -> dict:
    """
    Recommend waiting period aligned to employer sick pay.
    Longer waiting period → lower incidence risk (actuarial evidence).
    """
    employer_sick_pay_weeks = inp["employer_sick_pay_weeks"] or 0
    affordability_concern   = inp["affordability_concern"]

    # Align waiting period with employer sick pay to avoid redundant cover
    if employer_sick_pay_weeks >= 26:
        recommended_weeks = 26
        rationale = "Employer sick pay of 26+ weeks — recommended waiting period aligned to 26 weeks to avoid unnecessary duplication."
    elif employer_sick_pay_weeks >= 13:
        recommended_weeks = 13
        rationale = "Employer sick pay of 13+ weeks — recommended waiting period of 13 weeks."
    elif employer_sick_pay_weeks >= 8:
        recommended_weeks = 8
        rationale = "Employer sick pay of 8+ weeks — recommended waiting period of 8 weeks."
    elif employer_sick_pay_weeks >= 4:
        recommended_weeks = 4
        rationale = "Employer sick pay of 4+ weeks — recommended waiting period of 4 weeks."
    else:
        # No/minimal sick pay — shorter waiting period for protection
        recommended_weeks = 4
        rationale = "Minimal employer sick pay — recommended 4-week waiting period for early coverage."

    if affordability_concern:
        # Suggest longer waiting period to reduce premium
        if recommended_weeks < 13:
            recommended_weeks = 13
            rationale += " Waiting period extended to 13 weeks to reduce premium cost given affordability concern."

    # Incidence factor relative to 8-week baseline
    incidence_factor = WAITING_PERIOD_INCIDENCE_FACTOR.get(recommended_weeks, 1.0)

    existing_weeks = inp["existing_waiting_weeks"]
    comparison = None
    if existing_weeks is not None:
        if existing_weeks > recommended_weeks:
            comparison = "EXISTING_LONGER_THAN_RECOMMENDED"
        elif existing_weeks < recommended_weeks:
            comparison = "EXISTING_SHORTER_THAN_RECOMMENDED"
        else:
            comparison = "ALIGNED"

    return {
        "recommended_waiting_period_weeks": recommended_weeks,
        "existing_waiting_period_weeks":    existing_weeks,
        "comparison":                       comparison,
        "rationale":                        rationale,
        "employer_sick_pay_weeks":          employer_sick_pay_weeks,
        "incidence_risk_factor":            incidence_factor,
        "incidence_note":                   "Longer waiting period is associated with lower incidence (US group LTD study 2015-2022).",
    }


# =========================================================================
# BENEFIT PERIOD ANALYSIS
# =========================================================================

def _assess_benefit_period(inp: dict) -> dict:
    """
    Assess benefit period suitability.
    Two-year break point: own occupation may step down to any occupation after 24 months
    on some products (TAL Enhance/Focus pattern; L&G limited benefit period options).
    """
    age = inp["age"] or 40
    years_to_65 = max(0, 65 - age)
    wants_long  = inp["wants_long_benefit_period"]

    if years_to_65 >= 20 and wants_long:
        recommended_months = 0   # to age 65
        recommended_label  = "To age 65"
        rationale = "Client is more than 20 years from age 65 and wants long-term cover — to-age-65 benefit period recommended."
    elif years_to_65 >= 10:
        recommended_months = 60  # 5 years
        recommended_label  = "5 years"
        rationale = "5-year benefit period balances long-term protection with premium affordability."
    elif years_to_65 >= 5:
        recommended_months = 24
        recommended_label  = "2 years"
        rationale = "2-year benefit period given proximity to retirement (less than 10 years to age 65)."
    else:
        recommended_months = 12
        recommended_label  = "1 year"
        rationale = "Short benefit period appropriate given client is within 5 years of age 65."

    # Affordability concern: suggest shorter period to reduce premium
    if inp["affordability_concern"] and recommended_months == 0:
        recommended_months = 60
        recommended_label  = "5 years"
        rationale += " Limited to 5-year period due to affordability concern."

    # Step-down risk assessment
    existing_def = inp["existing_occupation_def"]
    proposed_def = inp["proposed_occupation_def"]
    active_def   = proposed_def if inp.get("proposed_insurer") else existing_def

    step_down_risk = "LOW"
    step_down_notes = []
    if inp["existing_step_down_applies"]:
        step_down_risk = "HIGH"
        step_down_notes.append(f"Existing policy has a step-down from own occupation to any occupation definition after {OWN_OCC_STEP_DOWN_MONTHS} months on claim. Client must understand that the definition becomes harder to satisfy after 2 years.")
    if active_def in ("ANY_OCCUPATION", "ACTIVITIES_OF_DAILY_LIVING"):
        step_down_risk = "MEDIUM" if step_down_risk == "LOW" else step_down_risk
        step_down_notes.append("Current occupation definition ('any occupation' or ADL) is less favourable than 'own occupation' — client may face higher bar to qualify for ongoing benefit.")

    existing_bp = inp["existing_benefit_period_months"]
    proposed_bp = inp["proposed_benefit_period_months"]

    return {
        "recommended_benefit_period_months": recommended_months,
        "recommended_benefit_period_label":  recommended_label,
        "existing_benefit_period_months":    existing_bp,
        "proposed_benefit_period_months":    proposed_bp,
        "years_to_age_65":                   years_to_65,
        "rationale":                         rationale,
        "occupation_definition_active":      active_def,
        "step_down_risk":                    step_down_risk,
        "step_down_notes":                   step_down_notes,
    }


# =========================================================================
# INDEXATION ANALYSIS
# =========================================================================

def _assess_indexation(inp: dict) -> dict:
    """
    Assess indexation suitability.
    Benefit must keep pace with inflation to maintain real income replacement.
    ASIC has flagged indexation calculation errors as a recurring industry issue.
    """
    wants_indexation = inp["wants_indexation"]
    has_existing_idx = inp["existing_has_indexation"]
    has_proposed_idx = inp["proposed_has_indexation"]
    existing_type    = inp["existing_indexation_type"] or "NONE"
    proposed_type    = inp["proposed_indexation_type"] or "NONE"

    # Determine active indexation type
    active_type = proposed_type if inp.get("proposed_insurer") else existing_type

    recommendations = []
    flags = []

    if not wants_indexation and not has_existing_idx:
        recommendations.append("No indexation selected. Consider adding CPI/RPI indexation to maintain the real value of the benefit over a long claim — benefits without indexation erode in value over time.")

    if active_type in ("CPI", "RPI"):
        recommendations.append(f"Indexation type '{active_type}' is appropriate. Benefit will increase annually by CPI/RPI subject to the {int(INDEXATION_CAP * 100)}% pa cap.")
        # Corresponding premium increase note
        recommendations.append(f"Premium will increase by approximately {active_type} × {INDEXATION_PREMIUM_MULTIPLIER} (capped) — ensure the client understands future premium increases.")

    if active_type == "FIXED":
        recommendations.append("Fixed indexation provides certainty but may underperform in high-inflation environments. CPI-linked indexation is generally preferred for long benefit periods.")

    # ASIC compliance flag
    flags.append({
        "code": "IP-COMP-IDX-001",
        "severity": "INFO",
        "message": "Indexation calculations must be audited for accuracy. ASIC has identified benefit payment/indexation errors as a recurring issue in IDII claims handling (ASIC IDII claims review, 2021).",
    })

    return {
        "existing_has_indexation":   has_existing_idx,
        "existing_indexation_type":  existing_type,
        "proposed_has_indexation":   has_proposed_idx,
        "proposed_indexation_type":  proposed_type,
        "active_indexation_type":    active_type,
        "indexation_cap_pa":         INDEXATION_CAP,
        "premium_multiplier":        INDEXATION_PREMIUM_MULTIPLIER,
        "recommendations":           recommendations,
        "compliance_flags":          flags,
    }


# =========================================================================
# PREMIUM & AFFORDABILITY
# =========================================================================

def _assess_affordability(inp: dict) -> dict:
    """
    Affordability assessment.
    Includes grace period rules and waiver-of-premium logic.
    """
    gross_income     = inp["annual_gross_income"]
    existing_premium = inp["existing_annual_premium"]
    proposed_premium = inp["proposed_annual_premium"]

    active_premium = proposed_premium if proposed_premium is not None else existing_premium

    affordability = _classify_affordability(active_premium, gross_income)

    notes = []
    if affordability == "UNAFFORDABLE":
        notes.append("Premium exceeds 8% of gross income — consider increasing the waiting period, reducing the benefit amount, or limiting the benefit period to reduce cost.")
    elif affordability == "STRETCHED":
        notes.append("Premium is at the upper end of affordability (5–8% of gross income). Monitor premium sustainability especially if reviewable premiums apply.")

    # Grace period / lapse logic (per L&G / Aviva policy evidence)
    grace_notes = [
        f"Standard premium grace period is {PREMIUM_GRACE_PERIOD_DAYS} days. If premium remains unpaid after {PREMIUM_GRACE_PERIOD_DAYS} days the policy lapses — no claim will be payable.",
        "Premiums are waived while benefit is being paid (premium waiver on claim) — policy does not lapse during an active disability claim.",
        "Premiums resume once the claim ends and the client returns to work (or the benefit period expires).",
    ]

    # Stepped vs reviewable premium risk
    premium_structure_note = (
        "Reviewable premiums may increase significantly at each review date — "
        "the insurer can change the premium without a fixed cap. "
        "Guaranteed/stepped premiums provide certainty but start higher. "
        "Ensure the client understands the reviewable premium risk, particularly in the context of UK Consumer Duty / Australian DDO fair value obligations."
    )

    return {
        "active_annual_premium":   active_premium,
        "gross_annual_income":     gross_income,
        "affordability_band":      affordability,
        "affordability_notes":     notes,
        "grace_period_days":       PREMIUM_GRACE_PERIOD_DAYS,
        "grace_period_lapse_note": grace_notes,
        "premium_structure_note":  premium_structure_note,
    }


# =========================================================================
# UNDERWRITING RISK
# =========================================================================

def _assess_underwriting_risk(inp: dict) -> dict:
    """
    Assess underwriting risk.
    Informs whether replacement/new application will face loadings or exclusions.
    """
    occ_risk = OCCUPATION_RISK_MAP.get(inp["occupation_class"], "MEDIUM")
    risk_factors = []
    risk_flags   = []

    if inp["is_smoker"]:
        risk_factors.append("SMOKER")

    for cond in inp["medical_conditions"]:
        risk_factors.append(f"CONDITION: {cond}")

    if inp["pending_investigations"]:
        risk_factors.append("PENDING_MEDICAL_INVESTIGATION")
        risk_flags.append({
            "code": "IP-UW-001",
            "severity": "WARNING",
            "message": "Pending medical investigation — insurers will typically defer cover or apply exclusions until investigation is resolved. Do not replace existing cover while investigation is outstanding.",
        })

    if inp["hazardous_activities"]:
        risk_factors.append(f"HAZARDOUS_ACTIVITIES: {', '.join(inp['hazardous_activities'])}")

    # Non-disclosure risk: replacing carries duty-of-disclosure obligations
    if inp["has_existing_policy"]:
        risk_flags.append({
            "code": "IP-UW-002",
            "severity": "WARNING",
            "message": "Replacing an existing IP policy triggers a fresh duty of disclosure (Insurance Contracts Act). Any non-disclosure may void the new policy — ensure a full medical and financial disclosure is completed before cancelling the existing policy.",
        })

    if inp["existing_has_loadings"]:
        risk_flags.append({
            "code": "IP-UW-003",
            "severity": "INFO",
            "message": f"Existing policy has loadings ({inp['existing_loading_details']}). New underwriting may maintain, increase, or remove these — obtain terms from the new insurer before recommending replacement.",
        })

    if inp["existing_has_exclusions"]:
        risk_flags.append({
            "code": "IP-UW-004",
            "severity": "INFO",
            "message": f"Existing policy has exclusions ({inp['existing_exclusion_details']}). New policy may apply the same or additional exclusions.",
        })

    risk_level_map = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}
    base_level = risk_level_map.get(occ_risk, 2)
    adjusted_level = base_level + len([f for f in risk_factors if "CONDITION" in f or "PENDING" in f])
    if adjusted_level >= 4:
        overall_risk = "CRITICAL"
    elif adjusted_level >= 3:
        overall_risk = "HIGH"
    elif adjusted_level >= 2:
        overall_risk = "MEDIUM"
    else:
        overall_risk = "LOW"

    return {
        "occupation_risk":   occ_risk,
        "overall_risk":      overall_risk,
        "risk_factors":      risk_factors,
        "compliance_flags":  risk_flags,
    }


# =========================================================================
# POLICY COMPARISON
# =========================================================================

def _compare_policies(inp: dict) -> dict | None:
    """
    Compare existing vs proposed policy.
    Only runs when both exist.
    """
    if not inp["has_existing_policy"] or not inp.get("proposed_insurer"):
        return None

    def_rank = {
        "OWN_OCCUPATION": 4, "MODIFIED_OWN_OCCUPATION": 3,
        "ANY_OCCUPATION": 2, "ACTIVITIES_OF_DAILY_LIVING": 1, "UNKNOWN": 0,
    }

    existing_def_score  = def_rank.get(inp["existing_occupation_def"], 0)
    proposed_def_score  = def_rank.get(inp["proposed_occupation_def"], 0)
    definition_improved = proposed_def_score > existing_def_score
    definition_worse    = proposed_def_score < existing_def_score

    existing_bp  = inp["existing_benefit_period_months"] or 0
    proposed_bp  = inp["proposed_benefit_period_months"] or 0
    # 0 = to-age-65 sentinel; treat as 480 months (40 years) for comparison
    existing_bp_n = 480 if existing_bp == 0 else existing_bp
    proposed_bp_n = 480 if proposed_bp == 0 else proposed_bp

    existing_benefit = inp["existing_monthly_benefit"] or 0
    proposed_benefit = inp["proposed_monthly_benefit"] or 0

    existing_premium = inp["existing_annual_premium"] or 0
    proposed_premium = inp["proposed_annual_premium"] or 0

    advantages    = []
    disadvantages = []
    warnings      = []

    if definition_improved:
        advantages.append(f"Proposed policy offers a better occupation definition ({inp['proposed_occupation_def']} vs {inp['existing_occupation_def']}).")
    if definition_worse:
        disadvantages.append(f"Proposed policy has a weaker occupation definition ({inp['proposed_occupation_def']} vs {inp['existing_occupation_def']}) — client may face a harder test to claim.")
        warnings.append("Weaker occupation definition is a material downgrade. Ensure the client gives informed consent.")

    if proposed_bp_n > existing_bp_n:
        advantages.append("Proposed policy has a longer benefit period.")
    elif proposed_bp_n < existing_bp_n:
        disadvantages.append("Proposed policy has a shorter benefit period — reduced long-term protection.")

    if proposed_benefit > existing_benefit:
        advantages.append(f"Proposed monthly benefit (${proposed_benefit:,.0f}) is higher than existing (${existing_benefit:,.0f}).")
    elif proposed_benefit < existing_benefit:
        disadvantages.append(f"Proposed monthly benefit (${proposed_benefit:,.0f}) is lower than existing (${existing_benefit:,.0f}).")

    if proposed_premium < existing_premium and proposed_premium > 0:
        advantages.append(f"Proposed premium (${proposed_premium:,.0f} pa) is lower than existing (${existing_premium:,.0f} pa).")
    elif proposed_premium > existing_premium > 0:
        disadvantages.append(f"Proposed premium (${proposed_premium:,.0f} pa) is higher than existing (${existing_premium:,.0f} pa).")

    if inp["proposed_has_waiver"] and not inp["existing_has_waiver"]:
        advantages.append("Proposed policy includes premium waiver — existing policy does not.")
    if inp["existing_has_waiver"] and not inp["proposed_has_waiver"]:
        disadvantages.append("Existing policy includes premium waiver — proposed policy does not.")

    if inp["proposed_has_indexation"] and not inp["existing_has_indexation"]:
        advantages.append("Proposed policy includes indexation — existing policy does not.")
    if inp["existing_has_indexation"] and not inp["proposed_has_indexation"]:
        disadvantages.append("Existing policy includes indexation — proposed policy does not. Real benefit value will erode.")

    overall = "BETTER" if len(advantages) > len(disadvantages) else ("WORSE" if len(disadvantages) > len(advantages) else "SIMILAR")

    return {
        "overall":             overall,
        "advantages":          advantages,
        "disadvantages":       disadvantages,
        "warnings":            warnings,
        "definition_improved": definition_improved,
        "definition_worse":    definition_worse,
    }


# =========================================================================
# REPLACEMENT RISK
# =========================================================================

def _assess_replacement_risk(inp: dict) -> dict:
    """
    ASIC IDII guidelines & Australian Insurance Contracts Act replacement risk.
    Also aligns with UK FCA Consumer Duty on replacing policies.
    """
    if not inp["has_existing_policy"]:
        return {"applies": False, "risk_level": "NONE", "flags": []}

    flags = []
    risk_score = 0

    # Cover gap risk: cancel before new policy commences
    flags.append({
        "code": "IP-REP-001",
        "severity": "WARNING",
        "message": "Do NOT cancel the existing policy until the new policy has been accepted (not merely offered) in writing, the premium has been received by the new insurer, and the policy is in force. A cover gap leaves the client uninsured.",
    })

    # Grandfathered terms
    existing_date = inp["existing_commencement_date"]
    if existing_date and (inp["evaluation_date"] - existing_date).days > 365 * 3:
        flags.append({
            "code": "IP-REP-002",
            "severity": "WARNING",
            "message": "Existing policy commenced more than 3 years ago. It may contain grandfathered terms (pre-APRA sustainability changes) that are more favourable than those available in new policies (e.g. full own-occupation definition for the entire benefit period without step-down). Verify whether the existing terms are superior before recommending replacement.",
        })
        risk_score += 1

    if inp["existing_has_exclusions"]:
        flags.append({
            "code": "IP-REP-003",
            "severity": "INFO",
            "message": "Existing exclusions may not carry over — new insurer may apply same or additional exclusions. Obtain full underwriting terms before proceeding.",
        })
        risk_score += 1

    if inp["pending_investigations"]:
        flags.append({
            "code": "IP-REP-004",
            "severity": "CRITICAL",
            "message": "PENDING MEDICAL INVESTIGATION: Do not replace existing cover while a medical investigation is outstanding. New insurer will likely defer or exclude the condition being investigated.",
        })
        risk_score += 3

    if inp["existing_has_loadings"]:
        risk_score += 1

    risk_level = "LOW" if risk_score == 0 else ("MEDIUM" if risk_score <= 1 else ("HIGH" if risk_score <= 3 else "CRITICAL"))

    return {
        "applies":     True,
        "risk_level":  risk_level,
        "risk_score":  risk_score,
        "flags":       flags,
    }


# =========================================================================
# COMPLIANCE FLAGS
# =========================================================================

def _build_compliance_flags(inp: dict, underwriting_risk: dict, replacement_risk: dict) -> list[dict]:
    """
    Build a consolidated compliance checklist aligned to:
    - Australian DDO (ASIC RG 274, updated Sept 2024)
    - ASIC IDII claims handling guidelines (2021)
    - UK Consumer Duty / FCA ICOBS demands-and-needs
    - APRA IDII sustainability measures
    - FATF/AML onboarding obligations (applicable to all jurisdictions)
    """
    flags = []

    # --- Target market / DDO ---
    flags.append({
        "code":     "IP-COMP-DDO-001",
        "domain":   "PRODUCT_GOVERNANCE",
        "severity": "INFO",
        "message":  "Confirm the client falls within the Target Market Determination (TMD) for this income protection product (ASIC DDO, RG 274 updated Sept 2024). Document the target market check before issuing the policy.",
    })

    # --- Demands and needs (UK ICOBS / AU suitability) ---
    flags.append({
        "code":     "IP-COMP-SUIT-001",
        "domain":   "SUITABILITY",
        "severity": "INFO",
        "message":  "Complete and document a demands-and-needs / Statement of Advice (SOA) before making a recommendation. The occupation definition, waiting period, and benefit period must be individually justified for this client (FCA ICOBS; ASIC personal advice obligations).",
    })

    # --- Claims handling ---
    flags.append({
        "code":     "IP-COMP-CLAIM-001",
        "domain":   "CLAIMS_HANDLING",
        "severity": "INFO",
        "message":  "Advise the client about the claims evidence requirements upfront: claim form, medical reports (GP and specialists), income/tax evidence, and ongoing monthly certificates. ASIC has highlighted non-disclosure investigations and surveillance practices as areas requiring governance (ASIC IDII claims review).",
    })

    # --- Indexation accuracy ---
    flags.append({
        "code":     "IP-COMP-IDX-002",
        "domain":   "CLAIMS_PAYMENT",
        "severity": "INFO",
        "message":  "Ensure the insurer's systems correctly apply CPI/RPI indexation to both benefits and premiums at each anniversary. ASIC has identified benefit calculation and indexation payment errors as a recurring issue requiring industry remediation.",
    })

    # --- AML/CTF onboarding ---
    flags.append({
        "code":     "IP-COMP-AML-001",
        "domain":   "AML_CFT",
        "severity": "INFO",
        "message":  "Complete AML/CTF identity verification before policy issue. For Australia: AUSTRAC guidance for life insurers applies. For Singapore: MAS Notice 314 (effective July 2025). For Hong Kong: IA GL3 (effective May 30, 2025). For India: IRDAI AML Master Guidelines. For Canada: FINTRAC life insurer guidance.",
    })

    # --- Premium waiver reminder ---
    if not inp.get("existing_has_waiver") and not inp.get("proposed_has_waiver"):
        flags.append({
            "code":     "IP-COMP-WAV-001",
            "domain":   "PRODUCT_FEATURES",
            "severity": "WARNING",
            "message":  "No premium waiver on claim — the client must continue paying premiums during a disability claim or risk policy lapse. Consider including premium waiver as a key feature to protect retention and customer outcomes.",
        })

    # --- APRA sustainability (AU) ---
    flags.append({
        "code":     "IP-COMP-APRA-001",
        "domain":   "PRUDENTIAL",
        "severity": "INFO",
        "message":  f"Monthly benefit is capped at {int(MAX_REPLACEMENT_RATIO * 100)}% of pre-disability income per APRA IDII sustainability measures (2019). Ensure the proposed benefit does not exceed this ratio. Benefit period and occupation definition step-down rules (own → any occupation after 24 months) must be disclosed to the client.",
    })

    # Merge flags from sub-assessments
    for f in underwriting_risk.get("compliance_flags", []):
        flags.append({**f, "domain": "UNDERWRITING"})
    for f in replacement_risk.get("flags", []):
        flags.append({**f, "domain": "REPLACEMENT"})

    return flags


# =========================================================================
# REQUIRED ACTIONS
# =========================================================================

def _build_required_actions(inp: dict, benefit_need: dict, waiting: dict, benefit_period: dict,
                             underwriting: dict, replacement: dict, comparison: dict | None) -> list[dict]:
    actions = []
    priority = 1

    if benefit_need["shortfall_level"] in ("SIGNIFICANT", "CRITICAL"):
        actions.append({
            "priority": priority,
            "action": f"Address significant income protection shortfall of ${benefit_need['annual_gap']:,.0f} pa. Consider increasing monthly benefit or adding a second policy.",
            "category": "BENEFIT_GAP",
        })
        priority += 1

    if waiting["comparison"] == "EXISTING_LONGER_THAN_RECOMMENDED":
        actions.append({
            "priority": priority,
            "action": f"Review waiting period: existing policy has {waiting['existing_waiting_period_weeks']} weeks but {waiting['recommended_waiting_period_weeks']} weeks is recommended. A shorter waiting period would improve early-disability coverage.",
            "category": "WAITING_PERIOD",
        })
        priority += 1

    if benefit_period["step_down_risk"] in ("HIGH",):
        actions.append({
            "priority": priority,
            "action": "Disclose step-down from own occupation to any occupation definition after 24 months on claim. Ensure client understands the definition change and its claim impact.",
            "category": "OCCUPATION_DEFINITION",
        })
        priority += 1

    if replacement["risk_level"] in ("HIGH", "CRITICAL"):
        actions.append({
            "priority": priority,
            "action": "DO NOT proceed with replacement until all replacement risks (pending investigations, grandfathered terms, cover gap) have been resolved. See compliance flags IP-REP-001 to IP-REP-004.",
            "category": "REPLACEMENT_RISK",
        })
        priority += 1

    if underwriting["overall_risk"] in ("HIGH", "CRITICAL"):
        actions.append({
            "priority": priority,
            "action": "High underwriting risk — obtain pre-approval / indicative underwriting terms from the new insurer before recommending replacement of the existing policy.",
            "category": "UNDERWRITING",
        })
        priority += 1

    if comparison and comparison["definition_worse"]:
        actions.append({
            "priority": priority,
            "action": "Proposed policy has a weaker occupation definition. Document informed consent from the client before proceeding with replacement.",
            "category": "POLICY_COMPARISON",
        })
        priority += 1

    if not inp.get("existing_has_waiver") and not inp.get("proposed_has_waiver"):
        actions.append({
            "priority": priority,
            "action": "Add premium waiver on claim to the policy. Without it, the client risks policy lapse during a disability — defeating the purpose of the cover.",
            "category": "PRODUCT_FEATURE",
        })
        priority += 1

    return actions


# =========================================================================
# RECOMMENDATION ENGINE
# =========================================================================

def _recommend(inp: dict, benefit_need: dict, comparison: dict | None,
                underwriting: dict, replacement: dict) -> dict:
    """
    Rule-based recommendation:
    PURCHASE_NEW / RETAIN_EXISTING / REPLACE_EXISTING / SUPPLEMENT_EXISTING / NEEDS_MORE_INFO
    """
    reasons = []
    risks   = []

    has_existing  = inp["has_existing_policy"]
    has_proposed  = bool(inp.get("proposed_insurer"))
    shortfall     = benefit_need["shortfall_level"]

    # Missing critical info
    if benefit_need["gross_annual_income"] == 0:
        return {
            "type":    "NEEDS_MORE_INFO",
            "summary": "Unable to generate a recommendation — client income is required to assess income replacement need.",
            "reasons": ["Annual gross income not provided."],
            "risks":   [],
        }

    if not has_existing and not has_proposed:
        # Pure purchase scenario — no existing cover
        if shortfall in ("MODERATE", "SIGNIFICANT", "CRITICAL"):
            rec_type = "PURCHASE_NEW"
            reasons.append("Client has no existing income protection cover and has a significant income replacement need.")
            reasons.append(f"Recommended monthly benefit: ${benefit_need['recommended_monthly_benefit']:,.0f} (capped at {MAX_REPLACEMENT_RATIO * 100:.0f}% of gross monthly income per APRA IDII sustainability rules).")
        elif shortfall == "MINOR":
            rec_type = "PURCHASE_NEW"
            reasons.append("Client has no existing IP cover. Even a minor gap warrants establishing protection given disability risk.")
        else:
            rec_type = "PURCHASE_NEW"
            reasons.append("No existing income protection. A new policy should be evaluated to protect against disability income loss.")
        return {"type": rec_type, "summary": reasons[0], "reasons": reasons, "risks": risks}

    if has_existing and not has_proposed:
        # Retention scenario — no proposed policy
        if shortfall in ("NONE", "MINOR"):
            rec_type = "RETAIN_EXISTING"
            reasons.append("Existing policy appears to adequately cover the client's income replacement need.")
            reasons.append("No proposed replacement policy provided — retaining existing cover is appropriate unless a material deficiency is identified.")
        else:
            rec_type = "SUPPLEMENT_EXISTING"
            reasons.append(f"Existing policy does not fully cover the income replacement need — a shortfall of ${benefit_need['annual_gap']:,.0f} pa exists.")
            reasons.append("Consider supplementing with an additional IP policy to close the gap, subject to total replacement ratio remaining within the 70% cap.")
            risks.append("Dual-policy offsets may apply — confirm offset provisions of both policies with the insurer.")
        return {"type": rec_type, "summary": reasons[0], "reasons": reasons, "risks": risks}

    if has_existing and has_proposed:
        # Replacement scenario
        if replacement["risk_level"] in ("CRITICAL",):
            rec_type = "RETAIN_EXISTING"
            reasons.append("Replacement is not recommended due to critical risks (pending investigation or other critical risk factors). Retain existing cover.")
            risks.append("Critical replacement risk detected — see compliance flags.")
        elif comparison and comparison["overall"] == "BETTER" and replacement["risk_level"] not in ("HIGH", "CRITICAL"):
            rec_type = "REPLACE_EXISTING"
            reasons.append("Proposed policy is materially better than the existing policy.")
            reasons += comparison.get("advantages", [])[:3]
            risks  += comparison.get("disadvantages", [])[:2]
        elif comparison and comparison["overall"] == "WORSE":
            rec_type = "RETAIN_EXISTING"
            reasons.append("Proposed policy is worse than the existing policy on balance — retaining existing cover is recommended.")
            risks   += comparison.get("disadvantages", [])[:3]
        else:
            rec_type = "RETAIN_EXISTING"
            reasons.append("Proposed and existing policy are broadly similar — replacement is not clearly justified. Retain existing cover and monitor.")
            risks.append("Replacement triggers re-underwriting, potential exclusions, and a cover gap risk.")

        if underwriting["overall_risk"] in ("HIGH", "CRITICAL"):
            risks.append(f"Underwriting risk is {underwriting['overall_risk']} — replacement may result in adverse terms on the new policy.")

        return {"type": rec_type, "summary": reasons[0] if reasons else "Assessment inconclusive.", "reasons": reasons, "risks": risks}

    # Fallback
    return {
        "type":    "NEEDS_MORE_INFO",
        "summary": "Insufficient information to generate a recommendation.",
        "reasons": [],
        "risks":   [],
    }


# =========================================================================
# TOOL CLASS
# =========================================================================

class IncomeProtectionPolicyTool(BaseTool):
    name        = "purchase_retain_income_protection_policy"
    version     = ENGINE_VERSION
    description = (
        "Analyses income protection / disability income insurance scenarios for Australian "
        "financial advisers. Evaluates benefit need (70% replacement ratio cap per APRA IDII), "
        "waiting period alignment to employer sick pay, benefit period suitability, "
        "indexation rules, occupation definition step-down risk, premium affordability "
        "(grace period / lapse / waiver mechanics), underwriting risk, policy comparison, "
        "and replacement risk. Returns a rule-based recommendation with a compliance "
        "checklist aligned to ASIC DDO, APRA IDII sustainability measures, AML/CTF "
        "obligations, and Consumer Duty / fair-value principles."
    )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "evaluationDate": {"type": "string", "format": "date-time", "description": "ISO 8601 evaluation date. Defaults to now."},
                "client": {
                    "type": "object",
                    "properties": {
                        "age":                  {"type": "integer", "description": "Client age in years."},
                        "dateOfBirth":          {"type": "string",  "format": "date", "description": "ISO date YYYY-MM-DD. Used to compute age if age is omitted."},
                        "occupationClass":      {"type": "string",  "enum": ["CLASS_1_WHITE_COLLAR", "CLASS_2_LIGHT_BLUE", "CLASS_3_BLUE_COLLAR", "CLASS_4_HAZARDOUS", "UNKNOWN"]},
                        "occupation":           {"type": "string",  "description": "Free-text occupation description."},
                        "employmentType":       {"type": "string",  "enum": ["EMPLOYED_FULL_TIME", "EMPLOYED_PART_TIME", "SELF_EMPLOYED", "UNEMPLOYED", "UNKNOWN"]},
                        "annualGrossIncome":    {"type": "number",  "description": "Annual gross income AUD."},
                        "annualNetIncome":      {"type": "number",  "description": "Annual net (after-tax) income AUD. Estimated if omitted."},
                        "isSmoker":             {"type": "boolean"},
                        "residency":            {"type": "string",  "description": "e.g. 'AUSTRALIA', 'UK'"},
                    },
                    "required": ["annualGrossIncome"],
                },
                "existingPolicy": {
                    "type": "object",
                    "properties": {
                        "hasExistingPolicy":        {"type": "boolean"},
                        "insurerName":              {"type": "string"},
                        "waitingPeriodWeeks":        {"type": "integer", "enum": [2, 4, 8, 13, 26, 52]},
                        "benefitPeriodMonths":       {"type": "integer", "description": "0 = to age 65. Otherwise 12, 24, 60."},
                        "monthlyBenefit":            {"type": "number", "description": "AUD monthly benefit amount."},
                        "annualPremium":             {"type": "number", "description": "AUD annual premium."},
                        "occupationDefinition":     {"type": "string",  "enum": ["OWN_OCCUPATION", "MODIFIED_OWN_OCCUPATION", "ANY_OCCUPATION", "ACTIVITIES_OF_DAILY_LIVING", "UNKNOWN"]},
                        "stepDownApplies":           {"type": "boolean", "description": "True if own-occupation steps down to any-occupation after 24 months."},
                        "hasIndexation":             {"type": "boolean"},
                        "indexationType":            {"type": "string",  "enum": ["CPI", "RPI", "FIXED", "NONE"]},
                        "hasPremiumWaiver":          {"type": "boolean"},
                        "hasPartialDisabilityCover": {"type": "boolean"},
                        "hasRehabBenefit":           {"type": "boolean"},
                        "hasSuperContributionsBenefit": {"type": "boolean"},
                        "offsets":                  {"type": "array",  "items": {"type": "string"}},
                        "hasLoadings":               {"type": "boolean"},
                        "loadingDetails":            {"type": "string"},
                        "hasExclusions":             {"type": "boolean"},
                        "exclusionDetails":          {"type": "string"},
                        "commencementDate":          {"type": "string", "format": "date"},
                    },
                },
                "proposedPolicy": {
                    "type": "object",
                    "description": "Candidate replacement or new policy.",
                    "properties": {
                        "insurerName":              {"type": "string"},
                        "waitingPeriodWeeks":        {"type": "integer", "enum": [2, 4, 8, 13, 26, 52]},
                        "benefitPeriodMonths":       {"type": "integer"},
                        "monthlyBenefit":            {"type": "number"},
                        "annualPremium":             {"type": "number"},
                        "occupationDefinition":     {"type": "string",  "enum": ["OWN_OCCUPATION", "MODIFIED_OWN_OCCUPATION", "ANY_OCCUPATION", "ACTIVITIES_OF_DAILY_LIVING", "UNKNOWN"]},
                        "hasIndexation":             {"type": "boolean"},
                        "indexationType":            {"type": "string",  "enum": ["CPI", "RPI", "FIXED", "NONE"]},
                        "hasPremiumWaiver":          {"type": "boolean"},
                        "hasPartialDisabilityCover": {"type": "boolean"},
                        "hasRehabBenefit":           {"type": "boolean"},
                        "hasSuperContributionsBenefit": {"type": "boolean"},
                        "offsets":                  {"type": "array",  "items": {"type": "string"}},
                        "expectedLoadings":          {"type": "string"},
                        "expectedExclusions":        {"type": "string"},
                    },
                },
                "health": {
                    "type": "object",
                    "properties": {
                        "existingMedicalConditions": {"type": "array",  "items": {"type": "string"}},
                        "currentMedications":        {"type": "array",  "items": {"type": "string"}},
                        "pendingInvestigations":     {"type": "boolean"},
                        "familyHistoryConditions":   {"type": "array",  "items": {"type": "string"}},
                        "hazardousActivities":       {"type": "array",  "items": {"type": "string"}},
                    },
                },
                "goals": {
                    "type": "object",
                    "properties": {
                        "wantsReplacement":               {"type": "boolean"},
                        "wantsRetention":                 {"type": "boolean"},
                        "affordabilityIsConcern":         {"type": "boolean"},
                        "wantsOwnOccupationDefinition":   {"type": "boolean"},
                        "wantsLongBenefitPeriod":         {"type": "boolean"},
                        "wantsIndexation":                {"type": "boolean"},
                        "prioritisesPremiumWaiver":       {"type": "boolean"},
                        "wantsSuperContributionsBenefit": {"type": "boolean"},
                        "employerSickPayWeeks":           {"type": "integer", "description": "Weeks of employer-paid sick pay available before the waiting period matters."},
                    },
                },
                "financialPosition": {
                    "type": "object",
                    "properties": {
                        "liquidAssets":    {"type": "number"},
                        "mortgageBalance": {"type": "number"},
                        "monthlyExpenses": {"type": "number", "description": "Monthly living expenses AUD."},
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

        # 3. Run all analyses (partial results even with missing info)
        benefit_need     = _calc_benefit_need(inp)
        waiting          = _assess_waiting_period(inp)
        benefit_period   = _assess_benefit_period(inp)
        indexation       = _assess_indexation(inp)
        affordability    = _assess_affordability(inp)
        underwriting     = _assess_underwriting_risk(inp)
        replacement      = _assess_replacement_risk(inp)
        comparison       = _compare_policies(inp)

        # 4. Compliance flags (consolidated)
        compliance_flags = _build_compliance_flags(inp, underwriting, replacement)

        # 5. Required actions
        required_actions = _build_required_actions(
            inp, benefit_need, waiting, benefit_period, underwriting, replacement, comparison
        )

        # 6. Recommendation
        recommendation = _recommend(inp, benefit_need, comparison, underwriting, replacement)
        recommendation["benefit_need"]       = benefit_need
        recommendation["waiting_period"]     = waiting
        recommendation["benefit_period"]     = benefit_period
        recommendation["indexation"]         = indexation
        recommendation["affordability"]      = affordability
        recommendation["underwriting_risk"]  = underwriting
        recommendation["replacement_risk"]   = replacement
        recommendation["policy_comparison"]  = comparison
        recommendation["required_actions"]   = required_actions

        # 7. Advice mode
        advice_mode = "NEEDS_MORE_INFO" if blocking else "STRATEGIC_ADVICE"

        return {
            "recommendation":       recommendation,
            "validation":           validation,
            "missing_info_questions": missing_questions,
            "compliance_flags":     compliance_flags,
            "advice_mode":          advice_mode,
            "engine_version":       ENGINE_VERSION,
        }
