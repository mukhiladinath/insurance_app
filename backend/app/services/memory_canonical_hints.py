"""
memory_canonical_hints.py — Deterministic extraction of canonical factfind keys from AI memory markdown.

Used when building insurance tool inputs: values found here take precedence over the
structured factfind (memory first, then factfind gaps, then user overrides).

Only extracts fields we can match reliably with regex (age, annual gross income).
Extend patterns here if new critical fields should be sourced from memory.
"""

from __future__ import annotations

import re
from typing import Any

# Must match factfind section keys used by build_tool_input_from_memory
CANONICAL_SECTIONS = ("personal", "financial", "insurance", "health", "goals")

# Scan client_memories categories in this order; first successful value wins per field
MEMORY_CATEGORY_SCAN_ORDER = [
    "profile",
    "employment-income",
    "financial-position",
    "goals-risk-profile",
    "insurance",
    "health",
    "interactions",
    "tax-structures",
    "estate-planning",
]

# Age: "Age: 42", "Aged 42", "42 years old", bullet lines
_AGE_PATTERNS = [
    re.compile(r"(?:^|\n)\s*[-*•]?\s*(?:Age|Aged)\s*[:.]?\s*(\d{1,3})\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"\b(\d{1,3})\s*years?\s*old\b", re.IGNORECASE),
    re.compile(r"\bAge\s+is\s+(\d{1,3})\b", re.IGNORECASE),
]

# Income: lines mentioning annual/gross income/salary with a dollar or plain number
_INCOME_PATTERNS = [
    re.compile(
        r"(?:^|\n)\s*[-*•]?\s*"
        r"(?:Annual\s+(?:gross\s+)?income|Gross\s+income|Base\s+salary|Annual\s+salary|Salary|Total\s+remuneration)\b"
        r"\s*[:.]?\s*(?:AUD|USD)?\s*\$?\s*([\d,]+(?:\.\d+)?)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
    re.compile(
        r"(?:^|\n)\s*[-*•]?\s*Income\s*[:.]?\s*(?:AUD|USD)?\s*\$?\s*([\d,]+(?:\.\d+)?)\b",
        re.IGNORECASE | re.MULTILINE,
    ),
]


def _empty_sections() -> dict[str, dict[str, Any]]:
    return {s: {} for s in CANONICAL_SECTIONS}


def _parse_income_number(raw: str) -> float | None:
    s = raw.replace(",", "").strip()
    if not s:
        return None
    try:
        v = float(s)
    except ValueError:
        return None
    # Ignore tiny numbers (likely not annual income)
    if v < 1_000:
        return None
    return v


def parse_markdown_for_hints(markdown: str) -> dict[str, dict[str, Any]]:
    """
    Extract canonical personal.age and financial.annual_gross_income from one markdown blob.
    """
    out = _empty_sections()
    if not markdown or not markdown.strip():
        return out

    text = markdown

    for rx in _AGE_PATTERNS:
        m = rx.search(text)
        if m:
            age = int(m.group(1))
            if 16 <= age <= 100:
                out["personal"]["age"] = age
                break

    for rx in _INCOME_PATTERNS:
        m = rx.search(text)
        if m:
            inc = _parse_income_number(m.group(1))
            if inc is not None:
                # Tool layer accepts int-like where factfind uses whole dollars
                out["financial"]["annual_gross_income"] = int(inc) if inc == int(inc) else inc
                break

    return out


def merge_hints_across_memory_categories(
    category_to_markdown: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """
    Walk MEMORY_CATEGORY_SCAN_ORDER; first category that yields a value wins for each field.
    """
    merged = _empty_sections()
    for cat in MEMORY_CATEGORY_SCAN_ORDER:
        md = category_to_markdown.get(cat) or ""
        chunk = parse_markdown_for_hints(md)
        for section in CANONICAL_SECTIONS:
            for key, val in chunk[section].items():
                if val is None:
                    continue
                if key not in merged[section]:
                    merged[section][key] = val
    return merged


def merge_memory_then_factfind(
    memory_hints: dict[str, dict[str, Any]],
    factfind_facts: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """
    For each canonical section.field: use memory_hints if present, else factfind_facts.
    """
    out: dict[str, dict[str, Any]] = {s: {} for s in CANONICAL_SECTIONS}
    for section in CANONICAL_SECTIONS:
        m = memory_hints.get(section) or {}
        f = factfind_facts.get(section) or {}
        keys = set(m.keys()) | set(f.keys())
        for k in keys:
            mv = m.get(k)
            fv = f.get(k)
            if mv is not None:
                out[section][k] = mv
            elif fv is not None:
                out[section][k] = fv
    return out


def apply_canonical_overrides(
    canonical: dict[str, dict[str, Any]],
    overrides: dict[str, Any],
) -> None:
    """Mutate canonical in place: overrides use keys like personal.age."""
    for canon_path, value in overrides.items():
        if value is None:
            continue
        parts = canon_path.split(".", 1)
        if len(parts) != 2:
            continue
        section, field = parts
        if section in canonical:
            canonical[section][field] = value


async def load_memory_canonical_hints(client_id: str) -> dict[str, dict[str, Any]]:
    """
    Load all client_memories docs and extract age / annual_gross_income hints.
    """
    from app.db.repositories.client_memory_repository import get_all_memories

    docs = await get_all_memories(client_id)
    cat_md = {d.get("category", ""): d.get("content", "") or "" for d in docs}
    return merge_hints_across_memory_categories(cat_md)
