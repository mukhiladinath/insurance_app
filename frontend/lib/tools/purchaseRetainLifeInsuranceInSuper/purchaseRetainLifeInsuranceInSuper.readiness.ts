// =============================================================================
// ADVICE READINESS — purchaseRetainLifeInsuranceInSuper
//
// Determines how personalised and certain the output can be, based on what
// facts have been supplied. Prevents the engine from overstating certainty.
//
// Output modes:
//   NEEDS_MORE_INFO      — blocking legal facts are absent
//   FACTUAL_ONLY         — legal facts complete; strategic facts absent
//   GENERAL_GUIDANCE     — legal facts + some strategic facts present
//   PERSONAL_ADVICE_READY — all material facts present
// =============================================================================

import {
  AdviceMode,
  LegalStatus,
  MissingInfoCategory,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  NormalizedInput,
  LegalResult,
  PlacementResult,
  AdviceReadinessResult,
  MissingInfoQuestion,
  ValidationResult,
} from './purchaseRetainLifeInsuranceInSuper.types';

// ---------------------------------------------------------------------------
// Fact-group presence checks
// ---------------------------------------------------------------------------

function legalFactsComplete(validation: ValidationResult): boolean {
  // If there are any blocking errors, legal facts are incomplete.
  return validation.isValid;
}

function hasCoreBeneficiaryFact(input: NormalizedInput): boolean {
  return (
    input.beneficiaryTypeExpected != null ||
    input.preferredBeneficiaryCategory != null ||
    input.hasDependants != null
  );
}

function hasCoreCashflowFact(input: NormalizedInput): boolean {
  return (
    input.cashflowPressure != null ||
    input.annualIncome != null ||
    input.currentMonthlySurplusAfterExpenses != null ||
    input.estimatedAnnualPremium != null
  );
}

function hasCoreRetirementFact(input: NormalizedInput): boolean {
  return (
    input.retirementPriorityHigh != null ||
    input.yearsToRetirement != null ||
    input.superBalanceAdequacy != null
  );
}

function hasCoreFlexibilityFact(input: NormalizedInput): boolean {
  return (
    input.needForPolicyFlexibility != null ||
    input.needForOwnOccupationStyleDefinitions != null ||
    input.needForPolicyOwnershipOutsideTrusteeControl != null
  );
}

function hasTaxFact(input: NormalizedInput): boolean {
  return input.marginalTaxRate != null;
}

/** Count how many of the five strategic fact groups are present. */
function countStrategicFactGroups(input: NormalizedInput): number {
  return [
    hasCoreBeneficiaryFact(input),
    hasCoreCashflowFact(input),
    hasCoreRetirementFact(input),
    hasCoreFlexibilityFact(input),
    hasTaxFact(input),
  ].filter(Boolean).length;
}

// ---------------------------------------------------------------------------
// Missing question generators per group
// ---------------------------------------------------------------------------

function beneficiaryMissingQuestions(): MissingInfoQuestion[] {
  return [
    {
      id: 'Q-BENEFICIARY-READINESS',
      question:
        'Who is the intended primary beneficiary of the life insurance proceeds (spouse/dependant child, non-dependant adult, or the estate)?',
      category: MissingInfoCategory.BENEFICIARY_ESTATE,
      blocking: false,
    },
    {
      id: 'Q-DEPENDANTS',
      question: 'Does the member have financial dependants (spouse, children)?',
      category: MissingInfoCategory.BENEFICIARY_ESTATE,
      blocking: false,
    },
  ];
}

