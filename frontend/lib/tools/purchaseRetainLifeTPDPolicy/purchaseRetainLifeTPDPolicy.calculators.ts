// =============================================================================
// CALCULATORS — purchaseRetainLifeTPDPolicy
//
// Modular need-analysis and affordability functions.
// All pure functions — no side effects.
// =============================================================================

import { ShortfallLevel } from './purchaseRetainLifeTPDPolicy.enums';
import type {
  NormalizedInput,
  LifeNeedResult,
  TPDNeedResult,
  AffordabilityResult,
} from './purchaseRetainLifeTPDPolicy.types';
import {
  DEFAULT_FINAL_EXPENSES_AUD,
  DEFAULT_EDUCATION_FUNDING_PER_CHILD_AUD,
  DEFAULT_INCOME_REPLACEMENT_YEARS,
  DEFAULT_MEDICAL_REHAB_BUFFER_AUD,
  DEFAULT_HOME_MODIFICATION_BUFFER_AUD,
  DEFAULT_ONGOING_CARE_BUFFER_AUD,
  TPD_CAPITALISATION_RATE,
  DEFAULT_INCOME_REPLACEMENT_PERCENT,
  SHORTFALL_THRESHOLDS,
  AFFORDABILITY_INCOME_BANDS,
  AFFORDABILITY_NET_INCOME_BANDS,
  STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR,
} from './purchaseRetainLifeTPDPolicy.constants';
import {
  presentValueAnnuity,
  projectSteppedPremium,
  clamp,
  round,
} from './purchaseRetainLifeTPDPolicy.utils';
import { PremiumStructure } from './purchaseRetainLifeTPDPolicy.enums';

// =============================================================================
// SHORTFALL LEVEL CLASSIFICATION
// =============================================================================

function classifyShortfall(net: number): ShortfallLevel {
  if (net <= SHORTFALL_THRESHOLDS.NONE) return ShortfallLevel.NONE;
  if (net <= SHORTFALL_THRESHOLDS.MINOR) return ShortfallLevel.MINOR;
  if (net <= SHORTFALL_THRESHOLDS.MODERATE) return ShortfallLevel.MODERATE;
  if (net <= SHORTFALL_THRESHOLDS.SIGNIFICANT) return ShortfallLevel.SIGNIFICANT;
  return ShortfallLevel.CRITICAL;
}

// =============================================================================
// A — LIFE INSURANCE NEED ANALYSIS
//
// Formula:
//   Gross need = debt clearance + education funding + income replacement + final expenses
//   Net need   = gross need − existing cover − liquid assets
// =============================================================================

export function calculateLifeNeed(input: NormalizedInput): LifeNeedResult {
  const assumptions: string[] = [];

  // 1. Debt clearance: mortgage + other debts
  const debtClearanceNeed = (input.mortgageBalance ?? 0) + (input.otherDebts ?? 0);
  if (input.mortgageBalance == null) {
    assumptions.push('Mortgage balance not provided — assumed $0.');
  }

  // 2. Education funding: per dependent child × default
  const numDependants = input.numberOfDependants ?? 0;
  const childrenEstimate = input.youngestDependantAge != null
    ? Math.max(0, numDependants)
    : numDependants;
  const educationFundingNeed = childrenEstimate * DEFAULT_EDUCATION_FUNDING_PER_CHILD_AUD;
  if (input.numberOfDependants == null) {
    assumptions.push('Number of dependants not provided — assumed 0 for education funding.');
  }

  // 3. Income replacement
  //    Uses annual gross income × replacement years (years to retirement or default)
  //    Reduced by assumed partner income contribution (50% if partner exists)
  const incomeToReplace =
    (input.annualGrossIncome ?? 0) * DEFAULT_INCOME_REPLACEMENT_PERCENT;
  const yearsToReplace = input.yearsToRetirement ?? DEFAULT_INCOME_REPLACEMENT_YEARS;
  const partnerContributionFactor = input.hasPartner === true ? 0.5 : 0;
  const incomeReplacementNeed = round(
    incomeToReplace * yearsToReplace * (1 - partnerContributionFactor),
    0,
  );
  if (input.yearsToRetirement == null) {
    assumptions.push(`Years to retirement not provided — defaulted to ${DEFAULT_INCOME_REPLACEMENT_YEARS} years.`);
  }
  if (input.hasPartner === true) {
    assumptions.push('Partner income assumed to contribute 50% — income replacement need halved.');
  }

  // 4. Final expenses
  const finalExpensesNeed = DEFAULT_FINAL_EXPENSES_AUD;

  // 5. Other capital needs (not quantified here — caller can extend)
  const otherCapitalNeeds = 0;

  const grossNeed = debtClearanceNeed + educationFundingNeed + incomeReplacementNeed + finalExpensesNeed + otherCapitalNeeds;

  // Less: existing total life cover across all policies
  const lessExistingCover =
    (input.existingLifeCoverSumInsured ?? 0) +
    (input.existingLifeSumInsured ?? 0);

  // Less: liquid assets (assumed accessible on death)
  const lessLiquidAssets = input.liquidAssets ?? 0;

  const netLifeInsuranceNeed = Math.max(0, grossNeed - lessExistingCover - lessLiquidAssets);

  return {
    debtClearanceNeed,
    educationFundingNeed,
    incomeReplacementNeed,
    finalExpensesNeed,
    otherCapitalNeeds,
    grossNeed,
    lessExistingCover,
    lessLiquidAssets,
    netLifeInsuranceNeed,
    shortfallLevel: classifyShortfall(netLifeInsuranceNeed),
    assumptions,
  };
}

