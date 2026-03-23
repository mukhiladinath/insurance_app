# Test Scenarios — Purchase / Retain Life & TPD in Superannuation

**Module:** `purchase_retain_life_tpd_in_super`
**Engine version:** 1.0.0
**Parent doc:** [`docs/product-overview/life-tpd-in-super.md`](../product-overview/life-tpd-in-super.md)
**Rules reference:** [`docs/05-rules/life-tpd-in-super-rules.md`](../05-rules/life-tpd-in-super-rules.md)

---

## Scenario Format

Each scenario includes:
- **Name** — short descriptive label
- **Inputs** — the structured facts provided to the engine
- **Expected rule result** — which rules fire and with what result
- **Expected eligibility** — ELIGIBLE | INELIGIBLE | REQUIRES_ACTION | REFER
- **Expected explanation** — plain-English reason for the outcome
- **Expected notices** — which notices should be generated
- **Expected audit events** — which audit events should be logged

---

## TS-001 — Standard eligible member, MySuper, all gates clear

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 32
- inactivity_months: 3
- current_balance: 45000
- elections: none
- exceptions: none

**Expected rule result:**
- R-001: ALLOW (life cover permitted)
- R-002: CONTINUE (not exempt)
- R-003: CONTINUE (no opt-out)
- R-010: NOT_FIRED (3 months inactive < 16)
- R-011: NOT_FIRED (age 32 ≥ 25)
- R-012: NOT_FIRED (balance $45,000 ≥ $6,000)
- R-080: ELIGIBLE

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Member passes all eligibility gates. No PYS triggers fired. Default life cover may be issued.
**Expected notices:** None required at issuance unless product rules require a welcome notice.
**Expected audit events:** ELIGIBILITY_ASSESSED, COVER_ISSUED

---

## TS-002 — Inactive account, no election, no exception → cover must cease

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 40
- inactivity_months: 18
- current_balance: 12000
- elections: none
- exceptions: none

**Expected rule result:**
- R-001: ALLOW
- R-002: CONTINUE
- R-003: CONTINUE
- R-010: TRIGGER_FIRED (18 months ≥ 16)
- R-050 to R-060: none apply
- R-080: INELIGIBLE

**Expected eligibility:** INELIGIBLE
**Expected explanation:** Account has been inactive for 18 months. No exception or opt-in election overrides this. Insurance must be ceased.
**Expected notices:** CESSATION notice to member
**Expected audit events:** ELIGIBILITY_ASSESSED, COVER_CEASED (reason: INACTIVITY)

---

## TS-003 — Inactive account, valid opt-in election → cover continues

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 40
- inactivity_months: 18
- current_balance: 12000
- elections: [{ type: OPT_IN, status: ACTIVE, cover_type: LIFE }]

**Expected rule result:**
- R-010: TRIGGER_FIRED
- R-060: ELECTION_APPLIES (OPT_IN overrides R-010)
- R-080: ELIGIBLE (trigger overridden by election)

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Account inactive for 18 months (PYS trigger fired), but a valid member opt-in election overrides this trigger. Cover continues.
**Expected notices:** None (election already recorded)
**Expected audit events:** ELIGIBILITY_ASSESSED (election noted in trace)

---

## TS-004 — Member under 25, MySuper, no election → default cover blocked

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 22
- inactivity_months: 2
- current_balance: 3500
- elections: none
- exceptions: none

**Expected rule result:**
- R-011: TRIGGER_FIRED (age 22 < 25, MySuper)
- R-012: TRIGGER_FIRED (balance $3,500 < $6,000, not grandfathered)
- No exceptions override either trigger
- R-080: INELIGIBLE

**Expected eligibility:** INELIGIBLE
**Expected explanation:** Member is under 25 (default cover prohibited without opt-in election) and account balance is below $6,000 (low-balance trigger). Member must lodge a written opt-in direction to receive insurance.
**Expected notices:** ELIGIBILITY notice explaining right to elect
**Expected audit events:** ELIGIBILITY_ASSESSED

---

