# Implementation Plan — Purchase / Retain Life & TPD in Superannuation (Tool 3)

**Module:** `purchase_retain_life_tpd_in_super`
**Parent doc:** [`docs/product-overview/life-tpd-in-super.md`](../product-overview/life-tpd-in-super.md)
**Rules reference:** [`docs/05-rules/life-tpd-in-super-rules.md`](../05-rules/life-tpd-in-super-rules.md)
**Test scenarios:** [`docs/08-evals/tool-3-evals.md`](../08-evals/tool-3-evals.md)

---

## Guiding Principles

- Follow the same architecture as Tool 1 (`life_insurance_in_super.py`) and Tool 2 (`life_tpd_policy.py`)
- Reuse shared helpers: `_safe_parse_date`, `_compute_age`, `_pv_annuity`, `_clamp`, validation envelope format, missing-info-questions format, rule trace format
- No LLM calls inside the tool — deterministic only
- All rule IDs, legal basis, and reasons stored as metadata — never hard-coded into UI
- Tax rates passed as parameters — never embedded in logic
- Each phase must be fully tested before the next phase begins

---

## Phase 1 — Rules Foundation (Backend Tool Core)

**Goal:** Build the deterministic eligibility engine as a standalone Python tool.

### Tasks

1. **Create tool file:** `backend/app/tools/implementations/life_tpd_in_super.py`
   - ENGINE_VERSION = "1.0.0"
   - Normalise function: convert raw input dict → clean internal format
   - Validate function: check required fields, build missing_info_questions
   - Rule evaluation functions (one per rule ID)
   - Final eligibility resolver (R-080)

2. **Implement Tier 1 rules (R-001 to R-003):**
   - R-001: Permitted cover type check
   - R-002: Fund type exempt check
   - R-003: Member opt-out election check

3. **Implement Tier 2 PYS gate rules (R-010 to R-012):**
   - R-010: Inactivity trigger (16 months)
   - R-011: Under-25 trigger (MySuper only)
   - R-012: Low-balance trigger ($6,000 with grandfathering)

4. **Implement Tier 3 exception and election rules (R-050 to R-060):**
   - R-050: Small fund / defined benefit exception
   - R-051: ADF exception
   - R-052: Employer premium exception (with excess verification)
   - R-053: Dangerous occupation exception
   - R-054: SFT exception (with equivalent rights flag)
   - R-055: Rights not affected (fixed-term / fully-paid)
   - R-060: Member opt-in election

5. **Implement Tier 4 final resolver (R-080):**
   - Combine all Tier 1–3 results into final eligibility determination

6. **Implement Tier 5 underwriting rules (R-090, R-091):**
   - AAL comparison
   - Coverage gap detection
   - Underwriting outcome mapping

7. **Register tool in registry:**
   - Add `PurchaseRetainLifeTPDInSuperTool` to `backend/app/tools/registry.py`
   - Tool name: `purchase_retain_life_tpd_in_super`

8. **Smoke test the tool** with all 27 test scenarios from `docs/08-evals/tool-3-evals.md`

**Deliverable:** Tool passes all TS-001 through TS-015 scenarios deterministically.

---

## Phase 2 — Data Model and Repositories

**Goal:** Implement all new MongoDB collections and repository classes.

### New Collections

| Collection name | Entity |
|---|---|
| `super_accounts` | SuperAccount |
| `insurance_covers` | InsuranceCover |
| `insurance_elections` | InsuranceElection |
| `insurance_eligibility_snapshots` | InsuranceEligibilitySnapshot |
| `exception_qualifications` | ExceptionQualification |
| `occupation_assessments` | OccupationAssessment |
| `employer_premium_notices` | EmployerPremiumNotice |
| `contribution_events` | ContributionEvent |
| `balance_history` | BalanceHistory |
| `underwriting_cases` | UnderwritingCase |
| `claim_cases` | ClaimCase |
| `evidence_items` | EvidenceItem |
| `trustee_release_decisions` | TrusteeReleaseDecision |
| `notices` | Notice |

### Tasks

1. **Add collection name constants** to `backend/app/db/collections.py`

2. **Implement `ensure_indexes()`** for each new collection — see data model section in main doc for required indexes

