"""
life_tpd_policy.py — Purchase/Retain Life & TPD Policy tool.

Python port of the TypeScript engine in:
  frontend/lib/tools/purchaseRetainLifeTPDPolicy/

Produces: life need, TPD need, affordability, policy comparison,
underwriting risk, replacement risk, rule-based recommendation, compliance flags.

This tool is deterministic: same input → same output. No LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolValidationError

# =========================================================================
# CONSTANTS (ported from purchaseRetainLifeTPDPolicy.constants.ts)
# =========================================================================

ENGINE_VERSION = "1.0.0"
DEFAULT_FINAL_EXPENSES_AUD = 25_000
DEFAULT_EDUCATION_FUNDING_PER_CHILD_AUD = 50_000
DEFAULT_INCOME_REPLACEMENT_YEARS = 10
DEFAULT_MEDICAL_REHAB_BUFFER_AUD = 75_000
DEFAULT_HOME_MODIFICATION_BUFFER_AUD = 50_000
DEFAULT_ONGOING_CARE_BUFFER_AUD = 60_000
TPD_CAPITALISATION_RATE = 0.05
DEFAULT_INCOME_REPLACEMENT_PERCENT = 1.0
STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR = 0.06

SHORTFALL_THRESHOLDS = {"NONE": 0, "MINOR": 50_000, "MODERATE": 200_000, "SIGNIFICANT": 500_000}
AFFORDABILITY_INCOME_BANDS = {"COMFORTABLE": 0.01, "MANAGEABLE": 0.03, "STRETCHED": 0.05}
AFFORDABILITY_NET_INCOME_BANDS = {"COMFORTABLE": 0.015, "MANAGEABLE": 0.04, "STRETCHED": 0.07}

TPD_DEFINITION_RANK = {
    "OWN_OCCUPATION": 5, "MODIFIED_OWN_OCCUPATION": 4, "ANY_OCCUPATION": 3,
    "ACTIVITIES_OF_DAILY_LIVING": 2, "HOME_DUTIES": 1, "UNKNOWN": 0,
}
OCCUPATION_RISK_MAP = {
    "CLASS_1_WHITE_COLLAR": "LOW", "CLASS_2_LIGHT_BLUE": "MEDIUM",
    "CLASS_3_BLUE_COLLAR": "HIGH", "CLASS_4_HAZARDOUS": "CRITICAL", "UNKNOWN": "MEDIUM",
}
BMI_THRESHOLDS = {"UNDERWEIGHT": 18.5, "NORMAL": 25.0, "OVERWEIGHT": 30.0, "OBESE": 35.0}
COMPARISON_MATERIALLY_BETTER = 0.15
COMPARISON_MARGINALLY_BETTER = 0.05


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


def _pv_annuity(pmt: float, n: float, r: float) -> float:
    if r == 0:
        return pmt * n
    return pmt * (1 - (1 + r) ** -n) / r


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


def _bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if height_cm and weight_kg and height_cm > 0:
        return weight_kg / ((height_cm / 100) ** 2)
    return None


def _bmi_category(bmi: float | None) -> str:
    if bmi is None:
        return "UNKNOWN"
    if bmi < BMI_THRESHOLDS["UNDERWEIGHT"]:
        return "UNDERWEIGHT"
    if bmi < BMI_THRESHOLDS["NORMAL"]:
        return "NORMAL"
    if bmi < BMI_THRESHOLDS["OVERWEIGHT"]:
        return "OVERWEIGHT"
    if bmi < BMI_THRESHOLDS["OBESE"]:
        return "OBESE"
    return "SEVERELY_OBESE"


# =========================================================================
# NORMALIZE
# =========================================================================

def _normalize(raw: dict) -> dict:
    eval_date = _safe_parse_date(raw.get("evaluationDate")) or datetime.now(timezone.utc)
    c = raw.get("client") or {}
    ep = raw.get("existingPolicy") or {}
    h = raw.get("health") or {}
    g = raw.get("goals") or {}
    np_ = raw.get("newPolicyCandidate") or {}

    dob = _safe_parse_date(c.get("dateOfBirth"))
    age = c.get("age")
    if age is None and dob:
        age = _compute_age(dob, eval_date)

    return {
        "advice_mode": raw.get("adviceMode", "PERSONAL_ADVICE"),
        "evaluation_date": eval_date,
        # Client
        "age": age,
        "smoker": c.get("smoker", False),
        "occupation": c.get("occupation"),
        "occupation_class": c.get("occupationClass", "UNKNOWN"),
        "employment_type": c.get("employmentType", "UNKNOWN"),
        "annual_gross_income": c.get("annualGrossIncome"),
        "annual_net_income": c.get("annualNetIncome"),
        "has_partner": c.get("hasPartner"),
        "partner_income": c.get("partnerIncome"),
        "number_of_dependants": c.get("numberOfDependants"),
        "youngest_dependant_age": c.get("youngestDependantAge"),
        "mortgage_balance": c.get("mortgageBalance"),
        "other_debts": c.get("otherDebts"),
        "liquid_assets": c.get("liquidAssets"),
        "existing_life_cover_si": c.get("existingLifeCoverSumInsured"),
        "existing_tpd_cover_si": c.get("existingTPDCoverSumInsured"),
        "years_to_retirement": c.get("yearsToRetirement"),
        # Existing policy
        "has_existing_policy": ep.get("hasExistingPolicy", False),
        "existing_insurer": ep.get("insurer"),
        "existing_ownership": ep.get("ownership", "UNKNOWN"),
        "existing_commencement_date": _safe_parse_date(ep.get("commencementDate")),
        "existing_cover_types": ep.get("coverTypes", []),
        "existing_life_si": ep.get("lifeSumInsured"),
        "existing_tpd_si": ep.get("tpdSumInsured"),
        "existing_tpd_definition": ep.get("tpdDefinition", "UNKNOWN"),
        "existing_premium_structure": ep.get("premiumStructure", "UNKNOWN"),
        "existing_annual_premium": ep.get("annualPremium"),
        "existing_has_loadings": ep.get("hasLoadings", False),
        "existing_loading_details": ep.get("loadingDetails"),
        "existing_has_exclusions": ep.get("hasExclusions", False),
        "existing_exclusion_details": ep.get("exclusionDetails"),
        "existing_has_indexation": ep.get("hasIndexation", False),
        "existing_riders": ep.get("riders", []),
        "existing_non_disclosure_risk": ep.get("hasFullNonDisclosureRisk", False),
        "existing_superior_grandfathered": ep.get("hasSuperiorGrandfatheredTerms", False),
        # Health
        "height_cm": h.get("heightCm"),
        "weight_kg": h.get("weightKg"),
        "medical_conditions": h.get("existingMedicalConditions", []),
        "medications": h.get("currentMedications", []),
        "pending_investigations": h.get("pendingInvestigations", False),
        "pending_investigation_details": h.get("pendingInvestigationDetails"),
        "family_history": h.get("familyHistoryConditions", []),
        "hazardous_activities": h.get("hazardousActivities", []),
        "non_disclosure_risk": h.get("nonDisclosureRisk", False),
        # Goals
        "primary_reason": g.get("primaryReason"),
        "wants_replacement": g.get("wantsReplacement"),
        "wants_retention": g.get("wantsRetention"),
        "affordability_concern": g.get("affordabilityIsConcern"),
        "wants_premium_certainty": g.get("wantsPremiumCertainty"),
        "wants_own_occupation_tpd": g.get("wantsOwnOccupationTPD"),
        "desired_cover_horizon": g.get("desiredCoverHorizon"),
        "willing_to_underwrite": g.get("willingToUnderwrite"),
        "prioritises_definition_quality": g.get("prioritisesDefinitionQuality"),
        "prioritises_claims_reputation": g.get("prioritisesClaimsReputation"),
        # New policy candidate
        "has_new_candidate": bool(np_.get("insurer")),
        "new_insurer": np_.get("insurer"),
        "new_ownership": np_.get("ownership", "UNKNOWN"),
        "new_cover_types": np_.get("coverTypes", []),
        "new_life_si": np_.get("lifeSumInsured"),
        "new_tpd_si": np_.get("tpdSumInsured"),
        "new_tpd_definition": np_.get("tpdDefinition", "UNKNOWN"),
        "new_premium_structure": np_.get("premiumStructure", "UNKNOWN"),
        "new_annual_premium": np_.get("projectedAnnualPremium"),
        "new_expected_loadings": np_.get("expectedLoadings"),
        "new_expected_exclusions": np_.get("expectedExclusions"),
        "new_has_indexation": np_.get("hasIndexation", False),
        "new_flexibility_features": np_.get("flexibilityFeatures", []),
        "new_claims_quality": np_.get("claimsQualityRating"),
        "new_underwriting_status": np_.get("underwritingStatus"),
    }


# =========================================================================
# VALIDATION
# =========================================================================

def _validate(raw: dict) -> dict:
    errors = []
    warnings = []
    questions = []
    c = raw.get("client") or {}

    if c.get("age") is None and not c.get("dateOfBirth"):
        errors.append({"field": "client.age", "message": "Client age or DOB required.", "category": "CLIENT_PROFILE"})
        questions.append({"id": "Q-001", "question": "What is the client's age?", "category": "CLIENT_PROFILE", "blocking": True})

    if c.get("annualGrossIncome") is None:
        errors.append({"field": "client.annualGrossIncome", "message": "Annual gross income required for need analysis.", "category": "CLIENT_PROFILE"})
        questions.append({"id": "Q-002", "question": "What is the client's annual gross income?", "category": "CLIENT_PROFILE", "blocking": True})

    ep = raw.get("existingPolicy") or {}
    if ep.get("hasExistingPolicy") and ep.get("lifeSumInsured") is None and ep.get("tpdSumInsured") is None:
        warnings.append({"field": "existingPolicy.lifeSumInsured", "message": "Existing policy sum insured not provided — comparison will be incomplete."})
        questions.append({"id": "Q-003", "question": "What is the existing policy's sum insured (life/TPD)?", "category": "EXISTING_POLICY", "blocking": False})

    h = raw.get("health") or {}
    if not h:
        questions.append({"id": "Q-004", "question": "Please provide health information (height, weight, conditions, medications).", "category": "HEALTH", "blocking": False})

    is_valid = len(errors) == 0
    return {"isValid": is_valid, "errors": errors, "warnings": warnings, "missingInfoQuestions": questions}


# =========================================================================
# CALCULATIONS — LIFE NEED
# =========================================================================

def _calc_life_need(inp: dict) -> dict:
    assumptions = []
    debt_clearance = (inp["mortgage_balance"] or 0) + (inp["other_debts"] or 0)
    if inp["mortgage_balance"] is None:
        assumptions.append("Mortgage balance not provided — assumed $0.")

    num_dep = inp["number_of_dependants"] or 0
    education_need = num_dep * DEFAULT_EDUCATION_FUNDING_PER_CHILD_AUD
    if inp["number_of_dependants"] is None:
        assumptions.append("Number of dependants not provided — assumed 0.")

    gross_income = inp["annual_gross_income"] or 0
    years = inp["years_to_retirement"] or DEFAULT_INCOME_REPLACEMENT_YEARS
    partner_factor = 0.5 if inp["has_partner"] else 0.0
    income_replacement = round(gross_income * DEFAULT_INCOME_REPLACEMENT_PERCENT * years * (1 - partner_factor), 0)
    if inp["years_to_retirement"] is None:
        assumptions.append(f"Years to retirement not provided — defaulted to {DEFAULT_INCOME_REPLACEMENT_YEARS}.")
    if inp["has_partner"]:
        assumptions.append("Partner income assumed to contribute 50% — income replacement halved.")

    gross = debt_clearance + education_need + income_replacement + DEFAULT_FINAL_EXPENSES_AUD

    less_existing = (inp["existing_life_cover_si"] or 0) + (inp["existing_life_si"] or 0)
    less_liquid = inp["liquid_assets"] or 0
    net = max(0.0, gross - less_existing - less_liquid)

    return {
        "debt_clearance_need": debt_clearance,
        "education_funding_need": education_need,
        "income_replacement_need": income_replacement,
        "final_expenses_need": DEFAULT_FINAL_EXPENSES_AUD,
        "other_capital_needs": 0,
        "gross_need": gross,
        "less_existing_cover": less_existing,
        "less_liquid_assets": less_liquid,
        "net_life_insurance_need": net,
        "shortfall_level": _classify_shortfall(net),
        "assumptions": assumptions,
    }


# =========================================================================
# CALCULATIONS — TPD NEED
# =========================================================================

def _calc_tpd_need(inp: dict) -> dict:
    assumptions = []
    debt_clearance = (inp["mortgage_balance"] or 0) + (inp["other_debts"] or 0)
    net_income = inp["annual_net_income"]
    gross = inp["annual_gross_income"]

    if net_income is None and gross is not None:
        net_income = round(gross * 0.7, 0)
        assumptions.append("Net income not provided — estimated at 70% of gross income.")
    net_income = net_income or 0

    years = inp["years_to_retirement"] or DEFAULT_INCOME_REPLACEMENT_YEARS
    if inp["years_to_retirement"] is None:
        assumptions.append(f"Years to retirement not provided — defaulted to {DEFAULT_INCOME_REPLACEMENT_YEARS}.")
    assumptions.append(f"TPD income capitalisation rate: {TPD_CAPITALISATION_RATE * 100:.1f}% p.a.")

    capitalised_income = round(_pv_annuity(net_income, years, TPD_CAPITALISATION_RATE), 0)
    gross_need = (
        debt_clearance + DEFAULT_MEDICAL_REHAB_BUFFER_AUD + capitalised_income +
        DEFAULT_HOME_MODIFICATION_BUFFER_AUD + DEFAULT_ONGOING_CARE_BUFFER_AUD
    )
    less_existing = (inp["existing_tpd_cover_si"] or 0) + (inp["existing_tpd_si"] or 0)
    less_liquid = inp["liquid_assets"] or 0
    net = max(0.0, gross_need - less_existing - less_liquid)

    return {
        "debt_clearance_need": debt_clearance,
        "medical_rehab_buffer": DEFAULT_MEDICAL_REHAB_BUFFER_AUD,
        "income_replacement_capitalised": capitalised_income,
        "home_modification_buffer": DEFAULT_HOME_MODIFICATION_BUFFER_AUD,
        "ongoing_care_buffer": DEFAULT_ONGOING_CARE_BUFFER_AUD,
        "gross_need": gross_need,
        "less_existing_tpd_cover": less_existing,
        "less_liquid_assets": less_liquid,
        "net_tpd_need": net,
        "shortfall_level": _classify_shortfall(net),
        "capitalisation_rate": TPD_CAPITALISATION_RATE,
        "assumptions": assumptions,
    }


# =========================================================================
# CALCULATIONS — AFFORDABILITY
# =========================================================================

def _calc_affordability(inp: dict) -> dict:
    notes = []
    premium = inp["new_annual_premium"] or inp["existing_annual_premium"]

    if premium is None:
        return {
            "total_annual_premium": None, "premium_as_pct_gross": None, "premium_as_pct_net": None,
            "projected_premium_10yr": None, "affordability_score": 50, "lapse_risk_score": 50,
            "stress_case_affordable": None, "assessment": "UNKNOWN",
            "notes": ["Premium not provided — affordability cannot be assessed."],
        }

    gross = inp["annual_gross_income"] or 0
    net = inp["annual_net_income"] or gross * 0.7
    pct_gross = round((premium / gross) * 100, 2) if gross > 0 else None
    pct_net = round((premium / net) * 100, 2) if net > 0 else None

    struct = inp["new_premium_structure"] if inp["new_premium_structure"] != "UNKNOWN" else inp["existing_premium_structure"]
    projected_10yr = round(premium * ((1 + STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR) ** 10), 0) if struct == "STEPPED" else premium
    if struct == "STEPPED":
        notes.append(f"Stepped premium projected to ~${projected_10yr:,.0f} p.a. in 10 years.")

    gross_ratio = pct_gross or 0.0
    if gross_ratio < AFFORDABILITY_INCOME_BANDS["COMFORTABLE"] * 100:
        score, assessment = 90, "COMFORTABLE"
    elif gross_ratio < AFFORDABILITY_INCOME_BANDS["MANAGEABLE"] * 100:
        score, assessment = 70, "MANAGEABLE"
    elif gross_ratio < AFFORDABILITY_INCOME_BANDS["STRETCHED"] * 100:
        score, assessment = 45, "STRETCHED"
    else:
        score, assessment = 20, "UNAFFORDABLE"

    if gross > 0 and projected_10yr is not None:
        future_ratio = (projected_10yr / gross) * 100
        if future_ratio >= AFFORDABILITY_INCOME_BANDS["STRETCHED"] * 100:
            score = max(0, score - 15)
            notes.append("Future stepped premium approaches affordability limits.")

    if inp["affordability_concern"]:
        score = max(0, score - 15)
        notes.append("Client has indicated affordability is a concern.")

    stress_ok = (projected_10yr / gross < AFFORDABILITY_NET_INCOME_BANDS["STRETCHED"]) if (gross > 0 and projected_10yr) else None

    return {
        "total_annual_premium": premium, "premium_as_pct_gross": pct_gross, "premium_as_pct_net": pct_net,
        "projected_premium_10yr": projected_10yr, "affordability_score": _clamp(score, 0, 100),
        "lapse_risk_score": _clamp(100 - score, 0, 100), "stress_case_affordable": stress_ok,
        "assessment": assessment, "notes": notes,
    }


# =========================================================================
# UNDERWRITING RISK
# =========================================================================

def _assess_underwriting_risk(inp: dict) -> dict:
    factors = []
    risk_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    max_risk = "LOW"

    def add_factor(factor: str, risk: str, detail: str):
        nonlocal max_risk
        factors.append({"factor": factor, "risk_contribution": risk, "detail": detail})
        if risk_rank[risk] > risk_rank[max_risk]:
            max_risk = risk

    occ_risk = OCCUPATION_RISK_MAP.get(inp["occupation_class"], "MEDIUM")
    add_factor("HAZARDOUS_OCCUPATION" if occ_risk in ("HIGH", "CRITICAL") else "OCCUPATION", occ_risk, f"Occupation class: {inp['occupation_class']}.")

    if inp["smoker"]:
        add_factor("SMOKER", "HIGH", "Smoker — standard premium loading expected.")

    bmi_val = _bmi(inp["height_cm"], inp["weight_kg"])
    bmi_cat = _bmi_category(bmi_val)
    if bmi_cat == "OBESE":
        add_factor("BMI_HIGH", "HIGH", f"BMI {bmi_val:.1f} — obese category.")
    elif bmi_cat == "SEVERELY_OBESE":
        add_factor("BMI_VERY_HIGH", "CRITICAL", f"BMI {bmi_val:.1f} — severely obese.")

    if inp["medical_conditions"]:
        add_factor("EXISTING_CONDITION", "HIGH", f"{len(inp['medical_conditions'])} existing medical condition(s).")

    if inp["pending_investigations"]:
        add_factor("PENDING_INVESTIGATION", "CRITICAL", "Pending medical investigations — outcome unknown.")

    if inp["family_history"]:
        add_factor("ADVERSE_FAMILY_HISTORY", "MEDIUM", f"{len(inp['family_history'])} adverse family history condition(s).")

    if inp["hazardous_activities"]:
        add_factor("HAZARDOUS_ACTIVITY", "HIGH", f"{len(inp['hazardous_activities'])} hazardous activity/activities.")

    if inp["non_disclosure_risk"]:
        add_factor("NON_DISCLOSURE_RISK", "CRITICAL", "Non-disclosure risk identified — existing cover may be voidable.")

    likely_outcome = {
        "LOW": "STANDARD", "MEDIUM": "LOADED_PREMIUM", "HIGH": "LOADED_AND_EXCLUSION",
        "CRITICAL": "DECLINE_POSSIBLE",
    }[max_risk]

    recommendations = []
    if max_risk in ("HIGH", "CRITICAL"):
        recommendations.append("Obtain pre-assessment or indication from insurer before proceeding.")
    if inp["non_disclosure_risk"]:
        recommendations.append("Specialist adviser review of non-disclosure risk essential.")

    return {
        "overall_risk": max_risk,
        "factors": factors,
        "bmi": round(bmi_val, 1) if bmi_val else None,
        "bmi_category": bmi_cat,
        "likely_outcome": likely_outcome,
        "recommendations": recommendations,
    }


# =========================================================================
# REPLACEMENT RISK
# =========================================================================

def _assess_replacement_risk(inp: dict, uw_risk: dict, comparison: dict) -> dict:
    factors = []
    risk_rank = {"NEGLIGIBLE": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "BLOCKING": 4}
    max_risk = "NEGLIGIBLE"

    def add_factor(factor: str, risk: str, desc: str):
        nonlocal max_risk
        factors.append({"factor": factor, "risk_level": risk, "description": desc})
        if risk_rank[risk] > risk_rank[max_risk]:
            max_risk = risk

    if inp["existing_superior_grandfathered"]:
        add_factor("GRANDFATHERED_TERMS", "BLOCKING", "Existing policy has superior grandfathered terms — replacement is high risk.")

    if inp["existing_non_disclosure_risk"]:
        add_factor("NON_DISCLOSURE", "BLOCKING", "Non-disclosure risk on existing policy — replacement could void current cover.")

    if inp["pending_investigations"]:
        add_factor("PENDING_INVESTIGATIONS", "HIGH", "Pending medical investigations — new policy could exclude or decline cover.")

    if uw_risk["overall_risk"] == "CRITICAL":
        add_factor("CRITICAL_UNDERWRITING", "BLOCKING", "Critical underwriting risk — new policy likely to decline or impose harsh terms.")

    if inp["existing_has_loadings"] and not inp["new_expected_loadings"]:
        add_factor("LOADING_RISK", "HIGH", "Existing policy has loadings that may be replicated or worsened on new policy.")

    if inp["existing_has_exclusions"] and not inp["new_expected_exclusions"]:
        add_factor("EXCLUSION_RISK", "MODERATE", "Existing exclusions may be replicated or additional ones added on new policy.")

    warnings = []
    if max_risk in ("HIGH", "BLOCKING"):
        warnings.append("Do not cancel existing cover until new cover is fully accepted in writing.")
    if inp["existing_superior_grandfathered"]:
        warnings.append("Grandfathered terms will be permanently lost on replacement — document carefully.")

    required_actions = []
    if max_risk == "BLOCKING":
        required_actions.append("STOP: Replacement risk is BLOCKING. Seek specialist advice before proceeding.")

    return {
        "overall_risk": max_risk,
        "factors": factors,
        "existing_cover_at_risk": max_risk in ("HIGH", "BLOCKING"),
        "coverage_gap_possible": True if inp["has_new_candidate"] else False,
        "warnings": warnings,
        "required_actions": required_actions,
    }


# =========================================================================
# POLICY COMPARISON
# =========================================================================

def _compare_policies(inp: dict) -> dict:
    if not inp["has_new_candidate"]:
        return {
            "has_comparison_candidate": False, "overall_outcome": "INSUFFICIENT_DATA",
            "dimensions": [], "premium_difference_annual": None,
            "sum_insured_diff_life": None, "sum_insured_diff_tpd": None,
            "tpd_definition_change": "UNKNOWN", "exclusion_change": "UNKNOWN",
            "loading_change": "UNKNOWN", "reasoning": [], "replacement_warnings": [],
        }

    dimensions = []
    total_weight = 0.0
    weighted_advantage = 0.0

    def add_dim(name: str, existing, new_, verdict: str, weight: float, note: str):
        nonlocal total_weight, weighted_advantage
        dimensions.append({"dimension": name, "existing_value": existing, "new_value": new_, "verdict": verdict, "weight": weight, "notes": note})
        total_weight += weight
        if verdict == "NEW_BETTER":
            weighted_advantage += weight
        elif verdict == "NEW_WORSE":
            weighted_advantage -= weight

    # Premium (lower is better for client)
    ep = inp["existing_annual_premium"]
    np_ = inp["new_annual_premium"]
    prem_diff = (ep - np_) if (ep and np_) else None
    prem_verdict = ("NEW_BETTER" if prem_diff and prem_diff > 0 else "NEW_WORSE" if prem_diff and prem_diff < 0 else "EQUIVALENT")
    add_dim("Premium", ep, np_, prem_verdict, 0.25, f"Annual premium difference: ${prem_diff:,.0f}" if prem_diff else "Premium not comparable.")

    # Sum insured life
    life_diff = (inp["new_life_si"] or 0) - (inp["existing_life_si"] or 0)
    life_verdict = "NEW_BETTER" if life_diff > 0 else "NEW_WORSE" if life_diff < 0 else "EQUIVALENT"
    add_dim("Life Sum Insured", inp["existing_life_si"], inp["new_life_si"], life_verdict, 0.20, f"Life SI difference: ${life_diff:,.0f}.")

    # TPD definition
    exist_rank = TPD_DEFINITION_RANK.get(inp["existing_tpd_definition"], 0)
    new_rank = TPD_DEFINITION_RANK.get(inp["new_tpd_definition"], 0)
    tpd_def_verdict = "NEW_BETTER" if new_rank > exist_rank else "NEW_WORSE" if new_rank < exist_rank else "EQUIVALENT"
    tpd_def_change = "IMPROVED" if new_rank > exist_rank else "WORSENED" if new_rank < exist_rank else "SAME"
    add_dim("TPD Definition", inp["existing_tpd_definition"], inp["new_tpd_definition"], tpd_def_verdict, 0.25, f"Definition rank: {exist_rank} → {new_rank}.")

    # Exclusions
    excl_verdict = "NEW_BETTER" if (inp["existing_has_exclusions"] and not inp["new_expected_exclusions"]) else "EQUIVALENT"
    add_dim("Exclusions", inp["existing_exclusion_details"], inp["new_expected_exclusions"], excl_verdict, 0.15, "Exclusion comparison.")

    # Loadings
    load_verdict = "NEW_BETTER" if (inp["existing_has_loadings"] and not inp["new_expected_loadings"]) else "EQUIVALENT"
    add_dim("Loadings", inp["existing_loading_details"], inp["new_expected_loadings"], load_verdict, 0.10, "Loading comparison.")

    # Flexibility
    flex_verdict = "NEW_BETTER" if inp["new_flexibility_features"] else "EQUIVALENT"
    add_dim("Flexibility", len(inp["existing_riders"]), len(inp["new_flexibility_features"]), flex_verdict, 0.05, "Feature/flexibility comparison.")

    advantage_ratio = weighted_advantage / total_weight if total_weight > 0 else 0.0
    if advantage_ratio >= COMPARISON_MATERIALLY_BETTER:
        outcome = "NEW_MATERIALLY_BETTER"
    elif advantage_ratio >= COMPARISON_MARGINALLY_BETTER:
        outcome = "NEW_MARGINALLY_BETTER"
    elif advantage_ratio <= -COMPARISON_MATERIALLY_BETTER:
        outcome = "NEW_MATERIALLY_WORSE"
    elif advantage_ratio <= -COMPARISON_MARGINALLY_BETTER:
        outcome = "NEW_MARGINALLY_WORSE"
    else:
        outcome = "EQUIVALENT"

    reasoning = [d["notes"] for d in dimensions if d["verdict"] in ("NEW_BETTER", "NEW_WORSE")]
    replacement_warnings = []
    if tpd_def_change == "WORSENED":
        replacement_warnings.append("New policy has a WORSE TPD definition — replacement would reduce cover quality.")
    if outcome in ("NEW_MARGINALLY_WORSE", "NEW_MATERIALLY_WORSE"):
        replacement_warnings.append("New policy is overall worse than existing — replacement is not recommended.")

    return {
        "has_comparison_candidate": True, "overall_outcome": outcome,
        "dimensions": dimensions, "premium_difference_annual": prem_diff,
        "sum_insured_diff_life": life_diff, "sum_insured_diff_tpd": (inp["new_tpd_si"] or 0) - (inp["existing_tpd_si"] or 0),
        "tpd_definition_change": tpd_def_change, "exclusion_change": "UNKNOWN",
        "loading_change": "UNKNOWN", "reasoning": reasoning, "replacement_warnings": replacement_warnings,
    }


# =========================================================================
# COMPLIANCE FLAGS
# =========================================================================

def _generate_compliance(inp: dict, recommendation: str, uw_risk: dict, replacement_risk: dict | None, comparison: dict) -> dict:
    advice_mode = inp["advice_mode"]
    has_replacement = recommendation in ("REPLACE_EXISTING", "SUPPLEMENT_EXISTING")

    return {
        "requires_fsg": True,
        "requires_soa": advice_mode == "PERSONAL_ADVICE",
        "requires_general_advice_warning": advice_mode == "GENERAL_ADVICE",
        "pds_required": True,
        "pds_acknowledged": None,
        "tmd_check_required": True,
        "tmd_matched": None,
        "anti_hawking_safe": True,
        "underwriting_incomplete": inp["new_underwriting_status"] not in ("ACCEPTED_STANDARD", "ACCEPTED_WITH_TERMS") if inp["has_new_candidate"] else False,
        "replacement_risk_acknowledgement_required": has_replacement,
        "cooling_off_explanation_required": inp["has_new_candidate"],
        "manual_review_required": recommendation == "REFER_TO_HUMAN",
        "compliance_notes": [
            "Full SOA required for personal advice recommendations.",
            "PDS must be provided before any new policy application.",
            *comparison.get("replacement_warnings", []),
        ],
    }


# =========================================================================
# RULE ENGINE
# =========================================================================

def _apply_rules(
    inp: dict, validation: dict, life_need: dict | None, tpd_need: dict | None,
    affordability: dict, comparison: dict, uw_risk: dict, replacement_risk: dict | None
) -> tuple[str, list[dict]]:
    rule_trace = []
    blocked = set()
    forced = None

    def trace(rule_id: str, name: str, triggered: bool, outcome: str, explanation: str, facts: dict):
        rule_trace.append({"rule_id": rule_id, "rule_name": name, "triggered": triggered, "outcome": outcome, "explanation": explanation, "supporting_facts": facts})

    def force(rec: str):
        nonlocal forced
        if forced is None:
            forced = rec

    def block(rec: str):
        blocked.add(rec)

    # R-001: Missing critical data
    if not validation["isValid"]:
        trace("R-001", "Missing Critical Data", True, "REFER_TO_HUMAN", "Critical data missing — cannot produce recommendation.", {"errors": [e["message"] for e in validation["errors"]]})
        force("REFER_TO_HUMAN")

    # R-002: Non-disclosure / pending investigations → refer
    if (inp["non_disclosure_risk"] or inp["pending_investigations"]) and forced is None:
        trace("R-002", "Refer — Non-disclosure / Pending Investigations", True, "REFER_TO_HUMAN", "Non-disclosure or pending investigations require human adviser review.", {})
        force("REFER_TO_HUMAN")

    # R-004: Block replacement — critical underwriting
    if uw_risk["overall_risk"] == "CRITICAL":
        trace("R-004", "Block Replacement — Critical Underwriting", True, "BLOCK_REPLACE", "Critical underwriting risk blocks replacement recommendation.", {})
        block("REPLACE_EXISTING")

    # R-005: Block replacement — materially worse
    if comparison["has_comparison_candidate"] and comparison["overall_outcome"] in ("NEW_MATERIALLY_WORSE", "NEW_MARGINALLY_WORSE"):
        trace("R-005", "Block Replacement — Materially Worse", True, "BLOCK_REPLACE", f"New policy is {comparison['overall_outcome']} — replacement blocked.", {})
        block("REPLACE_EXISTING")

    # R-006: Block replacement — TPD definition worsened
    if comparison.get("tpd_definition_change") == "WORSENED":
        trace("R-006", "Block Replacement — TPD Definition Worsened", True, "BLOCK_REPLACE", "New TPD definition is worse — replacement blocked.", {})
        block("REPLACE_EXISTING")

    # R-007: Block replacement — high replacement risk
    if replacement_risk and replacement_risk["overall_risk"] in ("BLOCKING",):
        trace("R-007", "Block Replacement — Blocking Risk", True, "BLOCK_REPLACE", "Replacement risk is BLOCKING.", {})
        block("REPLACE_EXISTING")

    if forced is None:
        # R-008: Purchase new — no existing cover, cover need exists
        if not inp["has_existing_policy"]:
            life_net = life_need["net_life_insurance_need"] if life_need else 0
            tpd_net = tpd_need["net_tpd_need"] if tpd_need else 0
            if life_net > 0 or tpd_net > 0:
                trace("R-008", "Purchase New — No Existing Cover", True, "PURCHASE_NEW", "No existing cover and insurance need identified.", {})
                force("PURCHASE_NEW")

    if forced is None:
        # R-009: Retain — low shortfall
        life_sl = life_need["shortfall_level"] if life_need else "NONE"
        tpd_sl = tpd_need["shortfall_level"] if tpd_need else "NONE"
        if inp["has_existing_policy"] and life_sl in ("NONE", "MINOR") and tpd_sl in ("NONE", "MINOR"):
            trace("R-009", "Retain Existing — Low Shortfall", True, "RETAIN_EXISTING", "Existing policy meets needs — shortfall is minor or nil.", {})
            force("RETAIN_EXISTING")

    if forced is None:
        # R-012: Replace if materially better
        if (inp["has_new_candidate"] and comparison["overall_outcome"] == "NEW_MATERIALLY_BETTER"
                and "REPLACE_EXISTING" not in blocked):
            trace("R-012", "Replace — Materially Better", True, "REPLACE_EXISTING", "New policy is materially better and replacement risk is acceptable.", {})
            force("REPLACE_EXISTING")

    if forced is None:
        # R-010: Supplement — significant shortfall
        life_sl2 = life_need["shortfall_level"] if life_need else "NONE"
        tpd_sl2 = tpd_need["shortfall_level"] if tpd_need else "NONE"
        if inp["has_existing_policy"] and life_sl2 in ("SIGNIFICANT", "CRITICAL") or tpd_sl2 in ("SIGNIFICANT", "CRITICAL"):
            trace("R-010", "Supplement Existing — Significant Shortfall", True, "SUPPLEMENT_EXISTING", "Existing policy has a significant coverage shortfall.", {})
            force("SUPPLEMENT_EXISTING")

    if forced is None:
        # R-011: Reduce cover — affordability
        if affordability["assessment"] in ("STRETCHED", "UNAFFORDABLE") and inp["has_existing_policy"]:
            trace("R-011", "Reduce Cover — Affordability", True, "REDUCE_COVER", "Premium is stretched/unaffordable — recommend reduction.", {})
            force("REDUCE_COVER")

    final = forced or "DEFER_NO_ACTION"
    return final, rule_trace


# =========================================================================
# REQUIRED ACTIONS
# =========================================================================

def _generate_required_actions(recommendation: str, inp: dict) -> list[dict]:
    actions = []
    if recommendation == "REFER_TO_HUMAN":
        actions.append({"action_id": "ACT-001", "priority": "CRITICAL", "action": "Escalate to an experienced human adviser before taking any further action.", "rationale": "Case complexity prevents automated recommendation."})
    if inp["pending_investigations"]:
        actions.append({"action_id": "ACT-002", "priority": "CRITICAL", "action": "Pause all insurance decisions until pending medical investigations are resolved.", "rationale": "Unknown investigation outcome creates high underwriting risk."})
    if inp["non_disclosure_risk"]:
        actions.append({"action_id": "ACT-003", "priority": "CRITICAL", "action": "Engage a specialist to review non-disclosure risk.", "rationale": "Non-disclosure can void existing and future coverage."})
    if recommendation in ("REPLACE_EXISTING", "SUPPLEMENT_EXISTING"):
        actions.append({"action_id": "ACT-004", "priority": "HIGH", "action": "Ensure new policy underwriting is fully accepted before cancelling or reducing existing cover.", "rationale": "Cancelling before new cover confirmed creates an unacceptable coverage gap."})
    if recommendation == "PURCHASE_NEW":
        actions.append({"action_id": "ACT-005", "priority": "HIGH", "action": "Obtain quotes from multiple insurers and complete full underwriting before committing.", "rationale": "Health and occupation factors may affect available terms."})
    if recommendation == "RETAIN_EXISTING" and inp["existing_superior_grandfathered"]:
        actions.append({"action_id": "ACT-006", "priority": "MEDIUM", "action": "Document the superior grandfathered terms on the existing policy in the client file.", "rationale": "Grandfathered terms must be noted so future advisers do not recommend replacement inadvertently."})
    return actions


# =========================================================================
# TOOL CLASS
# =========================================================================

_SUMMARY_MAP = {
    "PURCHASE_NEW": "Based on the identified insurance need and no existing cover, purchasing new life and/or TPD cover is recommended.",
    "RETAIN_EXISTING": "The existing policy meets current needs. No replacement or supplementation is required at this time.",
    "REPLACE_EXISTING": "The new policy is materially better and replacement risk is acceptable. Replacement is recommended subject to compliance and disclosure requirements.",
    "SUPPLEMENT_EXISTING": "The existing policy is sound but an insurance shortfall exists. Supplementing with additional cover is recommended.",
    "REDUCE_COVER": "Premium affordability is under pressure. Reducing the sum insured is recommended to manage premium costs.",
    "DEFER_NO_ACTION": "Insufficient information or conditions not suitable for a recommendation at this time.",
    "REFER_TO_HUMAN": "This case requires review by a qualified human adviser before any action is taken.",
}


class LifeTPDPolicyTool(BaseTool):
    name = "purchase_retain_life_tpd_policy"
    version = "1.0.0"
    description = (
        "Analyses a client's life and TPD insurance situation and produces a structured recommendation: "
        "PURCHASE_NEW, RETAIN_EXISTING, REPLACE_EXISTING, SUPPLEMENT_EXISTING, REDUCE_COVER, "
        "DEFER_NO_ACTION, or REFER_TO_HUMAN. Includes life need, TPD need, affordability, "
        "policy comparison, underwriting risk assessment, and compliance flags."
    )

    def get_input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "client": {"type": "object", "description": "Client demographic and financial profile"},
                "existingPolicy": {"type": "object", "description": "Existing insurance policy details"},
                "health": {"type": "object", "description": "Health and lifestyle information"},
                "goals": {"type": "object", "description": "Client goals and preferences"},
                "newPolicyCandidate": {"type": "object", "description": "Proposed replacement or new policy"},
                "adviceMode": {"type": "string", "enum": ["PERSONAL_ADVICE", "GENERAL_ADVICE", "FACTUAL_INFORMATIONAL"]},
                "evaluationDate": {"type": "string", "description": "ISO 8601 evaluation date"},
            },
        }

    def execute(self, input_data: dict) -> dict:
        # 1. Normalize
        inp = _normalize(input_data)

        # 2. Validate
        validation = _validate(input_data)

        # 3. Calculations
        life_need = _calc_life_need(inp) if validation["isValid"] else None
        tpd_need = _calc_tpd_need(inp) if validation["isValid"] else None
        affordability = _calc_affordability(inp)

        # 4. Comparison
        comparison = _compare_policies(inp)

        # 5. Underwriting risk
        uw_risk = _assess_underwriting_risk(inp)

        # 6. Replacement risk
        replacement_risk = _assess_replacement_risk(inp, uw_risk, comparison) if inp["has_existing_policy"] else None

        # 7. Rule engine
        recommendation, rule_trace = _apply_rules(
            inp, validation, life_need, tpd_need, affordability, comparison, uw_risk, replacement_risk
        )

        # 8. Compliance flags
        compliance = _generate_compliance(inp, recommendation, uw_risk, replacement_risk, comparison)

        # 9. Required actions
        required_actions = _generate_required_actions(recommendation, inp)

        reasons = [r["explanation"] for r in rule_trace if r["triggered"]]
        risks = (comparison.get("replacement_warnings", []) +
                 (replacement_risk["warnings"] if replacement_risk else []) +
                 uw_risk.get("recommendations", []))

        return {
            "validation": validation,
            "recommendation": {
                "type": recommendation,
                "advice_mode": inp["advice_mode"],
                "summary": _SUMMARY_MAP.get(recommendation, ""),
                "reasons": reasons,
                "risks": risks,
                "required_actions": required_actions,
                "life_need": life_need,
                "tpd_need": tpd_need,
                "affordability": affordability,
                "comparison": comparison if comparison["has_comparison_candidate"] else None,
                "underwriting_risk": uw_risk,
                "replacement_risk": replacement_risk,
                "compliance_flags": compliance,
                "rule_trace": rule_trace,
            },
            "missing_info_questions": validation["missingInfoQuestions"],
            "engine_version": ENGINE_VERSION,
            "evaluated_at": inp["evaluation_date"].isoformat(),
        }
