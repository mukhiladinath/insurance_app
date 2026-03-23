# Rules Engine — Purchase / Retain Life & TPD in Superannuation

**Module:** `purchase_retain_life_tpd_in_super`
**Rule set version:** 1.0.0
**Legislation as of:** 2026-03-23
**Parent doc:** [`docs/product-overview/life-tpd-in-super.md`](../product-overview/life-tpd-in-super.md)

---

## Design Principles

1. **Priority ordering** — rules execute in strict ID order within each tier. Lower number = higher priority.
2. **First forcing rule wins** — once a rule forces a definitive outcome (BLOCK, ALLOW, REFER), rules of the same tier do not override it.
3. **Machine-readable outputs** — every rule evaluation returns a structured object.
4. **Human-readable reasons** — every rule result includes a plain-English reason string.
5. **Legal basis metadata** — every rule stores the citation separately from the reason text. UI must never hard-code legal text.
6. **Explainability trace** — every engine run produces a full array of rule evaluations stored in ComplianceTrace.
7. **No hard-coded tax rates** — tax rate values are parameters, not constants.
8. **Overrides are explicit** — every override (exception, election) is recorded with its source ID.

---

## Rule Output Object

Every rule evaluation returns:

```json
{
  "rule_id": "R-001",
  "rule_name": "Permitted Insurance Type Inside Super",
  "tier": "ELIGIBILITY",
  "fired": true,
  "result": "BLOCK",
  "reason": "Own-occupation TPD is not a permitted insured event under super law. Redirect to outside-super option.",
  "legal_basis": "SIS Act s67A(2)",
  "override_applied": null,
  "override_source_id": null,
  "inputs_checked": { "tpd_definition": "OWN_OCCUPATION" }
}
```

---

## Tier 1 — Cover Type Eligibility Rules (R-001 to R-005)

These rules run first, before any PYS gate checks. A BLOCK at this tier is unconditional — no exception or election overrides it.

### R-001 — Permitted Insurance Type Inside Super

| Field | Value |
|---|---|
| Rule ID | R-001 |
| Tier | COVER_TYPE |
| Priority | 1 |
| Legal basis | SIS Act s67A, s67AA |

**Logic:**
- Life / death cover → ALLOW
- Terminal illness cover → ALLOW
- TPD with definition = ANY_OCCUPATION, MODIFIED_OWN_OCCUPATION, ACTIVITIES_OF_DAILY_LIVING → ALLOW
- TPD with definition = OWN_OCCUPATION → BLOCK — not a permitted event inside super
- Income protection (temporary incapacity, reasonable benefit period) → ALLOW with flag
- Trauma / critical illness → BLOCK — no consistent release condition
- Unknown TPD definition → FLAG — require clarification before assessment

**Fired result:** BLOCK | ALLOW | FLAG

---

### R-002 — Fund Exempt from PYS Rules?

| Field | Value |
|---|---|
| Rule ID | R-002 |
| Tier | COVER_TYPE |
| Priority | 2 |
| Legal basis | SIS Act s68AAA |

**Logic:**
- fund_type = SMSF → EXEMPT (skip PYS checks, proceed to underwriting tier)
- fund_type = SMALL_APRA (≤ 6 members) → EXEMPT
- fund_type = DEFINED_BENEFIT → EXEMPT
- fund_type = ADF → EXEMPT
- All other fund types → CONTINUE to PYS checks

**Fired result:** EXEMPT | CONTINUE

---

### R-003 — Member Has Opted Out

| Field | Value |
|---|---|
| Rule ID | R-003 |
| Tier | COVER_TYPE |
| Priority | 3 |
| Legal basis | SIS Act s68AAA |

**Logic:**
- Active OPT_OUT election exists for this account and cover type → BLOCK
- No opt-out → CONTINUE

**Fired result:** BLOCK | CONTINUE

---

## Tier 2 — PYS Switch-Off Gate Rules (R-010 to R-030)

These rules apply after R-001 to R-003 have passed. They may be overridden by elections or exceptions.

### R-010 — Inactivity Trigger (16 Months)

| Field | Value |
|---|---|
| Rule ID | R-010 |
| Tier | PYS_GATE |
| Priority | 10 |
| Legal basis | SIS Act s68AAA(1)(a) |

**Logic:**
- inactivity_months >= 16 → TRIGGER_FIRED
- inactivity_months < 16 → NOT_FIRED

**If TRIGGER_FIRED:** proceed to exception/election evaluation (R-050 tier)

---

### R-011 — Under-25 Trigger (MySuper only)

| Field | Value |
|---|---|
| Rule ID | R-011 |
| Tier | PYS_GATE |
| Priority | 11 |
| Legal basis | SIS Act s68AAA(3) |

