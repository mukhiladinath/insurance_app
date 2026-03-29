"""
load_context_smart.py — Dynamic message history loader.

Replaces the legacy load_context node in the orchestrator graph.
Loads exactly context_requirements.message_history_depth messages
instead of the fixed MAX_CONTEXT_MESSAGES (20).

Typical values:
  3  — fresh query, no follow-up signals
  8  — follow-up ("also", "continue", "what else")
  15 — explicit history reference ("what did we discuss earlier?", "you said...")

State reads:  conversation_id, context_requirements
State writes: recent_messages
"""

import logging

from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

_ABSOLUTE_MAX = 20   # hard cap regardless of requirements
_DEFAULT_DEPTH = 5   # fallback when requirements not set


async def load_context_smart(state: AgentState) -> dict:
    """Load exactly as many messages as the query needs."""
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        return {"recent_messages": []}

    requirements = state.get("context_requirements", {})
    depth = min(
        requirements.get("message_history_depth", _DEFAULT_DEPTH),
        _ABSOLUTE_MAX,
    )

    try:
        db = get_db()
        repo = MessageRepository(db)
        messages = await repo.get_recent(conversation_id, n=depth)

        context_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant", "system")
        ]

        logger.info(
            "load_context_smart: loaded %d/%d messages (requested depth=%d)",
            len(context_messages), depth, depth,
        )
        return {"recent_messages": context_messages}

    except Exception as exc:
        logger.error("load_context_smart error: %s", exc)
        return {
            "recent_messages": [],
            "errors": state.get("errors", []) + [f"Context load error: {exc}"],
        }
