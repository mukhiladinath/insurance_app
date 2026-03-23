// =============================================================================
// TEST CASES — purchaseRetainLifeTPDPolicy
// Realistic Australian life/TPD insurance scenarios.
// Run with: npx ts-node purchaseRetainLifeTPDPolicy.test-cases.ts
// =============================================================================

import {
  AdviceMode,
  CoverType,
  EmploymentType,
  OccupationClass,
  PolicyOwnership,
  PremiumStructure,
  RecommendationType,
  TPDDefinitionType,
} from './purchaseRetainLifeTPDPolicy.enums';
import type { PurchaseRetainLifeTPDPolicyOutput } from './purchaseRetainLifeTPDPolicy.types';
import { runPurchaseRetainLifeTPDPolicyWorkflow } from './purchaseRetainLifeTPDPolicy.engine';

// ---------------------------------------------------------------------------
// Lightweight test runner (no external dependency)
// ---------------------------------------------------------------------------

interface TestCase {
  name: string;
  input: Parameters<typeof runPurchaseRetainLifeTPDPolicyWorkflow>[0];
  assertions: Array<{
    path: string;
    expected: unknown;
    description: string;
  }>;
}

function getPath(obj: unknown, path: string): unknown {
  return path.split('.').reduce((o) => (o as Record<string, unknown>)?.[path.split('.')[0]], obj);
}

// Simplified deep-path resolver
function resolvePath(obj: unknown, dotPath: string): unknown {
  return dotPath.split('.').reduce(
    (curr, key) => (curr != null ? (curr as Record<string, unknown>)[key] : undefined),
    obj,
  );
}

function runTest(tc: TestCase): { name: string; passed: boolean; failures: string[] } {
  const result = runPurchaseRetainLifeTPDPolicyWorkflow(tc.input);
  const failures: string[] = [];
  for (const a of tc.assertions) {
    const actual = resolvePath(result, a.path);
    if (actual !== a.expected) {
      failures.push(
        `  FAIL [${a.path}]: expected "${String(a.expected)}", got "${String(actual)}" — ${a.description}`,
      );
    }
  }
  return { name: tc.name, passed: failures.length === 0, failures };
}

// =============================================================================
// SCENARIO 1 — Young professional, no existing cover, clear need
// =============================================================================

const s1: TestCase = {
  name: 'SCENARIO-1: No existing policy — purchase new',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 30,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      employmentType: EmploymentType.EMPLOYED_FULL_TIME,
      annualGrossIncome: 95_000,
      annualNetIncome: 70_000,
      hasPartner: true,
      numberOfDependants: 1,
      youngestDependantAge: 2,
      mortgageBalance: 600_000,
      otherDebts: 20_000,
      liquidAssets: 30_000,
      yearsToRetirement: 35,
    },
    existingPolicy: { hasExistingPolicy: false },
    health: { existingMedicalConditions: [], pendingInvestigations: false },
    goals: { primaryReason: 'Protect family after mortgage', wantsReplacement: false },
    newPolicyCandidate: {
      insurer: 'AIA',
      ownership: PolicyOwnership.SELF_OWNED,
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 1_200_000,
      tpdSumInsured: 1_200_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      projectedAnnualPremium: 1_800,
      underwritingStatus: 'ACCEPTED_STANDARD',
    },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.PURCHASE_NEW,
      description: 'No existing cover with a clear need → PURCHASE_NEW',
    },
    {
      path: 'recommendation.complianceFlags.requiresSOA',
      expected: true,
      description: 'Personal advice mode requires SOA',
    },
  ],
};

// =============================================================================
// SCENARIO 2 — Existing policy, low shortfall — retain
// =============================================================================

