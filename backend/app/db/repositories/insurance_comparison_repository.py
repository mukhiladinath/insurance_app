"""Persistence for insurance_tool_comparisons."""

from __future__ import annotations

from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id


def _serialize(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


class InsuranceComparisonRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.INSURANCE_TOOL_COMPARISONS]

    async def create(
        self,
        *,
        client_id: str,
        left_tool_run_id: str,
        right_tool_run_id: str,
        left_tool_name: str,
        right_tool_name: str,
        comparison_type: str,
        comparison_mode: str,
        comparison_result: dict[str, Any],
        fact_find_version: str | int | None,
        created_by: str,
    ) -> dict:
        now = utc_now()
        doc = {
            "client_id": client_id,
            "left_tool_run_id": left_tool_run_id,
            "right_tool_run_id": right_tool_run_id,
            "left_tool_name": left_tool_name,
            "right_tool_name": right_tool_name,
            "comparison_type": comparison_type,
            "comparison_mode": comparison_mode,
            "comparison_result": comparison_result,
            "fact_find_version": fact_find_version,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        res = await self._col.insert_one(doc)
        doc["_id"] = res.inserted_id
        return _serialize(doc)  # type: ignore[return-value]

    async def list_by_client(self, client_id: str, limit: int = 50) -> list[dict]:
        cur = self._col.find({"client_id": client_id}).sort("created_at", DESCENDING).limit(limit)
        docs = await cur.to_list(length=limit)
        return [_serialize(d) for d in docs]

    async def get_by_id(self, doc_id: str) -> dict | None:
        oid = to_object_id(doc_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return _serialize(doc)
