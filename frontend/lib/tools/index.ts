// =============================================================================
// TOOLS INDEX — frontend/lib/tools/index.ts
//
// Central registry for all business-logic tool modules.
// Import from here to discover available tools consistently.
// Do not add UI components here — this is domain logic only.
// =============================================================================

// ---------------------------------------------------------------------------
// Tool: Purchase / Retain Life Insurance Policy in Superannuation
// ---------------------------------------------------------------------------
export { runPurchaseRetainLifeInsuranceInSuperWorkflow } from './purchaseRetainLifeInsuranceInSuper/purchaseRetainLifeInsuranceInSuper.engine';
export type {
  PurchaseRetainLifeInsuranceInSuperInput,
  PurchaseRetainLifeInsuranceInSuperOutput,
} from './purchaseRetainLifeInsuranceInSuper/purchaseRetainLifeInsuranceInSuper.types';

// ---------------------------------------------------------------------------
// Tool: Purchase / Retain Life / TPD Policy
// ---------------------------------------------------------------------------
export { runPurchaseRetainLifeTPDPolicyWorkflow } from './purchaseRetainLifeTPDPolicy/purchaseRetainLifeTPDPolicy.engine';
export type {
  PurchaseRetainLifeTPDPolicyInput,
  PurchaseRetainLifeTPDPolicyOutput,
} from './purchaseRetainLifeTPDPolicy/purchaseRetainLifeTPDPolicy.types';
