"""
memory_event_service.py — Thin service for persisting memory audit events.

Memory events provide an immutable audit trail of every fact addition, correction,
revocation, and update to structured client memory. Useful for debugging,
compliance review, and future ML training.

Events are written fire-and-don't-care: failures are logged but never raise
to the caller — the memory itself is already updated; events are supplementary.
"""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.conversation_memory_repository import MemoryEventRepository

logger = logging.getLogger(__name__)


class MemoryEventService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._repo = MemoryEventRepository(db)

    async def record_events(self, events: list[dict]) -> None:
        """
        Persist a batch of memory event dicts.
        Silently drops empty batches. Logs but does not raise on errors.
        """
        if not events:
            return
        try:
            await self._repo.create_many(events)
            logger.debug("memory_event_service: recorded %d events", len(events))
        except Exception as exc:
            logger.error("memory_event_service: failed to record events: %s", exc)