**Logic:**
- fund_type = MYSUPER AND member age < 25 → TRIGGER_FIRED
- Any other condition → NOT_FIRED

**If TRIGGER_FIRED:** proceed to election evaluation — exception E-004 (employer) and E-005 (dangerous occ) do NOT override this trigger; only the member's own OPT_IN election does.

---

### R-012 — Low-Balance Trigger ($6,000)

| Field | Value |
|---|---|
| Rule ID | R-012 |
| Tier | PYS_GATE |
| Priority | 12 |
| Legal basis | SIS Act s68AAA(1)(b) |

**Logic:**
- current_balance < 6000 AND balance_ever_above_6000_since_baseline = false → TRIGGER_FIRED
- current_balance >= 6000 OR balance_ever_above_6000_since_baseline = true → NOT_FIRED

**Grandfathering note:** baseline date is 1 November 2019. If balance was ≥ $6,000 on or after that date, this trigger never fires for that account.

---

## Tier 3 — Exception and Election Override Rules (R-050 to R-070)

These rules evaluate whether a triggered PYS gate can be overridden. Only evaluated if at least one Tier 2 rule fired.

### R-050 — Small Fund or Defined Benefit Exception (E-001, E-002)

| Field | Value |
|---|---|
| Rule ID | R-050 |
| Tier | EXCEPTION |
| Priority | 50 |
| Legal basis | SIS Act s68AAA |
| Overrides | R-010, R-012 |

**Logic:**
- fund_type in [SMSF, SMALL_APRA, DEFINED_BENEFIT] → EXCEPTION_APPLIES
- (Should have been caught by R-002 — belt-and-suspenders check)

---

### R-051 — ADF / Commonwealth Exception (E-003)

| Field | Value |
|---|---|
| Rule ID | R-051 |
| Tier | EXCEPTION |
| Priority | 51 |
| Legal basis | SIS Act s68AAA |
| Overrides | R-010, R-011, R-012 |

**Logic:**
- member.is_adf_member = true AND relevant Commonwealth framework applies → EXCEPTION_APPLIES

---

### R-052 — Employer-Paid Premium Exception (E-004)

| Field | Value |
|---|---|
| Rule ID | R-052 |
| Tier | EXCEPTION |
| Priority | 52 |
| Legal basis | SIS Act s68AAA(4A) |
| Overrides | R-010, R-012 |
| Does NOT override | R-011 (under-25) |

**Logic:**
- Active EmployerPremiumNotice exists AND excess_contribution >= premium_amount → EXCEPTION_APPLIES
- If notice exists but excess_contribution < premium_amount → EXCEPTION_LAPSES

---

### R-053 — Dangerous Occupation Exception (E-005)

| Field | Value |
|---|---|
| Rule ID | R-053 |
| Tier | EXCEPTION |
| Priority | 53 |
| Legal basis | SIS Act s68AAA(4) |
| Overrides | R-010, R-012 |
| Does NOT override | R-011 (under-25) |

**Logic:**
- Active ExceptionQualification of type E-005 exists for this account → EXCEPTION_APPLIES

---

### R-054 — Successor Fund Transfer Exception (E-006)

| Field | Value |
|---|---|
| Rule ID | R-054 |
| Tier | EXCEPTION |
| Priority | 54 |
| Legal basis | SIS Act s68AAA |
| Overrides | R-010, R-011, R-012 |

**Logic:**
- Active InsuranceElection of type SFT_CARRIED_OVER exists AND successor trustee has confirmed equivalent rights → EXCEPTION_APPLIES

---

### R-055 — Rights Not Affected (E-007)

| Field | Value |
|---|---|
| Rule ID | R-055 |
| Tier | EXCEPTION |
| Priority | 55 |
| Legal basis | SIS Act s68AAA |
| Overrides | R-010, R-011, R-012 |

**Logic:**
- InsuranceCover.premium_structure = FULLY_PAID OR cover is fixed-term with no ongoing premium → EXCEPTION_APPLIES

---

### R-060 — Member Opt-In Election Override

| Field | Value |
|---|---|
| Rule ID | R-060 |
| Tier | ELECTION |
| Priority | 60 |
| Legal basis | SIS Act s68AAA |
| Overrides | R-010, R-011, R-012 (all triggers) |

**Logic:**
- Active InsuranceElection of type OPT_IN exists for this account and cover type → ELECTION_APPLIES

---

## Tier 4 — Final Eligibility Determination (R-080)

### R-080 — Resolve Final Eligibility

| Field | Value |
|---|---|
| Rule ID | R-080 |
| Tier | FINAL |
| Priority | 80 |

