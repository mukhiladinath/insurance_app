"""
workspace_schemas.py — Pydantic request/response models for the workspace API.

Endpoints:
  POST /api/clients                            → CreateClientRequest / ClientOut
  GET  /api/clients                            → ClientListOut
  GET  /api/workspace/{client_id}             → WorkspaceOut
  PATCH /api/clients/{client_id}/factfind     → PatchFactfindRequest / FactfindOut
  POST /api/clients/{client_id}/factfind/proposals/{id}/accept → AcceptProposalRequest
  POST /api/workspace/{client_id}/run         → WorkspaceRunRequest / WorkspaceRunResponse
  GET  /api/workspace/{client_id}/ai-context  → AiContextOut
  PATCH /api/workspace/{client_id}/ai-context → PatchAiContextRequest / AiContextOut
  GET  /api/workspace/{client_id}/saved-runs  → SavedRunListOut
  POST /api/workspace/{client_id}/saved-runs/{id}/save → SaveRunRequest
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Shared sub-models
# ─────────────────────────────────────────────────────────────────────────────

class AttachedFileRef(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    storage_ref: str


class MissingFieldOut(BaseModel):
    field_path: str    # e.g. "personal.age"
    label: str         # e.g. "Client Age"
    section: str       # e.g. "personal"
    required: bool = True


class PlanStepOut(BaseModel):
    step_id: str
    tool_name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    rationale: str = ""


class StepResultOut(BaseModel):
    step_id: str
    tool_name: str
    description: str = ""
    status: str   # "completed" | "failed" | "skipped" | "cached"
    error: str | None = None
    cache_source_run_id: str | None = None


class DataCardOut(BaseModel):
    step_id: str
    tool_name: str
    type: str
    title: str
    display_hint: str
    data: dict[str, Any]


class UiActionOut(BaseModel):
    type: str     # e.g. "open_factfind_panel", "highlight_missing_fields", "refresh_ai_context"
    payload: dict[str, Any] = Field(default_factory=dict)


class ProposedFieldOut(BaseModel):
    field_path: str
    label: str
    current_value: Any | None
    proposed_value: Any
    confidence: float
    evidence: str = ""


class ProposedPatchOut(BaseModel):
    proposal_id: str
    source_document_id: str
    fields: list[ProposedFieldOut]


# ─────────────────────────────────────────────────────────────────────────────
# Client
# ─────────────────────────────────────────────────────────────────────────────

class CreateClientRequest(BaseModel):
    user_id: str
    name: str
    email: str | None = None
    phone: str | None = None
    date_of_birth: str | None = None


class ClientOut(BaseModel):
    id: str
    user_id: str
    name: str
    email: str | None
    phone: str | None
    date_of_birth: str | None
    status: str
    created_at: datetime
    updated_at: datetime


class ClientListOut(BaseModel):
    clients: list[ClientOut]


# ─────────────────────────────────────────────────────────────────────────────
# Factfind
# ─────────────────────────────────────────────────────────────────────────────

class FactfindFieldOut(BaseModel):
    value: Any | None
    status: str
    source: str
    confidence: float
    updated_at: datetime | None = None
    updated_by: str = ""


class FactfindSectionOut(BaseModel):
    fields: dict[str, FactfindFieldOut] = Field(default_factory=dict)


class FactfindProposalOut(BaseModel):
    proposal_id: str
    source_document_id: str
    proposed_fields: dict[str, Any]
    status: str
    created_at: datetime


class FactfindOut(BaseModel):
    client_id: str
    version: int
    sections: dict[str, dict[str, Any]]
    pending_proposals: list[FactfindProposalOut] = Field(default_factory=list)
    completeness_pct: float = 0.0
    updated_at: datetime | None = None


class PatchFactfindRequest(BaseModel):
    changes: dict[str, Any]   # {"personal.age": 42, "financial.super_balance": 150000}
    source: str = "manual"


class AcceptProposalRequest(BaseModel):
    field_paths: list[str] | None = None   # None = accept all


# ─────────────────────────────────────────────────────────────────────────────
# AI Context
# ─────────────────────────────────────────────────────────────────────────────

class AiContextLayerOut(BaseModel):
    label: str
    user_can_view: bool
    user_can_edit: bool
    system_owned: bool
    affects_planning: bool
    data: Any


class AiContextOut(BaseModel):
    layers: dict[str, AiContextLayerOut]
    overrides: dict[str, Any] = Field(default_factory=dict)


class PatchAiContextRequest(BaseModel):
    overrides: dict[str, Any]


# ─────────────────────────────────────────────────────────────────────────────
# Workspace overview
# ─────────────────────────────────────────────────────────────────────────────

class SavedRunSummaryOut(BaseModel):
    id: str
    name: str
    tool_names: list[str]
    summary: str
    saved_at: datetime
    tags: list[str] = Field(default_factory=list)


class PendingClarificationOut(BaseModel):
    resume_token: str
    question: str
    missing_fields: list[MissingFieldOut]
    created_at: datetime


class WorkspaceOut(BaseModel):
    workspace_id: str
    client: ClientOut
    factfind: FactfindOut
    advisory_notes: dict[str, Any]
    scratch_pad: list[dict[str, Any]]
    active_conversation_id: str | None
    saved_runs: list[SavedRunSummaryOut]
    ai_context: AiContextOut
    pending_clarification: PendingClarificationOut | None


# ─────────────────────────────────────────────────────────────────────────────
# Saved tool runs
# ─────────────────────────────────────────────────────────────────────────────

class SavedRunDetailOut(BaseModel):
    id: str
    client_id: str
    workspace_id: str
    run_id: str
    name: str
    tool_names: list[str]
    inputs_snapshot: dict[str, Any]
    step_results: list[StepResultOut]
    data_cards: list[DataCardOut]
    summary: str
    saved_at: datetime
    tags: list[str]


class SavedRunListOut(BaseModel):
    saved_runs: list[SavedRunSummaryOut]


class SaveRunRequest(BaseModel):
    name: str
    tags: list[str] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# Main run endpoint
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceRunRequest(BaseModel):
    user_id: str
    message: str
    conversation_id: str | None = None

    attached_files: list[AttachedFileRef] = Field(default_factory=list)

    # Clarification resume
    resume_token: str | None = None
    clarification_answer: str | None = None

    # Patch-rerun
    rerun_from_saved_run_id: str | None = None
    patched_inputs: dict[str, Any] | None = None

    # Optional save
    save_run_as: str | None = None


class WorkspaceRunResponse(BaseModel):
    # Identifiers
    run_id: str
    client_id: str
    workspace_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str | None = None

    # Run status
    run_status: Literal["completed", "awaiting_clarification", "failed", "partial"]

    # Main response text
    assistant_content: str

    # Clarification (when run_status = "awaiting_clarification")
    clarification_needed: bool = False
    clarification_question: str | None = None
    missing_fields: list[MissingFieldOut] = Field(default_factory=list)
    resume_token: str | None = None

    # Tool run results
    plan_steps: list[PlanStepOut] = Field(default_factory=list)
    step_results: list[StepResultOut] = Field(default_factory=list)
    data_cards: list[DataCardOut] = Field(default_factory=list)

    # Factfind changes proposed by this run
    proposed_factfind_patches: ProposedPatchOut | None = None

    # Saved run
    saved_run_id: str | None = None

    # Frontend action queue
    ui_actions: list[UiActionOut] = Field(default_factory=list)

    # Context snapshot reference
    context_snapshot_id: str | None = None
    context_summary: dict[str, Any] = Field(default_factory=dict)

    errors: list[str] = Field(default_factory=list)
