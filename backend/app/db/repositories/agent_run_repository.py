"""
agent_run_repository.py — CRUD helpers for the agent_runs collection.

Document shape:
  _id                  : ObjectId
  conversation_id      : str
  user_message_id      : str
  selected_tool        : str | None
  intent               : str | None
  status               : str  ("running" | "completed" | "failed" | "partial")
  started_at           : datetime (UTC)
  ended_at             : datetime | None
  final_response       : str | None
  tool_result_summary  : str | None
  metadata             : dict
"""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id
from app.core.constants import AgentRunStatus


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


class AgentRunRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.AGENT_RUNS]

    async def create(
        self, conversation_id: str, user_message_id: str
    ) -> dict:
        now = utc_now()
        doc = {
            "conversation_id": conversation_id,
            "user_message_id": user_message_id,
            "selected_tool": None,
            "intent": None,
            "status": AgentRunStatus.RUNNING,
            "started_at": now,
            "ended_at": None,
            "final_response": None,
            "tool_result_summary": None,
            "metadata": {},
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def get_by_id(self, run_id: str) -> dict | None:
        doc = await self._col.find_one({"_id": to_object_id(run_id)})
        return _serialize(doc) if doc else None

    async def complete(
        self,
        run_id: str,
        final_response: str,
        intent: str | None = None,
        selected_tool: str | None = None,
        tool_result_summary: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        update: dict = {
            "status": AgentRunStatus.COMPLETED,
            "ended_at": utc_now(),
            "final_response": final_response,
        }
        if intent:
            update["intent"] = intent
        if selected_tool:
            update["selected_tool"] = selected_tool
        if tool_result_summary:
            update["tool_result_summary"] = tool_result_summary
        if metadata:
            update["metadata"] = metadata

        await self._col.update_one(
            {"_id": to_object_id(run_id)}, {"$set": update}
        )

    async def fail(self, run_id: str, error: str) -> None:
        await self._col.update_one(
            {"_id": to_object_id(run_id)},
            {
                "$set": {
                    "status": AgentRunStatus.FAILED,
                    "ended_at": utc_now(),
                    "metadata.error": error,
                }
            },
        )
