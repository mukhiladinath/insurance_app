"""
orchestrator_graph.py — LangGraph workflow for the dynamic agent workspace.

Full node sequence:

  assess_context          ← rule-based: decide what context this query needs
       │
  load_context_smart      ← load N messages (N from context_requirements)
       │
  load_memory_smart       ← load specific client_facts sections + advisory notes
       │
  load_documents_smart    ← load doc text only if needed; always merge facts
       │
  plan_execution          ← LLM: decompose instruction into PlanSteps
       │
  ┌────┴──────────────────┐
  │ clarification_needed? │
  └────┬──────────────────┘
       │ yes → orchestrate_persist → update_memory → END  (returns question)
       │ no  ↓
  execute_steps           ← run tools in order; resolve {{step_N.field}} chains
       │
  orchestrate_summarize   ← LLM: synthesise results into adviser prose
       │
  distill_advisory        ← persist advisory conclusions to agent_workspace
       │
  orchestrate_persist     ← save message + agent run + tool call records
       │
  update_memory           ← extract & merge client facts from user message
       │
  END

Context layer design
--------------------
  assess_context decides how much of each layer to load:
    - Message history: 3 (default) | 8 (follow-up) | 15 (historical reference)
    - Memory sections: subset of [personal, financial, insurance, health, goals]
    - Advisory notes:  loaded only for "what did we decide" / SOA queries
    - Documents:       loaded only if query explicitly references a document
    - Scratch pad:     always loaded (tiny)

Advisory memory
---------------
  After every tool run, distill_advisory writes structured conclusions
  (verdict, recommendation, key numbers) to the agent_workspace collection.
  These survive across conversations so "what did we decide?" works instantly.
"""

import logging
from langgraph.graph import StateGraph, END

from app.agents.state import AgentState

# Context loading (new smart nodes)
from app.agents.orchestrator_nodes.assess_context_node import assess_context
from app.agents.orchestrator_nodes.load_context_smart import load_context_smart
from app.agents.orchestrator_nodes.load_memory_smart import load_memory_smart
from app.agents.orchestrator_nodes.load_documents_smart import load_documents_smart

# Orchestrator nodes
from app.agents.orchestrator_nodes.plan_node import plan_execution
from app.agents.orchestrator_nodes.execute_steps_node import execute_steps
from app.agents.orchestrator_nodes.summarize_node import orchestrate_summarize
from app.agents.orchestrator_nodes.distill_advisory_node import distill_advisory
from app.agents.orchestrator_nodes.persist_node import orchestrate_persist

# Shared with legacy graph
from app.agents.nodes.update_memory import update_memory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def _route_after_plan(state: AgentState) -> str:
    """
    After planning:
      clarification_needed → skip execution, go straight to persist
                             (final_response already set to the question)
      otherwise            → proceed to execute_steps
    """
    if state.get("clarification_needed"):
        logger.info("orchestrator: clarification needed → orchestrate_persist")
        return "orchestrate_persist"
    return "execute_steps"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_orchestrator_graph() -> StateGraph:
    builder = StateGraph(AgentState)

    # ---- Context assessment + smart loading ----
    builder.add_node("assess_context",       assess_context)
    builder.add_node("load_context_smart",   load_context_smart)
    builder.add_node("load_memory_smart",    load_memory_smart)
    builder.add_node("load_documents_smart", load_documents_smart)

    # ---- Orchestrator nodes ----
    builder.add_node("plan_execution",        plan_execution)
    builder.add_node("execute_steps",         execute_steps)
    builder.add_node("orchestrate_summarize", orchestrate_summarize)
    builder.add_node("distill_advisory",      distill_advisory)
    builder.add_node("orchestrate_persist",   orchestrate_persist)

    # ---- Shared tail (reused from legacy graph) ----
    builder.add_node("update_memory", update_memory)

    # ---- Entry point ----
    builder.set_entry_point("assess_context")

    # ---- Context loading chain ----
    builder.add_edge("assess_context",       "load_context_smart")
    builder.add_edge("load_context_smart",   "load_memory_smart")
    builder.add_edge("load_memory_smart",    "load_documents_smart")
    builder.add_edge("load_documents_smart", "plan_execution")

    # ---- Plan → execute or clarify ----
    builder.add_conditional_edges(
        "plan_execution",
        _route_after_plan,
        {
            "execute_steps":       "execute_steps",
            "orchestrate_persist": "orchestrate_persist",   # clarification path
        },
    )

    # ---- Execution path ----
    builder.add_edge("execute_steps",         "orchestrate_summarize")
    builder.add_edge("orchestrate_summarize", "distill_advisory")
    builder.add_edge("distill_advisory",      "orchestrate_persist")

    # ---- Shared tail: persist → update_memory → END ----
    builder.add_edge("orchestrate_persist", "update_memory")
    builder.add_edge("update_memory",       END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Singleton + runner
# ---------------------------------------------------------------------------

_orchestrator_graph = None


def get_orchestrator_graph():
    global _orchestrator_graph
    if _orchestrator_graph is None:
        _orchestrator_graph = build_orchestrator_graph()
        logger.info("Orchestrator LangGraph compiled.")
    return _orchestrator_graph


async def run_orchestrator(initial_state: AgentState) -> AgentState:
    graph = get_orchestrator_graph()
    result = await graph.ainvoke(initial_state)
    return result
