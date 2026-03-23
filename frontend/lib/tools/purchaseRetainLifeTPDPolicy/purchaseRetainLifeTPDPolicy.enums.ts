// =============================================================================
// ENUMS — purchaseRetainLifeTPDPolicy
// Purchase / Retain Life / TPD Policy — Australian insurance advice engine
// =============================================================================

/**
 * The final strategic recommendation the engine can produce.
 * Ordered from most to least action-oriented.
 */
export enum RecommendationType {
  /** No existing policy exists and a net cover need is present. */
  PURCHASE_NEW = 'PURCHASE_NEW',
  /** Existing policy is sound; current cover level is sufficient. */
  RETAIN_EXISTING = 'RETAIN_EXISTING',
  /** Existing policy should be replaced by a materially better alternative. */
  REPLACE_EXISTING = 'REPLACE_EXISTING',
  /** Existing policy is kept; additional cover is added alongside it. */
  SUPPLEMENT_EXISTING = 'SUPPLEMENT_EXISTING',
  /** Existing cover is adequate but unaffordable — reduce sum insured or premium structure. */
  REDUCE_COVER = 'REDUCE_COVER',
  /** Insufficient data or conditions are not ripe for a recommendation. */
  DEFER_NO_ACTION = 'DEFER_NO_ACTION',
  /** Case is too complex or sensitive for automated logic; escalate to human adviser. */
  REFER_TO_HUMAN = 'REFER_TO_HUMAN',
}

/** Controls how personalised and certain the output can be. */
export enum AdviceMode {
  /** Product facts only — no strategy or suitability commentary. */
  FACTUAL_INFORMATIONAL = 'FACTUAL_INFORMATIONAL',
  /** General strategic context without reference to client-specific circumstances. */
  GENERAL_ADVICE = 'GENERAL_ADVICE',
  /** Full personal advice output — client facts drive every conclusion. */
  PERSONAL_ADVICE = 'PERSONAL_ADVICE',
}

/** Life and TPD are the primary covers modelled. Trauma/IP are referenced for completeness. */
export enum CoverType {
  LIFE = 'LIFE',
  TPD = 'TPD',
  TRAUMA = 'TRAUMA',
  INCOME_PROTECTION = 'INCOME_PROTECTION',
}

/**
 * TPD definitions — ordered from most favourable to client (own occupation)
 * to least favourable (home duties only). This ordering underpins comparison logic.
 */
export enum TPDDefinitionType {
  OWN_OCCUPATION = 'OWN_OCCUPATION',
  MODIFIED_OWN_OCCUPATION = 'MODIFIED_OWN_OCCUPATION',
  ANY_OCCUPATION = 'ANY_OCCUPATION',
  ACTIVITIES_OF_DAILY_LIVING = 'ACTIVITIES_OF_DAILY_LIVING',
  HOME_DUTIES = 'HOME_DUTIES',
  UNKNOWN = 'UNKNOWN',
}

export enum PremiumStructure {
  STEPPED = 'STEPPED',
  LEVEL = 'LEVEL',
  HYBRID = 'HYBRID',
  UNKNOWN = 'UNKNOWN',
}

export enum PolicyOwnership {
  SELF_OWNED = 'SELF_OWNED',
  SUPER_OWNED = 'SUPER_OWNED',
  BUSINESS_OWNED = 'BUSINESS_OWNED',
  UNKNOWN = 'UNKNOWN',
}

export enum EmploymentType {
  EMPLOYED_FULL_TIME = 'EMPLOYED_FULL_TIME',
  EMPLOYED_PART_TIME = 'EMPLOYED_PART_TIME',
  SELF_EMPLOYED = 'SELF_EMPLOYED',
  CASUAL = 'CASUAL',
  UNEMPLOYED = 'UNEMPLOYED',
  RETIRED = 'RETIRED',
  UNKNOWN = 'UNKNOWN',
}

/**
 * Insurer occupation classification — directly affects available cover types,
 * definitions available, and premium rates.
 */
export enum OccupationClass {
  /** Professional / clerical — best rates, own occupation TPD available. */
  CLASS_1_WHITE_COLLAR = 'CLASS_1_WHITE_COLLAR',
  /** Light manual or supervisory. */
  CLASS_2_LIGHT_BLUE = 'CLASS_2_LIGHT_BLUE',
  /** Manual trade — limited or no own-occupation TPD. */
  CLASS_3_BLUE_COLLAR = 'CLASS_3_BLUE_COLLAR',
  /** High-risk occupation — significant restrictions. */
  CLASS_4_HAZARDOUS = 'CLASS_4_HAZARDOUS',
  UNKNOWN = 'UNKNOWN',
}

/** Overall underwriting risk that new cover could face. */
export enum UnderwritingRisk {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  /** Likely decline — do not recommend replacement without full underwriting resolution. */
  CRITICAL = 'CRITICAL',
}

/**
 * Risk of replacing an existing policy and losing valuable terms.
 * BLOCKING means the engine must not produce REPLACE_EXISTING.
 */
export enum ReplacementRisk {
  NEGLIGIBLE = 'NEGLIGIBLE',
  LOW = 'LOW',
  MODERATE = 'MODERATE',
  HIGH = 'HIGH',
  /** Replacement should not proceed — existing terms are too valuable to risk. */
  BLOCKING = 'BLOCKING',
}

/** Net outcome of comparing an existing policy to a new candidate. */
export enum ComparisonOutcome {
  NEW_MATERIALLY_BETTER = 'NEW_MATERIALLY_BETTER',
  NEW_MARGINALLY_BETTER = 'NEW_MARGINALLY_BETTER',
  EQUIVALENT = 'EQUIVALENT',
  NEW_MARGINALLY_WORSE = 'NEW_MARGINALLY_WORSE',
  NEW_MATERIALLY_WORSE = 'NEW_MATERIALLY_WORSE',
  INSUFFICIENT_DATA = 'INSUFFICIENT_DATA',
}

/** Groups missing-information questions for display. */
export enum MissingInfoCategory {
  CLIENT_PROFILE = 'CLIENT_PROFILE',
  EXISTING_POLICY = 'EXISTING_POLICY',
  HEALTH = 'HEALTH',
  GOALS = 'GOALS',
  AFFORDABILITY = 'AFFORDABILITY',
  NEW_POLICY = 'NEW_POLICY',
  COMPLIANCE = 'COMPLIANCE',
}

/** Indicates how large the identified insurance shortfall is. */
export enum ShortfallLevel {
  NONE = 'NONE',
  MINOR = 'MINOR',
  MODERATE = 'MODERATE',
  SIGNIFICANT = 'SIGNIFICANT',
  CRITICAL = 'CRITICAL',
}

/** Health / lifestyle risk factor categories. */
export enum HealthRiskFactor {
  BMI_HIGH = 'BMI_HIGH',
  BMI_VERY_HIGH = 'BMI_VERY_HIGH',
  EXISTING_CONDITION = 'EXISTING_CONDITION',
  PENDING_INVESTIGATION = 'PENDING_INVESTIGATION',
  ADVERSE_FAMILY_HISTORY = 'ADVERSE_FAMILY_HISTORY',
  SMOKER = 'SMOKER',
  HAZARDOUS_ACTIVITY = 'HAZARDOUS_ACTIVITY',
  HAZARDOUS_OCCUPATION = 'HAZARDOUS_OCCUPATION',
  NON_DISCLOSURE_RISK = 'NON_DISCLOSURE_RISK',
}
