// =============================================================================
// RULES — purchaseRetainLifeInsuranceInSuper
//
// All legal rule functions are pure — same input → same output, no side-effects.
// Statutory references are noted inline.
// =============================================================================

import {
  ProductType,
  FundType,
  CoverPermissibility,
  LegalStatus,
  SwitchOffTrigger,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  NormalizedInput,
  SwitchOffEvaluation,
  ExceptionResult,
  RuleTraceEntry,
  LegalResult,
} from './purchaseRetainLifeInsuranceInSuper.types';
import {
  INACTIVITY_THRESHOLD_MONTHS,
  LOW_BALANCE_THRESHOLD_AUD,
  LOW_BALANCE_GRANDFATHERING_DATE,
  UNDER_25_AGE_THRESHOLD,
  PERMITTED_COVER_TYPES,
  NON_PERMITTED_COVER_TYPES,
  LEGACY_COVER_CUTOFF_DATE,
  RULE_IDS,
  PYS_COMMENCEMENT_DATE,
} from './purchaseRetainLifeInsuranceInSuper.constants';
import { monthsBetween } from './purchaseRetainLifeInsuranceInSuper.utils';
import { evaluateAllExceptions } from './purchaseRetainLifeInsuranceInSuper.exceptions';

// =============================================================================
// R-001 — PERMITTED COVER TYPE CHECK (SIS s67A)
// =============================================================================

/**
 * Map each cover type present on the policy to its permissibility status.
 * A trustee of a regulated super fund may ONLY provide insurance benefits
 * for the death, terminal medical condition, permanent incapacity, or
 * temporary incapacity of a member (SIS s67A).
 */
export function mapLifeCoverIntentToPermittedEvent(
  coverTypes: ProductType[],
  input: NormalizedInput,
): Map<ProductType, CoverPermissibility> {
  const result = new Map<ProductType, CoverPermissibility>();

  for (const ct of coverTypes) {
    if ((PERMITTED_COVER_TYPES as readonly string[]).includes(ct)) {
      result.set(ct, CoverPermissibility.PERMITTED);
    } else if ((NON_PERMITTED_COVER_TYPES as readonly string[]).includes(ct)) {
      // Check transitional / legacy indicators before marking NOT_PERMITTED
      if (input.coverCommencedBefore2014 || input.legacyNonStandardFeatureFlag) {
        result.set(ct, CoverPermissibility.TRANSITIONAL_REVIEW_REQUIRED);
      } else {
        result.set(ct, CoverPermissibility.NOT_PERMITTED);
      }
    } else {
      result.set(ct, CoverPermissibility.UNKNOWN);
    }
  }

  return result;
}

/**
 * Aggregate permissibility across all present cover types.
 * Returns the "worst-case" permissibility to drive the legal status decision.
 */
export function isPermittedInSuper(input: NormalizedInput): CoverPermissibility {
  if (input.coverTypesPresent.length === 0) return CoverPermissibility.UNKNOWN;

  const map = mapLifeCoverIntentToPermittedEvent(input.coverTypesPresent, input);
  const values = [...map.values()];

  // If ANY cover type is NOT_PERMITTED (and no transitional flag), reject the aggregate.
  if (values.includes(CoverPermissibility.NOT_PERMITTED)) {
    return CoverPermissibility.NOT_PERMITTED;
  }
  // If any type needs transitional review, surface that.
  if (values.includes(CoverPermissibility.TRANSITIONAL_REVIEW_REQUIRED)) {
    return CoverPermissibility.TRANSITIONAL_REVIEW_REQUIRED;
  }
  // If all types are either PERMITTED or UNKNOWN
  if (values.every((v) => v === CoverPermissibility.PERMITTED)) {
    return CoverPermissibility.PERMITTED;
  }
  return CoverPermissibility.UNKNOWN;
}

// =============================================================================
// R-002 — LEGACY / TRANSITIONAL CASE CHECK
// =============================================================================

