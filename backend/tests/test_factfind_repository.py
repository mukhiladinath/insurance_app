"""FactfindRepository.patch_fields — including clearing values with None."""

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import collections as col
from app.db.repositories.factfind_repository import FactfindRepository
from app.utils.timestamps import utc_now


@pytest.mark.asyncio
async def test_patch_fields_writes_null_value_to_clear_field():
    """JSON null / Python None must persist so cleared factfind fields stay cleared."""
    now = utc_now()
    existing = {
        "_id": "ff1",
        "client_id": "c1",
        "version": 1,
        "sections": {
            "personal": {
                "age": {
                    "value": 42,
                    "status": "confirmed",
                    "source": "manual",
                    "source_ref": "x",
                    "confidence": 1.0,
                    "updated_at": now,
                    "updated_by": "user",
                }
            },
            "financial": {},
            "insurance": {},
            "health": {},
            "goals": {},
        },
        "pending_proposals": [],
        "created_at": now,
        "updated_at": now,
    }

    mock_col = AsyncMock()
    mock_log = AsyncMock()
    mock_log.insert_many = AsyncMock()
    mock_db = MagicMock()

    def getitem(name: str):
        if name == col.FACTFINDS:
            return mock_col
        if name == col.FACTFIND_CHANGE_LOG:
            return mock_log
        raise KeyError(name)

    mock_db.__getitem__ = MagicMock(side_effect=getitem)

    calls: list[dict] = []

    async def find_one_and_update(_filter, update, **_kw):
        calls.append(update)
        if "$setOnInsert" in update:
            # get_or_create runs _serialize on this doc (mutates: pop _id) — return a copy.
            return copy.deepcopy(existing)
        set_ops = update["$set"]
        age_entry = set_ops.get("sections.personal.age")
        assert age_entry is not None
        assert age_entry["value"] is None
        assert age_entry["status"] == "confirmed"
        out = {
            **existing,
            "_id": existing["_id"],
            "version": set_ops.get("version", 2),
            "sections": {
                **existing["sections"],
                "personal": {"age": age_entry},
            },
        }
        return out

    mock_col.find_one_and_update = AsyncMock(side_effect=find_one_and_update)

    repo = FactfindRepository(mock_db)
    await repo.patch_fields(
        client_id="c1",
        changes={"personal.age": None},
        source="manual",
        source_ref="api",
        changed_by="user",
    )

    assert len(calls) == 2
