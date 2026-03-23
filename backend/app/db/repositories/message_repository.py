"""
message_repository.py — CRUD helpers for the messages collection.

Document shape:
  _id                : ObjectId
  conversation_id    : str
  agent_run_id       : str | None
  role               : str  ("user" | "assistant" | "tool" | "system")
  content            : str
  structured_payload : dict | None  (tool result, metadata, etc.)
  created_at         : datetime (UTC)
"""

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class MessageRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.MESSAGES]

    async def create(
        self,
        conversation_id: str,
        role: str,
        content: str,
        agent_run_id: str | None = None,
        structured_payload: dict | None = None,
    ) -> dict:
        now = utc_now()
        doc = {
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "role": role,
            "content": content,
            "structured_payload": structured_payload,
            "created_at": now,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def list_by_conversation(
        self, conversation_id: str, limit: int = 100, skip: int = 0
    ) -> list[dict]:
        cursor = (
            self._col.find({"conversation_id": conversation_id})
            .sort("created_at", 1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]

    async def get_recent(self, conversation_id: str, n: int = 20) -> list[dict]:
        """Return the n most recent messages ordered oldest-first (for context)."""
        cursor = (
            self._col.find({"conversation_id": conversation_id})
            .sort("created_at", -1)
            .limit(n)
        )
        docs = await cursor.to_list(length=n)
        docs.reverse()  # oldest first for LLM context
        return [_serialize(d) for d in docs]
