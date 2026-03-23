# Purchase / Retain Life / TPD Policy

**Tool module:** `frontend/lib/tools/purchaseRetainLifeTPDPolicy/`
**Entry point:** `purchaseRetainLifeTPDPolicy.engine.ts` → `runPurchaseRetainLifeTPDPolicyWorkflow()`
**Engine version:** 1.0.0
**Legislation as of:** 2026-03-20

---

## Business Purpose

This tool answers a structured, multi-layered advisory question for Australian financial advice:

> Should this client purchase new life and/or TPD insurance, retain their existing policy, replace it with a better alternative, supplement it to close a coverage gap, or reduce it to manage affordability?

It covers four distinct analytical layers:

1. **Need analysis** — What is the client's quantified life and TPD insurance need based on debts, dependants, income, and assets?
2. **Policy comparison** — If a new policy candidate exists, is it materially better than the existing policy across premium, sum insured, TPD definition, exclusions, loadings, and flexibility?
3. **Risk assessment** — What underwriting risk does the client's health and occupation profile present? What replacement risk does switching carry?
4. **Hard rule application** — Which recommendation types are legally and strategically permissible given the facts? What compliance obligations attach?

---

## User Problem It Solves

Australian clients and advisers face four recurring problems when dealing with life and TPD insurance:

1. **Undercoverage** — Many clients hold insurance that was appropriate years ago but no longer reflects current debts, income, dependants, or lifestyle.
2. **Over-replacement risk** — Poorly informed replacement decisions can strip clients of grandfathered policy terms, expose them to new exclusions or loadings, or leave them uninsured during underwriting.
3. **Affordability drift** — Stepped premiums increase with age. A policy that was affordable at 35 may be unaffordable at 55 without a structured review.
4. **Compliance exposure** — Replacement of an insurance policy is a high-risk advice event under ASIC Regulatory Guide 175. Advisers must demonstrably show the new policy is better and document the decision trail.

This tool:
- quantifies the life and TPD need using standardised financial formulas
- scores existing versus new policy candidates across six weighted dimensions
- applies a strict hierarchy of blocking and positive recommendation rules
- generates an auditable rule trace for every decision
- produces all required compliance flags for adviser disclosure obligations

---

## Key Inputs

### Client Profile
- Age and/or date of birth
- Annual gross income and annual net income
- Employment type and occupation class
- Smoker status
- Whether a partner exists and partner income
- Number of dependants and age of youngest dependant
- Mortgage balance and other debts
- Liquid assets
- Years to retirement
- Existing life and TPD cover across all policies (outside the policy under review)

### Existing Policy
- Whether a policy exists
- Insurer name
- Policy ownership (self / super / business)
- Commencement date
- Cover types (Life, TPD, Trauma, IP)
- Life and TPD sum insured
- TPD definition type
- Premium structure (stepped / level / hybrid)
- Annual premium
- Whether loadings apply (and details)
- Whether exclusions apply (and details)
- Whether indexation applies
- Riders attached
- Full non-disclosure risk flag
- Superior grandfathered terms flag

### Health
- Height (cm) and weight (kg) — used to compute BMI
- Existing medical conditions
- Current medications
- Pending medical investigations (and details)
- Adverse family history conditions
- Hazardous activities
- Non-disclosure risk flag

### Client Goals
- Primary reason for review
- Whether client wants replacement or retention
- Whether affordability is a concern
- Whether client wants premium certainty
- Whether client wants own-occupation TPD definition
- Desired cover horizon
- Willingness to undergo underwriting
- Whether client prioritises definition quality and claims reputation

### New Policy Candidate (if applicable)
- Insurer name
- Policy ownership
- Cover types
- Life and TPD sum insured
- TPD definition type
- Premium structure
- Projected annual premium
- Expected loadings and exclusions
- Indexation flag
- Flexibility features / riders
- Claims quality rating
- Underwriting status (NOT_STARTED / IN_PROGRESS / ACCEPTED / DECLINED)

### Advice Mode
- `FACTUAL_INFORMATIONAL` — product facts only
- `GENERAL_ADVICE` — strategy context, no client-specific suitability
- `PERSONAL_ADVICE` — full SOA-grade output, client facts drive all conclusions

---

## Recommendation Types

| Recommendation | Meaning |
|---|---|
| `PURCHASE_NEW` | No existing cover; a net insurance need has been identified — purchase new cover |
| `RETAIN_EXISTING` | Shortfall is nil or minor; existing policy is sound — no change warranted |
| `REPLACE_EXISTING` | New policy is materially better and replacement risk is low — replace existing cover |
| `SUPPLEMENT_EXISTING` | Existing policy is kept; additional cover is needed alongside it to close the gap |
| `REDUCE_COVER` | Premiums are unaffordable; reduce sum insured on the existing policy to ease cost |
| `DEFER_NO_ACTION` | Critical facts are missing; no recommendation can be made until resolved |
| `REFER_TO_HUMAN` | Case complexity, critical underwriting risk, or non-disclosure risk requires escalation |

