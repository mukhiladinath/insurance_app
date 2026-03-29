"""
client_analysis_output_repository.py — Persisted LLM narratives from analysis tool runs.

Each document is one completed orchestrator run that included at least one
analysis-style tool (insurance engines, SOA). The `content` field holds the
synthesized markdown from the summarizer and may be edited by the adviser.
"""

from __future__ import annotations

import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id

logger = logging.getLogger(__name__)


def _serialize(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


class ClientAnalysisOutputRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CLIENT_ANALYSIS_OUTPUTS]

    async def create(
        self,
        client_id: str,
        instruction: str,
        tool_ids: list[str],
        step_labels: list[str],
        content: str,
        source: str = "manual",
        structured_step_results: list[dict[str, Any]] | None = None,
    ) -> dict:
        now = utc_now()
        doc = {
            "client_id": client_id,
            "instruction": instruction,
            "tool_ids": tool_ids,
            "step_labels": step_labels,
            "content": content,
            "source": source,
            "structured_step_results": structured_step_results or [],
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.insert_one(doc)
        saved = await self._col.find_one({"_id": result.inserted_id})
        return _serialize(saved) or {}

    async def list_for_client(self, client_id: str, limit: int = 100) -> list[dict]:
        cursor = (
            self._col.find({"client_id": client_id})
            .sort("created_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [d for d in (_serialize(x) for x in docs) if d]

    async def get(self, output_id: str, client_id: str) -> dict | None:
        try:
            oid = to_object_id(output_id)
        except ValueError:
            return None
        doc = await self._col.find_one({"_id": oid, "client_id": client_id})
        return _serialize(doc)

    async def update_content(self, output_id: str, client_id: str, content: str) -> dict | None:
        try:
            oid = to_object_id(output_id)
        except ValueError:
            return None
        now = utc_now()
        doc = await self._col.find_one_and_update(
            {"_id": oid, "client_id": client_id},
            {"$set": {"content": content, "updated_at": now}},
            return_document=True,
        )
        return _serialize(doc)
