"""Adviser-ready narrative from comparison result dict (post-engine)."""

from __future__ import annotations

from typing import Any


def build_narrative(comp: dict[str, Any]) -> str:
    left = comp.get("left") or {}
    right = comp.get("right") or {}
    mode = comp.get("comparisonMode", "partial")
    frame = comp.get("recommendationFrame") or {}
    insights = comp.get("insights") or {}
    facts = comp.get("factsTable") or []

    lt = left.get("toolName", "Option A")
    rt = right.get("toolName", "Option B")

    parts: list[str] = []

    parts.append(
        f"This comparison uses structured facts from two saved tool outputs ({lt} vs {rt}). "
        f"Comparison mode is {mode.upper()}: "
        + (
            "broad overlap of comparable fields."
            if mode == "direct"
            else "limited overlap — interpret with care."
            if mode == "partial"
            else "different tools — focus on strategic trade-offs, not like-for-like premiums only."
        )
    )

    majors = insights.get("majorDifferences") or []
    if majors:
        parts.append("Major numeric or directional differences in the fact table include: " + "; ".join(majors[:5]) + ".")

    # Balanced paragraph from recommendation frame
    cost = frame.get("betterForLowCost", "unknown")
    cov = frame.get("betterForHigherCover", "unknown")
    tax = frame.get("betterForTaxEfficiency", "unknown")
    simp = frame.get("betterForSimplicity", "unknown")

    def _name(side: str) -> str:
        return "Option A (left)" if side == "left" else "Option B (right)" if side == "right" else "Neither option clearly"

    if cost != "unknown" or cov != "unknown":
        parts.append(
            f"On cost, {_name(cost)} appears stronger on annual premium signals where data exists. "
            f"On cover/adequacy signals, {_name(cov)} scores higher where scores were available. "
            f"Tax efficiency favours {_name(tax)} where comparable. "
            f"Simplicity (warnings / replacement) slightly favours {_name(simp)}."
        )

    aff = insights.get("affordability", "")
    ade = insights.get("adequacy", "")
    if aff:
        parts.append(aff)
    if ade:
        parts.append(ade)

    risky = [f.get("message") for f in (comp.get("riskFlags") or []) if f.get("severity") == "high"]
    if risky:
        parts.append("High-severity items to address explicitly: " + " ".join(risky[:4]))

    parts.append(
        "This summary is factual and tool-driven — it is not a substitute for client-specific advice, "
        "SOA requirements, or insurer terms. Where data was missing, comparisons were marked not applicable rather than inferred."
    )

    return " ".join(parts)


def attach_narrative(comp: dict[str, Any]) -> dict[str, Any]:
    out = dict(comp)
    out["narrativeSummary"] = build_narrative(comp)
    return out
