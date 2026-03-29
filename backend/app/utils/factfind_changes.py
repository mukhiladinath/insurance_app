"""
Normalize factfind PATCH payloads from UIs and LLM planners.

Orchestrator / planner often emits nested objects:
  { "financial": { "annual_gross_income": 120000 } }
The API and repository expect flat paths:
  { "financial.annual_gross_income": 120000 }
"""

from __future__ import annotations

from typing import Any

_SECTIONS = frozenset({"personal", "financial", "insurance", "health", "goals"})


def normalize_factfind_changes(changes: dict[str, Any]) -> dict[str, Any]:
    """
    Flatten nested section dicts into dotted field paths.

    - Keeps existing flat keys as-is (section.field → value).
    - Expands { "financial": { "super_balance": 1 } } → { "financial.super_balance": 1 }.
    - Drops keys that cannot be mapped to section.field (caller may treat empty result as error).
    """
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if key in _SECTIONS and isinstance(value, dict):
            for field, val in value.items():
                if val is None:
                    continue
                out[f"{key}.{field}"] = val
            continue
        if "." in key:
            out[key] = value
    return out


def count_valid_factfind_paths(changes: dict[str, Any]) -> int:
    """Number of keys that look like section.field (repository will accept)."""
    n = 0
    for field_path in changes:
        parts = field_path.split(".", 1)
        if len(parts) == 2 and parts[0] in _SECTIONS:
            n += 1
    return n
