"""Optional weighted 0–10 scoring with explicit reasons."""

from __future__ import annotations

from typing import Any

DEFAULT_WEIGHTS: dict[str, float] = {
    "affordability": 0.25,
    "adequacy": 0.30,
    "taxEfficiency": 0.15,
    "flexibility": 0.10,
    "implementationEase": 0.10,
    "claimsPracticality": 0.10,
}


def _pick(side: dict[str, Any], *keys: str) -> float | None:
    s = side.get("suitability") or {}
    for k in keys:
        v = s.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    return None


def score_side(
    label: str,
    side: dict[str, Any],
    *,
    weights: dict[str, float] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, float | None], float | None]:
    wts = weights or DEFAULT_WEIGHTS
    affordability = _pick(side, "affordabilityScore")
    adequacy = _pick(side, "adequacyScore")
    tax_eff = _pick(side, "taxEfficiencyScore")
    flex = _pick(side, "flexibilityScore")
    impl = _pick(side, "implementationEaseScore")
    claims = _pick(side, "claimsPracticalityScore")

    breakdown: list[dict[str, Any]] = []
    values: dict[str, float | None] = {
        "affordability": affordability,
        "adequacy": adequacy,
        "taxEfficiency": tax_eff,
        "flexibility": flex,
        "implementationEase": impl,
        "claimsPracticality": claims,
    }

    for cat, score in values.items():
        reason = f"{label}: {cat} score unavailable — insufficient normalized data."
        if score is not None:
            reason = f"{label}: {cat} normalised to {score:.1f}/10 from tool output."
        breakdown.append({"category": cat, "score": score, "reason": reason})

    total_w = 0.0
    acc = 0.0
    for cat, wt in wts.items():
        v = values.get(cat)
        if v is None:
            continue
        acc += v * wt
        total_w += wt
    weighted = round(acc / total_w, 2) if total_w > 0 else None
    return breakdown, values, weighted


def compare_weighted_scores(
    left: dict[str, Any],
    right: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    bl, vl, wl = score_side("Option A", left, weights=weights)
    br, vr, wr = score_side("Option B", right, weights=weights)
    explanation = "Weighted totals use only categories where both sides supplied scores; null categories are excluded from the denominator."
    if wl is None and wr is None:
        explanation = "Weighted total could not be computed — no overlapping suitability scores."
    elif wl is None:
        explanation = "Left weighted total unavailable — missing suitability scores."
    elif wr is None:
        explanation = "Right weighted total unavailable — missing suitability scores."
    return {
        "scoreBreakdown": bl + br,
        "weightedTotals": {"left": wl, "right": wr},
        "scoreExplanation": explanation,
    }
