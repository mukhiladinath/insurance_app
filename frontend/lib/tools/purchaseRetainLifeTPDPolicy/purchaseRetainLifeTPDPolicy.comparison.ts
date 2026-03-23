// =============================================================================
// COMPARISON — purchaseRetainLifeTPDPolicy
//
// Policy comparison logic: existing policy vs new candidate across all dimensions.
// =============================================================================

import {
  ComparisonOutcome,
  TPDDefinitionType,
} from './purchaseRetainLifeTPDPolicy.enums';
import type {
  NormalizedInput,
  PolicyComparisonResult,
  PolicyComparisonDimension,
} from './purchaseRetainLifeTPDPolicy.types';
import {
  TPD_DEFINITION_RANK,
  COMPARISON_WEIGHTS,
  COMPARISON_MATERIALLY_BETTER_THRESHOLD,
  COMPARISON_MARGINALLY_BETTER_THRESHOLD,
} from './purchaseRetainLifeTPDPolicy.constants';
import { round } from './purchaseRetainLifeTPDPolicy.utils';

// ---------------------------------------------------------------------------
// TPD Definition helpers
// ---------------------------------------------------------------------------

/**
 * Compare two TPD definitions and return whether new is better, same, or worse.
 */
function compareTPDDefinitions(
  existing: TPDDefinitionType,
  newDef: TPDDefinitionType,
): PolicyComparisonDimension['verdict'] {
  const existingRank = TPD_DEFINITION_RANK[existing] ?? 0;
  const newRank = TPD_DEFINITION_RANK[newDef] ?? 0;
  if (newRank > existingRank) return 'NEW_BETTER';
  if (newRank === existingRank) return 'EQUIVALENT';
  return 'NEW_WORSE';
}

// ---------------------------------------------------------------------------
// Main comparison function
// ---------------------------------------------------------------------------

