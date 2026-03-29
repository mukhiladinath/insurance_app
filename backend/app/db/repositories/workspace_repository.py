"""
workspace_repository.py — CRUD for client_workspaces and workspace_context_snapshots.

client_workspaces document shape:
  _id                    : ObjectId
  client_id              : str  (unique index)
  user_id                : str
  ai_context_overrides   : dict  — user-edited overrides per layer key
  active_conversation_id : str | None
  advisory_notes         : dict  — tool_name → advisory conclusion (client-scoped, not conv-scoped)
  scratch_pad            : list[dict]
  objectives_automation_fingerprint : str | None  — hash of goals text last used for auto tool runs
  created_at             : datetime
  updated_at             : datetime

workspace_context_snapshots document shape:
  _id          : ObjectId
  client_id    : str
  workspace_id : str
  run_id       : str
  context_tree : dict  — full hierarchical context used for this run
  created_at   : datetime
"""

import logging
from typing import Any

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


class WorkspaceRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CLIENT_WORKSPACES]
        self._snaps = db[col.WORKSPACE_CONTEXT_SNAPSHOTS]

    # ----------------------------------------------------------------
    # Workspace CRUD
    # ----------------------------------------------------------------

    async def get_by_client(self, client_id: str) -> dict | None:
        doc = await self._col.find_one({"client_id": client_id})
        return _serialize(doc) if doc else None

    async def get_or_create(self, client_id: str, user_id: str) -> dict:
        now = utc_now()
        empty = {
            "client_id": client_id,
            "user_id": user_id,
            "ai_context_overrides": {},
            "active_conversation_id": None,
            "advisory_notes": {},
            "scratch_pad": [],
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.find_one_and_update(
            {"client_id": client_id},
            {"$setOnInsert": empty},
            upsert=True,
            return_document=True,
        )
        return _serialize(result)

    async def set_active_conversation(
        self, client_id: str, conversation_id: str
    ) -> None:
        await self._col.update_one(
            {"client_id": client_id},
            {"$set": {"active_conversation_id": conversation_id, "updated_at": utc_now()}},
        )

    async def set_objectives_automation_fingerprint(
        self, client_id: str, fingerprint: str | None
    ) -> None:
        """SHA-256 hex (or None) of goals text last used for automated tool runs."""
        await self._col.update_one(
            {"client_id": client_id},
            {
                "$set": {
                    "objectives_automation_fingerprint": fingerprint,
                    "updated_at": utc_now(),
                }
            },
        )

    async def patch_ai_context_overrides(
        self, client_id: str, overrides: dict[str, Any]
    ) -> dict | None:
        """Merge new overrides into the existing ai_context_overrides dict."""
        set_ops: dict[str, Any] = {"updated_at": utc_now()}
        for key, value in overrides.items():
            set_ops[f"ai_context_overrides.{key}"] = value

        doc = await self._col.find_one_and_update(
            {"client_id": client_id},
            {"$set": set_ops},
            return_document=True,
        )
        return _serialize(doc) if doc else None

    async def upsert_advisory_note(
        self, client_id: str, tool_name: str, note: dict
    ) -> None:
        """Write or overwrite the advisory conclusion for a specific tool."""
        await self._col.update_one(
            {"client_id": client_id},
            {
                "$set": {
                    f"advisory_notes.{tool_name}": note,
                    "updated_at": utc_now(),
                }
            },
        )

    async def append_scratch_pad(self, client_id: str, entry: dict) -> None:
        await self._col.update_one(
            {"client_id": client_id},
            {
                "$push": {"scratch_pad": entry},
                "$set": {"updated_at": utc_now()},
            },
        )

    # ----------------------------------------------------------------
    # Context snapshots
    # ----------------------------------------------------------------

    async def save_context_snapshot(
        self,
        client_id: str,
        workspace_id: str,
        run_id: str,
        context_tree: dict,
    ) -> str:
        doc = {
            "client_id": client_id,
            "workspace_id": workspace_id,
            "run_id": run_id,
            "context_tree": context_tree,
            "created_at": utc_now(),
        }
        result = await self._snaps.insert_one(doc)
        return str(result.inserted_id)

    async def get_latest_snapshot(self, client_id: str) -> dict | None:
        doc = await self._snaps.find_one(
            {"client_id": client_id},
            sort=[("created_at", DESCENDING)],
        )
        return _serialize(doc) if doc else None

    async def get_snapshot_by_run(self, run_id: str) -> dict | None:
        doc = await self._snaps.find_one({"run_id": run_id})
        return _serialize(doc) if doc else None