/**
 * Determine whether this is a legacy or transitional cover arrangement that
 * should NOT be auto-rejected based solely on cover-type classification.
 *
 * Indicators:
 *   - Cover commenced before 1 January 2014 (pre-modern SIS insurance framework)
 *   - legacyNonStandardFeatureFlag is set by the caller (e.g. pre-SIS product)
 */
export function isLegacyOrTransitionalCase(input: NormalizedInput): boolean {
  if (input.legacyNonStandardFeatureFlag) return true;
  if (
    input.productStartDate &&
    input.productStartDate < LEGACY_COVER_CUTOFF_DATE
  ) {
    return true;
  }
  if (input.coverCommencedBefore2014) return true;
  return false;
}

// =============================================================================
// R-003 — MYSUPER DEFAULT INSURANCE BASELINE
// =============================================================================

/**
 * Determine whether the MySuper default insurance baseline is applicable.
 * MySuper trustees must offer default death + TPD cover, BUT this baseline
 * is suspended if any PYS switch-off trigger applies (before elections).
 *
 * This function checks the structural precondition only — not triggers.
 */
export function isMySuperBaselineApplicable(input: NormalizedInput): boolean {
  return (
    input.fundType === FundType.MYSUPER &&
    !input.isDefinedBenefitMember &&
    !input.optedOutOfInsurance
  );
}

// =============================================================================
// R-004 — INACTIVITY RULE (SIS s68AAA(1)(a))
// =============================================================================

/**
 * Evaluate whether the 16-month inactivity switch-off trigger has fired.
 *
 * The trigger fires when no contribution or rollover has been credited to the
 * account for 16 consecutive months.
 *
 * Two input modes:
 *   (a) lastAmountReceivedDate — compute months from that date to evaluationDate
 *   (b) receivedAmountInLast16Months — direct boolean override
 */
export function evaluateInactivityRule(input: NormalizedInput): SwitchOffEvaluation {
  let triggered = false;
  let monthsInactive = 0;
  let determinationBasis = '';

  if (input.lastAmountReceivedDate) {
    monthsInactive = monthsBetween(input.lastAmountReceivedDate, input.evaluationDate);
    triggered = monthsInactive >= INACTIVITY_THRESHOLD_MONTHS;
    determinationBasis = `Computed ${monthsInactive} months since last amount received on ${input.lastAmountReceivedDate.toISOString().slice(0, 10)}.`;
  } else if (input.receivedAmountInLast16Months != null) {
    triggered = !input.receivedAmountInLast16Months;
    determinationBasis = `Caller-supplied flag: receivedAmountInLast16Months = ${input.receivedAmountInLast16Months}.`;
  } else {
    // Cannot evaluate — fail safe to not trigger (missing info handled by validator)
    triggered = false;
    determinationBasis = 'Inactivity cannot be assessed — no date or flag provided.';
  }

  return {
    trigger: SwitchOffTrigger.INACTIVITY_16_MONTHS,
    triggered,
    overriddenByException: false, // resolved later
    overriddenByElection: false,  // resolved later
    effectivelyActive: triggered, // updated after exception / election resolution
    reason: triggered
      ? `Inactivity switch-off rule triggered: ${determinationBasis}`
      : `Inactivity rule not triggered: ${determinationBasis}`,
    supportingFacts: {
      lastAmountReceivedDate: input.lastAmountReceivedDate?.toISOString() ?? null,
      receivedAmountInLast16Months: input.receivedAmountInLast16Months,
      monthsInactive: input.lastAmountReceivedDate ? monthsInactive : null,
      threshold: INACTIVITY_THRESHOLD_MONTHS,
      evaluationDate: input.evaluationDate.toISOString().slice(0, 10),
    },
  };
}

// =============================================================================
// R-005 — LOW BALANCE RULE (SIS s68AAA(1)(b))
// =============================================================================

