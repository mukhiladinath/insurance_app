"""Orchestrate dashboard resolution, deterministic projections, persistence."""

from __future__ import annotations

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.client_insurance_dashboard_repository import ClientInsuranceDashboardRepository
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.insurance_dashboard_session_repository import InsuranceDashboardSessionRepository
from app.services.insurance_dashboard.input_resolution import (
    build_resolved_inputs,
    detect_insurance_types_present,
    infer_dashboard_type,
    missing_fields_for_dashboard,
)
from app.services.insurance_dashboard.projection_engine import (
    build_yearly_insurance_projection,
    build_yearly_ip_projection,
    build_yearly_tpd_projection,
    calculate_cover_adequacy,
    calculate_family_protection_outcome,
    calculate_premium_impact,
    compare_insurance_strategies,
    compute_affordability_flag,
    normalize_projection_horizon,
)
from app.services.insurance_dashboard.spec_builder import build_dashboard_spec

logger = logging.getLogger(__name__)


class DashboardGenerationError(Exception):
    """Business-rule failure (e.g. comparison needs two analyses)."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


def _source_label(meta: dict[str, Any] | None) -> str:
    if not meta:
        return "Saved analyses / client context"
    oid = meta.get("analysis_output_id")
    idx = meta.get("step_index")
    tid = meta.get("tool_id") or ""
    if oid is not None and idx is not None:
        return f"Saved analysis {str(oid)[:8]}… step {idx} ({tid})"
    return "Saved analyses"


def _snapshot_bar_chart(ex_life: Any, rec_life: Any) -> dict[str, Any]:
    return {
        "id": "cover_snapshot_bar",
        "type": "bar",
        "title": "Current vs recommended cover (today)",
        "series": [
            {"name": "Existing", "value": ex_life},
            {"name": "Recommended", "value": rec_life},
        ],
    }


def _yearly_projection_charts(yearly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build multi-chart spec from deterministic yearly rows."""
    if not yearly_rows:
        return []
    data = yearly_rows
    charts: list[dict[str, Any]] = [
        {
            "id": "proj_need_vs_covers",
            "type": "line",
            "title": "Protection need vs existing vs recommended cover over time",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Required cover", "dataKey": "requiredCover"},
                {"name": "Existing cover", "dataKey": "existingCover"},
                {"name": "Recommended cover", "dataKey": "recommendedCover"},
            ],
            "data": data,
        },
        {
            "id": "proj_shortfall",
            "type": "line",
            "title": "Shortfall over time",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Shortfall (vs existing)", "dataKey": "shortfallExisting"},
                {"name": "Shortfall (vs recommended)", "dataKey": "shortfallRecommended"},
            ],
            "data": data,
        },
        {
            "id": "proj_debt_support",
            "type": "line",
            "title": "Debt and support needs over time",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Outstanding debt", "dataKey": "outstandingDebt"},
                {"name": "Dependent support need", "dataKey": "dependentSupportNeed"},
                {"name": "Income support need", "dataKey": "incomeSupportNeed"},
            ],
            "data": data,
        },
        {
            "id": "proj_adequacy",
            "type": "line",
            "title": "Adequacy ratio over time (cover ÷ required)",
            "xKey": "year",
            "valueFormat": "ratio",
            "lines": [
                {"name": "Existing ÷ required", "dataKey": "adequacyRatioExisting"},
                {"name": "Recommended ÷ required", "dataKey": "adequacyRatioRecommended"},
            ],
            "data": data,
        },
    ]
    if any(
        r.get("premiumAffordabilityRatioExisting") is not None
        or r.get("premiumAffordabilityRatioRecommended") is not None
        for r in data
    ):
        charts.append(
            {
                "id": "proj_premium_affordability",
                "type": "line",
                "title": "Premium affordability over time (premium ÷ income)",
                "xKey": "year",
                "valueFormat": "percent",
                "lines": [
                    {"name": "Existing cover premium", "dataKey": "premiumAffordabilityRatioExisting"},
                    {"name": "Recommended cover premium", "dataKey": "premiumAffordabilityRatioRecommended"},
                ],
                "data": data,
            }
        )
    return charts


