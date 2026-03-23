// =============================================================================
// TYPES & INTERFACES — purchaseRetainLifeInsuranceInSuper
// =============================================================================

import {
  ProductType,
  FundType,
  CoverPermissibility,
  LegalStatus,
  PlacementRecommendation,
  AdviceMode,
  BeneficiaryCategory,
  RiskLevel,
  ExceptionType,
  SwitchOffTrigger,
  MissingInfoCategory,
  EmploymentStatus,
} from './purchaseRetainLifeInsuranceInSuper.enums';

// =============================================================================
// RAW INPUTS — caller-supplied, all fields optional (validated downstream)
// =============================================================================

export interface MemberInput {
  age?: number;
  dateOfBirth?: string; // ISO 8601
  employmentStatus?: EmploymentStatus;
  occupation?: string;
  annualIncome?: number;
  marginalTaxRate?: number; // decimal e.g. 0.325
  hasDependants?: boolean;
  beneficiaryTypeExpected?: BeneficiaryCategory;
  cashflowPressure?: boolean;
  retirementPriorityHigh?: boolean;
  existingInsuranceNeedsEstimate?: number; // AUD
  healthOrUnderwritingComplexity?: boolean;
  wantsInsideSuper?: boolean;
  wantsAffordability?: boolean;
  wantsEstateControl?: boolean;
}

export interface FundInput {
  fundType?: FundType;
  fundMemberCount?: number;
  isDefinedBenefitMember?: boolean;
  isADFOrCommonwealthExceptionCase?: boolean;
  hasDangerousOccupationElection?: boolean;
  dangerousOccupationElectionInForce?: boolean;
  trusteeAllowsOptInOnline?: boolean;
  successorFundTransferOccurred?: boolean;
}

export interface ProductInput {
  productStartDate?: string; // ISO 8601
  accountBalance?: number; // AUD
  /**
   * True if the member's account held a balance >= $6,000 on or after 1 November 2019.
   * Required to determine whether the PYS low-balance grandfathering provision applies.
   */
  hadBalanceGe6000OnOrAfter2019_11_01?: boolean;
  lastAmountReceivedDate?: string; // ISO 8601 — date of most recent contribution/rollover
  receivedAmountInLast16Months?: boolean; // alternative to date if exact date is unknown
  coverTypesPresent?: ProductType[];
  coverCommencedBefore2014?: boolean;
  fixedTermCover?: boolean;
  fullyPaidOrNonPremiumPaying?: boolean;
  legacyNonStandardFeatureFlag?: boolean;
}

export interface ElectionsInput {
  optedInToRetainInsurance?: boolean;
  optInElectionDate?: string; // ISO 8601
  optedOutOfInsurance?: boolean;
  optOutDate?: string; // ISO 8601
  priorElectionCarriedViaSuccessorTransfer?: boolean;
  equivalentRightsConfirmed?: boolean;
}

export interface EmployerExceptionInput {
  /**
   * SIS s68AAA(4A)(a): employer has given the trustee written notification that
   * it wishes insurance to be maintained for this member.
   */
  employerHasNotifiedTrusteeInWriting?: boolean;
  /**
   * SIS s68AAA(4A)(b): employer contributions to the fund for this member exceed
   * the SG minimum by an amount at least equal to the insurance fee.
   */
  employerContributionsExceedSGMinimumByInsuranceFeeAmount?: boolean;
}

export interface AdviceContextInput {
  contributionCapPressure?: boolean;
  concessionalContributionsAlreadyHigh?: boolean;
  superBalanceAdequacy?: 'low' | 'adequate' | 'high';
  preferredBeneficiaryCategory?: BeneficiaryCategory;
  needForPolicyFlexibility?: boolean;
  needForOwnOccupationStyleDefinitions?: boolean;
  needForPolicyOwnershipOutsideTrusteeControl?: boolean;
  retirementPriorityHigh?: boolean;
  estimatedAnnualPremium?: number; // AUD
  yearsToRetirement?: number;
  assumedGrowthRate?: number; // decimal e.g. 0.07
  currentMonthlySurplusAfterExpenses?: number; // AUD
}

// =============================================================================
// COMBINED RAW INPUT (top-level entry point)
// =============================================================================

