"""
graph.py — LangGraph workflow definition.

Node order:
  load_context → load_memory → classify_intent
    → [execute_tool if tool selected]
    → overseer_quality_gate          ← NEW quality-gate node
    → [retry loop: back to classify_intent or execute_tool if overseer says so]
    → compose_response → persist_results → update_memory → END

Routing:
  classify_intent   → execute_tool          (if selected_tool is set)
  classify_intent   → compose_response      (direct response path)
  execute_tool      → overseer_quality_gate
  overseer_quality_gate → classify_intent   (retry_extraction — bad tool input)
  overseer_quality_gate → execute_tool      (retry_tool — transient error)
  overseer_quality_gate → compose_response  (proceed / proceed_with_caution / ask_user / reset_context)
"""

import logging
from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.load_context import load_context
from app.agents.nodes.load_memory import load_memory
from app.agents.nodes.load_documents import load_documents
from app.agents.nodes.classify_intent import classify_intent
from app.agents.nodes.execute_tool import execute_tool
from app.agents.nodes.overseer_quality_gate import overseer_quality_gate
from app.agents.nodes.compose_response import compose_response
from app.agents.nodes.persist_results import persist_results
from app.agents.nodes.update_memory import update_memory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_classify(state: AgentState) -> str:
    """Route to execute_tool if a tool was selected, otherwise straight to compose_response."""
    if state.get("selected_tool"):
        return "execute_tool"
    return "compose_response"


def _route_after_overseer(state: AgentState) -> str:
    """
    Route based on the overseer's verdict.

    retry_extraction → classify_intent  (re-extract tool inputs; one retry max)
    retry_tool       → execute_tool     (re-run the same tool; one retry max)
    everything else  → compose_response
    """
    status = state.get("overseer_status", "proceed")

    if status == "retry_extraction":
        logger.info("overseer routing: retry_extraction → classify_intent")
        return "classify_intent"

    if status == "retry_tool":
        logger.info("overseer routing: retry_tool → execute_tool")
        return "execute_tool"

    # proceed / proceed_with_caution / ask_user / reset_context / fallback
    return "compose_response"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_graph() -> StateGraph:
    """Construct and compile the LangGraph agent workflow."""
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("load_context",          load_context)
    builder.add_node("load_memory",           load_memory)
    builder.add_node("load_documents",        load_documents)  # NEW: inject document text + merge facts
    builder.add_node("classify_intent",       classify_intent)
    builder.add_node("execute_tool",          execute_tool)
    builder.add_node("overseer_quality_gate", overseer_quality_gate)  # NEW
    builder.add_node("compose_response",      compose_response)
    builder.add_node("persist_results",       persist_results)
    builder.add_node("update_memory",         update_memory)

    # Entry point
    builder.set_entry_point("load_context")

    # load_context → load_memory → load_documents → classify_intent
    builder.add_edge("load_context",   "load_memory")
    builder.add_edge("load_memory",    "load_documents")
    builder.add_edge("load_documents", "classify_intent")

    # classify_intent → execute_tool OR compose_response
    builder.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {
            "execute_tool":    "execute_tool",
            "compose_response": "compose_response",
        },
    )

    # execute_tool → overseer_quality_gate (always)
    builder.add_edge("execute_tool", "overseer_quality_gate")

    # overseer_quality_gate → retry or compose
    builder.add_conditional_edges(
        "overseer_quality_gate",
        _route_after_overseer,
        {
            "classify_intent":  "classify_intent",   # retry_extraction path
            "execute_tool":     "execute_tool",       # retry_tool path
            "compose_response": "compose_response",   # normal / caution / ask / reset
        },
    )

    # compose_response → persist_results → update_memory → END
    builder.add_edge("compose_response",  "persist_results")
    builder.add_edge("persist_results",   "update_memory")
    builder.add_edge("update_memory",     END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
        logger.info("LangGraph agent workflow compiled.")
    return _graph


async def run_agent(initial_state: AgentState) -> AgentState:
    """Invoke the agent graph and return the final state."""
    graph = get_graph()
    result = await graph.ainvoke(initial_state)
    return result
