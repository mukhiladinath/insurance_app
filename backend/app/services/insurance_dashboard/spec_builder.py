"""Build JSON dashboard specs (widgets, charts metadata) from projection payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_dashboard_spec(
    *,
    title: str,
    dashboard_type: str,
    client_name: str | None,
    source_label: str,
    resolved: dict[str, Any],
    projections: dict[str, Any],
) -> dict[str, Any]:
    return {
        "title": title,
        "type": dashboard_type,
        "generatedAt": _now_iso(),
        "header": {
            "title": title,
            "clientName": client_name or "",
            "source": source_label,
            "timestamp": _now_iso(),
        },
        "summaryCards": projections.get("summaryCards") or [],
        "charts": projections.get("charts") or [],
        "tables": projections.get("tables") or [],
        "insights": projections.get("insights") or [],
        "warnings": projections.get("warnings") or [],
        "controls": projections.get("controls") or [],
        "assumptions": resolved.get("assumptions_table") or [],
    }
