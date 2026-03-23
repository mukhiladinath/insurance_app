"""
chat.py — Chat routes.

POST /api/chat/message
  Receives a user message, runs the full agent workflow, returns a structured response.
"""

import logging
from fastapi import APIRouter, HTTPException
from app.schemas.chat import ChatMessageRequest, ChatMessageResponse
from app.services.chat_service import ChatService
from app.db.mongo import get_db

router = APIRouter(prefix="/chat", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/message", response_model=ChatMessageResponse)
async def send_message(req: ChatMessageRequest):
    """
    Process a user message through the full LangGraph agent workflow.

    - Creates a conversation if conversation_id is omitted.
    - Saves the user message to MongoDB.
    - Runs intent classification, optional tool execution, and response composition.
    - Persists results and returns a fully structured response.
    """
    db = get_db()
    service = ChatService(db)

    try:
        return await service.handle_message(req)
    except ValueError as exc:
        logger.warning("Chat message validation error: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Chat message runtime error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in chat endpoint: %s", exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")
