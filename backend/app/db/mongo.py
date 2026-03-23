"""
mongo.py — Motor async MongoDB connection manager.

A single Motor client is created at startup and reused for the app lifetime.
Call connect() on startup and disconnect() on shutdown via FastAPI lifespan.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


async def connect() -> None:
    """Open the Motor client and verify connectivity."""
    global _client, _db
    settings = get_settings()

    logger.info("Connecting to MongoDB at %s ...", settings.mongo_uri)
    _client = AsyncIOMotorClient(settings.mongo_uri)
    _db = _client[settings.mongo_db_name]

    # Verify the connection by issuing a ping command.
    await _client.admin.command("ping")
    logger.info("MongoDB connected. Database: %s", settings.mongo_db_name)


async def disconnect() -> None:
    """Close the Motor client."""
    global _client, _db
    if _client is not None:
        _client.close()
        _client = None
        _db = None
        logger.info("MongoDB disconnected.")


def get_db() -> AsyncIOMotorDatabase:
    """
    Return the active database handle.
    Raises RuntimeError if connect() has not been called.
    """
    if _db is None:
        raise RuntimeError("MongoDB not connected. Call db.mongo.connect() first.")
    return _db
