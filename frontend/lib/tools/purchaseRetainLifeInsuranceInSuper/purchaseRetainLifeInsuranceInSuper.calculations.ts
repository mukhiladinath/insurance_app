// =============================================================================
// CALCULATIONS — purchaseRetainLifeInsuranceInSuper
//
// All functions are pure — no side-effects, no rounding of intermediate values.
// Dollar figures are in AUD. Rates are decimals (e.g. 0.07 for 7%).
// =============================================================================

import {
  BeneficiaryCategory,
  RiskLevel,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  NormalizedInput,
  RetirementDragEstimate,
  CashflowMetrics,
  TaxFundingMetric,
  PlacementScores,
  CalculationsOutput,
  BeneficiaryTaxRiskAssessment,
} from './purchaseRetainLifeInsuranceInSuper.types';
import {
  futureValueAnnuity,
  clamp,
  round,
} from './purchaseRetainLifeInsuranceInSuper.utils';

// ---------------------------------------------------------------------------
// Default assumptions when caller has not supplied values
// ---------------------------------------------------------------------------
const DEFAULT_GROWTH_RATE = 0.07; // 7% p.a. — conservative long-run balanced fund assumption
const DEFAULT_YEARS_TO_RETIREMENT = 20;

// =============================================================================
// A — INACTIVITY MONTHS (utility, used here for informational calculations)
// =============================================================================

// (See rules.ts for the inactivity trigger evaluation. This file does not
//  re-derive the trigger — it only computes the metric for display.)

// =============================================================================
// B — RETIREMENT DRAG (opportunity cost of premiums inside super)
// =============================================================================

/**
 * Estimate the compound-growth opportunity cost of paying annual insurance
 * premiums from the super balance rather than leaving that capital invested.
 *
 * Uses future-value-of-annuity formula:
 *   FV = P × [((1 + r)^n − 1) / r]
 *
 * This represents the additional retirement balance the member WOULD have
 * accumulated had premiums not been deducted.
 *
 * IMPORTANT: this is not a recommendation to avoid insurance — the insured
 * benefit may far exceed this drag. It is a transparency metric only.
 */
export function estimateRetirementDrag(
  annualPremium: number,
  yearsToRetirement: number,
  assumedGrowthRate: number,
): RetirementDragEstimate {
  const drag = futureValueAnnuity(annualPremium, yearsToRetirement, assumedGrowthRate);

  return {
    annualPremium,
    yearsToRetirement,
    assumedGrowthRate,
    estimatedTotalDrag: round(drag, 2),
    explanation:
      `At an assumed growth rate of ${(assumedGrowthRate * 100).toFixed(1)}% p.a., ` +
      `paying $${annualPremium.toLocaleString()} p.a. in premiums for ${yearsToRetirement} year(s) ` +
      `represents an estimated retirement balance reduction of $${round(drag, 0).toLocaleString()}. ` +
      `This is the opportunity cost of the premium stream, not a net loss — ` +
      `the insurance coverage provided may substantially outweigh this figure.`,
  };
}

// =============================================================================
// C — CASHFLOW PRESSURE METRICS
// =============================================================================

/**
 * Compute cashflow stress indicators for the insurance premium relative to
 * the member's income and monthly surplus.
 *
 * Thresholds (indicative, not statutory):
 *   Premium as % of income:   > 3% = HIGH, 1–3% = MEDIUM, < 1% = LOW
 *   Premium as % of monthly surplus: > 20% = HIGH, 5–20% = MEDIUM, < 5% = LOW
 */
export function computeCashflowMetrics(input: NormalizedInput): CashflowMetrics {
  const premium = input.estimatedAnnualPremium;
  const income = input.annualIncome;
  const surplus = input.currentMonthlySurplusAfterExpenses;

  if (premium == null) {
    return {
      premiumAsPercentOfIncome: null,
      premiumAsPercentOfMonthlySurplus: null,
      postPremiumMonthlySurplus: null,
      cashflowStressIndicator: 'UNKNOWN',
    };
  }

  const premiumAsPercentOfIncome =
    income != null && income > 0 ? round((premium / income) * 100, 2) : null;

  const monthlyPremium = premium / 12;
  const premiumAsPercentOfMonthlySurplus =
    surplus != null && surplus > 0
      ? round((monthlyPremium / surplus) * 100, 2)
      : null;

  const postPremiumMonthlySurplus =
    surplus != null ? round(surplus - monthlyPremium, 2) : null;

  // Stress indicator — take the more conservative of the two metrics
  let stressIndicator: 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN' = 'UNKNOWN';

  if (premiumAsPercentOfIncome != null || premiumAsPercentOfMonthlySurplus != null) {
    const incomeStress =
      premiumAsPercentOfIncome != null
        ? premiumAsPercentOfIncome > 3
          ? 'HIGH'
          : premiumAsPercentOfIncome >= 1
            ? 'MEDIUM'
            : 'LOW'
        : 'UNKNOWN';

    const surplusStress =
      premiumAsPercentOfMonthlySurplus != null
        ? premiumAsPercentOfMonthlySurplus > 20
          ? 'HIGH'
          : premiumAsPercentOfMonthlySurplus >= 5
            ? 'MEDIUM'
            : 'LOW'
        : 'UNKNOWN';

    const ranking: Record<string, number> = { LOW: 0, MEDIUM: 1, HIGH: 2, UNKNOWN: -1 };
    if (ranking[incomeStress] >= ranking[surplusStress]) {
      stressIndicator = incomeStress as 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN';
    } else {
      stressIndicator = surplusStress as 'LOW' | 'MEDIUM' | 'HIGH' | 'UNKNOWN';
    }
  }

  return {
    premiumAsPercentOfIncome,
    premiumAsPercentOfMonthlySurplus,
    postPremiumMonthlySurplus,
    cashflowStressIndicator: stressIndicator,
  };
}

