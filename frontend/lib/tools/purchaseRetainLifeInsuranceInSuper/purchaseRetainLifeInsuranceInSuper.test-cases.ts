// =============================================================================
// TEST CASES — purchaseRetainLifeInsuranceInSuper
//
// Each scenario represents a realistic Australian super insurance situation.
// Run with: npx ts-node purchaseRetainLifeInsuranceInSuper.test-cases.ts
//
// These are functional test cases — they call the engine and assert expected
// outcomes. No test framework dependency is required; a simple runner is
// included at the bottom.
// =============================================================================

import {
  AdviceMode,
  BeneficiaryCategory,
  EmploymentStatus,
  FundType,
  LegalStatus,
  PlacementRecommendation,
  ProductType,
} from './purchaseRetainLifeInsuranceInSuper.enums';
import type { PurchaseRetainLifeInsuranceInSuperOutput } from './purchaseRetainLifeInsuranceInSuper.types';
import { runPurchaseRetainLifeInsuranceInSuperWorkflow } from './purchaseRetainLifeInsuranceInSuper.engine';

// ---------------------------------------------------------------------------
// Test harness
// ---------------------------------------------------------------------------

interface TestCase {
  name: string;
  description: string;
  input: Parameters<typeof runPurchaseRetainLifeInsuranceInSuperWorkflow>[0];
  assertions: Array<{
    field: keyof PurchaseRetainLifeInsuranceInSuperOutput | string;
    expected: unknown;
    description: string;
  }>;
}

function runTestCase(tc: TestCase): { name: string; passed: boolean; failures: string[] } {
  const result = runPurchaseRetainLifeInsuranceInSuperWorkflow(tc.input);
  const failures: string[] = [];

  for (const assertion of tc.assertions) {
    // Support dot-notation for nested paths
    const actual = assertion.field
      .split('.')
      .reduce((obj: unknown, key) => (obj as Record<string, unknown>)?.[key], result);

    if (actual !== assertion.expected) {
      failures.push(
        `  FAIL [${assertion.field}]: expected "${String(assertion.expected)}", got "${String(actual)}" — ${assertion.description}`,
      );
    }
  }

  return { name: tc.name, passed: failures.length === 0, failures };
}

// =============================================================================
// SCENARIO 1 — Young MySuper member under 25, new job, no opt-in
// =============================================================================

const scenario1: TestCase = {
  name: 'SCENARIO-1: Under-25 MySuper member, no opt-in',
  description:
    'A 22-year-old joins a MySuper fund for the first time. No opt-in election has been lodged. ' +
    'Under the PYS under-25 rule, default insurance cannot be provided without an opt-in direction.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 22,
      employmentStatus: EmploymentStatus.EMPLOYED_FULL_TIME,
      annualIncome: 55_000,
      marginalTaxRate: 0.19,
      hasDependants: false,
      beneficiaryTypeExpected: BeneficiaryCategory.NON_DEPENDANT_ADULT,
      cashflowPressure: true,
      retirementPriorityHigh: false,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2026-01-15',
      accountBalance: 3_200,
      hadBalanceGe6000OnOrAfter2019_11_01: false,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: {
      optedInToRetainInsurance: false,
    },
    adviceContext: {
      estimatedAnnualPremium: 300,
      yearsToRetirement: 43,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 600,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_BUT_OPT_IN_REQUIRED,
      description: 'Under-25 on MySuper without opt-in requires an election',
    },
    {
      field: 'adviceReadiness',
      expected: AdviceMode.GENERAL_GUIDANCE,
      description: 'Some strategic facts present but not all five groups',
    },
  ],
};

// =============================================================================
// SCENARIO 2 — Low-balance member with grandfathered balance (prior >= $6,000)
// =============================================================================

const scenario2: TestCase = {
  name: 'SCENARIO-2: Low balance but grandfathered (had >= $6,000 after Nov 2019)',
  description:
    'A 34-year-old has a balance of $4,200 but the account previously held $11,500 after 1 Nov 2019. ' +
    'The low-balance trigger does not fire due to grandfathering.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 34,
      annualIncome: 62_000,
      marginalTaxRate: 0.325,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: false,
      retirementPriorityHigh: false,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2018-06-01',
      accountBalance: 4_200,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER, ProductType.TOTAL_AND_PERMANENT_DISABILITY],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 480,
      yearsToRetirement: 31,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 1_200,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Grandfathering protects from low-balance trigger',
    },
  ],
};

// =============================================================================
// SCENARIO 3 — Inactive account > 16 months, no opt-in
// =============================================================================

