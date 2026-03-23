"""
timestamps.py — Consistent UTC timestamp helpers.

All timestamps stored in MongoDB are UTC. Never use naive datetimes.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


def to_isoformat(dt: datetime | None) -> str | None:
    """Serialize a datetime to ISO 8601 string, or None if not provided."""
    if dt is None:
        return None
    return dt.isoformat()


def from_isoformat(s: str | None) -> datetime | None:
    """Parse an ISO 8601 string to a timezone-aware datetime, or None."""
    if not s:
        return None
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
