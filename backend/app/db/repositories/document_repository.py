"""
document_repository.py — MongoDB repository for uploaded document records.

Document schema:
  _id              : ObjectId (used as storage_ref on the frontend)
  user_id          : str
  client_id        : str | None  (set when uploading from a client profile / workspace)
  conversation_id  : str | None  (None if uploaded before first message)
  filename         : str
  content_type     : str
  size_bytes       : int
  storage_path     : str          (relative path from backend root, e.g. "uploads/abc123/file.pdf")
  extracted_text   : str          (full text extracted from the document)
  extracted_facts  : dict         (canonical memory schema delta — client facts found in doc)
  facts_merged     : bool         (True once facts have been merged into conversation_memory)
  created_at       : datetime
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.collections import DOCUMENTS

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serialisable dict."""
    if not doc:
        return {}
    d = dict(doc)
    d["id"] = str(d.pop("_id"))
    return d


class DocumentRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[DOCUMENTS]

    async def create(
        self,
        *,
        user_id: str,
        client_id: str | None = None,
        conversation_id: str | None,
        filename: str,
        content_type: str,
        size_bytes: int,
        storage_path: str,
        extracted_text: str,
        extracted_facts: dict,
    ) -> dict:
        """Insert a new document record and return it with a string id."""
        now = datetime.now(timezone.utc)
        doc = {
            "user_id":         user_id,
            "client_id":       client_id,
            "conversation_id": conversation_id,
            "filename":        filename,
            "content_type":    content_type,
            "size_bytes":      size_bytes,
            "storage_path":    storage_path,
            "extracted_text":  extracted_text,
            "extracted_facts": extracted_facts,
            "facts_merged":    False,
            "created_at":      now,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def get_by_id(self, doc_id: str) -> dict | None:
        """Fetch a document record by its string ObjectId."""
        try:
            doc = await self._col.find_one({"_id": ObjectId(doc_id)})
        except Exception:
            return None
        return _serialize(doc) if doc else None

    async def list_by_conversation(self, conversation_id: str) -> list[dict]:
        """All documents for a conversation, ordered by upload time."""
        cursor = self._col.find(
            {"conversation_id": conversation_id}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=100)
        return [_serialize(d) for d in docs]

    async def list_for_client(
        self,
        client_id: str,
        user_id: str,
        conversation_id: str | None,
    ) -> list[dict]:
        """
        Documents visible for a client workspace: tagged with client_id and/or
        linked to the active conversation (same advisor user_id).
        """
        clauses: list[dict] = [{"client_id": client_id}]
        if conversation_id:
            clauses.append({"conversation_id": conversation_id})
        cursor = (
            self._col.find({"user_id": user_id, "$or": clauses})
            .sort("created_at", 1)
        )
        docs = await cursor.to_list(length=200)
        return [_serialize(d) for d in docs]

    async def list_unlinked_by_user(self, user_id: str) -> list[dict]:
        """Documents uploaded by a user that have no conversation_id yet."""
        cursor = self._col.find(
            {"user_id": user_id, "conversation_id": None}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=100)
        return [_serialize(d) for d in docs]

    async def list_unmerged(self, conversation_id: str) -> list[dict]:
        """Documents whose facts have not yet been merged into conversation_memory."""
        cursor = self._col.find(
            {"conversation_id": conversation_id, "facts_merged": False}
        ).sort("created_at", 1)
        docs = await cursor.to_list(length=100)
        return [_serialize(d) for d in docs]

    async def mark_merged(self, doc_id: str) -> None:
        """Mark a document's facts as merged into conversation_memory."""
        try:
            await self._col.update_one(
                {"_id": ObjectId(doc_id)},
                {"$set": {"facts_merged": True}},
            )
        except Exception as exc:
            logger.warning("mark_merged failed for doc %s: %s", doc_id, exc)

    async def attach_conversation(self, doc_id: str, conversation_id: str) -> None:
        """Associate an uploaded document with a conversation (set post-upload)."""
        try:
            await self._col.update_one(
                {"_id": ObjectId(doc_id)},
                {"$set": {"conversation_id": conversation_id}},
            )
        except Exception as exc:
            logger.warning("attach_conversation failed for doc %s: %s", doc_id, exc)
