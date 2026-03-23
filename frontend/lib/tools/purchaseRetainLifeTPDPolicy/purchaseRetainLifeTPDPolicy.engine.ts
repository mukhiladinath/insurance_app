// =============================================================================
// ENGINE — purchaseRetainLifeTPDPolicy
//
// Top-level orchestrator. Single public entry point.
//
// Execution order:
//   1. Normalize input
//   2. Validate
//   3. Run calculations (life need, TPD need, affordability)
//   4. Run policy comparison
//   5. Assess underwriting risk
//   6. Assess replacement risk
//   7. Apply hard rules (in strict order)
//   8. Generate compliance flags
//   9. Generate required actions
//   10. Assemble final output
// =============================================================================

import {
  AdviceMode,
  CoverType,
  EmploymentType,
  OccupationClass,
  PolicyOwnership,
  PremiumStructure,
  RecommendationType,
  TPDDefinitionType,
} from './purchaseRetainLifeTPDPolicy.enums';
import type {
  PurchaseRetainLifeTPDPolicyInput,
  PurchaseRetainLifeTPDPolicyOutput,
  NormalizedInput,
  RecommendationResult,
  RequiredAction,
  RuleTraceEntry,
} from './purchaseRetainLifeTPDPolicy.types';
import { ENGINE_VERSION } from './purchaseRetainLifeTPDPolicy.constants';
import { safeParseDate, computeAge } from './purchaseRetainLifeTPDPolicy.utils';
import { validateInput } from './purchaseRetainLifeTPDPolicy.validators';
import {
  calculateLifeNeed,
  calculateTPDNeed,
  calculateAffordability,
} from './purchaseRetainLifeTPDPolicy.calculators';
import { comparePolicies } from './purchaseRetainLifeTPDPolicy.comparison';
import {
  assessUnderwritingRisk,
  assessReplacementRisk,
} from './purchaseRetainLifeTPDPolicy.underwriting';
import { generateComplianceFlags } from './purchaseRetainLifeTPDPolicy.compliance';
import {
  ruleMissingCriticalData,
  ruleUnderwritingIncomplete,
  ruleExistingPolicyDataIncomplete,
  ruleBlockReplacementCriticalUnderwriting,
  ruleBlockReplacementMateriallyWorse,
  ruleBlockReplacementTPDDefinitionWorsened,
  ruleBlockReplacementRisk,
  rulePurchaseNewNoCoverage,
  ruleRetainExistingLowShortfall,
  ruleSupplementExistingSignificantShortfall,
  ruleReduceCoverAffordability,
  ruleReplaceIfMateriallyBetter,
  ruleReferToHuman,
} from './purchaseRetainLifeTPDPolicy.rules';

// =============================================================================
// STEP 1 — NORMALIZE INPUT
// =============================================================================

