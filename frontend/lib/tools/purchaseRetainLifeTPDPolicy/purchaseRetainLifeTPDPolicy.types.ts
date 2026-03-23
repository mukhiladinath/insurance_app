// =============================================================================
// TYPES & INTERFACES — purchaseRetainLifeTPDPolicy
// =============================================================================

import {
  RecommendationType,
  AdviceMode,
  CoverType,
  TPDDefinitionType,
  PremiumStructure,
  PolicyOwnership,
  EmploymentType,
  OccupationClass,
  UnderwritingRisk,
  ReplacementRisk,
  ComparisonOutcome,
  MissingInfoCategory,
  ShortfallLevel,
  HealthRiskFactor,
} from './purchaseRetainLifeTPDPolicy.enums';

// =============================================================================
// RAW INPUTS
// =============================================================================

export interface ClientProfileInput {
  age?: number;
  dateOfBirth?: string; // ISO 8601
  smoker?: boolean;
  occupation?: string;
  occupationClass?: OccupationClass;
  employmentType?: EmploymentType;
  annualGrossIncome?: number; // AUD
  annualNetIncome?: number; // AUD — used for TPD income replacement calculation
  hasPartner?: boolean;
  partnerIncome?: number; // AUD
  numberOfDependants?: number;
  youngestDependantAge?: number;
  mortgageBalance?: number; // AUD
  otherDebts?: number; // AUD
  liquidAssets?: number; // AUD — cash, investments, accessible super
  existingLifeCoverSumInsured?: number; // AUD — all policies combined
  existingTPDCoverSumInsured?: number; // AUD — all policies combined
  yearsToRetirement?: number;
}

export interface ExistingPolicyInput {
  hasExistingPolicy?: boolean;
  insurer?: string;
  ownership?: PolicyOwnership;
  commencementDate?: string; // ISO 8601
  coverTypes?: CoverType[];
  lifeSumInsured?: number; // AUD
  tpdSumInsured?: number; // AUD
  tpdDefinition?: TPDDefinitionType;
  premiumStructure?: PremiumStructure;
  annualPremium?: number; // AUD total for all covers on this policy
  hasLoadings?: boolean;
  loadingDetails?: string;
  hasExclusions?: boolean;
  exclusionDetails?: string;
  hasIndexation?: boolean;
  indexationRate?: number; // decimal e.g. 0.05
  riders?: string[]; // e.g. ['Premium Waiver', 'Trauma Conversion']
  /** Whether the client has disclosed all material facts at commencement. */
  hasFullNonDisclosureRisk?: boolean;
  /** Whether existing terms are regarded as superior to current market (e.g. grandfathered definition). */
  hasSuperiorGrandfatheredTerms?: boolean;
}

export interface HealthInput {
  heightCm?: number;
  weightKg?: number;
  existingMedicalConditions?: string[]; // free-text list
  currentMedications?: string[];
  pendingInvestigations?: boolean;
  pendingInvestigationDetails?: string;
  familyHistoryConditions?: string[];
  hazardousActivities?: string[];
  /** Any non-disclosure risk — e.g. tests done but not disclosed at existing policy commencement. */
  nonDisclosureRisk?: boolean;
}

export interface ClientGoalsInput {
  primaryReason?: string; // free-text — why they want cover or want to act
  wantsReplacement?: boolean;
  wantsRetention?: boolean;
  affordabilityIsConcern?: boolean;
  wantsPremiumCertainty?: boolean; // prefers level premium
  wantsOwnOccupationTPD?: boolean;
  desiredCoverHorizon?: number; // years
  willingToUnderwrite?: boolean; // willing to go through new underwriting
  prioritisesDefinitionQuality?: boolean;
  prioritisesClaimsReputation?: boolean;
}

export interface NewPolicyCandidateInput {
  insurer?: string;
  ownership?: PolicyOwnership;
  coverTypes?: CoverType[];
  lifeSumInsured?: number; // AUD
  tpdSumInsured?: number; // AUD
  tpdDefinition?: TPDDefinitionType;
  premiumStructure?: PremiumStructure;
  projectedAnnualPremium?: number; // AUD
  expectedLoadings?: string;
  expectedExclusions?: string;
  hasIndexation?: boolean;
  flexibilityFeatures?: string[]; // e.g. ['Future Insurability', 'Business Events']
  claimsQualityRating?: number; // 0–10 adviser-assessed
  underwritingStatus?: 'NOT_STARTED' | 'IN_PROGRESS' | 'ACCEPTED_STANDARD' | 'ACCEPTED_WITH_TERMS' | 'DECLINED';
}

// =============================================================================
// TOP-LEVEL RAW INPUT
// =============================================================================

export interface PurchaseRetainLifeTPDPolicyInput {
  adviceMode?: AdviceMode;
  client?: ClientProfileInput;
  existingPolicy?: ExistingPolicyInput;
  health?: HealthInput;
  goals?: ClientGoalsInput;
  newPolicyCandidate?: NewPolicyCandidateInput;
  evaluationDate?: string; // ISO 8601
}