## TS-005 — Member under 25, MySuper, employer premium exception → still blocked

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 22
- inactivity_months: 2
- current_balance: 3500
- exceptions: [{ type: E-004, status: ACTIVE, excess_contribution: 600, premium_amount: 450 }]

**Expected rule result:**
- R-011: TRIGGER_FIRED (under-25)
- R-052: EXCEPTION_APPLIES for inactivity/low-balance triggers BUT does not override R-011 (under-25 trigger)
- R-080: INELIGIBLE (R-011 not overridden)

**Expected eligibility:** INELIGIBLE
**Expected explanation:** Employer premium exception overrides the low-balance trigger but cannot override the under-25 trigger. Only the member's own opt-in election can override the under-25 prohibition.
**Expected notices:** ELIGIBILITY notice explaining that only member opt-in will resolve this
**Expected audit events:** ELIGIBILITY_ASSESSED

---

## TS-006 — Member turns 25 — under-25 trigger lifts

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 25 (just turned 25 today)
- inactivity_months: 1
- current_balance: 8000
- elections: none (previously blocked)

**Expected rule result:**
- R-011: NOT_FIRED (age now 25, trigger does not apply)
- R-012: NOT_FIRED (balance $8,000 ≥ $6,000)
- R-080: ELIGIBLE

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Member has turned 25. The under-25 prohibition no longer applies. Member is now eligible for default cover. Trustee should issue a notice and offer default cover.
**Expected notices:** ELIGIBILITY notice offering default cover
**Expected audit events:** ELIGIBILITY_ASSESSED, COVER_ISSUED (if default cover issued)

---

## TS-007 — Balance below $6,000, grandfathered → trigger does not apply

**Inputs:**
- fund_type: MYSUPER
- cover_type: TPD (any occupation)
- member_age: 38
- inactivity_months: 4
- current_balance: 4200
- balance_ever_above_6000_since_baseline: true (reached $8,500 in March 2020)
- elections: none

**Expected rule result:**
- R-012: NOT_FIRED (grandfathered — balance was ≥ $6,000 on or after 1 November 2019)
- R-080: ELIGIBLE

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Account balance is below $6,000 but the account is grandfathered — it held a balance at or above $6,000 after 1 November 2019. The low-balance trigger does not apply to grandfathered accounts.
**Expected notices:** None
**Expected audit events:** ELIGIBILITY_ASSESSED

---

## TS-008 — Own-occupation TPD requested inside super → blocked

**Inputs:**
- fund_type: MYSUPER
- cover_type: TPD
- tpd_definition: OWN_OCCUPATION
- member_age: 35
- inactivity_months: 0
- current_balance: 55000

**Expected rule result:**
- R-001: BLOCK (own-occupation TPD not permitted inside super)
- No further rules evaluated

**Expected eligibility:** INELIGIBLE
**Expected explanation:** Own-occupation TPD insurance is not a permitted insured event under super law (SIS Act s67A(2)). This cover cannot be held inside super. The member should be referred to the outside-super insurance module for own-occupation TPD options.
**Expected notices:** REDIRECT notice explaining outside-super option
**Expected audit events:** ELIGIBILITY_ASSESSED (BLOCKED at cover type check)

---

## TS-009 — Trauma/critical illness requested inside super → blocked

**Inputs:**
- fund_type: MYSUPER
- cover_type: TRAUMA
- member_age: 42

**Expected rule result:**
- R-001: BLOCK (trauma not a permitted insured event inside super)

**Expected eligibility:** INELIGIBLE
**Expected explanation:** Trauma / critical illness insurance does not align with any superannuation condition of release and is not a permitted insured event inside super. Must be held outside super.
**Expected notices:** REDIRECT notice
**Expected audit events:** ELIGIBILITY_ASSESSED (BLOCKED)

---

## TS-010 — SMSF member — PYS rules do not apply

**Inputs:**
- fund_type: SMSF
- cover_type: LIFE
- member_age: 55
- inactivity_months: 24 (no contributions for 2 years)
- current_balance: 350000

**Expected rule result:**
- R-002: EXEMPT (SMSF — s68AAA does not apply)
- R-010 through R-012: NOT EVALUATED
- R-080: ELIGIBLE (no PYS gates apply)

