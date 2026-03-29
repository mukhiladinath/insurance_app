"""
workspace_state.py — LangGraph state definition for the client-workspace-centric agent.

WorkspaceState is the TypedDict that flows through every node in the new
workspace graph. It replaces AgentState for the new /api/workspace/{client_id}/run
endpoint while the legacy AgentState continues to serve the old /api/agent/run.

Primary unit: client_id (not conversation_id).
Every persistent resource is scoped to the client workspace.
"""

from typing import Any, Literal, TypedDict

ActiveMode = Literal[
    "plan_tool_subflow",            # default: AI bar tool run
    "extract_factfind_from_document",
    "update_factfind",
    "inspect_ai_context",
    "edit_ai_context",
    "resume_after_clarification",
    "rerun_patched",
]


class WorkspaceState(TypedDict, total=False):
    # ----------------------------------------------------------------
    # Identifiers — all set before graph invocation
    # ----------------------------------------------------------------
    user_id: str
    client_id: str           # primary unit
    workspace_id: str        # client_workspaces._id
    conversation_id: str     # thread within workspace
    run_id: str              # this agent_run's id

    # ----------------------------------------------------------------
    # Routing
    # ----------------------------------------------------------------
    active_mode: ActiveMode

    # ----------------------------------------------------------------
    # Input
    # ----------------------------------------------------------------
    user_message: str
    user_message_id: str | None
    attached_files: list[dict]   # [{filename, content_type, storage_ref, size_bytes}]

    # Clarification resume
    resume_token: str | None
    clarification_answer: str | None

    # Patch-rerun
    patched_inputs: dict | None          # {field_path: new_value}
    rerun_from_saved_run_id: str | None

    # Optional: save result under this name after run
    save_run_as: str | None

    # ----------------------------------------------------------------
    # Context loaded at run start
    # ----------------------------------------------------------------
    recent_messages: list[dict]
    factfind_snapshot: dict          # canonical factfind field values (flat: section.field → value)
    factfind_full: dict              # full factfind doc (with per-field metadata)
    ai_context_hierarchy: dict       # layered context tree (for planner + UI)
    ai_context_overrides: dict       # user-edited overrides from client_workspaces
    extracted_document_context: str | None

    # ----------------------------------------------------------------
    # Planning
    # ----------------------------------------------------------------
    tool_plan: list[dict]        # PlanStep list
    dependency_graph: dict       # step_id → list[step_id] it invalidates

    # ----------------------------------------------------------------
    # Execution
    # ----------------------------------------------------------------
    step_results: list[dict]     # StepResult list (includes status="cached")
    cached_step_results: dict    # step_id → StepResult (loaded from prior saved run)
    invalidated_steps: list[str] # step_ids that must re-execute due to patches

    # ----------------------------------------------------------------
    # Clarification state
    # ----------------------------------------------------------------
    clarification_needed: bool
    clarification_question: str | None
    missing_fields: list[dict]   # [{field_path, label, section, required}]

    # ----------------------------------------------------------------
    # Advisory / workspace memory (loaded + updated)
    # ----------------------------------------------------------------
    advisory_notes: dict         # tool_name → advisory note (client-scoped)
    scratch_pad: list[dict]

    # ----------------------------------------------------------------
    # Factfind changes (for update_factfind / extract modes)
    # ----------------------------------------------------------------
    factfind_draft_changes: dict   # field_path → new value (proposed by LLM or AI bar)
    factfind_proposal_id: str | None  # pending_proposals entry id after doc extraction

    # ----------------------------------------------------------------
    # Output / persistence
    # ----------------------------------------------------------------
    final_response: str
    structured_response_payload: dict | None
    data_cards: list[dict]
    ui_actions: list[dict]         # [{type, payload}] — instructions to frontend

    # IDs written during persist phase
    assistant_message_id: str | None
    saved_run_id: str | None        # if auto-saved or user requested save_run_as
    context_snapshot_id: str | None

    # Written by persist_pending_clarification so the service can return it
    # in the response without a second DB round-trip
    pending_resume_token: str | None

    # ----------------------------------------------------------------
    # Errors
    # ----------------------------------------------------------------
    errors: list[str]
