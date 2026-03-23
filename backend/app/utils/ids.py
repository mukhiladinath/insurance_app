"""
ids.py — Document ID helpers.

MongoDB uses BSON ObjectIds. This module provides consistent generation
and string-conversion helpers so the rest of the app works with plain strings.
"""

from bson import ObjectId


def new_id() -> str:
    """Generate a new MongoDB ObjectId as a hex string."""
    return str(ObjectId())


def to_object_id(id_str: str) -> ObjectId:
    """Convert a hex string to a BSON ObjectId (raises ValueError if invalid)."""
    if not ObjectId.is_valid(id_str):
        raise ValueError(f"Invalid ObjectId: {id_str!r}")
    return ObjectId(id_str)


def is_valid_id(id_str: str) -> bool:
    """Return True if the string is a valid 24-hex ObjectId."""
    return ObjectId.is_valid(id_str)
