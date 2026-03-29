"""
client_memory_repository.py — Data access layer for client AI memory documents.

Each client has up to 9 category documents stored in the client_memories collection.
Categories mirror finobi's S3 folder structure but stored in MongoDB.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.db.mongo import get_db
from app.db.collections import CLIENT_MEMORIES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Valid categories
# ---------------------------------------------------------------------------

MEMORY_CATEGORIES = [
    "profile",
    "employment-income",
    "financial-position",
    "insurance",
    "goals-risk-profile",
    "tax-structures",
    "estate-planning",
    "health",
    "interactions",
]

CATEGORY_LABELS = {
    "profile": "Profile",
    "employment-income": "Employment & Income",
    "financial-position": "Financial Position",
    "insurance": "Insurance",
    "goals-risk-profile": "Goals & Risk Profile",
    "tax-structures": "Tax & Structures",
    "estate-planning": "Estate Planning",
    "health": "Health",
    "interactions": "Interactions",
}


# ---------------------------------------------------------------------------
# Repository functions
# ---------------------------------------------------------------------------


async def get_memory(client_id: str, category: str) -> dict[str, Any] | None:
    """Return a single memory document for (client_id, category), or None."""
    db = get_db()
    doc = await db[CLIENT_MEMORIES].find_one(
        {"client_id": client_id, "category": category},
        {"_id": 0},
    )
    return doc


async def get_all_memories(client_id: str) -> list[dict[str, Any]]:
    """Return all memory documents for a client (up to 9 categories)."""
    db = get_db()
    cursor = db[CLIENT_MEMORIES].find({"client_id": client_id}, {"_id": 0})
    return await cursor.to_list(length=20)


async def upsert_memory(
    client_id: str,
    category: str,
    content: str,
    sources: list[dict[str, Any]] | None = None,
    fact_count: int | None = None,
) -> dict[str, Any]:
    """
    Create or update a memory document.
    Returns the updated document.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    update: dict[str, Any] = {
        "$set": {
            "client_id": client_id,
            "category": category,
            "content": content,
            "last_updated": now,
        },
    }

    if fact_count is not None:
        update["$set"]["fact_count"] = fact_count

    if sources:
        # Append new sources (avoid duplicates by filename+date)
        update["$push"] = {"sources": {"$each": sources}}

    result = await db[CLIENT_MEMORIES].find_one_and_update(
        {"client_id": client_id, "category": category},
        update,
        upsert=True,
        return_document=True,
    )

    # Strip MongoDB _id before returning
    if result and "_id" in result:
        result.pop("_id")
    return result or {}


async def initialize_empty_memories(client_id: str) -> None:
    """
    Create empty memory stubs for all 9 categories for a new client.
    Skips categories that already exist.
    """
    db = get_db()
    now = datetime.now(timezone.utc)

    for category in MEMORY_CATEGORIES:
        existing = await db[CLIENT_MEMORIES].find_one(
            {"client_id": client_id, "category": category}
        )
        if not existing:
            await db[CLIENT_MEMORIES].insert_one({
                "client_id": client_id,
                "category": category,
                "content": f"## {CATEGORY_LABELS[category]}\n\nNo information recorded yet.",
                "last_updated": now,
                "fact_count": 0,
                "sources": [],
            })


async def search_memories(client_id: str, query: str) -> list[dict[str, Any]]:
    """
    Simple text search across all memory documents for a client.
    Returns documents whose content contains the query (case-insensitive).
    """
    db = get_db()
    import re
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    cursor = db[CLIENT_MEMORIES].find(
        {"client_id": client_id, "content": {"$regex": pattern}},
        {"_id": 0},
    )
    return await cursor.to_list(length=20)


async def delete_all_memories(client_id: str) -> int:
    """Delete all memory documents for a client. Returns deleted count."""
    db = get_db()
    result = await db[CLIENT_MEMORIES].delete_many({"client_id": client_id})
    return result.deleted_count
