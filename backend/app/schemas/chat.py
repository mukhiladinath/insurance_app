"""
chat.py — Pydantic schemas for the chat endpoint request/response contract.

This defines the primary API surface consumed by the frontend.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Inbound — POST /api/chat/message
# -------------------------------------------------------------------------

class AttachedFileMetadata(BaseModel):
    """Placeholder for future file attachment support."""
    filename: str
    content_type: str
    size_bytes: int | None = None
    storage_ref: str | None = None  # future: blob storage reference


class ChatMessageRequest(BaseModel):
    user_id: str = Field(..., description="Caller-supplied user identifier")
    conversation_id: str | None = Field(
        default=None,
        description="Existing conversation to continue; omit to create a new one",
    )
    message: str = Field(..., min_length=1, max_length=32_000)
    attached_files: list[AttachedFileMetadata] = Field(default_factory=list)

    # Optional structured tool input — caller may pre-fill tool parameters
    # to short-circuit the intent classification step.
    tool_hint: str | None = Field(
        default=None,
        description="Optional tool name hint to assist intent classification",
    )
    tool_input: dict[str, Any] | None = Field(
        default=None,
        description="Pre-structured tool input payload (skips LLM extraction if provided)",
    )


# -------------------------------------------------------------------------
# Outbound — POST /api/chat/message
# -------------------------------------------------------------------------

class AgentRunSummary(BaseModel):
    id: str
    intent: str | None = None
    selected_tool: str | None = None
    status: str


class ToolResultEnvelope(BaseModel):
    tool_name: str
    tool_version: str
    status: str
    payload: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class UserMessageOut(BaseModel):
    id: str
    role: str = "user"
    content: str
    created_at: datetime


class AssistantMessageOut(BaseModel):
    id: str
    role: str = "assistant"
    content: str
    structured_payload: dict[str, Any] | None = None
    created_at: datetime


class ConversationOut(BaseModel):
    id: str
    title: str
    user_id: str
    status: str
    created_at: datetime
    updated_at: datetime


class ChatMessageResponse(BaseModel):
    conversation: ConversationOut
    user_message: UserMessageOut
    assistant_message: AssistantMessageOut
    agent_run: AgentRunSummary
    tool_result: ToolResultEnvelope | None = None
