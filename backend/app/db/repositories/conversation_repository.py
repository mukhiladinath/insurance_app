"""
conversation_repository.py — CRUD helpers for the conversations collection.

Document shape:
  _id              : ObjectId (str in API layer)
  user_id          : str
  title            : str
  status           : str  ("active" | "archived")
  created_at       : datetime (UTC)
  updated_at       : datetime (UTC)
  last_message_at  : datetime | None
"""

from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id
from app.core.constants import ConversationStatus


def _serialize(doc: dict) -> dict:
    """Convert ObjectId fields to strings for safe passing to Pydantic."""
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class ConversationRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CONVERSATIONS]

    async def create(self, user_id: str, title: str) -> dict:
        now = utc_now()
        doc = {
            "user_id": user_id,
            "title": title,
            "status": ConversationStatus.ACTIVE,
            "created_at": now,
            "updated_at": now,
            "last_message_at": None,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def get_by_id(self, conversation_id: str) -> dict | None:
        doc = await self._col.find_one({"_id": to_object_id(conversation_id)})
        return _serialize(doc) if doc else None

    async def list_by_user(
        self, user_id: str, limit: int = 50, skip: int = 0
    ) -> list[dict]:
        cursor = (
            self._col.find({"user_id": user_id, "status": ConversationStatus.ACTIVE})
            .sort("updated_at", -1)
            .skip(skip)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]

    async def touch(self, conversation_id: str, last_message_at: datetime) -> None:
        """Update updated_at and last_message_at after a new message is added."""
        now = utc_now()
        await self._col.update_one(
            {"_id": to_object_id(conversation_id)},
            {"$set": {"updated_at": now, "last_message_at": last_message_at}},
        )

    async def update_title(self, conversation_id: str, title: str) -> None:
        await self._col.update_one(
            {"_id": to_object_id(conversation_id)},
            {"$set": {"title": title, "updated_at": utc_now()}},
        )

    async def delete(self, conversation_id: str) -> bool:
        """Hard-delete a conversation. Returns True if a document was deleted."""
        result = await self._col.delete_one({"_id": to_object_id(conversation_id)})
        return result.deleted_count > 0
