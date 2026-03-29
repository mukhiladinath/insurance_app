"""Tests for factfind → conversation_memory sync."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_sync_skips_when_no_conversation_resolvable():
    from app.services import factfind_conversation_memory_sync as mod

    db = MagicMock()
    ws = MagicMock()
    ws.get_by_client = AsyncMock(
        return_value={"active_conversation_id": None, "user_id": ""}
    )
    doc_r = MagicMock()
    doc_r.latest_conversation_id_for_client = AsyncMock(return_value=None)

    with (
        patch.object(mod, "WorkspaceRepository", return_value=ws),
        patch.object(mod, "DocumentRepository", return_value=doc_r),
    ):
        await mod.sync_factfind_changes_to_conversation_memory(
            db, "client-1", {"personal.age": 40}
        )

    ws.get_by_client.assert_awaited_once_with("client-1")
    doc_r.latest_conversation_id_for_client.assert_awaited_once_with("client-1")


@pytest.mark.asyncio
async def test_sync_merges_and_upserts_when_conversation_active():
    from app.services import factfind_conversation_memory_sync as mod

    db = MagicMock()
    ws = MagicMock()
    ws.get_by_client = AsyncMock(
        return_value={"active_conversation_id": "conv-99"}
    )

    mem_repo = MagicMock()
    mem_repo.get_or_create = AsyncMock(
        return_value={
            "conversation_id": "conv-99",
            "version": 1,
            "client_facts": {
                "personal": {},
                "financial": {},
                "insurance": {},
                "health": {},
                "goals": {},
            },
            "field_meta": {},
        }
    )
    mem_repo.upsert = AsyncMock(
        return_value={"version": 2, "conversation_id": "conv-99"}
    )

    event_svc = MagicMock()
    event_svc.record_events = AsyncMock()

    doc_r = MagicMock()
    doc_r.latest_conversation_id_for_client = AsyncMock(return_value=None)

    with (
        patch.object(mod, "WorkspaceRepository", return_value=ws),
        patch.object(mod, "DocumentRepository", return_value=doc_r),
        patch.object(mod, "ConversationMemoryRepository", return_value=mem_repo),
        patch.object(mod, "MemoryEventService", return_value=event_svc),
    ):
        await mod.sync_factfind_changes_to_conversation_memory(
            db, "client-1", {"personal.age": 41}
        )

    mem_repo.get_or_create.assert_awaited_once_with("conv-99")
    mem_repo.upsert.assert_awaited_once()
    assert mem_repo.upsert.await_args.args[0]["client_facts"]["personal"]["age"] == 41


@pytest.mark.asyncio
async def test_sync_uses_conversation_from_latest_upload_when_active_unset():
    from app.services import factfind_conversation_memory_sync as mod

    db = MagicMock()
    ws_mock = MagicMock()
    ws_mock.get_by_client = AsyncMock(
        return_value={"active_conversation_id": None, "user_id": "user-1"}
    )
    ws_mock.set_active_conversation = AsyncMock()

    doc_r = MagicMock()
    doc_r.latest_conversation_id_for_client = AsyncMock(return_value="conv-from-doc")

    mem_repo = MagicMock()
    mem_repo.get_or_create = AsyncMock(
        return_value={
            "conversation_id": "conv-from-doc",
            "version": 0,
            "client_facts": {
                "personal": {},
                "financial": {},
                "insurance": {},
                "health": {},
                "goals": {},
            },
            "field_meta": {},
        }
    )
    mem_repo.upsert = AsyncMock(return_value={"version": 1})

    with (
        patch.object(mod, "WorkspaceRepository", return_value=ws_mock),
        patch.object(mod, "DocumentRepository", return_value=doc_r),
        patch.object(mod, "ConversationMemoryRepository", return_value=mem_repo),
        patch.object(mod, "MemoryEventService", return_value=MagicMock()),
    ):
        await mod.sync_factfind_changes_to_conversation_memory(
            db, "client-1", {"personal.age": 55}
        )

    ws_mock.set_active_conversation.assert_awaited_once_with("client-1", "conv-from-doc")
    mem_repo.get_or_create.assert_awaited_once_with("conv-from-doc")
