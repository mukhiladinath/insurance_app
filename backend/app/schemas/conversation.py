"""
conversation.py — Pydantic schemas for conversations and messages.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Conversation
# -------------------------------------------------------------------------

class ConversationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None


class ConversationListItem(BaseModel):
    id: str
    title: str
    status: str
    updated_at: datetime
    last_message_at: datetime | None = None


# -------------------------------------------------------------------------
# Message
# -------------------------------------------------------------------------

class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    agent_run_id: str | None = None
    role: str
    content: str
    structured_payload: dict[str, Any] | None = None
    created_at: datetime