/**
 * Evaluate whether the low-balance switch-off trigger has fired.
 *
 * Trigger fires when account balance < $6,000 AND the account never held
 * >= $6,000 on or after 1 November 2019 (grandfathering does NOT apply).
 *
 * Note: the PYS commencement date matters — the rule only applies to accounts
 * that were below threshold at or after 1 July 2019 without grandfathering.
 */
export function evaluateLowBalanceRule(input: NormalizedInput): SwitchOffEvaluation {
  const balance = input.accountBalance ?? 0;
  const belowThreshold = balance < LOW_BALANCE_THRESHOLD_AUD;

  // Grandfathering: if the account ever held >= $6,000 after 1 Nov 2019,
  // the low-balance trigger cannot apply.
  const isGrandfathered = input.hadBalanceGe6000OnOrAfter2019_11_01 === true;

  // The rule only became operative from PYS commencement.
  const postPYS = input.productStartDate
    ? input.productStartDate <= PYS_COMMENCEMENT_DATE || input.evaluationDate >= PYS_COMMENCEMENT_DATE
    : true;

  const triggered = belowThreshold && !isGrandfathered && postPYS;

  return {
    trigger: SwitchOffTrigger.LOW_BALANCE_UNDER_6000,
    triggered,
    overriddenByException: false,
    overriddenByElection: false,
    effectivelyActive: triggered,
    reason: triggered
      ? `Low-balance switch-off triggered: balance $${balance.toLocaleString()} is below $${LOW_BALANCE_THRESHOLD_AUD.toLocaleString()} and grandfathering does not apply.`
      : !belowThreshold
        ? `Low-balance rule not triggered: balance $${balance.toLocaleString()} is at or above $${LOW_BALANCE_THRESHOLD_AUD.toLocaleString()}.`
        : isGrandfathered
          ? `Low-balance rule not triggered: balance below threshold but account held >= $6,000 on or after ${LOW_BALANCE_GRANDFATHERING_DATE.toISOString().slice(0, 10)} (grandfathered).`
          : `Low-balance rule not triggered.`,
    supportingFacts: {
      accountBalance: balance,
      threshold: LOW_BALANCE_THRESHOLD_AUD,
      belowThreshold,
      isGrandfathered,
      hadBalanceGe6000OnOrAfter2019_11_01: input.hadBalanceGe6000OnOrAfter2019_11_01,
    },
  };
}

// =============================================================================
// R-006 — UNDER-25 RULE (SIS s68AAA(3))
// =============================================================================

/**
 * Evaluate whether the under-25 switch-off rule applies.
 *
 * MySuper trustees must not provide default insurance to members under 25
 * unless the member has lodged a written direction to maintain cover.
 *
 * Unlike the inactivity and low-balance rules, this rule prevents DEFAULT
 * provision rather than mandating cessation of existing cover.
 * A member who never had cover and is under 25 → ALLOWED_BUT_OPT_IN_REQUIRED.
 * A member who had cover and aged below 25 → impossible (age only increases).
 *
 * This rule applies to MySuper products. Choice products may still provide
 * insurance to under-25 members but it must be member-elected, not default.
 */
export function evaluateUnder25Rule(input: NormalizedInput): SwitchOffEvaluation {
  const isUnder25 = input.age != null && input.age < UNDER_25_AGE_THRESHOLD;
  const isMySuperProduct = input.fundType === FundType.MYSUPER;

  // Trigger: under 25 on a MySuper product with no opt-in election
  const triggered = isUnder25 && isMySuperProduct && !input.optedInToRetainInsurance;

  return {
    trigger: SwitchOffTrigger.UNDER_25_NO_ELECTION,
    triggered,
    overriddenByException: false,
    overriddenByElection: false,
    effectivelyActive: triggered,
    reason: triggered
      ? `Under-25 rule triggered: member is age ${input.age} on a MySuper product and has not lodged an opt-in direction.`
      : !isUnder25
        ? `Under-25 rule not triggered: member is age ${input.age ?? 'unknown'} (>= 25).`
        : !isMySuperProduct
          ? `Under-25 rule does not apply: fund type is ${input.fundType ?? 'unknown'} (not MySuper).`
          : `Under-25 rule not triggered: member has lodged a valid opt-in direction.`,
    supportingFacts: {
      age: input.age,
      fundType: input.fundType,
      isUnder25,
      isMySuperProduct,
      optedInToRetainInsurance: input.optedInToRetainInsurance,
    },
  };
}