const s2: TestCase = {
  name: 'SCENARIO-2: Existing policy, low shortfall — retain existing',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 42,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      employmentType: EmploymentType.EMPLOYED_FULL_TIME,
      annualGrossIncome: 140_000,
      annualNetIncome: 100_000,
      hasPartner: true,
      numberOfDependants: 2,
      mortgageBalance: 400_000,
      otherDebts: 10_000,
      liquidAssets: 120_000,
      yearsToRetirement: 23,
      existingLifeCoverSumInsured: 1_800_000,
      existingTPDCoverSumInsured: 1_000_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'TAL',
      ownership: PolicyOwnership.SELF_OWNED,
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 1_800_000,
      tpdSumInsured: 1_000_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      annualPremium: 3_200,
      hasLoadings: false,
      hasExclusions: false,
    },
    health: { existingMedicalConditions: [], pendingInvestigations: false },
    goals: { affordabilityIsConcern: false, wantsRetention: true },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.RETAIN_EXISTING,
      description: 'Existing cover > need → retain',
    },
  ],
};

// =============================================================================
// SCENARIO 3 — Existing policy, significant shortfall — supplement
// =============================================================================

const s3: TestCase = {
  name: 'SCENARIO-3: Significant shortfall, sound policy — supplement existing',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 38,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      employmentType: EmploymentType.EMPLOYED_FULL_TIME,
      annualGrossIncome: 120_000,
      annualNetIncome: 85_000,
      hasPartner: true,
      numberOfDependants: 3,
      youngestDependantAge: 4,
      mortgageBalance: 750_000,
      otherDebts: 30_000,
      liquidAssets: 50_000,
      yearsToRetirement: 27,
      existingLifeCoverSumInsured: 500_000,
      existingTPDCoverSumInsured: 300_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'Zurich',
      ownership: PolicyOwnership.SELF_OWNED,
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 500_000,
      tpdSumInsured: 300_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.LEVEL,
      annualPremium: 2_400,
      hasLoadings: false,
      hasExclusions: false,
      hasSuperiorGrandfatheredTerms: false,
    },
    health: { existingMedicalConditions: [], pendingInvestigations: false },
    goals: { wantsReplacement: false, affordabilityIsConcern: false },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.SUPPLEMENT_EXISTING,
      description: 'Good existing policy but shortfall is significant → supplement',
    },
  ],
};

// =============================================================================
// SCENARIO 4 — Replacement: new policy materially better, low risk
// =============================================================================

const s4: TestCase = {
  name: 'SCENARIO-4: New policy materially better, safe to replace',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 35,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      employmentType: EmploymentType.EMPLOYED_FULL_TIME,
      annualGrossIncome: 110_000,
      annualNetIncome: 80_000,
      hasPartner: false,
      numberOfDependants: 0,
      mortgageBalance: 450_000,
      liquidAssets: 80_000,
      yearsToRetirement: 30,
      existingLifeCoverSumInsured: 700_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'MLC',
      ownership: PolicyOwnership.SELF_OWNED,
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 700_000,
      tpdSumInsured: 700_000,
      tpdDefinition: TPDDefinitionType.ANY_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      annualPremium: 3_800,
      hasLoadings: true,
      loadingDetails: '50% loading on cardiovascular',
      hasExclusions: true,
      exclusionDetails: 'Back condition excluded',
      hasSuperiorGrandfatheredTerms: false,
    },
    health: {
      existingMedicalConditions: [],
      pendingInvestigations: false,
    },
    goals: { wantsReplacement: true, willingToUnderwrite: true },
    newPolicyCandidate: {
      insurer: 'AIA',
      ownership: PolicyOwnership.SELF_OWNED,
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 800_000,
      tpdSumInsured: 800_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      projectedAnnualPremium: 2_800,
      expectedLoadings: '',
      expectedExclusions: '',
      hasIndexation: true,
      flexibilityFeatures: ['Future Insurability', 'Premium Waiver'],
      underwritingStatus: 'ACCEPTED_STANDARD',
    },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.REPLACE_EXISTING,
      description:
        'New policy: better TPD definition, lower premium, no loadings/exclusions, more features → replace',
    },
    {
      path: 'recommendation.complianceFlags.replacementRiskAcknowledgementRequired',
      expected: true,
      description: 'Replacement always requires risk acknowledgement',
    },
  ],
};

// =============================================================================
// SCENARIO 5 — Underwriting incomplete — replacement blocked
// =============================================================================

