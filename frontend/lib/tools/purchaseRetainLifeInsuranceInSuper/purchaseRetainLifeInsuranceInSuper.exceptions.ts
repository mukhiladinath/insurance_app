// =============================================================================
// EXCEPTIONS — purchaseRetainLifeInsuranceInSuper
//
// Statutory exceptions that can override PYS switch-off triggers.
// Each function is pure and returns an ExceptionResult.
// =============================================================================

import { ExceptionType, FundType } from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  NormalizedInput,
  ExceptionResult,
  RuleTraceEntry,
} from './purchaseRetainLifeInsuranceInSuper.types';
import {
  SMALL_FUND_MEMBER_COUNT_THRESHOLD,
  RULE_IDS,
} from './purchaseRetainLifeInsuranceInSuper.constants';

// =============================================================================
// E-001 — SMALL FUND CARVE-OUT
// =============================================================================

/**
 * SMSFs and small APRA funds (≤ 6 members) have different trustee structures.
 * Because the members ARE the trustees in an SMSF, the PYS switch-off rules
 * that govern RSE licensees operate differently. In practice:
 *   - SMSFs are not RSE licensees and are not subject to the same
 *     automatic cessation obligations under s68AAA.
 *   - Small APRA funds with ≤ 6 members have simplified trustee arrangements
 *     that may reduce the impact of PYS switch-off obligations.
 *
 * This exception does NOT mean cover is unrestricted — SIS s67A permissibility
 * still applies. But the automatic switch-off triggers under s68AAA do not
 * apply in the same mandatory way to these fund types.
 */
export function isSmallFundCarveOutApplicable(input: NormalizedInput): ExceptionResult {
  const isSMSF = input.fundType === FundType.SMSF;
  const isSmallAPRA =
    input.fundType === FundType.SMALL_APRA &&
    (input.fundMemberCount ?? Infinity) <= SMALL_FUND_MEMBER_COUNT_THRESHOLD;

  const applied = isSMSF || isSmallAPRA;

  return {
    applied,
    type: ExceptionType.SMALL_FUND_CARVE_OUT,
    reason: applied
      ? isSMSF
        ? 'Fund is an SMSF. The PYS automatic switch-off obligations under SIS s68AAA do not apply to SMSFs as they are not RSE licensees.'
        : `Fund is a small APRA fund with ${input.fundMemberCount ?? 'unknown'} members (≤ ${SMALL_FUND_MEMBER_COUNT_THRESHOLD}). Switch-off obligations apply with reduced mandatory force.`
      : 'Small fund carve-out does not apply: fund is not an SMSF or qualifying small APRA fund.',
    supportingFacts: {
      fundType: input.fundType,
      fundMemberCount: input.fundMemberCount,
      isSMSF,
      isSmallAPRA,
      threshold: SMALL_FUND_MEMBER_COUNT_THRESHOLD,
    },
  };
}

// =============================================================================
// E-002 — DEFINED BENEFIT EXCEPTION
// =============================================================================

/**
 * Insurance for defined benefit fund members is typically embedded in the
 * benefit formula and is not a separately charged premium product. The PYS
 * switch-off rules were designed for accumulation-style products where premiums
 * are debited from member accounts. Defined benefit insurance is structurally
 * different and the s68AAA switch-off obligations do not apply in the same way.
 */
export function isDefinedBenefitExceptionApplicable(input: NormalizedInput): ExceptionResult {
  const applied =
    input.isDefinedBenefitMember || input.fundType === FundType.DEFINED_BENEFIT;

  return {
    applied,
    type: ExceptionType.DEFINED_BENEFIT,
    reason: applied
      ? 'Member is in a defined benefit fund. Insurance benefits are structurally embedded in the benefit formula; s68AAA premium-deduction switch-off rules do not apply in the same manner.'
      : 'Defined benefit exception does not apply: member is not in a defined benefit fund.',
    supportingFacts: {
      isDefinedBenefitMember: input.isDefinedBenefitMember,
      fundType: input.fundType,
    },
  };
}

// =============================================================================
// E-003 — ADF / COMMONWEALTH EXCEPTION
// =============================================================================

/**
 * Members of the Australian Defence Force and certain Commonwealth employees
 * may have insurance arrangements under specific Commonwealth legislation or
 * Commonwealth-administered super funds (e.g. Military Superannuation and
 * Benefits scheme, CSS, PSS). These members are typically subject to different
 * or overriding Commonwealth legislative frameworks that take precedence over
 * the PYS package obligations.
 */
export function isADFCommonwealthExceptionApplicable(input: NormalizedInput): ExceptionResult {
  const applied = input.isADFOrCommonwealthExceptionCase;

  return {
    applied,
    type: ExceptionType.ADF_COMMONWEALTH,
    reason: applied
      ? 'Member is identified as an ADF or Commonwealth exception case. Commonwealth-specific legislative frameworks may override or displace PYS switch-off obligations.'
      : 'ADF / Commonwealth exception does not apply.',
    supportingFacts: {
      isADFOrCommonwealthExceptionCase: input.isADFOrCommonwealthExceptionCase,
    },
  };
}