// =============================================================================
// NORMALIZED INPUT — all fields resolved, missing = null
// =============================================================================

export interface NormalizedInput {
  adviceMode: AdviceMode;
  evaluationDate: Date;
  // Client
  age: number | null;
  dateOfBirth: Date | null;
  smoker: boolean;
  occupation: string | null;
  occupationClass: OccupationClass;
  employmentType: EmploymentType;
  annualGrossIncome: number | null;
  annualNetIncome: number | null;
  hasPartner: boolean | null;
  partnerIncome: number | null;
  numberOfDependants: number | null;
  youngestDependantAge: number | null;
  mortgageBalance: number | null;
  otherDebts: number | null;
  liquidAssets: number | null;
  existingLifeCoverSumInsured: number | null;
  existingTPDCoverSumInsured: number | null;
  yearsToRetirement: number | null;
  // Existing policy
  hasExistingPolicy: boolean;
  existingInsurer: string | null;
  existingOwnership: PolicyOwnership;
  existingCommencementDate: Date | null;
  existingCoverTypes: CoverType[];
  existingLifeSumInsured: number | null;
  existingTPDSumInsured: number | null;
  existingTPDDefinition: TPDDefinitionType;
  existingPremiumStructure: PremiumStructure;
  existingAnnualPremium: number | null;
  existingHasLoadings: boolean;
  existingLoadingDetails: string | null;
  existingHasExclusions: boolean;
  existingExclusionDetails: string | null;
  existingHasIndexation: boolean;
  existingRiders: string[];
  existingHasFullNonDisclosureRisk: boolean;
  existingHasSuperiorGrandfatheredTerms: boolean;
  // Health
  heightCm: number | null;
  weightKg: number | null;
  existingMedicalConditions: string[];
  currentMedications: string[];
  pendingInvestigations: boolean;
  pendingInvestigationDetails: string | null;
  familyHistoryConditions: string[];
  hazardousActivities: string[];
  nonDisclosureRisk: boolean;
  // Goals
  primaryReason: string | null;
  wantsReplacement: boolean | null;
  wantsRetention: boolean | null;
  affordabilityIsConcern: boolean | null;
  wantsPremiumCertainty: boolean | null;
  wantsOwnOccupationTPD: boolean | null;
  desiredCoverHorizon: number | null;
  willingToUnderwrite: boolean | null;
  prioritisesDefinitionQuality: boolean | null;
  prioritisesClaimsReputation: boolean | null;
  // New policy candidate
  hasNewPolicyCandidate: boolean;
  newInsurer: string | null;
  newOwnership: PolicyOwnership;
  newCoverTypes: CoverType[];
  newLifeSumInsured: number | null;
  newTPDSumInsured: number | null;
  newTPDDefinition: TPDDefinitionType;
  newPremiumStructure: PremiumStructure;
  newProjectedAnnualPremium: number | null;
  newExpectedLoadings: string | null;
  newExpectedExclusions: string | null;
  newHasIndexation: boolean;
  newFlexibilityFeatures: string[];
  newClaimsQualityRating: number | null;
  newUnderwritingStatus: NewPolicyCandidateInput['underwritingStatus'];
}

// =============================================================================
// VALIDATION
// =============================================================================

export interface ValidationError {
  field: string;
  message: string;
  category: MissingInfoCategory;
}

export interface ValidationWarning {
  field: string;
  message: string;
}

export interface MissingInfoQuestion {
  id: string;
  question: string;
  category: MissingInfoCategory;
  blocking: boolean;
}

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  missingInfoQuestions: MissingInfoQuestion[];
}

// =============================================================================
// CALCULATIONS
// =============================================================================

export interface LifeNeedResult {
  debtClearanceNeed: number;
  educationFundingNeed: number;
  incomeReplacementNeed: number;
  finalExpensesNeed: number;
  otherCapitalNeeds: number;
  grossNeed: number;
  lessExistingCover: number;
  lessLiquidAssets: number;
  netLifeInsuranceNeed: number;
  shortfallLevel: ShortfallLevel;
  assumptions: string[];
}

export interface TPDNeedResult {
  debtClearanceNeed: number;
  medicalRehabBuffer: number;
  incomeReplacementCapitalised: number;
  homeModificationBuffer: number;
  ongoingCareBuffer: number;
  grossNeed: number;
  lessExistingTPDCover: number;
  lessLiquidAssets: number;
  netTPDNeed: number;
  shortfallLevel: ShortfallLevel;
  capitalisationRate: number;
  assumptions: string[];
}

