// =============================================================================
// ENGINE — purchaseRetainLifeInsuranceInSuper
//
// Top-level orchestrator. Calls every layer in order and assembles the final
// deterministic output. This is the single public entry point.
//
// Layer execution order:
//   1. Normalize input
//   2. Validate
//   3. Resolve legal status (rules + exceptions)
//   4. Run calculations
//   5. Assess beneficiary tax risk
//   6. Run placement engine
//   7. Run advice readiness
//   8. Generate member actions
//   9. Assemble final output
// =============================================================================

import {
  AdviceMode,
  BeneficiaryCategory,
  EmploymentStatus,
  FundType,
  LegalStatus,
  ProductType,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  PurchaseRetainLifeInsuranceInSuperInput,
  PurchaseRetainLifeInsuranceInSuperOutput,
  NormalizedInput,
  MemberAction,
} from './purchaseRetainLifeInsuranceInSuper.types';
import { LAW_VERSION } from './purchaseRetainLifeInsuranceInSuper.constants';
import { safeParseDate, computeAge } from './purchaseRetainLifeInsuranceInSuper.utils';
import { validateInput } from './purchaseRetainLifeInsuranceInSuper.validators';
import { resolveLegalStatus } from './purchaseRetainLifeInsuranceInSuper.rules';
import { runCalculations, assessBeneficiaryTaxRisk } from './purchaseRetainLifeInsuranceInSuper.calculations';
import { evaluatePlacementInsideVsOutsideSuper } from './purchaseRetainLifeInsuranceInSuper.placement';
import { evaluateAdviceReadiness } from './purchaseRetainLifeInsuranceInSuper.readiness';

// =============================================================================
// STEP 1 — NORMALIZE INPUT
// =============================================================================