**Expected eligibility:** ELIGIBLE
**Expected explanation:** SMSF members are not subject to the Protecting Your Super switch-off rules. Eligibility is determined by the SMSF trust deed and insurer policy terms only.
**Expected notices:** None
**Expected audit events:** ELIGIBILITY_ASSESSED (exempt path noted)

---

## TS-011 — Dangerous occupation exception overrides inactivity trigger

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 34
- inactivity_months: 20
- current_balance: 15000
- exceptions: [{ type: E-005, status: ACTIVE }]

**Expected rule result:**
- R-010: TRIGGER_FIRED (20 months inactive)
- R-053: EXCEPTION_APPLIES (dangerous occupation, overrides R-010)
- R-080: ELIGIBLE (trigger overridden by exception)

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Inactivity trigger fired (20 months without contributions), but a valid dangerous occupation exception is active. Cover continues.
**Expected notices:** None
**Expected audit events:** ELIGIBILITY_ASSESSED (exception noted)

---

## TS-012 — Employer exception lapses — cover must now be re-assessed

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 40
- inactivity_months: 18
- current_balance: 5800
- exceptions: [{ type: E-004, status: ACTIVE, excess_contribution: 200, premium_amount: 450 }]

**Expected rule result:**
- R-010: TRIGGER_FIRED (inactivity)
- R-012: TRIGGER_FIRED (low balance, not grandfathered)
- R-052: EXCEPTION_LAPSES (excess $200 < premium $450 — condition not met)
- R-080: INELIGIBLE (both triggers fire, no valid exception or election)

**Expected eligibility:** INELIGIBLE
**Expected explanation:** The employer premium exception has lapsed because the employer's excess contributions no longer cover the insurance premium. Both the inactivity and low-balance triggers are now active with no override. Cover must cease unless the member lodges an opt-in election.
**Expected notices:** CESSATION notice to member + notice to employer
**Expected audit events:** EXCEPTION_EXPIRED, COVER_CEASED, NOTICE_SENT

---

## TS-013 — Successor fund transfer — election carries over

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 45
- inactivity_months: 17
- current_balance: 3500
- elections: [{ type: SFT_CARRIED_OVER, status: ACTIVE, equivalent_rights_confirmed: true }]

**Expected rule result:**
- R-010: TRIGGER_FIRED (17 months inactive)
- R-012: TRIGGER_FIRED (low balance)
- R-054: EXCEPTION_APPLIES (SFT election with confirmed equivalent rights overrides both)
- R-080: ELIGIBLE

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Both inactivity and low-balance triggers fired, but a successor fund transfer election with confirmed equivalent rights is active. Cover continues under the carried-over election.
**Expected notices:** None
**Expected audit events:** ELIGIBILITY_ASSESSED (SFT exception noted)

---

## TS-014 — Underwriting required — sum insured above AAL

**Inputs:**
- fund_type: MYSUPER
- cover_type: LIFE
- member_age: 38
- requested_sum_insured: 1500000
- automatic_acceptance_limit: 500000
- all eligibility gates clear

**Expected rule result:**
- R-080: ELIGIBLE
- R-090: UNDERWRITING_REQUIRED (requested $1.5M > AAL $500K)

**Expected eligibility:** ELIGIBLE_PENDING_UNDERWRITING
**Expected explanation:** Member is eligible for life cover. However, the requested sum insured of $1,500,000 exceeds the automatic acceptance limit of $500,000. Underwriting is required before this level of cover can be issued.
**Expected notices:** Underwriting request sent to insurer
**Expected audit events:** ELIGIBILITY_ASSESSED, UNDERWRITING_INITIATED

---

## TS-015 — Underwriting declined

**Inputs:**
- fund_type: MYSUPER
- cover_type: TPD
- member_age: 48
- underwriting_status: DECLINED
- underwriting_reason: severe pre-existing spinal condition

**Expected rule result:**
- R-091: BLOCK (underwriting declined)

