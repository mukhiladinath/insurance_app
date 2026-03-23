// =============================================================================
// PLACEMENT ENGINE — purchaseRetainLifeInsuranceInSuper
//
// Deterministic placement recommendation: INSIDE_SUPER / OUTSIDE_SUPER /
// SPLIT_STRATEGY / INSUFFICIENT_INFO.
//
// The engine:
//   1. Refuses to recommend INSIDE_SUPER if legal status prohibits it.
//   2. Returns INSUFFICIENT_INFO if strategic facts are too sparse.
//   3. Computes a net weighted score and compares inside vs outside.
//   4. Recommends SPLIT_STRATEGY when the net scores are close.
// =============================================================================

import {
  PlacementRecommendation,
  LegalStatus,
  MissingInfoCategory,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  NormalizedInput,
  LegalResult,
  PlacementScores,
  PlacementResult,
  MissingInfoQuestion,
} from './purchaseRetainLifeInsuranceInSuper.types';
import {
  PLACEMENT_WEIGHTS,
  PLACEMENT_INSIDE_THRESHOLD,
  PLACEMENT_OUTSIDE_THRESHOLD,
  RULE_IDS,
} from './purchaseRetainLifeInsuranceInSuper.constants';
import { clamp, round } from './purchaseRetainLifeInsuranceInSuper.utils';

// ---------------------------------------------------------------------------
// Strategic fact completeness check
// ---------------------------------------------------------------------------

/**
 * Determine whether sufficient strategic facts are present for a placement
 * recommendation. Returns missing questions if not.
 */