function normalizeInput(
  raw: PurchaseRetainLifeInsuranceInSuperInput,
): NormalizedInput {
  const evaluationDate = safeParseDate(raw.evaluationDate) ?? new Date();
  const dobParsed = safeParseDate(raw.member?.dateOfBirth);

  // Resolve age from explicit field or compute from DOB
  let age: number | null = raw.member?.age ?? null;
  if (age == null && dobParsed) {
    age = computeAge(dobParsed, evaluationDate);
  }

  return {
    // Member
    age,
    dateOfBirth: dobParsed,
    employmentStatus: raw.member?.employmentStatus ?? EmploymentStatus.UNKNOWN,
    occupation: raw.member?.occupation ?? null,
    annualIncome: raw.member?.annualIncome ?? null,
    marginalTaxRate: raw.member?.marginalTaxRate ?? null,
    hasDependants: raw.member?.hasDependants ?? null,
    beneficiaryTypeExpected: raw.member?.beneficiaryTypeExpected ?? BeneficiaryCategory.UNKNOWN,
    cashflowPressure: raw.member?.cashflowPressure ?? null,
    retirementPriorityHigh: raw.member?.retirementPriorityHigh ?? null,
    existingInsuranceNeedsEstimate: raw.member?.existingInsuranceNeedsEstimate ?? null,
    healthOrUnderwritingComplexity: raw.member?.healthOrUnderwritingComplexity ?? null,
    wantsInsideSuper: raw.member?.wantsInsideSuper ?? null,
    wantsAffordability: raw.member?.wantsAffordability ?? null,
    wantsEstateControl: raw.member?.wantsEstateControl ?? null,
    // Fund
    fundType: raw.fund?.fundType ?? null,
    fundMemberCount: raw.fund?.fundMemberCount ?? null,
    isDefinedBenefitMember: raw.fund?.isDefinedBenefitMember ?? false,
    isADFOrCommonwealthExceptionCase: raw.fund?.isADFOrCommonwealthExceptionCase ?? false,
    hasDangerousOccupationElection: raw.fund?.hasDangerousOccupationElection ?? false,
    dangerousOccupationElectionInForce: raw.fund?.dangerousOccupationElectionInForce ?? false,
    trusteeAllowsOptInOnline: raw.fund?.trusteeAllowsOptInOnline ?? false,
    successorFundTransferOccurred: raw.fund?.successorFundTransferOccurred ?? false,
    // Product
    productStartDate: safeParseDate(raw.product?.productStartDate),
    accountBalance: raw.product?.accountBalance ?? null,
    hadBalanceGe6000OnOrAfter2019_11_01: raw.product?.hadBalanceGe6000OnOrAfter2019_11_01 ?? null,
    lastAmountReceivedDate: safeParseDate(raw.product?.lastAmountReceivedDate),
    receivedAmountInLast16Months: raw.product?.receivedAmountInLast16Months ?? null,
    coverTypesPresent: raw.product?.coverTypesPresent ?? [],
    coverCommencedBefore2014: raw.product?.coverCommencedBefore2014 ?? false,
    fixedTermCover: raw.product?.fixedTermCover ?? false,
    fullyPaidOrNonPremiumPaying: raw.product?.fullyPaidOrNonPremiumPaying ?? false,
    legacyNonStandardFeatureFlag: raw.product?.legacyNonStandardFeatureFlag ?? false,
    // Elections
    optedInToRetainInsurance: raw.elections?.optedInToRetainInsurance ?? false,
    optInElectionDate: safeParseDate(raw.elections?.optInElectionDate),
    optedOutOfInsurance: raw.elections?.optedOutOfInsurance ?? false,
    optOutDate: safeParseDate(raw.elections?.optOutDate),
    priorElectionCarriedViaSuccessorTransfer: raw.elections?.priorElectionCarriedViaSuccessorTransfer ?? false,
    equivalentRightsConfirmed: raw.elections?.equivalentRightsConfirmed ?? false,
    // Employer exception
    employerHasNotifiedTrusteeInWriting: raw.employerException?.employerHasNotifiedTrusteeInWriting ?? false,
    employerContributionsExceedSGMinimumByInsuranceFeeAmount:
      raw.employerException?.employerContributionsExceedSGMinimumByInsuranceFeeAmount ?? false,
    // Advice context
    contributionCapPressure: raw.adviceContext?.contributionCapPressure ?? null,
    concessionalContributionsAlreadyHigh: raw.adviceContext?.concessionalContributionsAlreadyHigh ?? null,
    superBalanceAdequacy: raw.adviceContext?.superBalanceAdequacy ?? null,
    preferredBeneficiaryCategory: raw.adviceContext?.preferredBeneficiaryCategory ?? null,
    needForPolicyFlexibility: raw.adviceContext?.needForPolicyFlexibility ?? null,
    needForOwnOccupationStyleDefinitions: raw.adviceContext?.needForOwnOccupationStyleDefinitions ?? null,
    needForPolicyOwnershipOutsideTrusteeControl:
      raw.adviceContext?.needForPolicyOwnershipOutsideTrusteeControl ?? null,
    estimatedAnnualPremium: raw.adviceContext?.estimatedAnnualPremium ?? null,
    yearsToRetirement: raw.adviceContext?.yearsToRetirement ?? null,
    assumedGrowthRate: raw.adviceContext?.assumedGrowthRate ?? null,
    currentMonthlySurplusAfterExpenses: raw.adviceContext?.currentMonthlySurplusAfterExpenses ?? null,
    // Meta
    evaluationDate,
  };
}

// =============================================================================
// STEP 8 — GENERATE MEMBER ACTIONS
// =============================================================================