// =============================================================================
// B — TPD INSURANCE NEED ANALYSIS
//
// Formula:
//   Gross need = debt clearance + medical/rehab + capitalised income replacement
//                + home modification + ongoing care
//   Net need   = gross need − existing TPD cover − liquid assets
// =============================================================================

export function calculateTPDNeed(input: NormalizedInput): TPDNeedResult {
  const assumptions: string[] = [];

  // 1. Debt clearance (same as life)
  const debtClearanceNeed = (input.mortgageBalance ?? 0) + (input.otherDebts ?? 0);

  // 2. Medical / rehabilitation buffer
  const medicalRehabBuffer = DEFAULT_MEDICAL_REHAB_BUFFER_AUD;

  // 3. Income replacement — capitalised using present value of annuity
  //    Uses net income if available, otherwise estimated from gross income at 70%
  const annualIncomeForTPD =
    input.annualNetIncome ??
    (input.annualGrossIncome != null ? round(input.annualGrossIncome * 0.7, 0) : 0);
  if (input.annualNetIncome == null && input.annualGrossIncome != null) {
    assumptions.push('Net income not provided — estimated at 70% of gross income for TPD capitalisation.');
  }

  const yearsToCapitalise = input.yearsToRetirement ?? DEFAULT_INCOME_REPLACEMENT_YEARS;
  const incomeReplacementCapitalised = round(
    presentValueAnnuity(annualIncomeForTPD, yearsToCapitalise, TPD_CAPITALISATION_RATE),
    0,
  );
  if (input.yearsToRetirement == null) {
    assumptions.push(`Years to retirement not provided — defaulted to ${DEFAULT_INCOME_REPLACEMENT_YEARS} years for TPD capitalisation.`);
  }
  assumptions.push(`TPD income capitalisation rate: ${(TPD_CAPITALISATION_RATE * 100).toFixed(1)}% p.a.`);

  // 4. Home modification buffer
  const homeModificationBuffer = DEFAULT_HOME_MODIFICATION_BUFFER_AUD;

  // 5. Ongoing care buffer
  const ongoingCareBuffer = DEFAULT_ONGOING_CARE_BUFFER_AUD;

  const grossNeed =
    debtClearanceNeed +
    medicalRehabBuffer +
    incomeReplacementCapitalised +
    homeModificationBuffer +
    ongoingCareBuffer;

  // Less: existing TPD cover (all policies)
  const lessExistingTPDCover =
    (input.existingTPDCoverSumInsured ?? 0) +
    (input.existingTPDSumInsured ?? 0);

  // Less: liquid assets
  const lessLiquidAssets = input.liquidAssets ?? 0;

  const netTPDNeed = Math.max(0, grossNeed - lessExistingTPDCover - lessLiquidAssets);

  return {
    debtClearanceNeed,
    medicalRehabBuffer,
    incomeReplacementCapitalised,
    homeModificationBuffer,
    ongoingCareBuffer,
    grossNeed,
    lessExistingTPDCover,
    lessLiquidAssets,
    netTPDNeed,
    shortfallLevel: classifyShortfall(netTPDNeed),
    capitalisationRate: TPD_CAPITALISATION_RATE,
    assumptions,
  };
}

// =============================================================================
// C — AFFORDABILITY ANALYSIS
// =============================================================================

/**
 * Compute affordability metrics for the current or proposed premium.
 * If both existing and new premiums are provided, uses the new premium
 * for prospective affordability; uses existing for current burden.
 */