function cashflowMissingQuestions(): MissingInfoQuestion[] {
  return [
    {
      id: 'Q-INCOME',
      question: 'What is the member\'s approximate annual income?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    },
    {
      id: 'Q-SURPLUS',
      question: 'What is the member\'s estimated monthly surplus after all living expenses?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    },
    {
      id: 'Q-PREMIUM-READINESS',
      question: 'What is the estimated annual insurance premium?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    },
  ];
}

function retirementMissingQuestions(): MissingInfoQuestion[] {
  return [
    {
      id: 'Q-YEARS-TO-RETIRE',
      question: 'How many years until the member intends to retire?',
      category: MissingInfoCategory.STRATEGIC,
      blocking: false,
    },
    {
      id: 'Q-SUPER-BALANCE-ADEQUACY',
      question:
        'Is the member\'s current super balance broadly adequate for their retirement goals, or is it below where they need it to be?',
      category: MissingInfoCategory.STRATEGIC,
      blocking: false,
    },
  ];
}

function flexibilityMissingQuestions(): MissingInfoQuestion[] {
  return [
    {
      id: 'Q-FLEXIBILITY-READINESS',
      question:
        'Does the member need the ability to change insurer, adjust policy terms, or access \'own occupation\' TPD definitions independently of the super trustee?',
      category: MissingInfoCategory.PRODUCT_STRUCTURE,
      blocking: false,
    },
  ];
}

function taxMissingQuestions(): MissingInfoQuestion[] {
  return [
    {
      id: 'Q-MARGINAL-RATE',
      question: 'What is the member\'s current marginal income tax rate?',
      category: MissingInfoCategory.AFFORDABILITY,
      blocking: false,
    },
  ];
}

// =============================================================================
// MAIN READINESS EVALUATOR
// =============================================================================

export function evaluateAdviceReadiness(
  input: NormalizedInput,
  legalResult: LegalResult,
  placementResult: PlacementResult,
  validation: ValidationResult,
): AdviceReadinessResult {
  const missingInfoQuestions: MissingInfoQuestion[] = [];
  const readinessReasons: string[] = [];

  // -------------------------------------------------------------------------
  // Gate 1: Legal facts incomplete → NEEDS_MORE_INFO
  // -------------------------------------------------------------------------
  if (!legalFactsComplete(validation)) {
    readinessReasons.push(
      'One or more mandatory legal facts are absent. The engine cannot determine legal status until these are provided.',
    );
    // Surface all blocking validation questions
    missingInfoQuestions.push(
      ...validation.missingInfoQuestions.filter((q) => q.blocking),
    );
    return {
      mode: AdviceMode.NEEDS_MORE_INFO,
      missingInfoQuestions,
      readinessReasons,
    };
  }

  // If legal status itself is indeterminate, promote to NEEDS_MORE_INFO
  if (legalResult.status === LegalStatus.NEEDS_MORE_INFO) {
    readinessReasons.push(
      'Legal status could not be resolved — additional facts are required.',
    );
    missingInfoQuestions.push(
      ...validation.missingInfoQuestions.filter((q) => q.blocking),
    );
    return {
      mode: AdviceMode.NEEDS_MORE_INFO,
      missingInfoQuestions,
      readinessReasons,
    };
  }

  // -------------------------------------------------------------------------
  // Gate 2: Count strategic fact groups
  // -------------------------------------------------------------------------
  const strategicGroupCount = countStrategicFactGroups(input);

  // Collect all non-blocking missing questions
  if (!hasCoreBeneficiaryFact(input)) {
    missingInfoQuestions.push(...beneficiaryMissingQuestions());
  }
  if (!hasCoreCashflowFact(input)) {
    missingInfoQuestions.push(...cashflowMissingQuestions());
  }
  if (!hasCoreRetirementFact(input)) {
    missingInfoQuestions.push(...retirementMissingQuestions());
  }
  if (!hasCoreFlexibilityFact(input)) {
    missingInfoQuestions.push(...flexibilityMissingQuestions());
  }
  if (!hasTaxFact(input)) {
    missingInfoQuestions.push(...taxMissingQuestions());
  }

  // -------------------------------------------------------------------------
  // Determine mode
  // -------------------------------------------------------------------------

  if (strategicGroupCount === 0) {
    // Legal facts only — no strategic context at all
    readinessReasons.push(
      `Legal status has been determined (${legalResult.status}) but no strategic suitability facts have been provided. Output is factual only.`,
    );
    readinessReasons.push(
      'To progress to general guidance or personal advice, provide income, beneficiary, retirement horizon, and premium details.',
    );
    return {
      mode: AdviceMode.FACTUAL_ONLY,
      missingInfoQuestions,
      readinessReasons,
    };
  }

  if (strategicGroupCount >= 1 && strategicGroupCount <= 2) {
    // Partial strategic facts — general guidance only
    readinessReasons.push(
      `Legal facts complete. ${strategicGroupCount} of 5 strategic fact groups present. ` +
      `General strategic context can be provided but a personalised recommendation requires more information.`,
    );
    return {
      mode: AdviceMode.GENERAL_GUIDANCE,
      missingInfoQuestions,
      readinessReasons,
    };
  }

  if (strategicGroupCount >= 3 && strategicGroupCount <= 4) {
    // Good strategic coverage — general guidance with strong context
    readinessReasons.push(
      `Legal facts complete. ${strategicGroupCount} of 5 strategic fact groups present. ` +
      `Substantial strategic context is available. Placement recommendation produced with noted caveats.`,
    );
    // Still missing 1–2 groups — surface as non-blocking
    return {
      mode: AdviceMode.GENERAL_GUIDANCE,
      missingInfoQuestions,
      readinessReasons,
    };
  }

  // strategicGroupCount === 5 — all fact groups present
  readinessReasons.push(
    'All legal and strategic fact groups are present. A fully personalised, personal-advice-grade structured output has been produced.',
  );

  // Check for any residual non-blocking warnings
  if (validation.warnings.length > 0) {
    readinessReasons.push(
      `Note: ${validation.warnings.length} non-blocking data quality warning(s) recorded. Review before finalising advice.`,
    );
  }

  return {
    mode: AdviceMode.PERSONAL_ADVICE_READY,
    missingInfoQuestions,
    readinessReasons,
  };
}
