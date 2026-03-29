"""Pending dashboard generation sessions (resume after missing fields)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import collections as col
from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


def _serialize(doc: dict | None) -> dict | None:
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    return doc


class InsuranceDashboardSessionRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.INSURANCE_DASHBOARD_SESSIONS]

    async def create(
        self,
        *,
        client_id: str,
        dashboard_type: str,
        instruction: str,
        analysis_output_id: str | None,
        step_index: int | None,
        second_analysis_output_id: str | None,
        second_step_index: int | None,
        accumulated_overrides: dict[str, Any],
    ) -> dict:
        token = str(uuid.uuid4())
        now = utc_now()
        doc = {
            "client_id": client_id,
            "session_token": token,
            "dashboard_type": dashboard_type,
            "instruction": instruction,
            "analysis_output_id": analysis_output_id,
            "step_index": step_index,
            "second_analysis_output_id": second_analysis_output_id,
            "second_step_index": second_step_index,
            "accumulated_overrides": accumulated_overrides,
            "status": "pending",
            "created_at": now,
            "updated_at": now,
        }
        res = await self._col.insert_one(doc)
        doc = await self._col.find_one({"_id": res.inserted_id})
        logger.info("insurance_dashboard_session created token=%s client=%s", token, client_id)
        return _serialize(doc) or {}

    async def get_by_token(self, token: str) -> dict | None:
        doc = await self._col.find_one({"session_token": token})
        return _serialize(doc)

    async def update_overrides(self, token: str, new_overrides: dict[str, Any]) -> dict | None:
        doc = await self._col.find_one({"session_token": token, "status": "pending"})
        if not doc:
            return None
        acc = dict(doc.get("accumulated_overrides") or {})
        acc.update(new_overrides)
        now = utc_now()
        await self._col.update_one(
            {"_id": doc["_id"]},
            {"$set": {"accumulated_overrides": acc, "updated_at": now}},
        )
        return await self.get_by_token(token)

    async def complete(self, token: str) -> None:
        await self._col.update_one(
            {"session_token": token},
            {"$set": {"status": "completed", "updated_at": utc_now()}},
        )