const scenario3: TestCase = {
  name: 'SCENARIO-3: Inactive 20 months, no opt-in, no exception',
  description:
    'A 45-year-old has not received any contributions for 20 months. No opt-in election. ' +
    'The inactivity switch-off rule fires and no exception applies.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 45,
      annualIncome: 90_000,
      marginalTaxRate: 0.325,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2010-01-01',
      accountBalance: 45_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      lastAmountReceivedDate: '2024-07-10', // ~20 months before eval date
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 800,
      yearsToRetirement: 20,
      assumedGrowthRate: 0.07,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.MUST_BE_SWITCHED_OFF,
      description: 'Inactivity trigger fires and no override exists',
    },
    {
      field: 'placementAssessment.recommendation',
      expected: PlacementRecommendation.OUTSIDE_SUPER,
      description: 'Legal block forces OUTSIDE_SUPER placement',
    },
  ],
};

// =============================================================================
// SCENARIO 4 — Inactive account with valid opt-in election
// =============================================================================

const scenario4: TestCase = {
  name: 'SCENARIO-4: Inactive 20 months but valid opt-in election on file',
  description:
    'Same as Scenario 3, but the member lodged a written opt-in direction before the ' +
    '16-month threshold was reached. Inactivity trigger is overridden by the election.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 45,
      annualIncome: 90_000,
      marginalTaxRate: 0.325,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: false,
      retirementPriorityHigh: false,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2010-01-01',
      accountBalance: 45_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      lastAmountReceivedDate: '2024-07-10',
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: {
      optedInToRetainInsurance: true,
      optInElectionDate: '2024-09-01', // lodged before the 16-month mark
    },
    adviceContext: {
      estimatedAnnualPremium: 800,
      yearsToRetirement: 20,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 2_000,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Opt-in election overrides inactivity trigger',
    },
  ],
};

// =============================================================================
// SCENARIO 5 — Dangerous occupation exception
// =============================================================================

const scenario5: TestCase = {
  name: 'SCENARIO-5: Dangerous occupation election in force',
  description:
    'A 38-year-old miner. Account inactive for 18 months. ' +
    'A dangerous occupation election is registered and in force — overrides the inactivity trigger.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 38,
      occupation: 'Underground Mining Operator',
      annualIncome: 130_000,
      marginalTaxRate: 0.37,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: false,
      retirementPriorityHigh: false,
    },
    fund: {
      fundType: FundType.MYSUPER,
      hasDangerousOccupationElection: true,
      dangerousOccupationElectionInForce: true,
    },
    product: {
      productStartDate: '2012-03-01',
      accountBalance: 85_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      lastAmountReceivedDate: '2024-09-01',
      coverTypesPresent: [ProductType.DEATH_COVER, ProductType.TOTAL_AND_PERMANENT_DISABILITY],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 2_400,
      yearsToRetirement: 27,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 3_500,
      needForPolicyFlexibility: false,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Dangerous occupation exception overrides inactivity trigger',
    },
  ],
};

// =============================================================================
// SCENARIO 6 — Employer-sponsored exception
// =============================================================================

const scenario6: TestCase = {
  name: 'SCENARIO-6: Employer-sponsored contribution exception (SIS s68AAA(4A))',
  description:
    'A 31-year-old with 17 months inactivity. The employer has lodged written notification ' +
    'and contributions exceed SG minimum by the insurance fee. Both conditions met.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 31,
      annualIncome: 72_000,
      marginalTaxRate: 0.325,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
    },
    fund: { fundType: FundType.CHOICE },
    product: {
      productStartDate: '2017-08-01',
      accountBalance: 22_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      lastAmountReceivedDate: '2024-10-01',
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    employerException: {
      employerHasNotifiedTrusteeInWriting: true,
      employerContributionsExceedSGMinimumByInsuranceFeeAmount: true,
    },
    adviceContext: {
      estimatedAnnualPremium: 600,
      yearsToRetirement: 34,
      assumedGrowthRate: 0.07,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Employer-sponsored exception overrides inactivity trigger',
    },
  ],
};

// =============================================================================
// SCENARIO 7 — Small fund carve-out (SMSF)
// =============================================================================

const scenario7: TestCase = {
  name: 'SCENARIO-7: SMSF — small fund carve-out',
  description:
    'A 55-year-old SMSF trustee/member with death cover inside their SMSF. ' +
    'Account inactive for 22 months. PYS switch-off rules do not apply to SMSFs.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 55,
      annualIncome: 180_000,
      marginalTaxRate: 0.45,
      hasDependants: false,
      beneficiaryTypeExpected: BeneficiaryCategory.NON_DEPENDANT_ADULT,
      retirementPriorityHigh: true,
      wantsEstateControl: true,
    },
    fund: {
      fundType: FundType.SMSF,
      fundMemberCount: 2,
    },
    product: {
      productStartDate: '2008-07-01',
      accountBalance: 920_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      lastAmountReceivedDate: '2024-05-01',
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 8_500,
      yearsToRetirement: 10,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 5_000,
      needForPolicyFlexibility: true,
      preferredBeneficiaryCategory: BeneficiaryCategory.NON_DEPENDANT_ADULT,
      retirementPriorityHigh: true,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'SMSF carve-out overrides inactivity trigger',
    },
  ],
};