def _yearly_tpd_charts(yearly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not yearly_rows:
        return []
    data = yearly_rows
    return [
        {
            "id": "tpd_income_vs_lump",
            "type": "line",
            "title": "TPD: income replacement need vs lump-sum need vs cover",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Income replacement need (annual)", "dataKey": "incomeReplacementNeed"},
                {"name": "Lump-sum need", "dataKey": "lumpSumNeed"},
                {"name": "Existing TPD cover", "dataKey": "existingCover"},
                {"name": "Recommended TPD cover", "dataKey": "recommendedCover"},
            ],
            "data": data,
        },
        {
            "id": "tpd_shortfall",
            "type": "line",
            "title": "TPD: shortfall over time",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Shortfall (vs existing)", "dataKey": "shortfallExisting"},
                {"name": "Shortfall (vs recommended)", "dataKey": "shortfallRecommended"},
            ],
            "data": data,
        },
        {
            "id": "tpd_adequacy",
            "type": "line",
            "title": "TPD: adequacy ratio over time",
            "xKey": "year",
            "valueFormat": "ratio",
            "lines": [
                {"name": "Existing ÷ required", "dataKey": "adequacyRatioExisting"},
                {"name": "Recommended ÷ required", "dataKey": "adequacyRatioRecommended"},
            ],
            "data": data,
        },
        {
            "id": "tpd_years_income",
            "type": "line",
            "title": "TPD: years of income equivalent (lump sum ÷ income)",
            "xKey": "year",
            "valueFormat": "ratio",
            "lines": [
                {"name": "Existing cover", "dataKey": "yearsOfIncomeCoveredExisting"},
                {"name": "Recommended cover", "dataKey": "yearsOfIncomeCoveredRecommended"},
            ],
            "data": data,
        },
    ]


def _yearly_ip_charts(yearly_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not yearly_rows:
        return []
    data = yearly_rows
    charts: list[dict[str, Any]] = [
        {
            "id": "ip_benefit_need",
            "type": "line",
            "title": "Income protection: annual benefit need vs existing vs recommended (annualized)",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Required annual benefit", "dataKey": "requiredCover"},
                {"name": "Existing annual benefit", "dataKey": "existingCover"},
                {"name": "Recommended annual benefit", "dataKey": "recommendedCover"},
            ],
            "data": data,
        },
        {
            "id": "ip_shortfall",
            "type": "line",
            "title": "Income protection: shortfall over time",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [
                {"name": "Shortfall (vs existing)", "dataKey": "shortfallExisting"},
                {"name": "Shortfall (vs recommended)", "dataKey": "shortfallRecommended"},
            ],
            "data": data,
        },
        {
            "id": "ip_adequacy",
            "type": "line",
            "title": "Income protection: adequacy ratio over time",
            "xKey": "year",
            "valueFormat": "ratio",
            "lines": [
                {"name": "Existing ÷ required", "dataKey": "adequacyRatioExisting"},
                {"name": "Recommended ÷ required", "dataKey": "adequacyRatioRecommended"},
            ],
            "data": data,
        },
        {
            "id": "ip_monthly_track",
            "type": "line",
            "title": "Income protection: monthly benefit need (illustrative taper)",
            "xKey": "year",
            "valueFormat": "currency",
            "lines": [{"name": "Monthly benefit need", "dataKey": "monthlyBenefitNeed"}],
            "data": data,
        },
    ]
    if any(
        r.get("premiumAffordabilityRatioExisting") is not None
        or r.get("premiumAffordabilityRatioRecommended") is not None
        for r in data
    ):
        charts.append(
            {
                "id": "ip_premium_affordability",
                "type": "line",
                "title": "Premium affordability over time (premium ÷ income)",
                "xKey": "year",
                "valueFormat": "percent",
                "lines": [
                    {"name": "Reference premium", "dataKey": "premiumAffordabilityRatioExisting"},
                    {"name": "Recommended premium", "dataKey": "premiumAffordabilityRatioRecommended"},
                ],
                "data": data,
            }
        )
    return charts


