// =============================================================================
// COMPLIANCE — purchaseRetainLifeTPDPolicy
//
// Generates compliance flags that the UI must consume and display correctly.
// These flags do NOT enforce UI behaviour in this module — they are outputs
// that the calling layer (UI, agent) must act on.
// =============================================================================

import {
  AdviceMode,
  ReplacementRisk,
  UnderwritingRisk,
  RecommendationType,
} from './purchaseRetainLifeTPDPolicy.enums';
import type {
  NormalizedInput,
  ComplianceFlags,
  UnderwritingRiskResult,
  ReplacementRiskResult,
  PolicyComparisonResult,
} from './purchaseRetainLifeTPDPolicy.types';

export function generateComplianceFlags(
  input: NormalizedInput,
  recommendation: RecommendationType,
  underwritingRisk: UnderwritingRiskResult,
  replacementRisk: ReplacementRiskResult | null,
  comparison: PolicyComparisonResult | null,
): ComplianceFlags {
  const notes: string[] = [];

  // -------------------------------------------------------------------------
  // FSG required: always required when providing financial product advice
  // -------------------------------------------------------------------------
  const requiresFSG = input.adviceMode !== AdviceMode.FACTUAL_INFORMATIONAL;

  // -------------------------------------------------------------------------
  // SOA required: required for personal advice
  // -------------------------------------------------------------------------
  const requiresSOA = input.adviceMode === AdviceMode.PERSONAL_ADVICE;
  if (requiresSOA) {
    notes.push('A Statement of Advice (SOA) must be prepared and provided to the client before acting on a personal advice recommendation.');
  }

  // -------------------------------------------------------------------------
  // General advice warning: required for general advice mode
  // -------------------------------------------------------------------------
  const requiresGeneralAdviceWarning = input.adviceMode === AdviceMode.GENERAL_ADVICE;
  if (requiresGeneralAdviceWarning) {
    notes.push('A general advice warning must be provided: this advice does not take the client\'s personal circumstances into account.');
  }

  // -------------------------------------------------------------------------
  // PDS required: any product recommendation requires PDS disclosure
  // -------------------------------------------------------------------------
  const pdsRequired =
    recommendation === RecommendationType.PURCHASE_NEW ||
    recommendation === RecommendationType.REPLACE_EXISTING ||
    recommendation === RecommendationType.SUPPLEMENT_EXISTING;
  const pdsAcknowledged = null; // To be set by UI interaction layer

  // -------------------------------------------------------------------------
  // TMD check required (Design and Distribution Obligations — DDO)
  // -------------------------------------------------------------------------
  const tmdCheckRequired = pdsRequired;
  const tmdMatched = null; // To be set by UI interaction layer after product selection

  if (tmdCheckRequired) {
    notes.push('Target Market Determination (TMD) check required. Confirm the recommended product is within the target market for this client.');
  }

  // -------------------------------------------------------------------------
  // Anti-hawking: safe if client has approached adviser (not unsolicited offer)
  // -------------------------------------------------------------------------
  // In this engine context we assume the client initiated the engagement.
  const antiHawkingSafe = true;

  // -------------------------------------------------------------------------
  // Underwriting completeness
  // -------------------------------------------------------------------------
  const underwritingIncomplete =
    input.hasNewPolicyCandidate &&
    (input.newUnderwritingStatus === 'NOT_STARTED' ||
      input.newUnderwritingStatus === 'IN_PROGRESS' ||
      input.newUnderwritingStatus == null);

  if (underwritingIncomplete) {
    notes.push('COMPLIANCE: New policy underwriting is not complete. Replacement or new purchase cannot be finalised until underwriting is accepted.');
  }

  // -------------------------------------------------------------------------
  // Replacement risk acknowledgement
  // -------------------------------------------------------------------------
  const replacementRiskAcknowledgementRequired =
    recommendation === RecommendationType.REPLACE_EXISTING ||
    (replacementRisk != null &&
      replacementRisk.overallRisk !== ReplacementRisk.NEGLIGIBLE &&
      replacementRisk.overallRisk !== ReplacementRisk.LOW);

  if (replacementRiskAcknowledgementRequired) {
    notes.push(
      'COMPLIANCE: Replacement risk acknowledgement is required. ' +
      'The client must understand the risks of replacing existing insurance, including potential coverage gaps, ' +
      'loss of grandfathered terms, and the effect of health changes on new underwriting.',
    );
  }

  // Specific ASIC / regulatory note for replacement
  if (recommendation === RecommendationType.REPLACE_EXISTING) {
    notes.push(
      'REPLACEMENT DISCLOSURE: Under ASIC Regulatory Guide 175 and applicable Codes, ' +
      'advisers must take reasonable steps to ensure a replacement recommendation is in the client\'s best interests. ' +
      'Document why the new policy is clearly better for the client.',
    );
  }

  // -------------------------------------------------------------------------
  // Cooling off explanation
  // -------------------------------------------------------------------------
  const coolingOffExplanationRequired =
    recommendation === RecommendationType.PURCHASE_NEW ||
    recommendation === RecommendationType.REPLACE_EXISTING ||
    recommendation === RecommendationType.SUPPLEMENT_EXISTING;

  if (coolingOffExplanationRequired) {
    notes.push('Cooling-off period must be explained: client has 30 days from commencement (or receipt of policy document) to cancel without penalty.');
  }

  // -------------------------------------------------------------------------
  // Manual review required
  // -------------------------------------------------------------------------
  const manualReviewRequired =
    recommendation === RecommendationType.REFER_TO_HUMAN ||
    underwritingRisk.overallRisk === UnderwritingRisk.CRITICAL ||
    (replacementRisk?.overallRisk === ReplacementRisk.BLOCKING) ||
    input.nonDisclosureRisk;

  if (manualReviewRequired) {
    notes.push('MANUAL REVIEW REQUIRED: This case has complexity or risk that requires direct human adviser review before any action is taken.');
  }

  return {
    requiresFSG,
    requiresSOA,
    requiresGeneralAdviceWarning,
    pdsRequired,
    pdsAcknowledged,
    tmdCheckRequired,
    tmdMatched,
    antiHawkingSafe,
    underwritingIncomplete,
    replacementRiskAcknowledgementRequired,
    coolingOffExplanationRequired,
    manualReviewRequired,
    complianceNotes: notes,
  };
}
