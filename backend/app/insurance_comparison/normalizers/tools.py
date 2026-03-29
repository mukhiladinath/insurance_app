"""
Normalizers for registered insurance tools.

Each function returns a plain dict matching ComparisonReadyToolOutput (all nested keys
present; use null for unknowns).
"""

from __future__ import annotations

from typing import Any

from app.insurance_comparison import fact_keys as fk
from app.insurance_comparison.utils import (
    fact_row,
    money_display,
    monthly_from_annual,
    normalize_ownership,
    num_or_none,
    score_0_10_from_0_100,
    yes_no_display,
)


def _base(
    tool_name: str,
    tool_run_id: str,
    client_id: str,
    strategy_name: str,
    generated_at: str,
) -> dict[str, Any]:
    return {
        "toolName": tool_name,
        "toolRunId": tool_run_id,
        "strategyName": strategy_name,
        "clientId": client_id,
        "generatedAt": generated_at,
        "scenarioSummary": {"title": "", "description": "", "recommendationType": ""},
        "comparisonFacts": [],
        "cover": {
            "life": None,
            "tpd": None,
            "trauma": None,
            "incomeProtectionMonthly": None,
            "incomeProtectionReplacementRatio": None,
            "waitingPeriod": None,
            "benefitPeriod": None,
            "ownOccupationTPD": None,
            "anyOccupationTPD": None,
            "heldInsideSuper": None,
            "splitOwnership": None,
        },
        "premiums": {
            "monthly": None,
            "annual": None,
            "fundedFromSuper": None,
            "fundedPersonally": None,
            "deductiblePersonally": None,
            "taxImpactEstimate": None,
        },
        "structural": {
            "owner": None,
            "insurer": None,
            "fundName": None,
            "policyType": None,
            "steppedOrLevel": None,
            "replacementInvolved": None,
            "underwritingRequired": None,
        },
        "suitability": {
            "affordabilityScore": None,
            "adequacyScore": None,
            "flexibilityScore": None,
            "taxEfficiencyScore": None,
            "claimsPracticalityScore": None,
            "implementationEaseScore": None,
        },
        "tradeoffs": [],
        "risks": [],
        "assumptions": [],
        "warnings": [],
        "explanation": "",
    }


def _placement_owner(rec: str) -> str | None:
    if rec in ("INSIDE_SUPER",):
        return "super"
    if rec in ("OUTSIDE_SUPER", "RETAIL", "MOVE_OUTSIDE_SUPER"):
        return "personal"
    if rec in ("SPLIT_STRATEGY",):
        return "split"
    return None


