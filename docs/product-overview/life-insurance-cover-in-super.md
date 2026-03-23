# Life Insurance Cover in Superannuation

**Tool module:** `frontend/lib/tools/purchaseRetainLifeInsuranceInSuper/`
**Entry point:** `purchaseRetainLifeInsuranceInSuper.engine.ts` → `runPurchaseRetainLifeInsuranceInSuperWorkflow()`
**Engine version:** 1.0.0
**Legislation as of:** 2026-03-20

---

## Business Purpose

This tool answers a precise legal and strategic question for Australian financial advice:

> Can life insurance legally exist inside this member's superannuation fund, and is it strategically beneficial to keep it there?

It covers two distinct layers:

1. **Legal permissibility** — Is the cover type permitted under the Superannuation Industry (Supervision) Act 1993 (Cth) ("SIS Act")? Have any of the three Protecting Your Super (PYS) switch-off rules been triggered? Does a statutory exception override those rules? Can the member elect to retain cover?

2. **Strategic placement** — Is inside-super the better structural home for this cover versus holding it outside super? This is a scoring-based analysis that weighs cashflow, tax-funding, and convenience benefits against retirement-balance erosion, beneficiary tax risk, and flexibility limitations.

---

## User Problem It Solves

Australian super fund members face a complex web of rules that can automatically cancel their insurance without them knowing — the PYS "switch-off" rules introduced in 2019. At the same time, holding insurance inside super has real strategic trade-offs that are not well understood.

This tool:
- tells the member or adviser whether the insurance is currently legal and active, or whether action is needed
- surfaces statutory exceptions that override switch-off rules
- calculates an evidence-based placement recommendation (inside vs outside vs split)
- generates the precise missing-information questions needed to reach that decision
- produces an auditable rule trace for every decision made

---

## Key Inputs

### Member
- Age and/or date of birth
- Employment status and occupation
- Annual income and marginal tax rate
- Dependants and expected beneficiary type
- Cashflow pressure and retirement priority flags
- Preferences (wants inside super, wants affordability, wants estate control)

### Fund
- Fund type: MySuper / choice / SMSF / small APRA / defined benefit
- Fund member count
- ADF/Commonwealth exception flag
- Dangerous occupation election status
- Successor fund transfer occurred flag

### Product
- Product start date
- Account balance
- Whether balance was ≥ $6,000 on or after 1 November 2019 (grandfathering)
- Date of last contribution/rollover, or inactivity flag
- Cover types present (death, terminal illness, TPD, IP)
- Legacy/pre-2014 flags
- Fixed-term or fully-paid policy flags

### Elections
- Opt-in to retain insurance (with date)
- Opt-out of insurance
- Successor fund election carryover and equivalent rights confirmation

### Employer Exception
- Written notification to trustee
- Contributions exceeding SG minimum by insurance fee amount

### Advice Context
- Estimated annual premium
- Years to retirement and assumed growth rate
- Monthly surplus, contribution cap pressure
- Preferred beneficiary category
- Flexibility and ownership needs

---

## Decision Outputs (Legal Status)

| Status | Meaning |
|---|---|
| `ALLOWED_AND_ACTIVE` | Cover is permitted; no unresolved switch-off trigger |
| `ALLOWED_BUT_OPT_IN_REQUIRED` | Under-25 rule applies; member must lodge opt-in direction |
| `MUST_BE_SWITCHED_OFF` | Inactivity or low-balance trigger fired; no exception or election overrides it |
| `NOT_ALLOWED_IN_SUPER` | Cover type is not a permitted insured event under SIS s67A |
| `TRANSITIONAL_REVIEW_REQUIRED` | Legacy or pre-reform cover; cannot auto-resolve |
| `COMPLEX_RIGHTS_CHECK_REQUIRED` | Successor transfer, fixed-term, or legacy non-standard features present |
| `NEEDS_MORE_INFO` | Critical facts are missing; cannot determine status |

---

## Placement Recommendation

| Recommendation | Meaning |
|---|---|
| `INSIDE_SUPER` | Benefits outweigh penalties; inside super is the better structural home |
| `OUTSIDE_SUPER` | Penalties dominate; outside super is preferred |
| `SPLIT_STRATEGY` | Mixed signals; part inside and part outside is optimal |
| `INSUFFICIENT_INFO` | Too few strategic facts to score |

---

## Logic Flow (High Level)

```
Input → Normalize → Validate
           ↓
    R-001: Permitted cover type? (SIS s67A)
           ↓
    R-002: Legacy / transitional indicators?
           ↓
    R-007: Member opted out? → MUST_BE_SWITCHED_OFF
           ↓
    R-004: Inactivity rule (16 months)
    R-005: Low-balance rule ($6,000)
    R-006: Under-25 rule
           ↓
    E-001..E-007: Exceptions (small fund, DB, ADF, employer, dangerous occ, SFT, rights-not-affected)
           ↓
    Apply exception overrides to each trigger
    Apply election overrides to each trigger
           ↓
    R-008: Resolve final LegalStatus
           ↓
    Calculations: retirement drag, cashflow metrics, tax-funding metric, placement scores
           ↓
    P-001: Placement engine (weighted net score → INSIDE / OUTSIDE / SPLIT)
           ↓
    A-001: Advice readiness (FACTUAL_ONLY / GENERAL_GUIDANCE / PERSONAL_ADVICE_READY)
           ↓
    Member action generation
           ↓
    Final output assembly
```

