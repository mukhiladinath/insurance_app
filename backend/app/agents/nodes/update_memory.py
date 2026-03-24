"""
update_memory.py — Node: extract delta facts from the current turn and update memory.

This node runs LAST in the graph, after persist_results. It:
  1. Calls memory_extractor.extract_delta on the current user message
     (with last 2 recent messages as context, current memory as known-facts baseline).
  2. Calls memory_merge_service.merge_delta to apply the delta deterministically.
  3. Upserts the updated memory document to MongoDB.
  4. Persists memory event records for any corrections, new facts, or revocations.
  5. Optionally regenerates the rolling summary (every SUMMARY_REFRESH_TURNS turns).

Failure isolation:
  - Any error in this node is logged and swallowed — the response is already
    saved and returned to the caller by this point.
  - A partial failure (e.g. extractor returns {}) results in no memory change.
  - Memory is NEVER cleared on extractor failure.

State reads:
  user_message, user_message_id, client_memory, recent_messages, conversation_id

State writes:
  client_memory (updated)  — so the in-memory state reflects the latest version.
"""

import logging
from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.services.memory_extractor import extract_delta
from app.services.memory_merge_service import merge_delta
from app.services.memory_event_service import MemoryEventService
from app.services.summary_service import should_refresh_summary, generate_summary
from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


async def update_memory(state: AgentState) -> dict:
    """Extract delta from current turn and persist updated client memory."""
    conversation_id = state.get("conversation_id")
    user_message = state.get("user_message", "")
    user_message_id = state.get("user_message_id", "")
    current_memory: dict = state.get("client_memory") or {}
    recent_messages: list[dict] = state.get("recent_messages") or []

    if not conversation_id or not user_message:
        return {}

    try:
        db = get_db()
        memory_repo = ConversationMemoryRepository(db)
        event_service = MemoryEventService(db)

        # Ensure memory document exists (creates an empty one if brand-new conversation)
        if not current_memory.get("conversation_id"):
            current_memory = await memory_repo.get_or_create(conversation_id)

        # --- Step 1: Extract delta from current user message ---
        # Context = last 2 messages before this one (for pronoun resolution etc.)
        context_msgs = recent_messages[-3:-1] if len(recent_messages) > 1 else []
        delta = await extract_delta(user_message, context_msgs, current_memory)

        # If extractor returned nothing meaningful, still increment turn count
        has_content = any(
            k in delta for k in ("personal", "financial", "insurance", "health", "goals")
        )
        if not has_content and not delta.get("_meta", {}).get("revoked_fields"):
            logger.debug("update_memory: no extractable facts in this turn — skipping merge")
            await memory_repo.increment_turn_count(conversation_id)
            return {}

        # --- Step 2: Merge delta into current memory ---
        updated_memory, events = merge_delta(
            current_memory,
            delta,
            source_message_id=user_message_id or "unknown",
        )

        # Bump turn count
        updated_memory["turn_count"] = current_memory.get("turn_count", 0) + 1
        updated_memory["conversation_id"] = conversation_id

        # --- Step 3: Optionally refresh rolling summary ---
        if should_refresh_summary(updated_memory):
            summary_text = await generate_summary(updated_memory, recent_messages)
            if summary_text:
                updated_memory["summary_memory"] = {
                    "text": summary_text,
                    "last_summarized_at": utc_now(),
                    "turn_count_at_summary": updated_memory["turn_count"],
                    "summarized_through_message_id": user_message_id or "unknown",
                }
                logger.debug("update_memory: summary refreshed at turn %d", updated_memory["turn_count"])

        # --- Step 4: Persist updated memory ---
        saved_memory = await memory_repo.upsert(updated_memory)

        # --- Step 5: Persist memory events (fire-and-forget on error) ---
        if events:
            await event_service.record_events(events)
            logger.debug("update_memory: %d events recorded", len(events))

        logger.info(
            "update_memory: memory v%s updated (%d events) for conversation %s",
            saved_memory.get("version", "?"),
            len(events),
            conversation_id,
        )
        return {"client_memory": saved_memory}

    except Exception as exc:
        logger.error("update_memory error (non-fatal): %s", exc)
        # Do not propagate — memory update failure must not break the response
        return {}
