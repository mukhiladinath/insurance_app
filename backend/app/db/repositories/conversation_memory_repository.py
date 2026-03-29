"""
conversation_memory_repository.py — CRUD for conversation_memory and memory_events collections.

conversation_memory document shape:
  _id               : ObjectId
  conversation_id   : str  (unique index)
  version           : int  (incremented on every update)
  turn_count        : int  (incremented on every user turn)
  client_facts      : dict — canonical nested facts by domain
    personal        : dict
    financial       : dict
    insurance       : dict
    health          : dict
    goals           : dict
  field_meta        : dict — "section.field" → {source_message_id, updated_at, confidence, status, evidence_text}
  summary_memory    : dict — {text, last_summarized_at, turn_count_at_summary, summarized_through_message_id}
  created_at        : datetime (UTC)
  updated_at        : datetime (UTC)

memory_events document shape:
  _id               : ObjectId
  conversation_id   : str
  source_message_id : str
  event_type        : str  "new_fact" | "correction" | "uncertain" | "revoke" | "update"
  field_path        : str  e.g. "financial.super_balance"
  old_value         : Any
  new_value         : Any
  confidence        : float
  evidence_text     : str
  created_at        : datetime (UTC)
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from pymongo import ASCENDING

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


def _empty_memory(conversation_id: str) -> dict:
    """Return a freshly initialised (unsaved) memory document."""
    now = utc_now()
    return {
        "conversation_id": conversation_id,
        "version": 0,
        "turn_count": 0,
        "client_facts": {
            "personal": {},
            "financial": {},
            "insurance": {},
            "health": {},
            "goals": {},
        },
        "field_meta": {},
        "summary_memory": {
            "text": "",
            "last_summarized_at": None,
            "turn_count_at_summary": 0,
            "summarized_through_message_id": None,
        },
        "created_at": now,
        "updated_at": now,
    }


class ConversationMemoryRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CONVERSATION_MEMORY]

    async def get_by_conversation_id(self, conversation_id: str) -> dict | None:
        """Return the memory document or None if not yet initialised."""
        doc = await self._col.find_one({"conversation_id": conversation_id})
        return _serialize(doc) if doc else None

    async def get_or_create(self, conversation_id: str) -> dict:
        """
        Return the existing memory document, or create and return an empty one.
        Uses find_one_and_update with upsert=True to avoid race conditions.
        """
        now = utc_now()
        empty = _empty_memory(conversation_id)

        # $setOnInsert only fires on INSERT — existing documents are not modified.
        result = await self._col.find_one_and_update(
            {"conversation_id": conversation_id},
            {"$setOnInsert": empty},
            upsert=True,
            return_document=True,
        )
        return _serialize(result)

    async def upsert(self, memory: dict) -> dict:
        """
        Persist the full memory document. Increments version and updates updated_at.
        Accepts a dict that may or may not have an "id" key (from serialization).
        """
        conversation_id = memory["conversation_id"]
        now = utc_now()

        # Build the $set payload — everything except the id fields
        payload = {k: v for k, v in memory.items() if k not in ("id", "_id")}
        payload["updated_at"] = now
        payload["version"] = memory.get("version", 0) + 1

        result = await self._col.find_one_and_update(
            {"conversation_id": conversation_id},
            {"$set": payload},
            upsert=True,
            return_document=True,
        )
        return _serialize(result)

    async def patch_facts(self, conversation_id: str, sections: dict) -> None:
        """
        Patch specific fields in client_facts without touching other memory.

        Args:
            conversation_id: Target conversation.
            sections: Dict of {section_name: {field: value, ...}}.
                      A value of None means unset that field.
        """
        set_ops: dict = {"updated_at": utc_now()}
        unset_ops: dict = {}

        for section, fields in sections.items():
            for field, value in fields.items():
                key = f"client_facts.{section}.{field}"
                if value is None:
                    unset_ops[key] = ""
                else:
                    set_ops[key] = value

        update: dict = {"$set": set_ops}
        if unset_ops:
            update["$unset"] = unset_ops

        await self._col.update_one(
            {"conversation_id": conversation_id},
            update,
            upsert=True,
        )

    async def increment_turn_count(self, conversation_id: str) -> None:
        """Increment turn_count by 1. Called from update_memory node."""
        await self._col.update_one(
            {"conversation_id": conversation_id},
            {
                "$inc": {"turn_count": 1},
                "$set": {"updated_at": utc_now()},
            },
        )


class MemoryEventRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.MEMORY_EVENTS]

    async def create_many(self, events: list[dict]) -> None:
        """Insert multiple memory event records in one operation."""
        if not events:
            return
        now = utc_now()
        docs = [{**e, "created_at": now} for e in events]
        await self._col.insert_many(docs)

    async def list_by_conversation(
        self, conversation_id: str, limit: int = 100
    ) -> list[dict]:
        cursor = (
            self._col.find({"conversation_id": conversation_id})
            .sort("created_at", ASCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]
