// =============================================================================
// UNDERWRITING — purchaseRetainLifeTPDPolicy
//
// Two modules:
//   1. Underwriting risk assessment — risk that new cover will be loaded/excluded/declined
//   2. Replacement risk assessment  — risk of losing valuable existing cover
// =============================================================================

import {
  UnderwritingRisk,
  ReplacementRisk,
  HealthRiskFactor,
  ComparisonOutcome,
  OccupationClass,
} from './purchaseRetainLifeTPDPolicy.enums';
import type {
  NormalizedInput,
  UnderwritingRiskResult,
  UnderwritingRiskFactor,
  ReplacementRiskResult,
  ReplacementRiskFactor,
  PolicyComparisonResult,
} from './purchaseRetainLifeTPDPolicy.types';
import { OCCUPATION_RISK_MAP, BMI_THRESHOLDS } from './purchaseRetainLifeTPDPolicy.constants';
import { computeBMI } from './purchaseRetainLifeTPDPolicy.utils';

// =============================================================================
// RISK LEVEL ORDERING
// =============================================================================

const RISK_LEVEL_ORDER: Record<UnderwritingRisk, number> = {
  [UnderwritingRisk.LOW]: 0,
  [UnderwritingRisk.MEDIUM]: 1,
  [UnderwritingRisk.HIGH]: 2,
  [UnderwritingRisk.CRITICAL]: 3,
};

function maxRisk(a: UnderwritingRisk, b: UnderwritingRisk): UnderwritingRisk {
  return RISK_LEVEL_ORDER[a] >= RISK_LEVEL_ORDER[b] ? a : b;
}

const REPLACEMENT_RISK_ORDER: Record<ReplacementRisk, number> = {
  [ReplacementRisk.NEGLIGIBLE]: 0,
  [ReplacementRisk.LOW]: 1,
  [ReplacementRisk.MODERATE]: 2,
  [ReplacementRisk.HIGH]: 3,
  [ReplacementRisk.BLOCKING]: 4,
};

function maxReplacementRisk(a: ReplacementRisk, b: ReplacementRisk): ReplacementRisk {
  return REPLACEMENT_RISK_ORDER[a] >= REPLACEMENT_RISK_ORDER[b] ? a : b;
}

// =============================================================================
// BMI CLASSIFICATION
// =============================================================================

function classifyBMI(
  bmi: number,
): UnderwritingRiskResult['bmiCategory'] {
  if (bmi < BMI_THRESHOLDS.UNDERWEIGHT_MAX) return 'UNDERWEIGHT';
  if (bmi < BMI_THRESHOLDS.NORMAL_MAX) return 'NORMAL';
  if (bmi < BMI_THRESHOLDS.OVERWEIGHT_MAX) return 'OVERWEIGHT';
  if (bmi < BMI_THRESHOLDS.OBESE_MAX) return 'OBESE';
  return 'SEVERELY_OBESE';
}

// =============================================================================
// A — UNDERWRITING RISK ASSESSMENT
// =============================================================================