// =============================================================================
// E-004 — EMPLOYER-SPONSORED CONTRIBUTION EXCEPTION (SIS s68AAA(4A))
// =============================================================================

/**
 * Under SIS s68AAA(4A), a trustee is NOT required to switch off insurance if:
 *   (a) an employer has given the trustee written notice that it wishes the
 *       member's insurance to be maintained; AND
 *   (b) the employer's contributions to the fund in respect of the member
 *       for the period exceed the SG minimum by an amount at least equal
 *       to the amount of the insurance fees for the period.
 *
 * This exception overrides the inactivity and low-balance triggers.
 * It does NOT override the under-25 rule (which requires member's own election).
 */
export function isEmployerSponsoredContributionExceptionApplicable(
  input: NormalizedInput,
): ExceptionResult {
  const notificationMet = input.employerHasNotifiedTrusteeInWriting;
  const contributionMet = input.employerContributionsExceedSGMinimumByInsuranceFeeAmount;
  const applied = notificationMet && contributionMet;

  const partiallyMet = (notificationMet || contributionMet) && !applied;

  return {
    applied,
    type: ExceptionType.EMPLOYER_SPONSORED_CONTRIBUTION,
    reason: applied
      ? 'Employer-sponsored contribution exception applies (SIS s68AAA(4A)): trustee has written notification from employer and employer contributions exceed SG minimum by the insurance fee amount.'
      : partiallyMet
        ? `Employer-sponsored exception partially met but NOT applicable: ${!notificationMet ? 'written employer notification is missing' : ''}${!contributionMet ? 'employer contributions do not exceed SG minimum by the insurance fee' : ''}.`
        : 'Employer-sponsored contribution exception does not apply: neither condition is met.',
    supportingFacts: {
      employerHasNotifiedTrusteeInWriting: input.employerHasNotifiedTrusteeInWriting,
      employerContributionsExceedSGMinimumByInsuranceFeeAmount:
        input.employerContributionsExceedSGMinimumByInsuranceFeeAmount,
      notificationMet,
      contributionMet,
    },
  };
}

// =============================================================================
// E-005 — DANGEROUS OCCUPATION EXCEPTION
// =============================================================================

/**
 * Where a member works in a dangerous occupation and the trustee has registered
 * that occupation election (or the member has lodged an equivalent direction),
 * the trustee may maintain insurance despite inactivity or low-balance triggers.
 * This typically operates via a member's direction under the fund's governing rules
 * or via specific SIS regulation exemption categories.
 */
export function isDangerousOccupationExceptionApplicable(input: NormalizedInput): ExceptionResult {
  const applied =
    input.hasDangerousOccupationElection && input.dangerousOccupationElectionInForce;

  const electionExistsButNotActive =
    input.hasDangerousOccupationElection && !input.dangerousOccupationElectionInForce;

  return {
    applied,
    type: ExceptionType.DANGEROUS_OCCUPATION,
    reason: applied
      ? 'Dangerous occupation exception applies: a dangerous occupation election is registered and currently in force. Insurance may be maintained despite inactivity or low-balance triggers.'
      : electionExistsButNotActive
        ? 'A dangerous occupation election exists but is not currently in force — exception does not apply.'
        : 'Dangerous occupation exception does not apply: no election registered.',
    supportingFacts: {
      hasDangerousOccupationElection: input.hasDangerousOccupationElection,
      dangerousOccupationElectionInForce: input.dangerousOccupationElectionInForce,
    },
  };
}

// =============================================================================
// E-006 — SUCCESSOR FUND TRANSFER CONTINUITY
// =============================================================================

/**
 * When a member's account is transferred to a successor fund, the trustee of the
 * successor fund must provide equivalent insurance rights (SIS s29B and related
 * provisions). Where those equivalent rights are confirmed:
 *   - any prior opt-in elections are treated as carried across
 *   - the insurance continuity is preserved without the need for a new election
 *
 * This exception is only valid when equivalentRightsConfirmed = true.
 */
export function isSuccessorTransferContinuityApplicable(input: NormalizedInput): ExceptionResult {
  const applied =
    input.successorFundTransferOccurred && input.equivalentRightsConfirmed;

  const transferredButUnconfirmed =
    input.successorFundTransferOccurred && !input.equivalentRightsConfirmed;

  return {
    applied,
    type: ExceptionType.SUCCESSOR_FUND_TRANSFER,
    reason: applied
      ? 'Successor fund transfer continuity applies: transfer has occurred and equivalent insurance rights have been confirmed by the successor fund trustee.'
      : transferredButUnconfirmed
        ? 'Successor fund transfer occurred but equivalent rights have NOT been confirmed — continuity cannot be relied upon until confirmed.'
        : 'Successor fund transfer exception does not apply: no transfer occurred.',
    supportingFacts: {
      successorFundTransferOccurred: input.successorFundTransferOccurred,
      equivalentRightsConfirmed: input.equivalentRightsConfirmed,
      priorElectionCarriedViaSuccessorTransfer:
        input.priorElectionCarriedViaSuccessorTransfer,
    },
  };
}

