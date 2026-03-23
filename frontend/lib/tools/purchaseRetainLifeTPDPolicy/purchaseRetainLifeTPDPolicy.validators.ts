// =============================================================================
// VALIDATORS — purchaseRetainLifeTPDPolicy
// Three-pass validation: mandatory → conditional → contradictions
// =============================================================================

import { MissingInfoCategory, PolicyOwnership } from './purchaseRetainLifeTPDPolicy.enums';
import type {
  PurchaseRetainLifeTPDPolicyInput,
  ValidationResult,
  ValidationError,
  ValidationWarning,
  MissingInfoQuestion,
} from './purchaseRetainLifeTPDPolicy.types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function err(
  field: string,
  message: string,
  category: MissingInfoCategory,
): ValidationError {
  return { field, message, category };
}

function warn(field: string, message: string): ValidationWarning {
  return { field, message };
}

function q(
  id: string,
  question: string,
  category: MissingInfoCategory,
  blocking: boolean,
): MissingInfoQuestion {
  return { id, question, category, blocking };
}

// =============================================================================
// MAIN VALIDATOR
// =============================================================================

export function validateInput(
  input: PurchaseRetainLifeTPDPolicyInput,
): ValidationResult {
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];
  const questions: MissingInfoQuestion[] = [];

  const c = input.client;
  const ep = input.existingPolicy;
  const h = input.health;
  const g = input.goals;
  const np = input.newPolicyCandidate;

  // =========================================================================
  // PASS A — MANDATORY FACTS (blocking)
  // =========================================================================

  if (c?.age == null && c?.dateOfBirth == null) {
    errors.push(err('client.age', 'Client age or date of birth is required.', MissingInfoCategory.CLIENT_PROFILE));
    questions.push(q('Q-AGE', "What is the client's date of birth?", MissingInfoCategory.CLIENT_PROFILE, true));
  }

  if (c?.annualGrossIncome == null) {
    errors.push(err('client.annualGrossIncome', 'Annual gross income is required for need calculations.', MissingInfoCategory.CLIENT_PROFILE));
    questions.push(q('Q-INCOME', "What is the client's annual gross income?", MissingInfoCategory.CLIENT_PROFILE, true));
  }

  if (ep?.hasExistingPolicy == null) {
    errors.push(err('existingPolicy.hasExistingPolicy', 'Whether the client has an existing policy must be specified.', MissingInfoCategory.EXISTING_POLICY));
    questions.push(q('Q-EXISTING', 'Does the client currently hold a life or TPD insurance policy?', MissingInfoCategory.EXISTING_POLICY, true));
  }

  // =========================================================================
  // PASS B — CONDITIONAL REQUIREMENTS
  // =========================================================================

  // B1: If existing policy exists, we need its key details
  if (ep?.hasExistingPolicy === true) {
    if (!ep.coverTypes || ep.coverTypes.length === 0) {
      errors.push(err('existingPolicy.coverTypes', 'Cover types on existing policy are required.', MissingInfoCategory.EXISTING_POLICY));
      questions.push(q('Q-COVER-TYPES', 'What types of cover does the existing policy provide (Life, TPD)?', MissingInfoCategory.EXISTING_POLICY, true));
    }
    if (ep.lifeSumInsured == null && ep.tpdSumInsured == null) {
      errors.push(err('existingPolicy.lifeSumInsured', 'At least one sum insured amount is required for the existing policy.', MissingInfoCategory.EXISTING_POLICY));
      questions.push(q('Q-SUM-INSURED', 'What is the current sum insured for life and/or TPD cover?', MissingInfoCategory.EXISTING_POLICY, true));
    }
    if (ep.annualPremium == null) {
      questions.push(q('Q-PREM-EXISTING', 'What is the current annual premium for the existing policy?', MissingInfoCategory.EXISTING_POLICY, false));
    }
    if (ep.tpdDefinition == null && ep.coverTypes?.includes('TPD' as never)) {
      questions.push(q('Q-TPD-DEF', 'What is the TPD definition on the existing policy (own occupation, any occupation, etc.)?', MissingInfoCategory.EXISTING_POLICY, false));
    }
  }

  // B2: If replacement is being considered, new policy data is needed
  if (g?.wantsReplacement === true && !np?.insurer) {
    errors.push(err('newPolicyCandidate', 'A new policy candidate must be provided when replacement is being considered.', MissingInfoCategory.NEW_POLICY));
    questions.push(q('Q-NEW-POLICY', 'Please provide details of the proposed replacement policy (insurer, cover type, sum insured, premium).', MissingInfoCategory.NEW_POLICY, true));
  }

  // B3: Underwriting status required if replacement is proposed
  if (np?.insurer && np.underwritingStatus == null) {
    questions.push(q('Q-UW-STATUS', 'What is the current underwriting status for the new policy (not started, in progress, accepted standard, accepted with terms, declined)?', MissingInfoCategory.NEW_POLICY, false));
  }

  // B4: Net income needed for TPD capitalisation if available
  if (c?.annualNetIncome == null && c?.annualGrossIncome != null) {
    questions.push(q('Q-NET-INCOME', "What is the client's annual net (after-tax) income? This is used for TPD income replacement calculations.", MissingInfoCategory.CLIENT_PROFILE, false));
  }

  // B5: Years to retirement affects multiple calculations
  if (c?.yearsToRetirement == null && c?.age != null) {
    questions.push(q('Q-RETIRE', 'How many years until the client plans to retire?', MissingInfoCategory.CLIENT_PROFILE, false));
  }

  // B6: Debt details affect need calculations
  if (c?.mortgageBalance == null) {
    questions.push(q('Q-MORTGAGE', "What is the client's outstanding mortgage balance (if any)?", MissingInfoCategory.CLIENT_PROFILE, false));
  }

  // =========================================================================
  // PASS C — CONTRADICTIONS / CONSISTENCY
  // =========================================================================

  // C1: Cannot want both replacement and retention simultaneously
  if (g?.wantsReplacement === true && g?.wantsRetention === true) {
    errors.push(err('goals', 'Client cannot simultaneously want replacement and retention. Clarify intent.', MissingInfoCategory.GOALS));
  }

  // C2: Super-owned TPD with own-occupation definition is not permitted
  if (
    ep?.ownership === PolicyOwnership.SUPER_OWNED &&
    ep?.tpdDefinition === 'OWN_OCCUPATION'
  ) {
    warnings.push(warn(
      'existingPolicy.tpdDefinition',
      'Own-occupation TPD definition cannot be held inside super (SIS Act restriction). Verify the policy ownership and definition — this may be an error.',
    ));
  }

  // C3: New policy with own-occupation TPD and super ownership is not permitted
  if (
    np?.ownership === PolicyOwnership.SUPER_OWNED &&
    np?.tpdDefinition === 'OWN_OCCUPATION'
  ) {
    errors.push(err(
      'newPolicyCandidate.tpdDefinition',
      'Own-occupation TPD is not available inside super. Review new policy candidate details.',
      MissingInfoCategory.NEW_POLICY,
    ));
  }

  // C4: Pending investigations flag without details
  if (h?.pendingInvestigations === true && !h.pendingInvestigationDetails) {
    warnings.push(warn('health.pendingInvestigationDetails', 'Pending investigations are flagged but no details provided. This is a significant underwriting risk — details are required before finalising.'));
    questions.push(q('Q-INVESTIGATIONS', 'What are the nature and status of the pending medical investigations?', MissingInfoCategory.HEALTH, false));
  }

  // C5: Non-disclosure risk — surface prominently
  if (h?.nonDisclosureRisk === true) {
    warnings.push(warn('health.nonDisclosureRisk', 'Non-disclosure risk is flagged. This puts both the existing policy and any proposed replacement at risk. This case must be escalated to a human adviser before any replacement is recommended.'));
  }

  // =========================================================================
  // NON-BLOCKING STRATEGIC QUESTIONS
  // =========================================================================

  if (c?.numberOfDependants == null) {
    questions.push(q('Q-DEPENDANTS', 'How many financial dependants does the client have?', MissingInfoCategory.CLIENT_PROFILE, false));
  }

  if (g?.affordabilityIsConcern == null) {
    questions.push(q('Q-AFFORDABILITY', 'Is affordability a concern for the client (i.e. is the current or proposed premium stretching their budget)?', MissingInfoCategory.AFFORDABILITY, false));
  }

  if (g?.wantsOwnOccupationTPD == null) {
    questions.push(q('Q-OWN-OCC', 'Does the client require an own-occupation TPD definition for their risk profile?', MissingInfoCategory.GOALS, false));
  }

  if (c?.liquidAssets == null) {
    questions.push(q('Q-LIQUID-ASSETS', "What are the client's approximate liquid assets (cash, managed funds, accessible super)?", MissingInfoCategory.CLIENT_PROFILE, false));
  }

  return {
    isValid: errors.length === 0,
    errors,
    warnings,
    missingInfoQuestions: questions,
  };
}
