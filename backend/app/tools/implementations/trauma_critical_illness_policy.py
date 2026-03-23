"""
trauma_critical_illness_policy.py — Purchase/Retain Trauma / Critical Illness Policy tool.

Implements the regulatory rules and product mechanics for trauma/critical illness (CI)
insurance as documented in the deep research report (trauma.md):

  - Australian regulatory framework: APRA Life Prudential Standards, ASIC Corporations Act,
    Life Insurance Act 1995, Life Insurance Code of Practice (FSC, effective 1 Jul 2017)
  - Waiting period enforcement (standard 90 days / 3 months)
  - Survival period requirements (14–30 days post-diagnosis)
  - CI sum insured need analysis (income replacement, debt clearance, rehab costs)
  - Covered condition set (Life Code minimum: cancer, heart attack, stroke + extended list)
  - Advancement / partial benefit mechanics (early-stage or less-severe events)
  - Premium type comparison (stepped vs level)
  - Underwriting risk assessment (age, smoking, BMI, health history, occupation)
  - Affordability analysis (premium as % of gross income)
  - Free-look / cooling-off period (14 days statutory, 30 days industry practice)
  - Superannuation exclusion (CI not permitted in super post-July 2014, Life Code s3.2)
  - Exclusions: self-harm, suicide, pre-existing conditions, waiting period symptoms
  - Multi-claim (Double CI) rider analysis
  - APRA LICAT capital treatment (~15% of sum insured for trauma benefits)
  - Compliance flags: Life Code minimum definitions, ASIC PDS requirements

This tool is deterministic: same input → same output. No LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolValidationError

# =============================================================================
# CONSTANTS (sourced from trauma.md research report)
# =============================================================================

ENGINE_VERSION = "1.0.0"

# Waiting period before any CI benefit is payable (days) — Life Code / TAL standard
STANDARD_WAITING_PERIOD_DAYS = 90   # 3 months
MAX_REASONABLE_WAITING_PERIOD_DAYS = 180

# Survival period after diagnosis before payout (days) — TAL: 14 days; market max: 30 days
STANDARD_SURVIVAL_PERIOD_DAYS = 14
MAX_SURVIVAL_PERIOD_DAYS = 30

# Free-look / cooling-off period (days)
STATUTORY_COOLING_OFF_DAYS = 14   # Corporations Act s1019B
INDUSTRY_COOLING_OFF_DAYS = 30    # Life Code / TAL industry practice

# Grace period for premium payment before lapse
PREMIUM_GRACE_PERIOD_DAYS = 30

# Contestability window (years) — insurer can void for non-disclosure
CONTESTABILITY_PERIOD_YEARS = 2

# Income replacement multiplier for CI sum insured need calculation
# Represents years of income needed to cover treatment, rehab, and recovery
CI_INCOME_REPLACEMENT_YEARS = 3

# Minimum rehabilitation / medical expense buffer
MIN_REHAB_ALLOWANCE_AUD = 50_000

# APRA LICAT risk factor for trauma (lump-sum) benefits
LICAT_TRAUMA_CAPITAL_FACTOR = 0.15  # 15% of sum insured

# Affordability bands — premium as a fraction of gross annual income
AFFORDABILITY_BANDS = {
    "COMFORTABLE": 0.02,   # ≤ 2% of gross income
    "MANAGEABLE":  0.04,   # ≤ 4%
    "STRETCHED":   0.07,   # ≤ 7%
    # > 7% → UNAFFORDABLE
}

# Shortfall severity thresholds (AUD gap between need and existing cover)
SHORTFALL_THRESHOLDS = {
    "NONE":         0,
    "MINOR":        20_000,
    "MODERATE":     75_000,
    "SIGNIFICANT":  200_000,
    # > 200_000 → CRITICAL
}

# Life Code minimum CI covered conditions
LIFE_CODE_MINIMUM_CONDITIONS = {
    "INVASIVE_CANCER",
    "HEART_ATTACK",
    "STROKE",
}

# Extended standard CI covered conditions (typical retail policy list)
STANDARD_CI_CONDITIONS = {
    "INVASIVE_CANCER",
    "HEART_ATTACK",
    "STROKE",
    "CORONARY_ARTERY_BYPASS",
    "HEART_VALVE_SURGERY",
    "KIDNEY_FAILURE",
    "MAJOR_ORGAN_TRANSPLANT",
    "BLINDNESS",
    "DEAFNESS",
    "PARALYSIS",
    "MOTOR_NEURONE_DISEASE",
    "MULTIPLE_SCLEROSIS",
    "ALZHEIMERS_DISEASE",
    "PARKINSONS_DISEASE",
    "AORTA_SURGERY",
    "SEVERE_BURNS",
    "LOSS_OF_LIMBS",
    "BENIGN_BRAIN_TUMOUR",
    "APLASTIC_ANAEMIA",
    "COMA",
    "ENCEPHALITIS",
    "MENINGITIS",
}

# Conditions that attract a partial/advancement benefit (less-severe variants)
ADVANCEMENT_BENEFIT_CONDITIONS = {
    "EARLY_STAGE_CANCER",           # non-invasive / CIS
    "ANGIOPLASTY",                  # single-vessel, non-urgent
    "PARTIAL_BLINDNESS",
    "PARTIAL_DEAFNESS",
    "CARCINOMA_IN_SITU",
    "EARLY_PROSTATE_CANCER",
    "LOW_GRADE_PROSTATE_CANCER",
    "EARLY_MELANOMA",
}

# Occupation risk class → underwriting risk impact on CI
OCCUPATION_RISK_MAP = {
    "CLASS_1_WHITE_COLLAR":    "LOW",
    "CLASS_2_LIGHT_BLUE":      "MEDIUM",
    "CLASS_3_BLUE_COLLAR":     "HIGH",
    "CLASS_4_HAZARDOUS":       "CRITICAL",
    "UNKNOWN":                 "MEDIUM",
}

# Age bands for CI incidence multiplier (relative to 40-year-old baseline = 1.0)
# Sources: AIHW, AIA crisis recovery brochure, actuarial industry norms
AGE_INCIDENCE_MULTIPLIER = {
    (18, 29): 0.25,
    (30, 39): 0.55,
    (40, 49): 1.00,   # baseline
    (50, 59): 2.10,
    (60, 69): 4.00,
    (70, 99): 7.50,
}

# Smoker loading on CI premium (fraction)
SMOKER_PREMIUM_LOADING = 0.75   # 75% uplift

# High BMI (obese) loading
HIGH_BMI_PREMIUM_LOADING = 0.20

# BMI obesity threshold
BMI_OBESITY_THRESHOLD = 30.0

# Stepped vs level premium crossover age (approximate)
LEVEL_PREMIUM_CROSSOVER_AGE = 45

# Maximum entry age for a new CI policy
MAX_ENTRY_AGE = 60

# Maximum policy expiry age
MAX_POLICY_EXPIRY_AGE = 75

# Minimum CI sum insured (AUD)
MIN_SUM_INSURED = 50_000

# Maximum CI sum insured without full medical evidence (AUD)
NO_EXAM_LIMIT = 500_000


# =============================================================================
# HELPERS
# =============================================================================

def _safe_parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d
    except (ValueError, TypeError):
        return None


def _age_from_dob(dob: datetime) -> int:
    today = datetime.now(timezone.utc)
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def _get_age_incidence_multiplier(age: int) -> float:
    for (lo, hi), mult in AGE_INCIDENCE_MULTIPLIER.items():
        if lo <= age <= hi:
            return mult
    return 1.0


def _bmi(height_m: float, weight_kg: float) -> float | None:
    if height_m and weight_kg and height_m > 0:
        return weight_kg / (height_m ** 2)
    return None


def _classify_shortfall(gap_aud: float) -> str:
    if gap_aud <= SHORTFALL_THRESHOLDS["NONE"]:
        return "NONE"
    if gap_aud <= SHORTFALL_THRESHOLDS["MINOR"]:
        return "MINOR"
    if gap_aud <= SHORTFALL_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    if gap_aud <= SHORTFALL_THRESHOLDS["SIGNIFICANT"]:
        return "SIGNIFICANT"
    return "CRITICAL"


def _missing_conditions(covered: set[str]) -> list[str]:
    """Return Life Code minimum conditions that are missing from covered set."""
    return sorted(LIFE_CODE_MINIMUM_CONDITIONS - covered)


# =============================================================================
# CALCULATION ENGINE
# =============================================================================

def _calc_ci_need(
    annual_gross_income: float | None,
    total_liabilities: float,
    liquid_assets: float,
    monthly_expenses: float,
) -> dict:
    """
    Estimate the required CI sum insured.

    Method (from trauma.md recommendations):
      1. Medical / rehab allowance: max(MIN_REHAB_ALLOWANCE, income × 0.5)
      2. Income replacement during treatment/recovery: income × CI_INCOME_REPLACEMENT_YEARS
      3. Debt clearance: total liabilities (mortgage, personal loans)
      4. Emergency liquidity buffer: 6 months of expenses
      5. Less existing liquid assets
    """
    if not annual_gross_income or annual_gross_income <= 0:
        # Return an estimate based only on liabilities
        raw_need = max(
            MIN_REHAB_ALLOWANCE_AUD,
            total_liabilities,
        )
        return {
            "calculated_need_aud": round(raw_need),
            "components": {
                "rehab_allowance_aud": MIN_REHAB_ALLOWANCE_AUD,
                "income_replacement_aud": 0,
                "debt_clearance_aud": round(total_liabilities),
                "liquidity_buffer_aud": 0,
            },
            "income_known": False,
            "note": "Income not provided; need estimated from liabilities and minimum rehab buffer only.",
        }

    rehab = max(MIN_REHAB_ALLOWANCE_AUD, annual_gross_income * 0.50)
    income_replacement = annual_gross_income * CI_INCOME_REPLACEMENT_YEARS
    debt = max(0.0, total_liabilities)
    liquidity_buffer = monthly_expenses * 6 if monthly_expenses > 0 else annual_gross_income * 0.25
    gross_need = rehab + income_replacement + debt + liquidity_buffer
    net_need = max(0.0, gross_need - liquid_assets)

    return {
        "calculated_need_aud": round(net_need),
        "gross_need_aud": round(gross_need),
        "components": {
            "rehab_allowance_aud": round(rehab),
            "income_replacement_aud": round(income_replacement),
            "debt_clearance_aud": round(debt),
            "liquidity_buffer_aud": round(liquidity_buffer),
        },
        "less_liquid_assets_aud": round(liquid_assets),
        "income_known": True,
    }


def _calc_waiting_period_analysis(
    current_waiting_days: int,
    proposed_waiting_days: int | None,
) -> dict:
    """
    Evaluate waiting period compliance and impact.

    Australian standard: 90-day waiting period before CI benefit is payable.
    Shorter waiting increases risk of adverse selection. Longer periods
    (>90 days) are uncommon in Australian CI and indicate a non-standard policy.
    """
    current_compliant = current_waiting_days >= STANDARD_WAITING_PERIOD_DAYS
    flags = []

    if current_waiting_days < STANDARD_WAITING_PERIOD_DAYS:
        flags.append({
            "code": "WAITING_PERIOD_BELOW_STANDARD",
            "severity": "WARNING",
            "message": (
                f"Current waiting period ({current_waiting_days} days) is below the "
                f"Australian standard of {STANDARD_WAITING_PERIOD_DAYS} days. "
                "This may indicate a non-standard or older policy wording."
            ),
        })
    if current_waiting_days > MAX_REASONABLE_WAITING_PERIOD_DAYS:
        flags.append({
            "code": "WAITING_PERIOD_EXCESSIVE",
            "severity": "WARNING",
            "message": (
                f"Waiting period of {current_waiting_days} days exceeds the typical "
                f"maximum of {MAX_REASONABLE_WAITING_PERIOD_DAYS} days and may "
                "significantly limit claim eligibility."
            ),
        })

    result = {
        "current_waiting_days": current_waiting_days,
        "standard_waiting_days": STANDARD_WAITING_PERIOD_DAYS,
        "current_compliant_with_standard": current_compliant,
        "flags": flags,
    }

    if proposed_waiting_days is not None:
        proposed_compliant = proposed_waiting_days >= STANDARD_WAITING_PERIOD_DAYS
        result["proposed_waiting_days"] = proposed_waiting_days
        result["proposed_compliant_with_standard"] = proposed_compliant
        if proposed_waiting_days < current_waiting_days:
            result["change"] = "SHORTER_PROPOSED"
        elif proposed_waiting_days > current_waiting_days:
            result["change"] = "LONGER_PROPOSED"
        else:
            result["change"] = "SAME"

    return result


def _calc_survival_period_analysis(
    current_survival_days: int,
    proposed_survival_days: int | None,
) -> dict:
    """
    Evaluate survival period (post-diagnosis days required before payout).

    14-day survival is the TAL/industry standard.
    30-day survival is common in some policies but creates a harder bar for
    rapidly progressing illnesses (e.g. aggressive cancer).
    """
    flags = []

    if current_survival_days > MAX_SURVIVAL_PERIOD_DAYS:
        flags.append({
            "code": "SURVIVAL_PERIOD_EXCESSIVE",
            "severity": "WARNING",
            "message": (
                f"Survival period of {current_survival_days} days exceeds the "
                f"industry maximum of {MAX_SURVIVAL_PERIOD_DAYS} days and may "
                "preclude claims for acute critical events."
            ),
        })

    result = {
        "current_survival_days": current_survival_days,
        "standard_survival_days": STANDARD_SURVIVAL_PERIOD_DAYS,
        "maximum_recommended_days": MAX_SURVIVAL_PERIOD_DAYS,
        "flags": flags,
    }

    if proposed_survival_days is not None:
        result["proposed_survival_days"] = proposed_survival_days
        if proposed_survival_days < current_survival_days:
            result["change"] = "SHORTER_PROPOSED"
            result["change_note"] = "Shorter survival period improves claim eligibility for acute events."
        elif proposed_survival_days > current_survival_days:
            result["change"] = "LONGER_PROPOSED"
            result["change_note"] = "Longer survival period reduces claim eligibility — evaluate carefully."
        else:
            result["change"] = "SAME"

    return result


def _calc_coverage_gap(
    existing_sum_insured: float,
    calculated_need: float,
) -> dict:
    """
    Compare existing CI sum insured against the calculated need.
    """
    gap = max(0.0, calculated_need - existing_sum_insured)
    coverage_pct = (existing_sum_insured / calculated_need * 100) if calculated_need > 0 else 0.0
    shortfall_label = _classify_shortfall(gap)

    return {
        "calculated_need_aud": round(calculated_need),
        "existing_sum_insured_aud": round(existing_sum_insured),
        "gap_aud": round(gap),
        "coverage_percentage": round(coverage_pct, 1),
        "shortfall_severity": shortfall_label,
    }


def _calc_affordability(
    annual_premium: float | None,
    annual_gross_income: float | None,
) -> dict:
    """
    Assess premium affordability as a fraction of gross annual income.
    """
    if not annual_premium or annual_premium <= 0:
        return {
            "annual_premium_aud": 0,
            "premium_to_income_ratio": None,
            "band": "UNKNOWN",
            "note": "Premium not provided; affordability cannot be assessed.",
        }

    if not annual_gross_income or annual_gross_income <= 0:
        return {
            "annual_premium_aud": round(annual_premium),
            "premium_to_income_ratio": None,
            "band": "UNKNOWN",
            "note": "Gross income not provided; affordability cannot be assessed.",
        }

    ratio = annual_premium / annual_gross_income
    if ratio <= AFFORDABILITY_BANDS["COMFORTABLE"]:
        band = "COMFORTABLE"
    elif ratio <= AFFORDABILITY_BANDS["MANAGEABLE"]:
        band = "MANAGEABLE"
    elif ratio <= AFFORDABILITY_BANDS["STRETCHED"]:
        band = "STRETCHED"
    else:
        band = "UNAFFORDABLE"

    return {
        "annual_premium_aud": round(annual_premium),
        "annual_gross_income_aud": round(annual_gross_income),
        "premium_to_income_ratio": round(ratio, 4),
        "premium_to_income_pct": round(ratio * 100, 2),
        "band": band,
        "band_thresholds": {
            "comfortable_max_pct": AFFORDABILITY_BANDS["COMFORTABLE"] * 100,
            "manageable_max_pct": AFFORDABILITY_BANDS["MANAGEABLE"] * 100,
            "stretched_max_pct": AFFORDABILITY_BANDS["STRETCHED"] * 100,
        },
    }


def _assess_underwriting_risk(
    age: int | None,
    is_smoker: bool,
    occupation_class: str,
    health_conditions: list[str],
    height_m: float | None,
    weight_kg: float | None,
) -> dict:
    """
    Assess CI underwriting risk level and loading factors.

    Risk drivers (trauma.md):
    - Age (incidence rises sharply after 40)
    - Smoking status (≈75% premium loading)
    - Occupation class
    - Pre-existing health conditions (exclusions or loadings)
    - BMI (obesity loading ~20%)
    """
    risk_factors = []
    premium_loadings: list[dict] = []
    risk_level = "LOW"

    # Age risk
    if age is not None:
        incidence_mult = _get_age_incidence_multiplier(age)
        age_risk = "LOW" if incidence_mult < 0.6 else ("MEDIUM" if incidence_mult < 1.5 else "HIGH")
        risk_factors.append({
            "factor": "AGE",
            "value": age,
            "incidence_multiplier": incidence_mult,
            "risk": age_risk,
        })
        if age >= 50:
            risk_level = "HIGH"
        elif age >= 40 and risk_level == "LOW":
            risk_level = "MEDIUM"

        if age > MAX_ENTRY_AGE:
            risk_factors.append({
                "factor": "AGE_OVER_ENTRY_LIMIT",
                "value": age,
                "risk": "CRITICAL",
                "note": f"Age {age} exceeds maximum entry age of {MAX_ENTRY_AGE}; new CI policy not available.",
            })
            risk_level = "CRITICAL"

    # Smoking
    if is_smoker:
        risk_factors.append({
            "factor": "SMOKER",
            "value": True,
            "risk": "HIGH",
            "note": "Smoker status significantly elevates CI incidence for cancer and cardiovascular events.",
        })
        premium_loadings.append({
            "reason": "SMOKER",
            "loading_pct": round(SMOKER_PREMIUM_LOADING * 100),
        })
        if risk_level not in ("CRITICAL",):
            risk_level = "HIGH"

    # Occupation
    occ_risk = OCCUPATION_RISK_MAP.get(occupation_class, "MEDIUM")
    risk_factors.append({
        "factor": "OCCUPATION_CLASS",
        "value": occupation_class,
        "risk": occ_risk,
    })
    if occ_risk == "CRITICAL":
        risk_level = "CRITICAL"
    elif occ_risk == "HIGH" and risk_level in ("LOW", "MEDIUM"):
        risk_level = "HIGH"

    # BMI
    bmi_val = _bmi(height_m, weight_kg) if height_m and weight_kg else None
    if bmi_val is not None:
        bmi_risk = "HIGH" if bmi_val >= BMI_OBESITY_THRESHOLD else "LOW"
        risk_factors.append({
            "factor": "BMI",
            "value": round(bmi_val, 1),
            "risk": bmi_risk,
        })
        if bmi_val >= BMI_OBESITY_THRESHOLD:
            premium_loadings.append({
                "reason": "HIGH_BMI",
                "loading_pct": round(HIGH_BMI_PREMIUM_LOADING * 100),
            })
            if risk_level == "LOW":
                risk_level = "MEDIUM"

    # Health conditions
    ci_relevant_conditions = []
    for cond in (health_conditions or []):
        cond_upper = cond.upper().replace(" ", "_").replace("-", "_")
        # If the pre-existing condition matches or contains a covered CI condition name,
        # it is likely to lead to an exclusion or loading
        is_ci_related = any(
            ci_cond_fragment in cond_upper
            for ci_cond_fragment in [
                "CANCER", "HEART", "STROKE", "CARDIAC", "TUMOUR", "TUMOR",
                "ORGAN", "KIDNEY", "LIVER", "MULTIPLE_SCLEROSIS", "PARKINSON",
                "ALZHEIMER", "MOTOR_NEURONE", "PARALYSIS", "BLINDNESS",
                "DEAFNESS", "TRANSPLANT",
            ]
        )
        if is_ci_related:
            ci_relevant_conditions.append(cond)
            risk_factors.append({
                "factor": "PRE_EXISTING_CI_CONDITION",
                "value": cond,
                "risk": "HIGH",
                "note": f"Pre-existing condition '{cond}' may result in a specific exclusion or "
                        "premium loading under the CI policy.",
            })
            if risk_level in ("LOW", "MEDIUM"):
                risk_level = "HIGH"

    # Medical evidence required
    requires_medical_evidence = (age is not None and age >= 45) or is_smoker or len(ci_relevant_conditions) > 0

    return {
        "overall_risk_level": risk_level,
        "risk_factors": risk_factors,
        "premium_loadings": premium_loadings,
        "ci_relevant_pre_existing_conditions": ci_relevant_conditions,
        "requires_medical_evidence": requires_medical_evidence,
        "contestability_period_years": CONTESTABILITY_PERIOD_YEARS,
        "note": (
            "Premium loadings are indicative only. Insurer underwriting guidelines apply. "
            "Conditions pre-dating the policy may be excluded under the duty of disclosure "
            "(Insurance Contracts Act 1984 s21)."
        ),
    }


def _eval_covered_conditions(
    covered_conditions: list[str],
) -> dict:
    """
    Check covered conditions against Life Code minimum definitions and
    the extended standard CI condition list.
    """
    covered_set = {c.upper().replace(" ", "_").replace("-", "_") for c in (covered_conditions or [])}
    missing_minimum = _missing_conditions(covered_set)
    standard_coverage = STANDARD_CI_CONDITIONS - covered_set
    advancement_supported = bool(ADVANCEMENT_BENEFIT_CONDITIONS & covered_set)

    flags = []
    if missing_minimum:
        flags.append({
            "code": "MISSING_LIFE_CODE_MINIMUM_CONDITIONS",
            "severity": "CRITICAL",
            "message": (
                f"Policy does not cover Life Code minimum conditions: {', '.join(missing_minimum)}. "
                "Under the FSC Life Insurance Code of Practice (2017), all CI policies must meet "
                "minimum definitions for cancer, heart attack, and stroke."
            ),
        })
    if standard_coverage:
        flags.append({
            "code": "STANDARD_CONDITIONS_NOT_COVERED",
            "severity": "INFO",
            "message": (
                f"{len(standard_coverage)} standard CI conditions not explicitly listed: "
                f"{', '.join(sorted(standard_coverage))}. Confirm with insurer whether any "
                "are covered under alternative wordings."
            ),
        })

    return {
        "covered_conditions": sorted(covered_set),
        "life_code_minimum_met": len(missing_minimum) == 0,
        "missing_minimum_conditions": missing_minimum,
        "standard_conditions_not_covered": sorted(standard_coverage),
        "advancement_benefit_supported": advancement_supported,
        "total_covered_count": len(covered_set),
        "flags": flags,
    }


def _eval_super_eligibility() -> dict:
    """
    CI insurance cannot be held inside a superannuation fund under Australian law.

    Source: FSC Life Insurance Code of Practice s3.2 (effective 1 Jul 2014);
    SIS Act — CI is not a permissible insurance benefit inside super.
    MoneySmart confirms: super funds no longer issue new trauma cover (post-July 2014).
    """
    return {
        "permitted_in_super": False,
        "regulatory_basis": (
            "CI/Trauma insurance has been prohibited inside Australian superannuation funds "
            "for new business since 1 July 2014 (FSC Life Insurance Code of Practice s3.2; "
            "SIS Act). CI must be held as a standalone retail policy outside super."
        ),
        "action": (
            "Confirm policy is held outside superannuation. If client has legacy CI inside "
            "super (pre-July 2014), review whether continuation elections have been lodged."
        ),
    }


def _eval_cooling_off() -> dict:
    """
    Cooling-off / free-look period entitlements.
    """
    return {
        "statutory_cooling_off_days": STATUTORY_COOLING_OFF_DAYS,
        "industry_practice_days": INDUSTRY_COOLING_OFF_DAYS,
        "regulatory_basis": (
            f"Corporations Act 2001 s1019B provides a {STATUTORY_COOLING_OFF_DAYS}-day "
            f"free-look period for life insurance. Industry practice (TAL, AIA, etc.) "
            f"extends this to {INDUSTRY_COOLING_OFF_DAYS} days with a full premium refund."
        ),
        "note": (
            "Cooling-off rights reset on policy reinstatement. During cooling-off, "
            "no claims are payable if the policy is cancelled."
        ),
    }


def _eval_premium_type(
    premium_type: str | None,
    age: int | None,
) -> dict:
    """
    Evaluate stepped vs level premium structure and suitability.
    """
    premium_type = (premium_type or "UNKNOWN").upper()
    flags = []

    recommendation = None
    if age is not None:
        if age < LEVEL_PREMIUM_CROSSOVER_AGE and premium_type == "LEVEL":
            recommendation = "STEPPED_MAY_BE_CHEAPER_SHORT_TERM"
            flags.append({
                "code": "LEVEL_PREMIUM_YOUNG_CLIENT",
                "severity": "INFO",
                "message": (
                    f"At age {age}, stepped premiums are typically cheaper in the short term. "
                    f"Level premiums become cost-effective around age {LEVEL_PREMIUM_CROSSOVER_AGE}+ "
                    "and are preferable if long-term retention is the goal."
                ),
            })
        elif age >= LEVEL_PREMIUM_CROSSOVER_AGE and premium_type == "STEPPED":
            recommendation = "LEVEL_MAY_BE_MORE_COST_EFFECTIVE_LONG_TERM"
            flags.append({
                "code": "STEPPED_PREMIUM_OLDER_CLIENT",
                "severity": "INFO",
                "message": (
                    f"At age {age}, stepped premiums increase sharply with each birthday. "
                    "Consider whether a level premium option provides better long-term value "
                    "and reduces lapse risk due to premium shock."
                ),
            })

    return {
        "current_premium_type": premium_type,
        "stepped_description": "Premium increases with age; cheaper initially, more expensive long-term.",
        "level_description": "Premium remains stable (or grows slowly); more expensive initially.",
        "approximate_crossover_age": LEVEL_PREMIUM_CROSSOVER_AGE,
        "recommendation": recommendation,
        "flags": flags,
    }


def _generate_recommendation(
    has_existing_policy: bool,
    shortfall_severity: str,
    waiting_period_compliant: bool,
    survival_period_ok: bool,
    life_code_minimum_met: bool,
    affordability_band: str,
    underwriting_risk_level: str,
    client_age: int | None,
    wants_replacement: bool | None,
    wants_retention: bool | None,
) -> dict:
    """
    Generate a structured recommendation for the CI policy.

    Decision logic (aligned with trauma.md recommendations):
      1. If no existing policy → PURCHASE_NEW (unless CRITICAL underwriting risk)
      2. If existing policy with NONE/MINOR shortfall AND waiting/survival OK → RETAIN_EXISTING
      3. If existing policy is deficient (missing Life Code minimums, waiting > std, survival > 30d) → REPLACE_WITH_BETTER
      4. If MODERATE/SIGNIFICANT shortfall → SUPPLEMENT or REPLACE_WITH_BETTER
      5. If CRITICAL shortfall → REPLACE_WITH_BETTER (urgently)
      6. If underwriting risk is CRITICAL (over max entry age) → CANNOT_OBTAIN_NEW_COVER
    """
    if underwriting_risk_level == "CRITICAL" and client_age and client_age > MAX_ENTRY_AGE:
        return {
            "type": "CANNOT_OBTAIN_NEW_COVER",
            "summary": (
                f"Client is age {client_age}, which exceeds the maximum entry age of "
                f"{MAX_ENTRY_AGE} for a new CI policy. No new CI policy can be issued. "
                "Retention of any existing policy is strongly recommended."
            ),
            "reasons": [
                f"Age {client_age} exceeds maximum new-business entry age ({MAX_ENTRY_AGE}).",
            ],
            "risks": [
                "Existing policy may lapse if premiums are not maintained.",
            ],
            "actions": [
                "Ensure existing policy premiums are maintained.",
                "Do not cancel or surrender any existing CI cover.",
                "Review whether any existing policy has guaranteed insurability for sum insured increases.",
            ],
            "urgency": "HIGH",
        }

    if not has_existing_policy:
        rec_type = "PURCHASE_NEW"
        reasons = [
            "Client has no existing CI coverage.",
            f"Calculated CI need indicates a {'significant financial gap' if shortfall_severity in ('SIGNIFICANT','CRITICAL') else 'coverage shortfall'} without protection.",
        ]
        risks = [
            "Without CI cover, a critical illness event could result in significant financial hardship.",
            "Medical, rehabilitation, and income replacement costs can easily exceed $200,000.",
        ]
        actions = [
            "Obtain quotes from multiple insurers (TAL, AIA, Zurich, etc.).",
            "Ensure policy covers all Life Code minimum conditions (cancer, heart attack, stroke).",
            f"Confirm 90-day waiting period and {STANDARD_SURVIVAL_PERIOD_DAYS}-day survival period in policy wording.",
            "Consider advancement benefit for partial-severity events.",
            f"Utilise {INDUSTRY_COOLING_OFF_DAYS}-day free-look period to review final policy documents.",
        ]
        if affordability_band in ("STRETCHED", "UNAFFORDABLE"):
            risks.append("Premium affordability is a concern; consider a smaller sum insured or stepped premium.")
            actions.append("Review sum insured to balance coverage need with premium affordability.")

        return {
            "type": rec_type,
            "summary": (
                "Client has no existing CI/Trauma policy. A new CI policy should be arranged "
                "to protect against the financial impact of a critical illness event."
            ),
            "reasons": reasons,
            "risks": risks,
            "actions": actions,
            "urgency": "HIGH" if shortfall_severity in ("SIGNIFICANT", "CRITICAL") else "MEDIUM",
        }

    # Existing policy path
    deficiencies = []
    if not life_code_minimum_met:
        deficiencies.append("Does not meet Life Code minimum condition definitions.")
    if not waiting_period_compliant:
        deficiencies.append(f"Waiting period is below the standard {STANDARD_WAITING_PERIOD_DAYS} days.")
    if not survival_period_ok:
        deficiencies.append(f"Survival period exceeds the recommended maximum of {MAX_SURVIVAL_PERIOD_DAYS} days.")

    if shortfall_severity in ("CRITICAL", "SIGNIFICANT") or deficiencies:
        rec_type = "REPLACE_WITH_BETTER"
        if wants_retention:
            rec_type = "SUPPLEMENT_EXISTING"

        reasons = [
            f"Shortfall severity: {shortfall_severity}.",
        ] + deficiencies
        risks = [
            "Existing CI cover is materially inadequate relative to the client's financial exposure.",
        ]
        if deficiencies:
            risks.append(
                "Policy deficiencies may result in claims being declined or reduced under "
                "current wording."
            )
        actions = [
            "Obtain comparative quotes for a replacement or supplementary CI policy.",
            "Ensure replacement policy meets Life Code minimum condition definitions.",
            "Do not cancel existing policy before replacement cover is confirmed and in-force.",
            "Consider guaranteed insurability options to avoid re-underwriting at replacement.",
        ]
        return {
            "type": rec_type,
            "summary": (
                f"Existing CI policy has a {shortfall_severity.lower()} shortfall "
                + (f"and the following deficiencies: {'; '.join(deficiencies)}. " if deficiencies else ". ")
                + "Replacement or supplementation is recommended."
            ),
            "reasons": reasons,
            "risks": risks,
            "actions": actions,
            "urgency": "HIGH" if shortfall_severity == "CRITICAL" else "MEDIUM",
        }

    if shortfall_severity == "MODERATE":
        rec_type = "SUPPLEMENT_EXISTING"
        if wants_replacement:
            rec_type = "REPLACE_WITH_BETTER"
        return {
            "type": rec_type,
            "summary": (
                "Existing CI policy provides moderate but not complete coverage. "
                "Supplementing with additional cover is recommended to close the gap."
            ),
            "reasons": [
                "Coverage gap exists between existing sum insured and calculated need.",
                "No critical policy deficiencies identified.",
            ],
            "risks": [
                "Partial underinsurance leaves the client exposed if a major CI event occurs.",
            ],
            "actions": [
                "Explore topping up the existing sum insured if the insurer allows it.",
                "Alternatively, consider a supplementary CI policy with a separate insurer.",
                "Reassess need annually or after major life events (mortgage, family change).",
            ],
            "urgency": "MEDIUM",
        }

    # NONE or MINOR shortfall, policy is compliant
    return {
        "type": "RETAIN_EXISTING",
        "summary": (
            "Existing CI policy appears adequate for the client's current needs. "
            "Retention is recommended subject to annual review."
        ),
        "reasons": [
            "Sum insured is within an acceptable range of the calculated CI need.",
            "Policy meets Life Code minimum condition definitions.",
            "Waiting and survival periods are within standard parameters.",
        ],
        "risks": [
            "Sum insured may erode in real terms over time if not indexed.",
            "Life events (new mortgage, family changes) may increase the CI need.",
        ],
        "actions": [
            "Review CI cover annually or after major life events.",
            "Confirm whether indexation is included or can be added to maintain real value.",
            "Ensure the policy includes an advancement benefit for early-stage events.",
        ],
        "urgency": "LOW",
    }


def _build_missing_info_questions(
    annual_gross_income: float | None,
    existing_sum_insured: float | None,
    covered_conditions: list[str],
    age: int | None,
    annual_premium: float | None,
    has_existing_policy: bool | None,
) -> dict:
    """
    Return blocking and optional questions for incomplete inputs.
    """
    blocking = []
    optional = []

    if has_existing_policy is None:
        blocking.append({
            "field": "existingPolicy.hasExistingPolicy",
            "question": "Does the client currently have a CI/Trauma insurance policy?",
        })

    if age is None:
        blocking.append({
            "field": "client.age",
            "question": "What is the client's age? (Required to assess underwriting eligibility and premium.)",
        })

    if annual_gross_income is None or annual_gross_income <= 0:
        blocking.append({
            "field": "client.annualGrossIncome",
            "question": "What is the client's annual gross income (AUD)? (Required to calculate CI need.)",
        })

    if has_existing_policy and (existing_sum_insured is None or existing_sum_insured <= 0):
        blocking.append({
            "field": "existingPolicy.sumInsured",
            "question": "What is the existing CI policy's sum insured (AUD)?",
        })

    if not covered_conditions:
        optional.append({
            "field": "existingPolicy.coveredConditions",
            "question": "What conditions does the existing CI policy cover? (Needed to check Life Code compliance.)",
        })

    if annual_premium is None:
        optional.append({
            "field": "existingPolicy.annualPremium",
            "question": "What is the current annual CI premium (AUD)?",
        })

    return {
        "blocking_questions": blocking,
        "optional_questions": optional,
        "total_blocking": len(blocking),
        "total_optional": len(optional),
        "analysis_completeness": "PARTIAL" if blocking else "SUFFICIENT",
    }


# =============================================================================
# TOOL IMPLEMENTATION
# =============================================================================

class TraumaCIPolicyTool(BaseTool):
    """
    Trauma / Critical Illness (CI) insurance advisory tool.

    Covers:
    - CI sum insured need analysis
    - Waiting and survival period compliance (Life Code / APRA standards)
    - Covered condition audit (Life Code minimum: cancer, heart attack, stroke)
    - Advancement/partial benefit evaluation
    - Premium affordability (stepped vs level)
    - Underwriting risk assessment
    - Superannuation exclusion confirmation
    - Cooling-off / free-look entitlements
    - Purchase / retain / replace / supplement recommendation
    """

    name = "purchase_retain_trauma_ci_policy"
    version = ENGINE_VERSION
    description = (
        "Advise on purchasing, retaining, replacing, or supplementing a "
        "Trauma / Critical Illness (CI) insurance policy. Analyses CI need, "
        "Life Code condition compliance, waiting/survival periods, affordability, "
        "underwriting risk, and generates a structured recommendation."
    )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "client": {
                    "type": "object",
                    "properties": {
                        "age": {"type": "integer", "minimum": 1},
                        "dateOfBirth": {"type": "string", "description": "ISO date YYYY-MM-DD"},
                        "annualGrossIncome": {"type": "number"},
                        "isSmoker": {"type": "boolean"},
                        "occupationClass": {
                            "type": "string",
                            "enum": [
                                "CLASS_1_WHITE_COLLAR", "CLASS_2_LIGHT_BLUE",
                                "CLASS_3_BLUE_COLLAR", "CLASS_4_HAZARDOUS", "UNKNOWN",
                            ],
                        },
                        "occupation": {"type": "string"},
                    },
                },
                "existingPolicy": {
                    "type": "object",
                    "properties": {
                        "hasExistingPolicy": {"type": "boolean"},
                        "insurerName": {"type": "string"},
                        "sumInsured": {"type": "number"},
                        "annualPremium": {"type": "number"},
                        "waitingPeriodDays": {"type": "integer"},
                        "survivalPeriodDays": {"type": "integer"},
                        "premiumType": {
                            "type": "string",
                            "enum": ["STEPPED", "LEVEL", "UNKNOWN"],
                        },
                        "coveredConditions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "hasAdvancementBenefit": {"type": "boolean"},
                        "hasChildRider": {"type": "boolean"},
                        "hasFemaleRider": {"type": "boolean"},
                        "hasMultiClaimRider": {"type": "boolean"},
                    },
                },
                "proposedPolicy": {
                    "type": "object",
                    "properties": {
                        "insurerName": {"type": "string"},
                        "sumInsured": {"type": "number"},
                        "annualPremium": {"type": "number"},
                        "waitingPeriodDays": {"type": "integer"},
                        "survivalPeriodDays": {"type": "integer"},
                        "premiumType": {
                            "type": "string",
                            "enum": ["STEPPED", "LEVEL", "UNKNOWN"],
                        },
                        "coveredConditions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "hasAdvancementBenefit": {"type": "boolean"},
                    },
                },
                "health": {
                    "type": "object",
                    "properties": {
                        "height": {"type": "number", "description": "metres, e.g. 1.75"},
                        "weight": {"type": "number", "description": "kg"},
                        "conditions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Pre-existing medical conditions",
                        },
                    },
                },
                "financialPosition": {
                    "type": "object",
                    "properties": {
                        "totalLiabilities": {"type": "number"},
                        "liquidAssets": {"type": "number"},
                        "mortgageBalance": {"type": "number"},
                        "monthlyExpenses": {"type": "number"},
                    },
                },
                "goals": {
                    "type": "object",
                    "properties": {
                        "wantsReplacement": {"type": "boolean"},
                        "wantsRetention": {"type": "boolean"},
                        "affordabilityIsConcern": {"type": "boolean"},
                        "wantsAdvancementBenefit": {"type": "boolean"},
                        "wantsMultiClaimRider": {"type": "boolean"},
                    },
                },
            },
        }

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
        # ------------------------------------------------------------------
        # 1. Extract inputs
        # ------------------------------------------------------------------
        client = input_data.get("client") or {}
        existing = input_data.get("existingPolicy") or {}
        proposed = input_data.get("proposedPolicy") or {}
        health = input_data.get("health") or {}
        financial = input_data.get("financialPosition") or {}
        goals = input_data.get("goals") or {}

        # Client fields
        age: int | None = client.get("age")
        dob_str: str | None = client.get("dateOfBirth")
        if age is None and dob_str:
            dob = _safe_parse_date(dob_str)
            if dob:
                age = _age_from_dob(dob)
        annual_gross_income: float | None = client.get("annualGrossIncome")
        is_smoker: bool = bool(client.get("isSmoker", False))
        occupation_class: str = client.get("occupationClass", "UNKNOWN")

        # Existing policy fields
        has_existing: bool | None = existing.get("hasExistingPolicy")
        existing_sum_insured: float = float(existing.get("sumInsured") or 0)
        existing_annual_premium: float | None = existing.get("annualPremium")
        existing_waiting_days: int = int(existing.get("waitingPeriodDays") or STANDARD_WAITING_PERIOD_DAYS)
        existing_survival_days: int = int(existing.get("survivalPeriodDays") or STANDARD_SURVIVAL_PERIOD_DAYS)
        existing_premium_type: str | None = existing.get("premiumType")
        existing_conditions: list[str] = existing.get("coveredConditions") or []
        has_advancement: bool = bool(existing.get("hasAdvancementBenefit", False))
        has_multi_claim: bool = bool(existing.get("hasMultiClaimRider", False))

        # Proposed policy fields
        proposed_waiting_days: int | None = proposed.get("waitingPeriodDays")
        proposed_survival_days: int | None = proposed.get("survivalPeriodDays")
        proposed_sum_insured: float | None = proposed.get("sumInsured")
        proposed_annual_premium: float | None = proposed.get("annualPremium")
        proposed_premium_type: str | None = proposed.get("premiumType")
        proposed_conditions: list[str] = proposed.get("coveredConditions") or []

        # Financial
        total_liabilities: float = float(financial.get("totalLiabilities") or 0)
        # Also incorporate mortgage if provided separately
        mortgage: float = float(financial.get("mortgageBalance") or 0)
        if mortgage > total_liabilities:
            total_liabilities = mortgage
        liquid_assets: float = float(financial.get("liquidAssets") or 0)
        monthly_expenses: float = float(financial.get("monthlyExpenses") or 0)

        # Goals
        wants_replacement: bool | None = goals.get("wantsReplacement")
        wants_retention: bool | None = goals.get("wantsRetention")

        # Health
        health_conditions: list[str] = health.get("conditions") or []
        height_m: float | None = health.get("height")
        weight_kg: float | None = health.get("weight")

        # ------------------------------------------------------------------
        # 2. Derive effective coverage parameters
        # ------------------------------------------------------------------
        effective_sum_insured = existing_sum_insured if has_existing else 0.0
        effective_conditions = existing_conditions if has_existing else []
        effective_waiting_days = existing_waiting_days if has_existing else STANDARD_WAITING_PERIOD_DAYS
        effective_survival_days = existing_survival_days if has_existing else STANDARD_SURVIVAL_PERIOD_DAYS
        effective_premium = existing_annual_premium if has_existing else proposed_annual_premium

        # ------------------------------------------------------------------
        # 3. Run all analysis modules
        # ------------------------------------------------------------------

        ci_need = _calc_ci_need(
            annual_gross_income=annual_gross_income,
            total_liabilities=total_liabilities,
            liquid_assets=liquid_assets,
            monthly_expenses=monthly_expenses,
        )

        coverage_gap = _calc_coverage_gap(
            existing_sum_insured=effective_sum_insured,
            calculated_need=ci_need["calculated_need_aud"],
        )

        waiting_analysis = _calc_waiting_period_analysis(
            current_waiting_days=effective_waiting_days,
            proposed_waiting_days=proposed_waiting_days,
        )

        survival_analysis = _calc_survival_period_analysis(
            current_survival_days=effective_survival_days,
            proposed_survival_days=proposed_survival_days,
        )

        condition_eval = _eval_covered_conditions(effective_conditions)

        affordability = _calc_affordability(
            annual_premium=effective_premium,
            annual_gross_income=annual_gross_income,
        )

        underwriting_risk = _assess_underwriting_risk(
            age=age,
            is_smoker=is_smoker,
            occupation_class=occupation_class,
            health_conditions=health_conditions,
            height_m=height_m,
            weight_kg=weight_kg,
        )

        premium_type_eval = _eval_premium_type(
            premium_type=existing_premium_type if has_existing else proposed_premium_type,
            age=age,
        )

        super_eligibility = _eval_super_eligibility()
        cooling_off = _eval_cooling_off()

        # Proposed policy comparison (if proposal exists)
        proposed_comparison: dict | None = None
        if proposed_sum_insured or proposed_annual_premium:
            proposed_need_gap = max(
                0.0,
                ci_need["calculated_need_aud"] - (proposed_sum_insured or 0)
            ) if proposed_sum_insured else None

            proposed_condition_eval = (
                _eval_covered_conditions(proposed_conditions) if proposed_conditions else None
            )

            proposed_comparison = {
                "proposed_sum_insured_aud": proposed_sum_insured,
                "proposed_annual_premium_aud": proposed_annual_premium,
                "proposed_waiting_period_days": proposed_waiting_days,
                "proposed_survival_period_days": proposed_survival_days,
                "proposed_premium_type": proposed_premium_type,
                "remaining_gap_if_adopted_aud": round(proposed_need_gap) if proposed_need_gap is not None else None,
                "proposed_condition_evaluation": proposed_condition_eval,
                "proposed_affordability": _calc_affordability(
                    annual_premium=proposed_annual_premium,
                    annual_gross_income=annual_gross_income,
                ) if proposed_annual_premium else None,
            }

        # Missing info
        missing_info = _build_missing_info_questions(
            annual_gross_income=annual_gross_income,
            existing_sum_insured=existing_sum_insured if has_existing else None,
            covered_conditions=effective_conditions,
            age=age,
            annual_premium=effective_premium,
            has_existing_policy=has_existing,
        )

        # ------------------------------------------------------------------
        # 4. Generate recommendation
        # ------------------------------------------------------------------
        recommendation = _generate_recommendation(
            has_existing_policy=bool(has_existing),
            shortfall_severity=coverage_gap["shortfall_severity"],
            waiting_period_compliant=waiting_analysis["current_compliant_with_standard"],
            survival_period_ok=(effective_survival_days <= MAX_SURVIVAL_PERIOD_DAYS),
            life_code_minimum_met=condition_eval["life_code_minimum_met"],
            affordability_band=affordability.get("band", "UNKNOWN"),
            underwriting_risk_level=underwriting_risk["overall_risk_level"],
            client_age=age,
            wants_replacement=wants_replacement,
            wants_retention=wants_retention,
        )

        # ------------------------------------------------------------------
        # 5. Compliance flags (aggregate)
        # ------------------------------------------------------------------
        all_flags: list[dict] = []
        all_flags.extend(waiting_analysis.get("flags", []))
        all_flags.extend(survival_analysis.get("flags", []))
        all_flags.extend(condition_eval.get("flags", []))
        all_flags.extend(premium_type_eval.get("flags", []))
        if underwriting_risk["overall_risk_level"] == "CRITICAL":
            all_flags.append({
                "code": "CRITICAL_UNDERWRITING_RISK",
                "severity": "CRITICAL",
                "message": "Client underwriting risk is critical — new CI policy issuance may be refused.",
            })

        # ------------------------------------------------------------------
        # 6. Member actions (actionable steps)
        # ------------------------------------------------------------------
        member_actions = list(recommendation.get("actions", []))

        # Add CI-specific standard actions
        if not has_existing:
            member_actions.append(
                "Ensure policy documents contain the 30-day free-look (cooling-off) clause."
            )
        if has_existing and not has_advancement:
            member_actions.append(
                "Review whether the existing policy includes an advancement (partial) benefit "
                "for early-stage conditions (e.g. carcinoma in situ, single-vessel angioplasty)."
            )
        if has_existing and not has_multi_claim:
            member_actions.append(
                "Consider a Double CI / multi-claim rider if a second critical illness event "
                "benefit is important to the client's financial plan."
            )

        # ------------------------------------------------------------------
        # 7. Assemble final result
        # ------------------------------------------------------------------
        return {
            "tool": self.name,
            "version": self.version,
            "ci_need": ci_need,
            "coverage_gap": coverage_gap,
            "waiting_period_analysis": waiting_analysis,
            "survival_period_analysis": survival_analysis,
            "covered_condition_evaluation": condition_eval,
            "premium_type_evaluation": premium_type_eval,
            "affordability": affordability,
            "underwriting_risk": underwriting_risk,
            "super_eligibility": super_eligibility,
            "cooling_off": cooling_off,
            "proposed_policy_comparison": proposed_comparison,
            "recommendation": recommendation,
            "compliance_flags": all_flags,
            "member_actions": member_actions,
            "missing_info_questions": missing_info,
            "policy_features": {
                "has_advancement_benefit": has_advancement,
                "has_child_rider": bool(existing.get("hasChildRider", False)),
                "has_female_rider": bool(existing.get("hasFemaleRider", False)),
                "has_multi_claim_rider": has_multi_claim,
            },
            "regulatory_notes": {
                "not_permitted_in_super": True,
                "life_code_minimum_conditions": sorted(LIFE_CODE_MINIMUM_CONDITIONS),
                "standard_waiting_period_days": STANDARD_WAITING_PERIOD_DAYS,
                "standard_survival_period_days": STANDARD_SURVIVAL_PERIOD_DAYS,
                "cooling_off_statutory_days": STATUTORY_COOLING_OFF_DAYS,
                "cooling_off_industry_days": INDUSTRY_COOLING_OFF_DAYS,
                "contestability_period_years": CONTESTABILITY_PERIOD_YEARS,
                "licat_capital_factor_pct": LICAT_TRAUMA_CAPITAL_FACTOR * 100,
            },
        }