---

## Calculation Modules

### A — Life Insurance Need Analysis

**Formula:**
```
Gross need = debt clearance + education funding + income replacement + final expenses
Net need   = gross need − existing life cover (all policies) − liquid assets
```

**Components:**
- **Debt clearance** — mortgage balance + other debts
- **Education funding** — $50,000 per dependent child (default allowance)
- **Income replacement** — gross income × years to retirement (or 10 years if unknown) × (1 − 0.5 if partner present)
- **Final expenses** — $25,000 default (funeral, estate administration, legal fees)
- **Deductions** — existing life cover across all policies + liquid assets (assumed accessible on death)

**Shortfall levels:**

| Level | Net need range |
|---|---|
| `NONE` | ≤ $0 |
| `MINOR` | $1 – $50,000 |
| `MODERATE` | $50,001 – $200,000 |
| `SIGNIFICANT` | $200,001 – $500,000 |
| `CRITICAL` | > $500,000 |

---

### B — TPD Insurance Need Analysis

**Formula:**
```
Gross need = debt clearance + medical/rehab buffer + capitalised income replacement
             + home modification buffer + ongoing care buffer
Net need   = gross need − existing TPD cover (all policies) − liquid assets
```

**Components:**
- **Debt clearance** — mortgage balance + other debts
- **Medical / rehabilitation buffer** — $75,000 default
- **Capitalised income replacement** — present value of an annuity of annual net income (or 70% of gross if net not provided) over years to retirement at 5% discount rate
- **Home modification buffer** — $50,000 default
- **Ongoing care buffer** — $60,000 default (approx. 2 years personal care)
- **Deductions** — existing TPD cover across all policies + liquid assets

The same shortfall level thresholds as life insurance apply.

---

### C — Affordability Analysis

Premium affordability is assessed as a percentage of annual gross income:

| Band | Gross income threshold | Score |
|---|---|---|
| `COMFORTABLE` | < 1% | 90 |
| `MANAGEABLE` | 1–3% | 70 |
| `STRETCHED` | 3–5% | 45 |
| `UNAFFORDABLE` | > 5% | 20 |

Adjustments applied:
- Stepped premium projected 10 years forward at ~6% p.a. — score reduced if projection crosses upper threshold bands
- Client-flagged affordability concern — score reduced by 15 points
- Lapse risk score = 100 − affordability score

A stress-case affordability check asks whether the 10-year stepped projection remains below 7% of net income.

---

## Policy Comparison Logic

The comparison module (`purchaseRetainLifeTPDPolicy.comparison.ts`) scores the existing policy against the new candidate across six dimensions.

### Comparison Dimensions and Weights

| Dimension | Weight | Scoring basis |
|---|---|---|
| Premium | 25% | New < 95% of existing → better; new > 105% → worse |
| Life sum insured | 20% | New > 105% of existing → better; new < 95% → worse |
| TPD definition | 25% | Rank-ordered: own occ (5) > modified own (4) > any occ (3) > ADL (2) > home duties (1) > unknown (0) |
| Exclusions | 15% | Fewer exclusions on new policy → better; more exclusions → worse |
| Loadings | 10% | Fewer loadings on new policy → better; more loadings → worse |
| Flexibility / riders | 5% | More features on new policy → better; fewer → worse |

**Total must sum to 1.0.**

### Outcome Thresholds (weighted delta)

| Outcome | Weighted delta |
|---|---|
| `NEW_MATERIALLY_BETTER` | ≥ +0.15 |
| `NEW_MARGINALLY_BETTER` | +0.05 to +0.15 |
| `EQUIVALENT` | −0.05 to +0.05 |
| `NEW_MARGINALLY_WORSE` | −0.15 to −0.05 |
| `NEW_MATERIALLY_WORSE` | ≤ −0.15 |
| `INSUFFICIENT_DATA` | No candidate provided |

### Replacement Warnings

The comparison module generates automatic replacement warnings when:
- TPD definition worsens (e.g., own occupation → any occupation)
- New policy introduces exclusions not present on the existing policy
- New policy introduces loadings not present on the existing policy
- Existing policy holds superior grandfathered terms that cannot be replicated

---

## Underwriting Risk Logic

Assessed by `assessUnderwritingRisk()` in `purchaseRetainLifeTPDPolicy.underwriting.ts`.

### Risk Factors