// =============================================================================
// D — TAX-FUNDING CONTEXTUAL METRIC
// =============================================================================

/**
 * Compute the relative tax-funding advantage of holding insurance inside super.
 *
 * CONTEXT:
 * When a member's super balance is funded by concessional (pre-tax) contributions
 * taxed at 15%, premiums deducted from that balance are effectively funded at the
 * 15% rate. Outside super, the member would need to earn income at their marginal
 * rate and then pay the premium from after-tax dollars.
 *
 * This function produces a contextual support score — NOT an absolute dollar
 * saving. The calculation illustrates relative advantage only.
 *
 * Formula:
 *   personalAfterTaxBurdenFactor = 1 / (1 − marginalRate)
 *   insideSuperFactor = 1 / (1 − 0.15)  [concessional rate]
 *   relativeScore = 1 − (insideSuperFactor / personalAfterTaxBurdenFactor)
 *   → 0 means no relative advantage; approaches 1 as marginal rate increases
 *
 * This score is capped at 0–1 and should be presented as a contextual indicator,
 * not a dollar saving guarantee.
 */
export function computeTaxFundingMetric(input: NormalizedInput): TaxFundingMetric {
  const marginalRate = input.marginalTaxRate;

  if (marginalRate == null) {
    return {
      marginalTaxRate: null,
      insideSuperRelativeFundingScore: null,
      personalAfterTaxBurdenFactor: null,
      explanation:
        'Marginal tax rate not provided — tax-funding advantage cannot be calculated.',
    };
  }

  const superTaxRate = 0.15; // concessional contributions tax rate
  const personalAfterTaxBurdenFactor = round(1 / (1 - marginalRate), 4);
  const insideSuperFactor = round(1 / (1 - superTaxRate), 4);
  const relativeScore = clamp(
    round(1 - insideSuperFactor / personalAfterTaxBurdenFactor, 4),
    0,
    1,
  );

  const advantageDescription =
    relativeScore >= 0.2
      ? 'meaningful'
      : relativeScore >= 0.05
        ? 'modest'
        : 'minimal';

  return {
    marginalTaxRate: marginalRate,
    insideSuperRelativeFundingScore: relativeScore,
    personalAfterTaxBurdenFactor,
    explanation:
      `At a marginal tax rate of ${(marginalRate * 100).toFixed(1)}%, the member faces a ` +
      `personal after-tax funding burden factor of ${personalAfterTaxBurdenFactor.toFixed(2)}x ` +
      `compared to ${insideSuperFactor.toFixed(2)}x inside super (at the 15% concessional rate). ` +
      `This represents a ${advantageDescription} relative funding advantage (score: ${(relativeScore * 100).toFixed(1)}/100) ` +
      `for funding premiums inside super rather than from personal after-tax income. ` +
      `This is a contextual indicator only — not a guaranteed dollar saving.`,
  };
}

// =============================================================================
// E — PLACEMENT SCORING INPUTS (0–100 per dimension)
// =============================================================================

/**
 * Produce numeric scores for each placement dimension.
 * Higher = stronger case FOR inside super (benefits) or stronger case AGAINST (penalties).
 * Each score is independently derived from input facts.
 */
