# Product Overview

## What this project is
This project is an insurance advisory application built as a tool-driven agent system.

The application is designed to help model, evaluate, and explain insurance-related decisions through a structured backend agent and deterministic tools. The user interacts with the system through a frontend application, while the backend agent orchestrates workflows and calls business tools.

This is not a general-purpose chatbot. The core value of the application comes from:
- explicit business rules
- deterministic tool execution
- structured outputs
- clear decision support flows

---

## Core product idea
The product combines:
- a frontend for interaction and presentation
- a backend agent for orchestration
- deterministic tools for domain logic
- MongoDB for persistence

The agent is responsible for deciding what to do next. The tools are responsible for performing the actual business computations and structured decision logic.

---

## Product philosophy
The application follows these principles:

### 1. Tools first
Business logic belongs in tools, not in free-form model responses.

### 2. Deterministic decision support
Where the system evaluates scenarios or produces a recommendation, it should rely on documented rules and reproducible logic.

### 3. Explainable outputs
The result should be understandable and traceable to the inputs and the rules used.

### 4. Modular architecture
The system should remain easy to scale by adding tools, rules, and flows without collapsing into a single monolithic prompt.

### 5. Agent-friendly engineering
The repository must remain clear enough for coding agents and human developers to navigate safely and consistently.

---

## Initial scope
The first phase of the project focuses on:
- setting up the environment and repo structure
- establishing harness-engineering documentation
- defining business rules
- modeling the first tools clearly
- building the backend and frontend foundation
- integrating LangGraph and MongoDB

The early product will support only a small number of tools, but it should be designed so more tools can be added later without changing the overall architecture.

---

## System roles

### User
The user interacts with the app through the frontend, provides inputs, and reviews outputs and recommendations.

### Frontend
The frontend collects input, sends requests to the backend, and displays structured outputs clearly.

### Agent
The backend agent interprets the request, determines whether a tool is needed, selects the correct tool flow, and composes the final response.

### Tool
A tool performs deterministic logic based on well-defined inputs and returns structured outputs.

### MongoDB
MongoDB stores conversations, messages, agent runs, tool calls, and future application state.

---

## Related overview documents

| Document | Purpose |
|---|---|
| [`architecture-overview.md`](./architecture-overview.md) | Frontend/backend separation, component roles, data flow |
| [`docs-structure.md`](./docs-structure.md) | Documentation system — folder purposes, change-to-doc mapping, update policy |

---

## What this system is not
This system is not intended to be:
- an unrestricted chatbot
- a prompt-only advice engine
- a purely retrieval-based system
- a vector-search-first architecture
- a multi-agent system in its initial form

The product is intentionally narrow and structured in order to remain reliable and maintainable.

---

## Expected evolution
Over time, the application may expand with:
- more tools
- richer frontend workflows
- better explanation layers
- additional evaluation coverage
- stronger operational patterns

However, the core model should remain the same:
- agent orchestrates
- tools execute
- rules are documented
- data is persisted cleanly