**Expected eligibility:** INELIGIBLE
**Expected explanation:** The insurer has declined the underwriting application for TPD cover due to a pre-existing medical condition. Cover cannot be issued at this time. The member has the right to seek an internal review of this decision.
**Expected notices:** UNDERWRITING_RESULT notice with IDR rights
**Expected audit events:** UNDERWRITING_DECLINED, NOTICE_SENT

---

## TS-016 — Death claim — full process

**Inputs:**
- claim_type: DEATH
- event_date: [date of death]
- cover active on event date: true
- evidence: death certificate present, claimant is spouse (tax dependant)
- insurer decision: ACCEPTED
- release condition assessed: DEATH

**Expected rule result:**
- C-001: ELIGIBLE_FOR_CLAIM (cover active on event date)
- C-002: MATCH (death claim matches life cover)
- C-003: EVIDENCE_SUFFICIENT
- Insurer: ACCEPTED
- T-001: CONDITION_MET (dependant spouse confirmed)
- T-010: payment form = lump sum to dependant → VALID

**Expected eligibility:** APPROVED_PENDING_PAYMENT
**Expected explanation:** Death claim accepted by insurer. Trustee confirms death release condition is satisfied — beneficiary is a tax dependant (spouse). Lump sum payment authorised. No tax withheld (dependant recipient).
**Expected notices:** CLAIM_DECISION, BENEFIT_PAYMENT confirmation
**Expected audit events:** CLAIM_OPENED, INSURER_DECISION, TRUSTEE_DECISION, BENEFIT_PAID

---

## TS-017 — TPD claim — insurer accepts, trustee condition not met (yet)

**Inputs:**
- claim_type: TPD
- cover_type: TPD (any occupation)
- cover active on event date: true
- insurer decision: ACCEPTED (TPD definition under policy met)
- evidence for trustee release: only 1 medical certificate (requires 2)

**Expected rule result:**
- C-001: ELIGIBLE
- C-002: MATCH
- Insurer: ACCEPTED
- T-003: CONDITION_NOT_MET (only 1 medical certificate, need 2 for permanent incapacity)

**Expected eligibility:** APPROVED_BY_INSURER_TRUSTEE_PENDING
**Expected explanation:** The insurer has accepted the TPD claim under the policy terms. However, the trustee cannot yet confirm the super law permanent incapacity release condition — only one medical practitioner certificate has been received and two are required. The benefit is preserved in super until the second certificate is provided.
**Expected notices:** RELEASE_DETERMINATION notice explaining outstanding evidence requirement
**Expected audit events:** INSURER_DECISION, TRUSTEE_DECISION (condition not met), NOTICE_SENT

---

## TS-018 — TPD claim — own-occupation insurer test vs any-occupation super law test

**Inputs:**
- claim_type: TPD
- cover_type: TPD (any occupation — as required inside super)
- insurer policy definition: any occupation (correctly aligned)
- insurer decision: ACCEPTED under any-occupation test
- super law test: two medical practitioners certify permanent incapacity under SIS Act test

**Expected rule result:**
- T-003: CONDITION_MET (both medical certificates confirm permanent incapacity under super law test)

**Expected eligibility:** APPROVED
**Expected explanation:** Insurer accepted the claim under the any-occupation TPD definition. Trustee confirms the permanent incapacity release condition is satisfied under super law. Benefit may be paid.
**Expected notices:** RELEASE_DETERMINATION (condition met), BENEFIT_PAYMENT
**Expected audit events:** TRUSTEE_DECISION, BENEFIT_PAID

---

## TS-019 — Terminal illness claim — life expectancy 14 months

**Inputs:**
- claim_type: TERMINAL_ILLNESS
- cover active: true
- evidence: 2 medical certificates — specialist confirms life expectancy ≤ 24 months (14 months prognosis)
- insurer decision: ACCEPTED

**Expected rule result:**
- T-002: CONDITION_MET (2 certificates, life expectancy ≤ 24 months confirmed)