export function computePlacementScores(input: NormalizedInput): PlacementScores {
  // --- BENEFITS ---

  // Cashflow benefit: inside-super premiums relieve personal after-tax cashflow pressure.
  let cashflowBenefit = 30; // baseline
  if (input.cashflowPressure === true) cashflowBenefit = 85;
  else if (input.wantsAffordability === true) cashflowBenefit = 70;
  else if (
    input.estimatedAnnualPremium != null &&
    input.annualIncome != null &&
    input.annualIncome > 0 &&
    (input.estimatedAnnualPremium / input.annualIncome) > 0.03
  ) {
    cashflowBenefit = 75;
  } else if (
    input.estimatedAnnualPremium != null &&
    input.currentMonthlySurplusAfterExpenses != null &&
    input.currentMonthlySurplusAfterExpenses > 0 &&
    (input.estimatedAnnualPremium / 12 / input.currentMonthlySurplusAfterExpenses) > 0.20
  ) {
    cashflowBenefit = 70;
  }

  // Tax-funding benefit: higher marginal rate = more advantage inside super.
  let taxFundingBenefit = 40; // baseline
  if (input.marginalTaxRate != null) {
    if (input.marginalTaxRate >= 0.45) taxFundingBenefit = 90;
    else if (input.marginalTaxRate >= 0.37) taxFundingBenefit = 80;
    else if (input.marginalTaxRate >= 0.325) taxFundingBenefit = 65;
    else if (input.marginalTaxRate >= 0.19) taxFundingBenefit = 45;
    else taxFundingBenefit = 25; // low or nil rate — less benefit
  }
  // If caps are already full, the concessional contribution channel is constrained.
  if (input.concessionalContributionsAlreadyHigh === true) {
    taxFundingBenefit = Math.max(20, taxFundingBenefit - 30);
  }

  // Convenience benefit: default coverage is easy to maintain.
  let convenienceBenefit = 40; // baseline
  if (input.wantsInsideSuper === true) convenienceBenefit = 75;
  if (input.trusteeAllowsOptInOnline) convenienceBenefit = Math.min(convenienceBenefit + 15, 80);

  // Structural protection benefit: super assets have some creditor-protection characteristics.
  let structuralProtectionBenefit = 20; // baseline — minor factor for most members
  if (input.hasDangerousOccupationElection) structuralProtectionBenefit = 55;

  // --- PENALTIES ---

  // Retirement erosion: premium drain reduces compound growth.
  let retirementErosionPenalty = 40; // baseline
  if (input.retirementPriorityHigh === true) retirementErosionPenalty = 85;
  if (input.yearsToRetirement != null) {
    if (input.yearsToRetirement <= 5) retirementErosionPenalty = Math.max(retirementErosionPenalty, 90);
    else if (input.yearsToRetirement <= 10) retirementErosionPenalty = Math.max(retirementErosionPenalty, 80);
    else if (input.yearsToRetirement <= 20) retirementErosionPenalty = Math.max(retirementErosionPenalty, 60);
  }
  if (input.superBalanceAdequacy === 'low') {
    retirementErosionPenalty = Math.max(retirementErosionPenalty, 70);
  }

  // Beneficiary tax risk: super death benefits may be taxable for non-dependants.
  let beneficiaryTaxRiskPenalty = 20; // baseline (low if dependants assumed)
  const bene = input.preferredBeneficiaryCategory ?? input.beneficiaryTypeExpected;
  if (bene === BeneficiaryCategory.NON_DEPENDANT_ADULT) beneficiaryTaxRiskPenalty = 90;
  else if (bene === BeneficiaryCategory.LEGAL_PERSONAL_REPRESENTATIVE) beneficiaryTaxRiskPenalty = 75;
  else if (bene === BeneficiaryCategory.FINANCIAL_DEPENDANT) beneficiaryTaxRiskPenalty = 35;
  else if (bene === BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD) beneficiaryTaxRiskPenalty = 15;
  if (input.wantsEstateControl === true) {
    beneficiaryTaxRiskPenalty = Math.max(beneficiaryTaxRiskPenalty, 65);
  }
  if (input.hasDependants === false) {
    // No dependants means likely a non-dependant beneficiary scenario
    beneficiaryTaxRiskPenalty = Math.max(beneficiaryTaxRiskPenalty, 55);
  }

  // Flexibility / control penalty: inside-super cover has trustee-controlled definitions.
  let flexibilityControlPenalty = 20; // baseline
  if (input.needForPolicyFlexibility === true) flexibilityControlPenalty = 75;
  if (input.needForOwnOccupationStyleDefinitions === true) flexibilityControlPenalty = 85;
  if (input.needForPolicyOwnershipOutsideTrusteeControl === true) flexibilityControlPenalty = 90;
  if (input.healthOrUnderwritingComplexity === true) {
    // Complex underwriting is often better managed outside super
    flexibilityControlPenalty = Math.max(flexibilityControlPenalty, 65);
  }

  // Contribution cap pressure penalty: using super for premiums competes with contributions.
  let contributionCapPressurePenalty = 20; // baseline
  if (input.contributionCapPressure === true) contributionCapPressurePenalty = 80;
  if (input.concessionalContributionsAlreadyHigh === true) {
    contributionCapPressurePenalty = Math.max(contributionCapPressurePenalty, 75);
  }

  return {
    cashflowBenefit: clamp(cashflowBenefit, 0, 100),
    taxFundingBenefit: clamp(taxFundingBenefit, 0, 100),
    convenienceBenefit: clamp(convenienceBenefit, 0, 100),
    structuralProtectionBenefit: clamp(structuralProtectionBenefit, 0, 100),
    retirementErosionPenalty: clamp(retirementErosionPenalty, 0, 100),
    beneficiaryTaxRiskPenalty: clamp(beneficiaryTaxRiskPenalty, 0, 100),
    flexibilityControlPenalty: clamp(flexibilityControlPenalty, 0, 100),
    contributionCapPressurePenalty: clamp(contributionCapPressurePenalty, 0, 100),
  };
}

