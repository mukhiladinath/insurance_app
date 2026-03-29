"""
pending_clarification_repository.py — CRUD for pending_clarifications collection.

pending_clarifications document shape:
  _id                    : ObjectId
  client_id              : str
  workspace_id           : str
  run_id                 : str  (the agent_run that was blocked)
  conversation_id        : str
  question               : str  (natural-language question for the user)
  missing_fields         : list[dict]
    field_path  : str   e.g. "personal.age"
    label       : str   e.g. "Client Age"
    section     : str
    required    : bool
  frozen_plan            : list[dict]  (full tool_plan at time of blocking)
  frozen_step_results    : list[dict]  (any steps completed before the block)
  frozen_inputs_snapshot : dict        (factfind + context at blocking time)
  status                 : "pending" | "resolved" | "expired"
  resume_token           : str  (UUID — returned to frontend, sent back on answer)
  created_at             : datetime
  resolved_at            : datetime | None
  answer                 : str | None  (user's answer text)
"""

import logging
import uuid
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class PendingClarificationRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.PENDING_CLARIFICATIONS]

    async def create(
        self,
        client_id: str,
        workspace_id: str,
        run_id: str,
        conversation_id: str,
        question: str,
        missing_fields: list[dict],
        frozen_plan: list[dict],
        frozen_step_results: list[dict],
        frozen_inputs_snapshot: dict,
    ) -> dict:
        resume_token = str(uuid.uuid4())
        now = utc_now()
        doc = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "conversation_id": conversation_id,
            "question": question,
            "missing_fields": missing_fields,
            "frozen_plan": frozen_plan,
            "frozen_step_results": frozen_step_results,
            "frozen_inputs_snapshot": frozen_inputs_snapshot,
            "status": "pending",
            "resume_token": resume_token,
            "created_at": now,
            "resolved_at": None,
            "answer": None,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        logger.info(
            "pending_clarification: created token=%s for client=%s run=%s",
            resume_token, client_id, run_id,
        )
        return _serialize(doc)

    async def get_by_token(self, resume_token: str) -> dict | None:
        doc = await self._col.find_one({"resume_token": resume_token})
        return _serialize(doc) if doc else None

    async def get_pending_for_client(self, client_id: str) -> dict | None:
        """Return the most recent pending clarification for a client, if any."""
        from pymongo import DESCENDING
        doc = await self._col.find_one(
            {"client_id": client_id, "status": "pending"},
            sort=[("created_at", DESCENDING)],
        )
        return _serialize(doc) if doc else None

    async def resolve(self, resume_token: str, answer: str) -> dict | None:
        doc = await self._col.find_one_and_update(
            {"resume_token": resume_token, "status": "pending"},
            {
                "$set": {
                    "status": "resolved",
                    "answer": answer,
                    "resolved_at": utc_now(),
                }
            },
            return_document=True,
        )
        return _serialize(doc) if doc else None

    async def expire_old(self, client_id: str) -> None:
        """Expire any pending clarifications for a client when a new run starts fresh."""
        await self._col.update_many(
            {"client_id": client_id, "status": "pending"},
            {"$set": {"status": "expired", "resolved_at": utc_now()}},
        )
