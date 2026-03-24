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


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: str):
    """Hard-delete a conversation and its messages."""
    from app.db.collections import MESSAGES
    db = get_db()
    conv_repo = ConversationRepository(db)
    deleted = await conv_repo.delete(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    # Also remove all messages belonging to this conversation
    await db[MESSAGES].delete_many({"conversation_id": conversation_id})


@router.get("/{conversation_id}/documents")
async def list_documents(conversation_id: str):
    """
    List all uploaded documents for a conversation.

    Returns documents linked to this conversation AND documents uploaded by the
    same user that have no conversation_id yet (uploaded before the first message).
    """
    from app.db.repositories.document_repository import DocumentRepository
    from app.db.repositories.conversation_repository import ConversationRepository
    from pydantic import BaseModel
    from datetime import datetime

    class DocumentOut(BaseModel):
        id: str
        filename: str
        content_type: str
        size_bytes: int
        facts_found: bool
        facts_summary: str
        created_at: datetime

    db = get_db()
    doc_repo = DocumentRepository(db)
    conv_repo = ConversationRepository(db)

    # Primary: documents explicitly linked to this conversation
    linked = await doc_repo.list_by_conversation(conversation_id)
    linked_ids = {d["id"] for d in linked}

    # Fallback: documents with no conversation_id for this user
    # (uploaded before the conversation was created, not yet linked by load_documents)
    conv = await conv_repo.get_by_id(conversation_id)
    unlinked = []
    if conv:
        unlinked = await doc_repo.list_unlinked_by_user(conv["user_id"])

    all_docs = linked + [d for d in unlinked if d["id"] not in linked_ids]
    all_docs.sort(key=lambda d: d.get("created_at") or datetime.min)

    result = []
    for d in all_docs:
        facts = d.get("extracted_facts") or {}
        result.append(DocumentOut(
            id=d["id"],
            filename=d.get("filename", "unknown"),
            content_type=d.get("content_type", ""),
            size_bytes=d.get("size_bytes", 0),
            facts_found=bool(facts),
            facts_summary=", ".join(facts.keys()) if facts else "No facts extracted",
            created_at=d.get("created_at"),
        ))
    return result


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
