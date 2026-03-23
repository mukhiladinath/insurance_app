# Documentation Structure and Maintenance Guide

**Location:** `docs/00-overview/docs-structure.md`
**Authority:** This is the source of truth for documentation discipline in this repository.
**Rule:** Documentation must be updated in the same task as any code change. No exceptions.

---

## 1. Purpose of the Docs System

The `docs/` folder is not supplementary material — it is a primary engineering deliverable.

It exists to serve three distinct audiences:

**Engineers and developers** — understand what has been built, why decisions were made, and where to make changes without breaking existing logic.

**Coding agents (AI assistants)** — load structured context before reading or writing code. The docs reduce ambiguity, prevent duplicated logic, and keep agents aligned with the intended architecture.

**Product and QA** — understand what each tool decides, what the expected input/output contracts are, and what the documented test cases cover.

### Why documentation drift is a real defect

When code changes without corresponding doc updates:
- agents load stale context and make decisions based on incorrect models
- new developers implement logic that conflicts with undocumented rules
- QA can no longer verify tool behavior against a reference
- business rules accumulate silently in code with no auditable trace

Treating documentation drift as a defect is not aspirational — it is a practical constraint of this architecture.

---

## 2. Folder-by-Folder Explanation

### `docs/00-overview/`
**Purpose:** High-level system orientation. Read this first.

Contains: what the product is, how the architecture works, how the repository is structured, and how the docs system itself is organized.

This folder answers: *What is this system and how does it fit together?*

| File | What belongs there |
|---|---|
| `product-overview.md` | What the product is, its core philosophy, system roles, what it is not, expected evolution |
| `architecture-overview.md` | Frontend/backend separation, component responsibilities, data flow, separation of concerns, infrastructure |
| `repo-map.md` | Directory tree with explanations for each folder and key file — a navigation map for humans and agents |
| `docs-structure.md` | This file — the documentation system itself, folder purposes, file intent, change-to-doc mapping, update policy |

---

### `docs/01-environment/`
**Purpose:** Everything needed to run the project locally.

Contains: setup steps, configuration, infrastructure start commands, troubleshooting.

This folder answers: *How do I get this running on my machine?*

| File | What belongs there |
|---|---|
| `local-setup.md` | End-to-end local setup steps — Node.js, Python, dependencies, environment variables, first run |
| `mongodb-setup.md` | MongoDB-specific setup — Docker Compose usage, connection strings, local vs hosted |
| `frontend-setup.md` | Frontend-specific setup — Next.js version, npm commands, env vars, port conventions |
| `backend-setup.md` | Backend-specific setup — FastAPI, virtual environment, Pydantic, LangGraph version pins |
| `runbook.md` | Day-to-day operational commands — start, stop, reset, re-seed, test, build |

---

### `docs/02-product/`
**Purpose:** Business context and user-facing perspective.

Contains: who uses this system, what problems it solves, the language used across the domain, and the workflows users go through.

This folder answers: *What is this product for and who uses it?*

| File | What belongs there |
|---|---|
| `business-context.md` | Why this product exists, the regulatory and market context, the advisory problem being solved |
| `user-personas.md` | Who the users are — advisers, clients, QA engineers, compliance officers |
| `workflows.md` | The end-to-end journeys a user takes through the system — input → agent → tool → output |
| `glossary.md` | Domain-specific terms: SIS Act, PYS rules, TPD, SOA, FSG, TMD, ASIC RG 175, etc. |

---

### `docs/03-agent/`
**Purpose:** How the LangGraph agent is designed and what it is allowed to do.

Contains: agent responsibilities, behavior constraints, orchestration patterns, state model, response formatting policy.

This folder answers: *What does the agent do and what rules govern it?*

| File | What belongs there |
|---|---|
| `agent-purpose.md` | Why the agent exists, what it is responsible for, what it must never do |
| `agent-behavior-rules.md` | Hard rules governing agent behavior — must call tools for domain decisions, must not invent outcomes |
| `langgraph-architecture.md` | LangGraph node layout, edge definitions, conditional routing, how tool calls fit in the graph |
| `state-model.md` | The state object that flows through the graph — fields, types, updates, persistence |
| `response-policy.md` | How the agent formats and structures its final responses — what to include, what to exclude |

---

### `docs/04-tools/`
**Purpose:** Tool contracts, specifications, and integration rules.

Contains: what tools exist, what each one accepts and returns, how the agent calls them, how failures are handled.

This folder answers: *What tools exist and how do they work at the interface level?*

| File | What belongs there |
|---|---|
| `tools-overview.md` | Index of all tools — name, purpose, module location, version, status |
| `tool-1-spec.md` | Full spec for Tool 1 — inputs, outputs, error cases, example calls |
| `tool-2-spec.md` | Full spec for Tool 2 — inputs, outputs, error cases, example calls |
| `tool-contracts.md` | Shared contracts all tools must honour — input validation, output shape, error envelope |
| `tool-failure-handling.md` | How tools signal failure, what the agent does when a tool fails, partial result handling |

