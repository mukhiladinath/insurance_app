"""DocumentRepository.list_for_client — query shape for workspace document list."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repositories.document_repository import DocumentRepository


@pytest.mark.asyncio
async def test_list_for_client_queries_user_and_or_clauses():
    mock_col = AsyncMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    mock_col.find = MagicMock(return_value=cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    repo = DocumentRepository(mock_db)
    await repo.list_for_client("client_a", "advisor-1", "conv_99")

    mock_col.find.assert_called_once()
    q = mock_col.find.call_args[0][0]
    assert q["user_id"] == "advisor-1"
    assert q["$or"] == [
        {"client_id": "client_a"},
        {"conversation_id": "conv_99"},
    ]


@pytest.mark.asyncio
async def test_list_for_client_without_conversation_only_client_tag():
    mock_col = AsyncMock()
    cursor = MagicMock()
    cursor.sort = MagicMock(return_value=cursor)
    cursor.to_list = AsyncMock(return_value=[])
    mock_col.find = MagicMock(return_value=cursor)
    mock_db = MagicMock()
    mock_db.__getitem__ = MagicMock(return_value=mock_col)

    repo = DocumentRepository(mock_db)
    await repo.list_for_client("client_a", "advisor-1", None)

    q = mock_col.find.call_args[0][0]
    assert q["$or"] == [{"client_id": "client_a"}]
