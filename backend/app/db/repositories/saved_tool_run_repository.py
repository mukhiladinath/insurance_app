"""
saved_tool_run_repository.py — CRUD for saved_tool_runs and run_steps collections.

saved_tool_runs document shape:
  _id              : ObjectId
  client_id        : str
  workspace_id     : str
  run_id           : str  (source agent_run)
  name             : str  (user-given or auto-generated)
  tool_names       : list[str]
  inputs_snapshot  : dict  (full inputs at time of save)
  step_results     : list[dict]
  data_cards       : list[dict]
  summary          : str  (adviser summary text)
  saved_at         : datetime
  saved_by         : str
  tags             : list[str]

run_steps document shape:
  _id                  : ObjectId
  run_id               : str
  client_id            : str
  step_id              : str
  tool_name            : str
  inputs               : dict
  output               : dict | None
  data_card            : dict | None
  status               : "completed" | "failed" | "skipped" | "cached"
  cache_source_run_id  : str | None
  started_at           : datetime
  completed_at         : datetime | None
  error                : str | None
"""

import logging
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import DESCENDING

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id

logger = logging.getLogger(__name__)


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class RunStepRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.RUN_STEPS]

    async def bulk_insert(self, steps: list[dict]) -> None:
        if not steps:
            return
        now = utc_now()
        docs = [{**s, "created_at": now} for s in steps]
        await self._col.insert_many(docs)

    async def get_by_run(self, run_id: str) -> list[dict]:
        cursor = self._col.find({"run_id": run_id}).sort("step_id", 1)
        docs = await cursor.to_list(length=100)
        return [_serialize(d) for d in docs]


class SavedToolRunRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.SAVED_TOOL_RUNS]

    async def save(
        self,
        client_id: str,
        workspace_id: str,
        run_id: str,
        name: str,
        tool_names: list[str],
        inputs_snapshot: dict,
        step_results: list[dict],
        data_cards: list[dict],
        summary: str,
        saved_by: str,
        tags: list[str] | None = None,
    ) -> dict:
        now = utc_now()
        doc = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "name": name,
            "tool_names": tool_names,
            "inputs_snapshot": inputs_snapshot,
            "step_results": step_results,
            "data_cards": data_cards,
            "summary": summary,
            "saved_at": now,
            "saved_by": saved_by,
            "tags": tags or [],
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def get_by_id(self, saved_run_id: str) -> dict | None:
        oid = to_object_id(saved_run_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return _serialize(doc) if doc else None

    async def list_by_client(
        self,
        client_id: str,
        tool_name: str | None = None,
        limit: int = 20,
    ) -> list[dict]:
        query: dict[str, Any] = {"client_id": client_id}
        if tool_name:
            query["tool_names"] = tool_name
        cursor = (
            self._col.find(query)
            .sort("saved_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]

    async def delete(self, saved_run_id: str) -> bool:
        oid = to_object_id(saved_run_id)
        if oid is None:
            return False
        result = await self._col.delete_one({"_id": oid})
        return result.deleted_count > 0

    async def update_step_results(self, saved_run_id: str, step_results: list[dict]) -> dict | None:
        """Replace step_results (e.g. after attaching comparison_envelope)."""
        oid = to_object_id(saved_run_id)
        if oid is None:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$set": {"step_results": step_results, "updated_at": utc_now()}},
            return_document=True,
        )
        return _serialize(doc) if doc else None

    async def update_name(
        self, saved_run_id: str, name: str, tags: list[str]
    ) -> dict | None:
        oid = to_object_id(saved_run_id)
        if oid is None:
            return None
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$set": {"name": name, "tags": tags}},
            return_document=True,
        )
        return _serialize(doc) if doc else None