> **Note:** For in-depth product-level documentation of each tool's business logic (calculations, rules, scoring), see `docs/product-overview/` — a parallel folder created to document the tool implementations in detail. That folder is the source of truth for tool business behaviour; `docs/04-tools/` is the source of truth for tool interface contracts.

---

### `docs/05-rules/`
**Purpose:** The explicit business rules that tools implement.

Contains: the decisions tools must make, the logic they must follow, the assumptions baked in, and the recommendation criteria.

This folder answers: *What rules must the system follow when making decisions?*

| File | What belongs there |
|---|---|
| `global-business-rules.md` | Rules that apply across all tools — eligibility gates, override precedence, edge cases |
| `policy-modelling-rules.md` | How insurance policies are modelled — cover types, definitions, sum insured, premium structures |
| `recommendation-rules.md` | The rules that determine which recommendation a tool produces — hierarchy, blocking logic, forcing logic |
| `assumptions-policy.md` | What assumptions tools are allowed to make when data is missing — defaults, approximations, caveats |

---

### `docs/06-data/`
**Purpose:** MongoDB schema and document shape definitions.

Contains: what is stored, how it is structured, what each field means, and how documents evolve.

This folder answers: *What is stored in the database and in what shape?*

| File | What belongs there |
|---|---|
| `mongodb-schema.md` | Overview of MongoDB usage — database name, collection list, indexing strategy |
| `collections.md` | Per-collection documentation — purpose, document lifecycle, access patterns |
| `document-shapes.md` | Field-by-field definitions for each document type — types, optionality, validation rules |
| `conversation-memory.md` | How conversation history is stored, retrieved, and used by the agent |

---

### `docs/07-prompts/`
**Purpose:** System prompts, routing instructions, and response templates.

Contains: the text passed to the model at each stage of the agent flow.

This folder answers: *What instructions does the model receive and when?*

| File | What belongs there |
|---|---|
| `system-prompt.md` | The agent's base system prompt — role, constraints, output format rules |
| `routing-prompt.md` | The instructions used to route requests to the correct tool or flow |
| `tool-selection-prompt.md` | The instructions that determine which tool to call given the current context |
| `explanation-prompt.md` | The instructions that govern how the agent narrates and explains tool outputs to the user |

---

### `docs/08-evals/`
**Purpose:** Expected behavior, golden test cases, and regression coverage.

Contains: documented scenarios that define correct system behavior — used for testing, QA, and agent alignment.

This folder answers: *What outputs should the system produce for these inputs?*

| File | What belongs there |
|---|---|
| `eval-strategy.md` | How evals are structured, what they test, how results are interpreted |
| `tool-1-evals.md` | Golden cases for Tool 1 — input scenario, expected recommendation, expected flags |
| `tool-2-evals.md` | Golden cases for Tool 2 — input scenario, expected recommendation, expected flags |
| `golden-cases.md` | Cross-tool golden cases and edge cases that span more than one tool |

---

### `docs/09-delivery/`
**Purpose:** Implementation standards, roadmap, and engineering process.

Contains: coding standards, the implementation plan, milestones, and delivery tracking.

This folder answers: *How is this being built and to what standard?*

| File | What belongs there |
|---|---|
| `coding-standards.md` | TypeScript and Python style rules, naming conventions, file structure rules, forbidden patterns |
| `implementation-plan.md` | The ordered plan for implementing the system — what gets built first and why |
| `milestones.md` | Progress checkpoints — what constitutes a completed phase |

---

## 3. Change-to-Doc Mapping Rules

When you change code, the following table tells you which docs to update. **Update docs in the same task as the code change.**