function generateMemberActions(
  normalizedInput: NormalizedInput,
  legalStatus: LegalStatus,
  adviceMode: AdviceMode,
): MemberAction[] {
  const actions: MemberAction[] = [];

  // Action: opt in to retain cover (when required)
  if (legalStatus === LegalStatus.ALLOWED_BUT_OPT_IN_REQUIRED) {
    actions.push({
      actionId: 'ACT-001',
      priority: 'HIGH',
      action: 'Lodge a written opt-in direction with the super fund trustee to retain insurance inside super.',
      rationale:
        'The under-25 rule (SIS s68AAA(3)) prevents default insurance for members under 25. A written opt-in direction is required to activate and maintain cover.',
    });
  }

  // Action: review dangerous occupation election
  if (
    normalizedInput.hasDangerousOccupationElection &&
    !normalizedInput.dangerousOccupationElectionInForce
  ) {
    actions.push({
      actionId: 'ACT-002',
      priority: 'HIGH',
      action: 'Verify and reinstate the dangerous occupation election with the trustee.',
      rationale:
        'A dangerous occupation election exists on record but is not currently in force. While it exists it does not override switch-off triggers. Reinstatement is required to maintain the exception.',
    });
  }

  // Action: confirm employer exception evidence
  if (
    normalizedInput.employerHasNotifiedTrusteeInWriting &&
    !normalizedInput.employerContributionsExceedSGMinimumByInsuranceFeeAmount
  ) {
    actions.push({
      actionId: 'ACT-003',
      priority: 'HIGH',
      action: 'Confirm with the employer that contributions to the fund exceed the SG minimum by the insurance fee amount for the relevant period.',
      rationale:
        'The employer-sponsored exception (SIS s68AAA(4A)) requires both written notification AND the contribution excess condition. The second condition has not been confirmed.',
    });
  }

  // Action: review legacy policy documents
  if (
    normalizedInput.legacyNonStandardFeatureFlag ||
    normalizedInput.coverCommencedBefore2014
  ) {
    actions.push({
      actionId: 'ACT-004',
      priority: 'MEDIUM',
      action: 'Obtain and review the original policy documents and trust deed provisions for this legacy insurance arrangement.',
      rationale:
        'Cover with legacy or pre-2014 features may have non-standard terms that require specialist review before determining legal status and strategic suitability.',
    });
  }

  // Action: beneficiary review / estate planning
  if (
    normalizedInput.beneficiaryTypeExpected === BeneficiaryCategory.NON_DEPENDANT_ADULT ||
    normalizedInput.beneficiaryTypeExpected === BeneficiaryCategory.LEGAL_PERSONAL_REPRESENTATIVE ||
    normalizedInput.preferredBeneficiaryCategory === BeneficiaryCategory.NON_DEPENDANT_ADULT
  ) {
    actions.push({
      actionId: 'ACT-005',
      priority: 'HIGH',
      action:
        'Review beneficiary nomination and estate planning structure. Consider whether holding this cover outside super (with a direct ownership structure) would reduce the beneficiary tax exposure.',
      rationale:
        'Non-dependant adult beneficiaries or estate-directed death benefits inside super attract up to 17% tax on the taxable component. Outside-super ownership may substantially reduce this burden.',
    });
  }

  // Action: consider outside-super ownership for flexibility
  if (
    normalizedInput.needForPolicyFlexibility === true ||
    normalizedInput.needForOwnOccupationStyleDefinitions === true ||
    normalizedInput.needForPolicyOwnershipOutsideTrusteeControl === true
  ) {
    actions.push({
      actionId: 'ACT-006',
      priority: 'MEDIUM',
      action:
        'Consider obtaining standalone life cover outside super to achieve the required policy flexibility, definition quality, or direct ownership control.',
      rationale:
        'Inside-super insurance is controlled by the trustee and subject to standardised SIS definitions. Own-occupation TPD definitions and direct policy ownership are only achievable outside super.',
    });
  }

  // Action: successor fund — confirm equivalent rights
  if (normalizedInput.successorFundTransferOccurred && !normalizedInput.equivalentRightsConfirmed) {
    actions.push({
      actionId: 'ACT-007',
      priority: 'HIGH',
      action: 'Obtain written confirmation from the successor fund trustee that equivalent insurance rights have been transferred.',
      rationale:
        'A successor fund transfer has occurred but equivalent rights have not been confirmed. Without this confirmation, the insurance continuity exception cannot be relied upon and a fresh election may be required.',
    });
  }

  // Action: review switch-off status and opt-in if desired
  if (legalStatus === LegalStatus.MUST_BE_SWITCHED_OFF) {
    actions.push({
      actionId: 'ACT-008',
      priority: 'HIGH',
      action:
        'A switch-off trigger has fired and insurance inside super must cease unless an applicable exception applies. Review whether any statutory exception is available (e.g. employer notification, dangerous occupation). If no exception applies, arrange replacement cover outside super before the switch-off takes effect.',
      rationale:
        'Insurance ceasing inside super without replacement cover in place could leave the member and their dependants unprotected.',
    });
  }

  return actions;
}

