"""
Canonical comparison fact keys (extensible).

New tools should map outputs to these keys where possible; unknown keys can be
added with metadata in engine.COMPARISON_KEY_META.
"""

LIFE_COVER_AMOUNT = "life_cover_amount"
TPD_COVER_AMOUNT = "tpd_cover_amount"
TRAUMA_COVER_AMOUNT = "trauma_cover_amount"
IP_MONTHLY_BENEFIT = "ip_monthly_benefit"
IP_REPLACEMENT_RATIO = "ip_replacement_ratio"
WAITING_PERIOD = "waiting_period"
BENEFIT_PERIOD = "benefit_period"
ANNUAL_PREMIUM = "annual_premium"
MONTHLY_PREMIUM = "monthly_premium"
FUNDING_SOURCE = "funding_source"
OWNERSHIP_STRUCTURE = "ownership_structure"
INSIDE_SUPER = "inside_super"
TAX_DEDUCTIBLE = "tax_deductible"
UNDERWRITING_REQUIRED = "underwriting_required"
REPLACEMENT_INVOLVED = "replacement_involved"
INSURER_NAME = "insurer_name"
FUND_NAME = "fund_name"
PREMIUM_TYPE = "premium_type"
OWN_OCC_TPD = "own_occupation_tpd"
ANY_OCC_TPD = "any_occupation_tpd"
ADEQUACY_SCORE = "adequacy_score"
AFFORDABILITY_SCORE = "affordability_score"
TAX_EFFICIENCY_SCORE = "tax_efficiency_score"
FLEXIBILITY_SCORE = "flexibility_score"
IMPLEMENTATION_EASE_SCORE = "implementation_ease_score"
CLAIMS_PRACTICALITY_SCORE = "claims_practicality_score"
RECOMMENDATION_TYPE = "recommendation_type"
LEGAL_OR_POLICY_STATUS = "legal_or_policy_status"

CANONICAL_KEYS = frozenset({
    LIFE_COVER_AMOUNT,
    TPD_COVER_AMOUNT,
    TRAUMA_COVER_AMOUNT,
    IP_MONTHLY_BENEFIT,
    IP_REPLACEMENT_RATIO,
    WAITING_PERIOD,
    BENEFIT_PERIOD,
    ANNUAL_PREMIUM,
    MONTHLY_PREMIUM,
    FUNDING_SOURCE,
    OWNERSHIP_STRUCTURE,
    INSIDE_SUPER,
    TAX_DEDUCTIBLE,
    UNDERWRITING_REQUIRED,
    REPLACEMENT_INVOLVED,
    INSURER_NAME,
    FUND_NAME,
    PREMIUM_TYPE,
    OWN_OCC_TPD,
    ANY_OCC_TPD,
    ADEQUACY_SCORE,
    AFFORDABILITY_SCORE,
    TAX_EFFICIENCY_SCORE,
    FLEXIBILITY_SCORE,
    IMPLEMENTATION_EASE_SCORE,
    CLAIMS_PRACTICALITY_SCORE,
    RECOMMENDATION_TYPE,
    LEGAL_OR_POLICY_STATUS,
})
