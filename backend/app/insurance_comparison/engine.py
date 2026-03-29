"""Universal comparison engine over two ComparisonReadyToolOutput dicts."""

from __future__ import annotations

from typing import Any, Literal

from app.insurance_comparison import fact_keys as fk

BetterSide = Literal["left", "right", "neutral", "unknown"]
DeltaType = Literal["increase", "decrease", "same", "not_applicable"]

# Canonical key → (group, label, direction for "better" when numeric)
COMPARISON_KEY_META: dict[str, tuple[str, str, str]] = {
    fk.LIFE_COVER_AMOUNT: ("Cover", "Life cover", "higher_better"),
    fk.TPD_COVER_AMOUNT: ("Cover", "TPD cover", "higher_better"),
    fk.TRAUMA_COVER_AMOUNT: ("Cover", "Trauma cover", "higher_better"),
    fk.IP_MONTHLY_BENEFIT: ("Cover", "IP monthly benefit", "higher_better"),
    fk.IP_REPLACEMENT_RATIO: ("Cover", "IP replacement ratio", "higher_better"),
    fk.WAITING_PERIOD: ("Cover", "Waiting period", "neutral"),
    fk.BENEFIT_PERIOD: ("Cover", "Benefit period", "neutral"),
    fk.ANNUAL_PREMIUM: ("Cost", "Annual premium", "lower_better"),
    fk.MONTHLY_PREMIUM: ("Cost", "Monthly premium", "lower_better"),
    fk.FUNDING_SOURCE: ("Tax / Super", "Funding source", "neutral"),
    fk.OWNERSHIP_STRUCTURE: ("Structure", "Ownership", "neutral"),
    fk.INSIDE_SUPER: ("Tax / Super", "Inside super", "neutral"),
    fk.TAX_DEDUCTIBLE: ("Tax / Super", "Tax deductible", "neutral"),
    fk.UNDERWRITING_REQUIRED: ("Risks / Trade-offs", "Underwriting required", "lower_better"),
    fk.REPLACEMENT_INVOLVED: ("Risks / Trade-offs", "Replacement involved", "lower_better"),
    fk.INSURER_NAME: ("Structure", "Insurer", "neutral"),
    fk.FUND_NAME: ("Structure", "Fund", "neutral"),
    fk.PREMIUM_TYPE: ("Cost", "Premium type", "neutral"),
    fk.OWN_OCC_TPD: ("Cover", "Own occupation TPD", "higher_better"),
    fk.ANY_OCC_TPD: ("Cover", "Any occupation TPD", "neutral"),
    fk.ADEQUACY_SCORE: ("Suitability", "Adequacy score", "higher_better"),
    fk.AFFORDABILITY_SCORE: ("Suitability", "Affordability score", "higher_better"),
    fk.TAX_EFFICIENCY_SCORE: ("Suitability", "Tax efficiency score", "higher_better"),
    fk.FLEXIBILITY_SCORE: ("Suitability", "Flexibility score", "higher_better"),
    fk.IMPLEMENTATION_EASE_SCORE: ("Suitability", "Implementation ease", "higher_better"),
    fk.CLAIMS_PRACTICALITY_SCORE: ("Suitability", "Claims practicality", "higher_better"),
    fk.RECOMMENDATION_TYPE: ("Structure", "Recommendation type", "neutral"),
    fk.LEGAL_OR_POLICY_STATUS: ("Structure", "Legal / policy status", "neutral"),
}

GROUP_ORDER = (
    "Cover",
    "Cost",
    "Tax / Super",
    "Structure",
    "Risks / Trade-offs",
    "Suitability",
)