| Code area changed | Primary docs to update | Secondary docs to consider |
|---|---|---|
| Tool business logic (rules, calculations, scoring) | `docs/04-tools/tool-N-spec.md` | `docs/05-rules/recommendation-rules.md`, `docs/product-overview/` |
| Tool inputs or outputs (schema change) | `docs/04-tools/tool-N-spec.md`, `docs/04-tools/tool-contracts.md` | `docs/06-data/document-shapes.md` if persisted |
| Adding a new tool | `docs/04-tools/tools-overview.md`, new `tool-N-spec.md` | `docs/05-rules/`, `docs/product-overview/`, `docs/08-evals/tool-N-evals.md` |
| Agent flow / LangGraph graph changes | `docs/03-agent/langgraph-architecture.md` | `docs/03-agent/agent-behavior-rules.md`, `docs/03-agent/state-model.md` |
| Agent state model | `docs/03-agent/state-model.md` | `docs/06-data/conversation-memory.md` |
| System / routing / tool-selection prompts | `docs/07-prompts/` (relevant file) | `docs/03-agent/response-policy.md` |
| MongoDB collections or document shapes | `docs/06-data/collections.md`, `docs/06-data/document-shapes.md` | `docs/06-data/mongodb-schema.md` |
| MongoDB conversation memory | `docs/06-data/conversation-memory.md` | `docs/03-agent/state-model.md` |
| Environment / local setup commands | `docs/01-environment/local-setup.md` or relevant sub-file | `AGENTS.md` if key commands changed |
| Infrastructure (Docker Compose, ports, env vars) | `docs/01-environment/` | `docs/00-overview/architecture-overview.md` |
| Repo folder structure | `docs/00-overview/repo-map.md` | `AGENTS.md`, `docs/00-overview/architecture-overview.md` |
| Frontend architecture | `docs/00-overview/architecture-overview.md` | `docs/01-environment/frontend-setup.md` |
| Frontend ↔ backend API wiring (store, api.ts, env vars) | `docs/02-frontend/frontend-backend-integration.md` | `docs/00-overview/architecture-overview.md` |
| Backend architecture | `docs/00-overview/architecture-overview.md` | `docs/01-environment/backend-setup.md` |
| Business/domain rules | `docs/05-rules/` (most specific matching file) | `docs/product-overview/` tool docs |
| Recommendation logic | `docs/05-rules/recommendation-rules.md` | `docs/product-overview/` tool docs, `docs/08-evals/` |
| Assumptions / defaults | `docs/05-rules/assumptions-policy.md` | `docs/product-overview/` tool docs |
| Eval / golden test cases | `docs/08-evals/` (relevant file) | — |
| Implementation plan or milestones | `docs/09-delivery/implementation-plan.md`, `docs/09-delivery/milestones.md` | — |
| Coding standards | `docs/09-delivery/coding-standards.md` | `AGENTS.md` if standards affect core repo rules |
| Product purpose / philosophy | `docs/00-overview/product-overview.md` | `AGENTS.md` |
| Compliance rules or flags | `docs/05-rules/global-business-rules.md` | `docs/product-overview/` tool docs |

---

## 4. Documentation Update Policy

These rules are non-negotiable:

### Rule 1: Same task, same update
Docs must be updated in the same task as the code change. Do not finish a task with code changes and undated docs. Stale docs are a defect.

### Rule 2: Update before create
Always check whether an existing doc is the correct home for new information before creating a new file. Creating a new doc when an existing one should be updated causes fragmentation.

### Rule 3: Create only when no appropriate home exists
Create a new doc only when the concept genuinely has no home in the existing structure. When creating a new file:
- place it in the most natural section
- link it from the relevant overview or index file for that section
- do not leave it orphaned

### Rule 4: Cross-link new docs
When a new doc is created, add a reference to it from the relevant parent or index file. New files that are not referenced from anywhere will not be discovered by engineers or agents.

### Rule 5: Match specificity
If both a general and a specific doc cover the same area, update the more specific one. Reference the specific one from the general one if the relationship is not yet documented.

### Rule 6: Docs drift is a blocking issue for agents
Agents load docs as context. A stale doc causes an agent to work from incorrect assumptions. This is equivalent to a misconfigured tool — the output will be wrong even when the input is correct.

---

## 5. Agent and Developer Workflow

Before finishing any task that changes code, run through this checklist:

```
[ ] Identify which code areas were changed or added
[ ] Map each changed area to the docs sections in Section 3 above
[ ] Open each affected doc and update it to reflect the change
[ ] If a new concept has no home, create a new doc in the right section
[ ] Link any new doc from its parent or index file
[ ] Confirm no other doc references the old behavior (search for it if in doubt)
[ ] In your final summary, list: code files changed, docs files changed, why each doc was updated
```

This checklist applies to every task — not just large feature additions. A single constant change can invalidate an assumption documented in `docs/05-rules/`. A renamed field can invalidate `docs/06-data/`. Treat every change as potentially doc-relevant.

---

## 6. Practical Examples for This Codebase

### Example 1: Adding a new insurance tool (e.g., Income Protection tool)

**Code changes:**
- Create `frontend/lib/tools/incomeProtection/` (12 TypeScript files)
- Export from `frontend/lib/tools/index.ts`

**Required doc updates:**
- Create `docs/product-overview/income-protection.md` — full product-level specification
- Update `docs/product-overview/README.md` — add the new tool to the Tool Index
- Create `docs/04-tools/tool-3-spec.md` — interface contract (inputs, outputs, errors)
- Update `docs/04-tools/tools-overview.md` — add entry for new tool
- Create `docs/08-evals/tool-3-evals.md` — golden cases for the new tool
- Update `docs/05-rules/recommendation-rules.md` if new recommendation types are introduced