export interface AffordabilityResult {
  totalAnnualPremium: number | null;
  premiumAsPercentOfGrossIncome: number | null;
  premiumAsPercentOfNetIncome: number | null;
  projectedPremiumIn10Years: number | null; // for stepped policies
  affordabilityScore: number; // 0–100
  lapseRiskScore: number; // 0–100 (higher = more likely to lapse)
  stressCaseAffordable: boolean | null;
  assessment: 'COMFORTABLE' | 'MANAGEABLE' | 'STRETCHED' | 'UNAFFORDABLE' | 'UNKNOWN';
  notes: string[];
}

// =============================================================================
// POLICY COMPARISON
// =============================================================================

export interface PolicyComparisonDimension {
  dimension: string;
  existingValue: string | number | null;
  newValue: string | number | null;
  verdict: 'NEW_BETTER' | 'EQUIVALENT' | 'NEW_WORSE' | 'UNKNOWN';
  weight: number; // 0–1 importance weight
  notes: string;
}

export interface PolicyComparisonResult {
  hasComparisonCandidate: boolean;
  overallOutcome: ComparisonOutcome;
  dimensions: PolicyComparisonDimension[];
  premiumDifferenceAnnual: number | null; // positive = new is cheaper
  sumInsuredDifferenceLife: number | null;
  sumInsuredDifferenceTPD: number | null;
  tpdDefinitionChange: 'IMPROVED' | 'SAME' | 'WORSENED' | 'UNKNOWN';
  exclusionChange: 'FEWER' | 'SAME' | 'MORE' | 'UNKNOWN';
  loadingChange: 'REDUCED' | 'SAME' | 'INCREASED' | 'UNKNOWN';
  reasoning: string[];
  replacementWarnings: string[];
}

// =============================================================================
// UNDERWRITING RISK
// =============================================================================

export interface UnderwritingRiskFactor {
  factor: HealthRiskFactor;
  riskContribution: UnderwritingRisk;
  detail: string;
}

export interface UnderwritingRiskResult {
  overallRisk: UnderwritingRisk;
  factors: UnderwritingRiskFactor[];
  bmi: number | null;
  bmiCategory: 'UNDERWEIGHT' | 'NORMAL' | 'OVERWEIGHT' | 'OBESE' | 'SEVERELY_OBESE' | 'UNKNOWN';
  likelyOutcome:
    | 'STANDARD'
    | 'LOADED_PREMIUM'
    | 'EXCLUSION_APPLIED'
    | 'LOADED_AND_EXCLUSION'
    | 'DECLINE_POSSIBLE'
    | 'UNKNOWN';
  recommendations: string[];
}

// =============================================================================
// REPLACEMENT RISK
// =============================================================================

export interface ReplacementRiskFactor {
  factor: string;
  riskLevel: ReplacementRisk;
  description: string;
}

export interface ReplacementRiskResult {
  overallRisk: ReplacementRisk;
  factors: ReplacementRiskFactor[];
  existingCoverAtRisk: boolean;
  coverageGapPossible: boolean;
  warnings: string[];
  requiredActions: string[];
}

// =============================================================================
// COMPLIANCE FLAGS
// =============================================================================

export interface ComplianceFlags {
  requiresFSG: boolean;
  requiresSOA: boolean;
  requiresGeneralAdviceWarning: boolean;
  pdsRequired: boolean;
  pdsAcknowledged: boolean | null;
  tmdCheckRequired: boolean;
  tmdMatched: boolean | null;
  antiHawkingSafe: boolean;
  underwritingIncomplete: boolean;
  replacementRiskAcknowledgementRequired: boolean;
  coolingOffExplanationRequired: boolean;
  manualReviewRequired: boolean;
  complianceNotes: string[];
}

// =============================================================================
// RULE TRACE
// =============================================================================

export interface RuleTraceEntry {
  ruleId: string;
  ruleName: string;
  triggered: boolean;
  outcome: string;
  explanation: string;
  supportingFacts: Record<string, unknown>;
}

// =============================================================================
// REQUIRED ACTION
// =============================================================================

export interface RequiredAction {
  actionId: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  action: string;
  rationale: string;
}

// =============================================================================
// RECOMMENDATION RESULT
// =============================================================================

export interface RecommendationResult {
  type: RecommendationType;
  adviceMode: AdviceMode;
  summary: string;
  reasons: string[];
  risks: string[];
  requiredActions: RequiredAction[];
  lifeNeed: LifeNeedResult | null;
  tpdNeed: TPDNeedResult | null;
  affordability: AffordabilityResult;
  comparison: PolicyComparisonResult | null;
  underwritingRisk: UnderwritingRiskResult;
  replacementRisk: ReplacementRiskResult | null;
  complianceFlags: ComplianceFlags;
  ruleTrace: RuleTraceEntry[];
}

// =============================================================================
// FINAL ENGINE OUTPUT
// =============================================================================

export interface PurchaseRetainLifeTPDPolicyOutput {
  normalizedInput: NormalizedInput;
  validation: ValidationResult;
  recommendation: RecommendationResult;
  missingInfoQuestions: MissingInfoQuestion[];
  engineVersion: string;
  evaluatedAt: string;
}
