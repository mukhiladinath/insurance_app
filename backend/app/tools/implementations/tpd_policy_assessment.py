"""
tpd_policy_assessment.py — TPD Policy Definition, Placement & Claims Assessment tool.

Implements the deep regulatory rules and product mechanics for Total and Permanent
Disability (TPD) insurance as documented in the research report (tpd_insurance_policy.md):

  - TPD definition quality ranking: own-occ > modified-own-occ > any-occ > ADL
  - SIS Act / Regulation compliance: Reg 4.07C (AAL), Reg 4.07D (non-conforming cover),
    s68AA (MySuper any-occupation mandate), permanent incapacity condition of release
  - Super vs retail placement analysis (definition, tax, portability, governance)
  - APRA SPS 250 (Insurance in Superannuation, effective July 2022) governance flags
  - Tax treatment: retail (tax-free benefit) vs super (ITAA 1997 Div. 295 taxed component)
  - TPD lump-sum need calculation (income, rehab, home modification, debt, care)
  - Claims eligibility assessment: own-occ (~88% approval) vs ADL (~40% approval)
  - Dual-test for super claims: contract definition + SIS permanent incapacity test
  - Standard TPD exclusions (self-inflicted, war, criminal, drug/alcohol)
  - Lapse and reinstatement rules (3-year window, back-payment, health evidence)
  - Dispute resolution path: IDR → AFCA (up to $3M for life insurance disputes)
  - Premium structure evaluation: stepped vs level, group vs individual
  - Ownership and portability analysis

This tool is deterministic: same input → same output. No LLM calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.tools.base import BaseTool, ToolValidationError

# =============================================================================
# CONSTANTS (sourced from tpd_insurance_policy.md research report)
# =============================================================================

ENGINE_VERSION = "1.0.0"

# ── SIS Act / Regulation thresholds ─────────────────────────────────────────

# SIS Reg 4.07C — Automatic Acceptance Limit (no medical questions required)
AUTO_ACCEPTANCE_LIMIT_AUD = 100_000

# Age boundaries for default MySuper cover eligibility
MYSUPER_MIN_AGE = 25
MYSUPER_MAX_AGE = 65

# Inactivity threshold before cover switches off (months) — PYS reforms 2018-20
INACTIVITY_THRESHOLD_MONTHS = 16

# Cut-off date after which new non-conforming (own-occ / ADL) TPD in super is prohibited
# SIS Reg 4.07D effective 1 July 2014
NON_CONFORMING_CUTOFF_YEAR = 2014
NON_CONFORMING_CUTOFF_MONTH = 7

# Contestability / non-disclosure lookback (years) — insurer can void for misstatement
CONTESTABILITY_YEARS = 2

# Reinstatement window (years) — Life Code of Practice / industry norm
REINSTATEMENT_WINDOW_YEARS = 3

# AFCA maximum claim value for life insurance disputes
AFCA_MAX_CLAIM_AUD = 3_000_000

# ── Definition quality ranking ───────────────────────────────────────────────
# Higher = more favourable to claimant (from tpd_insurance_policy.md)
TPD_DEFINITION_RANK = {
    "OWN_OCCUPATION":          5,
    "MODIFIED_OWN_OCCUPATION": 4,
    "ANY_OCCUPATION":          3,
    "ACTIVITIES_OF_DAILY_LIVING": 2,  # ADL — high decline rate ~60%
    "HOME_DUTIES":             1,
    "UNKNOWN":                 0,
}

# Approximate claim approval rates by definition type
# Source: ASIC Rep 498 / Rep 633
DEFINITION_APPROVAL_RATE = {
    "OWN_OCCUPATION":          0.88,
    "MODIFIED_OWN_OCCUPATION": 0.84,
    "ANY_OCCUPATION":          0.80,
    "ACTIVITIES_OF_DAILY_LIVING": 0.40,  # ~60% decline rate per ASIC Rep 633
    "HOME_DUTIES":             0.55,
    "UNKNOWN":                 0.75,
}

# ── Tax rates — super TPD lump sum (ITAA 1997 Div. 295) ─────────────────────
# Taxable component taxed at these rates (includes 2% Medicare Levy)
SUPER_TPD_TAX_UNDER_60 = 0.22   # 20% + 2% Medicare
SUPER_TPD_TAX_OVER_60  = 0.00   # Tax-free for taxed element (superannuation benefit)

# ── Affordability bands — premium as fraction of gross income ────────────────
AFFORDABILITY_BANDS = {
    "COMFORTABLE": 0.02,
    "MANAGEABLE":  0.04,
    "STRETCHED":   0.07,
}

# ── Occupation risk for underwriting ─────────────────────────────────────────
OCCUPATION_RISK_MAP = {
    "CLASS_1_WHITE_COLLAR":    "LOW",
    "CLASS_2_LIGHT_BLUE":      "MEDIUM",
    "CLASS_3_BLUE_COLLAR":     "HIGH",
    "CLASS_4_HAZARDOUS":       "CRITICAL",
    "UNKNOWN":                 "MEDIUM",
}

# ── Stepped premium annual escalation ─────────────────────────────────────────
STEPPED_ANNUAL_INCREASE_FACTOR = 0.06  # ~6% per year (age-based escalation)

# ── Shortfall severity buckets (AUD gap between need and existing cover) ──────
SHORTFALL_THRESHOLDS = {
    "NONE":         0,
    "MINOR":        50_000,
    "MODERATE":     200_000,
    "SIGNIFICANT":  500_000,
}

# ── TPD need components ───────────────────────────────────────────────────────
DEFAULT_MEDICAL_REHAB_BUFFER    = 75_000
DEFAULT_HOME_MODIFICATION       = 50_000
DEFAULT_ONGOING_CARE_ANNUAL     = 30_000   # per year, annuitised
DEFAULT_CARE_YEARS              = 20       # expected care period
INCOME_CAPITALISATION_RATE      = 0.05     # discount rate for PV of income

# ── ADL warning flag threshold ────────────────────────────────────────────────
ADL_HIGH_DECLINE_RATE_PCT = 60  # per ASIC Rep 633

# ── Super TPD governance (SPS 250) ────────────────────────────────────────────
SPS_250_EFFECTIVE_DATE = "2022-07-01"
SPS_250_TRUSTEE_OBLIGATIONS = [
    "Annual review of insurance strategy and member outcomes",
    "Certify insurance arrangements are in members' best interests (SIS s52(7)(d))",
    "Obtain independent assessment for related-party insurance (SPS 250 Pt B)",
    "Publish insurance strategy as part of Product Disclosure Statement",
    "Assess whether default cover settings remain appropriate annually",
    "Maintain data capability to measure claims experience and outcomes",
]


# =============================================================================
# HELPERS
# =============================================================================

def _safe_parse_date(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d
    except (ValueError, TypeError):
        return None


def _age_from_dob(dob: datetime) -> int:
    today = datetime.now(timezone.utc)
    years = today.year - dob.year
    if (today.month, today.day) < (dob.month, dob.day):
        years -= 1
    return max(0, years)


def _pv_annuity(annual_pmt: float, years: float, rate: float) -> float:
    """Present value of an ordinary annuity."""
    if rate == 0 or years <= 0:
        return annual_pmt * max(0.0, years)
    return annual_pmt * (1 - (1 + rate) ** -years) / rate


def _classify_shortfall(gap: float) -> str:
    if gap <= SHORTFALL_THRESHOLDS["NONE"]:
        return "NONE"
    if gap <= SHORTFALL_THRESHOLDS["MINOR"]:
        return "MINOR"
    if gap <= SHORTFALL_THRESHOLDS["MODERATE"]:
        return "MODERATE"
    if gap <= SHORTFALL_THRESHOLDS["SIGNIFICANT"]:
        return "SIGNIFICANT"
    return "CRITICAL"


def _is_definition_sis_compliant(definition: str, in_super: bool, is_grandfathered: bool) -> bool:
    """
    Return True if the TPD definition is permissible for the given ownership context.

    SIS Act s68AA mandates any-occupation (or better) for MySuper default.
    SIS Reg 4.07D prohibits new own-occ or ADL-linked TPD in super post-July 2014
    unless grandfathered from pre-2014.
    """
    if not in_super:
        return True  # All definitions are permissible for retail/personal policies
    rank = TPD_DEFINITION_RANK.get(definition, 0)
    any_occ_rank = TPD_DEFINITION_RANK["ANY_OCCUPATION"]
    if rank >= any_occ_rank:
        return True
    # Below any-occ (ADL, HOME_DUTIES) — only allowed if grandfathered
    if definition in ("ACTIVITIES_OF_DAILY_LIVING", "HOME_DUTIES"):
        return is_grandfathered
    # OWN_OCCUPATION and MODIFIED_OWN_OCCUPATION in super — only grandfathered pre-2014
    if definition in ("OWN_OCCUPATION", "MODIFIED_OWN_OCCUPATION"):
        return is_grandfathered
    return True


# =============================================================================
# ANALYSIS MODULES
# =============================================================================

def _eval_tpd_definition(
    definition: str,
    in_super: bool,
    is_grandfathered: bool,
) -> dict:
    """
    Evaluate TPD definition quality, SIS compliance, and claim risk.

    Key findings from ASIC Rep 633:
    - ADL definitions have ~60% decline rate vs ~12% for standard own/any-occ
    - Own-occupation is the most favourable but is prohibited in new super policies
    - Any-occupation is the baseline permissible definition for MySuper (s68AA)
    """
    rank = TPD_DEFINITION_RANK.get(definition, 0)
    approval_rate = DEFINITION_APPROVAL_RATE.get(definition, 0.75)
    sis_compliant = _is_definition_sis_compliant(definition, in_super, is_grandfathered)

    flags = []

    if definition == "ACTIVITIES_OF_DAILY_LIVING":
        flags.append({
            "code": "ADL_HIGH_DECLINE_RISK",
            "severity": "CRITICAL",
            "message": (
                f"Activities of Daily Living (ADL) TPD definitions have an approximate "
                f"{ADL_HIGH_DECLINE_RATE_PCT}% claim decline rate per ASIC Report 633. "
                "This is significantly higher than any-occupation (~20%) or own-occupation (~12%). "
                "ASIC and APRA have specifically called out ADL definitions as leading to "
                "poor consumer outcomes."
            ),
        })

    if definition in ("OWN_OCCUPATION", "MODIFIED_OWN_OCCUPATION") and in_super:
        if is_grandfathered:
            flags.append({
                "code": "OWN_OCC_SUPER_GRANDFATHERED",
                "severity": "INFO",
                "message": (
                    "Own-occupation TPD inside super is grandfathered from pre-1 July 2014 "
                    "(SIS Reg 4.07D). This is a valuable legacy benefit — do not cancel or "
                    "restructure without careful analysis, as it cannot be re-issued in super."
                ),
            })
        else:
            flags.append({
                "code": "OWN_OCC_IN_SUPER_NOT_PERMITTED",
                "severity": "CRITICAL",
                "message": (
                    "Own-occupation TPD cannot be issued inside superannuation for new policies "
                    "after 1 July 2014 (SIS Reg 4.07D). This cover arrangement is non-conforming "
                    "and must be restructured or held as a retail policy outside super."
                ),
            })

    if not sis_compliant and in_super:
        flags.append({
            "code": "SIS_NON_CONFORMING_COVER",
            "severity": "CRITICAL",
            "message": (
                f"TPD definition '{definition}' does not comply with SIS Act requirements "
                "for insurance inside superannuation (SIS Reg 4.07D). Trustees must not "
                "issue or continue non-conforming cover unless properly grandfathered."
            ),
        })

    if rank < TPD_DEFINITION_RANK["ANY_OCCUPATION"] and not in_super:
        flags.append({
            "code": "DEFINITION_BELOW_ANY_OCC_RETAIL",
            "severity": "WARNING",
            "message": (
                f"Retail TPD with an '{definition}' definition is below the any-occupation "
                "standard. While permissible, this significantly restricts claim eligibility "
                "and may represent poor value. Consider recommending any-occupation or "
                "own-occupation cover instead."
            ),
        })

    quality_label = {
        5: "EXCELLENT",
        4: "GOOD",
        3: "STANDARD",
        2: "POOR",
        1: "VERY_POOR",
        0: "UNKNOWN",
    }.get(rank, "UNKNOWN")

    return {
        "definition": definition,
        "definition_rank": rank,
        "definition_quality": quality_label,
        "approximate_approval_rate_pct": round(approval_rate * 100, 1),
        "approximate_decline_rate_pct": round((1 - approval_rate) * 100, 1),
        "sis_compliant": sis_compliant,
        "is_grandfathered": is_grandfathered,
        "in_super": in_super,
        "flags": flags,
        "definition_descriptions": {
            "OWN_OCCUPATION": "Pays if unable to return to own specific occupation (most favourable).",
            "MODIFIED_OWN_OCCUPATION": "Own-occ with step-down to any-occ after 2 years on claim.",
            "ANY_OCCUPATION": "Pays if unable to work in any occupation suited to education/experience.",
            "ACTIVITIES_OF_DAILY_LIVING": "Pays only if unable to perform basic daily tasks — highest decline risk.",
            "HOME_DUTIES": "Pays if unable to perform home duties — typically for non-employed persons.",
        }.get(definition, "Unknown definition type."),
    }


def _eval_super_placement(
    in_super: bool,
    definition: str,
    is_grandfathered: bool,
    member_age: int | None,
    account_inactive_months: int,
    sum_insured: float,
    fund_type: str,
    is_mysuper: bool,
    has_opted_in: bool,
) -> dict:
    """
    Evaluate compliance and suitability of TPD held inside superannuation.

    Key SIS rules:
    - SIS Reg 4.07C: Automatic Acceptance Limit (AAL) = ~$100K (no health questions)
    - SIS Reg 4.07D: No new non-conforming cover after 1 Jul 2014
    - SIS s68AA: MySuper must provide any-occupation TPD by default
    - PYS reforms: cover switches off after 16 months inactivity unless opted-in
    - Age: no default cover for members under 25 or over 65 in MySuper
    - SPS 250: trustee governance and member outcome obligations
    """
    if not in_super:
        return {
            "in_super": False,
            "summary": "Policy is held as a retail (personal) policy outside superannuation.",
            "sis_compliance": "N/A — SIS Act insurance rules do not apply to retail policies.",
            "portability": "PORTABLE — cover continues regardless of employer or fund changes.",
            "flags": [],
        }

    flags = []

    # Age eligibility
    if member_age is not None:
        if member_age < MYSUPER_MIN_AGE:
            flags.append({
                "code": "UNDER_25_NO_DEFAULT_MYSUPER_COVER",
                "severity": "WARNING",
                "message": (
                    f"Member is age {member_age}, under the MySuper minimum entry age of "
                    f"{MYSUPER_MIN_AGE}. Default TPD cover is not automatically provided in "
                    "MySuper products for members under 25 (SIS s68AA). An opt-in election "
                    "is required to obtain cover."
                ),
            })
        if member_age >= MYSUPER_MAX_AGE:
            flags.append({
                "code": "OVER_65_COVER_LIKELY_CEASED",
                "severity": "WARNING",
                "message": (
                    f"Member is age {member_age}, at or above the maximum default cover age "
                    f"of {MYSUPER_MAX_AGE}. TPD cover typically ceases at age 65 under "
                    "MySuper/group super arrangements."
                ),
            })

    # Inactivity check
    if account_inactive_months >= INACTIVITY_THRESHOLD_MONTHS and not has_opted_in:
        flags.append({
            "code": "PYS_INACTIVITY_SWITCH_OFF",
            "severity": "CRITICAL",
            "message": (
                f"Account has been inactive for {account_inactive_months} months "
                f"(threshold: {INACTIVITY_THRESHOLD_MONTHS} months). Under Protecting Your "
                "Super (PYS) reforms, TPD cover switches off automatically unless the member "
                "has elected to retain it. Cover may have already ceased."
            ),
        })
    elif account_inactive_months >= INACTIVITY_THRESHOLD_MONTHS and has_opted_in:
        flags.append({
            "code": "PYS_INACTIVITY_OPTED_IN",
            "severity": "INFO",
            "message": (
                f"Account inactive for {account_inactive_months} months but member has "
                "lodged an opt-in election. Cover is retained under PYS rules."
            ),
        })

    # AAL compliance
    requires_evidence = sum_insured > AUTO_ACCEPTANCE_LIMIT_AUD
    if sum_insured > AUTO_ACCEPTANCE_LIMIT_AUD:
        flags.append({
            "code": "ABOVE_AUTO_ACCEPTANCE_LIMIT",
            "severity": "INFO",
            "message": (
                f"Sum insured of ${sum_insured:,.0f} exceeds the Automatic Acceptance Limit "
                f"(AAL) of ${AUTO_ACCEPTANCE_LIMIT_AUD:,.0f} (SIS Reg 4.07C). "
                "Health evidence / financial questionnaire is required for the excess amount."
            ),
        })

    # Definition compliance
    sis_compliant = _is_definition_sis_compliant(definition, in_super=True, is_grandfathered=is_grandfathered)
    if not sis_compliant:
        flags.append({
            "code": "SUPER_DEFINITION_NON_CONFORMING",
            "severity": "CRITICAL",
            "message": (
                f"'{definition}' TPD definition is non-conforming for new super policies "
                "under SIS Reg 4.07D (post 1 July 2014). Trustee must not continue "
                "issuing this cover without a valid grandfathering exemption."
            ),
        })

    # SPS 250 note
    flags.append({
        "code": "SPS_250_GOVERNANCE_APPLIES",
        "severity": "INFO",
        "message": (
            f"APRA Prudential Standard SPS 250 (effective {SPS_250_EFFECTIVE_DATE}) "
            "imposes trustee governance, data, and member-outcome obligations. "
            "Annual insurance strategy review and certification is required."
        ),
    })

    return {
        "in_super": True,
        "fund_type": fund_type,
        "is_mysuper": is_mysuper,
        "sis_compliant": sis_compliant,
        "auto_acceptance_limit_aud": AUTO_ACCEPTANCE_LIMIT_AUD,
        "sum_insured_requires_evidence": requires_evidence,
        "inactivity_threshold_months": INACTIVITY_THRESHOLD_MONTHS,
        "account_inactive_months": account_inactive_months,
        "has_opted_in": has_opted_in,
        "portability": (
            "NON-PORTABLE — cover generally ceases on leaving the fund (unless new fund "
            "provides equivalent default cover or member arranges retail replacement)."
        ),
        "permanent_incapacity_condition": (
            "For a claim to be paid from super, the trustee must be reasonably satisfied "
            "that due to ill-health the member is unlikely ever again to engage in gainful "
            "employment for which they are reasonably qualified by education, training, or "
            "experience (SIS Reg 1.03C — permanent incapacity condition of release)."
        ),
        "sps_250_trustee_obligations": SPS_250_TRUSTEE_OBLIGATIONS,
        "flags": flags,
    }


def _calc_tax_impact(
    in_super: bool,
    sum_insured: float,
    taxable_component_pct: float,
    member_age: int | None,
) -> dict:
    """
    Calculate tax impact of TPD benefit payment.

    Retail: benefit is tax-free (not assessable income per life insurance rules).
    Super: benefit is a super lump-sum — taxable component taxed at Div. 295 rates:
      - Under 60: 20% + 2% Medicare = 22%
      - 60+: tax-free (taxed element also tax-free from age 60)
    """
    if not in_super:
        return {
            "tax_treatment": "RETAIL_TAX_FREE",
            "benefit_aud": round(sum_insured),
            "estimated_tax_aud": 0,
            "net_benefit_aud": round(sum_insured),
            "premium_deductibility": "NOT_DEDUCTIBLE (personal/retail premiums are not tax-deductible)",
            "note": (
                "Personal TPD insurance benefits are generally received tax-free as they "
                "are not assessable income (Life Insurance Act 1995 / ICA framework)."
            ),
        }

    # Super lump sum tax
    taxable_amount = sum_insured * taxable_component_pct
    tax_free_amount = sum_insured - taxable_amount

    if member_age is not None and member_age >= 60:
        tax_rate = SUPER_TPD_TAX_OVER_60
        tax_note = "Member is 60+: taxed element is tax-free (ITAA 1997 Div. 295)."
    else:
        tax_rate = SUPER_TPD_TAX_UNDER_60
        tax_note = (
            f"Member is under 60: taxed element taxed at {tax_rate*100:.0f}% "
            "(20% concessional rate + 2% Medicare Levy, ITAA 1997 s307-145)."
        )

    estimated_tax = taxable_amount * tax_rate
    net_benefit = sum_insured - estimated_tax

    return {
        "tax_treatment": "SUPER_LUMP_SUM",
        "benefit_aud": round(sum_insured),
        "taxable_component_aud": round(taxable_amount),
        "tax_free_component_aud": round(tax_free_amount),
        "estimated_tax_aud": round(estimated_tax),
        "net_benefit_aud": round(net_benefit),
        "effective_tax_rate_pct": round(tax_rate * 100, 1),
        "premium_deductibility": (
            "DEDUCTIBLE TO FUND (premiums paid by super fund are tax-deductible to "
            "the fund; member does not deduct personally)"
        ),
        "tax_note": tax_note,
        "itaa_reference": "ITAA 1997 Div. 295 / s307-145 (super lump-sum tax components)",
        "note": (
            "Tax estimates are indicative. Actual tax depends on total super balance, "
            "low-rate cap, and member's marginal tax rate. Seek tax advice."
        ),
    }


def _calc_tpd_need(
    annual_gross_income: float | None,
    years_to_retirement: float,
    mortgage_balance: float,
    other_debts: float,
    liquid_assets: float,
    existing_tpd_cover: float,
    include_care_costs: bool,
) -> dict:
    """
    Calculate TPD-specific lump-sum need.

    Components:
    1. PV of future income to retirement (capitalised at INCOME_CAPITALISATION_RATE)
    2. Medical / rehabilitation buffer
    3. Home modification costs (wheelchair access, etc.)
    4. Ongoing care costs (PV of annual care cost × care years)
    5. Debt clearance (mortgage + other debts)
    Less: existing TPD cover + liquid assets
    """
    income_pv = 0.0
    if annual_gross_income and annual_gross_income > 0 and years_to_retirement > 0:
        income_pv = _pv_annuity(annual_gross_income, years_to_retirement, INCOME_CAPITALISATION_RATE)

    rehab = DEFAULT_MEDICAL_REHAB_BUFFER
    home_mod = DEFAULT_HOME_MODIFICATION
    care_pv = (
        _pv_annuity(DEFAULT_ONGOING_CARE_ANNUAL, DEFAULT_CARE_YEARS, INCOME_CAPITALISATION_RATE)
        if include_care_costs else 0.0
    )
    debt = max(0.0, mortgage_balance + other_debts)

    gross_need = income_pv + rehab + home_mod + care_pv + debt
    net_need = max(0.0, gross_need - existing_tpd_cover - liquid_assets)
    gap = max(0.0, net_need)

    return {
        "calculated_need_aud": round(gross_need),
        "net_shortfall_aud": round(net_need),
        "gap_aud": round(gap),
        "shortfall_severity": _classify_shortfall(gap),
        "components": {
            "income_pv_aud": round(income_pv),
            "medical_rehab_aud": rehab,
            "home_modification_aud": home_mod,
            "ongoing_care_pv_aud": round(care_pv),
            "debt_clearance_aud": round(debt),
        },
        "less": {
            "existing_tpd_cover_aud": round(existing_tpd_cover),
            "liquid_assets_aud": round(liquid_assets),
        },
        "assumptions": {
            "capitalisation_rate": INCOME_CAPITALISATION_RATE,
            "care_years": DEFAULT_CARE_YEARS if include_care_costs else 0,
            "years_to_retirement": round(years_to_retirement, 1),
        },
        "income_known": annual_gross_income is not None and annual_gross_income > 0,
    }


def _eval_claims_eligibility(
    definition: str,
    in_super: bool,
    medical_conditions: list[str],
    occupation_class: str,
    sum_insured: float,
    policy_age_years: float,
) -> dict:
    """
    Assess likely claims eligibility and documentation requirements.

    Key issues from ASIC Rep 633:
    - Consumers face multiple information requests, long delays, surveillance
    - ADL definitions cause ~60% decline rate
    - Super claims require meeting BOTH contract definition AND SIS permanent incapacity test
    - High-risk occupations and certain conditions may trigger complex assessments
    """
    approval_rate = DEFINITION_APPROVAL_RATE.get(definition, 0.75)
    flags = []
    required_evidence = [
        "Completed TPD claim form (insurer-specific)",
        "Treating doctor's report confirming permanent inability to work",
        "Specialist medical reports (relevant to disability type)",
        "Employment records / work history for the past 2 years",
        "Evidence of income / payslips (for own-occ and any-occ claims)",
        "ATO tax returns (typically last 2-3 years)",
    ]

    if definition == "ACTIVITIES_OF_DAILY_LIVING":
        flags.append({
            "code": "ADL_CLAIM_HIGH_RISK",
            "severity": "CRITICAL",
            "message": (
                "ADL-based claims face a ~60% decline rate per ASIC Report 633. "
                "Claimants must demonstrate inability to perform at least 2 of 5 basic "
                "activities of daily living (bathing, dressing, eating, toileting, mobility). "
                "This test is unrelated to work capacity and is difficult to satisfy for "
                "many disabling conditions (e.g. severe mental illness, spinal injuries)."
            ),
        })
        required_evidence.append("Functional capacity assessment by occupational therapist or physiatrist")
        required_evidence.append("Evidence of inability to perform specific ADL tasks (2 of 5 minimum)")

    if in_super:
        flags.append({
            "code": "DUAL_TEST_SUPER_CLAIM",
            "severity": "WARNING",
            "message": (
                "Claims from superannuation must satisfy TWO tests simultaneously: "
                "(1) The insurer's contract TPD definition; AND "
                "(2) SIS Act permanent incapacity condition of release: the trustee must be "
                "'reasonably satisfied' the member is unlikely to ever again engage in "
                "gainful employment for which they are qualified (SIS Reg 1.03C). "
                "A successful insurance claim does not automatically trigger a super payout "
                "— trustee determination is also required."
            ),
        })
        required_evidence.append(
            "Trustee determination: medical and vocational evidence for SIS permanent incapacity test"
        )

    # Contestability check
    if policy_age_years < CONTESTABILITY_YEARS:
        flags.append({
            "code": "POLICY_WITHIN_CONTESTABILITY_PERIOD",
            "severity": "WARNING",
            "message": (
                f"Policy is within the {CONTESTABILITY_YEARS}-year contestability period. "
                "The insurer may investigate pre-existing conditions and non-disclosure. "
                "Claims within this period may face additional scrutiny."
            ),
        })

    # AFCA note
    flags.append({
        "code": "AFCA_DISPUTE_PATHWAY_AVAILABLE",
        "severity": "INFO",
        "message": (
            f"If a TPD claim is declined, the member can appeal via the insurer's Internal "
            f"Dispute Resolution (IDR) process, then escalate to AFCA "
            f"(Australian Financial Complaints Authority). AFCA handles life insurance "
            f"disputes up to ${AFCA_MAX_CLAIM_AUD:,.0f}. AFCA is free to the complainant."
        ),
    })

    return {
        "definition": definition,
        "approximate_approval_rate_pct": round(approval_rate * 100, 1),
        "approximate_decline_rate_pct": round((1 - approval_rate) * 100, 1),
        "required_evidence": required_evidence,
        "in_super_dual_test": in_super,
        "dispute_resolution": {
            "step_1": "Internal Dispute Resolution (IDR) — insurer must respond within 45 days (Life Code)",
            "step_2": "AFCA (Australian Financial Complaints Authority) — up to $3M TPD disputes",
            "step_3": "Court proceedings (for claims exceeding AFCA jurisdiction or unresolved)",
        },
        "flags": flags,
    }


def _eval_exclusions(
    hazardous_activities: list[str],
    medical_conditions: list[str],
    is_smoker: bool,
) -> dict:
    """
    Assess standard TPD exclusions and any likely personalised exclusions.
    """
    standard_exclusions = [
        {
            "exclusion": "SELF_INFLICTED_INJURY",
            "description": "No TPD benefit for total and permanent disability resulting from self-inflicted injury.",
        },
        {
            "exclusion": "WAR_OR_CIVIL_UNREST",
            "description": "No benefit for disability arising from declared war or active participation in civil war.",
        },
        {
            "exclusion": "CRIMINAL_ACT",
            "description": "Disability occurring while committing a criminal act is excluded.",
        },
        {
            "exclusion": "DRUG_ALCOHOL",
            "description": (
                "Disability primarily caused by drug or alcohol abuse or addiction is typically excluded, "
                "or may require an additional premium loading."
            ),
        },
    ]

    personal_exclusions = []

    if hazardous_activities:
        personal_exclusions.append({
            "exclusion": "HAZARDOUS_ACTIVITIES",
            "activities": hazardous_activities,
            "description": (
                f"Declared hazardous activities ({', '.join(hazardous_activities)}) may attract "
                "a specific exclusion or premium loading at underwriting."
            ),
        })

    ci_relevant = [
        c for c in (medical_conditions or [])
        if any(kw in c.upper() for kw in [
            "BACK", "SPINE", "CARDIAC", "HEART", "STROKE", "CANCER", "MENTAL",
            "DEPRESSION", "ANXIETY", "JOINT", "ARTHRITIS", "NEUROLOG",
        ])
    ]
    if ci_relevant:
        personal_exclusions.append({
            "exclusion": "PRE_EXISTING_CONDITIONS",
            "conditions": ci_relevant,
            "description": (
                f"Pre-existing conditions ({', '.join(ci_relevant)}) disclosed at application may "
                "result in specific exclusions under the non-disclosure / duty of disclosure rules "
                "(Insurance Contracts Act 1984 s21). Review policy wording carefully."
            ),
        })

    if is_smoker:
        personal_exclusions.append({
            "exclusion": "SMOKER_PREMIUM_LOADING",
            "description": (
                "Smoker status typically attracts a premium loading of 50–100% on TPD cover "
                "rather than an exclusion. The loading reflects higher disability risk."
            ),
        })

    return {
        "standard_exclusions": standard_exclusions,
        "likely_personal_exclusions": personal_exclusions,
        "total_standard": len(standard_exclusions),
        "total_personal": len(personal_exclusions),
        "contestability_period_years": CONTESTABILITY_YEARS,
        "note": (
            "Actual exclusions are insurer-specific. Review the policy schedule and "
            "policy document for all applicable exclusions."
        ),
    }


def _eval_premium_structure(
    premium_type: str | None,
    annual_premium: float | None,
    annual_gross_income: float | None,
    age: int | None,
    in_super: bool,
) -> dict:
    """
    Evaluate premium structure suitability and affordability.
    """
    premium_type = (premium_type or "UNKNOWN").upper()
    flags = []

    if in_super:
        flags.append({
            "code": "GROUP_SUPER_PREMIUM_POOLED",
            "severity": "INFO",
            "message": (
                "Super/group TPD premiums are based on the fund's pooled group rating "
                "(age/occupation bands), not individual underwriting. Premiums are typically "
                "age-stepped and deducted from the member's super balance."
            ),
        })

    crossover_note = None
    if age is not None:
        if premium_type == "STEPPED" and age >= 45:
            crossover_note = (
                f"At age {age}, stepped premiums escalate significantly with each year "
                "(~6% p.a. increase). Consider whether a level premium option provides "
                "better long-term value and reduces lapse risk from premium shock."
            )
            flags.append({
                "code": "STEPPED_PREMIUM_HIGH_AGE_ESCALATION",
                "severity": "WARNING",
                "message": crossover_note,
            })
        elif premium_type == "LEVEL" and age < 40:
            flags.append({
                "code": "LEVEL_PREMIUM_YOUNG_OVERSHOOTING",
                "severity": "INFO",
                "message": (
                    f"At age {age}, stepped premiums are typically more cost-effective in the "
                    "short term. Level premiums may be overpaying now for future certainty. "
                    "This is appropriate if long-term retention is the goal."
                ),
            })

    affordability: dict = {"band": "UNKNOWN", "premium_to_income_pct": None}
    if annual_premium and annual_premium > 0 and annual_gross_income and annual_gross_income > 0:
        ratio = annual_premium / annual_gross_income
        if ratio <= AFFORDABILITY_BANDS["COMFORTABLE"]:
            band = "COMFORTABLE"
        elif ratio <= AFFORDABILITY_BANDS["MANAGEABLE"]:
            band = "MANAGEABLE"
        elif ratio <= AFFORDABILITY_BANDS["STRETCHED"]:
            band = "STRETCHED"
        else:
            band = "UNAFFORDABLE"
            flags.append({
                "code": "PREMIUM_UNAFFORDABLE",
                "severity": "WARNING",
                "message": (
                    f"Annual premium of ${annual_premium:,.0f} represents "
                    f"{ratio*100:.1f}% of gross income — above the 7% stretched threshold. "
                    "Review sum insured or premium type to improve affordability."
                ),
            })
        affordability = {
            "band": band,
            "annual_premium_aud": round(annual_premium),
            "annual_gross_income_aud": round(annual_gross_income),
            "premium_to_income_pct": round(ratio * 100, 2),
        }

    return {
        "premium_type": premium_type,
        "in_super": in_super,
        "annual_premium_aud": annual_premium,
        "affordability": affordability,
        "stepped_description": (
            "Stepped: premium increases with age (~6% p.a.) — cheaper when young, "
            "progressively more expensive; risk of lapse from premium shock at older ages."
        ),
        "level_description": (
            "Level: premium is fixed (or slowly grows with CPI) — more expensive when "
            "young, provides long-term cost certainty and reduces lapse risk."
        ),
        "approximate_annual_stepped_increase_pct": STEPPED_ANNUAL_INCREASE_FACTOR * 100,
        "crossover_note": crossover_note,
        "flags": flags,
    }


def _eval_lapse_reinstatement(
    policy_lapsed: bool,
    months_since_lapse: int | None,
    in_super: bool,
    account_inactive_months: int,
) -> dict:
    """
    Evaluate lapse status and reinstatement options.

    Life Code: insurers must give adequate notice before lapse.
    Reinstatement: typically within 3 years (back-payment + health evidence).
    Super: PYS automatic switch-off after 16 months inactivity.
    """
    flags = []

    if policy_lapsed:
        if months_since_lapse is not None:
            reinstatement_months = REINSTATEMENT_WINDOW_YEARS * 12
            within_window = months_since_lapse <= reinstatement_months
            flags.append({
                "code": "POLICY_LAPSED" if within_window else "POLICY_LAPSED_WINDOW_EXPIRED",
                "severity": "CRITICAL",
                "message": (
                    f"Policy lapsed {months_since_lapse} month(s) ago. "
                    + (
                        f"Reinstatement is possible within the {REINSTATEMENT_WINDOW_YEARS}-year "
                        "window — contact insurer immediately to reinstate with back-payment of "
                        "premiums and evidence of good health."
                        if within_window else
                        f"Reinstatement window ({REINSTATEMENT_WINDOW_YEARS} years) has expired. "
                        "A new policy application with full underwriting is required."
                    )
                ),
            })
        else:
            flags.append({
                "code": "POLICY_LAPSED_DURATION_UNKNOWN",
                "severity": "CRITICAL",
                "message": "Policy is lapsed. Determine time since lapse to assess reinstatement eligibility.",
            })

    if in_super and account_inactive_months >= INACTIVITY_THRESHOLD_MONTHS:
        flags.append({
            "code": "SUPER_COVER_PYS_SWITCHED_OFF",
            "severity": "CRITICAL",
            "message": (
                f"Super account inactive for {account_inactive_months} months exceeds "
                f"the {INACTIVITY_THRESHOLD_MONTHS}-month PYS threshold. "
                "TPD cover in super may have been automatically cancelled. "
                "Confirm with the trustee and lodge an opt-in election if cover is still required."
            ),
        })

    return {
        "policy_lapsed": policy_lapsed,
        "months_since_lapse": months_since_lapse,
        "reinstatement_window_years": REINSTATEMENT_WINDOW_YEARS,
        "reinstatement_requirements": [
            f"Contact insurer within {REINSTATEMENT_WINDOW_YEARS} years of lapse",
            "Back-payment of all unpaid premiums (with interest if required)",
            "New evidence of good health (medical declaration or exam)",
            "Re-underwriting may apply — existing exclusions or loadings can be varied",
        ],
        "life_code_lapse_notice": (
            "Under the Life Insurance Code of Practice, insurers must provide members "
            "with written notice before a policy lapses due to non-payment. "
            "If adequate notice was not given, the lapse may be contestable."
        ),
        "flags": flags,
    }


def _generate_recommendation(
    definition_quality: str,
    sis_compliant: bool,
    in_super: bool,
    shortfall_severity: str,
    approval_rate: float,
    affordability_band: str,
    underwriting_risk: str,
    policy_lapsed: bool,
    wants_replacement: bool | None,
    wants_retention: bool | None,
    is_grandfathered: bool,
    age: int | None,
) -> dict:
    """
    Generate overall TPD policy recommendation.

    Decision logic (from tpd_insurance_policy.md):
    1. Lapsed policy → REINSTATE or PURCHASE_NEW
    2. SIS non-compliant in super → RESTRUCTURE_TO_RETAIL (unless grandfathered)
    3. ADL definition → REPLACE_WITH_BETTER_DEFINITION (high decline risk)
    4. Significant/critical shortfall → SUPPLEMENT or REPLACE
    5. Own-occ grandfathered in super → RETAIN (highly valuable, cannot be re-issued)
    6. Adequate cover, compliant, appropriate definition → RETAIN
    """
    if policy_lapsed:
        return {
            "type": "REINSTATE_OR_PURCHASE_NEW",
            "summary": (
                "Policy has lapsed. Priority action is to either reinstate the existing "
                "policy or arrange new TPD cover as soon as possible to avoid uninsured exposure."
            ),
            "reasons": ["Policy is lapsed — client currently has no TPD protection."],
            "risks": [
                "Any disability event during the lapse period is uninsured.",
                "Full underwriting is required if reinstatement window has expired.",
            ],
            "actions": [
                "Contact insurer immediately to determine reinstatement eligibility.",
                "If within 3 years, back-pay premiums and provide health evidence.",
                "If window expired, apply for new TPD cover with full underwriting.",
            ],
            "urgency": "CRITICAL",
        }

    if not sis_compliant and in_super and not is_grandfathered:
        return {
            "type": "RESTRUCTURE_TO_RETAIL",
            "summary": (
                "Existing TPD cover in super is non-conforming under SIS Reg 4.07D. "
                "The trustee must not continue issuing this cover. Restructuring to a "
                "retail policy outside super is required."
            ),
            "reasons": [
                "TPD definition is non-conforming for new super policies after 1 July 2014.",
                "SIS Reg 4.07D prohibits new non-conforming insurance in superannuation.",
            ],
            "risks": [
                "Trustee may be in breach of SIS Act obligations.",
                "APRA may require corrective action if non-conforming cover is identified at audit.",
            ],
            "actions": [
                "Obtain retail TPD policy with equivalent or better definition outside super.",
                "Once retail cover is confirmed, request cancellation of non-conforming super cover.",
                "Document the restructuring recommendation in the Statement of Advice.",
            ],
            "urgency": "HIGH",
        }

    if in_super and is_grandfathered and definition_quality in ("EXCELLENT", "GOOD"):
        return {
            "type": "RETAIN_GRANDFATHERED",
            "summary": (
                "Existing TPD cover is a valuable grandfathered own-occupation policy inside super "
                "that cannot be re-issued. Retention is strongly recommended."
            ),
            "reasons": [
                "Grandfathered own-occupation TPD in super is no longer available for new members.",
                "Own-occupation definition provides the highest claim approval rate (~88%).",
                "Replacing would result in downgrade to any-occupation definition.",
            ],
            "risks": [
                "Any restructuring or cancellation permanently forfeits grandfathered status.",
            ],
            "actions": [
                "Ensure premiums are maintained to avoid lapse of grandfathered cover.",
                "Do not agree to any policy restructure or transfer that would cancel this cover.",
                "Supplement with retail cover for additional sum insured if a shortfall exists.",
            ],
            "urgency": "LOW",
        }

    if definition_quality == "POOR" and approval_rate < 0.50:
        return {
            "type": "REPLACE_WITH_BETTER_DEFINITION",
            "summary": (
                "Existing TPD policy has an ADL or low-quality definition with a high claim "
                "decline risk. Replacement with an any-occupation or own-occupation policy "
                "is strongly recommended."
            ),
            "reasons": [
                f"Current definition has ~{round((1-approval_rate)*100)}% decline rate per ASIC Report 633.",
                "ADL definitions are specifically criticised by ASIC and APRA for poor consumer outcomes.",
            ],
            "risks": [
                "Client may believe they are covered but face claim denial when needed most.",
                "Underinsurance risk despite paying premiums.",
            ],
            "actions": [
                "Obtain replacement TPD with any-occupation or own-occupation definition.",
                "Do not cancel existing cover until replacement is confirmed in-force.",
                "Disclose all health changes since original policy was issued.",
            ],
            "urgency": "HIGH",
        }

    if shortfall_severity in ("SIGNIFICANT", "CRITICAL"):
        rec_type = "SUPPLEMENT_EXISTING" if wants_retention else "REPLACE_WITH_HIGHER_COVER"
        return {
            "type": rec_type,
            "summary": (
                f"Existing TPD cover has a {shortfall_severity.lower()} shortfall relative to "
                "calculated need. Additional cover is required."
            ),
            "reasons": [
                f"Calculated shortfall is {shortfall_severity.lower()}.",
                "Existing sum insured does not adequately cover income replacement, rehab, and care costs.",
            ],
            "risks": [
                "A TPD event would leave the client significantly underinsured.",
                "Financial hardship is likely without adequate lump-sum cover.",
            ],
            "actions": [
                "Calculate full TPD need and arrange supplementary or replacement cover.",
                "Consider retail own-occupation TPD to close the gap and improve definition quality.",
                "Review sum insured annually or after major life events.",
            ],
            "urgency": "HIGH",
        }

    if shortfall_severity == "MODERATE":
        return {
            "type": "SUPPLEMENT_EXISTING",
            "summary": "Existing TPD cover has a moderate shortfall. Supplementing is recommended.",
            "reasons": ["Coverage gap between sum insured and calculated TPD need."],
            "risks": ["Partial underinsurance if a TPD event occurs."],
            "actions": [
                "Arrange supplementary retail TPD cover to close the gap.",
                "Reassess need after life events (mortgage increase, family changes).",
            ],
            "urgency": "MEDIUM",
        }

    # Adequate cover
    return {
        "type": "RETAIN_EXISTING",
        "summary": (
            "Existing TPD cover appears adequate and compliant. Retention is recommended "
            "subject to annual review."
        ),
        "reasons": [
            "Sum insured is adequate relative to calculated TPD need.",
            "Definition is compliant and of acceptable quality.",
            "Policy is in-force and meeting premium obligations.",
        ],
        "risks": [
            "Sum insured may erode in real terms without indexation.",
            "Life events may increase TPD need over time.",
        ],
        "actions": [
            "Review TPD cover annually or after major life events.",
            "Confirm indexation is in place to maintain real value.",
            "Ensure definition remains appropriate as occupation changes.",
        ],
        "urgency": "LOW",
    }


def _build_missing_info(
    age: int | None,
    annual_gross_income: float | None,
    sum_insured: float,
    definition: str,
    in_super: bool | None,
) -> dict:
    blocking = []
    optional = []

    if age is None:
        blocking.append({
            "field": "client.age",
            "question": "What is the client's age? (Required for eligibility and tax treatment.)",
        })
    if annual_gross_income is None:
        blocking.append({
            "field": "client.annualGrossIncome",
            "question": "What is the client's annual gross income (AUD)? (Required for TPD need calculation.)",
        })
    if sum_insured <= 0:
        blocking.append({
            "field": "existingPolicy.tpdSumInsured",
            "question": "What is the existing TPD sum insured (AUD)?",
        })
    if definition == "UNKNOWN":
        blocking.append({
            "field": "existingPolicy.tpdDefinition",
            "question": (
                "What is the TPD definition type? "
                "(OWN_OCCUPATION / MODIFIED_OWN_OCCUPATION / ANY_OCCUPATION / "
                "ACTIVITIES_OF_DAILY_LIVING / HOME_DUTIES)"
            ),
        })
    if in_super is None:
        blocking.append({
            "field": "existingPolicy.inSuper",
            "question": "Is the TPD cover held inside superannuation or as a retail policy?",
        })

    optional.append({
        "field": "client.yearsToRetirement",
        "question": "How many years until the client plans to retire? (Improves TPD need accuracy.)",
    })
    optional.append({
        "field": "existingPolicy.premiumType",
        "question": "Is the premium stepped or level? (Required for premium structure analysis.)",
    })
    optional.append({
        "field": "health.existingMedicalConditions",
        "question": "Does the client have any pre-existing medical conditions? (For exclusion assessment.)",
    })

    return {
        "blocking_questions": blocking,
        "optional_questions": optional,
        "total_blocking": len(blocking),
        "analysis_completeness": "PARTIAL" if blocking else "SUFFICIENT",
    }


# =============================================================================
# TOOL IMPLEMENTATION
# =============================================================================

class TPDPolicyAssessmentTool(BaseTool):
    """
    TPD Policy Definition, Placement & Claims Assessment tool.

    Covers:
    - TPD definition quality ranking and SIS compliance (own-occ / any-occ / ADL)
    - Super vs retail placement analysis (SIS Reg 4.07C/D, s68AA, SPS 250)
    - Tax impact analysis (retail tax-free vs super Div. 295 lump sum)
    - TPD lump-sum need calculation
    - Claims eligibility and dual-test for super claims
    - Standard and personal exclusions
    - Premium structure evaluation (stepped vs level, affordability)
    - Lapse and reinstatement rules (3-year window)
    - Dispute resolution pathway (IDR → AFCA $3M)
    - Structured recommendation with urgency rating
    """

    name = "tpd_policy_assessment"
    version = ENGINE_VERSION
    description = (
        "Assess a Total and Permanent Disability (TPD) policy: evaluate definition quality "
        "(own-occupation vs any-occupation vs ADL), super vs retail placement compliance "
        "(SIS Reg 4.07C/D, SPS 250), tax treatment, claims eligibility, exclusions, "
        "premium structure, lapse/reinstatement rules, and generate a structured recommendation."
    )

    def get_input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "client": {
                    "type": "object",
                    "properties": {
                        "age": {"type": "integer"},
                        "dateOfBirth": {"type": "string"},
                        "annualGrossIncome": {"type": "number"},
                        "annualNetIncome": {"type": "number"},
                        "occupationClass": {
                            "type": "string",
                            "enum": [
                                "CLASS_1_WHITE_COLLAR", "CLASS_2_LIGHT_BLUE",
                                "CLASS_3_BLUE_COLLAR", "CLASS_4_HAZARDOUS", "UNKNOWN",
                            ],
                        },
                        "occupation": {"type": "string"},
                        "isSmoker": {"type": "boolean"},
                        "yearsToRetirement": {"type": "number"},
                    },
                },
                "existingPolicy": {
                    "type": "object",
                    "properties": {
                        "hasExistingPolicy": {"type": "boolean"},
                        "insurerName": {"type": "string"},
                        "tpdSumInsured": {"type": "number"},
                        "annualPremium": {"type": "number"},
                        "premiumType": {"type": "string", "enum": ["STEPPED", "LEVEL", "UNKNOWN"]},
                        "tpdDefinition": {
                            "type": "string",
                            "enum": [
                                "OWN_OCCUPATION", "MODIFIED_OWN_OCCUPATION",
                                "ANY_OCCUPATION", "ACTIVITIES_OF_DAILY_LIVING",
                                "HOME_DUTIES", "UNKNOWN",
                            ],
                        },
                        "inSuper": {"type": "boolean"},
                        "fundType": {
                            "type": "string",
                            "enum": ["MYSUPER", "CHOICE", "SMSF", "DEFINED_BENEFIT", "UNKNOWN"],
                        },
                        "isMySuperProduct": {"type": "boolean"},
                        "isGrandfathered": {
                            "type": "boolean",
                            "description": "True if cover pre-dates 1 July 2014 SIS Reg 4.07D cutoff",
                        },
                        "policyLapsed": {"type": "boolean"},
                        "monthsSinceLapse": {"type": "integer"},
                        "policyAgeYears": {"type": "number"},
                        "accountInactiveMonths": {"type": "integer"},
                        "hasOptedIn": {
                            "type": "boolean",
                            "description": "True if member has lodged PYS opt-in election",
                        },
                        "taxableComponentPct": {
                            "type": "number",
                            "description": "Fraction of super benefit that is taxable (0.0–1.0)",
                        },
                    },
                },
                "proposedPolicy": {
                    "type": "object",
                    "properties": {
                        "insurerName": {"type": "string"},
                        "tpdSumInsured": {"type": "number"},
                        "annualPremium": {"type": "number"},
                        "premiumType": {"type": "string", "enum": ["STEPPED", "LEVEL", "UNKNOWN"]},
                        "tpdDefinition": {"type": "string"},
                        "inSuper": {"type": "boolean"},
                    },
                },
                "health": {
                    "type": "object",
                    "properties": {
                        "existingMedicalConditions": {"type": "array", "items": {"type": "string"}},
                        "hazardousActivities": {"type": "array", "items": {"type": "string"}},
                        "isSmoker": {"type": "boolean"},
                    },
                },
                "financialPosition": {
                    "type": "object",
                    "properties": {
                        "mortgageBalance": {"type": "number"},
                        "otherDebts": {"type": "number"},
                        "liquidAssets": {"type": "number"},
                        "monthlyExpenses": {"type": "number"},
                    },
                },
                "goals": {
                    "type": "object",
                    "properties": {
                        "wantsReplacement": {"type": "boolean"},
                        "wantsRetention": {"type": "boolean"},
                        "wantsOwnOccupation": {"type": "boolean"},
                        "affordabilityIsConcern": {"type": "boolean"},
                        "prioritisesDefinitionQuality": {"type": "boolean"},
                        "prioritisesClaimsReputation": {"type": "boolean"},
                        "includeCaresCosts": {"type": "boolean"},
                    },
                },
            },
        }

    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:  # noqa: C901
        # ------------------------------------------------------------------
        # 1. Extract inputs
        # ------------------------------------------------------------------
        client   = input_data.get("client") or {}
        existing = input_data.get("existingPolicy") or {}
        proposed = input_data.get("proposedPolicy") or {}
        health   = input_data.get("health") or {}
        financial = input_data.get("financialPosition") or {}
        goals    = input_data.get("goals") or {}

        # Client
        age: int | None = client.get("age")
        dob_str = client.get("dateOfBirth")
        if age is None and dob_str:
            dob = _safe_parse_date(dob_str)
            if dob:
                age = _age_from_dob(dob)

        annual_gross_income: float | None = client.get("annualGrossIncome")
        years_to_retirement: float = float(client.get("yearsToRetirement") or
                                           (max(0, (65 - age)) if age else 20))
        occupation_class: str = client.get("occupationClass", "UNKNOWN")
        is_smoker: bool = bool(client.get("isSmoker") or health.get("isSmoker", False))

        # Existing policy
        has_existing: bool = bool(existing.get("hasExistingPolicy", False))
        tpd_sum_insured: float = float(existing.get("tpdSumInsured") or 0)
        annual_premium: float | None = existing.get("annualPremium")
        premium_type: str | None = existing.get("premiumType")
        definition: str = existing.get("tpdDefinition", "UNKNOWN")
        in_super: bool | None = existing.get("inSuper")
        fund_type: str = existing.get("fundType", "UNKNOWN")
        is_mysuper: bool = bool(existing.get("isMySuperProduct", False))
        is_grandfathered: bool = bool(existing.get("isGrandfathered", False))
        policy_lapsed: bool = bool(existing.get("policyLapsed", False))
        months_since_lapse: int | None = existing.get("monthsSinceLapse")
        policy_age_years: float = float(existing.get("policyAgeYears") or 0)
        account_inactive_months: int = int(existing.get("accountInactiveMonths") or 0)
        has_opted_in: bool = bool(existing.get("hasOptedIn", False))
        taxable_component_pct: float = float(existing.get("taxableComponentPct") or 0.85)

        # Financial
        mortgage: float = float(financial.get("mortgageBalance") or 0)
        other_debts: float = float(financial.get("otherDebts") or 0)
        liquid_assets: float = float(financial.get("liquidAssets") or 0)

        # Health
        medical_conditions: list[str] = health.get("existingMedicalConditions") or []
        hazardous_activities: list[str] = health.get("hazardousActivities") or []

        # Goals
        wants_replacement: bool | None = goals.get("wantsReplacement")
        wants_retention: bool | None = goals.get("wantsRetention")
        include_care_costs: bool = bool(goals.get("includeCaresCosts", True))

        # Default in_super to False if not specified
        in_super_bool: bool = bool(in_super) if in_super is not None else False

        # ------------------------------------------------------------------
        # 2. Run analysis modules
        # ------------------------------------------------------------------

        definition_eval = _eval_tpd_definition(
            definition=definition,
            in_super=in_super_bool,
            is_grandfathered=is_grandfathered,
        )

        super_placement = _eval_super_placement(
            in_super=in_super_bool,
            definition=definition,
            is_grandfathered=is_grandfathered,
            member_age=age,
            account_inactive_months=account_inactive_months,
            sum_insured=tpd_sum_insured,
            fund_type=fund_type,
            is_mysuper=is_mysuper,
            has_opted_in=has_opted_in,
        )

        tax_impact = _calc_tax_impact(
            in_super=in_super_bool,
            sum_insured=tpd_sum_insured,
            taxable_component_pct=taxable_component_pct,
            member_age=age,
        )

        tpd_need = _calc_tpd_need(
            annual_gross_income=annual_gross_income,
            years_to_retirement=years_to_retirement,
            mortgage_balance=mortgage,
            other_debts=other_debts,
            liquid_assets=liquid_assets,
            existing_tpd_cover=tpd_sum_insured if has_existing else 0.0,
            include_care_costs=include_care_costs,
        )

        claims_eligibility = _eval_claims_eligibility(
            definition=definition,
            in_super=in_super_bool,
            medical_conditions=medical_conditions,
            occupation_class=occupation_class,
            sum_insured=tpd_sum_insured,
            policy_age_years=policy_age_years,
        )

        exclusions_eval = _eval_exclusions(
            hazardous_activities=hazardous_activities,
            medical_conditions=medical_conditions,
            is_smoker=is_smoker,
        )

        premium_eval = _eval_premium_structure(
            premium_type=premium_type,
            annual_premium=annual_premium,
            annual_gross_income=annual_gross_income,
            age=age,
            in_super=in_super_bool,
        )

        lapse_eval = _eval_lapse_reinstatement(
            policy_lapsed=policy_lapsed,
            months_since_lapse=months_since_lapse,
            in_super=in_super_bool,
            account_inactive_months=account_inactive_months,
        )

        # Proposed policy comparison
        proposed_comparison: dict | None = None
        if proposed.get("tpdSumInsured") or proposed.get("tpdDefinition"):
            prop_def = proposed.get("tpdDefinition", "UNKNOWN")
            prop_si = float(proposed.get("tpdSumInsured") or 0)
            prop_in_super = bool(proposed.get("inSuper", False))
            prop_def_eval = _eval_tpd_definition(prop_def, prop_in_super, False)
            prop_tax = _calc_tax_impact(prop_in_super, prop_si, taxable_component_pct, age)
            prop_premium_eval = _eval_premium_structure(
                proposed.get("premiumType"),
                proposed.get("annualPremium"),
                annual_gross_income,
                age,
                prop_in_super,
            )
            definition_upgrade = (
                TPD_DEFINITION_RANK.get(prop_def, 0) > TPD_DEFINITION_RANK.get(definition, 0)
            )
            proposed_comparison = {
                "proposed_insurer": proposed.get("insurerName"),
                "proposed_sum_insured_aud": prop_si,
                "proposed_definition": prop_def,
                "proposed_in_super": prop_in_super,
                "proposed_annual_premium_aud": proposed.get("annualPremium"),
                "definition_evaluation": prop_def_eval,
                "tax_impact": prop_tax,
                "premium_evaluation": prop_premium_eval,
                "definition_upgrade": definition_upgrade,
                "definition_rank_change": (
                    TPD_DEFINITION_RANK.get(prop_def, 0) - TPD_DEFINITION_RANK.get(definition, 0)
                ),
            }

        # Underwriting risk
        occ_risk = OCCUPATION_RISK_MAP.get(occupation_class, "MEDIUM")
        underwriting_risk_level = occ_risk
        if is_smoker and underwriting_risk_level in ("LOW", "MEDIUM"):
            underwriting_risk_level = "HIGH"
        if age and age > 55 and underwriting_risk_level == "LOW":
            underwriting_risk_level = "MEDIUM"

        # ------------------------------------------------------------------
        # 3. Recommendation
        # ------------------------------------------------------------------
        recommendation = _generate_recommendation(
            definition_quality=definition_eval["definition_quality"],
            sis_compliant=definition_eval["sis_compliant"],
            in_super=in_super_bool,
            shortfall_severity=tpd_need["shortfall_severity"],
            approval_rate=DEFINITION_APPROVAL_RATE.get(definition, 0.75),
            affordability_band=premium_eval["affordability"].get("band", "UNKNOWN"),
            underwriting_risk=underwriting_risk_level,
            policy_lapsed=policy_lapsed,
            wants_replacement=wants_replacement,
            wants_retention=wants_retention,
            is_grandfathered=is_grandfathered,
            age=age,
        )

        # ------------------------------------------------------------------
        # 4. Aggregate compliance flags
        # ------------------------------------------------------------------
        all_flags: list[dict] = []
        all_flags.extend(definition_eval.get("flags", []))
        all_flags.extend(super_placement.get("flags", []))
        all_flags.extend(claims_eligibility.get("flags", []))
        all_flags.extend(premium_eval.get("flags", []))
        all_flags.extend(lapse_eval.get("flags", []))

        # ------------------------------------------------------------------
        # 5. Member actions
        # ------------------------------------------------------------------
        member_actions = list(recommendation.get("actions", []))
        if not policy_lapsed and not has_existing:
            member_actions.append(
                "Obtain quotes for retail TPD with own-occupation definition if occupation class permits."
            )
        if in_super_bool and not is_grandfathered:
            member_actions.append(
                "Confirm TPD definition is any-occupation (or better) to comply with SIS Reg 4.07D."
            )

        # ------------------------------------------------------------------
        # 6. Missing info
        # ------------------------------------------------------------------
        missing_info = _build_missing_info(
            age=age,
            annual_gross_income=annual_gross_income,
            sum_insured=tpd_sum_insured,
            definition=definition,
            in_super=in_super,
        )

        # ------------------------------------------------------------------
        # 7. Assemble result
        # ------------------------------------------------------------------
        return {
            "tool": self.name,
            "version": self.version,
            "definition_evaluation": definition_eval,
            "super_placement": super_placement,
            "tax_impact": tax_impact,
            "tpd_need": tpd_need,
            "claims_eligibility": claims_eligibility,
            "exclusions": exclusions_eval,
            "premium_structure": premium_eval,
            "lapse_reinstatement": lapse_eval,
            "proposed_policy_comparison": proposed_comparison,
            "underwriting_risk": {
                "overall_risk_level": underwriting_risk_level,
                "occupation_class": occupation_class,
                "occupation_risk": occ_risk,
                "is_smoker": is_smoker,
            },
            "recommendation": recommendation,
            "compliance_flags": all_flags,
            "member_actions": member_actions,
            "missing_info_questions": missing_info,
            "regulatory_notes": {
                "sis_reg_407c_aal_aud": AUTO_ACCEPTANCE_LIMIT_AUD,
                "sis_reg_407d_cutoff": f"{NON_CONFORMING_CUTOFF_YEAR}-{NON_CONFORMING_CUTOFF_MONTH:02d}-01",
                "mysuper_min_age": MYSUPER_MIN_AGE,
                "mysuper_max_age": MYSUPER_MAX_AGE,
                "inactivity_switch_off_months": INACTIVITY_THRESHOLD_MONTHS,
                "contestability_years": CONTESTABILITY_YEARS,
                "reinstatement_window_years": REINSTATEMENT_WINDOW_YEARS,
                "afca_max_claim_aud": AFCA_MAX_CLAIM_AUD,
                "sps_250_effective_date": SPS_250_EFFECTIVE_DATE,
                "super_tpd_tax_under_60_pct": SUPER_TPD_TAX_UNDER_60 * 100,
                "super_tpd_tax_over_60_pct": SUPER_TPD_TAX_OVER_60 * 100,
            },
        }
