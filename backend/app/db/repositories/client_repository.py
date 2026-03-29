"""
client_repository.py — CRUD for the clients collection.

clients document shape:
  _id          : ObjectId
  user_id      : str   (the adviser who owns this client)
  name         : str
  email        : str | None
  phone        : str | None
  date_of_birth: str | None  (ISO date YYYY-MM-DD)
  status       : str   "active" | "archived"
  created_at   : datetime (UTC)
  updated_at   : datetime (UTC)
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


class ClientRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._col = db[col.CLIENTS]

    async def create(
        self,
        user_id: str,
        name: str,
        email: str | None = None,
        phone: str | None = None,
        date_of_birth: str | None = None,
    ) -> dict:
        now = utc_now()
        doc = {
            "user_id": user_id,
            "name": name,
            "email": email,
            "phone": phone,
            "date_of_birth": date_of_birth,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
        result = await self._col.insert_one(doc)
        doc["_id"] = result.inserted_id
        return _serialize(doc)

    async def get_by_id(self, client_id: str) -> dict | None:
        oid = to_object_id(client_id)
        if oid is None:
            return None
        doc = await self._col.find_one({"_id": oid})
        return _serialize(doc) if doc else None

    async def list_by_user(
        self,
        user_id: str,
        status: str = "active",
        limit: int = 100,
    ) -> list[dict]:
        cursor = (
            self._col.find({"user_id": user_id, "status": status})
            .sort("updated_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]

    async def update(self, client_id: str, fields: dict[str, Any]) -> dict | None:
        oid = to_object_id(client_id)
        if oid is None:
            return None
        fields["updated_at"] = utc_now()
        doc = await self._col.find_one_and_update(
            {"_id": oid},
            {"$set": fields},
            return_document=True,
        )
        return _serialize(doc) if doc else None

    async def archive(self, client_id: str) -> bool:
        oid = to_object_id(client_id)
        if oid is None:
            return False
        result = await self._col.update_one(
            {"_id": oid},
            {"$set": {"status": "archived", "updated_at": utc_now()}},
        )
        return result.modified_count > 0
