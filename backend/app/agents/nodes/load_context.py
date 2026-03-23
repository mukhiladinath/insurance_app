"""
load_context.py — Node: load recent conversation messages from MongoDB.

Populates state["recent_messages"] with the last N messages in the conversation.
These are used downstream for intent classification and response composition.
"""

import logging
from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.message_repository import MessageRepository
from app.core.constants import MAX_CONTEXT_MESSAGES

logger = logging.getLogger(__name__)


async def load_context(state: AgentState) -> dict:
    """Load recent conversation history from MongoDB."""
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        logger.warning("load_context: no conversation_id in state")
        return {"recent_messages": [], "errors": state.get("errors", [])}

    try:
        db = get_db()
        repo = MessageRepository(db)
        messages = await repo.get_recent(conversation_id, n=MAX_CONTEXT_MESSAGES)

        # Convert to simple {role, content} dicts for LLM context
        context_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant", "system")
        ]

        logger.debug("load_context: loaded %d messages for conversation %s", len(context_messages), conversation_id)
        return {"recent_messages": context_messages}

    except Exception as exc:
        logger.error("load_context error: %s", exc)
        return {
            "recent_messages": [],
            "errors": state.get("errors", []) + [f"Context load error: {exc}"],
        }
