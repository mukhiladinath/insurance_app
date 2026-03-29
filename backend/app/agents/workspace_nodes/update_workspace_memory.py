"""
update_workspace_memory.py — Extract new facts from the current turn and update the factfind.

Adapted from agents/nodes/update_memory.py.
Instead of updating conversation_memory (keyed by conversation_id), this node:
  - Reads the user_message to extract any incidental fact mentions
  - Patches the client's factfind (keyed by client_id)
  - Also increments conversation turn count for consistency

State reads:  user_message, user_message_id, factfind_snapshot, client_id,
              recent_messages, conversation_id
State writes: factfind_snapshot (updated)
"""

import logging

from app.agents.workspace_state import WorkspaceState
from app.db.mongo import get_db
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.services.memory_extractor import extract_delta
from app.services.memory_merge_service import merge_delta

logger = logging.getLogger(__name__)


async def update_workspace_memory(state: WorkspaceState) -> dict:
    """
    Extract factual deltas from the current user turn and update the factfind.

    Non-fatal: any error is swallowed — the response is already saved.
    """
    client_id = state.get("client_id", "")
    conversation_id = state.get("conversation_id", "")
    user_message = state.get("user_message", "")
    user_message_id = state.get("user_message_id", "")
    factfind_snapshot = dict(state.get("factfind_snapshot", {}))
    recent_messages: list[dict] = state.get("recent_messages", [])

    if not client_id or not user_message:
        return {}

    try:
        db = get_db()

        # Build a minimal client_memory-compatible dict so extract_delta works unchanged
        # (it expects {"client_facts": {"personal": {...}, ...}})
        sections: dict = {}
        for field_path, value in factfind_snapshot.items():
            if "." in field_path:
                section, field = field_path.split(".", 1)
                sections.setdefault(section, {})[field] = value

        client_memory_compat = {"client_facts": sections}
        context_msgs = recent_messages[-3:-1] if len(recent_messages) > 1 else []

        delta = await extract_delta(user_message, context_msgs, client_memory_compat)

        # Check if anything meaningful was extracted
        has_content = any(
            k in delta for k in ("personal", "financial", "insurance", "health", "goals")
        )
        if not has_content:
            logger.debug("update_workspace_memory: no new facts in this turn for client=%s", client_id)
            # Still increment conversation turn count
            if conversation_id:
                try:
                    mem_repo = ConversationMemoryRepository(db)
                    await mem_repo.increment_turn_count(conversation_id)
                except Exception:
                    pass
            return {}

        # Merge delta using existing merge service
        updated_memory, _ = merge_delta(client_memory_compat, delta, source_message_id=user_message_id or "unknown")
        updated_facts = updated_memory.get("client_facts", {})

        # Build changes dict for factfind patch
        changes: dict = {}
        for section, fields in updated_facts.items():
            for field_name, value in fields.items():
                field_path = f"{section}.{field_name}"
                old_value = factfind_snapshot.get(field_path)
                if value is not None and value != "" and value != [] and value != old_value:
                    changes[field_path] = value

        if changes:
            factfind_repo = FactfindRepository(db)
            await factfind_repo.patch_fields(
                client_id=client_id,
                changes=changes,
                source="ai_extracted",
                source_ref=user_message_id or "unknown",
                changed_by="agent",
            )
            updated_snapshot = {**factfind_snapshot, **changes}
            logger.info(
                "update_workspace_memory: %d new/changed fields for client=%s",
                len(changes), client_id,
            )
        else:
            updated_snapshot = factfind_snapshot

        # Increment conversation turn count
        if conversation_id:
            try:
                mem_repo = ConversationMemoryRepository(db)
                await mem_repo.increment_turn_count(conversation_id)
            except Exception:
                pass

        return {"factfind_snapshot": updated_snapshot}

    except Exception as exc:
        logger.error("update_workspace_memory error (non-fatal): %s", exc)
        return {}
