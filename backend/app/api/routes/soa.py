"""
soa.py — SOA generation API routes.

POST /api/soa/generate
  Generate (or regenerate with answers) SOA sections for a conversation.
  Saves the result to the conversation document for panel persistence.

GET /api/soa/{conversation_id}
  Fetch the saved SOA draft for a conversation (used on chat load).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/soa", tags=["soa"])
logger = logging.getLogger(__name__)


class SOAGenerateRequest(BaseModel):
    conversation_id: str
    answers: Optional[dict[str, str]] = None  # {question_id: answer_text}


class SOAMissingQuestion(BaseModel):
    id: str
    question: str


class SOASection(BaseModel):
    template_number: int
    template_name: str
    title: str
    our_recommendation: str
    why_appropriate: str
    what_to_consider: str
    more_information: str


class SOAGenerateResponse(BaseModel):
    sections: list[SOASection]
    missing_questions: list[SOAMissingQuestion]


async def _save_soa_draft(db, conversation_id: str, sections: list, missing_questions: list) -> None:
    """Upsert soa_draft onto the conversation document."""
    from app.db.collections import CONVERSATIONS
    from app.utils.ids import to_object_id
    await db[CONVERSATIONS].update_one(
        {"_id": to_object_id(conversation_id)},
        {"$set": {
            "soa_draft": {
                "sections": [s.model_dump() for s in sections],
                "missing_questions": [q.model_dump() for q in missing_questions],
            }
        }},
    )


@router.post("/generate", response_model=SOAGenerateResponse)
async def generate_soa(req: SOAGenerateRequest):
    """Generate SOA sections and persist the result to the conversation."""
    try:
        from app.db.mongo import get_db
        from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
        from app.db.collections import MESSAGES as messages_collection_name
        from app.services.soa_service import generate_soa as _generate_soa

        db = get_db()

        # Load conversation memory (client facts + summary)
        memory_repo = ConversationMemoryRepository(db)
        client_memory = await memory_repo.get_or_create(req.conversation_id)

        # Load recent messages for conversation context
        msg_col = db[messages_collection_name]
        raw_messages = await msg_col.find(
            {"conversation_id": req.conversation_id},
            {"role": 1, "content": 1, "_id": 0},
        ).sort("created_at", 1).to_list(length=30)

        recent_messages = [
            {"role": m.get("role", ""), "content": m.get("content", "")}
            for m in raw_messages
        ]

        result = await _generate_soa(client_memory, recent_messages, req.answers)

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        sections = []
        for s in result.get("sections", []):
            sections.append(SOASection(
                template_number=s.get("template_number", 0),
                template_name=s.get("template_name", ""),
                title=s.get("title", s.get("template_name", "")),
                our_recommendation=s.get("our_recommendation", ""),
                why_appropriate=s.get("why_appropriate", ""),
                what_to_consider=s.get("what_to_consider", ""),
                more_information=s.get("more_information", ""),
            ))

        missing = [
            SOAMissingQuestion(id=q["id"], question=q["question"])
            for q in result.get("missing_questions", [])
        ]

        # Persist so the panel can be restored when switching back to this chat
        try:
            await _save_soa_draft(db, req.conversation_id, sections, missing)
        except Exception as save_exc:
            logger.warning("Could not persist SOA draft: %s", save_exc)

        return SOAGenerateResponse(sections=sections, missing_questions=missing)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("SOA generation endpoint error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{conversation_id}", response_model=SOAGenerateResponse)
async def get_soa_draft(conversation_id: str):
    """Return the saved SOA draft for a conversation, or 404 if none exists."""
    try:
        from app.db.mongo import get_db
        from app.db.collections import CONVERSATIONS
        from app.utils.ids import to_object_id

        db = get_db()
        doc = await db[CONVERSATIONS].find_one(
            {"_id": to_object_id(conversation_id)},
            {"soa_draft": 1},
        )

        if not doc or not doc.get("soa_draft"):
            raise HTTPException(status_code=404, detail="No SOA draft found")

        draft = doc["soa_draft"]

        sections = [SOASection(**s) for s in draft.get("sections", [])]
        missing = [SOAMissingQuestion(**q) for q in draft.get("missing_questions", [])]

        return SOAGenerateResponse(sections=sections, missing_questions=missing)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("SOA draft fetch error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