// =============================================================================
// R-007 — ELECTION STATUS
// =============================================================================

export interface ElectionStatusResult {
  hasValidOptIn: boolean;
  hasOptOut: boolean;
  hasPortabilityElection: boolean;
  notes: string[];
}

/**
 * Evaluate the member's election state.
 * An opt-in election overrides inactivity, low-balance, and under-25 triggers.
 * An opt-out election mandates that insurance be ceased regardless of other factors.
 * Portability (successor fund transfer continuity) depends on equivalent-rights confirmation.
 */
export function evaluateElectionStatus(input: NormalizedInput): ElectionStatusResult {
  const notes: string[] = [];

  const hasValidOptIn =
    input.optedInToRetainInsurance &&
    input.optInElectionDate != null;

  if (input.optedInToRetainInsurance && !input.optInElectionDate) {
    notes.push('Opt-in is flagged as true but no election date is recorded — treating as unconfirmed.');
  }

  const hasOptOut = input.optedOutOfInsurance;

  if (hasOptOut) {
    notes.push('Member has elected to opt out of insurance. This overrides all other triggers and exceptions.');
  }

  const hasPortabilityElection =
    input.priorElectionCarriedViaSuccessorTransfer &&
    input.equivalentRightsConfirmed;

  if (input.priorElectionCarriedViaSuccessorTransfer && !input.equivalentRightsConfirmed) {
    notes.push('Successor fund transfer occurred but equivalent rights have not been confirmed — portability election cannot be relied upon.');
  }

  return { hasValidOptIn, hasOptOut, hasPortabilityElection, notes };
}

// =============================================================================
// R-008 — LEGAL STATUS RESOLUTION (orchestrates R-001 to R-007 + exceptions)
// =============================================================================

/**
 * Resolve the final legal status of life insurance inside super for this member.
 *
 * Resolution order:
 *   1. Cover permissibility (SIS s67A) — reject non-permitted cover types
 *   2. Legacy / transitional flag — route to review rather than hard reject
 *   3. Opt-out election — mandates cessation
 *   4. Evaluate all switch-off triggers (R-004, R-005, R-006)
 *   5. Evaluate all statutory exceptions
 *   6. Apply exception overrides to each trigger evaluation
 *   7. Apply election overrides to each trigger evaluation
 *   8. Determine whether any trigger remains effectively active
 *   9. Return deterministic LegalStatus
 */
