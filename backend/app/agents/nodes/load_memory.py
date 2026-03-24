"""
load_memory.py — Node: load persistent structured client memory from MongoDB.

Populates state["client_memory"] with the conversation_memory document for
this conversation. If no memory document exists yet (new conversation), returns
an empty canonical memory structure so downstream nodes always have a valid dict.

This node runs AFTER load_context so both recent_messages and client_memory
are available to classify_intent and compose_response.

Failure mode: on any error, returns an empty memory dict and logs the error.
The graph continues — missing memory degrades gracefully to the pre-memory
behaviour (recent-message-only extraction).
"""

import logging
from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository

logger = logging.getLogger(__name__)


async def load_memory(state: AgentState) -> dict:
    """Load structured client memory for the current conversation."""
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        logger.warning("load_memory: no conversation_id in state")
        return {"client_memory": {}}

    try:
        db = get_db()
        repo = ConversationMemoryRepository(db)
        memory = await repo.get_by_conversation_id(conversation_id)

        if memory is None:
            logger.debug("load_memory: no memory yet for conversation %s", conversation_id)
            return {"client_memory": {}}

        logger.debug(
            "load_memory: loaded memory v%s (turn %s) for conversation %s",
            memory.get("version", 0),
            memory.get("turn_count", 0),
            conversation_id,
        )
        return {"client_memory": memory}

    except Exception as exc:
        logger.error("load_memory error: %s", exc)
        return {
            "client_memory": {},
            "errors": state.get("errors", []) + [f"Memory load error: {exc}"],
        }