function checkStrategicFactsCompleteness(input: NormalizedInput): {
  sufficient: boolean;
  missingQuestions: MissingInfoQuestion[];
} {
  const missing: MissingInfoQuestion[] = [];

  if (input.estimatedAnnualPremium == null) {
    missing.push({
      id: 'Q-PREMIUM',
      question: 'What is the estimated annual insurance premium?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    });
  }

  if (input.yearsToRetirement == null) {
    missing.push({
      id: 'Q-RETIRE',
      question: 'How many years until the member plans to retire?',
      category: MissingInfoCategory.STRATEGIC,
      blocking: false,
    });
  }

  if (
    input.beneficiaryTypeExpected == null &&
    input.preferredBeneficiaryCategory == null
  ) {
    missing.push({
      id: 'Q-BENEFICIARY',
      question:
        'Who is the intended primary beneficiary (dependant spouse/child, non-dependant adult, or estate)?',
      category: MissingInfoCategory.BENEFICIARY_ESTATE,
      blocking: false,
    });
  }

  if (
    input.cashflowPressure == null &&
    input.annualIncome == null &&
    input.currentMonthlySurplusAfterExpenses == null
  ) {
    missing.push({
      id: 'Q-CASHFLOW-PLACEMENT',
      question: 'Is the member under cashflow pressure? What is their approximate monthly surplus?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    });
  }

  if (input.retirementPriorityHigh == null && input.superBalanceAdequacy == null) {
    missing.push({
      id: 'Q-RETIRE-PRIORITY',
      question:
        'Is maximising the retirement balance a high priority for this member? Is their current super balance adequate?',
      category: MissingInfoCategory.STRATEGIC,
      blocking: false,
    });
  }

  // We can still produce a recommendation if at least 3 of the 5 strategic
  // fact groups are present. If fewer are present, return INSUFFICIENT_INFO.
  const groupsPresent = [
    input.estimatedAnnualPremium != null,
    input.yearsToRetirement != null,
    input.beneficiaryTypeExpected != null || input.preferredBeneficiaryCategory != null,
    input.cashflowPressure != null || input.annualIncome != null || input.currentMonthlySurplusAfterExpenses != null,
    input.retirementPriorityHigh != null || input.superBalanceAdequacy != null,
  ].filter(Boolean).length;

  return {
    sufficient: groupsPresent >= 3,
    missingQuestions: missing,
  };
}

// ---------------------------------------------------------------------------
// Score computation
// ---------------------------------------------------------------------------

/**
 * Compute normalised inside-super and outside-super scores (both 0–100).
 *
 * Approach:
 *   netRaw = (weighted benefit scores) − (weighted penalty scores)
 *   Both halves are weighted from the PLACEMENT_WEIGHTS constants.
 *   The raw net ranges from approximately −40 to +60.
 *   Normalise: insideSuperScore = clamp(netRaw + 40, 0, 100)
 *   outsideSuperScore = 100 − insideSuperScore
 *
 * The benefit weight total = 0.25+0.20+0.10+0.05 = 0.60 → max +60
 * The penalty weight total = 0.20+0.10+0.05+0.05 = 0.40 → max −40
 * Net range: −40 to +60 (100-point spread)
 * Normalised by adding 40: 0 to 100.
 */
function computeNormalisedScores(scores: PlacementScores): {
  insideSuperScore: number;
  outsideSuperScore: number;
} {
  const w = PLACEMENT_WEIGHTS;

  const benefitRaw =
    scores.cashflowBenefit * w.cashflowBenefit +
    scores.taxFundingBenefit * w.taxFundingBenefit +
    scores.convenienceBenefit * w.convenienceBenefit +
    scores.structuralProtectionBenefit * w.structuralProtectionBenefit;

  const penaltyRaw =
    scores.retirementErosionPenalty * w.retirementErosionPenalty +
    scores.beneficiaryTaxRiskPenalty * w.beneficiaryTaxRiskPenalty +
    scores.flexibilityControlPenalty * w.flexibilityControlPenalty +
    scores.contributionCapPressurePenalty * w.contributionCapPressurePenalty;

  const netRaw = benefitRaw - penaltyRaw;
  const insideSuperScore = clamp(round(netRaw + 40, 1), 0, 100);
  const outsideSuperScore = clamp(round(100 - insideSuperScore, 1), 0, 100);

  return { insideSuperScore, outsideSuperScore };
}

// ---------------------------------------------------------------------------
// Reasoning narrative generation
// ---------------------------------------------------------------------------

function buildReasoning(
  scores: PlacementScores,
  recommendation: PlacementRecommendation,
  insideSuperScore: number,
  outsideSuperScore: number,
): string[] {
  const lines: string[] = [];
  const w = PLACEMENT_WEIGHTS;

  lines.push(
    `Placement recommendation: ${recommendation}. ` +
    `Inside-super score: ${insideSuperScore}/100. Outside-super score: ${outsideSuperScore}/100.`,
  );

  // Benefits commentary
  if (scores.cashflowBenefit >= 65) {
    lines.push(
      `Strong cashflow benefit (${scores.cashflowBenefit}/100, weight ${(w.cashflowBenefit * 100).toFixed(0)}%): ` +
      `funding premiums from super relieves personal after-tax cashflow pressure.`,
    );
  }
  if (scores.taxFundingBenefit >= 65) {
    lines.push(
      `Material tax-funding advantage (${scores.taxFundingBenefit}/100, weight ${(w.taxFundingBenefit * 100).toFixed(0)}%): ` +
      `member's marginal tax rate creates a meaningful gap between inside-super (15% contributions tax) and outside-super (personal rate) funding cost.`,
    );
  }

  // Penalties commentary
  if (scores.retirementErosionPenalty >= 65) {
    lines.push(
      `Significant retirement erosion risk (${scores.retirementErosionPenalty}/100, weight ${(w.retirementErosionPenalty * 100).toFixed(0)}%): ` +
      `premiums will meaningfully erode the retirement balance over the remaining accumulation period.`,
    );
  }
  if (scores.beneficiaryTaxRiskPenalty >= 65) {
    lines.push(
      `High beneficiary tax risk (${scores.beneficiaryTaxRiskPenalty}/100, weight ${(w.beneficiaryTaxRiskPenalty * 100).toFixed(0)}%): ` +
      `the intended beneficiary structure means the death benefit taxable component may attract up to 17% tax inside super. Outside-super ownership avoids this.`,
    );
  }
  if (scores.flexibilityControlPenalty >= 65) {
    lines.push(
      `Flexibility and control concerns (${scores.flexibilityControlPenalty}/100, weight ${(w.flexibilityControlPenalty * 100).toFixed(0)}%): ` +
      `member requires policy flexibility, own-occupation definitions, or direct ownership that inside-super structures cannot provide.`,
    );
  }
  if (scores.contributionCapPressurePenalty >= 65) {
    lines.push(
      `Contribution cap pressure (${scores.contributionCapPressurePenalty}/100, weight ${(w.contributionCapPressurePenalty * 100).toFixed(0)}%): ` +
      `existing concessional contribution usage limits the room available to fund premiums inside super.`,
    );
  }

  if (recommendation === PlacementRecommendation.SPLIT_STRATEGY) {
    lines.push(
      'A split strategy is recommended: retain base death cover inside super for cashflow and convenience benefits, ' +
      'while obtaining additional or alternative cover outside super for estate planning, flexibility, or underwriting reasons.',
    );
  }

  return lines;
}

function buildRisks(
  scores: PlacementScores,
  recommendation: PlacementRecommendation,
): string[] {
  const risks: string[] = [];

  if (
    (recommendation === PlacementRecommendation.INSIDE_SUPER ||
      recommendation === PlacementRecommendation.SPLIT_STRATEGY) &&
    scores.beneficiaryTaxRiskPenalty >= 55
  ) {
    risks.push(
      'INSIDE SUPER — BENEFICIARY TAX RISK: Non-dependant beneficiaries will pay 17% tax on the taxable component of the super death benefit. Review beneficiary nomination.',
    );
  }

  if (
    (recommendation === PlacementRecommendation.INSIDE_SUPER ||
      recommendation === PlacementRecommendation.SPLIT_STRATEGY) &&
    scores.retirementErosionPenalty >= 55
  ) {
    risks.push(
      'INSIDE SUPER — RETIREMENT DRAG: Ongoing premiums reduce the compounding super balance. Consider whether the sum insured is appropriately sized.',
    );
  }

  if (
    recommendation === PlacementRecommendation.OUTSIDE_SUPER &&
    scores.cashflowBenefit >= 55
  ) {
    risks.push(
      'OUTSIDE SUPER — CASHFLOW RISK: Premiums must be funded from after-tax income. Ensure budget sustainability before committing to outside-super cover.',
    );
  }

  if (
    recommendation === PlacementRecommendation.OUTSIDE_SUPER &&
    scores.taxFundingBenefit >= 55
  ) {
    risks.push(
      'OUTSIDE SUPER — TAX COST: Premiums paid from personal after-tax income are more expensive per unit of cover relative to inside-super funding at the 15% contributions tax rate.',
    );
  }

  return risks;
}

// =============================================================================
// MAIN PLACEMENT ENGINE
// =============================================================================

export function evaluatePlacementInsideVsOutsideSuper(
  input: NormalizedInput,
  legalResult: LegalResult,
  placementScores: PlacementScores,
): PlacementResult {
  // -------------------------------------------------------------------------
  // Hard block: if legal status does not allow inside super, do not recommend it
  // -------------------------------------------------------------------------
  const insideSuperLegallyBlocked =
    legalResult.status === LegalStatus.NOT_ALLOWED_IN_SUPER ||
    legalResult.status === LegalStatus.MUST_BE_SWITCHED_OFF;

  if (insideSuperLegallyBlocked) {
    const scores = computeNormalisedScores(placementScores);
    return {
      recommendation: PlacementRecommendation.OUTSIDE_SUPER,
      insideSuperScore: 0,
      outsideSuperScore: 100,
      benefitBreakdown: {
        cashflowBenefit: placementScores.cashflowBenefit,
        taxFundingBenefit: placementScores.taxFundingBenefit,
        convenienceBenefit: placementScores.convenienceBenefit,
        structuralProtectionBenefit: placementScores.structuralProtectionBenefit,
      },
      penaltyBreakdown: {
        retirementErosionPenalty: placementScores.retirementErosionPenalty,
        beneficiaryTaxRiskPenalty: placementScores.beneficiaryTaxRiskPenalty,
        flexibilityControlPenalty: placementScores.flexibilityControlPenalty,
        contributionCapPressurePenalty: placementScores.contributionCapPressurePenalty,
      },
      reasoning: [
        `Legal status is ${legalResult.status} — inside-super placement is not legally available. ` +
        `OUTSIDE_SUPER is the only viable option.`,
      ],
      risks: buildRisks(placementScores, PlacementRecommendation.OUTSIDE_SUPER),
    };
  }

  // -------------------------------------------------------------------------
  // Strategic sufficiency check
  // -------------------------------------------------------------------------
  const { sufficient, missingQuestions } = checkStrategicFactsCompleteness(input);

  if (!sufficient) {
    return {
      recommendation: PlacementRecommendation.INSUFFICIENT_INFO,
      insideSuperScore: 0,
      outsideSuperScore: 0,
      benefitBreakdown: {},
      penaltyBreakdown: {},
      reasoning: [
        'Insufficient strategic facts to produce a reliable placement recommendation. Please provide the missing information.',
        ...missingQuestions.map((q) => `Missing: ${q.question}`),
      ],
      risks: [],
    };
  }

  // -------------------------------------------------------------------------
  // Score and recommend
  // -------------------------------------------------------------------------
  const { insideSuperScore, outsideSuperScore } = computeNormalisedScores(placementScores);

  let recommendation: PlacementRecommendation;

  if (
    insideSuperScore >= PLACEMENT_INSIDE_THRESHOLD &&
    insideSuperScore > outsideSuperScore + 10
  ) {
    recommendation = PlacementRecommendation.INSIDE_SUPER;
  } else if (
    outsideSuperScore >= PLACEMENT_OUTSIDE_THRESHOLD &&
    outsideSuperScore > insideSuperScore + 10
  ) {
    recommendation = PlacementRecommendation.OUTSIDE_SUPER;
  } else {
    recommendation = PlacementRecommendation.SPLIT_STRATEGY;
  }

  const reasoning = buildReasoning(
    placementScores,
    recommendation,
    insideSuperScore,
    outsideSuperScore,
  );
  const risks = buildRisks(placementScores, recommendation);

  return {
    recommendation,
    insideSuperScore,
    outsideSuperScore,
    benefitBreakdown: {
      cashflowBenefit: placementScores.cashflowBenefit,
      taxFundingBenefit: placementScores.taxFundingBenefit,
      convenienceBenefit: placementScores.convenienceBenefit,
      structuralProtectionBenefit: placementScores.structuralProtectionBenefit,
    },
    penaltyBreakdown: {
      retirementErosionPenalty: placementScores.retirementErosionPenalty,
      beneficiaryTaxRiskPenalty: placementScores.beneficiaryTaxRiskPenalty,
      flexibilityControlPenalty: placementScores.flexibilityControlPenalty,
      contributionCapPressurePenalty: placementScores.contributionCapPressurePenalty,
    },
    reasoning,
    risks,
  };
}
