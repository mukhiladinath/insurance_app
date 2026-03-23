// =============================================================================
// VALIDATORS — purchaseRetainLifeInsuranceInSuper
//
// Three-pass validation:
//   Pass A — mandatory legal facts (blocking)
//   Pass B — conditional requirements (blocking when condition met)
//   Pass C — contradiction / consistency checks (blocking)
//
// Output also includes non-blocking warnings and grouped missing-info questions.
// =============================================================================

import {
  MissingInfoCategory,
  FundType,
  ProductType,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type {
  PurchaseRetainLifeInsuranceInSuperInput,
  ValidationResult,
  ValidationError,
  ValidationWarning,
  MissingInfoQuestion,
} from './purchaseRetainLifeInsuranceInSuper.types';
import { safeParseDate } from './purchaseRetainLifeInsuranceInSuper.utils';
import { NON_PERMITTED_COVER_TYPES } from './purchaseRetainLifeInsuranceInSuper.constants';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function error(
  field: string,
  message: string,
  category: MissingInfoCategory,
): ValidationError {
  return { field, message, category };
}

function warning(field: string, message: string): ValidationWarning {
  return { field, message };
}

function question(
  id: string,
  question: string,
  category: MissingInfoCategory,
  blocking: boolean,
): MissingInfoQuestion {
  return { id, question, category, blocking };
}

// ---------------------------------------------------------------------------
// Normalisation helpers used inside the validator only
// ---------------------------------------------------------------------------

function resolveAge(input: PurchaseRetainLifeInsuranceInSuperInput): number | null {
  if (input.member?.age != null) return input.member.age;
  if (input.member?.dateOfBirth) {
    const dob = safeParseDate(input.member.dateOfBirth);
    const ref = safeParseDate(input.evaluationDate) ?? new Date();
    if (dob) {
      let age = ref.getFullYear() - dob.getFullYear();
      const m = ref.getMonth() - dob.getMonth();
      if (m < 0 || (m === 0 && ref.getDate() < dob.getDate())) age--;
      return age;
    }
  }
  return null;
}

// ---------------------------------------------------------------------------
// Main validator
// ---------------------------------------------------------------------------

export function validateInput(
  input: PurchaseRetainLifeInsuranceInSuperInput,
): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];
  const missingInfoQuestions: MissingInfoQuestion[] = [];

  const age = resolveAge(input);
  const fundType = input.fund?.fundType;
  const accountBalance = input.product?.accountBalance;
  const coverTypes: ProductType[] = input.product?.coverTypesPresent ?? [];
  const optedIn = input.elections?.optedInToRetainInsurance ?? false;
  const optedOut = input.elections?.optedOutOfInsurance ?? false;
  const successorTransfer = input.fund?.successorFundTransferOccurred ?? false;
  const priorElectionViaTransfer =
    input.elections?.priorElectionCarriedViaSuccessorTransfer ?? false;
  const isDefinedBenefit = input.fund?.isDefinedBenefitMember ?? false;

  // =========================================================================
  // PASS A — MANDATORY LEGAL FACTS
  // =========================================================================

  if (age == null) {
    errors.push(error('member.age', 'Member age or date of birth is required.', MissingInfoCategory.LEGAL));
    missingInfoQuestions.push(
      question('Q-AGE', 'What is the member\'s date of birth or age?', MissingInfoCategory.LEGAL, true),
    );
  }

  if (!fundType) {
    errors.push(error('fund.fundType', 'Fund type is required to determine insurance eligibility rules.', MissingInfoCategory.LEGAL));
    missingInfoQuestions.push(
      question('Q-FUND-TYPE', 'What type of superannuation fund does this member belong to (MySuper, choice, SMSF, small APRA, defined benefit)?', MissingInfoCategory.LEGAL, true),
    );
  }

  if (accountBalance == null) {
    errors.push(error('product.accountBalance', 'Account balance is required to evaluate the low-balance switch-off rule.', MissingInfoCategory.LEGAL));
    missingInfoQuestions.push(
      question('Q-BALANCE', 'What is the current account balance?', MissingInfoCategory.LEGAL, true),
    );
  }

  if (!input.product?.productStartDate) {
    errors.push(error('product.productStartDate', 'Insurance product start date is required.', MissingInfoCategory.LEGAL));
    missingInfoQuestions.push(
      question('Q-START-DATE', 'When did the insurance cover commence?', MissingInfoCategory.LEGAL, true),
    );
  }

  if (coverTypes.length === 0) {
    errors.push(error('product.coverTypesPresent', 'At least one cover type must be specified to evaluate permissibility.', MissingInfoCategory.LEGAL));
    missingInfoQuestions.push(
      question('Q-COVER-TYPE', 'What types of insurance cover are held inside super (e.g. death cover, TPD, income protection)?', MissingInfoCategory.LEGAL, true),
    );
  }

  if (input.elections?.optedInToRetainInsurance == null) {
    // Not blocking — default to false — but add a question
    missingInfoQuestions.push(
      question('Q-OPT-IN', 'Has the member lodged a written direction to retain insurance inside super?', MissingInfoCategory.LEGAL, false),
    );
  }

  // Inactivity: need either lastAmountReceivedDate or receivedAmountInLast16Months
  const hasInactivityFact =
    input.product?.lastAmountReceivedDate != null ||
    input.product?.receivedAmountInLast16Months != null;

  if (!hasInactivityFact) {
    errors.push(
      error(
        'product.lastAmountReceivedDate',
        'Inactivity status cannot be assessed: provide either lastAmountReceivedDate or receivedAmountInLast16Months.',
        MissingInfoCategory.LEGAL,
      ),
    );
    missingInfoQuestions.push(
      question(
        'Q-INACTIVITY',
        'When was the most recent contribution or rollover credited to this account? Or has any amount been received in the past 16 months?',
        MissingInfoCategory.LEGAL,
        true,
      ),
    );
  }

  // =========================================================================
  // PASS B — CONDITIONAL REQUIREMENTS
  // =========================================================================

  // B1: If balance < $6,000, we need to know the grandfathering status
  if (
    accountBalance != null &&
    accountBalance < 6_000 &&
    input.product?.hadBalanceGe6000OnOrAfter2019_11_01 == null
  ) {
    errors.push(
      error(
        'product.hadBalanceGe6000OnOrAfter2019_11_01',
        'Account balance is below $6,000. Grandfathering status (whether the account held >= $6,000 on or after 1 November 2019) must be confirmed.',
        MissingInfoCategory.LEGAL,
      ),
    );
    missingInfoQuestions.push(
      question(
        'Q-GRANDFATHER',
        'Did this account ever hold a balance of $6,000 or more on or after 1 November 2019?',
        MissingInfoCategory.LEGAL,
        true,
      ),
    );
  }

  // B2: If age < 25, product start date is critical to assess pre-existing cover vs new cover
  if (age != null && age < 25 && !input.product?.productStartDate) {
    errors.push(
      error(
        'product.productStartDate',
        'Member is under 25 — product start date is required to determine whether insurance predates the under-25 rule.',
        MissingInfoCategory.LEGAL,
      ),
    );
  }

  // B3: Successor fund transfer — need equivalentRightsConfirmed
  if (
    (successorTransfer || priorElectionViaTransfer) &&
    input.elections?.equivalentRightsConfirmed == null
  ) {
    errors.push(
      error(
        'elections.equivalentRightsConfirmed',
        'Successor fund transfer indicated — equivalent rights confirmation is required before insurance continuity can be assessed.',
        MissingInfoCategory.LEGAL,
      ),
    );
    missingInfoQuestions.push(
      question(
        'Q-SFT-RIGHTS',
        'Has the successor fund trustee confirmed that equivalent insurance rights have been carried across from the predecessor fund?',
        MissingInfoCategory.LEGAL,
        true,
      ),
    );
  }

  // B4: If opted in, we need the opt-in election date
  if (optedIn && !input.elections?.optInElectionDate) {
    errors.push(
      error(
        'elections.optInElectionDate',
        'Opt-in is marked as true but no opt-in election date has been provided.',
        MissingInfoCategory.LEGAL,
      ),
    );
    missingInfoQuestions.push(
      question(
        'Q-OPT-IN-DATE',
        'On what date did the member lodge their written opt-in direction to retain insurance?',
        MissingInfoCategory.LEGAL,
        true,
      ),
    );
  }

  // =========================================================================
  // PASS C — CONTRADICTION / CONSISTENCY CHECKS
  // =========================================================================

  // C1: Defined-benefit fund type vs isDefinedBenefitMember flag inconsistency
  if (fundType === FundType.DEFINED_BENEFIT && !isDefinedBenefit) {
    warnings.push(
      warning(
        'fund.isDefinedBenefitMember',
        'Fund type is DEFINED_BENEFIT but isDefinedBenefitMember is false or absent — this is inconsistent. Defaulting to defined benefit member status.',
      ),
    );
  }
  if (fundType !== FundType.DEFINED_BENEFIT && isDefinedBenefit) {
    warnings.push(
      warning(
        'fund.fundType',
        'isDefinedBenefitMember is true but fundType is not DEFINED_BENEFIT — verify fund type.',
      ),
    );
  }

  // C2: Non-permitted cover types without any transitional flags
  const hasNonPermittedCover = coverTypes.some((ct) =>
    (NON_PERMITTED_COVER_TYPES as readonly string[]).includes(ct),
  );
  const hasTransitionalIndicator =
    input.product?.coverCommencedBefore2014 ||
    input.product?.legacyNonStandardFeatureFlag;

  if (hasNonPermittedCover && !hasTransitionalIndicator) {
    warnings.push(
      warning(
        'product.coverTypesPresent',
        'One or more cover types (TRAUMA, ACCIDENTAL_DEATH) are not permitted insured events under SIS s67A. Without a transitional or legacy indicator, this cover will be assessed as NOT_ALLOWED_IN_SUPER.',
      ),
    );
  }

  // C3: Contradictory election state
  if (optedIn && optedOut) {
    errors.push(
      error(
        'elections',
        'Contradictory elections: member cannot simultaneously be opted in and opted out. Verify election history.',
        MissingInfoCategory.LEGAL,
      ),
    );
  }

  // C4: Opt-out date before opt-in date
  if (optedIn && optedOut) {
    const inDate = safeParseDate(input.elections?.optInElectionDate);
    const outDate = safeParseDate(input.elections?.optOutDate);
    if (inDate && outDate && outDate < inDate) {
      errors.push(
        error(
          'elections.optOutDate',
          'Opt-out date is before opt-in date — check election dates.',
          MissingInfoCategory.LEGAL,
        ),
      );
    }
  }

  // C5: SMSF / small APRA fund with very high member count is suspicious
  if (
    (fundType === FundType.SMSF || fundType === FundType.SMALL_APRA) &&
    (input.fund?.fundMemberCount ?? 0) > 6
  ) {
    warnings.push(
      warning(
        'fund.fundMemberCount',
        'SMSFs and small APRA funds are capped at 6 members. A higher count may indicate an incorrect fund type selection.',
      ),
    );
  }

  // =========================================================================
  // STRATEGIC / ADVICE MISSING INFO (non-blocking)
  // =========================================================================

  if (input.adviceContext?.estimatedAnnualPremium == null) {
    missingInfoQuestions.push(
      question(
        'Q-PREMIUM',
        'What is the estimated annual insurance premium?',
        MissingInfoCategory.AFFORDABILITY,
        false,
      ),
    );
  }

  if (input.adviceContext?.yearsToRetirement == null) {
    missingInfoQuestions.push(
      question(
        'Q-RETIRE',
        'How many years until the member plans to retire?',
        MissingInfoCategory.STRATEGIC,
        false,
      ),
    );
  }

  if (input.adviceContext?.estimatedAnnualPremium == null || input.member?.annualIncome == null) {
    missingInfoQuestions.push(
      question(
        'Q-CASHFLOW',
        'What is the member\'s approximate annual income and current monthly surplus after living expenses?',
        MissingInfoCategory.AFFORDABILITY,
        false,
      ),
    );
  }

  if (input.member?.beneficiaryTypeExpected == null) {
    missingInfoQuestions.push(
      question(
        'Q-BENEFICIARY',
        'Who does the member intend as their primary beneficiary (spouse/dependant child, adult non-dependant, estate)?',
        MissingInfoCategory.BENEFICIARY_ESTATE,
        false,
      ),
    );
  }

  if (input.adviceContext?.needForPolicyFlexibility == null) {
    missingInfoQuestions.push(
      question(
        'Q-FLEXIBILITY',
        'Does the member require the ability to change insurer, sum insured, or policy terms independently of the trustee?',
        MissingInfoCategory.PRODUCT_STRUCTURE,
        false,
      ),
    );
  }

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    missingInfoQuestions,
  };
}