**Logic:**
```
if any R-001 or R-003 fired BLOCK → result = INELIGIBLE, reason = cover type or opt-out
elif all PYS triggers NOT_FIRED → result = ELIGIBLE
elif any PYS trigger FIRED:
    if any exception or election overrides ALL fired triggers → result = ELIGIBLE (with exception/election note)
    elif some triggers overridden, some not → result = PARTIALLY_OVERRIDDEN (manual review)
    else → result = INELIGIBLE (one or more triggers not overridden)
```

---

## Tier 5 — Underwriting Rules (R-090 to R-095)

### R-090 — Underwriting Required?

| Field | Value |
|---|---|
| Rule ID | R-090 |
| Tier | UNDERWRITING |
| Priority | 90 |

**Logic:**
- requested_sum_insured > automatic_acceptance_limit (AAL) → UNDERWRITING_REQUIRED
- member has a gap in cover > 90 days → UNDERWRITING_REQUIRED
- member health data triggers group policy underwriting requirements → UNDERWRITING_REQUIRED
- Otherwise → NO_UNDERWRITING_REQUIRED

---

### R-091 — Underwriting Outcome

| Field | Value |
|---|---|
| Rule ID | R-091 |
| Tier | UNDERWRITING |
| Priority | 91 |

**Logic:**
- underwriting_status = ACCEPTED → ALLOW
- underwriting_status = ACCEPTED_WITH_LOADINGS → ALLOW_WITH_CONDITIONS
- underwriting_status = ACCEPTED_WITH_EXCLUSIONS → ALLOW_WITH_CONDITIONS
- underwriting_status = DECLINED → BLOCK

---

## Tier 6 — Claims Rules (C-001 to C-020)

### C-001 — Cover Active at Claim Date

| Field | Value |
|---|---|
| Rule ID | C-001 |
| Tier | CLAIMS |
| Priority | 1 |
| Legal basis | Life Insurance Act 1995 |

**Logic:**
- InsuranceCover.cover_status = ACTIVE on event_date → ELIGIBLE_FOR_CLAIM
- Otherwise → CLAIM_INELIGIBLE — cover was not active on the event date

---

### C-002 — Claim Type Matches Cover Type

| Field | Value |
|---|---|
| Rule ID | C-002 |
| Tier | CLAIMS |
| Priority | 2 |

**Logic:**
- claim_type = DEATH AND cover_type in [LIFE, TERMINAL_ILLNESS] → MATCH
- claim_type = TPD AND cover_type = TPD → MATCH
- claim_type = TERMINAL_ILLNESS AND cover_type in [LIFE, TERMINAL_ILLNESS] → MATCH
- claim_type = TEMPORARY_INCAPACITY AND cover_type = IP → MATCH
- No match → CLAIM_INELIGIBLE

---

### C-003 — Evidence Completeness

| Field | Value |
|---|---|
| Rule ID | C-003 |
| Tier | CLAIMS |
| Priority | 3 |

**Logic:**
- Required evidence for claim type present → EVIDENCE_SUFFICIENT
- Missing required evidence → EVIDENCE_INCOMPLETE (generate missing_info_questions)

Evidence requirements per claim type:
- DEATH: death certificate + identity of dependant/LPR + beneficiary nomination
- TPD: at least 2 medical practitioner certificates + detailed medical history
- TERMINAL_ILLNESS: at least 2 medical certificates confirming life expectancy ≤ 24 months
- TEMPORARY_INCAPACITY: medical certificate + employer statement

---

## Tier 7 — Trustee Release-Condition Rules (T-001 to T-010)

### T-001 — Death Release Condition

| Field | Value |
|---|---|
| Rule ID | T-001 |
| Tier | TRUSTEE_RELEASE |
| Priority | 1 |
| Legal basis | SIS Act s62(1)(a), SIS Regs reg 6.01(1) |

**Logic:**
- Member is deceased AND claimant is a dependant OR legal personal representative → CONDITION_MET
- Claimant is neither → CONDITION_NOT_MET

---

### T-002 — Terminal Medical Condition Release Condition

| Field | Value |
|---|---|
| Rule ID | T-002 |
| Tier | TRUSTEE_RELEASE |
| Priority | 2 |
| Legal basis | SIS Act s62(1)(ba), SIS Regs reg 6.01(2) |

**Logic:**
- Two registered medical practitioners (at least one specialist) certify:
  - the member has a condition that is likely to result in death within 24 months, AND
  - the certification is current (within the required period)
- Both conditions met → CONDITION_MET
- Either missing → CONDITION_NOT_MET

---

### T-003 — Permanent Incapacity (TPD) Release Condition

