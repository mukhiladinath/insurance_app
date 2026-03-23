// =============================================================================
// CONSTANTS — purchaseRetainLifeTPDPolicy
// All threshold values, scoring weights, and metadata hardcoded here.
// =============================================================================

import { TPDDefinitionType, OccupationClass } from './purchaseRetainLifeTPDPolicy.enums';

// =============================================================================
// NEED CALCULATION DEFAULTS
// =============================================================================

/**
 * Default final expenses allowance in AUD.
 * Covers funeral costs, estate administration, legal fees.
 * Conservatively set; adviser may override per client.
 */
export const DEFAULT_FINAL_EXPENSES_AUD = 25_000;

/**
 * Default per-child education funding allowance in AUD.
 * Represents an approximate remaining education cost buffer to age 18.
 */
export const DEFAULT_EDUCATION_FUNDING_PER_CHILD_AUD = 50_000;

/**
 * Income replacement multiplier for life insurance.
 * Used as a fallback when years-to-retirement is unknown.
 * Represents approximate years of income to replace.
 */
export const DEFAULT_INCOME_REPLACEMENT_YEARS = 10;

/**
 * Medical / rehabilitation buffer for TPD claims.
 * Covers immediate and ongoing medical costs, rehabilitation, specialist care.
 */
export const DEFAULT_MEDICAL_REHAB_BUFFER_AUD = 75_000;

/**
 * Home modification buffer for TPD claimants who require physical adaptations.
 */
export const DEFAULT_HOME_MODIFICATION_BUFFER_AUD = 50_000;

/**
 * Ongoing care / lifestyle support buffer for TPD.
 * Represents 2 years of approximate personal care cost allowance.
 */
export const DEFAULT_ONGOING_CARE_BUFFER_AUD = 60_000;

/**
 * Assumed real discount/growth rate for TPD income capitalisation formula.
 * net of inflation. Conservative rate for long-horizon calculations.
 */
export const TPD_CAPITALISATION_RATE = 0.05;

/**
 * Minimum income replacement percentage assumed for life insurance calculation
 * if a specific target is not provided.
 */
export const DEFAULT_INCOME_REPLACEMENT_PERCENT = 1.0; // 100% of income

// =============================================================================
// SHORTFALL THRESHOLDS (AUD)
// =============================================================================

export const SHORTFALL_THRESHOLDS = {
  NONE: 0,
  MINOR: 50_000,
  MODERATE: 200_000,
  SIGNIFICANT: 500_000,
  // Above SIGNIFICANT = CRITICAL
} as const;

// =============================================================================
// AFFORDABILITY THRESHOLDS
// =============================================================================

/** Premium as a % of gross income — upper bounds for each assessment band. */
export const AFFORDABILITY_INCOME_BANDS = {
  COMFORTABLE: 0.01,  // < 1%
  MANAGEABLE: 0.03,   // 1–3%
  STRETCHED: 0.05,    // 3–5%
  UNAFFORDABLE: 1.0,  // > 5%
} as const;

/** Premium as a % of net income — tighter threshold. */
export const AFFORDABILITY_NET_INCOME_BANDS = {
  COMFORTABLE: 0.015,
  MANAGEABLE: 0.04,
  STRETCHED: 0.07,
  UNAFFORDABLE: 1.0,
} as const;

/**
 * Stepped premium projection factor per year.
 * Represents approximate year-on-year premium increase for age-stepped policies.
 * Actual insurer rates vary; this is a conservative approximation.
 */
export const STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR = 0.06; // ~6% p.a. increase

// =============================================================================
// TPD DEFINITION RANKING
// Higher rank = more favourable to the insured.
// Used in comparison logic to determine whether new policy worsens the definition.
// =============================================================================

export const TPD_DEFINITION_RANK: Record<TPDDefinitionType, number> = {
  [TPDDefinitionType.OWN_OCCUPATION]: 5,
  [TPDDefinitionType.MODIFIED_OWN_OCCUPATION]: 4,
  [TPDDefinitionType.ANY_OCCUPATION]: 3,
  [TPDDefinitionType.ACTIVITIES_OF_DAILY_LIVING]: 2,
  [TPDDefinitionType.HOME_DUTIES]: 1,
  [TPDDefinitionType.UNKNOWN]: 0,
};

// =============================================================================
// OCCUPATION CLASS RISK CONTRIBUTIONS
// =============================================================================

/** Underwriting risk contribution by occupation class. */
export const OCCUPATION_RISK_MAP: Record<OccupationClass, 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'> = {
  [OccupationClass.CLASS_1_WHITE_COLLAR]: 'LOW',
  [OccupationClass.CLASS_2_LIGHT_BLUE]: 'MEDIUM',
  [OccupationClass.CLASS_3_BLUE_COLLAR]: 'HIGH',
  [OccupationClass.CLASS_4_HAZARDOUS]: 'CRITICAL',
  [OccupationClass.UNKNOWN]: 'MEDIUM',
};

// =============================================================================
// BMI CLASSIFICATION BOUNDARIES
// =============================================================================

export const BMI_THRESHOLDS = {
  UNDERWEIGHT_MAX: 18.5,
  NORMAL_MAX: 25.0,
  OVERWEIGHT_MAX: 30.0,
  OBESE_MAX: 35.0,
  // Above 35 = SEVERELY_OBESE
} as const;

// =============================================================================
// POLICY COMPARISON DIMENSION WEIGHTS
// Must sum to 1.0
// =============================================================================

export const COMPARISON_WEIGHTS = {
  premium: 0.25,
  sumInsured: 0.20,
  tpdDefinition: 0.25,
  exclusions: 0.15,
  loadings: 0.10,
  flexibility: 0.05,
} as const;

// =============================================================================
// COMPARISON OUTCOME THRESHOLDS (weighted score delta)
// =============================================================================

/** Minimum weighted advantage for the new policy to qualify as MATERIALLY better. */
export const COMPARISON_MATERIALLY_BETTER_THRESHOLD = 0.15;
/** Minimum weighted advantage to qualify as MARGINALLY better. */
export const COMPARISON_MARGINALLY_BETTER_THRESHOLD = 0.05;

// =============================================================================
// RULE IDs
// =============================================================================

export const RULE_IDS = {
  // Core data rules
  MISSING_CRITICAL_DATA: 'R-001',
  UNDERWRITING_INCOMPLETE: 'R-002',
  EXISTING_POLICY_DATA_INCOMPLETE: 'R-003',
  // Hard block rules
  BLOCK_REPLACEMENT_UNDERWRITING: 'R-004',
  BLOCK_REPLACEMENT_MATERIALLY_WORSE: 'R-005',
  BLOCK_REPLACEMENT_TPD_DEFINITION: 'R-006',
  BLOCK_REPLACEMENT_REPLACEMENT_RISK: 'R-007',
  // Positive recommendation rules
  PURCHASE_NEW_NO_EXISTING: 'R-008',
  RETAIN_LOW_SHORTFALL: 'R-009',
  SUPPLEMENT_POLICY_STRONG: 'R-010',
  REDUCE_COVER_AFFORDABILITY: 'R-011',
  REPLACE_MATERIALLY_BETTER: 'R-012',
  REFER_DATA_MISSING: 'R-013',
  // Compliance
  COMPLIANCE_SOA: 'C-001',
  COMPLIANCE_REPLACEMENT: 'C-002',
  COMPLIANCE_TMD: 'C-003',
} as const;

// =============================================================================
// ENGINE VERSION
// =============================================================================

export const ENGINE_VERSION = '1.0.0';