function normalizeInput(raw: PurchaseRetainLifeTPDPolicyInput): NormalizedInput {
  const evaluationDate = safeParseDate(raw.evaluationDate) ?? new Date();
  const c = raw.client;
  const ep = raw.existingPolicy;
  const h = raw.health;
  const g = raw.goals;
  const np = raw.newPolicyCandidate;

  const dobParsed = safeParseDate(c?.dateOfBirth);
  let age: number | null = c?.age ?? null;
  if (age == null && dobParsed) {
    age = computeAge(dobParsed, evaluationDate);
  }

  return {
    adviceMode: raw.adviceMode ?? AdviceMode.PERSONAL_ADVICE,
    evaluationDate,
    // Client
    age,
    dateOfBirth: dobParsed,
    smoker: c?.smoker ?? false,
    occupation: c?.occupation ?? null,
    occupationClass: c?.occupationClass ?? OccupationClass.UNKNOWN,
    employmentType: c?.employmentType ?? EmploymentType.UNKNOWN,
    annualGrossIncome: c?.annualGrossIncome ?? null,
    annualNetIncome: c?.annualNetIncome ?? null,
    hasPartner: c?.hasPartner ?? null,
    partnerIncome: c?.partnerIncome ?? null,
    numberOfDependants: c?.numberOfDependants ?? null,
    youngestDependantAge: c?.youngestDependantAge ?? null,
    mortgageBalance: c?.mortgageBalance ?? null,
    otherDebts: c?.otherDebts ?? null,
    liquidAssets: c?.liquidAssets ?? null,
    existingLifeCoverSumInsured: c?.existingLifeCoverSumInsured ?? null,
    existingTPDCoverSumInsured: c?.existingTPDCoverSumInsured ?? null,
    yearsToRetirement: c?.yearsToRetirement ?? null,
    // Existing policy
    hasExistingPolicy: ep?.hasExistingPolicy ?? false,
    existingInsurer: ep?.insurer ?? null,
    existingOwnership: ep?.ownership ?? PolicyOwnership.UNKNOWN,
    existingCommencementDate: safeParseDate(ep?.commencementDate),
    existingCoverTypes: ep?.coverTypes ?? [],
    existingLifeSumInsured: ep?.lifeSumInsured ?? null,
    existingTPDSumInsured: ep?.tpdSumInsured ?? null,
    existingTPDDefinition: ep?.tpdDefinition ?? TPDDefinitionType.UNKNOWN,
    existingPremiumStructure: ep?.premiumStructure ?? PremiumStructure.UNKNOWN,
    existingAnnualPremium: ep?.annualPremium ?? null,
    existingHasLoadings: ep?.hasLoadings ?? false,
    existingLoadingDetails: ep?.loadingDetails ?? null,
    existingHasExclusions: ep?.hasExclusions ?? false,
    existingExclusionDetails: ep?.exclusionDetails ?? null,
    existingHasIndexation: ep?.hasIndexation ?? false,
    existingRiders: ep?.riders ?? [],
    existingHasFullNonDisclosureRisk: ep?.hasFullNonDisclosureRisk ?? false,
    existingHasSuperiorGrandfatheredTerms: ep?.hasSuperiorGrandfatheredTerms ?? false,
    // Health
    heightCm: h?.heightCm ?? null,
    weightKg: h?.weightKg ?? null,
    existingMedicalConditions: h?.existingMedicalConditions ?? [],
    currentMedications: h?.currentMedications ?? [],
    pendingInvestigations: h?.pendingInvestigations ?? false,
    pendingInvestigationDetails: h?.pendingInvestigationDetails ?? null,
    familyHistoryConditions: h?.familyHistoryConditions ?? [],
    hazardousActivities: h?.hazardousActivities ?? [],
    nonDisclosureRisk: h?.nonDisclosureRisk ?? false,
    // Goals
    primaryReason: g?.primaryReason ?? null,
    wantsReplacement: g?.wantsReplacement ?? null,
    wantsRetention: g?.wantsRetention ?? null,
    affordabilityIsConcern: g?.affordabilityIsConcern ?? null,
    wantsPremiumCertainty: g?.wantsPremiumCertainty ?? null,
    wantsOwnOccupationTPD: g?.wantsOwnOccupationTPD ?? null,
    desiredCoverHorizon: g?.desiredCoverHorizon ?? null,
    willingToUnderwrite: g?.willingToUnderwrite ?? null,
    prioritisesDefinitionQuality: g?.prioritisesDefinitionQuality ?? null,
    prioritisesClaimsReputation: g?.prioritisesClaimsReputation ?? null,
    // New policy candidate
    hasNewPolicyCandidate: np != null && np.insurer != null,
    newInsurer: np?.insurer ?? null,
    newOwnership: np?.ownership ?? PolicyOwnership.UNKNOWN,
    newCoverTypes: np?.coverTypes ?? [],
    newLifeSumInsured: np?.lifeSumInsured ?? null,
    newTPDSumInsured: np?.tpdSumInsured ?? null,
    newTPDDefinition: np?.tpdDefinition ?? TPDDefinitionType.UNKNOWN,
    newPremiumStructure: np?.premiumStructure ?? PremiumStructure.UNKNOWN,
    newProjectedAnnualPremium: np?.projectedAnnualPremium ?? null,
    newExpectedLoadings: np?.expectedLoadings ?? null,
    newExpectedExclusions: np?.expectedExclusions ?? null,
    newHasIndexation: np?.hasIndexation ?? false,
    newFlexibilityFeatures: np?.flexibilityFeatures ?? [],
    newClaimsQualityRating: np?.claimsQualityRating ?? null,
    newUnderwritingStatus: np?.underwritingStatus ?? undefined,
  };
}

// =============================================================================
// STEP 9 — GENERATE REQUIRED ACTIONS
// =============================================================================

