"""Unit tests for ClientAnalysisOutputRepository list/create serialization."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from app.db.repositories.client_analysis_output_repository import (
    ClientAnalysisOutputRepository,
)
from app.utils.timestamps import utc_now


@pytest.mark.asyncio
async def test_list_for_client_serializes_ids():
    oid = ObjectId()
    now = utc_now()
    doc = {
        "_id": oid,
        "client_id": "client_a",
        "instruction": "Analyse TPD",
        "tool_ids": ["tpd_policy_assessment"],
        "step_labels": ["TPD Assessment"],
        "content": "## Result\n\nOK",
        "created_at": now,
        "updated_at": now,
    }

    mock_col = AsyncMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.limit = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[doc])
    mock_col.find = MagicMock(return_value=cursor)

    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    repo = ClientAnalysisOutputRepository(mock_db)
    out = await repo.list_for_client("client_a")

    assert len(out) == 1
    assert out[0]["id"] == str(oid)
    assert out[0]["client_id"] == "client_a"
    assert out[0]["content"].startswith("## Result")


@pytest.mark.asyncio
async def test_update_content_invalid_id_returns_none():
    mock_col = AsyncMock()
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    repo = ClientAnalysisOutputRepository(mock_db)
    assert await repo.update_content("not-a-valid-objectid", "c1", "x") is None
    mock_col.find_one_and_update.assert_not_called()