export interface PurchaseRetainLifeInsuranceInSuperInput {
  member?: MemberInput;
  fund?: FundInput;
  product?: ProductInput;
  elections?: ElectionsInput;
  employerException?: EmployerExceptionInput;
  adviceContext?: AdviceContextInput;
  /** ISO 8601 — defaults to today if omitted. */
  evaluationDate?: string;
}

// =============================================================================
// NORMALIZED INPUT — all fields present after normalization, missing = null
// =============================================================================

export interface NormalizedInput {
  // Member
  age: number | null;
  dateOfBirth: Date | null;
  employmentStatus: EmploymentStatus;
  occupation: string | null;
  annualIncome: number | null;
  marginalTaxRate: number | null;
  hasDependants: boolean | null;
  beneficiaryTypeExpected: BeneficiaryCategory;
  cashflowPressure: boolean | null;
  retirementPriorityHigh: boolean | null;
  existingInsuranceNeedsEstimate: number | null;
  healthOrUnderwritingComplexity: boolean | null;
  wantsInsideSuper: boolean | null;
  wantsAffordability: boolean | null;
  wantsEstateControl: boolean | null;
  // Fund
  fundType: FundType | null;
  fundMemberCount: number | null;
  isDefinedBenefitMember: boolean;
  isADFOrCommonwealthExceptionCase: boolean;
  hasDangerousOccupationElection: boolean;
  dangerousOccupationElectionInForce: boolean;
  trusteeAllowsOptInOnline: boolean;
  successorFundTransferOccurred: boolean;
  // Product
  productStartDate: Date | null;
  accountBalance: number | null;
  hadBalanceGe6000OnOrAfter2019_11_01: boolean | null;
  lastAmountReceivedDate: Date | null;
  receivedAmountInLast16Months: boolean | null;
  coverTypesPresent: ProductType[];
  coverCommencedBefore2014: boolean;
  fixedTermCover: boolean;
  fullyPaidOrNonPremiumPaying: boolean;
  legacyNonStandardFeatureFlag: boolean;
  // Elections
  optedInToRetainInsurance: boolean;
  optInElectionDate: Date | null;
  optedOutOfInsurance: boolean;
  optOutDate: Date | null;
  priorElectionCarriedViaSuccessorTransfer: boolean;
  equivalentRightsConfirmed: boolean;
  // Employer exception
  employerHasNotifiedTrusteeInWriting: boolean;
  employerContributionsExceedSGMinimumByInsuranceFeeAmount: boolean;
  // Advice context
  contributionCapPressure: boolean | null;
  concessionalContributionsAlreadyHigh: boolean | null;
  superBalanceAdequacy: 'low' | 'adequate' | 'high' | null;
  preferredBeneficiaryCategory: BeneficiaryCategory | null;
  needForPolicyFlexibility: boolean | null;
  needForOwnOccupationStyleDefinitions: boolean | null;
  needForPolicyOwnershipOutsideTrusteeControl: boolean | null;
  estimatedAnnualPremium: number | null;
  yearsToRetirement: number | null;
  assumedGrowthRate: number | null;
  currentMonthlySurplusAfterExpenses: number | null;
  // Meta
  evaluationDate: Date;
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
  /** If true the engine cannot proceed without an answer. */
  blocking: boolean;
}

export interface ValidationResult {
  isValid: boolean;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  missingInfoQuestions: MissingInfoQuestion[];
}

// =============================================================================
// RULE TRACE
// =============================================================================

export interface RuleTraceEntry {
  ruleId: string;
  ruleName: string;
  passed: boolean;
  outcome: string;
  explanation: string;
  supportingFacts: Record<string, unknown>;
}

// =============================================================================
// SWITCH-OFF EVALUATION
// =============================================================================

export interface SwitchOffEvaluation {
  trigger: SwitchOffTrigger;
  triggered: boolean;
  overriddenByException: boolean;
  overriddenByElection: boolean;
  effectivelyActive: boolean; // triggered AND NOT (overriddenByException OR overriddenByElection)
  reason: string;
  supportingFacts: Record<string, unknown>;
}

// =============================================================================
// EXCEPTION RESULT
// =============================================================================

export interface ExceptionResult {
  applied: boolean;
  type: ExceptionType;
  reason: string;
  supportingFacts: Record<string, unknown>;
}

// =============================================================================
// LEGAL RESULT (intermediate, before final output assembly)
// =============================================================================

