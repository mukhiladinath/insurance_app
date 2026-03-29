"""
workspace_graph.py — LangGraph workflow for the client-workspace-centric agent.

Full routing logic:

  route_request
       │
       ├── resume_after_clarification
       │     load_workspace_context
       │     load_pending_clarification
       │     merge_clarification_answer
       │     plan_workspace  ──────────────────────────────────┐
       │                                                        │
       ├── rerun_patched                                        │
       │     load_workspace_context                            │
       │     apply_patches                                     │
       │     execute_workspace_steps ───────────────────────────┤
       │                                                        │
       ├── extract_factfind_from_document                       │
       │     load_workspace_context                            │
       │     extract_factfind_fields                           │
       │     propose_factfind_patch                            │
       │     persist_run_artifacts                             │
       │     update_workspace_memory                           │
       │     END                                               │
       │                                                        │
       ├── update_factfind / inspect/edit_ai_context            │
       │     load_workspace_context                            │
       │     update_factfind_node                              │
       │     persist_run_artifacts                             │
       │     update_workspace_memory                           │
       │     END                                               │
       │                                                        │
       └── plan_tool_subflow (default)                         │
             load_workspace_context                            │
             plan_workspace ─────── clarification_needed? ─── │
                                        yes: persist_pending_clarification → END
                                        no:  execute_workspace_steps ──────┘
                                               workspace_summarize
                                               persist_run_artifacts
                                               update_workspace_memory
                                               END
"""

import logging
from langgraph.graph import StateGraph, END

from app.agents.workspace_state import WorkspaceState

from app.agents.workspace_nodes.route_request import route_request
from app.agents.workspace_nodes.load_workspace_context import load_workspace_context
from app.agents.workspace_nodes.plan_workspace_node import plan_workspace
from app.agents.workspace_nodes.execute_workspace_steps import execute_workspace_steps
from app.agents.workspace_nodes.persist_pending_clarification import persist_pending_clarification
from app.agents.workspace_nodes.load_pending_clarification import load_pending_clarification
from app.agents.workspace_nodes.merge_clarification_answer import merge_clarification_answer
from app.agents.workspace_nodes.apply_patches import apply_patches
from app.agents.workspace_nodes.extract_factfind_fields import extract_factfind_fields
from app.agents.workspace_nodes.propose_factfind_patch import propose_factfind_patch
from app.agents.workspace_nodes.update_factfind_node import update_factfind_node
from app.agents.workspace_nodes.workspace_summarize import workspace_summarize
from app.agents.workspace_nodes.persist_run_artifacts import persist_run_artifacts
from app.agents.workspace_nodes.update_workspace_memory import update_workspace_memory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Routing functions
# ---------------------------------------------------------------------------

def _route_after_request(state: WorkspaceState) -> str:
    """Route to the appropriate loading node based on active_mode."""
    mode = state.get("active_mode", "plan_tool_subflow")

    # All modes load workspace context first, except clarification resume
    # which still needs context but also loads the frozen plan
    return "load_workspace_context"


def _route_after_context(state: WorkspaceState) -> str:
    """After loading context, branch based on active_mode."""
    mode = state.get("active_mode", "plan_tool_subflow")

    if mode == "resume_after_clarification":
        return "load_pending_clarification"
    if mode == "rerun_patched":
        return "apply_patches"
    if mode == "extract_factfind_from_document":
        return "extract_factfind_fields"
    if mode in ("update_factfind", "inspect_ai_context", "edit_ai_context"):
        return "update_factfind_node"
    # default: plan_tool_subflow
    return "plan_workspace"


def _route_after_plan(state: WorkspaceState) -> str:
    """After planning: clarification or execute."""
    if state.get("clarification_needed"):
        logger.info("workspace_graph: clarification_needed → persist_pending_clarification")
        return "persist_pending_clarification"
    return "execute_workspace_steps"