function generateRequiredActions(
  recommendation: RecommendationType,
  input: NormalizedInput,
  ruleTrace: RuleTraceEntry[],
): RequiredAction[] {
  const actions: RequiredAction[] = [];

  if (recommendation === RecommendationType.REFER_TO_HUMAN) {
    actions.push({
      actionId: 'ACT-001',
      priority: 'CRITICAL',
      action: 'Escalate to an experienced human adviser before taking any further action.',
      rationale: 'Case complexity, critical underwriting risk, or non-disclosure risk prevents automated recommendation.',
    });
  }

  if (input.pendingInvestigations) {
    actions.push({
      actionId: 'ACT-002',
      priority: 'CRITICAL',
      action: 'Pause all insurance decisions until pending medical investigations are resolved.',
      rationale: 'Unknown medical investigation outcome creates high underwriting risk and replacement danger.',
    });
  }

  if (input.nonDisclosureRisk) {
    actions.push({
      actionId: 'ACT-003',
      priority: 'CRITICAL',
      action: 'Engage a specialist adviser to review non-disclosure risk with both existing insurer and any proposed new insurer.',
      rationale: 'Non-disclosure risk can void existing and future coverage — must be resolved by an expert.',
    });
  }

  if (
    recommendation === RecommendationType.REPLACE_EXISTING ||
    recommendation === RecommendationType.SUPPLEMENT_EXISTING
  ) {
    actions.push({
      actionId: 'ACT-004',
      priority: 'HIGH',
      action: 'Ensure new policy underwriting is fully accepted before cancelling or reducing existing cover.',
      rationale: 'Cancelling existing cover before new cover is confirmed creates an unacceptable coverage gap.',
    });
  }

  if (recommendation === RecommendationType.PURCHASE_NEW) {
    actions.push({
      actionId: 'ACT-005',
      priority: 'HIGH',
      action: 'Obtain quotes from multiple insurers and complete full underwriting before committing.',
      rationale: 'Health and occupation factors may affect the terms available — a full market comparison is needed.',
    });
  }

  if (
    recommendation === RecommendationType.RETAIN_EXISTING &&
    input.existingHasSuperiorGrandfatheredTerms
  ) {
    actions.push({
      actionId: 'ACT-006',
      priority: 'MEDIUM',
      action: 'Document the superior grandfathered terms on the existing policy in the client file.',
      rationale: 'Grandfathered terms should be clearly noted so future advisers do not inadvertently recommend replacement.',
    });
  }

  if (recommendation === RecommendationType.REDUCE_COVER) {
    actions.push({
      actionId: 'ACT-007',
      priority: 'MEDIUM',
      action: 'Model reduced sum insured options with the existing insurer to achieve an affordable premium before exploring alternatives.',
      rationale: 'Reducing cover with the existing insurer avoids underwriting risk and preserves existing terms.',
    });
  }

  return actions;
}

// =============================================================================
// MAIN ORCHESTRATOR
// =============================================================================

