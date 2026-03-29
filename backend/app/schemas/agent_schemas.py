"""
agent_schemas.py — Pydantic request/response models for the agent workspace API.

POST /api/agent/run     → AgentRunRequest / AgentRunResponse
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------

class AttachedFileRef(BaseModel):
    filename: str
    content_type: str
    size_bytes: int
    storage_ref: str


class AgentRunRequest(BaseModel):
    """
    Payload sent by the frontend to kick off an orchestrated agent run.

    Fields
    ------
    user_id         — caller identity (required)
    message         — the user's natural-language instruction
    conversation_id — omit to create a new conversation
    attached_files  — storage refs for files already uploaded via /api/upload
    """

    user_id: str
    message: str
    conversation_id: str | None = None
    conversation_title: str | None = None   # client name — used as title for new conversations
    attached_files: list[AttachedFileRef] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Response sub-models
# ---------------------------------------------------------------------------

class PlanStepOut(BaseModel):
    """A single step in the execution plan (as returned to the frontend)."""
    step_id: str
    tool_name: str
    description: str
    depends_on: list[str] = Field(default_factory=list)
    rationale: str = ""


class StepResultOut(BaseModel):
    """Execution result for a single plan step."""
    step_id: str
    tool_name: str
    description: str = ""
    status: str                    # "completed" | "failed" | "skipped"
    error: str | None = None


class DataCardOut(BaseModel):
    """Structured UI card rendered from a tool's output."""
    step_id: str
    tool_name: str
    type: str                      # e.g. "life_in_super_analysis"
    title: str
    display_hint: str              # e.g. "recommendation_card"
    data: dict[str, Any]           # full tool output — frontend renders as needed


class ConversationOut(BaseModel):
    id: str
    title: str
    user_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class AgentRunOut(BaseModel):
    id: str
    intent: str | None = None
    status: str


# ---------------------------------------------------------------------------
# Top-level response
# ---------------------------------------------------------------------------

class AgentRunResponse(BaseModel):
    """
    Full structured response from an orchestrated agent run.

    The frontend uses this to:
      - Show the plan (plan_steps) with per-step status badges
      - Render data cards (data_cards) from tool results
      - Display the final adviser summary (assistant_message.content)
      - Navigate to the correct conversation (conversation.id)
    """

    # Conversation + message identifiers
    conversation: ConversationOut
    user_message_id: str
    assistant_message_id: str | None

    # The adviser's natural-language summary
    assistant_content: str

    # Orchestration metadata
    agent_run: AgentRunOut
    plan_steps: list[PlanStepOut]
    step_results: list[StepResultOut]
    data_cards: list[DataCardOut]

    # Set to True when the agent is asking the user for more information
    clarification_needed: bool = False
    clarification_question: str | None = None
    missing_context: list[str] = Field(default_factory=list)  # "section.field" dot-paths

    # What context was loaded for this run (sections, history depth, etc.)
    context_loaded: dict[str, Any] = Field(default_factory=dict)
