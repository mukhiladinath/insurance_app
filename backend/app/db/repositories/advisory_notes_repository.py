"""
advisory_notes_repository.py — CRUD for the agent_workspace collection.

One document per conversation stores two things:

  advisory_notes: dict
    Keyed by tool_name. Each entry is a structured conclusion extracted after
    a tool run, e.g.:
      {
        "purchase_retain_life_tpd_policy": {
          "verdict":           "REPLACE",
          "recommendation":    "Replace existing policy with higher sum insured",
          "key_numbers":       {"recommended_life_sum": 1200000, "tpd_gap": 450000},
          "key_findings":      "Existing cover $600k; need $1.2M based on income...",
          "analysed_at":       "2026-03-26T10:30:00Z",
          "agent_run_id":      "...",
        }
      }

  scratch_pad: list[dict]
    Append-only list of agent working notes, e.g.:
      [
        {
          "entry_id":      "sp_001",
          "category":      "observation",     # observation | hypothesis | todo | flag
          "content":       "Client seems uncertain about IP waiting period",
          "agent_run_id":  "...",
          "created_at":    "...",
        }
      ]

Both are loaded selectively by load_memory_smart and written by
distill_advisory_node after each run.
"""

import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.collections import AGENT_WORKSPACE
from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class AdvisoryNotesRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[AGENT_WORKSPACE]

    async def get_by_conversation(self, conversation_id: str) -> dict | None:
        doc = await self._col.find_one({"conversation_id": conversation_id})
        return _serialize(doc) if doc else None

    async def get_or_create(self, conversation_id: str) -> dict:
        doc = await self.get_by_conversation(conversation_id)
        if doc:
            return doc
        now = utc_now()
        new_doc = {
            "conversation_id": conversation_id,
            "advisory_notes": {},
            "scratch_pad": [],
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.insert_one(new_doc)
        new_doc["_id"] = result.inserted_id
        return _serialize(new_doc)

    async def upsert_advisory_note(
        self,
        conversation_id: str,
        tool_name: str,
        note: dict,
    ) -> None:
        """
        Write or overwrite the advisory conclusion for a specific tool.
        Uses dot-notation update to avoid overwriting other tools' notes.
        """
        await self._col.update_one(
            {"conversation_id": conversation_id},
            {
                "$set": {
                    f"advisory_notes.{tool_name}": note,
                    "updated_at": utc_now(),
                },
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "scratch_pad": [],
                    "created_at": utc_now(),
                },
            },
            upsert=True,
        )
        logger.debug(
            "advisory_notes: upserted note for tool=%s conv=%s", tool_name, conversation_id
        )

    async def append_scratch_pad(
        self,
        conversation_id: str,
        entry: dict,
    ) -> None:
        """Append a single scratch pad entry."""
        await self._col.update_one(
            {"conversation_id": conversation_id},
            {
                "$push": {"scratch_pad": entry},
                "$set": {"updated_at": utc_now()},
                "$setOnInsert": {
                    "conversation_id": conversation_id,
                    "advisory_notes": {},
                    "created_at": utc_now(),
                },
            },
            upsert=True,
        )

    async def get_advisory_notes(self, conversation_id: str) -> dict:
        """Return just the advisory_notes dict for a conversation."""
        doc = await self._col.find_one(
            {"conversation_id": conversation_id},
            {"advisory_notes": 1},
        )
        if not doc:
            return {}
        return doc.get("advisory_notes", {})

    async def get_scratch_pad(self, conversation_id: str) -> list[dict]:
        """Return the scratch pad entries for a conversation."""
        doc = await self._col.find_one(
            {"conversation_id": conversation_id},
            {"scratch_pad": 1},
        )
        if not doc:
            return []
        return doc.get("scratch_pad", [])