export function runPurchaseRetainLifeTPDPolicyWorkflow(
  rawInput: PurchaseRetainLifeTPDPolicyInput,
): PurchaseRetainLifeTPDPolicyOutput {
  // -------------------------------------------------------------------------
  // 1. Normalize
  // -------------------------------------------------------------------------
  const input = normalizeInput(rawInput);

  // -------------------------------------------------------------------------
  // 2. Validate
  // -------------------------------------------------------------------------
  const validation = validateInput(rawInput);

  // -------------------------------------------------------------------------
  // 3. Calculations
  // -------------------------------------------------------------------------
  const lifeNeed = validation.isValid ? calculateLifeNeed(input) : null;
  const tpdNeed = validation.isValid ? calculateTPDNeed(input) : null;
  const affordability = calculateAffordability(input);

  // -------------------------------------------------------------------------
  // 4. Policy comparison
  // -------------------------------------------------------------------------
  const comparison = comparePolicies(input);

  // -------------------------------------------------------------------------
  // 5. Underwriting risk
  // -------------------------------------------------------------------------
  const underwritingRisk = assessUnderwritingRisk(input);

  // -------------------------------------------------------------------------
  // 6. Replacement risk
  // -------------------------------------------------------------------------
  const replacementRisk = input.hasExistingPolicy
    ? assessReplacementRisk(input, underwritingRisk, comparison)
    : null;

  // -------------------------------------------------------------------------
  // 7. Apply hard rules in strict order
  // -------------------------------------------------------------------------
  const ruleTrace: RuleTraceEntry[] = [];
  const blockedRecommendations = new Set<RecommendationType>();
  let forcedRecommendation: RecommendationType | null = null;

  function applyRule(
    eval_: ReturnType<typeof ruleMissingCriticalData>,
  ): void {
    ruleTrace.push(eval_.trace);
    if (eval_.blockedRecommendation) {
      blockedRecommendations.add(eval_.blockedRecommendation);
    }
    // First forced recommendation wins (earlier rules take precedence)
    if (eval_.forcedRecommendation && forcedRecommendation == null) {
      forcedRecommendation = eval_.forcedRecommendation;
    }
  }

  // Order is critical — blocking rules first
  applyRule(ruleMissingCriticalData(validation));
  applyRule(ruleReferToHuman(underwritingRisk, replacementRisk, input));
  applyRule(ruleUnderwritingIncomplete(input));
  applyRule(ruleExistingPolicyDataIncomplete(input));
  applyRule(ruleBlockReplacementCriticalUnderwriting(underwritingRisk));
  applyRule(ruleBlockReplacementMateriallyWorse(comparison));
  applyRule(ruleBlockReplacementTPDDefinitionWorsened(comparison));
  applyRule(ruleBlockReplacementRisk(replacementRisk));

  // If forced recommendation from blocking rules — skip positive rules
  if (forcedRecommendation == null) {
    applyRule(rulePurchaseNewNoCoverage(input, lifeNeed, tpdNeed));
    if (forcedRecommendation == null) {
      applyRule(ruleRetainExistingLowShortfall(input, lifeNeed, tpdNeed, comparison));
    }
    if (forcedRecommendation == null) {
      applyRule(ruleReplaceIfMateriallyBetter(input, comparison, replacementRisk, blockedRecommendations));
    }
    if (forcedRecommendation == null) {
      applyRule(ruleSupplementExistingSignificantShortfall(input, lifeNeed, tpdNeed, comparison));
    }
    if (forcedRecommendation == null) {
      applyRule(ruleReduceCoverAffordability(input, affordability, lifeNeed, tpdNeed));
    }
  }

  // Final fallback
  const finalRecommendationType: RecommendationType =
    forcedRecommendation ??
    (validation.isValid ? RecommendationType.DEFER_NO_ACTION : RecommendationType.DEFER_NO_ACTION);

  // -------------------------------------------------------------------------
  // 8. Compliance flags
  // -------------------------------------------------------------------------
  const complianceFlags = generateComplianceFlags(
    input,
    finalRecommendationType,
    underwritingRisk,
    replacementRisk,
    comparison,
  );

  // -------------------------------------------------------------------------
  // 9. Required actions
  // -------------------------------------------------------------------------
  const requiredActions = generateRequiredActions(
    finalRecommendationType,
    input,
    ruleTrace,
  );

  // -------------------------------------------------------------------------
  // 10. Build recommendation summary
  // -------------------------------------------------------------------------
  const reasons: string[] = ruleTrace
    .filter((r) => r.triggered)
    .map((r) => r.explanation);

  const risks: string[] = [
    ...(comparison?.replacementWarnings ?? []),
    ...(replacementRisk?.warnings ?? []),
    ...(underwritingRisk.recommendations ?? []),
  ];

  const summaryMap: Record<RecommendationType, string> = {
    [RecommendationType.PURCHASE_NEW]:
      'Based on the identified insurance need and no existing cover, purchasing new life and/or TPD cover is recommended.',
    [RecommendationType.RETAIN_EXISTING]:
      'The existing policy meets current needs. No replacement or supplementation is required at this time.',
    [RecommendationType.REPLACE_EXISTING]:
      'The new policy is materially better and replacement risk is low. Replacing the existing policy is recommended subject to compliance and disclosure requirements.',
    [RecommendationType.SUPPLEMENT_EXISTING]:
      'The existing policy is sound but an insurance shortfall exists. Supplementing with additional cover alongside the existing policy is recommended.',
    [RecommendationType.REDUCE_COVER]:
      'Premium affordability is under pressure. Reducing the sum insured on the existing policy is recommended to manage premium costs while retaining valuable cover.',
    [RecommendationType.DEFER_NO_ACTION]:
      'Insufficient information or conditions are not suitable for a recommendation at this time. Review when more information is available.',
    [RecommendationType.REFER_TO_HUMAN]:
      'This case requires review by a qualified human adviser before any action is taken.',
  };

  const recommendationResult: RecommendationResult = {
    type: finalRecommendationType,
    adviceMode: input.adviceMode,
    summary: summaryMap[finalRecommendationType],
    reasons,
    risks,
    requiredActions,
    lifeNeed,
    tpdNeed,
    affordability,
    comparison: comparison.hasComparisonCandidate ? comparison : null,
    underwritingRisk,
    replacementRisk,
    complianceFlags,
    ruleTrace,
  };

  // -------------------------------------------------------------------------
  // Merge missing info questions (dedup by id)
  // -------------------------------------------------------------------------
  const allMissingQuestions = validation.missingInfoQuestions.filter(
    (q, i, arr) => arr.findIndex((x) => x.id === q.id) === i,
  );

  return {
    normalizedInput: input,
    validation,
    recommendation: recommendationResult,
    missingInfoQuestions: allMissingQuestions,
    engineVersion: ENGINE_VERSION,
    evaluatedAt: new Date().toISOString(),
  };
}