export function comparePolicies(input: NormalizedInput): PolicyComparisonResult {
  if (!input.hasNewPolicyCandidate) {
    return {
      hasComparisonCandidate: false,
      overallOutcome: ComparisonOutcome.INSUFFICIENT_DATA,
      dimensions: [],
      premiumDifferenceAnnual: null,
      sumInsuredDifferenceLife: null,
      sumInsuredDifferenceTPD: null,
      tpdDefinitionChange: 'UNKNOWN',
      exclusionChange: 'UNKNOWN',
      loadingChange: 'UNKNOWN',
      reasoning: ['No new policy candidate provided — comparison cannot be performed.'],
      replacementWarnings: [],
    };
  }

  const dimensions: PolicyComparisonDimension[] = [];
  const reasoning: string[] = [];
  const replacementWarnings: string[] = [];
  let weightedDelta = 0; // positive = new is better

  // -------------------------------------------------------------------------
  // 1. Premium comparison
  // -------------------------------------------------------------------------
  const existingPremium = input.existingAnnualPremium;
  const newPremium = input.newProjectedAnnualPremium;
  const premiumDifferenceAnnual =
    existingPremium != null && newPremium != null
      ? round(existingPremium - newPremium, 0)
      : null;

  let premiumVerdict: PolicyComparisonDimension['verdict'] = 'UNKNOWN';
  if (existingPremium != null && newPremium != null) {
    if (newPremium < existingPremium * 0.95) premiumVerdict = 'NEW_BETTER';
    else if (newPremium > existingPremium * 1.05) premiumVerdict = 'NEW_WORSE';
    else premiumVerdict = 'EQUIVALENT';
  }
  const premiumScore =
    premiumVerdict === 'NEW_BETTER' ? 1 : premiumVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += premiumScore * COMPARISON_WEIGHTS.premium;

  dimensions.push({
    dimension: 'Premium',
    existingValue: existingPremium ?? null,
    newValue: newPremium ?? null,
    verdict: premiumVerdict,
    weight: COMPARISON_WEIGHTS.premium,
    notes:
      premiumDifferenceAnnual != null
        ? premiumDifferenceAnnual > 0
          ? `New policy is $${premiumDifferenceAnnual.toLocaleString()} cheaper p.a.`
          : premiumDifferenceAnnual < 0
            ? `New policy is $${Math.abs(premiumDifferenceAnnual).toLocaleString()} more expensive p.a.`
            : 'Premiums are approximately equivalent.'
        : 'Premium comparison unavailable.',
  });

  // -------------------------------------------------------------------------
  // 2. Sum insured comparison
  // -------------------------------------------------------------------------
  const existingLifeSI = input.existingLifeSumInsured;
  const newLifeSI = input.newLifeSumInsured;
  const sumInsuredDifferenceLife =
    existingLifeSI != null && newLifeSI != null ? newLifeSI - existingLifeSI : null;

  let siVerdict: PolicyComparisonDimension['verdict'] = 'UNKNOWN';
  if (existingLifeSI != null && newLifeSI != null) {
    if (newLifeSI > existingLifeSI * 1.05) siVerdict = 'NEW_BETTER';
    else if (newLifeSI < existingLifeSI * 0.95) siVerdict = 'NEW_WORSE';
    else siVerdict = 'EQUIVALENT';
  }
  const siScore = siVerdict === 'NEW_BETTER' ? 1 : siVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += siScore * COMPARISON_WEIGHTS.sumInsured;

  dimensions.push({
    dimension: 'Life Sum Insured',
    existingValue: existingLifeSI ?? null,
    newValue: newLifeSI ?? null,
    verdict: siVerdict,
    weight: COMPARISON_WEIGHTS.sumInsured,
    notes:
      sumInsuredDifferenceLife != null
        ? `New policy life sum insured differs by $${Math.abs(sumInsuredDifferenceLife).toLocaleString()}.`
        : 'Life sum insured comparison unavailable.',
  });

  // -------------------------------------------------------------------------
  // 3. TPD definition comparison
  // -------------------------------------------------------------------------
  const existingTPDDef = input.existingTPDDefinition ?? TPDDefinitionType.UNKNOWN;
  const newTPDDef = input.newTPDDefinition ?? TPDDefinitionType.UNKNOWN;

  const tpdDefinitionVerdict =
    existingTPDDef !== TPDDefinitionType.UNKNOWN && newTPDDef !== TPDDefinitionType.UNKNOWN
      ? compareTPDDefinitions(existingTPDDef, newTPDDef)
      : 'UNKNOWN';

  const tpdScore = tpdDefinitionVerdict === 'NEW_BETTER' ? 1 : tpdDefinitionVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += tpdScore * COMPARISON_WEIGHTS.tpdDefinition;

  const existingTPDRank = TPD_DEFINITION_RANK[existingTPDDef];
  const newTPDRank = TPD_DEFINITION_RANK[newTPDDef];

  let tpdDefinitionChange: PolicyComparisonResult['tpdDefinitionChange'] = 'UNKNOWN';
  if (existingTPDDef !== TPDDefinitionType.UNKNOWN && newTPDDef !== TPDDefinitionType.UNKNOWN) {
    if (newTPDRank > existingTPDRank) tpdDefinitionChange = 'IMPROVED';
    else if (newTPDRank === existingTPDRank) tpdDefinitionChange = 'SAME';
    else tpdDefinitionChange = 'WORSENED';
  }

  if (tpdDefinitionChange === 'WORSENED') {
    replacementWarnings.push(
      `TPD definition WORSENED: changing from "${existingTPDDef}" to "${newTPDDef}". ` +
      'This is a material disadvantage and significantly raises the replacement risk. A replacement recommendation is blocked unless explicitly justified.',
    );
  }

  dimensions.push({
    dimension: 'TPD Definition',
    existingValue: existingTPDDef,
    newValue: newTPDDef,
    verdict: tpdDefinitionVerdict,
    weight: COMPARISON_WEIGHTS.tpdDefinition,
    notes:
      tpdDefinitionChange !== 'UNKNOWN'
        ? `TPD definition change: ${tpdDefinitionChange} (${existingTPDDef} → ${newTPDDef}).`
        : 'TPD definition comparison unavailable.',
  });

  // -------------------------------------------------------------------------
  // 4. Exclusions comparison
  // -------------------------------------------------------------------------
  const existingHasExclusions = input.existingHasExclusions;
  const newHasExclusions = input.newExpectedExclusions != null && input.newExpectedExclusions.length > 0;

  let exclusionVerdict: PolicyComparisonDimension['verdict'] = 'UNKNOWN';
  let exclusionChange: PolicyComparisonResult['exclusionChange'] = 'UNKNOWN';

  if (!existingHasExclusions && newHasExclusions) {
    exclusionVerdict = 'NEW_WORSE';
    exclusionChange = 'MORE';
    replacementWarnings.push('New policy introduces exclusions not present on the existing policy.');
  } else if (existingHasExclusions && !newHasExclusions) {
    exclusionVerdict = 'NEW_BETTER';
    exclusionChange = 'FEWER';
  } else if (!existingHasExclusions && !newHasExclusions) {
    exclusionVerdict = 'EQUIVALENT';
    exclusionChange = 'SAME';
  } else {
    exclusionVerdict = 'EQUIVALENT';
    exclusionChange = 'SAME';
  }

  const exclusionScore = exclusionVerdict === 'NEW_BETTER' ? 1 : exclusionVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += exclusionScore * COMPARISON_WEIGHTS.exclusions;

  dimensions.push({
    dimension: 'Exclusions',
    existingValue: existingHasExclusions ? input.existingExclusionDetails ?? 'Yes' : 'None',
    newValue: newHasExclusions ? input.newExpectedExclusions ?? 'Yes' : 'None',
    verdict: exclusionVerdict,
    weight: COMPARISON_WEIGHTS.exclusions,
    notes: `Exclusion change: ${exclusionChange}.`,
  });

  // -------------------------------------------------------------------------
  // 5. Loadings comparison
  // -------------------------------------------------------------------------
  const existingHasLoadings = input.existingHasLoadings;
  const newHasLoadings =
    input.newExpectedLoadings != null && input.newExpectedLoadings.length > 0;

  let loadingVerdict: PolicyComparisonDimension['verdict'] = 'UNKNOWN';
  let loadingChange: PolicyComparisonResult['loadingChange'] = 'UNKNOWN';

  if (!existingHasLoadings && newHasLoadings) {
    loadingVerdict = 'NEW_WORSE';
    loadingChange = 'INCREASED';
    replacementWarnings.push('New policy introduces premium loadings not present on the existing policy.');
  } else if (existingHasLoadings && !newHasLoadings) {
    loadingVerdict = 'NEW_BETTER';
    loadingChange = 'REDUCED';
  } else if (!existingHasLoadings && !newHasLoadings) {
    loadingVerdict = 'EQUIVALENT';
    loadingChange = 'SAME';
  } else {
    loadingVerdict = 'EQUIVALENT';
    loadingChange = 'SAME';
  }

  const loadingScore = loadingVerdict === 'NEW_BETTER' ? 1 : loadingVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += loadingScore * COMPARISON_WEIGHTS.loadings;

  dimensions.push({
    dimension: 'Loadings',
    existingValue: existingHasLoadings ? input.existingLoadingDetails ?? 'Yes' : 'None',
    newValue: newHasLoadings ? input.newExpectedLoadings : 'None',
    verdict: loadingVerdict,
    weight: COMPARISON_WEIGHTS.loadings,
    notes: `Loading change: ${loadingChange}.`,
  });

  // -------------------------------------------------------------------------
  // 6. Flexibility comparison
  // -------------------------------------------------------------------------
  const existingRidersCount = input.existingRiders.length;
  const newFeaturesCount = input.newFlexibilityFeatures.length;

  let flexVerdict: PolicyComparisonDimension['verdict'] = 'UNKNOWN';
  if (existingRidersCount === 0 && newFeaturesCount === 0) flexVerdict = 'EQUIVALENT';
  else if (newFeaturesCount > existingRidersCount) flexVerdict = 'NEW_BETTER';
  else if (newFeaturesCount < existingRidersCount) flexVerdict = 'NEW_WORSE';
  else flexVerdict = 'EQUIVALENT';

  const flexScore = flexVerdict === 'NEW_BETTER' ? 1 : flexVerdict === 'NEW_WORSE' ? -1 : 0;
  weightedDelta += flexScore * COMPARISON_WEIGHTS.flexibility;

  dimensions.push({
    dimension: 'Flexibility / Riders',
    existingValue: existingRidersCount > 0 ? input.existingRiders.join(', ') : 'None',
    newValue: newFeaturesCount > 0 ? input.newFlexibilityFeatures.join(', ') : 'None',
    verdict: flexVerdict,
    weight: COMPARISON_WEIGHTS.flexibility,
    notes: `Existing riders: ${existingRidersCount}. New features: ${newFeaturesCount}.`,
  });

  // -------------------------------------------------------------------------
  // Overall outcome
  // -------------------------------------------------------------------------
  let overallOutcome: ComparisonOutcome;

  if (weightedDelta >= COMPARISON_MATERIALLY_BETTER_THRESHOLD) {
    overallOutcome = ComparisonOutcome.NEW_MATERIALLY_BETTER;
    reasoning.push(`New policy scores materially better overall (weighted delta: +${round(weightedDelta, 3)}).`);
  } else if (weightedDelta >= COMPARISON_MARGINALLY_BETTER_THRESHOLD) {
    overallOutcome = ComparisonOutcome.NEW_MARGINALLY_BETTER;
    reasoning.push(`New policy scores marginally better overall (weighted delta: +${round(weightedDelta, 3)}).`);
  } else if (weightedDelta > -COMPARISON_MARGINALLY_BETTER_THRESHOLD) {
    overallOutcome = ComparisonOutcome.EQUIVALENT;
    reasoning.push(`New policy is broadly equivalent to the existing policy (weighted delta: ${round(weightedDelta, 3)}).`);
  } else if (weightedDelta > -COMPARISON_MATERIALLY_BETTER_THRESHOLD) {
    overallOutcome = ComparisonOutcome.NEW_MARGINALLY_WORSE;
    reasoning.push(`New policy scores marginally worse overall (weighted delta: ${round(weightedDelta, 3)}).`);
  } else {
    overallOutcome = ComparisonOutcome.NEW_MATERIALLY_WORSE;
    reasoning.push(`New policy is materially worse than the existing policy (weighted delta: ${round(weightedDelta, 3)}). Replacement strongly discouraged.`);
  }

  // Grandfathered terms warning
  if (input.existingHasSuperiorGrandfatheredTerms) {
    replacementWarnings.push(
      'Existing policy contains superior grandfathered terms that cannot be replicated in the current market. Replacing this policy risks permanently losing those terms.',
    );
  }

  const sumInsuredDifferenceTPD =
    input.existingTPDSumInsured != null && input.newTPDSumInsured != null
      ? input.newTPDSumInsured - input.existingTPDSumInsured
      : null;

  return {
    hasComparisonCandidate: true,
    overallOutcome,
    dimensions,
    premiumDifferenceAnnual,
    sumInsuredDifferenceLife,
    sumInsuredDifferenceTPD,
    tpdDefinitionChange,
    exclusionChange,
    loadingChange,
    reasoning,
    replacementWarnings,
  };
}
