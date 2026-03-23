"""
tool_call_repository.py — CRUD helpers for the tool_calls collection.

Document shape:
  _id             : ObjectId
  agent_run_id    : str
  conversation_id : str
  tool_name       : str
  tool_version    : str
  status          : str  ("started" | "completed" | "failed" | "validation_error")
  input_payload   : dict
  output_payload  : dict | None
  warnings        : list[str]
  error           : str | None
  started_at      : datetime (UTC)
  ended_at        : datetime | None
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id
from app.core.constants import ToolCallStatus


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class ToolCallRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.TOOL_CALLS]

    async def start(
        self,
        agent_run_id: str,
        conversation_id: str,
        tool_name: str,
        tool_version: str,
        input_payload: dict,
    ) -> dict:
        now = utc_now()
        doc = {
            "agent_run_id": agent_run_id,
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "tool_version": tool_version,
            "status": ToolCallStatus.STARTED,
            "input_payload": input_payload,
            "output_payload": None,
            "warnings": [],
            "error": None,
            "started_at": now,
            "ended_at": None,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def complete(
        self,
        tool_call_id: str,
        output_payload: dict,
        warnings: list[str] | None = None,
    ) -> None:
        await self._col.update_one(
            {"_id": to_object_id(tool_call_id)},
            {
                "$set": {
                    "status": ToolCallStatus.COMPLETED,
                    "output_payload": output_payload,
                    "warnings": warnings or [],
                    "ended_at": utc_now(),
                }
            },
        )

    async def fail(
        self,
        tool_call_id: str,
        error: str,
        status: str = ToolCallStatus.FAILED,
    ) -> None:
        await self._col.update_one(
            {"_id": to_object_id(tool_call_id)},
            {
                "$set": {
                    "status": status,
                    "error": error,
                    "ended_at": utc_now(),
                }
            },
        )

    async def list_by_run(self, agent_run_id: str) -> list[dict]:
        cursor = self._col.find({"agent_run_id": agent_run_id}).sort("started_at", 1)
        docs = await cursor.to_list(length=50)
        return [_serialize(d) for d in docs]