export function assessUnderwritingRisk(input: NormalizedInput): UnderwritingRiskResult {
  const factors: UnderwritingRiskFactor[] = [];
  let overallRisk: UnderwritingRisk = UnderwritingRisk.LOW;
  const recommendations: string[] = [];

  // -------------------------------------------------------------------------
  // BMI
  // -------------------------------------------------------------------------
  let bmi: number | null = null;
  let bmiCategory: UnderwritingRiskResult['bmiCategory'] = 'UNKNOWN';

  if (input.heightCm != null && input.weightKg != null) {
    bmi = computeBMI(input.heightCm, input.weightKg);
    bmiCategory = classifyBMI(bmi);

    if (bmiCategory === 'OBESE') {
      factors.push({
        factor: HealthRiskFactor.BMI_HIGH,
        riskContribution: UnderwritingRisk.MEDIUM,
        detail: `BMI ${bmi} — obese range. Likely premium loading.`,
      });
      overallRisk = maxRisk(overallRisk, UnderwritingRisk.MEDIUM);
    } else if (bmiCategory === 'SEVERELY_OBESE') {
      factors.push({
        factor: HealthRiskFactor.BMI_VERY_HIGH,
        riskContribution: UnderwritingRisk.HIGH,
        detail: `BMI ${bmi} — severely obese range. Likely significant loading or partial decline.`,
      });
      overallRisk = maxRisk(overallRisk, UnderwritingRisk.HIGH);
      recommendations.push('Obtain specialist medical report or specialist loading estimate before applying for new cover.');
    }
  }

  // -------------------------------------------------------------------------
  // Existing medical conditions
  // -------------------------------------------------------------------------
  if (input.existingMedicalConditions.length > 0) {
    const highRiskKeywords = [
      'cancer', 'cardiac', 'heart', 'stroke', 'diabetes', 'hiv', 'hepatitis',
      'kidney', 'liver', 'lung', 'copd', 'depression', 'anxiety', 'bipolar',
    ];
    const conditionsLower = input.existingMedicalConditions.map((c) => c.toLowerCase());
    const hasHighRiskCondition = conditionsLower.some((c) =>
      highRiskKeywords.some((kw) => c.includes(kw)),
    );

    const conditionRisk = hasHighRiskCondition
      ? UnderwritingRisk.HIGH
      : UnderwritingRisk.MEDIUM;

    factors.push({
      factor: HealthRiskFactor.EXISTING_CONDITION,
      riskContribution: conditionRisk,
      detail: `${input.existingMedicalConditions.length} existing medical condition(s) disclosed: ${input.existingMedicalConditions.slice(0, 3).join(', ')}${input.existingMedicalConditions.length > 3 ? ' ...' : ''}.`,
    });
    overallRisk = maxRisk(overallRisk, conditionRisk);
  }

  // -------------------------------------------------------------------------
  // Pending investigations
  // -------------------------------------------------------------------------
  if (input.pendingInvestigations) {
    factors.push({
      factor: HealthRiskFactor.PENDING_INVESTIGATION,
      riskContribution: UnderwritingRisk.HIGH,
      detail: `Pending medical investigations: ${input.pendingInvestigationDetails ?? 'details not provided'}. Underwriting outcome is uncertain until investigations complete.`,
    });
    overallRisk = maxRisk(overallRisk, UnderwritingRisk.HIGH);
    recommendations.push('Do not proceed with replacement until pending investigations are complete and results are known.');
  }

  // -------------------------------------------------------------------------
  // Family history
  // -------------------------------------------------------------------------
  if (input.familyHistoryConditions.length > 0) {
    factors.push({
      factor: HealthRiskFactor.ADVERSE_FAMILY_HISTORY,
      riskContribution: UnderwritingRisk.MEDIUM,
      detail: `Family history of: ${input.familyHistoryConditions.join(', ')}.`,
    });
    overallRisk = maxRisk(overallRisk, UnderwritingRisk.MEDIUM);
  }

  // -------------------------------------------------------------------------
  // Smoker status
  // -------------------------------------------------------------------------
  if (input.smoker) {
    factors.push({
      factor: HealthRiskFactor.SMOKER,
      riskContribution: UnderwritingRisk.MEDIUM,
      detail: 'Smoker rates apply — significantly higher premiums. Non-smoker rates are not available.',
    });
    overallRisk = maxRisk(overallRisk, UnderwritingRisk.MEDIUM);
  }

  // -------------------------------------------------------------------------
  // Hazardous activities
  // -------------------------------------------------------------------------
  if (input.hazardousActivities.length > 0) {
    factors.push({
      factor: HealthRiskFactor.HAZARDOUS_ACTIVITY,
      riskContribution: UnderwritingRisk.MEDIUM,
      detail: `Hazardous activities disclosed: ${input.hazardousActivities.join(', ')}. Exclusions or loadings likely.`,
    });
    overallRisk = maxRisk(overallRisk, UnderwritingRisk.MEDIUM);
  }

  // -------------------------------------------------------------------------
  // Occupation class
  // -------------------------------------------------------------------------
  const occupationRisk = OCCUPATION_RISK_MAP[input.occupationClass ?? OccupationClass.UNKNOWN];
  if (occupationRisk === 'HIGH' || occupationRisk === 'CRITICAL') {
    factors.push({
      factor: HealthRiskFactor.HAZARDOUS_OCCUPATION,
      riskContribution: occupationRisk as UnderwritingRisk,
      detail: `Occupation class ${input.occupationClass}: ${occupationRisk} underwriting risk. Own-occupation TPD may not be available.`,
    });
    overallRisk = maxRisk(overallRisk, occupationRisk as UnderwritingRisk);
  }

  // -------------------------------------------------------------------------
  // Non-disclosure risk
  // -------------------------------------------------------------------------
  if (input.nonDisclosureRisk) {
    factors.push({
      factor: HealthRiskFactor.NON_DISCLOSURE_RISK,
      riskContribution: UnderwritingRisk.CRITICAL,
      detail: 'Non-disclosure risk flagged. Any new policy application or existing policy claim may be voided. This case must be reviewed by an experienced adviser before any action is taken.',
    });
    overallRisk = UnderwritingRisk.CRITICAL;
    recommendations.push('CRITICAL: Non-disclosure risk must be resolved with the existing insurer before any replacement is contemplated.');
  }

  // -------------------------------------------------------------------------
  // Likely underwriting outcome
  // -------------------------------------------------------------------------
  let likelyOutcome: UnderwritingRiskResult['likelyOutcome'];
  const hasLoadingRisk =
    factors.some((f) =>
      [HealthRiskFactor.BMI_HIGH, HealthRiskFactor.BMI_VERY_HIGH, HealthRiskFactor.SMOKER].includes(f.factor),
    );
  const hasExclusionRisk = factors.some((f) =>
    [HealthRiskFactor.EXISTING_CONDITION, HealthRiskFactor.HAZARDOUS_ACTIVITY, HealthRiskFactor.HAZARDOUS_OCCUPATION].includes(f.factor),
  );

  if (overallRisk === UnderwritingRisk.CRITICAL) {
    likelyOutcome = 'DECLINE_POSSIBLE';
  } else if (hasLoadingRisk && hasExclusionRisk) {
    likelyOutcome = 'LOADED_AND_EXCLUSION';
  } else if (hasLoadingRisk) {
    likelyOutcome = 'LOADED_PREMIUM';
  } else if (hasExclusionRisk) {
    likelyOutcome = 'EXCLUSION_APPLIED';
  } else if (overallRisk === UnderwritingRisk.LOW) {
    likelyOutcome = 'STANDARD';
  } else {
    likelyOutcome = 'UNKNOWN';
  }

  return {
    overallRisk,
    factors,
    bmi,
    bmiCategory,
    likelyOutcome,
    recommendations,
  };
}

