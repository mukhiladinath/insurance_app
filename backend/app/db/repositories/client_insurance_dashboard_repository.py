"""Persisted insurance dashboard documents per client."""

from __future__ import annotations

import logging
from typing import Any

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


class ClientInsuranceDashboardRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CLIENT_INSURANCE_DASHBOARDS]

    async def create(
        self,
        *,
        client_id: str,
        organization_id: str | None,
        title: str,
        dashboard_type: str,
        source_analysis_ids: list[str],
        source_tool_ids: list[str],
        source_recommendation_ids: list[str] | None,
        assumptions: dict[str, Any],
        resolved_inputs: dict[str, Any],
        projection_data: dict[str, Any],
        dashboard_spec: dict[str, Any],
        ai_context_snapshot: dict[str, Any] | None,
        created_by: str | None,
        status: str = "active",
    ) -> dict:
        now = utc_now()
        doc = {
            "client_id": client_id,
            "organization_id": organization_id,
            "title": title,
            "dashboard_type": dashboard_type,
            "source_analysis_ids": source_analysis_ids,
            "source_tool_ids": source_tool_ids,
            "source_recommendation_ids": source_recommendation_ids or [],
            "assumptions": assumptions,
            "resolved_inputs": resolved_inputs,
            "projection_data": projection_data,
            "dashboard_spec": dashboard_spec,
            "ai_context_snapshot": ai_context_snapshot or {},
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
            "version": 1,
            "status": status,
        }
        res = await self._col.insert_one(doc)
        saved = await self._col.find_one({"_id": res.inserted_id})
        return _serialize(saved) or {}

    async def list_for_client(self, client_id: str, limit: int = 50) -> list[dict]:
        cur = self._col.find({"client_id": client_id}).sort("created_at", DESCENDING).limit(limit)
        docs = await cur.to_list(length=limit)
        return [d for d in (_serialize(x) for x in docs) if d]

    async def get(self, dashboard_id: str, client_id: str) -> dict | None:
        try:
            oid = to_object_id(dashboard_id)
        except ValueError:
            return None
        doc = await self._col.find_one({"_id": oid, "client_id": client_id})
        return _serialize(doc)

    async def update_regeneration(
        self,
        dashboard_id: str,
        client_id: str,
        *,
        assumptions: dict[str, Any],
        resolved_inputs: dict[str, Any],
        projection_data: dict[str, Any],
        dashboard_spec: dict[str, Any],
    ) -> dict | None:
        try:
            oid = to_object_id(dashboard_id)
        except ValueError:
            return None
        doc = await self._col.find_one({"_id": oid, "client_id": client_id})
        if not doc:
            return None
        ver = int(doc.get("version") or 1) + 1
        now = utc_now()
        updated = await self._col.find_one_and_update(
            {"_id": oid, "client_id": client_id},
            {
                "$set": {
                    "assumptions": assumptions,
                    "resolved_inputs": resolved_inputs,
                    "projection_data": projection_data,
                    "dashboard_spec": dashboard_spec,
                    "version": ver,
                    "updated_at": now,
                }
            },
            return_document=True,
        )
        return _serialize(updated)
