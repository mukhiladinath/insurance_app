// =============================================================================
// RULES — purchaseRetainLifeTPDPolicy
//
// Hard business rules applied in strict order before recommendation.
// Each rule function is pure, evaluates one condition, and returns a
// RuleTraceEntry. Rules that fire can block or modify the recommendation.
// =============================================================================

import {
  RecommendationType,
  ShortfallLevel,
  ReplacementRisk,
  UnderwritingRisk,
  ComparisonOutcome,
} from './purchaseRetainLifeTPDPolicy.enums';
import type {
  NormalizedInput,
  RuleTraceEntry,
  LifeNeedResult,
  TPDNeedResult,
  AffordabilityResult,
  PolicyComparisonResult,
  UnderwritingRiskResult,
  ReplacementRiskResult,
  ValidationResult,
} from './purchaseRetainLifeTPDPolicy.types';
import { RULE_IDS } from './purchaseRetainLifeTPDPolicy.constants';

// ---------------------------------------------------------------------------
// Rule result shape
// ---------------------------------------------------------------------------

export interface RuleEvaluation {
  fires: boolean;
  blockedRecommendation: RecommendationType | null;
  forcedRecommendation: RecommendationType | null;
  trace: RuleTraceEntry;
}

function mkRule(
  id: string,
  name: string,
  fires: boolean,
  outcome: string,
  explanation: string,
  facts: Record<string, unknown>,
  blockedRecommendation: RecommendationType | null = null,
  forcedRecommendation: RecommendationType | null = null,
): RuleEvaluation {
  return {
    fires,
    blockedRecommendation,
    forcedRecommendation,
    trace: {
      ruleId: id,
      ruleName: name,
      triggered: fires,
      outcome,
      explanation,
      supportingFacts: facts,
    },
  };
}

// =============================================================================
// R-001 — MISSING CRITICAL DATA
// If essential facts are missing, return DEFER_NO_ACTION.
// =============================================================================

export function ruleMissingCriticalData(
  validation: ValidationResult,
): RuleEvaluation {
  const hasCriticalErrors = validation.errors.length > 0;
  return mkRule(
    RULE_IDS.MISSING_CRITICAL_DATA,
    'Missing Critical Data',
    hasCriticalErrors,
    hasCriticalErrors ? 'DEFERRED' : 'PASS',
    hasCriticalErrors
      ? `${validation.errors.length} critical validation error(s). A recommendation cannot be made until these are resolved.`
      : 'All critical fields present.',
    { errorCount: validation.errors.length, errors: validation.errors.map((e) => e.message) },
    null,
    hasCriticalErrors ? RecommendationType.DEFER_NO_ACTION : null,
  );
}

// =============================================================================
// R-002 — UNDERWRITING INCOMPLETE
// Block any replacement if new underwriting is not resolved.
// =============================================================================