| Factor | Risk contribution |
|---|---|
| BMI 30–35 (obese) | MEDIUM |
| BMI > 35 (severely obese) | HIGH |
| Existing medical conditions | Scored by keyword severity |
| Pending medical investigations | HIGH (outcome unknown) |
| Adverse family history | MEDIUM |
| Smoker | MEDIUM |
| Hazardous activities | MEDIUM |
| Occupation class 1 (white collar) | LOW |
| Occupation class 2 (light blue) | MEDIUM |
| Occupation class 3 (blue collar) | HIGH |
| Occupation class 4 (hazardous) | CRITICAL |
| Non-disclosure risk | CRITICAL — immediately escalates |

### Overall Risk Levels

| Level | Likely outcome |
|---|---|
| `LOW` | Standard terms expected |
| `MEDIUM` | Possible loadings or minor exclusions |
| `HIGH` | Loadings or exclusions likely |
| `CRITICAL` | Likely decline or severe loading — do not recommend replacement |

---

## Replacement Risk Logic

Assessed by `assessReplacementRisk()` in `purchaseRetainLifeTPDPolicy.underwriting.ts`. Only evaluated when an existing policy is present.

### Replacement Risk Levels

| Level | Trigger condition |
|---|---|
| `NEGLIGIBLE` | No health deterioration, no special policy terms, standard underwriting expected |
| `LOW` | Minor concerns but replacement is generally safe |
| `MODERATE` | Coverage gap likely during underwriting; client must accept the gap risk |
| `HIGH` | TPD definition worsened, or existing policy has superior grandfathered terms |
| `BLOCKING` | Non-disclosure risk present, or new underwriting not complete — replacement must not proceed |

---

## Hard Rules (Decision Engine)

Applied in strict order. **First forced recommendation wins.** Blocking rules execute before positive recommendation rules.

| Rule ID | Name | Effect |
|---|---|---|
| R-001 | Missing Critical Data | If validation errors exist → force `DEFER_NO_ACTION` |
| R-002 | Underwriting Incomplete | If new underwriting not resolved → block `REPLACE_EXISTING` |
| R-003 | Existing Policy Data Incomplete | If existing sum insured missing → block `REPLACE_EXISTING` |
| R-004 | Critical Underwriting Risk | If underwriting is CRITICAL → block `REPLACE_EXISTING`, force `REFER_TO_HUMAN` |
| R-005 | New Policy Materially Worse | If comparison outcome is worse → block `REPLACE_EXISTING` |
| R-006 | TPD Definition Worsened | If TPD definition regresses → block `REPLACE_EXISTING` |
| R-007 | Replacement Risk Blocking | If replacement risk is BLOCKING → block `REPLACE_EXISTING`, force `REFER_TO_HUMAN` |
| R-008 | Purchase New — No Coverage | If no existing policy + need exists → force `PURCHASE_NEW` |
| R-009 | Retain — Low Shortfall | If shortfall is nil/minor + no clearly better alternative → force `RETAIN_EXISTING` |
| R-010 | Supplement — Shortfall Present | If shortfall is moderate/significant + new policy not clearly better → force `SUPPLEMENT_EXISTING` |
| R-011 | Reduce Cover — Unaffordable | If premiums are unaffordable + no shortfall → force `REDUCE_COVER` |
| R-012 | Replace — Materially Better | If new policy materially better + replacement safe + not blocked → force `REPLACE_EXISTING` |
| R-013 | Refer to Human | If CRITICAL underwriting, BLOCKING replacement risk, or non-disclosure risk → force `REFER_TO_HUMAN` |

> **Rule ordering is critical.** R-013 is evaluated early (before positive rules) to catch all human-referral scenarios. Later positive rules (R-008 through R-012) only execute if no forced recommendation has been set by the blocking rules.

---

## Compliance / Disclosure Flags

Generated by `generateComplianceFlags()` in `purchaseRetainLifeTPDPolicy.compliance.ts`.

| Flag | Condition |
|---|---|
| `requiresFSG` | Any advice mode other than FACTUAL_INFORMATIONAL |
| `requiresSOA` | PERSONAL_ADVICE mode |
| `requiresGeneralAdviceWarning` | GENERAL_ADVICE mode |
| `pdsRequired` | PURCHASE_NEW, REPLACE_EXISTING, or SUPPLEMENT_EXISTING |
| `tmdCheckRequired` | Same conditions as pdsRequired (DDO obligations) |
| `antiHawkingSafe` | Always `true` — engine assumes client-initiated engagement |
| `underwritingIncomplete` | New policy underwriting is NOT_STARTED or IN_PROGRESS |
| `replacementRiskAcknowledgementRequired` | REPLACE_EXISTING recommendation or non-negligible replacement risk |
| `coolingOffExplanationRequired` | PURCHASE_NEW, REPLACE_EXISTING, or SUPPLEMENT_EXISTING |
| `manualReviewRequired` | REFER_TO_HUMAN, CRITICAL underwriting, BLOCKING replacement risk, or non-disclosure |

