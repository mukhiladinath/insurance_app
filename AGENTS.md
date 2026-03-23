# AGENTS.md

## Purpose of this repository
This repository contains the insurance advisory application built using a harness-engineering approach. The application uses a separated frontend and backend architecture, with a LangGraph-based agent in the backend and MongoDB as the primary datastore.

This repository is not a general chatbot project. It is a structured decision-support system where:
- the agent orchestrates flows
- tools perform deterministic business logic
- MongoDB stores conversations, tool runs, and app data
- the frontend presents the workflow and outputs to the user

The agent must always treat tools as the source of truth for domain logic.

---

## Repository structure
Top-level structure:

- `frontend/` — Next.js frontend application
- `backend/` — FastAPI backend, LangGraph agent, business tools, MongoDB integration
- `infra/` — local infrastructure such as Docker Compose for MongoDB
- `docs/` — source of truth for business rules, architecture, tool behavior, evals, and implementation guidance

The `docs/` folder is the primary reference for all implementation work.

---

## How to navigate this repository
When working in this repository, use the following order of reference:

1. `docs/00-overview/`
   - understand the product, architecture, and repo layout
2. `docs/01-environment/`
   - understand how to run the project locally
3. `docs/03-agent/`
   - understand agent responsibilities, behavior, and orchestration rules
4. `docs/04-tools/`
   - understand tool definitions, schemas, and contracts
5. `docs/05-rules/`
   - understand business rules and decision logic
6. `docs/06-data/`
   - understand MongoDB collections and document shapes
7. `docs/08-evals/`
   - understand expected behavior and regression cases

If there is any ambiguity, prefer the more specific document over the more general one.

---

## Core engineering approach
This repository follows harness engineering principles:
- keep the environment easy for the agent to understand
- keep instructions in files, not only in prompts
- keep business logic deterministic and documented
- keep tool interfaces explicit
- keep architecture modular and navigable
- keep implementation aligned with documented rules
- keep behavior testable through defined eval cases

The repository should be easy for both humans and coding agents to work in safely and consistently.

---

## Architecture principles
The implementation must follow these principles:

### 1. Frontend and backend are separate
- frontend lives in `frontend/`
- backend lives in `backend/`
- do not mix backend business logic into frontend code
- do not place frontend UI code inside backend modules

### 2. Agent is an orchestrator, not the business engine
- the LangGraph agent decides flow
- tools execute business logic
- the agent must not invent or override deterministic tool results

### 3. Tools are deterministic
- no hidden reasoning inside tools
- no LLM-only decision making for domain logic
- tools must follow documented business rules
- same input should produce the same output

### 4. MongoDB is the primary data store
- use MongoDB for conversations, messages, agent runs, tool calls, and app configuration
- document shapes must match the definitions in `docs/06-data/`

### 5. Documentation is part of the product
- new features must update the relevant docs
- tools must not be implemented without a tool spec
- decision logic must not be implemented without documented business rules

---

## Coding expectations
When implementing code in this repository:

- prefer clear and explicit code over clever code
- follow existing module boundaries
- create small, well-named files
- keep functions focused
- validate all external inputs
- use typed schemas wherever possible
- avoid introducing unapproved frameworks or infrastructure

Do not introduce:
- vector databases
- PostgreSQL
- MCP
- multi-agent orchestration
unless the docs are updated and the project direction changes explicitly.

---

## Backend expectations
Backend implementation should use:
- FastAPI
- LangGraph
- MongoDB
- Pydantic
- clearly separated modules for agent, tools, data access, and schemas

Suggested backend structure:

- `backend/app/api/`
- `backend/app/agents/`
- `backend/app/tools/`
- `backend/app/db/`
- `backend/app/schemas/`
- `backend/app/services/`
- `backend/app/core/`

The backend should be built so that tools can be tested independently from the agent graph.

---

## Frontend expectations
Frontend implementation should use:
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui where useful

Frontend responsibilities:
- user interaction
- input collection
- rendering outputs
- showing tool results clearly
- reflecting backend state cleanly

The frontend should not contain the domain decision logic of the tools.

---

## Tool implementation rules
Every tool must have:

1. a documented purpose
2. a documented input schema
3. a documented output schema
4. deterministic business rules
5. failure handling rules
6. sample input/output examples
7. eval coverage

Before implementing or modifying a tool, read:
- `docs/04-tools/tools-overview.md`
- the specific tool spec file
- the relevant rules in `docs/05-rules/`

---

## Business rule enforcement
Business rules must be modeled explicitly and not buried inside prompts.

If a recommendation, comparison, or eligibility outcome is needed:
- derive the required fields
- evaluate the documented rules
- produce a structured result
- return flags, assumptions, and warnings where needed

If a rule is unclear or missing:
- do not invent it in code
- update the docs first

---

## Data and persistence rules
MongoDB must be used consistently.

Expected stored entities include:
- conversations
- messages
- agent runs
- tool calls
- app configuration
- future user preferences or workflow state

Every persisted object should have:
- a clear purpose
- predictable shape
- timestamps where relevant

---

## Local development
Infrastructure is started from `infra/` using Docker Compose.

Typical commands:
- start infra: `docker compose up -d`
- stop infra: `docker compose down`

Frontend and backend are run separately from their own folders.

Detailed setup instructions live in:
- `docs/01-environment/local-setup.md`
- `docs/01-environment/mongodb-setup.md`

---

## Documentation update rules
Whenever adding or changing a feature, update the relevant docs:
- architecture change → update `docs/00-overview/architecture-overview.md`
- environment change → update `docs/01-environment/`
- agent behavior change → update `docs/03-agent/`
- tool change → update `docs/04-tools/`
- business logic change → update `docs/05-rules/`
- MongoDB structure change → update `docs/06-data/`
- expected outcomes change → update `docs/08-evals/`

Documentation drift should be treated as a real issue.

For the full folder-by-folder breakdown, change-to-doc mapping table, practical examples, and the documentation update policy, see:
**`docs/00-overview/docs-structure.md`** — source of truth for documentation discipline in this repository.

---

## Implementation priority
For this repository, implementation should generally happen in this order:

1. environment and repo structure
2. architecture docs
3. agent behavior docs
4. tool specs
5. business rules
6. data model docs
7. backend scaffolding
8. frontend scaffolding
9. tool implementation
10. evals and refinement

---

## Current project constraints
Current fixed decisions:
- frontend and backend are separate folders
- backend uses LangGraph
- MongoDB is the datastore
- no vector DB
- no PostgreSQL
- no MCP for now
- tools are the source of business logic
- harness engineering docs must be maintained from the beginning

If any future work conflicts with these constraints, the docs must be updated before implementation proceeds.

---

## Final working rule
Do not treat this repository like a generic LLM demo.

Treat it as:
- a structured application
- a deterministic tool-driven advisory system
- a documented, agent-friendly engineering environment