export function calculateAffordability(input: NormalizedInput): AffordabilityResult {
  const notes: string[] = [];

  // Resolve which premium to assess
  const premiumToAssess =
    input.newProjectedAnnualPremium ?? input.existingAnnualPremium;

  if (premiumToAssess == null) {
    return {
      totalAnnualPremium: null,
      premiumAsPercentOfGrossIncome: null,
      premiumAsPercentOfNetIncome: null,
      projectedPremiumIn10Years: null,
      affordabilityScore: 50,
      lapseRiskScore: 50,
      stressCaseAffordable: null,
      assessment: 'UNKNOWN',
      notes: ['Premium amount not provided — affordability cannot be assessed.'],
    };
  }

  const grossIncome = input.annualGrossIncome ?? 0;
  const netIncome = input.annualNetIncome ?? (grossIncome * 0.7);

  const premiumAsPercentOfGrossIncome =
    grossIncome > 0 ? round((premiumToAssess / grossIncome) * 100, 2) : null;

  const premiumAsPercentOfNetIncome =
    netIncome > 0 ? round((premiumToAssess / netIncome) * 100, 2) : null;

  // Project stepped premium 10 years forward
  const premiumStructure =
    input.newPremiumStructure !== PremiumStructure.UNKNOWN
      ? input.newPremiumStructure
      : input.existingPremiumStructure;

  const projectedPremiumIn10Years =
    premiumStructure === PremiumStructure.STEPPED
      ? round(
          projectSteppedPremium(premiumToAssess, 10, STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR),
          0,
        )
      : premiumToAssess;

  if (premiumStructure === PremiumStructure.STEPPED) {
    notes.push(
      `Stepped premium projected to approximately $${projectedPremiumIn10Years.toLocaleString()} p.a. in 10 years (at ${(STEPPED_PREMIUM_ANNUAL_INCREASE_FACTOR * 100).toFixed(0)}% p.a. average increase).`,
    );
  }

  // Affordability score (0–100) based on % of gross income
  const grossRatio = premiumAsPercentOfGrossIncome ?? 0;
  let affordabilityScore: number;
  let assessment: AffordabilityResult['assessment'];

  if (grossRatio < AFFORDABILITY_INCOME_BANDS.COMFORTABLE * 100) {
    affordabilityScore = 90;
    assessment = 'COMFORTABLE';
  } else if (grossRatio < AFFORDABILITY_INCOME_BANDS.MANAGEABLE * 100) {
    affordabilityScore = 70;
    assessment = 'MANAGEABLE';
  } else if (grossRatio < AFFORDABILITY_INCOME_BANDS.STRETCHED * 100) {
    affordabilityScore = 45;
    assessment = 'STRETCHED';
  } else {
    affordabilityScore = 20;
    assessment = 'UNAFFORDABLE';
  }

  // Adjust downward for stepped premium if future burden is higher
  if (projectedPremiumIn10Years != null && grossIncome > 0) {
    const futureRatio = (projectedPremiumIn10Years / grossIncome) * 100;
    if (futureRatio >= AFFORDABILITY_INCOME_BANDS.UNAFFORDABLE * 100) {
      affordabilityScore = Math.max(0, affordabilityScore - 25);
      notes.push('Future stepped premium exceeds 5% of income — long-term affordability concern.');
    } else if (futureRatio >= AFFORDABILITY_INCOME_BANDS.STRETCHED * 100) {
      affordabilityScore = Math.max(0, affordabilityScore - 10);
      notes.push('Future stepped premium approaches affordability limits.');
    }
  }

  // Explicit affordability concern flag from client
  if (input.affordabilityIsConcern === true) {
    affordabilityScore = Math.max(0, affordabilityScore - 15);
    notes.push('Client has indicated affordability is a concern.');
  }

  // Lapse risk — inversely related to affordability
  const lapseRiskScore = clamp(100 - affordabilityScore, 0, 100);

  // Stress case: if premium structure is stepped, is the 10-year projection manageable?
  const stressCaseAffordable =
    projectedPremiumIn10Years != null && grossIncome > 0
      ? (projectedPremiumIn10Years / grossIncome) <
        AFFORDABILITY_NET_INCOME_BANDS.STRETCHED
      : null;

  return {
    totalAnnualPremium: premiumToAssess,
    premiumAsPercentOfGrossIncome,
    premiumAsPercentOfNetIncome,
    projectedPremiumIn10Years,
    affordabilityScore: clamp(affordabilityScore, 0, 100),
    lapseRiskScore: clamp(lapseRiskScore, 0, 100),
    stressCaseAffordable,
    assessment,
    notes,
  };
}