3. **Create repository files** (one per collection) in `backend/app/db/repositories/`:
   - `super_account_repository.py`
   - `insurance_cover_repository.py`
   - `insurance_election_repository.py`
   - `eligibility_snapshot_repository.py`
   - `exception_qualification_repository.py`
   - `occupation_assessment_repository.py`
   - `employer_premium_notice_repository.py`
   - `contribution_event_repository.py`
   - `balance_history_repository.py`
   - `underwriting_case_repository.py`
   - `claim_case_repository.py`
   - `evidence_item_repository.py`
   - `trustee_release_decision_repository.py`
   - `notice_repository.py`

4. **Follow existing repository conventions:**
   - `_serialize()` function converting `_id` → `id`
   - All timestamps use `utc_now()`
   - All IDs use `to_object_id()`
   - Async methods using Motor

5. **Extend `AuditLog`** collection (already exists as part of existing schema) with new `event_type` values for insurance lifecycle events

6. **Create `ComplianceTrace` repository** if not already present

**Deliverable:** All collections created, indexed, and accessible via repository pattern. No schema migration failures.

---

## Phase 3 — Claims and Trustee Release Engine

**Goal:** Build the claims lifecycle engine (Tier 6 and 7 rules).

### Tasks

1. **Implement Tier 6 claim rules (C-001 to C-003)** in the tool file:
   - C-001: Cover active at claim date
   - C-002: Claim type matches cover type
   - C-003: Evidence completeness check + missing evidence questions

2. **Implement Tier 7 trustee release-condition rules (T-001 to T-010):**
   - T-001: Death release condition
   - T-002: Terminal illness release condition
   - T-003: Permanent incapacity (TPD) release condition
   - T-004: Temporary incapacity release condition
   - T-010: Payment form validation

3. **Build ClaimsService** (`backend/app/services/claims_service.py`):
   - `open_claim()` — create ClaimCase, validate cover active, run C-001 to C-003
   - `record_insurer_decision()` — update ClaimCase, generate notice
   - `run_trustee_release_check()` — run T-001 to T-010, create TrusteeReleaseDecision, generate notice
   - `authorise_payment()` — validate T-010 (payment form), record payment event

4. **Build NoticeService** (`backend/app/services/notice_service.py`):
   - `send_notice()` — create Notice record, dispatch via configured channel
   - Notice types: all types listed in data model

5. **Smoke test claims flow** against TS-016 through TS-020 and TS-027

**Deliverable:** Claims lifecycle runs end-to-end, trustee release determination recorded correctly, notices generated.

---

## Phase 4 — API Routes and Service Layer

**Goal:** Expose all lifecycle operations as FastAPI endpoints.

### New Route Files

| File | Endpoints |
|---|---|
| `backend/app/api/routes/insurance_in_super.py` | All 12 endpoints from Section 7 of main doc |

### Tasks

1. **Create route file** with all 12 endpoints (see API design in main doc)

2. **Register router** in `backend/app/main.py` with prefix `/api/insurance-in-super`

3. **Create Pydantic schemas** for all request/response bodies:
   - `EligibilityRequest` / `EligibilityResult`
   - `ElectionRequest` / `ElectionResponse`
   - `ContributionEventRequest`
   - `BalanceUpdateRequest`
   - `UnderwritingRequest` / `UnderwritingResponse`
   - `CoverStatusUpdateRequest`
   - `ClaimIntakeRequest` / `ClaimResponse`
   - `InsurerDecisionRequest`
   - `TrusteeReleaseRequest` / `TrusteeReleaseResponse`
   - `NoticeRequest`
   - `AuditQueryParams` / `AuditHistoryResponse`

4. **Wire routes to services** — routes call service layer, not repositories directly

5. **Register `purchase_retain_life_tpd_in_super`** in the LangGraph agent's classify_intent keyword lists

6. **Add tool input schema** to `classify_intent.py` `_TOOL_INPUT_SCHEMAS` for the new tool name

**Deliverable:** All API endpoints respond correctly. LangGraph agent can route to the new tool via conversation.

---

## Phase 5 — Testing and Compliance Validation

**Goal:** Validate all 27 test scenarios pass and compliance obligations are met.

### Tasks

1. **Unit tests** — one test function per scenario in `docs/08-evals/tool-3-evals.md`
   - Test file: `backend/tests/test_life_tpd_in_super.py`
   - Each test: provide input dict, call `tool.safe_execute(input)`, assert expected eligibility and rule trace

2. **Integration tests** — test the full flow from API endpoint to MongoDB write to response
   - POST /api/insurance-in-super/eligibility
   - POST /api/insurance-in-super/claims
   - POST /api/insurance-in-super/claims/{id}/release-determination