def _run_yearly_projection(resolved: dict[str, Any]) -> dict[str, Any]:
    """Single source of truth for yearly deterministic projection."""
    rec_life = resolved.get("recommended_life_cover")
    ex_life = resolved.get("existing_life_cover")
    R0 = float(rec_life or 0)
    horizon = normalize_projection_horizon(resolved.get("projection_horizon"))
    dep_decay = resolved.get("dependent_support_decay_years")
    if dep_decay is None:
        dep_decay = resolved.get("years_independence_horizon")
    inc_y = resolved.get("income_support_years")
    debt_pay = resolved.get("debt_payoff_years")
    tol = resolved.get("premium_tolerance_ratio")
    if tol is not None:
        try:
            tol = float(tol)
        except (TypeError, ValueError):
            tol = None

    return build_yearly_insurance_projection(
        horizon_years=horizon,
        required_cover_year0=R0,
        existing_cover=float(ex_life) if ex_life is not None else None,
        recommended_cover=float(rec_life) if rec_life is not None else None,
        mortgage_balance=resolved.get("mortgage_balance"),
        debt_payoff_years=int(debt_pay) if debt_pay is not None else None,
        dependent_support_decay_years=int(dep_decay) if dep_decay is not None else None,
        income_support_years=int(inc_y) if inc_y is not None else None,
        dependants_count=resolved.get("dependants_count"),
        annual_income=resolved.get("annual_gross_income"),
        monthly_living_expense=resolved.get("monthly_living_expense"),
        premium_annual_existing=resolved.get("existing_annual_premium"),
        premium_annual_recommended=resolved.get("recommended_annual_premium"),
        premium_tolerance_ratio=tol,
    )


def _run_yearly_tpd_projection(resolved: dict[str, Any]) -> dict[str, Any]:
    rec = resolved.get("recommended_tpd_cover")
    ex = resolved.get("existing_tpd_cover")
    R0 = float(rec or 0)
    horizon = normalize_projection_horizon(resolved.get("projection_horizon"))
    inc_y = resolved.get("income_support_years")
    tol = resolved.get("premium_tolerance_ratio")
    if tol is not None:
        try:
            tol = float(tol)
        except (TypeError, ValueError):
            tol = None
    return build_yearly_tpd_projection(
        horizon_years=horizon,
        lump_sum_need_year0=R0,
        existing_tpd_cover=float(ex) if ex is not None else None,
        recommended_tpd_cover=float(rec) if rec is not None else None,
        annual_income=resolved.get("annual_gross_income"),
        income_support_years=int(inc_y) if inc_y is not None else None,
        premium_annual_existing=resolved.get("existing_annual_premium"),
        premium_annual_recommended=resolved.get("recommended_annual_premium"),
        premium_tolerance_ratio=tol,
    )


def _run_yearly_ip_projection(resolved: dict[str, Any]) -> dict[str, Any]:
    rec_m = resolved.get("recommended_ip_monthly_benefit")
    ex_m = resolved.get("existing_ip_monthly_benefit")
    m0 = float(rec_m or 0)
    horizon = normalize_projection_horizon(resolved.get("projection_horizon"))
    inc_y = resolved.get("income_support_years")
    tol = resolved.get("premium_tolerance_ratio")
    if tol is not None:
        try:
            tol = float(tol)
        except (TypeError, ValueError):
            tol = None
    return build_yearly_ip_projection(
        horizon_years=horizon,
        monthly_benefit_need_year0=m0,
        existing_monthly_benefit=float(ex_m) if ex_m is not None else None,
        recommended_monthly_benefit=float(rec_m) if rec_m is not None else None,
        annual_income=resolved.get("annual_gross_income"),
        income_support_years=int(inc_y) if inc_y is not None else None,
        premium_annual_existing=resolved.get("existing_annual_premium"),
        premium_annual_recommended=resolved.get("recommended_annual_premium"),
        premium_tolerance_ratio=tol,
    )


def insurance_kind_label(kind: str) -> str:
    return {"life": "Life", "tpd": "TPD", "income_protection": "Income protection"}.get(kind, kind)