const s5: TestCase = {
  name: 'SCENARIO-5: Underwriting incomplete — defer / no replacement',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 45,
      smoker: false,
      annualGrossIncome: 90_000,
      mortgageBalance: 300_000,
      liquidAssets: 50_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      lifeSumInsured: 600_000,
      tpdSumInsured: 400_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      annualPremium: 2_500,
      hasLoadings: false,
      hasExclusions: false,
    },
    health: { pendingInvestigations: true, pendingInvestigationDetails: 'Chest CT pending results' },
    goals: { wantsReplacement: true },
    newPolicyCandidate: {
      insurer: 'Zurich',
      lifeSumInsured: 700_000,
      tpdSumInsured: 500_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      projectedAnnualPremium: 2_200,
      underwritingStatus: 'IN_PROGRESS',
    },
  },
  assertions: [
    {
      path: 'recommendation.complianceFlags.underwritingIncomplete',
      expected: true,
      description: 'Underwriting in progress → flag must be set',
    },
    {
      path: 'recommendation.complianceFlags.manualReviewRequired',
      expected: false,
      description: 'No CRITICAL risk so manual review not auto-triggered',
    },
  ],
};

// =============================================================================
// SCENARIO 6 — Non-disclosure risk — refer to human
// =============================================================================

const s6: TestCase = {
  name: 'SCENARIO-6: Non-disclosure risk — refer to human',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 50,
      smoker: false,
      annualGrossIncome: 150_000,
      mortgageBalance: 200_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      lifeSumInsured: 1_000_000,
      tpdSumInsured: 500_000,
      annualPremium: 4_200,
      hasLoadings: false,
      hasExclusions: false,
    },
    health: {
      nonDisclosureRisk: true,
      existingMedicalConditions: ['Depression diagnosed post-policy commencement'],
    },
    goals: { wantsReplacement: false },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.REFER_TO_HUMAN,
      description: 'Non-disclosure risk → always refer to human',
    },
    {
      path: 'recommendation.complianceFlags.manualReviewRequired',
      expected: true,
      description: 'Non-disclosure triggers manual review flag',
    },
  ],
};

// =============================================================================
// SCENARIO 7 — Affordability crisis — reduce cover
// =============================================================================

const s7: TestCase = {
  name: 'SCENARIO-7: Premium unaffordable, no shortfall — reduce cover',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 48,
      smoker: true,
      occupationClass: OccupationClass.CLASS_2_LIGHT_BLUE,
      employmentType: EmploymentType.EMPLOYED_PART_TIME,
      annualGrossIncome: 45_000,
      annualNetIncome: 36_000,
      hasPartner: false,
      numberOfDependants: 0,
      mortgageBalance: 0,
      liquidAssets: 40_000,
      existingLifeCoverSumInsured: 500_000,
      existingTPDCoverSumInsured: 300_000,
      yearsToRetirement: 17,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'CommInsure',
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 500_000,
      tpdSumInsured: 300_000,
      tpdDefinition: TPDDefinitionType.ANY_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      annualPremium: 4_500,
      hasLoadings: false,
      hasExclusions: false,
    },
    health: { existingMedicalConditions: [], pendingInvestigations: false },
    goals: { affordabilityIsConcern: true, wantsRetention: true },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.REDUCE_COVER,
      description: 'Premiums > 10% of income (smoker, part-time), no shortfall → reduce cover',
    },
  ],
};

// =============================================================================
// SCENARIO 8 — TPD definition worsens in new policy — replacement blocked
// =============================================================================

const s8: TestCase = {
  name: 'SCENARIO-8: New policy worsens TPD definition — replacement blocked',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 40,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      annualGrossIncome: 130_000,
      annualNetIncome: 95_000,
      mortgageBalance: 500_000,
      liquidAssets: 60_000,
      yearsToRetirement: 25,
      existingLifeCoverSumInsured: 1_000_000,
      existingTPDCoverSumInsured: 1_000_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'BT',
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 1_000_000,
      tpdSumInsured: 1_000_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.STEPPED,
      annualPremium: 4_000,
      hasLoadings: false,
      hasExclusions: false,
    },
    health: { existingMedicalConditions: [], pendingInvestigations: false },
    goals: { wantsReplacement: true },
    newPolicyCandidate: {
      insurer: 'ClearView',
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 1_000_000,
      tpdSumInsured: 1_000_000,
      tpdDefinition: TPDDefinitionType.ANY_OCCUPATION, // WORSE than existing own occupation
      premiumStructure: PremiumStructure.STEPPED,
      projectedAnnualPremium: 3_600,
      underwritingStatus: 'ACCEPTED_STANDARD',
    },
  },
  assertions: [
    {
      path: 'recommendation.comparison.tpdDefinitionChange',
      expected: 'WORSENED',
      description: 'TPD definition change from own to any occupation = WORSENED',
    },
  ],
};