export function ruleUnderwritingIncomplete(
  input: NormalizedInput,
): RuleEvaluation {
  const fires =
    input.hasNewPolicyCandidate &&
    (input.newUnderwritingStatus === 'NOT_STARTED' ||
      input.newUnderwritingStatus === 'IN_PROGRESS' ||
      input.newUnderwritingStatus == null);

  return mkRule(
    RULE_IDS.UNDERWRITING_INCOMPLETE,
    'Underwriting Incomplete — Block Replacement',
    fires,
    fires ? 'REPLACEMENT_BLOCKED' : 'PASS',
    fires
      ? `New policy underwriting status is "${input.newUnderwritingStatus ?? 'unknown'}". Cannot recommend replacement until underwriting is fully resolved.`
      : 'Underwriting status is resolved or not applicable.',
    {
      hasNewPolicyCandidate: input.hasNewPolicyCandidate,
      newUnderwritingStatus: input.newUnderwritingStatus,
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
  );
}

// =============================================================================
// R-003 — EXISTING POLICY DATA INCOMPLETE
// If we cannot compare, do not recommend replacement.
// =============================================================================

export function ruleExistingPolicyDataIncomplete(
  input: NormalizedInput,
): RuleEvaluation {
  const fires =
    input.hasExistingPolicy &&
    input.existingLifeSumInsured == null &&
    input.existingTPDSumInsured == null;

  return mkRule(
    RULE_IDS.EXISTING_POLICY_DATA_INCOMPLETE,
    'Existing Policy Data Incomplete',
    fires,
    fires ? 'COMPARISON_BLOCKED' : 'PASS',
    fires
      ? 'Cannot compare policies or assess shortfall: existing policy sum insured details are missing.'
      : 'Existing policy data sufficient for comparison.',
    {
      hasExistingPolicy: input.hasExistingPolicy,
      existingLifeSumInsured: input.existingLifeSumInsured,
      existingTPDSumInsured: input.existingTPDSumInsured,
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
  );
}

// =============================================================================
// R-004 — BLOCK REPLACEMENT IF UNDERWRITING RISK IS CRITICAL
// =============================================================================

export function ruleBlockReplacementCriticalUnderwriting(
  underwritingRisk: UnderwritingRiskResult,
): RuleEvaluation {
  const fires = underwritingRisk.overallRisk === UnderwritingRisk.CRITICAL;

  return mkRule(
    RULE_IDS.BLOCK_REPLACEMENT_UNDERWRITING,
    'Block Replacement — Critical Underwriting Risk',
    fires,
    fires ? 'REFER_TO_HUMAN' : 'PASS',
    fires
      ? 'Underwriting risk is CRITICAL (likely decline or non-disclosure issue). Replacement is blocked — existing cover must be preserved. Refer to human adviser.'
      : 'Underwriting risk does not block replacement.',
    {
      overallRisk: underwritingRisk.overallRisk,
      likelyOutcome: underwritingRisk.likelyOutcome,
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
    fires ? RecommendationType.REFER_TO_HUMAN : null,
  );
}

// =============================================================================
// R-005 — BLOCK REPLACEMENT IF NEW POLICY MATERIALLY WORSE
// =============================================================================

export function ruleBlockReplacementMateriallyWorse(
  comparison: PolicyComparisonResult | null,
): RuleEvaluation {
  const fires =
    comparison != null &&
    (comparison.overallOutcome === ComparisonOutcome.NEW_MATERIALLY_WORSE ||
      comparison.overallOutcome === ComparisonOutcome.NEW_MARGINALLY_WORSE);

  return mkRule(
    RULE_IDS.BLOCK_REPLACEMENT_MATERIALLY_WORSE,
    'Block Replacement — New Policy Is Worse',
    fires,
    fires ? 'REPLACEMENT_BLOCKED' : 'PASS',
    fires
      ? `New policy comparison outcome: "${comparison?.overallOutcome}". Replacement is not in the client's best interest.`
      : 'New policy is not materially worse — replacement is not blocked by this rule.',
    {
      overallOutcome: comparison?.overallOutcome ?? null,
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
  );
}

// =============================================================================
// R-006 — BLOCK REPLACEMENT IF TPD DEFINITION WORSENS
// =============================================================================

export function ruleBlockReplacementTPDDefinitionWorsened(
  comparison: PolicyComparisonResult | null,
): RuleEvaluation {
  const fires = comparison?.tpdDefinitionChange === 'WORSENED';

  return mkRule(
    RULE_IDS.BLOCK_REPLACEMENT_TPD_DEFINITION,
    'Block Replacement — TPD Definition Worsened',
    fires,
    fires ? 'REPLACEMENT_BLOCKED' : 'PASS',
    fires
      ? 'The new policy\'s TPD definition is less favourable than the existing policy. This is a material disadvantage. Replacement blocked unless explicitly justified.'
      : 'TPD definition does not worsen with replacement.',
    {
      tpdDefinitionChange: comparison?.tpdDefinitionChange ?? null,
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
  );
}

// =============================================================================
// R-007 — BLOCK REPLACEMENT IF REPLACEMENT RISK IS BLOCKING
// =============================================================================

export function ruleBlockReplacementRisk(
  replacementRisk: ReplacementRiskResult | null,
): RuleEvaluation {
  const fires = replacementRisk?.overallRisk === ReplacementRisk.BLOCKING;

  return mkRule(
    RULE_IDS.BLOCK_REPLACEMENT_REPLACEMENT_RISK,
    'Block Replacement — Replacement Risk Is Blocking',
    fires,
    fires ? 'REPLACEMENT_BLOCKED' : 'PASS',
    fires
      ? 'Replacement risk assessment returned BLOCKING. Replacement cannot be recommended.'
      : 'Replacement risk does not block the recommendation.',
    {
      overallRisk: replacementRisk?.overallRisk ?? null,
      warnings: replacementRisk?.warnings ?? [],
    },
    fires ? RecommendationType.REPLACE_EXISTING : null,
    fires ? RecommendationType.REFER_TO_HUMAN : null,
  );
}

// =============================================================================
// R-008 — PURCHASE NEW (no existing policy, net need exists)
// =============================================================================

export function rulePurchaseNewNoCoverage(
  input: NormalizedInput,
  lifeNeed: LifeNeedResult | null,
  tpdNeed: TPDNeedResult | null,
): RuleEvaluation {
  const hasNeed =
    (lifeNeed?.netLifeInsuranceNeed ?? 0) > 0 ||
    (tpdNeed?.netTPDNeed ?? 0) > 0;

  const fires = !input.hasExistingPolicy && hasNeed;

  return mkRule(
    RULE_IDS.PURCHASE_NEW_NO_EXISTING,
    'Purchase New — No Existing Cover, Need Identified',
    fires,
    fires ? 'PURCHASE_NEW' : 'PASS',
    fires
      ? `No existing policy and an insurance need has been identified (life: $${(lifeNeed?.netLifeInsuranceNeed ?? 0).toLocaleString()}, TPD: $${(tpdNeed?.netTPDNeed ?? 0).toLocaleString()}).`
      : 'No existing policy but no quantified need, or existing policy is present.',
    {
      hasExistingPolicy: input.hasExistingPolicy,
      netLifeNeed: lifeNeed?.netLifeInsuranceNeed ?? null,
      netTPDNeed: tpdNeed?.netTPDNeed ?? null,
    },
    null,
    fires ? RecommendationType.PURCHASE_NEW : null,
  );
}

// =============================================================================
// R-009 — RETAIN EXISTING (shortfall is low or none, existing policy is sound)
// =============================================================================

export function ruleRetainExistingLowShortfall(
  input: NormalizedInput,
  lifeNeed: LifeNeedResult | null,
  tpdNeed: TPDNeedResult | null,
  comparison: PolicyComparisonResult | null,
): RuleEvaluation {
  const shortfallIsLow =
    (lifeNeed?.shortfallLevel === ShortfallLevel.NONE ||
      lifeNeed?.shortfallLevel === ShortfallLevel.MINOR) &&
    (tpdNeed?.shortfallLevel === ShortfallLevel.NONE ||
      tpdNeed?.shortfallLevel === ShortfallLevel.MINOR);

  const newPolicyNotClearlyBetter =
    comparison == null ||
    comparison.overallOutcome === ComparisonOutcome.EQUIVALENT ||
    comparison.overallOutcome === ComparisonOutcome.NEW_MARGINALLY_WORSE ||
    comparison.overallOutcome === ComparisonOutcome.NEW_MATERIALLY_WORSE;

  const fires = input.hasExistingPolicy && shortfallIsLow && newPolicyNotClearlyBetter;

  return mkRule(
    RULE_IDS.RETAIN_LOW_SHORTFALL,
    'Retain Existing — Shortfall Is Low and Policy Is Sound',
    fires,
    fires ? 'RETAIN_EXISTING' : 'PASS',
    fires
      ? 'Existing policy shortfall is nil or minor. No compelling case to replace or supplement at this time.'
      : 'Shortfall is not low or a better alternative exists.',
    {
      lifeShortfallLevel: lifeNeed?.shortfallLevel ?? null,
      tpdShortfallLevel: tpdNeed?.shortfallLevel ?? null,
      comparisonOutcome: comparison?.overallOutcome ?? null,
    },
    null,
    fires ? RecommendationType.RETAIN_EXISTING : null,
  );
}

// =============================================================================
// R-010 — SUPPLEMENT EXISTING (policy sound but shortfall is significant)
// =============================================================================

export function ruleSupplementExistingSignificantShortfall(
  input: NormalizedInput,
  lifeNeed: LifeNeedResult | null,
  tpdNeed: TPDNeedResult | null,
  comparison: PolicyComparisonResult | null,
): RuleEvaluation {
  const significantShortfall =
    (lifeNeed?.shortfallLevel === ShortfallLevel.MODERATE ||
      lifeNeed?.shortfallLevel === ShortfallLevel.SIGNIFICANT ||
      lifeNeed?.shortfallLevel === ShortfallLevel.CRITICAL) ||
    (tpdNeed?.shortfallLevel === ShortfallLevel.MODERATE ||
      tpdNeed?.shortfallLevel === ShortfallLevel.SIGNIFICANT ||
      tpdNeed?.shortfallLevel === ShortfallLevel.CRITICAL);

  // Supplement is preferred when: existing policy is not being replaced outright
  const newPolicyNotClearlyBetter =
    comparison == null ||
    comparison.overallOutcome !== ComparisonOutcome.NEW_MATERIALLY_BETTER;

  const fires = input.hasExistingPolicy && significantShortfall && newPolicyNotClearlyBetter;

  return mkRule(
    RULE_IDS.SUPPLEMENT_POLICY_STRONG,
    'Supplement Existing — Shortfall Present, Existing Policy Retained',
    fires,
    fires ? 'SUPPLEMENT_EXISTING' : 'PASS',
    fires
      ? 'Existing policy is retained but an insurance shortfall has been identified. Additional cover should be obtained to supplement existing cover.'
      : 'Supplement condition not met.',
    {
      lifeShortfallLevel: lifeNeed?.shortfallLevel ?? null,
      tpdShortfallLevel: tpdNeed?.shortfallLevel ?? null,
    },
    null,
    fires ? RecommendationType.SUPPLEMENT_EXISTING : null,
  );
}

// =============================================================================
// R-011 — REDUCE COVER (affordability critical, policy still needed)
// =============================================================================

export function ruleReduceCoverAffordability(
  input: NormalizedInput,
  affordability: AffordabilityResult,
  lifeNeed: LifeNeedResult | null,
  tpdNeed: TPDNeedResult | null,
): RuleEvaluation {
  const affordabilityStressed = affordability.assessment === 'UNAFFORDABLE';
  const stillHasNeed =
    (lifeNeed?.shortfallLevel !== ShortfallLevel.NONE) ||
    (tpdNeed?.shortfallLevel !== ShortfallLevel.NONE);

  const fires =
    input.hasExistingPolicy && affordabilityStressed && !stillHasNeed;

  return mkRule(
    RULE_IDS.REDUCE_COVER_AFFORDABILITY,
    'Reduce Cover — Affordability Crisis, Cover Still Valuable',
    fires,
    fires ? 'REDUCE_COVER' : 'PASS',
    fires
      ? 'Premiums are unaffordable and there is no current shortfall. Consider reducing sum insured to ease premium burden while retaining essential cover.'
      : 'Reduce cover rule does not apply.',
    {
      assessment: affordability.assessment,
      affordabilityScore: affordability.affordabilityScore,
      lifeShortfall: lifeNeed?.shortfallLevel ?? null,
      tpdShortfall: tpdNeed?.shortfallLevel ?? null,
    },
    null,
    fires ? RecommendationType.REDUCE_COVER : null,
  );
}

// =============================================================================
// R-012 — REPLACE EXISTING (new policy materially better AND replacement safe)
// =============================================================================

export function ruleReplaceIfMateriallyBetter(
  input: NormalizedInput,
  comparison: PolicyComparisonResult | null,
  replacementRisk: ReplacementRiskResult | null,
  blockedRecommendations: Set<RecommendationType>,
): RuleEvaluation {
  const newIsMateriallyBetter =
    comparison?.overallOutcome === ComparisonOutcome.NEW_MATERIALLY_BETTER;

  const replacementIsSafe =
    replacementRisk == null ||
    replacementRisk.overallRisk === ReplacementRisk.NEGLIGIBLE ||
    replacementRisk.overallRisk === ReplacementRisk.LOW;

  const replacementNotBlocked = !blockedRecommendations.has(RecommendationType.REPLACE_EXISTING);

  const fires =
    input.hasExistingPolicy &&
    newIsMateriallyBetter &&
    replacementIsSafe &&
    replacementNotBlocked;

  return mkRule(
    RULE_IDS.REPLACE_MATERIALLY_BETTER,
    'Replace Existing — New Policy Materially Better and Replacement Safe',
    fires,
    fires ? 'REPLACE_EXISTING' : 'PASS',
    fires
      ? 'New policy is materially better across comparison dimensions and replacement risk is low. Replacement is recommended.'
      : 'Replacement conditions not fully met (new policy may not be materially better, or replacement risk is elevated).',
    {
      overallOutcome: comparison?.overallOutcome ?? null,
      replacementRisk: replacementRisk?.overallRisk ?? null,
      replacementNotBlocked,
    },
    null,
    fires ? RecommendationType.REPLACE_EXISTING : null,
  );
}

// =============================================================================
// R-013 — REFER TO HUMAN (catch-all for unresolvable / high-risk cases)
// =============================================================================

export function ruleReferToHuman(
  underwritingRisk: UnderwritingRiskResult,
  replacementRisk: ReplacementRiskResult | null,
  input: NormalizedInput,
): RuleEvaluation {
  const fires =
    underwritingRisk.overallRisk === UnderwritingRisk.CRITICAL ||
    replacementRisk?.overallRisk === ReplacementRisk.BLOCKING ||
    input.nonDisclosureRisk;

  return mkRule(
    RULE_IDS.REFER_DATA_MISSING,
    'Refer to Human Adviser',
    fires,
    fires ? 'REFER_TO_HUMAN' : 'PASS',
    fires
      ? 'Case complexity or risk level requires human adviser review before any recommendation can be made or acted upon.'
      : 'No referral trigger found.',
    {
      underwritingRisk: underwritingRisk.overallRisk,
      replacementRisk: replacementRisk?.overallRisk ?? null,
      nonDisclosureRisk: input.nonDisclosureRisk,
    },
    null,
    fires ? RecommendationType.REFER_TO_HUMAN : null,
  );
}
