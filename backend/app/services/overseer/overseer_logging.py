"""
overseer_logging.py — Structured observability for every Overseer invocation.

Emits a single structured log entry per run via the standard logging framework.
In production, ship these to your log aggregator (Datadog, CloudWatch, etc.)
by configuring a JSON formatter on the root logger.

Log fields:
    event          : always "overseer.verdict"
    tool_name      : which tool was evaluated
    intent         : classified intent for this turn
    status         : verdict status code
    reason         : one-line reason
    overseer_source: "deterministic" | "llm" | "fallback"
    retry_count    : retries already consumed before this call
    missing_fields : list of missing field paths (if any)
    caution_count  : number of caution notes
    latency_ms     : wall-clock time for the overseer call (if measured)
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager

from app.services.overseer.overseer_models import OverseerVerdict

logger = logging.getLogger("overseer")


def log_verdict(
    tool_name: str,
    intent: str,
    verdict: OverseerVerdict,
    retry_count: int = 0,
    latency_ms: float | None = None,
) -> None:
    """
    Emit a structured INFO log entry for a completed overseer evaluation.
    """
    entry: dict = {
        "event": "overseer.verdict",
        "tool_name": tool_name,
        "intent": intent,
        "status": verdict.status,
        "reason": verdict.reason,
        "overseer_source": verdict.overseer_source,
        "retry_count": retry_count,
        "missing_fields": [m.field for m in verdict.missing_fields],
        "caution_count": len(verdict.caution_notes),
    }
    if latency_ms is not None:
        entry["latency_ms"] = round(latency_ms, 1)

    logger.info(
        "overseer.verdict | tool=%s intent=%s status=%s source=%s reason=%r",
        tool_name,
        intent,
        verdict.status,
        verdict.overseer_source,
        verdict.reason,
        extra=entry,
    )


@contextmanager
def timed():
    """Context manager that yields a dict with 'ms' set after the block exits."""
    t: dict[str, float] = {}
    start = time.monotonic()
    try:
        yield t
    finally:
        t["ms"] = (time.monotonic() - start) * 1000