// =============================================================================
// SCENARIO 8 — Legacy pre-2014 ambiguous cover
// =============================================================================

const scenario8: TestCase = {
  name: 'SCENARIO-8: Legacy pre-2014 cover with non-standard features',
  description:
    'A 51-year-old has an old trauma-style product inside super that commenced before 2014 ' +
    'and has legacy non-standard features. The engine must not auto-reject — it routes to COMPLEX review.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 51,
      annualIncome: 95_000,
      marginalTaxRate: 0.37,
      hasDependants: true,
    },
    fund: { fundType: FundType.CHOICE },
    product: {
      productStartDate: '2006-04-01',
      accountBalance: 180_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER, ProductType.TRAUMA],
      coverCommencedBefore2014: true,
      legacyNonStandardFeatureFlag: true,
    },
    elections: { optedInToRetainInsurance: false },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.COMPLEX_RIGHTS_CHECK_REQUIRED,
      description: 'Legacy non-standard cover requires manual review rather than auto-rejection',
    },
  ],
};

// =============================================================================
// SCENARIO 9 — Beneficiary tax-risk-heavy case
// =============================================================================

const scenario9: TestCase = {
  name: 'SCENARIO-9: Non-dependant adult beneficiary — high tax risk, outside super preferred',
  description:
    'A 48-year-old with $1.5M death cover inside super, intending to leave proceeds to an ' +
    'adult non-dependant child. 17% tax on the full taxable component is a major risk. ' +
    'The placement engine should strongly recommend outside super.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 48,
      annualIncome: 200_000,
      marginalTaxRate: 0.45,
      hasDependants: false,
      beneficiaryTypeExpected: BeneficiaryCategory.NON_DEPENDANT_ADULT,
      cashflowPressure: false,
      retirementPriorityHigh: true,
      wantsEstateControl: true,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2005-01-01',
      accountBalance: 650_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 12_000,
      yearsToRetirement: 17,
      assumedGrowthRate: 0.07,
      preferredBeneficiaryCategory: BeneficiaryCategory.NON_DEPENDANT_ADULT,
      needForPolicyFlexibility: true,
      needForPolicyOwnershipOutsideTrusteeControl: true,
      retirementPriorityHigh: true,
      contributionCapPressure: true,
      concessionalContributionsAlreadyHigh: true,
      currentMonthlySurplusAfterExpenses: 8_000,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Cover is legally permitted and active',
    },
    {
      field: 'placementAssessment.recommendation',
      expected: PlacementRecommendation.OUTSIDE_SUPER,
      description:
        'Non-dependant beneficiary, flexibility needs, and retirement priority all push strongly toward outside super',
    },
    {
      field: 'beneficiaryTaxRisk.riskLevel',
      expected: 'CRITICAL',
      description: 'Non-dependant adult beneficiary = CRITICAL tax risk',
    },
  ],
};

// =============================================================================
// SCENARIO 10 — High cashflow pressure, inside super is the relief valve
// =============================================================================

const scenario10: TestCase = {
  name: 'SCENARIO-10: High cashflow pressure — inside super strongly preferred',
  description:
    'A 33-year-old single parent with significant cashflow pressure. ' +
    'Dependant child is the intended beneficiary. ' +
    'The premium is a major percentage of monthly surplus. Inside super relieves this.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 33,
      annualIncome: 52_000,
      marginalTaxRate: 0.19,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: true,
      retirementPriorityHigh: false,
      wantsAffordability: true,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2015-03-01',
      accountBalance: 28_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 1_200,
      yearsToRetirement: 32,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 350, // $100/month premium = 29% of surplus
      preferredBeneficiaryCategory: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      needForPolicyFlexibility: false,
      contributionCapPressure: false,
      retirementPriorityHigh: false,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Cover is active and permitted',
    },
    {
      field: 'placementAssessment.recommendation',
      expected: PlacementRecommendation.INSIDE_SUPER,
      description: 'High cashflow pressure and dependant beneficiary favours inside super',
    },
  ],
};

// =============================================================================
// SCENARIO 11 — High retirement priority, near retirement — outside super wins
// =============================================================================

