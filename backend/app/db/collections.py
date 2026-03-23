"""
collections.py — Collection name registry and index creation.

Centralises all MongoDB collection names. Indexes are created once at startup
via ensure_indexes(), keeping index definitions alongside the collection they belong to.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Collection name constants
# -------------------------------------------------------------------------

CONVERSATIONS = "conversations"
MESSAGES = "messages"
AGENT_RUNS = "agent_runs"
TOOL_CALLS = "tool_calls"
APP_CONFIG = "app_config"


# -------------------------------------------------------------------------
# Index definitions
# -------------------------------------------------------------------------

async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all required indexes. Safe to call multiple times (idempotent).
    Called once at application startup after the DB connection is established.
    """

    # conversations
    await db[CONVERSATIONS].create_index(
        [("user_id", ASCENDING), ("updated_at", DESCENDING)]
    )
    await db[CONVERSATIONS].create_index([("status", ASCENDING)])

    # messages
    await db[MESSAGES].create_index(
        [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
    )
    await db[MESSAGES].create_index([("agent_run_id", ASCENDING)])

    # agent_runs
    await db[AGENT_RUNS].create_index([("conversation_id", ASCENDING)])
    await db[AGENT_RUNS].create_index([("status", ASCENDING)])
    await db[AGENT_RUNS].create_index([("started_at", DESCENDING)])

    # tool_calls
    await db[TOOL_CALLS].create_index([("agent_run_id", ASCENDING)])
    await db[TOOL_CALLS].create_index([("conversation_id", ASCENDING)])
    await db[TOOL_CALLS].create_index([("tool_name", ASCENDING)])

    logger.info("MongoDB indexes ensured.")
