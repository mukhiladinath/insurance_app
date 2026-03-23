// =============================================================================
// CONSTANTS — purchaseRetainLifeInsuranceInSuper
// All regulatory thresholds, dates, weights, and metadata are hardcoded here.
// No value in this file should ever be derived from runtime input.
// =============================================================================

import type { LawVersion } from './purchaseRetainLifeInsuranceInSuper.types';

// =============================================================================
// REGULATORY THRESHOLDS (SIS Act / PYS Package)
// =============================================================================

/**
 * SIS s68AAA(1)(a): insurance must be switched off if no amount has been
 * credited to the account for 16 consecutive months.
 */
export const INACTIVITY_THRESHOLD_MONTHS = 16;

/**
 * SIS s68AAA(1)(b): insurance must be switched off if the account balance
 * falls below this threshold (subject to grandfathering).
 */
export const LOW_BALANCE_THRESHOLD_AUD = 6_000;

/**
 * SIS s68AAA(3): trustees of MySuper products must not provide default
 * insurance to members who have not yet reached this age and have not
 * lodged an opt-in direction.
 */
export const UNDER_25_AGE_THRESHOLD = 25;

/**
 * Maximum member count for a fund to qualify as a "small APRA fund" or
 * similar small-fund arrangement for carve-out purposes.
 */
export const SMALL_FUND_MEMBER_COUNT_THRESHOLD = 6;

// =============================================================================
// REFORM / COMMENCEMENT DATES
// =============================================================================

/**
 * Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth)
 * — primary commencement for insurance switch-off provisions.
 * Inactivity, low-balance, and under-25 rules all took effect from this date.
 */
export const PYS_COMMENCEMENT_DATE = new Date('2019-07-01');

/**
 * Low-balance grandfathering reference date.
 * If a member's account held >= $6,000 on or after this date, the low-balance
 * switch-off trigger cannot be applied to that account (SIS s68AAA(2A) context).
 */
export const LOW_BALANCE_GRANDFATHERING_DATE = new Date('2019-11-01');

/**
 * Approximate cut-off used to classify cover as "legacy / pre-modern".
 * Cover commenced before this date may have non-standard features or
 * definitions that pre-date the standardised SIS insurance framework.
 */
export const LEGACY_COVER_CUTOFF_DATE = new Date('2014-01-01');

// =============================================================================
// PERMITTED INSURED EVENTS (SIS s67A)
// =============================================================================

/**
 * Cover types that map to permitted insured events under SIS s67A.
 * Trustees may only provide insurance benefits for these events.
 */
export const PERMITTED_COVER_TYPES = [
  'DEATH_COVER',
  'TERMINAL_ILLNESS',
  'TOTAL_AND_PERMANENT_DISABILITY',
  'INCOME_PROTECTION',
] as const;

/**
 * Cover types that are NOT permitted insured events under SIS s67A.
 * Trauma/critical illness and standalone accidental death riders
 * (not structured as death cover) are the primary examples.
 */
export const NON_PERMITTED_COVER_TYPES = ['TRAUMA', 'ACCIDENTAL_DEATH'] as const;

// =============================================================================
// PLACEMENT SCORING WEIGHTS
// All weights sum to exactly 1.00.
// Benefits contribute positively to an inside-super recommendation;
// penalties contribute negatively.
// =============================================================================

export const PLACEMENT_WEIGHTS = {
  // Benefits
  cashflowBenefit: 0.25,
  taxFundingBenefit: 0.20,
  convenienceBenefit: 0.10,
  structuralProtectionBenefit: 0.05,
  // Penalties (against inside-super)
  retirementErosionPenalty: 0.20,
  beneficiaryTaxRiskPenalty: 0.10,
  flexibilityControlPenalty: 0.05,
  contributionCapPressurePenalty: 0.05,
} as const;

/**
 * Minimum net inside-super score (0–100) required to recommend INSIDE_SUPER.
 * If the net score is below the outside threshold equivalent, we lean OUTSIDE_SUPER.
 * If neither side clears its threshold, we recommend SPLIT_STRATEGY.
 */
export const PLACEMENT_INSIDE_THRESHOLD = 55;
export const PLACEMENT_OUTSIDE_THRESHOLD = 55;

// =============================================================================
// RULE IDs (for ruleTrace auditability)
// =============================================================================

export const RULE_IDS = {
  PERMITTED_COVER_CHECK: 'R-001',
  LEGACY_TRANSITIONAL_CHECK: 'R-002',
  MYSUPER_BASELINE_CHECK: 'R-003',
  INACTIVITY_RULE: 'R-004',
  LOW_BALANCE_RULE: 'R-005',
  UNDER_25_RULE: 'R-006',
  ELECTION_STATUS: 'R-007',
  LEGAL_STATUS_RESOLUTION: 'R-008',
  SMALL_FUND_EXCEPTION: 'E-001',
  DEFINED_BENEFIT_EXCEPTION: 'E-002',
  ADF_COMMONWEALTH_EXCEPTION: 'E-003',
  EMPLOYER_SPONSORED_EXCEPTION: 'E-004',
  DANGEROUS_OCCUPATION_EXCEPTION: 'E-005',
  SUCCESSOR_FUND_EXCEPTION: 'E-006',
  RIGHTS_NOT_AFFECTED_EXCEPTION: 'E-007',
  PLACEMENT_EVALUATION: 'P-001',
  ADVICE_READINESS: 'A-001',
} as const;

// =============================================================================
// LAW VERSION METADATA
// =============================================================================

export const LAW_VERSION: LawVersion = {
  primaryAct: 'Superannuation Industry (Supervision) Act 1993 (Cth)',
  primaryActSection: 'Part 6, Div 4 — ss 67A, 67AA, 68AAA, 68B',
  reformName:
    'Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth)',
  reformCommencementDate: '2019-07-01',
  engineVersion: '1.0.0',
  evaluatedUnderLegislationAsOf: '2026-03-20',
};
