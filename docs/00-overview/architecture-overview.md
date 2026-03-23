# Architecture Overview

## High-level architecture
The project uses a separated frontend and backend architecture with local infrastructure support.

Main components:
- `frontend/` — Next.js application
- `backend/` — FastAPI application with LangGraph agent and tools
- `infra/` — Docker Compose infrastructure for MongoDB
- `docs/` — harness-engineering documentation and system reference

---

## Frontend
The frontend is responsible for:
- rendering the user interface
- collecting user input
- displaying agent responses
- showing structured tool outputs
- managing client-side interaction state

The frontend should not contain business decision logic.

Expected technologies:
- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui where useful

### Frontend → Backend integration

All API calls go through `frontend/lib/api.ts` — a typed fetch client that wraps every backend endpoint.
State management uses Zustand (`frontend/store/chat-store.ts`). All async actions (load conversations, fetch messages, send message, refresh workspace status) call the API client.

Full integration details: [`docs/02-frontend/frontend-backend-integration.md`](../02-frontend/frontend-backend-integration.md)

---

## Backend
The backend is responsible for:
- receiving requests from the frontend
- maintaining agent flow
- calling deterministic tools
- validating inputs and outputs
- persisting state in MongoDB
- returning structured and explainable results

Expected technologies:
- FastAPI
- LangGraph
- Pydantic
- MongoDB driver integration

---

## Agent architecture
The backend agent is implemented using LangGraph.

The LangGraph agent is responsible for:
- understanding the current request
- deciding whether a tool should be called
- selecting the right flow
- invoking the appropriate tool
- handling result formatting
- maintaining a structured execution path

The agent is an orchestrator. It is not the owner of domain business rules.

---

## Tool architecture
Tools are the business engine of the application.

Each tool should:
- accept validated structured input
- apply deterministic logic
- return structured output
- surface assumptions, warnings, and flags where required

Tools should be independently testable and should not rely on hidden prompt behavior to produce core domain outcomes.

---

## Data architecture
MongoDB is the primary datastore for this project.

MongoDB is expected to store:
- conversations
- messages
- agent runs
- tool calls
- app configuration
- future workflow state where needed

MongoDB is used because the project currently favors flexible document-oriented persistence over relational storage.

---

## Infrastructure architecture
Local development infrastructure is managed through Docker Compose in `infra/`.

The main infrastructure service in the current phase is:
- MongoDB

Optional supporting services may be added later, but the initial system should remain simple.

---

## Flow overview
A typical flow looks like this:

1. user interacts with the frontend
2. frontend sends a request to the backend
3. backend agent receives the request
4. agent decides whether a tool is needed
5. agent invokes the relevant tool
6. tool returns structured output
7. backend stores execution data in MongoDB
8. backend returns the final response
9. frontend renders the result

---

## Separation of concerns
The architecture should preserve these boundaries:

### Frontend
Responsible for presentation and interaction only

### Backend agent
Responsible for orchestration and flow control

### Tools
Responsible for deterministic business logic

### MongoDB
Responsible for persistence

### Docs
Responsible for expressing system behavior and implementation contracts

---

## Initial constraints
Current architecture constraints:
- separate frontend and backend
- LangGraph for agent orchestration
- MongoDB as primary data store
- no vector DB
- no PostgreSQL
- no MCP for now
- no multi-agent design for now

Any change to these constraints must be reflected in the docs before implementation changes begin.

---

## Architectural goal
The goal is to keep the system:
- modular
- deterministic where it matters
- easy to navigate
- easy to extend
- easy to implement using harness-engineering practices