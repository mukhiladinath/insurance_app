"""
apply_patches.py — Apply patched inputs to a saved run's tool plan and invalidate
downstream steps.

Used for the rerun_patched mode. Given:
  - rerun_from_saved_run_id: the saved run to reload
  - patched_inputs: { "field_path": new_value } (dot-notation factfind paths)

This node:
  1. Loads the saved run from saved_tool_runs.
  2. Restores the tool_plan and step outputs as cached_step_results.
  3. Applies patched_inputs to the factfind_snapshot.
  4. Finds which plan steps have inputs that reference the patched fields.
  5. Propagates invalidation through the dependency_graph.
  6. Returns invalidated_steps so execute_workspace_steps knows what to rerun.

State reads:  rerun_from_saved_run_id, patched_inputs, dependency_graph
State writes: tool_plan, cached_step_results, invalidated_steps,
              factfind_snapshot (patched)
"""

import logging
import re
from typing import Any

from app.agents.workspace_state import WorkspaceState
from app.db.mongo import get_db
from app.db.repositories.saved_tool_run_repository import SavedToolRunRepository

logger = logging.getLogger(__name__)


def _field_referenced_in_inputs(field_path: str, inputs: Any) -> bool:
    """
    Return True if the factfind field_path appears to be used in the step inputs.
    Checks both:
      - Direct value match (field name at end of path, e.g. "age" in "personal.age")
      - Template reference {{step_N.field}}
    """
    field_name = field_path.split(".")[-1]
    inputs_str = str(inputs)
    # Direct key reference
    if field_name in inputs_str:
        return True
    # {{step_N.something}} chains — the patched field might feed a chain
    return False


def _propagate_invalidation(
    initial_invalid: set[str],
    dependency_graph: dict[str, list[str]],
) -> list[str]:
    """
    BFS/DFS to find all steps downstream of the initially invalidated steps.
    dependency_graph[step_id] = [steps that depend on step_id]
    """
    invalidated: set[str] = set(initial_invalid)
    queue = list(initial_invalid)
    while queue:
        step_id = queue.pop(0)
        for downstream in dependency_graph.get(step_id, []):
            if downstream not in invalidated:
                invalidated.add(downstream)
                queue.append(downstream)
    return list(invalidated)


async def apply_patches(state: WorkspaceState) -> dict:
    """
    Load a saved run, apply input patches, and compute invalidated steps.

    Reads:  rerun_from_saved_run_id, patched_inputs, dependency_graph
    Writes: tool_plan, cached_step_results, invalidated_steps, factfind_snapshot (patched)
    """
    saved_run_id = state.get("rerun_from_saved_run_id")
    patched_inputs: dict = state.get("patched_inputs") or {}
    dependency_graph: dict = state.get("dependency_graph", {})
    factfind_snapshot = dict(state.get("factfind_snapshot", {}))

    if not saved_run_id:
        logger.error("apply_patches: rerun_from_saved_run_id missing")
        return {"errors": state.get("errors", []) + ["rerun_from_saved_run_id missing"]}

    try:
        db = get_db()
        repo = SavedToolRunRepository(db)
        saved_run = await repo.get_by_id(saved_run_id)
    except Exception as exc:
        logger.exception("apply_patches: failed to load saved run %s: %s", saved_run_id, exc)
        return {"errors": state.get("errors", []) + [f"Failed to load saved run: {exc}"]}

    if not saved_run:
        return {"errors": state.get("errors", []) + [f"Saved run {saved_run_id} not found"]}

    tool_plan: list[dict] = saved_run.get("inputs_snapshot", {}).get("tool_plan", [])
    prior_step_results: list[dict] = saved_run.get("step_results", [])

    if not tool_plan:
        # Saved run may store tool_plan differently — try top-level
        logger.warning("apply_patches: no tool_plan in inputs_snapshot for %s", saved_run_id)
        return {
            "tool_plan": [],
            "cached_step_results": {},
            "invalidated_steps": [],
        }

    # Build cache from prior step results
    cached: dict = {
        r["step_id"]: {**r, "run_id": saved_run_id}
        for r in prior_step_results
        if r.get("status") == "completed"
    }

    # Rebuild dependency_graph from the loaded plan if not already set
    if not dependency_graph:
        from app.agents.workspace_nodes.plan_workspace_node import _build_dependency_graph
        dependency_graph = _build_dependency_graph(tool_plan)

    # Find initially invalidated steps
    initially_invalid: set[str] = set()
    for field_path, _ in patched_inputs.items():
        for step in tool_plan:
            inputs = step.get("inputs", {})
            if _field_referenced_in_inputs(field_path, inputs):
                initially_invalid.add(step["step_id"])

    # Propagate through dependency graph
    all_invalidated = _propagate_invalidation(initially_invalid, dependency_graph)

    # Apply patches to factfind_snapshot
    patched_snapshot = {**factfind_snapshot, **patched_inputs}

    logger.info(
        "apply_patches: saved_run=%s patched=%s invalidated=%s",
        saved_run_id, list(patched_inputs.keys()), all_invalidated,
    )

    return {
        "tool_plan": tool_plan,
        "cached_step_results": cached,
        "invalidated_steps": all_invalidated,
        "dependency_graph": dependency_graph,
        "factfind_snapshot": patched_snapshot,
    }