3. **Compliance trace validation** — for every test scenario, assert:
   - `compliance_trace.rule_evaluations` contains entries for every evaluated rule
   - Every rule entry has `legal_basis` set
   - No tax rate values are hard-coded in the output
   - Missing-info questions use the standard format `{id, question, category, blocking}`

4. **Notice generation validation** — assert correct notice type is generated for:
   - Cessation events (TS-002, TS-012)
   - Pre-cessation warning (TS-026)
   - Election acknowledgement (TS-024)
   - Claim outcome (TS-016, TS-017)
   - Underwriting result (TS-015)

5. **Edge case validation** — manually test all scenarios from Section 9 (Edge Cases) of the main doc

6. **Compliance checklist review** — verify each item in Section 10 of the main doc is implemented and tested

**Deliverable:** All 27 scenarios pass. Compliance checklist fully verified. No hard-coded tax rates. All notices generated correctly.

---

## Phase 6 — Frontend Integration and Monitoring

**Goal:** Surface the new module in the chat UI and adviser panel.

### Tasks

1. **Update `classify_intent.py` keyword rules:**
   - Add keywords for life/TPD in super lifecycle events: "claim", "benefit", "cessation", "inactivity notice", etc.
   - Ensure the new tool routes correctly vs Tool 1 and Tool 2

2. **Update `_extract_tool_inputs` schema** in `classify_intent.py` to include the new tool's input fields

3. **Update `compose_response.py`** to handle the new tool's output format:
   - Eligibility result rendering
   - Claims status rendering
   - Trustee release determination rendering

4. **Create frontend type definitions** (`frontend/lib/types.ts`) for the new tool's response shape

5. **Add API client functions** to `frontend/lib/api.ts` for the new endpoints

6. **Ongoing monitoring setup:**
   - Configure contribution event listeners (or polling if feed-based)
   - Set up inactivity clock monitoring job
   - Set up balance threshold monitoring

7. **Annual strategy review task generation** — implement a scheduled job that flags when SPS 250 annual review is due

**Deliverable:** New module accessible via the chat interface. Adviser can ask about eligibility, claims, and receive structured responses. Ongoing monitoring runs without manual trigger.

---

## Phase 6 Completion Criteria

| Criterion | Verified by |
|---|---|
| All 27 test scenarios pass | Automated test suite |
| All compliance checklist items implemented | Code review + manual check |
| No hard-coded tax rates | Code review |
| All notices generated for required events | Integration tests |
| LangGraph routes correctly to new tool | Manual conversation test |
| Claims lifecycle runs end-to-end | Integration test |
| Trustee release and insurer decision tracked separately | Integration test |
| Audit logs created for all events | Integration test |
| Frontend displays eligibility and claim status | Manual UI test |
| Documentation updated (all 5 doc files) | Doc review |

---

## Dependencies on Existing Modules

| Dependency | Usage |
|---|---|
| `life_insurance_in_super.py` (Tool 1) | Reuse normalise, validate, PYS trigger, exception logic as reference |
| `life_tpd_policy.py` (Tool 2) | Reuse life need calc, TPD need calc, underwriting risk logic as reference |
| `backend/app/db/mongo.py` | MongoDB connection — no changes needed |
| `backend/app/utils/timestamps.py` | `utc_now()` — no changes needed |
| `backend/app/utils/ids.py` | `to_object_id()` — no changes needed |
| `backend/app/core/constants.py` | Add new status constants (ClaimStatus, ReleaseCondition, etc.) |
| `backend/app/agents/nodes/classify_intent.py` | Add new tool to keyword rules and input schema |
| `backend/app/agents/nodes/compose_response.py` | Add new tool name handling in summary builder |

---

## Estimated Scope

| Phase | Estimated new files | Notes |
|---|---|---|
| Phase 1 | 1 tool file (~600 lines) | Reuses patterns from Tool 1 and 2 |
| Phase 2 | 14 repository files (~80 lines each) | Boilerplate-heavy, pattern is established |
| Phase 3 | 2 service files (~300 lines each) | Claims and Notice services |
| Phase 4 | 1 route file + 1 schema file (~400 lines) | FastAPI standard pattern |
| Phase 5 | 1 test file (~500 lines) | 27 scenarios + edge cases |
| Phase 6 | Updates to 5 existing files + 2 frontend files | Integration wiring |