---

### Example 2: Changing recommendation logic in an existing tool

**Code changes:**
- Modify a rule function in `purchaseRetainLifeTPDPolicy.rules.ts` (e.g., changing the threshold for SUPPLEMENT vs REPLACE)

**Required doc updates:**
- Update `docs/product-overview/purchase-retain-life-tpd-policy.md` — update the affected rule in the Hard Rules table and the Decision Flow section
- Update `docs/05-rules/recommendation-rules.md` — update the documented rule condition
- Update `docs/08-evals/tool-2-evals.md` — update any golden cases whose expected output changes as a result

---

### Example 3: Changing a MongoDB collection or document shape

**Code changes:**
- Add a field to a `ToolCall` document in the backend MongoDB schema

**Required doc updates:**
- Update `docs/06-data/document-shapes.md` — add the new field with type, purpose, and optionality
- Update `docs/06-data/collections.md` — note the schema version or change description for the collection
- If the field affects conversation memory: update `docs/06-data/conversation-memory.md`

---

### Example 4: Changing prompt behavior

**Code changes:**
- Modify the agent's system prompt to add a new constraint or change response formatting

**Required doc updates:**
- Update `docs/07-prompts/system-prompt.md` — reflect the new instruction or constraint
- Update `docs/03-agent/response-policy.md` if the change affects how responses are structured
- Update `docs/03-agent/agent-behavior-rules.md` if a new behavioral rule is being enforced

---

### Example 5: Changing frontend setup steps

**Code changes:**
- Update `package.json`, change a Next.js config, or add a new required environment variable

**Required doc updates:**
- Update `docs/01-environment/frontend-setup.md` — add/update the setup step or env var
- Update `docs/01-environment/local-setup.md` if the change affects the end-to-end local setup sequence
- Update `docs/01-environment/runbook.md` if a command changes

---

### Example 6: Adding or changing eval cases

**Code changes:**
- Add new scenarios to `purchaseRetainLifeTPDPolicy.test-cases.ts`

**Required doc updates:**
- Update `docs/08-evals/tool-2-evals.md` — add the new scenario with its input summary, expected recommendation, and expected flags
- Update `docs/08-evals/eval-strategy.md` if the scenario introduces a new category of test coverage

---

### Example 7: Changing the rule that determines when REFER_TO_HUMAN fires

**Code changes:**
- Modify `ruleReferToHuman()` in `purchaseRetainLifeTPDPolicy.rules.ts`

**Required doc updates:**
- Update `docs/product-overview/purchase-retain-life-tpd-policy.md` — update R-013 in the Hard Rules table
- Update `docs/05-rules/recommendation-rules.md` — update the REFER_TO_HUMAN condition
- Update `docs/08-evals/tool-2-evals.md` — verify no golden cases now produce incorrect expected outputs

---

## 7. Known Structural Notes

The following deviations from the intended structure exist and should be resolved over time:

### `docs/product-overview/` folder
This folder (`docs/product-overview/`) sits outside the numbered folder structure. It was created to hold in-depth product-level tool documentation (business logic, calculations, scoring, law versions). It is the correct and intended home for this content. It should eventually be formally referenced from `docs/04-tools/tools-overview.md` and `docs/00-overview/repo-map.md` once those files are created.

### `docs/02-frontend/` — Frontend integration docs
This folder was created to document the frontend ↔ backend integration layer. It covers the API client, Zustand store design, message send flow, and environment variables.

| File | What belongs there |
|---|---|
| `frontend-backend-integration.md` | API contract, client functions, store actions, message flow, env vars |

Note: the originally planned `docs/02-product/` folder (for business context / user personas / glossary) has not yet been created. It should be created when that content is ready.

---

### Several numbered folders are empty or do not yet exist
The following sections of the docs structure described in this document do not yet have files:
- `docs/02-product/` (intended for business context — not yet created; `docs/02-frontend/` was created instead)
- `docs/03-agent/`
- `docs/04-tools/`
- `docs/05-rules/`
- `docs/06-data/`
- `docs/07-prompts/`
- `docs/08-evals/`
- `docs/09-delivery/`

These should be populated as the corresponding system components are built. Do not create placeholder files — create real files when the content exists.

### `docs/00-overview/repo-map.md` does not yet exist
This file should be created once the repository structure stabilises. It should contain a complete annotated directory tree.

---

## 8. Summary of This File's Purpose

This file (`docs/00-overview/docs-structure.md`) is the single source of truth for:
- understanding what each docs folder and file is for
- deciding which docs to update when code changes
- the policy that governs documentation maintenance
- the workflow checklist for agents and developers

It should be read:
- before starting any task that involves code changes
- when a new concept needs to be documented and you are unsure where it belongs
- when onboarding a new developer or agent to the repository