// =============================================================================
// SCENARIO 9 — Grandfathered terms, retain despite lower premium elsewhere
// =============================================================================

const s9: TestCase = {
  name: 'SCENARIO-9: Grandfathered terms on existing policy — retain',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      age: 52,
      smoker: false,
      occupationClass: OccupationClass.CLASS_1_WHITE_COLLAR,
      annualGrossIncome: 200_000,
      annualNetIncome: 140_000,
      mortgageBalance: 0,
      liquidAssets: 300_000,
      yearsToRetirement: 13,
      existingLifeCoverSumInsured: 2_000_000,
      existingTPDCoverSumInsured: 1_500_000,
    },
    existingPolicy: {
      hasExistingPolicy: true,
      insurer: 'MLC Legacy',
      coverTypes: [CoverType.LIFE, CoverType.TPD],
      lifeSumInsured: 2_000_000,
      tpdSumInsured: 1_500_000,
      tpdDefinition: TPDDefinitionType.OWN_OCCUPATION,
      premiumStructure: PremiumStructure.LEVEL,
      annualPremium: 8_000,
      hasLoadings: false,
      hasExclusions: false,
      hasSuperiorGrandfatheredTerms: true,
    },
    health: {
      existingMedicalConditions: ['Hypertension — controlled'],
      pendingInvestigations: false,
    },
    goals: { wantsReplacement: false, prioritisesDefinitionQuality: true },
  },
  assertions: [
    {
      path: 'recommendation.type',
      expected: RecommendationType.RETAIN_EXISTING,
      description: 'No shortfall, grandfathered terms, health deterioration → retain',
    },
  ],
};

// =============================================================================
// SCENARIO 10 — Missing critical data — defer no action
// =============================================================================

const s10: TestCase = {
  name: 'SCENARIO-10: Missing critical data — defer',
  input: {
    adviceMode: AdviceMode.PERSONAL_ADVICE,
    evaluationDate: '2026-03-20',
    client: {
      // age and income missing deliberately
      smoker: false,
    },
    existingPolicy: {
      // hasExistingPolicy missing
    },
  },
  assertions: [
    {
      path: 'validation.isValid',
      expected: false,
      description: 'Missing mandatory fields → validation fails',
    },
    {
      path: 'recommendation.type',
      expected: RecommendationType.DEFER_NO_ACTION,
      description: 'Failed validation → defer',
    },
  ],
};

// =============================================================================
// TEST RUNNER
// =============================================================================

export const ALL_TEST_CASES = [s1, s2, s3, s4, s5, s6, s7, s8, s9, s10];

export function runAllTests(): void {
  console.log('\n=== purchaseRetainLifeTPDPolicy — Test Suite ===\n');
  let passed = 0;
  let failed = 0;
  for (const tc of ALL_TEST_CASES) {
    const r = runTest(tc);
    if (r.passed) {
      console.log(`  ✓ ${r.name}`);
      passed++;
    } else {
      console.log(`  ✗ ${r.name}`);
      r.failures.forEach((f) => console.log(f));
      failed++;
    }
  }
  console.log(`\n${passed + failed} tests | ${passed} passed | ${failed} failed\n`);
  if (failed > 0) process.exit(1);
}

export function getScenarioResult(index: number): PurchaseRetainLifeTPDPolicyOutput {
  const tc = ALL_TEST_CASES[index];
  if (!tc) throw new Error(`No scenario at index ${index}`);
  return runPurchaseRetainLifeTPDPolicyWorkflow(tc.input);
}

if (require.main === module) {
  runAllTests();
}
