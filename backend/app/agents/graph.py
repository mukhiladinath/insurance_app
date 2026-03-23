"""
graph.py — LangGraph workflow definition.

Node order:
  load_context → classify_intent → [execute_tool if tool selected] → compose_response → persist_results

Routing:
  classify_intent → execute_tool   (if selected_tool is set)
  classify_intent → compose_response  (direct response path)
"""

import logging
from langgraph.graph import StateGraph, END

from app.agents.state import AgentState
from app.agents.nodes.load_context import load_context
from app.agents.nodes.classify_intent import classify_intent
from app.agents.nodes.execute_tool import execute_tool
from app.agents.nodes.compose_response import compose_response
from app.agents.nodes.persist_results import persist_results

logger = logging.getLogger(__name__)


def _route_after_classify(state: AgentState) -> str:
    """
    Route to execute_tool if a tool was selected, otherwise skip to compose_response.
    """
    if state.get("selected_tool"):
        return "execute_tool"
    return "compose_response"


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph agent workflow."""
    builder = StateGraph(AgentState)

    # Register nodes
    builder.add_node("load_context", load_context)
    builder.add_node("classify_intent", classify_intent)
    builder.add_node("execute_tool", execute_tool)
    builder.add_node("compose_response", compose_response)
    builder.add_node("persist_results", persist_results)

    # Entry point
    builder.set_entry_point("load_context")

    # Edges
    builder.add_edge("load_context", "classify_intent")

    # Conditional routing after classification
    builder.add_conditional_edges(
        "classify_intent",
        _route_after_classify,
        {
            "execute_tool": "execute_tool",
            "compose_response": "compose_response",
        },
    )

    builder.add_edge("execute_tool", "compose_response")
    builder.add_edge("compose_response", "persist_results")
    builder.add_edge("persist_results", END)

    return builder.compile()


# Singleton compiled graph (created once at module import)
_graph = None


def get_graph():
    global _graph
    if _graph is None:
        _graph = build_graph()
        logger.info("LangGraph agent workflow compiled.")
    return _graph


async def run_agent(initial_state: AgentState) -> AgentState:
    """
    Invoke the agent graph with the given initial state.
    Returns the final state after all nodes have run.
    """
    graph = get_graph()
    result = await graph.ainvoke(initial_state)
    return result