def _route_after_clarification_load(state: WorkspaceState) -> str:
    """After loading frozen plan from pending clarification: merge the answer."""
    errors = state.get("errors", [])
    if errors and any("not found" in e or "already" in e for e in errors):
        # Can't resume — go to plan fresh
        return "plan_workspace"
    return "merge_clarification_answer"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def build_workspace_graph() -> StateGraph:
    builder = StateGraph(WorkspaceState)

    # ---- Nodes ----
    builder.add_node("route_request",                route_request)
    builder.add_node("load_workspace_context",       load_workspace_context)
    builder.add_node("plan_workspace",               plan_workspace)
    builder.add_node("execute_workspace_steps",      execute_workspace_steps)
    builder.add_node("persist_pending_clarification", persist_pending_clarification)
    builder.add_node("load_pending_clarification",   load_pending_clarification)
    builder.add_node("merge_clarification_answer",   merge_clarification_answer)
    builder.add_node("apply_patches",                apply_patches)
    builder.add_node("extract_factfind_fields",      extract_factfind_fields)
    builder.add_node("propose_factfind_patch",       propose_factfind_patch)
    builder.add_node("update_factfind_node",         update_factfind_node)
    builder.add_node("workspace_summarize",          workspace_summarize)
    builder.add_node("persist_run_artifacts",        persist_run_artifacts)
    builder.add_node("update_workspace_memory",      update_workspace_memory)

    # ---- Entry ----
    builder.set_entry_point("route_request")

    # ---- route_request → load_workspace_context (always) ----
    builder.add_edge("route_request", "load_workspace_context")

    # ---- load_workspace_context → branch by active_mode ----
    builder.add_conditional_edges(
        "load_workspace_context",
        _route_after_context,
        {
            "load_pending_clarification":  "load_pending_clarification",
            "apply_patches":               "apply_patches",
            "extract_factfind_fields":     "extract_factfind_fields",
            "update_factfind_node":        "update_factfind_node",
            "plan_workspace":              "plan_workspace",
        },
    )

    # ---- Clarification resume path ----
    builder.add_conditional_edges(
        "load_pending_clarification",
        _route_after_clarification_load,
        {
            "merge_clarification_answer": "merge_clarification_answer",
            "plan_workspace":             "plan_workspace",
        },
    )
    builder.add_edge("merge_clarification_answer", "plan_workspace")

    # ---- Patch-rerun path ----
    builder.add_edge("apply_patches", "execute_workspace_steps")

    # ---- Document extraction path ----
    builder.add_edge("extract_factfind_fields",  "propose_factfind_patch")
    builder.add_edge("propose_factfind_patch",   "persist_run_artifacts")

    # ---- Factfind / AI context update path ----
    builder.add_edge("update_factfind_node", "persist_run_artifacts")

    # ---- Default tool-run path ----
    builder.add_conditional_edges(
        "plan_workspace",
        _route_after_plan,
        {
            "persist_pending_clarification": "persist_pending_clarification",
            "execute_workspace_steps":       "execute_workspace_steps",
        },
    )

    # ---- Clarification exit ----
    builder.add_edge("persist_pending_clarification", "persist_run_artifacts")

    # ---- Execution path ----
    builder.add_edge("execute_workspace_steps", "workspace_summarize")
    builder.add_edge("workspace_summarize",     "persist_run_artifacts")

    # ---- Shared tail ----
    builder.add_edge("persist_run_artifacts",   "update_workspace_memory")
    builder.add_edge("update_workspace_memory", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Singleton + runner
# ---------------------------------------------------------------------------

_workspace_graph = None


def get_workspace_graph():
    global _workspace_graph
    if _workspace_graph is None:
        _workspace_graph = build_workspace_graph()
        logger.info("Workspace LangGraph compiled.")
    return _workspace_graph


async def run_workspace_graph(initial_state: WorkspaceState) -> WorkspaceState:
    graph = get_workspace_graph()
    result = await graph.ainvoke(initial_state)
    return result