---

## Switch-Off Rules (Protecting Your Super)

### 1. Inactivity Rule (SIS s68AAA(1)(a))
Triggered if no contribution or rollover has been credited to the account for 16 consecutive months.
- Overridden by: member opt-in election, employer exception, dangerous occupation exception, ADF exception, defined benefit exception, small fund carve-out.

### 2. Low-Balance Rule (SIS s68AAA(1)(b))
Triggered if account balance is below $6,000.
- Does NOT trigger if the account held ≥ $6,000 on or after 1 November 2019 (grandfathering).
- Overridden by: same exceptions as inactivity rule.

### 3. Under-25 Rule (SIS s68AAA(3))
MySuper trustees must not provide **default** insurance to members under 25 without a member opt-in direction.
- Not a "switch-off" in the traditional sense — it prevents default provision.
- Result: `ALLOWED_BUT_OPT_IN_REQUIRED` (member can elect to activate cover).
- Only overridden by the member's own opt-in election (not employer exception or dangerous occupation).

---

## Statutory Exceptions

| Exception | Trigger condition |
|---|---|
| Small Fund Carve-Out | SMSF or small APRA fund (≤ 6 members) — s68AAA does not apply to RSE-exempt funds |
| Defined Benefit | Insurance embedded in benefit formula; s68AAA premium-deduction rules do not engage |
| ADF/Commonwealth | Commonwealth legislative frameworks may displace PYS obligations |
| Employer-Sponsored Contribution | Employer written notification + contributions exceed SG minimum by insurance fee amount (s68AAA(4A)) |
| Dangerous Occupation | Member election registered and in force |
| Successor Fund Transfer | Transfer occurred + equivalent rights confirmed by successor trustee |
| Rights Not Affected | Fixed-term or fully-paid cover — no ongoing premium charged, so s68AAA is not engaged |

---

## Strategic Placement Scoring

Benefits scored 0–100 each:
- **Cashflow benefit** (weight 25%) — premiums funded from super reduce personal after-tax burden
- **Tax-funding benefit** (weight 20%) — concessional contributions taxed at 15% vs marginal rate
- **Convenience** (weight 10%) — easy default access, trustee-managed
- **Structural protection** (weight 5%) — some creditor-protection characteristics

Penalties scored 0–100 each:
- **Retirement erosion** (weight 20%) — premium drain reduces compounding super balance
- **Beneficiary tax risk** (weight 10%) — non-dependant beneficiaries pay up to 17% tax on taxable component
- **Flexibility/control** (weight 5%) — trustee-controlled definitions, limited own-occupation TPD
- **Contribution cap pressure** (weight 5%) — competes with retirement savings contributions

Net inside-super score = (weighted benefits) − (weighted penalties), normalised 0–100.

---

## Advice Readiness

| Mode | Condition |
|---|---|
| `NEEDS_MORE_INFO` | Blocking legal facts are absent |
| `FACTUAL_ONLY` | Legal facts complete; no strategic facts |
| `GENERAL_GUIDANCE` | Legal facts + 1–4 strategic fact groups |
| `PERSONAL_ADVICE_READY` | All 5 strategic fact groups present |

Strategic fact groups: beneficiary, cashflow, retirement horizon, flexibility needs, tax rate.

---

## Beneficiary Tax Risk

Death benefits paid inside super to non-dependant adults are subject to **15% + 2% Medicare levy = 17% tax** on the taxable component (ITAA97 s302-195).
- Dependant spouse/child: tax-free
- Non-dependant adult: up to 17% tax → CRITICAL risk level
- Legal personal representative (estate): HIGH risk — depends on estate beneficiaries
- Unknown beneficiary: MEDIUM risk — flagged for clarification

---

## Law Version

- **Act:** Superannuation Industry (Supervision) Act 1993 (Cth)
- **Sections:** Part 6, Div 4 — ss 67A, 67AA, 68AAA, 68B
- **Reform:** Treasury Laws Amendment (Protecting Your Super Package) Act 2019 (Cth), commenced 1 July 2019
- **Engine evaluated against legislation as of:** 2026-03-20

---

## Risks and Caveats

1. The engine produces **deterministic structured output** — it is not a substitute for licensed financial advice. Outputs should be reviewed by a qualified adviser before being acted upon.
2. The **beneficiary tax risk** calculation assumes 100% taxable component (typical for life insurance proceeds inside super). Actual taxable vs tax-free split may vary.
3. **Stepped premium projections** in the placement score use a fixed approximation rate — actual insurer increases will vary.
4. The **grandfathering date** (1 November 2019) reflects the low-balance provision as modelled. Always verify against the current SIS Act text and relevant ATO/APRA guidance.
5. **SMSF members** are not subject to the same RSE-licensee s68AAA obligations, but are still subject to SIS s67A permitted-event restrictions.

---

## How It Fits the System

1. The frontend collects member/fund/product/election facts via a structured form.
2. The LangGraph agent in the backend calls this tool with the collected facts.
3. The tool returns a fully structured `PurchaseRetainLifeInsuranceInSuperOutput`.
4. The agent returns the output to the frontend.
5. The frontend renders the legal status, placement recommendation, missing-info questions, member actions, and rule trace.