def normalize_purchase_retain_life_insurance_in_super(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_life_insurance_in_super", tool_run_id, client_id, "", generated_at)
    placement = raw.get("placement_assessment") or {}
    rec = placement.get("recommendation") or raw.get("legal_status") or ""
    out["scenarioSummary"] = {
        "title": "Life insurance in super (PYS / SIS)",
        "description": (placement.get("reasoning") or [""])[0] if placement.get("reasoning") else "",
        "recommendationType": str(rec),
    }

    owner = _placement_owner(str(rec))
    out["structural"]["owner"] = owner
    out["structural"]["replacementInvolved"] = raw.get("legal_status") == "MUST_BE_SWITCHED_OFF"

    cna = raw.get("coverage_needs_analysis") or {}
    life_low = num_or_none(cna.get("total_need_low"))
    life_high = num_or_none(cna.get("total_need_high"))
    life_mid = None
    if life_low is not None and life_high is not None:
        life_mid = (life_low + life_high) / 2
    out["cover"]["life"] = life_mid
    out["cover"]["heldInsideSuper"] = True if owner == "super" else (False if owner == "personal" else None)
    out["cover"]["splitOwnership"] = owner == "split"

    rd = raw.get("retirement_drag_estimate")
    annual = num_or_none(rd.get("annual_premium")) if isinstance(rd, dict) else None
    out["premiums"]["annual"] = annual
    out["premiums"]["monthly"] = monthly_from_annual(annual) if annual else None

    scores = raw.get("placement_scores") or {}
    cash = num_or_none(scores.get("cashflow_benefit"))
    tax_b = num_or_none(scores.get("tax_funding_benefit"))
    if cash is not None and tax_b is not None:
        out["suitability"]["taxEfficiencyScore"] = score_0_10_from_0_100((cash + tax_b) / 2)
    flex_pen = num_or_none(scores.get("flexibility_control_penalty"))
    if flex_pen is not None:
        out["suitability"]["flexibilityScore"] = score_0_10_from_0_100(100 - flex_pen)

    short = cna.get("shortfall_level")
    if short in ("SIGNIFICANT", "CRITICAL", "MODERATE"):
        out["suitability"]["adequacyScore"] = 4.0
    elif short in ("MINOR", "NONE"):
        out["suitability"]["adequacyScore"] = 7.5
    elif cna.get("needs_analysis_available"):
        out["suitability"]["adequacyScore"] = 6.0

    btr = raw.get("beneficiary_tax_risk") or {}
    sev = (btr.get("risk_level") or "").upper()
    if sev in ("CRITICAL", "HIGH"):
        out["risks"].append({"severity": "high", "type": "beneficiary_tax", "message": btr.get("explanation", "")})
    elif sev == "MEDIUM":
        out["risks"].append({"severity": "medium", "type": "beneficiary_tax", "message": btr.get("explanation", "")})

    for r in placement.get("risks") or []:
        out["risks"].append({"severity": "medium", "type": "placement", "message": str(r)})

    val = raw.get("validation") or {}
    for w in val.get("warnings") or []:
        out["warnings"].append(w.get("message", str(w)) if isinstance(w, dict) else str(w))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Placement recommendation", "Structure", rec, str(rec).replace("_", " ")),
        fact_row(
            fk.LEGAL_OR_POLICY_STATUS,
            "Legal status",
            "Structure",
            raw.get("legal_status"),
            str(raw.get("legal_status") or "Not available"),
        ),
        fact_row(fk.LIFE_COVER_AMOUNT, "Indicative life need (mid-range)", "Cover", life_mid, money_display(life_mid)),
        fact_row(fk.ANNUAL_PREMIUM, "Estimated annual premium (super drag)", "Cost", annual, money_display(annual)),
        fact_row(
            fk.OWNERSHIP_STRUCTURE,
            "Ownership structure",
            "Structure",
            owner,
            owner.replace("_", " ").title() if owner else "Not available",
        ),
        fact_row(fk.INSIDE_SUPER, "Inside super focus", "Tax / Super", owner == "super", yes_no_display(owner == "super")),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = cna.get("recommendation_summary") or out["scenarioSummary"]["description"]
    return out


def normalize_purchase_retain_life_tpd_policy(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_life_tpd_policy", tool_run_id, client_id, "", generated_at)
    rec_block = raw.get("recommendation") or {}
    rec_type = rec_block.get("type") or ""
    out["scenarioSummary"] = {
        "title": "Life & TPD policy",
        "description": rec_block.get("summary") or "",
        "recommendationType": str(rec_type),
    }

    life_need = rec_block.get("life_need") or {}
    tpd_need = rec_block.get("tpd_need") or {}
    aff = rec_block.get("affordability") or {}
    comparison = rec_block.get("comparison") or {}
    uw = rec_block.get("underwriting_risk") or {}

    life_net = num_or_none(life_need.get("net_life_insurance_need"))
    tpd_net = num_or_none(tpd_need.get("net_tpd_need"))
    out["cover"]["life"] = life_net
    out["cover"]["tpd"] = tpd_net

    prem = num_or_none(aff.get("total_annual_premium"))
    out["premiums"]["annual"] = prem
    out["premiums"]["monthly"] = monthly_from_annual(prem) if prem else None

    out["structural"]["owner"] = normalize_ownership("PERSONAL")
    out["structural"]["replacementInvolved"] = rec_type in ("REPLACE_EXISTING", "SUPPLEMENT_EXISTING")
    out["structural"]["underwritingRequired"] = (uw.get("overall_risk") or "") in ("HIGH", "CRITICAL")

    aff_score = num_or_none(aff.get("affordability_score"))
    out["suitability"]["affordabilityScore"] = score_0_10_from_0_100(aff_score)
    short_life = life_need.get("shortfall_level")
    short_tpd = tpd_need.get("shortfall_level")
    adeq = 5.0
    if short_life in ("NONE", "MINOR") and short_tpd in ("NONE", "MINOR"):
        adeq = 8.0
    elif short_life in ("SIGNIFICANT", "CRITICAL") or short_tpd in ("SIGNIFICANT", "CRITICAL"):
        adeq = 3.5
    out["suitability"]["adequacyScore"] = adeq

    tpd_change = comparison.get("tpd_definition_change") if isinstance(comparison, dict) else None
    if tpd_change == "IMPROVED":
        out["cover"]["ownOccupationTPD"] = True
    elif tpd_change == "WORSENED":
        out["cover"]["anyOccupationTPD"] = True

    ps = None
    if isinstance(comparison, dict) and comparison.get("has_comparison_candidate"):
        dims = comparison.get("dimensions") or []
        for d in dims:
            if isinstance(d, dict) and d.get("dimension") == "Premium":
                ex = d.get("existing_value")
                nw = d.get("new_value")
                ps = "Comparable" if ex is not None and nw is not None else None
                break

    struct = (aff.get("assessment") or "").lower()
    if "stepped" in struct:
        out["structural"]["steppedOrLevel"] = "STEPPED"
    elif "level" in struct:
        out["structural"]["steppedOrLevel"] = "LEVEL"

    for w in rec_block.get("risks") or []:
        out["warnings"].append(str(w))
    val = raw.get("validation") or {}
    for w in val.get("warnings") or []:
        out["warnings"].append(w.get("message", str(w)) if isinstance(w, dict) else str(w))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Recommendation", "Structure", rec_type, str(rec_type)),
        fact_row(fk.LIFE_COVER_AMOUNT, "Net life need", "Cover", life_net, money_display(life_net)),
        fact_row(fk.TPD_COVER_AMOUNT, "Net TPD need", "Cover", tpd_net, money_display(tpd_net)),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium", "Cost", prem, money_display(prem)),
        fact_row(fk.PREMIUM_TYPE, "Premium structure", "Cost", out["structural"]["steppedOrLevel"], str(out["structural"]["steppedOrLevel"] or "Not available")),
        fact_row(
            fk.REPLACEMENT_INVOLVED,
            "Replacement involved",
            "Structure",
            out["structural"]["replacementInvolved"],
            yes_no_display(out["structural"]["replacementInvolved"]),
        ),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = rec_block.get("summary") or ""
    return out


def normalize_purchase_retain_income_protection_policy(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_income_protection_policy", tool_run_id, client_id, "", generated_at)
    rec_block = raw.get("recommendation") or {}
    rec_type = rec_block.get("type") or ""
    out["scenarioSummary"] = {
        "title": "Income protection",
        "description": rec_block.get("summary") or "",
        "recommendationType": str(rec_type),
    }
    bn = rec_block.get("benefit_need") or {}
    wait = rec_block.get("waiting_period") or {}
    bp = rec_block.get("benefit_period") or {}
    aff = rec_block.get("affordability") or {}
    pc = rec_block.get("policy_comparison")

    monthly = num_or_none(bn.get("recommended_monthly_benefit"))
    ratio = num_or_none(bn.get("replacement_ratio"))
    out["cover"]["incomeProtectionMonthly"] = monthly
    out["cover"]["incomeProtectionReplacementRatio"] = ratio
    ew = wait.get("existing_waiting_period_weeks")
    pw = wait.get("proposed_waiting_period_weeks")
    wk = pw if pw is not None else ew
    out["cover"]["waitingPeriod"] = f"{wk} weeks" if wk is not None else None
    ebm = bp.get("existing_benefit_period_months")
    pbm = bp.get("proposed_benefit_period_months")
    bm = pbm if pbm is not None else ebm
    out["cover"]["benefitPeriod"] = "To age 65" if bm == 0 else (f"{bm} months" if bm is not None else None)

    prem = num_or_none(aff.get("annual_premium"))
    if prem is None and isinstance(pc, dict):
        prem = num_or_none(pc.get("proposed_premium")) or num_or_none(pc.get("existing_premium"))
    out["premiums"]["annual"] = prem
    out["premiums"]["monthly"] = monthly_from_annual(prem) if prem else None

    out["structural"]["owner"] = "personal"
    out["structural"]["replacementInvolved"] = rec_type == "REPLACE_EXISTING"
    uw = rec_block.get("underwriting_risk") or {}
    out["structural"]["underwritingRequired"] = uw.get("overall_risk") in ("HIGH", "CRITICAL")

    out["suitability"]["affordabilityScore"] = score_0_10_from_0_100(aff.get("affordability_score"))
    sl = bn.get("shortfall_level")
    out["suitability"]["adequacyScore"] = 3.5 if sl in ("SIGNIFICANT", "CRITICAL") else (7.5 if sl in ("NONE", "MINOR") else 5.5)

    for r in rec_block.get("risks") or []:
        out["warnings"].append(str(r))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Recommendation", "Structure", rec_type, str(rec_type)),
        fact_row(fk.IP_MONTHLY_BENEFIT, "Monthly benefit", "Cover", monthly, money_display(monthly)),
        fact_row(
            fk.IP_REPLACEMENT_RATIO,
            "Replacement ratio",
            "Cover",
            ratio,
            f"{ratio * 100:.0f}%" if ratio is not None else "Not available",
        ),
        fact_row(fk.WAITING_PERIOD, "Waiting period", "Cover", out["cover"]["waitingPeriod"], out["cover"]["waitingPeriod"] or "Not available"),
        fact_row(fk.BENEFIT_PERIOD, "Benefit period", "Cover", out["cover"]["benefitPeriod"], out["cover"]["benefitPeriod"] or "Not available"),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium", "Cost", prem, money_display(prem)),
        fact_row(fk.OWNERSHIP_STRUCTURE, "Ownership", "Structure", "personal", "Personal"),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = rec_block.get("summary") or ""
    return out


def normalize_purchase_retain_ip_in_super(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_ip_in_super", tool_run_id, client_id, "", generated_at)
    placement = raw.get("placement_assessment") or {}
    rec = placement.get("recommendation") or ""
    rec_block = raw.get("recommendation") or {}
    rec_type = rec_block.get("type") or rec

    out["scenarioSummary"] = {
        "title": "Income protection in super",
        "description": rec_block.get("summary") or (placement.get("reasoning") or [""])[0],
        "recommendationType": str(rec_type),
    }

    owner = _placement_owner(str(rec))
    out["structural"]["owner"] = owner
    out["cover"]["heldInsideSuper"] = True if owner == "super" else (False if owner in ("personal",) else None)
    out["cover"]["splitOwnership"] = owner == "split"

    bn = raw.get("benefit_need") or {}
    if isinstance(bn, dict) and bn.get("status") != "INCOME_NOT_PROVIDED":
        amb = num_or_none(bn.get("active_monthly_benefit"))
        mm = num_or_none(bn.get("max_monthly_benefit"))
        out["cover"]["incomeProtectionMonthly"] = amb
        out["cover"]["incomeProtectionReplacementRatio"] = (amb / mm) if amb and mm else num_or_none(bn.get("max_replacement_ratio"))

    rd = raw.get("retirement_drag")
    annual = num_or_none(rd.get("annual_premium")) if isinstance(rd, dict) else None
    out["premiums"]["annual"] = annual
    out["premiums"]["monthly"] = monthly_from_annual(annual) if annual else None
    out["premiums"]["fundedFromSuper"] = annual if owner == "super" else None

    scores = raw.get("placement_scores") or {}
    out["suitability"]["taxEfficiencyScore"] = score_0_10_from_0_100(num_or_none(scores.get("tax_efficiency_benefit")))
    out["suitability"]["flexibilityScore"] = score_0_10_from_0_100(100 - (num_or_none(scores.get("definition_quality_penalty")) or 50))

    val = raw.get("validation") or {}
    for w in val.get("warnings") or []:
        out["warnings"].append(w.get("message", str(w)) if isinstance(w, dict) else str(w))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Recommendation", "Structure", rec_type, str(rec_type)),
        fact_row(fk.IP_MONTHLY_BENEFIT, "Active monthly benefit", "Cover", out["cover"]["incomeProtectionMonthly"], money_display(out["cover"]["incomeProtectionMonthly"])),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium (super drag)", "Cost", annual, money_display(annual)),
        fact_row(fk.OWNERSHIP_STRUCTURE, "Placement", "Structure", owner, str(owner or "Not available")),
        fact_row(fk.INSIDE_SUPER, "Inside super", "Tax / Super", owner == "super", yes_no_display(owner == "super")),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = rec_block.get("summary") or ""
    return out


def normalize_purchase_retain_tpd_in_super(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_tpd_in_super", tool_run_id, client_id, "", generated_at)
    placement = raw.get("placement_assessment") or {}
    rec = placement.get("recommendation") or ""
    out["scenarioSummary"] = {
        "title": "TPD in super",
        "description": (placement.get("reasoning") or [""])[0] if placement.get("reasoning") else "",
        "recommendationType": str(rec),
    }

    owner = _placement_owner(str(rec))
    if str(rec) == "RETAIL":
        owner = "personal"
    out["structural"]["owner"] = owner or ("split" if str(rec) == "SPLIT_STRATEGY" else None)
    out["cover"]["heldInsideSuper"] = True if rec == "INSIDE_SUPER" else (False if rec == "RETAIL" else None)
    out["cover"]["splitOwnership"] = str(rec) == "SPLIT_STRATEGY"

    cna = raw.get("coverage_needs_analysis") or {}
    tpd_low = num_or_none(cna.get("tpd_need_low"))
    tpd_high = num_or_none(cna.get("tpd_need_high"))
    tpd_mid = (tpd_low + tpd_high) / 2 if tpd_low is not None and tpd_high is not None else num_or_none(cna.get("shortfall_estimate"))
    out["cover"]["tpd"] = tpd_mid
    out["cover"]["anyOccupationTPD"] = True

    rd = raw.get("retirement_drag_estimate")
    annual = num_or_none(rd.get("annual_premium")) if isinstance(rd, dict) else None
    out["premiums"]["annual"] = annual
    out["premiums"]["monthly"] = monthly_from_annual(annual) if annual else None

    uw = raw.get("underwriting_assessment") or {}
    out["structural"]["underwritingRequired"] = bool(uw.get("above_aal"))

    val = raw.get("validation") or {}
    for w in val.get("warnings") or []:
        out["warnings"].append(w.get("message", str(w)) if isinstance(w, dict) else str(w))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Placement recommendation", "Structure", rec, str(rec)),
        fact_row(fk.TPD_COVER_AMOUNT, "TPD need focus", "Cover", tpd_mid, money_display(tpd_mid)),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium (estimate)", "Cost", annual, money_display(annual)),
        fact_row(fk.OWNERSHIP_STRUCTURE, "Structure", "Structure", out["structural"]["owner"], str(out["structural"]["owner"] or "Not available")),
        fact_row(fk.INSIDE_SUPER, "Inside super element", "Tax / Super", rec == "INSIDE_SUPER", yes_no_display(rec == "INSIDE_SUPER")),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = out["scenarioSummary"]["description"]
    return out


def normalize_purchase_retain_trauma_ci_policy(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("purchase_retain_trauma_ci_policy", tool_run_id, client_id, "", generated_at)
    rec_block = raw.get("recommendation") or {}
    rec_type = rec_block.get("type") or ""
    ci_need = raw.get("ci_need") or {}
    aff = raw.get("affordability") or {}

    out["scenarioSummary"] = {
        "title": "Trauma / critical illness",
        "description": rec_block.get("summary") or "",
        "recommendationType": str(rec_type),
    }

    trauma_si = num_or_none(ci_need.get("calculated_need_aud"))
    out["cover"]["trauma"] = trauma_si
    prem = num_or_none(aff.get("annual_premium_aud") or aff.get("annual_premium"))
    out["premiums"]["annual"] = prem
    out["premiums"]["monthly"] = monthly_from_annual(prem) if prem else None
    out["structural"]["owner"] = "personal"
    out["structural"]["replacementInvolved"] = rec_type in ("REPLACE_WITH_BETTER", "SUPPLEMENT_EXISTING")

    band = (aff.get("band") or "").upper()
    if band == "COMFORTABLE":
        out["suitability"]["affordabilityScore"] = 8.5
    elif band == "MANAGEABLE":
        out["suitability"]["affordabilityScore"] = 6.5
    elif band in ("STRETCHED", "UNAFFORDABLE"):
        out["suitability"]["affordabilityScore"] = 3.5
    out["suitability"]["adequacyScore"] = 6.0

    for r in rec_block.get("risks") or []:
        out["warnings"].append(str(r))

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Recommendation", "Structure", rec_type, str(rec_type)),
        fact_row(fk.TRAUMA_COVER_AMOUNT, "CI sum insured (need)", "Cover", trauma_si, money_display(trauma_si)),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium", "Cost", prem, money_display(prem)),
        fact_row(fk.OWNERSHIP_STRUCTURE, "Ownership", "Structure", "personal", "Personal (not in super)"),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = rec_block.get("summary") or ""
    return out


def normalize_tpd_policy_assessment(
    raw: dict[str, Any],
    *,
    tool_run_id: str,
    client_id: str,
    generated_at: str,
) -> dict[str, Any]:
    out = _base("tpd_policy_assessment", tool_run_id, client_id, "", generated_at)
    rec = raw.get("recommendation") or {}
    rec_type = rec.get("type") if isinstance(rec, dict) else ""
    summary_text = rec.get("summary", "") if isinstance(rec, dict) else ""

    out["scenarioSummary"] = {
        "title": "TPD policy assessment",
        "description": summary_text,
        "recommendationType": str(rec_type),
    }

    tpd_need = raw.get("tpd_need") or {}
    gap = num_or_none(tpd_need.get("gap_aud") or tpd_need.get("net_shortfall_aud"))
    out["cover"]["tpd"] = gap

    prem_eval = raw.get("premium_structure") or {}
    annual = num_or_none(prem_eval.get("annual_premium_aud") or prem_eval.get("annual_premium"))
    out["premiums"]["annual"] = annual
    out["premiums"]["monthly"] = monthly_from_annual(annual) if annual else None

    def_eval = raw.get("definition_evaluation") or {}
    dq = (def_eval.get("definition_quality") or "").upper()
    out["cover"]["ownOccupationTPD"] = dq in ("EXCELLENT", "GOOD") and "OWN" in str(def_eval.get("definition") or "").upper()
    sp = raw.get("super_placement") or {}
    out["cover"]["heldInsideSuper"] = bool(sp.get("in_super"))

    prop = raw.get("proposed_policy_comparison")
    if isinstance(prop, dict):
        out["structural"]["replacementInvolved"] = True
        out["structural"]["insurer"] = prop.get("proposed_insurer")

    facts: list[dict] = [
        fact_row(fk.RECOMMENDATION_TYPE, "Recommendation", "Structure", rec_type, str(rec_type)),
        fact_row(fk.TPD_COVER_AMOUNT, "TPD gap / need focus", "Cover", gap, money_display(gap)),
        fact_row(fk.ANNUAL_PREMIUM, "Annual premium", "Cost", annual, money_display(annual)),
        fact_row(fk.INSIDE_SUPER, "Inside super", "Tax / Super", out["cover"]["heldInsideSuper"], yes_no_display(out["cover"]["heldInsideSuper"])),
    ]
    out["comparisonFacts"] = facts
    out["explanation"] = summary_text
    return out


TOOL_NORMALIZERS: dict[str, Any] = {
    "purchase_retain_life_insurance_in_super": normalize_purchase_retain_life_insurance_in_super,
    "purchase_retain_life_tpd_policy": normalize_purchase_retain_life_tpd_policy,
    "purchase_retain_income_protection_policy": normalize_purchase_retain_income_protection_policy,
    "purchase_retain_ip_in_super": normalize_purchase_retain_ip_in_super,
    "purchase_retain_tpd_in_super": normalize_purchase_retain_tpd_in_super,
    "purchase_retain_trauma_ci_policy": normalize_purchase_retain_trauma_ci_policy,
    "tpd_policy_assessment": normalize_tpd_policy_assessment,
}
