# Product Overview

This folder contains product-level documentation for each insurance strategy tool in the system.

The purpose of this folder is **not** to duplicate technical API notes. It exists so that:
- product managers understand what each tool decides and why
- engineers understand the business intent before implementing or extending
- future AI agents can load these documents as context before running or modifying tools
- QA engineers understand the expected decision boundaries for each scenario

---

## How This Fits the Architecture

Each tool in `frontend/lib/tools/` is a self-contained, deterministic business-logic module. The agent (in `backend/`) calls these tools to produce structured results. The frontend renders those results.

This folder documents the **product behaviour** of those tools — what they are, what they decide, and what guardrails exist.

---

## Tool Index

### 1. Life Insurance Cover in Superannuation
**Module:** `frontend/lib/tools/purchaseRetainLifeInsuranceInSuper/`
**Backend:** `backend/app/tools/implementations/life_insurance_in_super.py`
**Documentation:** [life-insurance-cover-in-super.md](./life-insurance-cover-in-super.md)

Determines whether **life insurance** can legally exist inside a member's superannuation fund, whether it must be switched off under the Protecting Your Super rules, and whether holding it inside super is strategically beneficial versus outside super. Also evaluates statutory exceptions and generates member action recommendations.

**Scope:** Life insurance only. PYS eligibility + strategic placement scoring.

---

### 2. Purchase / Retain Life / TPD Policy
**Module:** `frontend/lib/tools/purchaseRetainLifeTPDPolicy/`
**Backend:** `backend/app/tools/implementations/life_tpd_policy.py`
**Documentation:** [purchase-retain-life-tpd-policy.md](./purchase-retain-life-tpd-policy.md)

Determines whether a client should purchase new life and/or TPD insurance, retain their existing policy, replace it, supplement it, or reduce it. Applies structured need-analysis calculations, policy comparison logic, underwriting risk assessment, replacement risk analysis, and hard compliance guardrails to produce a deterministic, auditable recommendation.

**Scope:** Life and TPD insurance — structurally agnostic (primarily outside-super oriented). Need analysis + policy comparison + underwriting risk.

---

### 3. Purchase / Retain Life & TPD Insurance in Superannuation
**Module (planned):** `backend/app/tools/implementations/life_tpd_in_super.py`
**Frontend (planned):** `frontend/lib/tools/purchaseRetainLifeTPDInSuper/`
**Documentation:** [life-tpd-in-super.md](./life-tpd-in-super.md)
**Rules engine:** [`docs/05-rules/life-tpd-in-super-rules.md`](../05-rules/life-tpd-in-super-rules.md)
**Test scenarios:** [`docs/08-evals/tool-3-evals.md`](../08-evals/tool-3-evals.md)
**Implementation plan:** [`docs/09-delivery/tool-3-implementation-plan.md`](../09-delivery/tool-3-implementation-plan.md)

Determines the full lifecycle of **both Life and TPD insurance held inside superannuation** — from initial eligibility (PYS gates, exceptions, elections) through underwriting, cover issuance, ongoing monitoring, claim handling, trustee release-condition determination, and benefit payment. Compliance-critical module covering SIS Act, SPS 250, PMIF reforms, and claims handling obligations.

**Scope:** Life and TPD inside super. Full lifecycle: eligibility → underwriting → monitoring → claims → trustee release → payment.

**Key distinction from Tool 1:** Covers both Life AND TPD. Includes the full claims pipeline and trustee release-condition determination layer. Tool 1 covers life-only eligibility and placement scoring only.

**Key distinction from Tool 2:** Inside-super specific. Applies super law release condition tests, not just insurer policy definitions. Tool 2 is primarily outside-super oriented.

---

## How the Three Tools Relate

```
Tool 3 (life-tpd-in-super)
  ├── Eligibility gates (extends Tool 1 PYS logic to cover TPD as well as Life)
  ├── Claims handling → Insurer assessment → Trustee release determination
  └── References Tool 1 for Life-only placement scoring when needed
       └── References Tool 2 for outside-super comparison when placement decision required
```

When a member asks about insurance inside super, the system routes first to Tool 3. If the question resolves to a placement decision (inside vs outside), Tool 3 may invoke Tool 1's placement engine. If an outside-super comparison is needed, Tool 2 is invoked for the outside-super analysis.

---

## Document Style

Each tool document covers:
1. Business purpose
2. User problem it solves
3. Key inputs
4. Decision outputs (recommendation types / eligibility results)
5. High-level logic flow
6. Calculation modules and rules
7. Major guardrails and hard rules
8. Compliance flags and notices
9. Risks and caveats
10. How it fits into the overall system

Tool 3 additionally covers (in its dedicated sections):
- Full 12-section design (research recap through implementation plan)
- Mermaid flowchart
- Complete data model
- Rules engine with legal citations
- 27+ named test scenarios
- Phased implementation plan

---

## Maintenance

When a tool's logic changes, update the corresponding document here.
Documentation drift should be treated as a real defect — see `AGENTS.md` for the full documentation update rules.
