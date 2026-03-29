"""Shared helpers for normalizers and the comparison engine."""

from __future__ import annotations

from typing import Any


def yes_no_display(val: bool | None) -> str:
    if val is None:
        return "Not available"
    return "Yes" if val else "No"


def money_display(n: float | int | None) -> str:
    if n is None:
        return "Not available"
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return str(n)


def num_or_none(v: Any) -> float | int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        if isinstance(v, float) and v != v:  # NaN
            return None
        return float(v) if isinstance(v, (int, float)) else float(str(v))
    except (TypeError, ValueError):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None


def annual_from_monthly(monthly: float | None) -> float | None:
    if monthly is None:
        return None
    return round(monthly * 12, 2)


def monthly_from_annual(annual: float | None) -> float | None:
    if annual is None:
        return None
    return round(annual / 12, 2)


def normalize_ownership(raw: str | None) -> str | None:
    if not raw or raw == "UNKNOWN":
        return None
    u = raw.upper().replace(" ", "_")
    if "SPLIT" in u:
        return "split"
    if "SUPER" in u and "NON" not in u:
        return "super"
    if "PERSONAL" in u or "OUTSIDE" in u or "NON_SUPER" in u:
        return "personal"
    return None


def score_0_10_from_0_100(v: float | int | None) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(10.0, x / 10.0)), 1)


def fact_row(
    key: str,
    label: str,
    category: str,
    value: str | float | int | bool | None,
    display_value: str,
    *,
    unit: str | None = None,
    comparable: bool = True,
    metadata: dict | None = None,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "category": category,
        "value": value,
        "displayValue": display_value,
        "unit": unit,
        "comparable": comparable,
        "metadata": metadata or {},
    }
