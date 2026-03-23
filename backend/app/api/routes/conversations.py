"""
conversations.py — Conversation and message retrieval routes.

GET /api/conversations                        → list conversations for a user
GET /api/conversations/{id}                   → get single conversation
GET /api/conversations/{id}/messages          → get all messages in a conversation
"""

from fastapi import APIRouter, HTTPException, Query
from app.services.conversation_service import ConversationService
from app.schemas.conversation import ConversationResponse, ConversationListItem, MessageResponse
from app.db.mongo import get_db

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    user_id: str = Query(..., description="User identifier"),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    """List active conversations for a user, ordered by most recently updated."""
    db = get_db()
    service = ConversationService(db)
    return await service.list_conversations(user_id=user_id, limit=limit, skip=skip)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(conversation_id: str):
    """Get a single conversation by ID."""
    db = get_db()
    service = ConversationService(db)
    conv = await service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found.")
    return conv


@router.get("/{conversation_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conversation_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    skip: int = Query(default=0, ge=0),
):
    """Retrieve all messages in a conversation, ordered oldest-first."""
    db = get_db()
    service = ConversationService(db)
    # Verify conversation exists
    conv = await service.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail=f"Conversation '{conversation_id}' not found.")
    return await service.list_messages(conversation_id=conversation_id, limit=limit, skip=skip)
