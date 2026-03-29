"""
When the canonical factfind is updated, mirror those fields into
conversation_memory (client_facts) so LangGraph chat context matches the factfind.

Conversation resolution (in order):
1. Workspace active_conversation_id (set after chat / orchestrator runs).
2. Latest document for this client that has conversation_id (e.g. upload included chat).
3. Create a new conversation for the workspace user_id, set it active, then sync.

This covers document → factfind flows where the user never opened chat (no active conv).
"""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.constants import DEFAULT_CONVERSATION_TITLE
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.services.memory_event_service import MemoryEventService
from app.services.memory_merge_service import merge_delta

logger = logging.getLogger(__name__)

# Recorded on field_meta and memory_events; not a real message id.
SOURCE_MESSAGE_ID = "factfind_sync"


async def _ensure_workspace(
    db: AsyncIOMotorDatabase, client_id: str
) -> dict | None:
    ws_repo = WorkspaceRepository(db)
    ws = await ws_repo.get_by_client(client_id)
    if ws is not None:
        return ws
    cr = ClientRepository(db)
    client = await cr.get_by_id(client_id)
    if not client:
        logger.warning("factfind sync: client not found client_id=%s", client_id)
        return None
    return await ws_repo.get_or_create(client_id, client.get("user_id", ""))


async def _resolve_conversation_id_for_factfind_sync(
    db: AsyncIOMotorDatabase,
    client_id: str,
    workspace: dict,
) -> str | None:
    cid = workspace.get("active_conversation_id")
    if cid:
        return str(cid)

    doc_repo = DocumentRepository(db)
    from_upload = await doc_repo.latest_conversation_id_for_client(client_id)
    if from_upload:
        ws_repo = WorkspaceRepository(db)
        await ws_repo.set_active_conversation(client_id, from_upload)
        logger.info(
            "factfind→conversation_memory: using conversation from latest upload client_id=%s conv=%s",
            client_id,
            from_upload,
        )
        return from_upload

    user_id = workspace.get("user_id") or ""
    if not user_id:
        logger.debug(
            "factfind→conversation_memory: no user_id; cannot create conversation client_id=%s",
            client_id,
        )
        return None

    conv_repo = ConversationRepository(db)
    ws_repo = WorkspaceRepository(db)
    conv = await conv_repo.create(
        user_id=user_id,
        title=DEFAULT_CONVERSATION_TITLE,
    )
    new_id = conv["id"]
    await ws_repo.set_active_conversation(client_id, new_id)
    logger.info(
        "factfind→conversation_memory: created conversation %s for client %s (factfind sync)",
        new_id,
        client_id,
    )
    return new_id


async def sync_factfind_changes_to_conversation_memory(
    db: AsyncIOMotorDatabase,
    client_id: str,
    normalized_changes: dict[str, Any],
) -> None:
    """
    Apply the same flat fact-find field updates to conversation_memory for a
    resolved conversation, using the same merge rules as chat turns.
    """
    if not normalized_changes:
        return

    workspace = await _ensure_workspace(db, client_id)
    if not workspace:
        return

    conversation_id = await _resolve_conversation_id_for_factfind_sync(
        db, client_id, workspace
    )
    if not conversation_id:
        logger.debug(
            "factfind→conversation_memory: skip (no conversation resolvable) client_id=%s",
            client_id,
        )
        return

    delta: dict[str, Any] = {}
    for field_path, value in normalized_changes.items():
        parts = field_path.split(".", 1)
        if len(parts) != 2:
            continue
        section, field = parts
        delta.setdefault(section, {})[field] = value

    if not delta:
        return

    memory_repo = ConversationMemoryRepository(db)
    try:
        memory = await memory_repo.get_or_create(conversation_id)
        updated_memory, events = merge_delta(
            memory,
            delta,
            source_message_id=SOURCE_MESSAGE_ID,
        )
        saved = await memory_repo.upsert(updated_memory)
        if events:
            await MemoryEventService(db).record_events(events)
        logger.info(
            "factfind→conversation_memory: conv=%s client=%s fields=%d memory_v=%s",
            conversation_id,
            client_id,
            len(normalized_changes),
            saved.get("version", "?"),
        )
    except Exception as exc:
        logger.error("factfind→conversation_memory sync failed (non-fatal): %s", exc)