// =============================================================================
// E-007 — RIGHTS NOT AFFECTED (fixed-term / fully-paid / non-premium-paying)
// =============================================================================

/**
 * The PYS switch-off rules operate by prohibiting trustees from charging or
 * deducting premiums in specified circumstances (SIS s68AAA — "must not charge
 * or deduct a premium"). If there is no premium being charged or deducted:
 *   - fixed-term cover where the term has not yet expired
 *   - fully-paid-up cover (no ongoing premiums)
 *   - non-premium-paying policies
 * then the prohibition in s68AAA is simply not engaged.
 * The member's rights under those arrangements are not affected.
 */
export function isRightsNotAffectedCase(input: NormalizedInput): ExceptionResult {
  const applied = input.fixedTermCover || input.fullyPaidOrNonPremiumPaying;

  return {
    applied,
    type: ExceptionType.RIGHTS_NOT_AFFECTED,
    reason: applied
      ? input.fixedTermCover
        ? 'Fixed-term cover: no ongoing premiums are charged from the account during the term. SIS s68AAA switch-off provisions are not engaged.'
        : 'Fully-paid or non-premium-paying cover: no ongoing premiums are charged from the account. SIS s68AAA switch-off provisions are not engaged.'
      : 'Rights-not-affected exception does not apply: cover is a standard premium-paying product.',
    supportingFacts: {
      fixedTermCover: input.fixedTermCover,
      fullyPaidOrNonPremiumPaying: input.fullyPaidOrNonPremiumPaying,
    },
  };
}

// =============================================================================
// AGGREGATE — evaluate all exceptions in order
// =============================================================================

export function evaluateAllExceptions(input: NormalizedInput): {
  exceptions: ExceptionResult[];
  exceptionRuleTrace: RuleTraceEntry[];
} {
  const smallFund = isSmallFundCarveOutApplicable(input);
  const definedBenefit = isDefinedBenefitExceptionApplicable(input);
  const adfCommonwealth = isADFCommonwealthExceptionApplicable(input);
  const employerSponsored = isEmployerSponsoredContributionExceptionApplicable(input);
  const dangerousOccupation = isDangerousOccupationExceptionApplicable(input);
  const successorTransfer = isSuccessorTransferContinuityApplicable(input);
  const rightsNotAffected = isRightsNotAffectedCase(input);

  const exceptions = [
    smallFund,
    definedBenefit,
    adfCommonwealth,
    employerSponsored,
    dangerousOccupation,
    successorTransfer,
    rightsNotAffected,
  ];

  const exceptionRuleTrace: RuleTraceEntry[] = [
    {
      ruleId: RULE_IDS.SMALL_FUND_EXCEPTION,
      ruleName: 'Small Fund Carve-Out',
      passed: smallFund.applied,
      outcome: smallFund.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: smallFund.reason,
      supportingFacts: smallFund.supportingFacts,
    },
    {
      ruleId: RULE_IDS.DEFINED_BENEFIT_EXCEPTION,
      ruleName: 'Defined Benefit Exception',
      passed: definedBenefit.applied,
      outcome: definedBenefit.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: definedBenefit.reason,
      supportingFacts: definedBenefit.supportingFacts,
    },
    {
      ruleId: RULE_IDS.ADF_COMMONWEALTH_EXCEPTION,
      ruleName: 'ADF / Commonwealth Exception',
      passed: adfCommonwealth.applied,
      outcome: adfCommonwealth.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: adfCommonwealth.reason,
      supportingFacts: adfCommonwealth.supportingFacts,
    },
    {
      ruleId: RULE_IDS.EMPLOYER_SPONSORED_EXCEPTION,
      ruleName: 'Employer-Sponsored Contribution Exception (SIS s68AAA(4A))',
      passed: employerSponsored.applied,
      outcome: employerSponsored.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: employerSponsored.reason,
      supportingFacts: employerSponsored.supportingFacts,
    },
    {
      ruleId: RULE_IDS.DANGEROUS_OCCUPATION_EXCEPTION,
      ruleName: 'Dangerous Occupation Exception',
      passed: dangerousOccupation.applied,
      outcome: dangerousOccupation.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: dangerousOccupation.reason,
      supportingFacts: dangerousOccupation.supportingFacts,
    },
    {
      ruleId: RULE_IDS.SUCCESSOR_FUND_EXCEPTION,
      ruleName: 'Successor Fund Transfer Continuity',
      passed: successorTransfer.applied,
      outcome: successorTransfer.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: successorTransfer.reason,
      supportingFacts: successorTransfer.supportingFacts,
    },
    {
      ruleId: RULE_IDS.RIGHTS_NOT_AFFECTED_EXCEPTION,
      ruleName: 'Rights Not Affected (Fixed-Term / Fully-Paid)',
      passed: rightsNotAffected.applied,
      outcome: rightsNotAffected.applied ? 'EXCEPTION_APPLIED' : 'NOT_APPLICABLE',
      explanation: rightsNotAffected.reason,
      supportingFacts: rightsNotAffected.supportingFacts,
    },
  ];

  return { exceptions, exceptionRuleTrace };
}