export function resolveLegalStatus(input: NormalizedInput): LegalResult {
  const ruleTrace: RuleTraceEntry[] = [];
  const reasons: string[] = [];

  // -------------------------------------------------------------------------
  // Step 1 & 2: Cover permissibility
  // -------------------------------------------------------------------------
  const permissibility = isPermittedInSuper(input);
  const isLegacy = isLegacyOrTransitionalCase(input);

  ruleTrace.push({
    ruleId: RULE_IDS.PERMITTED_COVER_CHECK,
    ruleName: 'Permitted Cover Type Check (SIS s67A)',
    passed: permissibility !== CoverPermissibility.NOT_PERMITTED,
    outcome: permissibility,
    explanation: `Cover types present: [${input.coverTypesPresent.join(', ')}]. Aggregate permissibility: ${permissibility}.`,
    supportingFacts: {
      coverTypesPresent: input.coverTypesPresent,
      permissibility,
    },
  });

  ruleTrace.push({
    ruleId: RULE_IDS.LEGACY_TRANSITIONAL_CHECK,
    ruleName: 'Legacy / Transitional Cover Check',
    passed: isLegacy,
    outcome: isLegacy ? 'LEGACY_INDICATOR_PRESENT' : 'NO_LEGACY_INDICATOR',
    explanation: isLegacy
      ? 'Legacy or pre-reform cover indicators are present — non-permitted cover types will be routed to transitional review rather than hard rejection.'
      : 'No legacy indicators found.',
    supportingFacts: {
      coverCommencedBefore2014: input.coverCommencedBefore2014,
      legacyNonStandardFeatureFlag: input.legacyNonStandardFeatureFlag,
      productStartDate: input.productStartDate?.toISOString() ?? null,
    },
  });

  if (permissibility === CoverPermissibility.NOT_PERMITTED && !isLegacy) {
    reasons.push('Cover type is not a permitted insured event under SIS Act s67A and no legacy / transitional indicators are present.');
    return {
      status: LegalStatus.NOT_ALLOWED_IN_SUPER,
      permissibility,
      reasons,
      switchOffEvaluations: [],
      exceptionsApplied: [],
      ruleTrace,
    };
  }

  if (permissibility === CoverPermissibility.TRANSITIONAL_REVIEW_REQUIRED || isLegacy) {
    // Check for complex legacy features
    if (input.legacyNonStandardFeatureFlag || input.fixedTermCover || input.fullyPaidOrNonPremiumPaying) {
      reasons.push('Legacy or pre-2014 cover with non-standard features — complex rights check required.');
      ruleTrace.push({
        ruleId: RULE_IDS.LEGACY_TRANSITIONAL_CHECK,
        ruleName: 'Complex Legacy / Rights-Not-Affected Assessment',
        passed: false,
        outcome: 'COMPLEX_RIGHTS_CHECK_REQUIRED',
        explanation: 'Cover has legacy non-standard features, fixed-term provisions, or fully-paid status that require manual review.',
        supportingFacts: {
          legacyNonStandardFeatureFlag: input.legacyNonStandardFeatureFlag,
          fixedTermCover: input.fixedTermCover,
          fullyPaidOrNonPremiumPaying: input.fullyPaidOrNonPremiumPaying,
        },
      });
      return {
        status: LegalStatus.COMPLEX_RIGHTS_CHECK_REQUIRED,
        permissibility,
        reasons,
        switchOffEvaluations: [],
        exceptionsApplied: [],
        ruleTrace,
      };
    }
    reasons.push('Cover type or structure may pre-date modern SIS insurance framework — transitional review required.');
    return {
      status: LegalStatus.TRANSITIONAL_REVIEW_REQUIRED,
      permissibility,
      reasons,
      switchOffEvaluations: [],
      exceptionsApplied: [],
      ruleTrace,
    };
  }

  // -------------------------------------------------------------------------
  // Step 3: Opt-out election
  // -------------------------------------------------------------------------
  const electionStatus = evaluateElectionStatus(input);

  if (electionStatus.hasOptOut) {
    reasons.push('Member has elected to opt out of insurance inside super.');
    ruleTrace.push({
      ruleId: RULE_IDS.ELECTION_STATUS,
      ruleName: 'Member Election Status',
      passed: false,
      outcome: 'OPT_OUT',
      explanation: 'Member opt-out election is on file. Insurance must be ceased.',
      supportingFacts: {
        optedOutOfInsurance: input.optedOutOfInsurance,
        optOutDate: input.optOutDate?.toISOString() ?? null,
      },
    });
    return {
      status: LegalStatus.MUST_BE_SWITCHED_OFF,
      permissibility,
      reasons,
      switchOffEvaluations: [],
      exceptionsApplied: [],
      ruleTrace,
    };
  }

  // -------------------------------------------------------------------------
  // Step 4: Evaluate switch-off triggers
  // -------------------------------------------------------------------------
  const inactivityEval = evaluateInactivityRule(input);
  const lowBalanceEval = evaluateLowBalanceRule(input);
  const under25Eval = evaluateUnder25Rule(input);

  ruleTrace.push({
    ruleId: RULE_IDS.INACTIVITY_RULE,
    ruleName: 'Inactivity Switch-Off Rule (SIS s68AAA(1)(a))',
    passed: !inactivityEval.triggered,
    outcome: inactivityEval.triggered ? 'TRIGGERED' : 'NOT_TRIGGERED',
    explanation: inactivityEval.reason,
    supportingFacts: inactivityEval.supportingFacts,
  });

  ruleTrace.push({
    ruleId: RULE_IDS.LOW_BALANCE_RULE,
    ruleName: 'Low-Balance Switch-Off Rule (SIS s68AAA(1)(b))',
    passed: !lowBalanceEval.triggered,
    outcome: lowBalanceEval.triggered ? 'TRIGGERED' : 'NOT_TRIGGERED',
    explanation: lowBalanceEval.reason,
    supportingFacts: lowBalanceEval.supportingFacts,
  });

  ruleTrace.push({
    ruleId: RULE_IDS.UNDER_25_RULE,
    ruleName: 'Under-25 Switch-Off Rule (SIS s68AAA(3))',
    passed: !under25Eval.triggered,
    outcome: under25Eval.triggered ? 'TRIGGERED' : 'NOT_TRIGGERED',
    explanation: under25Eval.reason,
    supportingFacts: under25Eval.supportingFacts,
  });

  // -------------------------------------------------------------------------
  // Step 5: Evaluate all statutory exceptions
  // -------------------------------------------------------------------------
  const { exceptions, exceptionRuleTrace } = evaluateAllExceptions(input);
  ruleTrace.push(...exceptionRuleTrace);

  const anyExceptionApplied = exceptions.some((e) => e.applied);

  // -------------------------------------------------------------------------
  // Step 6 & 7: Apply exception and election overrides to each trigger
  // -------------------------------------------------------------------------
  function applyOverrides(
    eval_: SwitchOffEvaluation,
    trigger: SwitchOffTrigger,
  ): SwitchOffEvaluation {
    if (!eval_.triggered) return eval_;

    // Election override: a valid opt-in overrides all three triggers
    const overriddenByElection =
      electionStatus.hasValidOptIn || electionStatus.hasPortabilityElection;

    // Exception override logic per trigger:
    // - Employer exception: overrides inactivity + low-balance only
    // - Dangerous occupation: overrides inactivity + low-balance only
    // - Small fund, defined benefit, ADF: override all three triggers
    // - Successor fund / rights-not-affected: override all three
    const overriddenByException = exceptions.some((ex) => {
      if (!ex.applied) return false;
      const allTriggerExceptions = [
        'SMALL_FUND_CARVE_OUT',
        'DEFINED_BENEFIT',
        'ADF_COMMONWEALTH',
        'SUCCESSOR_FUND_TRANSFER',
        'RIGHTS_NOT_AFFECTED',
      ];
      const inactivityLowBalanceExceptions = [
        'EMPLOYER_SPONSORED_CONTRIBUTION',
        'DANGEROUS_OCCUPATION',
      ];
      if (allTriggerExceptions.includes(ex.type)) return true;
      if (
        inactivityLowBalanceExceptions.includes(ex.type) &&
        trigger !== SwitchOffTrigger.UNDER_25_NO_ELECTION
      ) {
        return true;
      }
      return false;
    });

    const effectivelyActive = !overriddenByException && !overriddenByElection;

    return {
      ...eval_,
      overriddenByException,
      overriddenByElection,
      effectivelyActive,
      reason: effectivelyActive
        ? eval_.reason
        : `${eval_.reason} [Overridden by: ${overriddenByException ? 'statutory exception' : ''}${overriddenByElection ? ' member election' : ''}]`,
    };
  }

  const finalInactivity = applyOverrides(inactivityEval, SwitchOffTrigger.INACTIVITY_16_MONTHS);
  const finalLowBalance = applyOverrides(lowBalanceEval, SwitchOffTrigger.LOW_BALANCE_UNDER_6000);
  const finalUnder25 = applyOverrides(under25Eval, SwitchOffTrigger.UNDER_25_NO_ELECTION);

  const switchOffEvaluations = [finalInactivity, finalLowBalance, finalUnder25];

  // -------------------------------------------------------------------------
  // Step 8: Determine final status
  // -------------------------------------------------------------------------
  const hardTriggerActive =
    finalInactivity.effectivelyActive || finalLowBalance.effectivelyActive;
  const softTriggerActive = finalUnder25.effectivelyActive;

  ruleTrace.push({
    ruleId: RULE_IDS.LEGAL_STATUS_RESOLUTION,
    ruleName: 'Legal Status Resolution',
    passed: !hardTriggerActive && !softTriggerActive,
    outcome: hardTriggerActive
      ? 'MUST_BE_SWITCHED_OFF'
      : softTriggerActive
        ? 'ALLOWED_BUT_OPT_IN_REQUIRED'
        : 'ALLOWED_AND_ACTIVE',
    explanation: 'Aggregates all trigger evaluations, exception overrides, and election overrides.',
    supportingFacts: {
      inactivityTriggeredAndEffective: finalInactivity.effectivelyActive,
      lowBalanceTriggeredAndEffective: finalLowBalance.effectivelyActive,
      under25TriggeredAndEffective: finalUnder25.effectivelyActive,
      anyExceptionApplied,
      hasValidOptIn: electionStatus.hasValidOptIn,
    },
  });

  // -------------------------------------------------------------------------
  // Step 9: Successor fund transfer — route to COMPLEX if unresolved
  // -------------------------------------------------------------------------
  if (
    input.successorFundTransferOccurred &&
    !input.equivalentRightsConfirmed &&
    !anyExceptionApplied
  ) {
    reasons.push('Successor fund transfer occurred but equivalent rights have not been confirmed — complex rights check required.');
    return {
      status: LegalStatus.COMPLEX_RIGHTS_CHECK_REQUIRED,
      permissibility,
      reasons,
      switchOffEvaluations,
      exceptionsApplied: exceptions,
      ruleTrace,
    };
  }

  // -------------------------------------------------------------------------
  // Determine final status
  // -------------------------------------------------------------------------
  let finalStatus: LegalStatus;

  if (hardTriggerActive) {
    finalStatus = LegalStatus.MUST_BE_SWITCHED_OFF;
    reasons.push(
      finalInactivity.effectivelyActive
        ? finalInactivity.reason
        : finalLowBalance.reason,
    );
  } else if (softTriggerActive) {
    finalStatus = LegalStatus.ALLOWED_BUT_OPT_IN_REQUIRED;
    reasons.push(finalUnder25.reason);
    reasons.push('Member may lodge a written direction with the trustee to opt in to insurance coverage.');
  } else {
    finalStatus = LegalStatus.ALLOWED_AND_ACTIVE;
    reasons.push('No active switch-off triggers. Cover is legally permissible and may continue.');
    if (anyExceptionApplied) {
      const appliedTypes = exceptions.filter((e) => e.applied).map((e) => e.type);
      reasons.push(`Statutory exceptions applied: ${appliedTypes.join(', ')}.`);
    }
    if (electionStatus.hasValidOptIn) {
      reasons.push('Member has a valid opt-in election on file.');
    }
  }

  ruleTrace.push({
    ruleId: RULE_IDS.ELECTION_STATUS,
    ruleName: 'Member Election Status (final)',
    passed: electionStatus.hasValidOptIn || !hardTriggerActive,
    outcome: electionStatus.hasValidOptIn ? 'OPT_IN' : 'NO_ELECTION',
    explanation: electionStatus.notes.join(' ') || 'No election notes.',
    supportingFacts: {
      hasValidOptIn: electionStatus.hasValidOptIn,
      hasOptOut: electionStatus.hasOptOut,
      hasPortabilityElection: electionStatus.hasPortabilityElection,
      notes: electionStatus.notes,
    },
  });

  return {
    status: finalStatus,
    permissibility,
    reasons,
    switchOffEvaluations,
    exceptionsApplied: exceptions,
    ruleTrace,
  };
}