**Expected eligibility:** APPROVED
**Expected explanation:** Terminal illness claim accepted. Two medical certificates confirm prognosis of 14 months. Super law release condition for terminal medical condition is satisfied. Lump sum payment authorised.
**Expected notices:** CLAIM_DECISION, BENEFIT_PAYMENT
**Expected audit events:** TRUSTEE_DECISION, BENEFIT_PAID

---

## TS-020 — Temporary incapacity / IP claim

**Inputs:**
- claim_type: TEMPORARY_INCAPACITY
- cover_type: IP (income protection)
- cover active: true
- evidence: medical certificate + employer statutory declaration
- insurer decision: ACCEPTED

**Expected rule result:**
- T-004: CONDITION_MET
- T-010: payment form = income stream → VALID

**Expected eligibility:** APPROVED
**Expected explanation:** Temporary incapacity claim accepted. Release condition satisfied. Benefit paid as income stream (lump sum not permitted for temporary incapacity).
**Expected notices:** CLAIM_DECISION, BENEFIT_PAYMENT
**Expected audit events:** TRUSTEE_DECISION, BENEFIT_PAID

---

## TS-021 — Premium deduction fails — insufficient balance

**Inputs:**
- cover_type: LIFE
- cover active: true
- account balance: $180
- annual_premium: $520 (monthly: $43)
- next premium deduction due: today

**Expected rule result:**
- Premium deduction fails — balance $180 < monthly premium $43... wait, actually $180 > $43 monthly, let me recalculate. Annual premium $520 = monthly $43. Balance $180 > $43 — deduction proceeds. Let me use a clearer example.
- account balance: $25
- monthly premium: $43
- Premium deduction fails — balance $25 < $43

**Expected system behaviour:**
- Deduction fails
- Fund rules applied: cover lapses after grace period (e.g., 30 days) if balance not restored
- Member notified of impending lapse
- AuditLog event created

**Expected notices:** PREMIUM_FAILURE notice to member
**Expected audit events:** PREMIUM_DEDUCTION_FAILED, NOTICE_SENT

---

## TS-022 — Missing contribution feed — inactivity clock stale

**Inputs:**
- last_contribution_date: recorded 10 months ago
- contribution_feed_status: STALE (feed not received for 60 days)
- inactivity_months_computed: 10

**Expected system behaviour:**
- System flags DATA_QUALITY issue
- Does NOT fire inactivity trigger based on stale data
- Generates operational risk alert
- Requires manual verification before any cessation action

**Expected notices:** Internal operational alert (not member-facing)
**Expected audit events:** DATA_QUALITY_FLAG, OPERATIONAL_ALERT

---

## TS-023 — Data conflict — insurer says active, trustee says ceased

**Inputs:**
- InsuranceCover.cover_status: CEASED (in trustee system)
- Insurer system: shows cover ACTIVE
- Conflict detected on claim receipt

**Expected system behaviour:**
- System sets claim status to DATA_CONFLICT
- No payment or rejection issued until conflict resolved
- Escalation notice generated for trustee operations team
- AuditLog records the conflict

**Expected notices:** Internal escalation (not member-facing until resolved)
**Expected audit events:** DATA_CONFLICT_DETECTED, OPERATIONAL_ESCALATION

---

## TS-024 — Member opts in after cover already ceased

**Inputs:**
- cover_status: CEASED (ceased 3 months ago due to inactivity)
- inactivity_months: 19
- member action: lodges new OPT_IN election today
- current_balance: 12000

**Expected rule result:**
- R-060: ELECTION_APPLIES
- R-010: TRIGGER_FIRED but overridden by new election
- R-080: ELIGIBLE (with note that reinstatement may require underwriting)

**Expected eligibility:** ELIGIBLE_PENDING_REINSTATEMENT
**Expected explanation:** Member has lodged a valid opt-in election. Eligibility gates now cleared. Cover may be reinstated subject to fund rules on reinstatement and whether underwriting is required due to the gap in coverage.
**Expected notices:** ELECTION_ACKNOWLEDGEMENT, REINSTATEMENT notice (if cover reinstated)
**Expected audit events:** ELECTION_RECORDED, ELIGIBILITY_ASSESSED, COVER_ISSUED (if reinstated)

---

## TS-025 — Defined benefit fund — PYS rules exempt