def _facts_by_key(facts: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for f in facts:
        k = f.get("key")
        if k:
            out[str(k)] = f
    return out


def _coerce_number(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _compare_numeric(
    left: float,
    right: float,
    direction: str,
) -> tuple[float | None, DeltaType, BetterSide, str]:
    tol = 1e-6
    if abs(left - right) <= tol:
        return 0.0, "same", "neutral", "Values are effectively the same."

    delta = right - left
    if direction == "neutral":
        if delta > 0:
            return delta, "increase", "unknown", f"Right is higher by {delta:,.2f}."
        return delta, "decrease", "unknown", f"Right is lower by {abs(delta):,.2f}."

    if direction == "higher_better":
        if right > left:
            return delta, "increase", "right", "Right option shows a higher value (favourable for cover/adequacy)."
        return delta, "decrease", "left", "Left option shows a higher value (favourable for cover/adequacy)."

    # lower_better
    if right < left:
        return delta, "decrease", "right", "Right option is lower (favourable for cost/risk)."
    return delta, "increase", "left", "Left option is lower (favourable for cost/risk)."


def _merge_fact_keys(left_facts: dict[str, dict], right_facts: dict[str, dict]) -> list[str]:
    keys = sorted(set(left_facts.keys()) | set(right_facts.keys()))
    return keys


def determine_comparison_mode(
    left_tool: str,
    right_tool: str,
    comparable_key_count: int,
    total_keys: int,
) -> Literal["direct", "partial", "scenario"]:
    if left_tool != right_tool:
        # Different tools: always treat as scenario framing (strategic), not like-for-like.
        return "scenario"
    if comparable_key_count >= 5:
        return "direct"
    if comparable_key_count >= 2:
        return "partial"
    return "scenario"


def compare_normalized(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    left_tool_name: str,
    right_tool_name: str,
) -> dict[str, Any]:
    lf = _facts_by_key(left.get("comparisonFacts") or [])
    rf = _facts_by_key(right.get("comparisonFacts") or [])
    keys = _merge_fact_keys(lf, rf)

    facts_table: list[dict[str, Any]] = []
    comparable_count = 0

    for key in keys:
        meta = COMPARISON_KEY_META.get(key, ("Structure", key.replace("_", " ").title(), "neutral"))
        group, label, direction = meta
        lfact = lf.get(key, {})
        rfact = rf.get(key, {})
        lv = lfact.get("value")
        rv = rfact.get("value")
        ld = lfact.get("displayValue") or (str(lv) if lv is not None else "Not available")
        rd = rfact.get("displayValue") or (str(rv) if rv is not None else "Not available")
        comp_left = bool(lfact.get("comparable", True))
        comp_right = bool(rfact.get("comparable", True))
        comparable = comp_left and comp_right and (lv is not None or rv is not None)

        delta: float | None = None
        delta_type: DeltaType | None = "not_applicable"
        better: BetterSide = "unknown"
        summary = "Not applicable — missing or non-comparable on one side."

        ln = _coerce_number(lv)
        rn = _coerce_number(rv)
        if comparable and ln is not None and rn is not None:
            comparable_count += 1
            delta, delta_type, better, summary = _compare_numeric(ln, rn, direction)
        elif comparable and isinstance(lv, bool) and isinstance(rv, bool):
            comparable_count += 1
            if lv == rv:
                delta_type, better, summary = "same", "neutral", "Same Yes/No outcome."
            else:
                delta_type = "not_applicable"
                better = "unknown"
                summary = "Boolean differs — interpret in advice context."
        elif lv is None and rv is None:
            comparable = False
            summary = "Not available on either side."
        elif lv is None or rv is None:
            comparable = False
            delta_type = "not_applicable"
            better = "unknown"
            summary = "One side lacks data — comparison not applied."

        facts_table.append({
            "group": group,
            "key": key,
            "label": label,
            "leftValue": lv,
            "rightValue": rv,
            "leftDisplay": ld,
            "rightDisplay": rd,
            "delta": delta,
            "deltaType": delta_type,
            "differenceSummary": summary,
            "betterSide": better,
            "comparable": comparable and delta_type != "not_applicable" or (delta_type == "same"),
        })

    # Fix comparable flag for rows we counted as numeric/bool
    for row in facts_table:
        if row["deltaType"] == "not_applicable" and row["leftDisplay"] == "Not available" and row["rightDisplay"] == "Not available":
            row["comparable"] = False

    mode = determine_comparison_mode(
        left_tool_name,
        right_tool_name,
        comparable_count,
        max(len(keys), 1),
    )

    # Recommendation frame (heuristic from slices)
    def _sg(s: dict, k: str) -> float | None:
        return _coerce_number(s.get(k))

    lsu = left.get("suitability") or {}
    rsu = right.get("suitability") or {}
    lp = left.get("premiums") or {}
    rp = right.get("premiums") or {}

    la = _coerce_number(lp.get("annual"))
    ra = _coerce_number(rp.get("annual"))
    frame = {
        "betterForLowCost": "unknown",
        "betterForHigherCover": "unknown",
        "betterForTaxEfficiency": "unknown",
        "betterForSimplicity": "unknown",
        "betterForFlexibility": "unknown",
        "betterForImplementationEase": "unknown",
    }
    if la is not None and ra is not None:
        if abs(la - ra) < 1:
            frame["betterForLowCost"] = "neutral"
        elif la < ra:
            frame["betterForLowCost"] = "left"
        else:
            frame["betterForLowCost"] = "right"
    elif la is not None and ra is None:
        frame["betterForLowCost"] = "left"
    elif ra is not None and la is None:
        frame["betterForLowCost"] = "right"

    adl = _sg(lsu, "adequacyScore")
    adr = _sg(rsu, "adequacyScore")
    if adl is not None and adr is not None:
        if abs(adl - adr) < 0.25:
            frame["betterForHigherCover"] = "neutral"
        elif adl > adr:
            frame["betterForHigherCover"] = "left"
        else:
            frame["betterForHigherCover"] = "right"

    tl = _sg(lsu, "taxEfficiencyScore")
    tr_ = _sg(rsu, "taxEfficiencyScore")
    if tl is not None and tr_ is not None:
        if abs(tl - tr_) < 0.25:
            frame["betterForTaxEfficiency"] = "neutral"
        elif tl > tr_:
            frame["betterForTaxEfficiency"] = "left"
        else:
            frame["betterForTaxEfficiency"] = "right"

    fl = _sg(lsu, "flexibilityScore")
    fr = _sg(rsu, "flexibilityScore")
    if fl is not None and fr is not None:
        if abs(fl - fr) < 0.25:
            frame["betterForFlexibility"] = "neutral"
        elif fl > fr:
            frame["betterForFlexibility"] = "left"
        else:
            frame["betterForFlexibility"] = "right"

    iel = _sg(lsu, "implementationEaseScore")
    ier = _sg(rsu, "implementationEaseScore")
    if iel is not None and ier is not None:
        if abs(iel - ier) < 0.25:
            frame["betterForImplementationEase"] = "neutral"
        elif iel > ier:
            frame["betterForImplementationEase"] = "left"
        else:
            frame["betterForImplementationEase"] = "right"

    # Simplicity: fewer warnings + no replacement
    lw = len(left.get("warnings") or [])
    rw = len(right.get("warnings") or [])
    lrep = (left.get("structural") or {}).get("replacementInvolved")
    rrep = (right.get("structural") or {}).get("replacementInvolved")
    if lrep is True and rrep is not True:
        frame["betterForSimplicity"] = "right"
    elif rrep is True and lrep is not True:
        frame["betterForSimplicity"] = "left"
    elif lw < rw:
        frame["betterForSimplicity"] = "left"
    elif rw < lw:
        frame["betterForSimplicity"] = "right"
    else:
        frame["betterForSimplicity"] = "neutral"

    major = [r["differenceSummary"] for r in facts_table if r.get("comparable") and r.get("deltaType") not in ("same", "not_applicable")][:8]

    insights = {
        "majorDifferences": major,
        "affordability": "",
        "adequacy": "",
        "tax": "",
        "structure": "",
        "implementationRisk": "",
        "claimsPracticality": "",
    }
    al = _sg(lsu, "affordabilityScore")
    ar = _sg(rsu, "affordabilityScore")
    if al is not None or ar is not None:
        insights["affordability"] = (
            f"Affordability scores (0–10 normalised): left {al if al is not None else 'n/a'}, "
            f"right {ar if ar is not None else 'n/a'}. Lower premium does not always imply better outcome if cover is reduced."
        )
    if adl is not None or adr is not None:
        insights["adequacy"] = (
            f"Adequacy scores: left {adl if adl is not None else 'n/a'}, right {adr if adr is not None else 'n/a'}."
        )
    if tl is not None or tr_ is not None:
        insights["tax"] = (
            f"Tax efficiency scores: left {tl if tl is not None else 'n/a'}, right {tr_ if tr_ is not None else 'n/a'}."
        )
    insights["structure"] = (
        f"Left tool: {left_tool_name}; right tool: {right_tool_name}. "
        f"Mode={mode}. Interpret structural differences alongside client fact find."
    )
    if lrep or rrep:
        insights["implementationRisk"] = "One or both options involve replacement — manage cover gap, underwriting, and informed consent."
    cpl = _sg(lsu, "claimsPracticalityScore")
    cpr = _sg(rsu, "claimsPracticalityScore")
    if cpl is not None or cpr is not None:
        insights["claimsPracticality"] = f"Claims practicality scores: left {cpl}, right {cpr}."

    risk_flags: list[dict[str, Any]] = []
    def _sev(s: Any) -> str:
        x = str(s or "medium").lower()
        if x in ("high", "critical"):
            return "high"
        if x in ("low", "info"):
            return "low"
        return "medium"

    for rk in left.get("risks") or []:
        if isinstance(rk, dict):
            risk_flags.append({
                "severity": _sev(rk.get("severity")),
                "message": f"[Left] {rk.get('message', rk)}",
            })
    for rk in right.get("risks") or []:
        if isinstance(rk, dict):
            risk_flags.append({
                "severity": _sev(rk.get("severity")),
                "message": f"[Right] {rk.get('message', rk)}",
            })
    for w in left.get("warnings") or []:
        risk_flags.append({"severity": "low", "message": f"[Left warning] {w}"})
    for w in right.get("warnings") or []:
        risk_flags.append({"severity": "low", "message": f"[Right warning] {w}"})

    # Sort table by GROUP_ORDER then label
    order_map = {g: i for i, g in enumerate(GROUP_ORDER)}
    facts_table.sort(key=lambda r: (order_map.get(r["group"], 99), r["label"]))

    return {
        "left": left,
        "right": right,
        "factsTable": facts_table,
        "insights": insights,
        "riskFlags": risk_flags,
        "recommendationFrame": frame,
        "comparisonMode": mode,
        "narrativeSummary": "",
    }