export interface LegalResult {
  status: LegalStatus;
  permissibility: CoverPermissibility;
  reasons: string[];
  switchOffEvaluations: SwitchOffEvaluation[];
  exceptionsApplied: ExceptionResult[];
  ruleTrace: RuleTraceEntry[];
}

// =============================================================================
// CALCULATIONS
// =============================================================================

export interface RetirementDragEstimate {
  annualPremium: number;
  yearsToRetirement: number;
  assumedGrowthRate: number;
  /**
   * Future value of the premium stream: the compound growth that is sacrificed
   * by paying premiums from the super balance rather than leaving it invested.
   * FV = premium × [((1+r)^n − 1) / r]
   */
  estimatedTotalDrag: number;
  explanation: string;
}

export interface CashflowMetrics {
  premiumAsPercentOfIncome: number | null;
  premiumAsPercentOfMonthlySurplus: number | null;
  postPremiumMonthlySurplus: number | null;
  cashflowStressIndicator: 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN';
}

export interface TaxFundingMetric {
  marginalTaxRate: number | null;
  /**
   * Contextual score 0–1 expressing how much relief the super funding channel provides
   * relative to funding the same premium from personal after-tax income.
   * 0 = no advantage; 1 = maximum advantage.
   * NOT an absolute dollar saving — expressed as a relative contextual indicator.
   */
  insideSuperRelativeFundingScore: number | null;
  personalAfterTaxBurdenFactor: number | null;
  explanation: string;
}

export interface PlacementScores {
  // Benefits (0–100 each)
  cashflowBenefit: number;
  taxFundingBenefit: number;
  convenienceBenefit: number;
  structuralProtectionBenefit: number;
  // Penalties (0–100 each)
  retirementErosionPenalty: number;
  beneficiaryTaxRiskPenalty: number;
  flexibilityControlPenalty: number;
  contributionCapPressurePenalty: number;
}

export interface CalculationsOutput {
  retirementDrag: RetirementDragEstimate | null;
  cashflowMetrics: CashflowMetrics;
  taxFundingMetric: TaxFundingMetric;
  placementScores: PlacementScores;
}

// =============================================================================
// PLACEMENT RESULT
// =============================================================================

export interface PlacementResult {
  recommendation: PlacementRecommendation;
  insideSuperScore: number; // 0–100
  outsideSuperScore: number; // 0–100
  benefitBreakdown: Record<string, number>;
  penaltyBreakdown: Record<string, number>;
  reasoning: string[];
  risks: string[];
}

// =============================================================================
// ADVICE READINESS
// =============================================================================

export interface AdviceReadinessResult {
  mode: AdviceMode;
  missingInfoQuestions: MissingInfoQuestion[];
  readinessReasons: string[];
}

// =============================================================================
// MEMBER ACTIONS
// =============================================================================

export interface MemberAction {
  actionId: string;
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  action: string;
  rationale: string;
}

// =============================================================================
// BENEFICIARY TAX RISK
// =============================================================================

export interface BeneficiaryTaxRiskAssessment {
  riskLevel: RiskLevel;
  expectedBeneficiaryCategory: BeneficiaryCategory;
  estimatedTaxableComponent: 'LIKELY_HIGH' | 'LIKELY_LOW' | 'UNKNOWN';
  explanation: string;
}

// =============================================================================
// LAW VERSION METADATA
// =============================================================================

export interface LawVersion {
  primaryAct: string;
  primaryActSection: string;
  reformName: string;
  reformCommencementDate: string;
  engineVersion: string;
  evaluatedUnderLegislationAsOf: string;
}

// =============================================================================
// FINAL ENGINE OUTPUT
// =============================================================================

export interface PurchaseRetainLifeInsuranceInSuperOutput {
  normalizedInput: NormalizedInput;
  validation: ValidationResult;
  legalStatus: LegalStatus;
  legalReasons: string[];
  switchOffTriggers: SwitchOffEvaluation[];
  exceptionsApplied: ExceptionResult[];
  memberActions: MemberAction[];
  retirementDragEstimate: RetirementDragEstimate | null;
  beneficiaryTaxRisk: BeneficiaryTaxRiskAssessment;
  placementAssessment: PlacementResult;
  placementReasons: string[];
  placementRisks: string[];
  adviceReadiness: AdviceMode;
  missingInfoQuestions: MissingInfoQuestion[];
  ruleTrace: RuleTraceEntry[];
  lawVersion: LawVersion;
}