// =============================================================================
// BENEFICIARY TAX RISK ASSESSMENT
// =============================================================================

/**
 * Assess the beneficiary tax risk associated with holding life cover inside super.
 *
 * The taxable component of a super death benefit (typically 100% of untaxed
 * element for life insurance proceeds) is taxed at:
 *   - 0% for tax-dependants (SIS s302AE / ITAA97 s302-195)
 *   - 15% + 2% Medicare levy for non-dependants on the taxable component
 *
 * For non-dependant adult beneficiaries, this is a material risk.
 */
export function assessBeneficiaryTaxRisk(input: NormalizedInput): BeneficiaryTaxRiskAssessment {
  const bene = input.preferredBeneficiaryCategory ?? input.beneficiaryTypeExpected;

  if (bene === BeneficiaryCategory.UNKNOWN || bene == null) {
    return {
      riskLevel: RiskLevel.MEDIUM,
      expectedBeneficiaryCategory: BeneficiaryCategory.UNKNOWN,
      estimatedTaxableComponent: 'UNKNOWN',
      explanation:
        'Beneficiary category is unknown. If the intended beneficiary is a non-dependant adult, the taxable component of the death benefit inside super will be subject to 17% tax (15% + 2% Medicare levy). This risk should be assessed once the beneficiary is identified.',
    };
  }

  if (bene === BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD) {
    return {
      riskLevel: RiskLevel.LOW,
      expectedBeneficiaryCategory: bene,
      estimatedTaxableComponent: 'LIKELY_LOW',
      explanation:
        'Dependant spouse or child beneficiary: death benefits paid to tax-dependants inside super are generally tax-free (ITAA97 s302-195). Beneficiary tax risk is low.',
    };
  }

  if (bene === BeneficiaryCategory.FINANCIAL_DEPENDANT) {
    return {
      riskLevel: RiskLevel.LOW,
      expectedBeneficiaryCategory: bene,
      estimatedTaxableComponent: 'LIKELY_LOW',
      explanation:
        'Financial dependant beneficiary: if the financial dependency can be established, the death benefit is tax-free. Low risk, but dependency must be demonstrable.',
    };
  }

  if (bene === BeneficiaryCategory.LEGAL_PERSONAL_REPRESENTATIVE) {
    return {
      riskLevel: RiskLevel.HIGH,
      expectedBeneficiaryCategory: bene,
      estimatedTaxableComponent: 'LIKELY_HIGH',
      explanation:
        'Legal personal representative (estate): the taxable component will be included in the deceased\'s estate. Whether tax applies depends on who ultimately receives the estate assets. If non-dependant adults inherit, the 17% tax rate will apply. This is a HIGH risk if estate beneficiaries include non-dependants.',
    };
  }

  // Non-dependant adult
  return {
    riskLevel: RiskLevel.CRITICAL,
    expectedBeneficiaryCategory: bene,
    estimatedTaxableComponent: 'LIKELY_HIGH',
    explanation:
      'Non-dependant adult beneficiary: the taxable component of the death benefit (typically the entire life insurance payout) will be taxed at 15% plus the 2% Medicare levy (total 17%) in the hands of the non-dependant. For a $1,000,000 sum insured, this represents a $170,000 tax cost. Holding this cover OUTSIDE super (where proceeds are paid directly and tax-free) is materially more beneficial for this beneficiary structure.',
  };
}

// =============================================================================
// AGGREGATE — produce all calculations in one call
// =============================================================================

export function runCalculations(input: NormalizedInput): CalculationsOutput {
  const premium = input.estimatedAnnualPremium;
  const years = input.yearsToRetirement ?? DEFAULT_YEARS_TO_RETIREMENT;
  const rate = input.assumedGrowthRate ?? DEFAULT_GROWTH_RATE;

  const retirementDrag =
    premium != null
      ? estimateRetirementDrag(premium, years, rate)
      : null;

  return {
    retirementDrag,
    cashflowMetrics: computeCashflowMetrics(input),
    taxFundingMetric: computeTaxFundingMetric(input),
    placementScores: computePlacementScores(input),
  };
}