**Inputs:**
- fund_type: DEFINED_BENEFIT
- cover_type: LIFE (embedded in benefit formula)
- member_age: 52
- inactivity_months: 20
- current_balance: N/A (DB fund — account-based balance concept does not apply)

**Expected rule result:**
- R-002: EXEMPT (defined benefit fund)
- R-080: ELIGIBLE

**Expected eligibility:** ELIGIBLE
**Expected explanation:** Defined benefit funds are exempt from the Protecting Your Super switch-off rules. Insurance is embedded in the benefit formula and not subject to the inactivity, low-balance, or under-25 gates.
**Expected notices:** None
**Expected audit events:** ELIGIBILITY_ASSESSED (exempt path)

---

## TS-026 — Annual re-assessment — previously eligible, now inactivity threshold crossed

**Inputs:**
- Previous snapshot (12 months ago): ELIGIBLE, inactivity_months: 4
- Current snapshot: inactivity_months: 16 (no contributions received in 12 months)
- elections: none
- exceptions: none

**Expected rule result:**
- R-010: TRIGGER_FIRED (16 months now exactly reached)
- R-080: INELIGIBLE

**Expected eligibility:** INELIGIBLE
**Expected explanation:** At the last assessment, the member was eligible. Since then, no contributions have been received and the account has now been inactive for exactly 16 months. The inactivity trigger has fired. Pre-cessation notice must be sent and cover ceased unless the member lodges an opt-in direction within the notice period.
**Expected notices:** PRE_CESSATION notice to member (immediate)
**Expected audit events:** ELIGIBILITY_ASSESSED, PRE_CESSATION_NOTICE_SENT

---

## TS-027 — Death claim — non-dependant beneficiary — tax implications flagged

**Inputs:**
- claim_type: DEATH
- claimant: adult child (not financially dependent on deceased)
- benefit_amount: $450,000
- taxable_component_percentage: 100%
- insurer decision: ACCEPTED
- release condition: CONDITION_MET (LPR confirmed)

**Expected rule result:**
- T-001: CONDITION_MET
- T-010: VALID (lump sum to LPR permitted)
- Tax flag: NON_DEPENDANT_RECIPIENT — tax withheld required at applicable rate (parameter, not hard-coded)

**Expected eligibility:** APPROVED_WITH_TAX_IMPLICATION
**Expected explanation:** Death claim approved and release condition satisfied. The beneficiary is an adult non-dependant child. Tax must be withheld on the taxable component at the applicable rate under ITAA97 s302-195 before payment. Tax rate is applied as a parameter — verify current rate before processing payment.
**Expected notices:** CLAIM_DECISION with tax explanation, BENEFIT_PAYMENT confirmation
**Expected audit events:** TRUSTEE_DECISION, TAX_CALCULATED, BENEFIT_PAID

---

## Coverage Matrix

| Category | Scenarios covering it |
|---|---|
| Standard eligible path | TS-001 |
| Inactivity trigger — no override | TS-002 |
| Inactivity trigger — opt-in election override | TS-003 |
| Under-25 trigger — no election | TS-004 |
| Under-25 — employer exception does NOT override | TS-005 |
| Member turns 25 | TS-006 |
| Low balance — grandfathered | TS-007 |
| Own-occupation TPD blocked | TS-008 |
| Trauma blocked | TS-009 |
| SMSF exempt | TS-010, TS-025 |
| Dangerous occupation exception | TS-011 |
| Employer exception lapses | TS-012 |
| SFT election carries over | TS-013 |
| Underwriting required | TS-014 |
| Underwriting declined | TS-015 |
| Death claim — full process | TS-016, TS-027 |
| TPD — insurer accepted, trustee pending | TS-017 |
| TPD — both tests aligned | TS-018 |
| Terminal illness | TS-019 |
| Temporary incapacity / IP | TS-020 |
| Premium deduction failure | TS-021 |
| Stale contribution feed | TS-022 |
| Data conflict | TS-023 |
| Opt-in after cessation | TS-024 |
| Annual re-assessment trigger | TS-026 |