// =============================================================================
// B — REPLACEMENT RISK ASSESSMENT
// =============================================================================

export function assessReplacementRisk(
  input: NormalizedInput,
  underwritingRisk: UnderwritingRiskResult,
  comparison: PolicyComparisonResult | null,
): ReplacementRiskResult {
  if (!input.hasExistingPolicy) {
    return {
      overallRisk: ReplacementRisk.NEGLIGIBLE,
      factors: [],
      existingCoverAtRisk: false,
      coverageGapPossible: false,
      warnings: [],
      requiredActions: [],
    };
  }

  const factors: ReplacementRiskFactor[] = [];
  const warnings: string[] = [];
  const requiredActions: string[] = [];
  let overallRisk: ReplacementRisk = ReplacementRisk.NEGLIGIBLE;

  // -------------------------------------------------------------------------
  // Health deterioration since existing policy commencement
  // -------------------------------------------------------------------------
  const healthHasWorsened =
    input.existingMedicalConditions.length > 0 ||
    input.pendingInvestigations ||
    (underwritingRisk.overallRisk === UnderwritingRisk.HIGH ||
      underwritingRisk.overallRisk === UnderwritingRisk.CRITICAL);

  if (healthHasWorsened) {
    const riskLevel =
      underwritingRisk.overallRisk === UnderwritingRisk.CRITICAL
        ? ReplacementRisk.BLOCKING
        : ReplacementRisk.HIGH;
    factors.push({
      factor: 'Health Deterioration',
      riskLevel,
      description:
        'The client\'s health has deteriorated since the existing policy commenced. ' +
        'Replacing the policy risks new exclusions, loadings, or decline — permanently losing the existing clean-rate cover.',
    });
    overallRisk = maxReplacementRisk(overallRisk, riskLevel);

    if (riskLevel === ReplacementRisk.BLOCKING) {
      warnings.push('BLOCKING: Health deterioration to CRITICAL level — replacement must not proceed until new underwriting is fully accepted on standard terms or better.');
    } else {
      warnings.push('HIGH RISK: Health deterioration since existing policy commencement. New policy may come with loadings or exclusions that do not apply to existing cover.');
    }
    requiredActions.push('Obtain full underwriting acceptance on the new policy BEFORE cancelling the existing policy.');
  }

  // -------------------------------------------------------------------------
  // Non-disclosure risk
  // -------------------------------------------------------------------------
  if (input.nonDisclosureRisk) {
    factors.push({
      factor: 'Non-Disclosure Risk',
      riskLevel: ReplacementRisk.BLOCKING,
      description: 'Non-disclosure risk flagged. Both existing and new cover may be at risk. Replacement cannot proceed.',
    });
    overallRisk = ReplacementRisk.BLOCKING;
    warnings.push('BLOCKING: Non-disclosure risk — both existing and new policy are at risk. Do not replace. Refer to specialist adviser.');
  }

  // -------------------------------------------------------------------------
  // Superior grandfathered terms on existing policy
  // -------------------------------------------------------------------------
  if (input.existingHasSuperiorGrandfatheredTerms) {
    factors.push({
      factor: 'Superior Grandfathered Terms',
      riskLevel: ReplacementRisk.HIGH,
      description: 'Existing policy contains grandfathered terms (e.g. own-occupation TPD, legacy definitions) not available in the current market. Replacing will permanently lose these terms.',
    });
    overallRisk = maxReplacementRisk(overallRisk, ReplacementRisk.HIGH);
    warnings.push('Existing policy has superior grandfathered terms. Carefully evaluate whether any benefit from replacing outweighs the permanent loss of these terms.');
  }

  // -------------------------------------------------------------------------
  // TPD definition worsening
  // -------------------------------------------------------------------------
  if (comparison?.tpdDefinitionChange === 'WORSENED') {
    factors.push({
      factor: 'TPD Definition Deterioration',
      riskLevel: ReplacementRisk.HIGH,
      description: 'The new policy\'s TPD definition is less favourable than the existing policy. This is a material disadvantage for a TPD claim.',
    });
    overallRisk = maxReplacementRisk(overallRisk, ReplacementRisk.HIGH);
    warnings.push('TPD definition worsens with replacement — this significantly disadvantages the client on TPD claims.');
    requiredActions.push('Do not replace if the only reason is convenience or minor premium saving — the TPD definition worsening overrides minor cost advantages.');
  }

  // -------------------------------------------------------------------------
  // Coverage gap during transition
  // -------------------------------------------------------------------------
  const coverageGapPossible = input.hasExistingPolicy && input.hasNewPolicyCandidate;
  if (coverageGapPossible) {
    factors.push({
      factor: 'Coverage Gap During Transition',
      riskLevel: ReplacementRisk.MODERATE,
      description: 'There is a risk of a coverage gap between the cancellation of the existing policy and the commencement of the new policy, particularly if new underwriting is not yet complete.',
    });
    overallRisk = maxReplacementRisk(overallRisk, ReplacementRisk.MODERATE);
    requiredActions.push('Ensure new policy is fully accepted and in force before cancelling the existing policy.');
  }

  // -------------------------------------------------------------------------
  // Underwriting not complete
  // -------------------------------------------------------------------------
  if (
    input.newUnderwritingStatus === 'NOT_STARTED' ||
    input.newUnderwritingStatus === 'IN_PROGRESS'
  ) {
    factors.push({
      factor: 'Underwriting Incomplete',
      riskLevel: ReplacementRisk.BLOCKING,
      description: 'New policy underwriting has not been completed. Replacement cannot be recommended until the underwriting outcome is known.',
    });
    overallRisk = ReplacementRisk.BLOCKING;
    warnings.push('BLOCKING: New policy underwriting is not complete. Do not cancel existing cover until new cover is fully accepted.');
  }

  return {
    overallRisk,
    factors,
    existingCoverAtRisk: healthHasWorsened || input.nonDisclosureRisk,
    coverageGapPossible,
    warnings,
    requiredActions,
  };
}
