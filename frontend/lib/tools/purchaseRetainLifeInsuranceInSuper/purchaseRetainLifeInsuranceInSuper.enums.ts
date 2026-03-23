// =============================================================================
// ENUMS — purchaseRetainLifeInsuranceInSuper
// Australian super life-insurance strategy engine
//
// Statutory basis:
//   Superannuation Industry (Supervision) Act 1993 (Cth) — Part 6, Division 4
//   Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth)
// =============================================================================

/** Every cover type that might appear inside or alongside a super policy. */
export enum ProductType {
  DEATH_COVER = 'DEATH_COVER',
  TERMINAL_ILLNESS = 'TERMINAL_ILLNESS',
  TOTAL_AND_PERMANENT_DISABILITY = 'TOTAL_AND_PERMANENT_DISABILITY',
  INCOME_PROTECTION = 'INCOME_PROTECTION',
  TRAUMA = 'TRAUMA',
  ACCIDENTAL_DEATH = 'ACCIDENTAL_DEATH',
  UNKNOWN = 'UNKNOWN',
}

/** Regulated fund categories relevant to insurance eligibility. */
export enum FundType {
  MYSUPER = 'mysuper',
  CHOICE = 'choice',
  SMSF = 'smsf',
  SMALL_APRA = 'small_apra',
  DEFINED_BENEFIT = 'defined_benefit',
}

/**
 * Whether a given cover type is a permitted insured event under SIS Act s67A.
 * Permitted events: death (s67A(1)(a)), terminal medical condition (s67A(1)(b)),
 * permanent incapacity (s67A(1)(c)), temporary incapacity / IP (s67A(1)(d)).
 */
export enum CoverPermissibility {
  PERMITTED = 'PERMITTED',
  NOT_PERMITTED = 'NOT_PERMITTED',
  /** Pre-2014 or legacy arrangement — must not be auto-rejected without human review. */
  TRANSITIONAL_REVIEW_REQUIRED = 'TRANSITIONAL_REVIEW_REQUIRED',
  UNKNOWN = 'UNKNOWN',
}

/**
 * Final legal status of life insurance inside super for this member.
 * The engine resolves to exactly one of these values.
 */
export enum LegalStatus {
  /** Cover is permitted and no unresolved switch-off trigger applies. */
  ALLOWED_AND_ACTIVE = 'ALLOWED_AND_ACTIVE',
  /** Cover is possible but the member must first lodge a written opt-in direction (e.g. under-25). */
  ALLOWED_BUT_OPT_IN_REQUIRED = 'ALLOWED_BUT_OPT_IN_REQUIRED',
  /** A PYS switch-off trigger has fired and no statutory exception or member election overrides it. */
  MUST_BE_SWITCHED_OFF = 'MUST_BE_SWITCHED_OFF',
  /** Cover type is not a permitted insured event under SIS s67A. */
  NOT_ALLOWED_IN_SUPER = 'NOT_ALLOWED_IN_SUPER',
  /** Legacy or pre-reform cover — legal status cannot be auto-resolved; requires adviser review. */
  TRANSITIONAL_REVIEW_REQUIRED = 'TRANSITIONAL_REVIEW_REQUIRED',
  /** Successor-fund-transfer, fixed-term, or rights-not-affected situation — manual review required. */
  COMPLEX_RIGHTS_CHECK_REQUIRED = 'COMPLEX_RIGHTS_CHECK_REQUIRED',
  /** One or more critical legal facts are absent; engine cannot produce a legal determination. */
  NEEDS_MORE_INFO = 'NEEDS_MORE_INFO',
}

/** Placement recommendation for where life cover should be held. */
export enum PlacementRecommendation {
  INSIDE_SUPER = 'INSIDE_SUPER',
  OUTSIDE_SUPER = 'OUTSIDE_SUPER',
  /** Mixed outcome — part inside super, part outside is strategically optimal. */
  SPLIT_STRATEGY = 'SPLIT_STRATEGY',
  /** Insufficient strategic facts to produce a reliable recommendation. */
  INSUFFICIENT_INFO = 'INSUFFICIENT_INFO',
}