| Field | Value |
|---|---|
| Rule ID | T-003 |
| Tier | TRUSTEE_RELEASE |
| Priority | 3 |
| Legal basis | SIS Act s62(1)(b), SIS Regs reg 6.01(2) |

**Logic:**
- Two registered medical practitioners certify that, in their opinion, the member is unlikely to engage in gainful employment for which they are reasonably qualified by education, training, or experience
- Both certifications present and in required form → CONDITION_MET
- One or both missing → CONDITION_NOT_MET (flag missing evidence)

**Note:** This is the super law test, not the insurer policy definition test. They may diverge.

---

### T-004 — Temporary Incapacity Release Condition

| Field | Value |
|---|---|
| Rule ID | T-004 |
| Tier | TRUSTEE_RELEASE |
| Priority | 4 |
| Legal basis | SIS Act s62(1)(c), SIS Regs reg 1.07D |

**Logic:**
- Member is temporarily unable to engage in gainful employment
- Medical evidence confirms temporary (not permanent) incapacity
- Employment would have been engaged but for the incapacity
- All present → CONDITION_MET
- Missing → CONDITION_NOT_MET

---

### T-010 — Payment Form Validation

| Field | Value |
|---|---|
| Rule ID | T-010 |
| Tier | TRUSTEE_RELEASE |
| Priority | 10 |
| Legal basis | SIS Act s65 |

**Logic:**
- Death benefit: payable as lump sum or pension to dependant/LPR
- TPD (permanent incapacity): payable as lump sum or income stream
- Temporary incapacity: payable as income stream only (not lump sum)
- Terminal illness: payable as lump sum

If payment form does not match the release condition pathway → PAYMENT_FORM_INVALID

---

## Rule Evaluation Order Summary

```
R-001  Cover type permitted?
R-002  Fund exempt from PYS?
R-003  Member opted out?
  ↓
R-010  Inactivity trigger?
R-011  Under-25 trigger?
R-012  Low-balance trigger?
  ↓ (if any triggered)
R-050  Small fund / defined benefit exception?
R-051  ADF exception?
R-052  Employer premium exception?
R-053  Dangerous occupation exception?
R-054  SFT exception?
R-055  Rights not affected exception?
R-060  Member opt-in election?
  ↓
R-080  Resolve final eligibility
  ↓
R-090  Underwriting required?
R-091  Underwriting outcome
  ↓ (on claim event)
C-001  Cover active at claim date?
C-002  Claim type matches cover type?
C-003  Evidence completeness?
  ↓
T-001  Death release condition
T-002  Terminal illness release condition
T-003  Permanent incapacity release condition
T-004  Temporary incapacity release condition
T-010  Payment form validation
```

---

## Audit Trace Format

Every engine run stores the following in ComplianceTrace:

```json
{
  "trace_id": "...",
  "tool_name": "purchase_retain_life_tpd_in_super",
  "engine_version": "1.0.0",
  "evaluated_at": "2026-03-23T10:00:00Z",
  "input_snapshot": { ... },
  "rule_evaluations": [
    {
      "rule_id": "R-001",
      "rule_name": "Permitted Insurance Type Inside Super",
      "tier": "COVER_TYPE",
      "fired": true,
      "result": "ALLOW",
      "reason": "TPD with any-occupation definition is a permitted insured event under SIS Act s67A.",
      "legal_basis": "SIS Act s67A",
      "override_applied": null,
      "override_source_id": null,
      "inputs_checked": { "cover_type": "TPD", "tpd_definition": "ANY_OCCUPATION" }
    }
  ],
  "final_eligibility": "ELIGIBLE",
  "final_reasons": ["All eligibility gates passed. No PYS triggers fired."],
  "missing_info_questions": [],
  "decision_snapshot": { ... }
}
```

---

## Conventions Shared with Tool 1 and Tool 2

| Convention | Tool 1 | Tool 2 | Tool 3 (this module) |
|---|---|---|---|
| Rule ID format | R-XXX | R-XXX | R-XXX / C-XXX / T-XXX |
| Result values | ALLOW / BLOCK / NEEDS_MORE_INFO | DEFER / REFER / PURCHASE | ELIGIBLE / INELIGIBLE / REFER |
| legal_basis field | string | string | string |
| missing_info_questions | array of {id, question, category, blocking} | array of {id, question, category, blocking} | array of {id, question, category, blocking} |
| Rule trace | array of evaluations | array of evaluations | array of evaluations |
| Engine version | 1.0.0 | 1.0.0 | 1.0.0 |
| No hardcoded tax rates | ✓ | ✓ | ✓ |
| Deterministic output | ✓ | ✓ | ✓ |