### Replacement Disclosure (ASIC RG 175)
When `REPLACE_EXISTING` is recommended, the compliance module generates a mandatory note requiring the adviser to document why the new policy is clearly better for the client, consistent with ASIC Regulatory Guide 175 and applicable industry codes.

---

## Decision Flow Summary

```
Input
  ↓
Normalize (safeParseDate, computeAge, defaults applied)
  ↓
Validate (Pass A: critical facts → Pass B: conditional facts → Pass C: contradictions)
  ↓
Calculate life need (debt + education + income replacement + final expenses − offsets)
Calculate TPD need  (debt + medical + PV annuity + home mod + care − offsets)
Calculate affordability (premium % income → band → score → lapse risk)
  ↓
Compare policies (if new candidate present)
  — 6 dimensions scored and weighted → weighted delta → ComparisonOutcome
  ↓
Assess underwriting risk
  — BMI, conditions, investigations, occupation, smoker, non-disclosure → overall risk level
  ↓
Assess replacement risk (if existing policy present)
  — Health deterioration, non-disclosure, grandfathered terms, TPD regression, coverage gap
  ↓
Apply rules in strict order (R-001 → R-013):
  — Blocking rules first (R-001 to R-007)
  — Positive recommendation rules (R-008 to R-012) only if no forced recommendation yet
  — First forcedRecommendation wins
  ↓
Generate compliance flags
  ↓
Generate required actions (CRITICAL → HIGH → MEDIUM priority)
  ↓
Assemble PurchaseRetainLifeTPDPolicyOutput
```

---

## Required Actions

| Action ID | Priority | Trigger |
|---|---|---|
| ACT-001 | CRITICAL | `REFER_TO_HUMAN` recommendation |
| ACT-002 | CRITICAL | Pending medical investigations present |
| ACT-003 | CRITICAL | Non-disclosure risk flagged |
| ACT-004 | HIGH | `REPLACE_EXISTING` or `SUPPLEMENT_EXISTING` — confirm new underwriting before cancelling existing |
| ACT-005 | HIGH | `PURCHASE_NEW` — obtain quotes from multiple insurers |
| ACT-006 | MEDIUM | `RETAIN_EXISTING` + superior grandfathered terms — document terms in client file |
| ACT-007 | MEDIUM | `REDUCE_COVER` — model reduced sum insured options with existing insurer first |

---

## Law Version and Regulatory Context

- **Corporations Act 2001 (Cth)** — financial product advice obligations, SOA requirements
- **ASIC Regulatory Guide 175** — replacement of insurance policies; best interests duty
- **Life Insurance Act 1995 (Cth)** — product definitions and regulatory framework
- **Treasury Laws Amendment (Design and Distribution Obligations) Act 2019 (Cth)** — TMD / DDO requirements
- **SIS Act 1993 (Cth), s67A** — TPD definitions inside super are restricted to "any occupation" or broader (own-occupation TPD not permitted inside super)
- **Engine evaluated against legislation as of:** 2026-03-20

---

## Risks and Caveats

1. The engine produces **deterministic structured output** — it is not a substitute for licensed financial advice. Outputs must be reviewed by a qualified adviser before being acted upon.
2. **Life need calculation** uses simplified assumptions (debt, dependants, income, liquid assets). It does not model superannuation balances, Centrelink entitlements, or complex estate structures — the adviser should supplement this with a full financial plan.
3. **TPD capitalisation** uses a fixed 5% real discount rate. Actual rates vary. The formula is a planning proxy, not an actuarial calculation.
4. **Stepped premium projection** uses a fixed 6% p.a. increase factor. Actual insurer age-based premium increases vary significantly by insurer, age band, and product.
5. **Underwriting risk** is assessed from structured inputs, not from a full insurance application. Actual insurer decisions may differ significantly.
6. **Replacement risk flags** are advisory — they do not guarantee that a replacement will or will not proceed. BLOCKING is a hard stop for the engine but the adviser retains ultimate professional responsibility.
7. **Non-disclosure risk** is a CRITICAL flag because it can void both the existing policy and any new policy. This scenario must always be escalated to a specialist adviser.

---

## How It Fits the System

1. The frontend collects client, health, policy, and goals facts via a structured form.
2. The LangGraph agent in the backend calls this tool with the collected facts.
3. The tool returns a fully structured `PurchaseRetainLifeTPDPolicyOutput`.
4. The agent returns the output to the frontend.
5. The frontend renders the recommendation, rule trace, compliance flags, required actions, need calculations, and policy comparison results.