def compute_projection_bundle(
    dashboard_type: str,
    resolved: dict[str, Any],
    *,
    insurance_kind: str = "life",
) -> dict[str, Any]:
    """Deterministic charts/cards/tables — core output is yearlyProjection + chart specs."""
    ik = insurance_kind
    if ik == "life":
        rec_life = resolved.get("recommended_life_cover")
        ex_life = resolved.get("existing_life_cover")
    elif ik == "tpd":
        rec_life = resolved.get("recommended_tpd_cover")
        ex_life = resolved.get("existing_tpd_cover")
    else:
        rec_life = resolved.get("recommended_ip_monthly_benefit")
        ex_life = resolved.get("existing_ip_monthly_benefit")

    rec_prem = resolved.get("recommended_annual_premium")
    ex_prem = resolved.get("existing_annual_premium")
    income = resolved.get("annual_gross_income")
    horizon_disp = normalize_projection_horizon(resolved.get("projection_horizon"))

    if ik == "income_protection":
        rec_a = (rec_life * 12.0) if rec_life is not None else None
        ex_a = (ex_life * 12.0) if ex_life is not None else None
        adequacy = calculate_cover_adequacy(existing_cover=ex_a, recommended_cover=rec_a)
    else:
        adequacy = calculate_cover_adequacy(existing_cover=ex_life, recommended_cover=rec_life)
    prem_imp = calculate_premium_impact(
        current_annual_premium=ex_prem,
        recommended_annual_premium=rec_prem,
    )
    aff = compute_affordability_flag(annual_premium=rec_prem or ex_prem, annual_income=income)

    if ik == "life":
        summary_cards = [
            {"id": "existing_cover", "label": "Existing life cover", "value": ex_life, "format": "currency"},
            {"id": "recommended_cover", "label": "Recommended life cover", "value": rec_life, "format": "currency"},
            {"id": "shortfall", "label": "Shortfall / surplus", "value": adequacy.get("shortfall") or adequacy.get("surplus"), "format": "currency"},
            {"id": "annual_premium", "label": "Annual premium (ref.)", "value": rec_prem or ex_prem, "format": "currency"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]
    elif ik == "tpd":
        summary_cards = [
            {"id": "existing_cover", "label": "Existing TPD cover", "value": ex_life, "format": "currency"},
            {"id": "recommended_cover", "label": "Recommended TPD cover", "value": rec_life, "format": "currency"},
            {"id": "shortfall", "label": "Shortfall / surplus", "value": adequacy.get("shortfall") or adequacy.get("surplus"), "format": "currency"},
            {"id": "annual_premium", "label": "Annual premium (ref.)", "value": rec_prem or ex_prem, "format": "currency"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]
    else:
        summary_cards = [
            {"id": "existing_cover", "label": "Existing monthly benefit", "value": ex_life, "format": "currency"},
            {"id": "recommended_cover", "label": "Recommended monthly benefit", "value": rec_life, "format": "currency"},
            {"id": "shortfall", "label": "Shortfall / surplus (annualized)", "value": adequacy.get("shortfall") or adequacy.get("surplus"), "format": "currency"},
            {"id": "annual_premium", "label": "Annual premium (ref.)", "value": rec_prem or ex_prem, "format": "currency"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]

    tables: list[dict[str, Any]] = [
        {
            "id": "adequacy",
            "title": "Cover adequacy (today)",
            "columns": ["Metric", "Value"],
            "rows": [
                ["Status", str(adequacy.get("status"))],
                ["Adequacy ratio", f"{adequacy.get('adequacyRatio'):.2f}" if adequacy.get("adequacyRatio") is not None else "—"],
            ],
        }
    ]

    insights: list[str] = []
    warnings: list[str] = []
    if adequacy.get("status") == "shortfall":
        insights.append(
            "Recommended amount is above current cover — review funding and priorities."
            if ik != "income_protection"
            else "Recommended IP benefit is above current benefit on an annualized basis — review funding and priorities.",
        )
    if aff.get("status") == "stretched":
        warnings.append("Premium relative to income is above typical affordability thresholds (illustrative).")

    controls: list[dict[str, Any]] = [
        {
            "id": "projection_horizon",
            "label": "Projection horizon (years)",
            "field": "dashboard.projection_horizon",
            "inputType": "select",
            "options": [10, 15, 20, 25],
        },
        {
            "id": "adjust_recommended_cover",
            "label": {
                "life": "Recommended life cover override ($)",
                "tpd": "Recommended TPD cover override ($)",
                "income_protection": "Recommended monthly IP benefit override ($)",
            }.get(ik, "Recommended cover override ($)"),
            "field": {
                "life": "dashboard.recommended_life_cover",
                "tpd": "dashboard.recommended_tpd_cover",
                "income_protection": "dashboard.recommended_ip_monthly_benefit",
            }.get(ik, "dashboard.recommended_life_cover"),
            "inputType": "number",
        },
        {
            "id": "dependent_support_decay",
            "label": "Dependent support taper (years)",
            "field": "dashboard.dependent_support_decay_years",
            "inputType": "number",
        },
        {
            "id": "income_support_years",
            "label": "Income support taper (years)",
            "field": "dashboard.income_support_years",
            "inputType": "number",
        },
        {
            "id": "debt_payoff_years",
            "label": "Debt payoff (years)",
            "field": "dashboard.debt_payoff_years",
            "inputType": "number",
        },
        {
            "id": "years_independence",
            "label": "Years to dependant independence (fallback taper)",
            "field": "dashboard.years_independence_horizon",
            "inputType": "number",
        },
        {
            "id": "premium_tolerance",
            "label": "Premium tolerance (income fraction, e.g. 0.08)",
            "field": "dashboard.premium_tolerance_ratio",
            "inputType": "number",
        },
    ]

    projection_data: dict[str, Any] = {
        "coverAdequacy": adequacy,
        "premiumImpact": prem_imp,
        "affordability": aff,
    }

    if ik == "life":
        yproj = _run_yearly_projection(resolved)
    elif ik == "tpd":
        yproj = _run_yearly_tpd_projection(resolved)
    else:
        yproj = _run_yearly_ip_projection(resolved)
    projection_data["yearlyProjection"] = yproj
    projection_data["yearlySeries"] = yproj.get("yearlySeries") or []
    projection_data["insuranceKind"] = ik
    insights.extend(yproj.get("projectionAssumptions") or [])
    ys = yproj.get("yearlySeries") or []
    if ik == "life":
        yearly_charts = _yearly_projection_charts(ys)
    elif ik == "tpd":
        yearly_charts = _yearly_tpd_charts(ys)
    else:
        yearly_charts = _yearly_ip_charts(ys)

    snap = _snapshot_bar_chart(ex_life, rec_life)
    if ik == "tpd":
        snap["title"] = "Current vs recommended TPD cover (today)"
    elif ik == "income_protection":
        snap["title"] = "Current vs recommended monthly benefit (today)"
    charts: list[dict[str, Any]] = [snap] + yearly_charts

    if dashboard_type == "premium_affordability":
        summary_cards = [
            {"id": "current_prem", "label": "Current / reference annual premium", "value": ex_prem, "format": "currency"},
            {"id": "rec_prem", "label": "Recommended annual premium", "value": rec_prem, "format": "currency"},
            {"id": "delta", "label": "Annual difference", "value": prem_imp.get("deltaAnnual"), "format": "currency"},
            {"id": "afford_ratio", "label": "Premium / income", "value": aff.get("ratio"), "format": "percent"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]
        charts = [
            snap,
            {
                "id": "premium_bar",
                "type": "bar",
                "title": "Premium comparison (today)",
                "series": [
                    {"name": "Reference", "value": ex_prem},
                    {"name": "Recommended", "value": rec_prem},
                ],
            },
            *yearly_charts,
        ]
        projection_data["premiumAffordability"] = aff

    if dashboard_type == "protection_gap_time":
        if ik == "income_protection":
            need0 = float((rec_life or 0) * 12.0)
            existing = float((ex_life or 0) * 12.0)
            need_label = "Initial annual benefit need"
        else:
            need0 = float(rec_life or 0)
            existing = float(ex_life or 0)
            need_label = "Initial need"
        summary_cards = [
            {"id": "horizon", "label": "Horizon (years)", "value": horizon_disp, "format": "number"},
            {"id": "need_now", "label": need_label, "value": need0, "format": "currency"},
            {"id": "existing", "label": "Existing cover" if ik != "income_protection" else "Existing (annualized)", "value": existing, "format": "currency"},
            {"id": "rec_cover", "label": "Recommended cover" if ik != "income_protection" else "Recommended (annualized)", "value": rec_life if ik != "income_protection" else (rec_life or 0) * 12.0, "format": "currency"},
        ]
        tables = tables + [
            {
                "id": "milestones",
                "title": "Projection window",
                "columns": ["Label", "Year"],
                "rows": [["Start", 0], ["End", horizon_disp]],
            }
        ]

    if dashboard_type == "family_protection_outcome" and ik == "life":
        fp = calculate_family_protection_outcome(
            life_cover=resolved.get("recommended_life_cover") or resolved.get("existing_life_cover"),
            total_debts=resolved.get("mortgage_balance"),
            annual_income=income,
            monthly_living_expense=resolved.get("monthly_living_expense"),
        )
        projection_data["familyProtectionOutcome"] = fp
        summary_cards = [
            {"id": "cover", "label": "Life cover available", "value": fp.get("lifeCoverAvailable"), "format": "currency"},
            {"id": "debts", "label": "Debts assumed", "value": fp.get("debtsAssumed"), "format": "currency"},
            {"id": "years_support", "label": "Years of expense support (illustrative)", "value": fp.get("yearsOfIncomeSupportFunded"), "format": "number"},
            {"id": "stress", "label": "Financial stress risk", "value": fp.get("financialStressRisk"), "format": "text"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]

    if dashboard_type == "strategy_comparison":
        na = resolved.get("primary_normalized")
        nb = resolved.get("secondary_normalized")
        if not na or not nb:
            raise DashboardGenerationError("needs_second_analysis", "Two saved tool outputs are required for strategy comparison.")
        ma = resolved.get("primary_meta") or {}
        mb = resolved.get("secondary_meta") or {}
        comp = compare_insurance_strategies(
            label_a=ma.get("tool_id") or "A",
            norm_a=na,
            label_b=mb.get("tool_id") or "B",
            norm_b=nb,
        )
        projection_data["strategyComparison"] = comp
        compare_blocks: list[dict[str, Any]] = [
            {
                "id": "compare_premium",
                "type": "bar",
                "title": "Annual premium (strategies)",
                "series": [
                    {"name": comp["labelA"], "value": (na.get("premiums") or {}).get("annual")},
                    {"name": comp["labelB"], "value": (nb.get("premiums") or {}).get("annual")},
                ],
            },
        ]
        if ik == "life":
            compare_blocks.append(
                {
                    "id": "compare_life",
                    "type": "bar",
                    "title": "Life cover (strategies)",
                    "series": [
                        {"name": comp["labelA"], "value": (na.get("cover") or {}).get("life")},
                        {"name": comp["labelB"], "value": (nb.get("cover") or {}).get("life")},
                    ],
                }
            )
        elif ik == "tpd":
            compare_blocks.append(
                {
                    "id": "compare_tpd",
                    "type": "bar",
                    "title": "TPD cover (strategies)",
                    "series": [
                        {"name": comp["labelA"], "value": (na.get("cover") or {}).get("tpd")},
                        {"name": comp["labelB"], "value": (nb.get("cover") or {}).get("tpd")},
                    ],
                }
            )
        else:
            compare_blocks.append(
                {
                    "id": "compare_ip",
                    "type": "bar",
                    "title": "IP monthly benefit (strategies)",
                    "series": [
                        {"name": comp["labelA"], "value": (na.get("cover") or {}).get("incomeProtectionMonthly")},
                        {"name": comp["labelB"], "value": (nb.get("cover") or {}).get("incomeProtectionMonthly")},
                    ],
                }
            )
        compare_blocks.append(snap)
        charts = compare_blocks + yearly_charts
        tables = [
            {
                "id": "compare_table",
                "title": "Strategy comparison",
                "columns": ["Metric", "Option A", "Option B"],
                "rows": [[r["metric"], r["A"], r["B"]] for r in comp.get("rows") or []],
            }
        ]
        summary_cards = [
            {"id": "a_prem", "label": "Premium A", "value": (na.get("premiums") or {}).get("annual"), "format": "currency"},
            {"id": "b_prem", "label": "Premium B", "value": (nb.get("premiums") or {}).get("annual"), "format": "currency"},
            {"id": "proj_horizon", "label": "Projection horizon (years)", "value": horizon_disp, "format": "number"},
        ]
        insights.append("Comparison uses normalized fields from each saved analysis — review assumptions in the underlying tools.")

    return {
        "summaryCards": summary_cards,
        "charts": charts,
        "tables": tables,
        "insights": insights,
        "warnings": warnings,
        "controls": controls,
        "projection_data": projection_data,
    }


async def generate_insurance_dashboard(
    db: AsyncIOMotorDatabase,
    *,
    client_id: str,
    user_id: str | None,
    instruction: str | None,
    dashboard_type: str | None,
    analysis_output_id: str | None,
    step_index: int | None,
    second_analysis_output_id: str | None,
    second_step_index: int | None,
    session_token: str | None,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """
    Returns:
      { "status": "complete", "dashboard": {...}, "missing_fields": [] }
      or
      { "status": "missing_fields", "missing_fields": [...], "session_token": "..." }
    """
    dtype = infer_dashboard_type(instruction, dashboard_type)

    sess_repo = InsuranceDashboardSessionRepository(db)
    accumulated: dict[str, Any] = dict(overrides)

    if session_token:
        sess = await sess_repo.get_by_token(session_token)
        if not sess or sess.get("client_id") != client_id or sess.get("status") != "pending":
            raise ValueError("Invalid or expired dashboard session.")
        merged_overrides = dict(sess.get("accumulated_overrides") or {})
        merged_overrides.update(overrides)
        accumulated = merged_overrides
        dtype = sess.get("dashboard_type") or dtype
        analysis_output_id = analysis_output_id or sess.get("analysis_output_id")
        step_index = step_index if step_index is not None else sess.get("step_index")
        second_analysis_output_id = second_analysis_output_id or sess.get("second_analysis_output_id")
        second_step_index = second_step_index if second_step_index is not None else sess.get("second_step_index")
        await sess_repo.update_overrides(session_token, overrides)

    resolved = await build_resolved_inputs(
        db,
        client_id,
        analysis_output_id=analysis_output_id,
        step_index=step_index,
        second_analysis_output_id=second_analysis_output_id,
        second_step_index=second_step_index,
        overrides=accumulated,
    )

    if dtype == "strategy_comparison" and resolved.get("secondary_normalized") is None:
        raise DashboardGenerationError(
            "needs_second_analysis",
            "Save at least two insurance tool results (or run a compare with two steps) before opening a strategy comparison dashboard.",
        )

    missing = missing_fields_for_dashboard(dtype, resolved)
    if missing:
        if not session_token:
            sess_doc = await sess_repo.create(
                client_id=client_id,
                dashboard_type=dtype,
                instruction=instruction or "",
                analysis_output_id=analysis_output_id,
                step_index=step_index,
                second_analysis_output_id=second_analysis_output_id,
                second_step_index=second_step_index,
                accumulated_overrides=accumulated,
            )
            token = sess_doc.get("session_token") or ""
        else:
            token = session_token
        return {
            "status": "missing_fields",
            "missing_fields": missing,
            "session_token": token,
            "partial_resolved": {
                k: resolved.get(k)
                for k in (
                    "recommended_life_cover",
                    "recommended_tpd_cover",
                    "recommended_ip_monthly_benefit",
                    "annual_gross_income",
                )
                if k in resolved
            },
        }

    kinds = detect_insurance_types_present(resolved.get("primary_normalized"), resolved)
    if not kinds:
        kinds = ["life"]

    bundles_by_kind: dict[str, Any] = {}
    projection_by_kind: dict[str, Any] = {}
    for k in kinds:
        b = compute_projection_bundle(dtype, resolved, insurance_kind=k)
        projection_by_kind[k] = b.pop("projection_data")
        bundles_by_kind[k] = b

    first_kind = kinds[0]
    bundle = bundles_by_kind[first_kind]
    projection_data = {**projection_by_kind[first_kind], "insuranceDashboards": projection_by_kind}

    client_repo = ClientRepository(db)
    client_doc = await client_repo.get_by_id(client_id)
    client_name = client_doc.get("name") if client_doc else None

    primary_meta = resolved.get("primary_meta")
    resolved = dict(resolved)
    horizon_disp = normalize_projection_horizon(resolved.get("projection_horizon"))
    ypa: list[str] = []
    for _k in kinds:
        ypa.extend((projection_by_kind[_k].get("yearlyProjection") or {}).get("projectionAssumptions") or [])
    resolved["assumptions_table"] = [
        {"label": "Annual gross income", "value": resolved.get("annual_gross_income"), "format": "currency"},
        {"label": "Dependants", "value": resolved.get("dependants_count"), "format": "number"},
        {"label": "Projection horizon (years)", "value": resolved.get("projection_horizon") or horizon_disp, "format": "number"},
        {"label": "Years to independence (taper fallback)", "value": resolved.get("years_independence_horizon"), "format": "number"},
        {"label": "Dependent support taper (years)", "value": resolved.get("dependent_support_decay_years"), "format": "number"},
        {"label": "Income support taper (years)", "value": resolved.get("income_support_years"), "format": "number"},
        {"label": "Debt payoff (years)", "value": resolved.get("debt_payoff_years"), "format": "number"},
        {"label": "Premium tolerance (of income)", "value": resolved.get("premium_tolerance_ratio"), "format": "ratio"},
        *[{"label": f"Note {i + 1}", "value": text, "format": "text"} for i, text in enumerate(ypa)],
    ]
    title = {
        "insurance_needs": "Insurance needs dashboard",
        "premium_affordability": "Premium affordability dashboard",
        "protection_gap_time": "Protection gap over time",
        "family_protection_outcome": "Family protection outcome",
        "strategy_comparison": "Strategy comparison dashboard",
    }.get(dtype, "Insurance dashboard")

    spec = build_dashboard_spec(
        title=title,
        dashboard_type=dtype,
        client_name=client_name,
        source_label=_source_label(primary_meta if isinstance(primary_meta, dict) else None),
        resolved=resolved,
        projections=bundle,
    )
    spec["insuranceDashboards"] = {
        k: build_dashboard_spec(
            title=f"{title} — {insurance_kind_label(k)}",
            dashboard_type=dtype,
            client_name=client_name,
            source_label=_source_label(primary_meta if isinstance(primary_meta, dict) else None),
            resolved=resolved,
            projections=bundles_by_kind[k],
        )
        for k in kinds
    }

    src_ids: list[str] = []
    if isinstance(primary_meta, dict) and primary_meta.get("analysis_output_id"):
        src_ids.append(str(primary_meta["analysis_output_id"]))
    sm = resolved.get("secondary_meta")
    if isinstance(sm, dict) and sm.get("analysis_output_id"):
        src_ids.append(str(sm["analysis_output_id"]))

    tool_ids: list[str] = []
    if isinstance(primary_meta, dict) and primary_meta.get("tool_id"):
        tool_ids.append(str(primary_meta["tool_id"]))
    if isinstance(sm, dict) and sm.get("tool_id"):
        tool_ids.append(str(sm["tool_id"]))

    dash_repo = ClientInsuranceDashboardRepository(db)
    assumptions = {
        "years_independence_horizon": resolved.get("years_independence_horizon"),
        "projection_horizon": horizon_disp,
        "dependency_decay": True,
        "primary_analysis_output_id": (primary_meta or {}).get("analysis_output_id") if isinstance(primary_meta, dict) else None,
        "primary_step_index": (primary_meta or {}).get("step_index") if isinstance(primary_meta, dict) else None,
        "second_analysis_output_id": (sm or {}).get("analysis_output_id") if isinstance(sm, dict) else None,
        "second_step_index": (sm or {}).get("step_index") if isinstance(sm, dict) else None,
        "yearly_series_length": len(projection_data.get("yearlySeries") or []),
        "insurance_kinds": kinds,
    }
    saved = await dash_repo.create(
        client_id=client_id,
        organization_id=None,
        title=title,
        dashboard_type=dtype,
        source_analysis_ids=src_ids,
        source_tool_ids=tool_ids,
        source_recommendation_ids=[],
        assumptions=assumptions,
        resolved_inputs={
            k: v
            for k, v in resolved.items()
            if not k.endswith("_normalized") and not k.endswith("_meta")
        },
        projection_data=projection_data,
        dashboard_spec=spec,
        ai_context_snapshot={"instruction": instruction},
        created_by=user_id,
    )

    if session_token:
        await sess_repo.complete(session_token)

    return {
        "status": "complete",
        "dashboard": saved,
        "missing_fields": [],
        "session_token": None,
    }