// =============================================================================
// MAIN ORCHESTRATOR
// =============================================================================

export function runPurchaseRetainLifeInsuranceInSuperWorkflow(
  rawInput: PurchaseRetainLifeInsuranceInSuperInput,
): PurchaseRetainLifeInsuranceInSuperOutput {
  // -------------------------------------------------------------------------
  // 1. Normalize
  // -------------------------------------------------------------------------
  const normalizedInput = normalizeInput(rawInput);

  // -------------------------------------------------------------------------
  // 2. Validate
  // -------------------------------------------------------------------------
  const validation = validateInput(rawInput);

  // -------------------------------------------------------------------------
  // 3. Resolve legal status
  //    Run even if validation failed — we produce a partial result with
  //    NEEDS_MORE_INFO status rather than throwing.
  // -------------------------------------------------------------------------
  let legalResult;
  if (!validation.isValid) {
    legalResult = {
      status: LegalStatus.NEEDS_MORE_INFO,
      permissibility: normalizedInput.coverTypesPresent.length === 0
        ? ({ toString: () => 'UNKNOWN' } as never)
        : ({ toString: () => 'UNKNOWN' } as never),
      reasons: [
        'Validation failed — legal status cannot be fully determined until all mandatory facts are provided.',
        ...validation.errors.map((e) => e.message),
      ],
      switchOffEvaluations: [],
      exceptionsApplied: [],
      ruleTrace: [],
    };
  } else {
    legalResult = resolveLegalStatus(normalizedInput);
  }

  // -------------------------------------------------------------------------
  // 4. Run calculations
  // -------------------------------------------------------------------------
  const calculationsOutput = runCalculations(normalizedInput);

  // -------------------------------------------------------------------------
  // 5. Assess beneficiary tax risk
  // -------------------------------------------------------------------------
  const beneficiaryTaxRisk = assessBeneficiaryTaxRisk(normalizedInput);

  // -------------------------------------------------------------------------
  // 6. Run placement engine
  // -------------------------------------------------------------------------
  const placementAssessment = evaluatePlacementInsideVsOutsideSuper(
    normalizedInput,
    legalResult,
    calculationsOutput.placementScores,
  );

  // -------------------------------------------------------------------------
  // 7. Run advice readiness
  // -------------------------------------------------------------------------
  const adviceReadinessResult = evaluateAdviceReadiness(
    normalizedInput,
    legalResult,
    placementAssessment,
    validation,
  );

  // -------------------------------------------------------------------------
  // 8. Generate member actions
  // -------------------------------------------------------------------------
  const memberActions = generateMemberActions(
    normalizedInput,
    legalResult.status,
    adviceReadinessResult.mode,
  );

  // -------------------------------------------------------------------------
  // 9. Assemble final output
  // -------------------------------------------------------------------------

  // Merge all missing info questions from validation + readiness (deduplicate by id)
  const allMissingQuestions = [
    ...validation.missingInfoQuestions,
    ...adviceReadinessResult.missingInfoQuestions,
  ].filter(
    (q, index, self) => self.findIndex((x) => x.id === q.id) === index,
  );

  return {
    normalizedInput,
    validation,
    legalStatus: legalResult.status,
    legalReasons: legalResult.reasons,
    switchOffTriggers: legalResult.switchOffEvaluations,
    exceptionsApplied: legalResult.exceptionsApplied,
    memberActions,
    retirementDragEstimate: calculationsOutput.retirementDrag,
    beneficiaryTaxRisk,
    placementAssessment,
    placementReasons: placementAssessment.reasoning,
    placementRisks: placementAssessment.risks,
    adviceReadiness: adviceReadinessResult.mode,
    missingInfoQuestions: allMissingQuestions,
    ruleTrace: legalResult.ruleTrace,
    lawVersion: LAW_VERSION,
  };
}