const scenario11: TestCase = {
  name: 'SCENARIO-11: Near retirement, high balance priority — outside super preferred',
  description:
    'A 58-year-old with 7 years to retirement, high super balance adequacy concerns, ' +
    'and a dependant spouse beneficiary. The premium drag over the remaining period is material. ' +
    'Outside super is preferred to protect the retirement balance.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 58,
      annualIncome: 140_000,
      marginalTaxRate: 0.37,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: false,
      retirementPriorityHigh: true,
    },
    fund: { fundType: FundType.MYSUPER },
    product: {
      productStartDate: '2000-01-01',
      accountBalance: 420_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 9_500,
      yearsToRetirement: 7,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 5_000,
      preferredBeneficiaryCategory: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      needForPolicyFlexibility: false,
      retirementPriorityHigh: true,
      superBalanceAdequacy: 'low',
      contributionCapPressure: true,
      concessionalContributionsAlreadyHigh: true,
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Cover is legally active',
    },
    {
      field: 'placementAssessment.recommendation',
      expected: PlacementRecommendation.OUTSIDE_SUPER,
      description: 'High retirement priority, near retirement, and contribution pressure push toward outside super',
    },
  ],
};

// =============================================================================
// SCENARIO 12 — Split strategy case (mixed signals)
// =============================================================================

const scenario12: TestCase = {
  name: 'SCENARIO-12: Split strategy — mixed benefit and penalty signals',
  description:
    'A 40-year-old with moderate cashflow pressure, a spouse beneficiary (low tax risk), ' +
    'moderate retirement horizon, but some need for flexibility. ' +
    'Neither inside nor outside is dominant — split strategy is the output.',
  input: {
    evaluationDate: '2026-03-20',
    member: {
      age: 40,
      annualIncome: 100_000,
      marginalTaxRate: 0.325,
      hasDependants: true,
      beneficiaryTypeExpected: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      cashflowPressure: true,
      retirementPriorityHigh: false,
      wantsAffordability: true,
    },
    fund: { fundType: FundType.CHOICE },
    product: {
      productStartDate: '2012-07-01',
      accountBalance: 95_000,
      hadBalanceGe6000OnOrAfter2019_11_01: true,
      receivedAmountInLast16Months: true,
      coverTypesPresent: [ProductType.DEATH_COVER, ProductType.TOTAL_AND_PERMANENT_DISABILITY],
    },
    elections: { optedInToRetainInsurance: false },
    adviceContext: {
      estimatedAnnualPremium: 3_200,
      yearsToRetirement: 25,
      assumedGrowthRate: 0.07,
      currentMonthlySurplusAfterExpenses: 1_800,
      preferredBeneficiaryCategory: BeneficiaryCategory.DEPENDANT_SPOUSE_OR_CHILD,
      needForPolicyFlexibility: true,
      needForOwnOccupationStyleDefinitions: true,
      retirementPriorityHigh: false,
      contributionCapPressure: false,
      superBalanceAdequacy: 'adequate',
    },
  },
  assertions: [
    {
      field: 'legalStatus',
      expected: LegalStatus.ALLOWED_AND_ACTIVE,
      description: 'Cover is legally active',
    },
    {
      field: 'placementAssessment.recommendation',
      expected: PlacementRecommendation.SPLIT_STRATEGY,
      description: 'Mixed signals — cashflow pressure favours inside, flexibility needs favour outside → split',
    },
    {
      field: 'adviceReadiness',
      expected: AdviceMode.PERSONAL_ADVICE_READY,
      description: 'All five strategic fact groups present',
    },
  ],
};

// =============================================================================
// TEST RUNNER
// =============================================================================

export const ALL_TEST_CASES: TestCase[] = [
  scenario1,
  scenario2,
  scenario3,
  scenario4,
  scenario5,
  scenario6,
  scenario7,
  scenario8,
  scenario9,
  scenario10,
  scenario11,
  scenario12,
];

export function runAllTests(): void {
  console.log('\n=== purchaseRetainLifeInsuranceInSuper — Test Suite ===\n');

  let passed = 0;
  let failed = 0;

  for (const tc of ALL_TEST_CASES) {
    const result = runTestCase(tc);
    if (result.passed) {
      console.log(`  ✓ ${result.name}`);
      passed++;
    } else {
      console.log(`  ✗ ${result.name}`);
      for (const f of result.failures) {
        console.log(f);
      }
      failed++;
    }
  }

  console.log(`\n${passed + failed} tests | ${passed} passed | ${failed} failed\n`);

  if (failed > 0) {
    process.exit(1);
  }
}

/** Export individual scenario results for programmatic inspection. */
export function getScenarioResult(
  scenarioIndex: number,
): PurchaseRetainLifeInsuranceInSuperOutput {
  const tc = ALL_TEST_CASES[scenarioIndex];
  if (!tc) throw new Error(`No scenario at index ${scenarioIndex}`);
  return runPurchaseRetainLifeInsuranceInSuperWorkflow(tc.input);
}

// Run when executed directly
if (require.main === module) {
  runAllTests();
}