/** Governs how personalised and certain the engine's output is permitted to be. */
export enum AdviceMode {
  /** Legal facts complete; strategic suitability facts missing. Factual output only. */
  FACTUAL_ONLY = 'FACTUAL_ONLY',
  /** Legal facts complete; some strategic facts present. General context can be provided. */
  GENERAL_GUIDANCE = 'GENERAL_GUIDANCE',
  /** All material legal and strategic facts present. Full personal-advice-grade output. */
  PERSONAL_ADVICE_READY = 'PERSONAL_ADVICE_READY',
  /** Blocking facts are absent; engine must prompt for them before any output. */
  NEEDS_MORE_INFO = 'NEEDS_MORE_INFO',
}

/**
 * Tax treatment of super death benefits depends on this category.
 * Non-dependants face a 15% + 2% Medicare levy tax on taxable components (SIS s302AE / ITAA97).
 * This is one of the primary strategic risks of holding life cover inside super.
 */
export enum BeneficiaryCategory {
  DEPENDANT_SPOUSE_OR_CHILD = 'DEPENDANT_SPOUSE_OR_CHILD',
  FINANCIAL_DEPENDANT = 'FINANCIAL_DEPENDANT',
  /** Paid to estate — ultimate tax exposure depends on who inherits the estate. */
  LEGAL_PERSONAL_REPRESENTATIVE = 'LEGAL_PERSONAL_REPRESENTATIVE',
  /** Adult non-dependant child or sibling — maximum tax exposure on taxable component. */
  NON_DEPENDANT_ADULT = 'NON_DEPENDANT_ADULT',
  UNKNOWN = 'UNKNOWN',
}

export enum RiskLevel {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL',
}

/** Statutory or regulatory exception that can override a PYS switch-off trigger. */
export enum ExceptionType {
  SMALL_FUND_CARVE_OUT = 'SMALL_FUND_CARVE_OUT',
  DEFINED_BENEFIT = 'DEFINED_BENEFIT',
  ADF_COMMONWEALTH = 'ADF_COMMONWEALTH',
  EMPLOYER_SPONSORED_CONTRIBUTION = 'EMPLOYER_SPONSORED_CONTRIBUTION',
  DANGEROUS_OCCUPATION = 'DANGEROUS_OCCUPATION',
  SUCCESSOR_FUND_TRANSFER = 'SUCCESSOR_FUND_TRANSFER',
  RIGHTS_NOT_AFFECTED = 'RIGHTS_NOT_AFFECTED',
}

/** The specific Protecting Your Super switch-off rule that may fire. */
export enum SwitchOffTrigger {
  /** SIS s68AAA(1)(a) — no contribution or rollover received for 16+ consecutive months. */
  INACTIVITY_16_MONTHS = 'INACTIVITY_16_MONTHS',
  /** SIS s68AAA(1)(b) — account balance below $6,000. */
  LOW_BALANCE_UNDER_6000 = 'LOW_BALANCE_UNDER_6000',
  /** SIS s68AAA(3) — member is under 25 and has not lodged an opt-in direction. */
  UNDER_25_NO_ELECTION = 'UNDER_25_NO_ELECTION',
}

/** Groups missing-information questions so the agent or UI can present them coherently. */
export enum MissingInfoCategory {
  LEGAL = 'LEGAL',
  STRATEGIC = 'STRATEGIC',
  BENEFICIARY_ESTATE = 'BENEFICIARY_ESTATE',
  AFFORDABILITY = 'AFFORDABILITY',
  PRODUCT_STRUCTURE = 'PRODUCT_STRUCTURE',
}

export enum EmploymentStatus {
  EMPLOYED_FULL_TIME = 'EMPLOYED_FULL_TIME',
  EMPLOYED_PART_TIME = 'EMPLOYED_PART_TIME',
  SELF_EMPLOYED = 'SELF_EMPLOYED',
  CASUAL = 'CASUAL',
  UNEMPLOYED = 'UNEMPLOYED',
  RETIRED = 'RETIRED',
  UNKNOWN = 'UNKNOWN',
}
