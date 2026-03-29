"""Tests for deterministic insurance dashboard projection and resolution helpers."""

import pytest

from app.services.insurance_dashboard.input_resolution import (
    detect_insurance_types_present,
    infer_dashboard_type,
    merge_layers,
)
from app.services.insurance_dashboard.projection_engine import (
    build_yearly_insurance_projection,
    build_yearly_tpd_projection,
    calculate_cover_adequacy,
    calculate_premium_impact,
    calculate_protection_gap_over_time,
    compare_insurance_strategies,
    compute_affordability_flag,
    normalize_projection_horizon,
)
from app.services.insurance_dashboard.service import compute_projection_bundle


def test_calculate_cover_adequacy_shortfall():
    r = calculate_cover_adequacy(existing_cover=300_000, recommended_cover=500_000)
    assert r["status"] == "shortfall"
    assert r["shortfall"] == 200_000


def test_calculate_premium_impact_delta():
    r = calculate_premium_impact(current_annual_premium=2000, recommended_annual_premium=3200)
    assert r["deltaAnnual"] == 1200
    assert r["deltaMonthly"] == pytest.approx(100.0)


def test_protection_gap_series_length():
    r = calculate_protection_gap_over_time(
        required_cover_year0=500_000,
        existing_cover=200_000,
        horizon_years=5,
        dependency_decay=True,
    )
    assert len(r["series"]) == 6
    assert r["series"][0]["shortfall"] >= r["series"][-1]["shortfall"]


def test_affordability_flag():
    r = compute_affordability_flag(annual_premium=8000, annual_income=100_000, threshold=0.08)
    assert r["affordable"] is True
    r2 = compute_affordability_flag(annual_premium=12_000, annual_income=100_000, threshold=0.08)
    assert r2["affordable"] is False


def test_compare_insurance_strategies():
    a = {"toolName": "t1", "cover": {"life": 400_000}, "premiums": {"annual": 2000}, "suitability": {}}
    b = {"toolName": "t2", "cover": {"life": 500_000}, "premiums": {"annual": 2400}, "suitability": {}}
    out = compare_insurance_strategies(label_a="A", norm_a=a, label_b="B", norm_b=b)
    assert len(out["rows"]) >= 3


def test_infer_dashboard_type_keywords():
    assert infer_dashboard_type("show protection gap over time", None) == "protection_gap_time"
    assert infer_dashboard_type("premium affordability", None) == "premium_affordability"
    assert infer_dashboard_type("compare these two", None) == "strategy_comparison"


def test_merge_layers_prefers_analysis_numbers():
    from_analyses = {"recommended_life_cover": 600_000, "existing_life_cover": 400_000}
    memory_then_factfind = {
        "financial": {"annual_gross_income": 120_000},
        "personal": {"age": 40},
        "insurance": {},
        "health": {},
        "goals": {},
    }
    m = merge_layers(from_analyses=from_analyses, memory_then_factfind=memory_then_factfind)
    assert m["recommended_life_cover"] == 600_000
    assert m["annual_gross_income"] == 120_000


def test_normalize_projection_horizon_defaults_and_snap():
    assert normalize_projection_horizon(None) == 15
    assert normalize_projection_horizon(12) == 10
    assert normalize_projection_horizon(18) == 20
    assert normalize_projection_horizon(25) == 25


def test_build_yearly_insurance_projection_row_shape():
    out = build_yearly_insurance_projection(
        horizon_years=10,
        required_cover_year0=500_000,
        existing_cover=200_000,
        recommended_cover=450_000,
        mortgage_balance=100_000,
        debt_payoff_years=10,
        dependent_support_decay_years=10,
        income_support_years=10,
        dependants_count=2,
        annual_income=120_000,
        premium_annual_existing=2000,
        premium_annual_recommended=2800,
        premium_tolerance_ratio=0.08,
    )
    series = out["yearlySeries"]
    assert len(series) == 11
    row0 = series[0]
    for k in (
        "requiredCover",
        "existingCover",
        "recommendedCover",
        "shortfallExisting",
        "shortfallRecommended",
        "adequacyRatioExisting",
        "adequacyRatioRecommended",
        "dependentSupportNeed",
        "incomeSupportNeed",
    ):
        assert k in row0
    assert row0["year"] == 0
    assert row0["outstandingDebt"] is not None


def test_compute_projection_insurance_needs_bundle():
    resolved = {
        "recommended_life_cover": 500_000,
        "existing_life_cover": 300_000,
        "recommended_annual_premium": 3000,
        "existing_annual_premium": 2500,
        "annual_gross_income": 150_000,
    }
    b = compute_projection_bundle("insurance_needs", resolved)
    assert b["summaryCards"]
    assert b["charts"]
    pd = b["projection_data"]
    assert len(pd.get("yearlySeries") or []) == 16
    assert pd.get("yearlyProjection", {}).get("horizonYears") == 15


def test_detect_insurance_types_life_tpd():
    norm = {"cover": {"life": 1.0, "tpd": 2.0}}
    assert detect_insurance_types_present(norm, {}) == ["life", "tpd"]


def test_detect_insurance_types_from_resolved_only():
    assert detect_insurance_types_present(None, {"recommended_tpd_cover": 100}) == ["tpd"]


def test_build_yearly_tpd_projection_rows():
    out = build_yearly_tpd_projection(
        horizon_years=5,
        lump_sum_need_year0=400_000,
        existing_tpd_cover=200_000,
        recommended_tpd_cover=380_000,
        annual_income=100_000,
        income_support_years=5,
        premium_annual_existing=2000,
        premium_annual_recommended=2800,
        premium_tolerance_ratio=0.08,
    )
    assert len(out["yearlySeries"]) == 6
    assert "lumpSumNeed" in out["yearlySeries"][0]
    assert "incomeReplacementNeed" in out["yearlySeries"][0]


def test_compute_projection_tpd_bundle():
    resolved = {
        "recommended_tpd_cover": 400_000,
        "existing_tpd_cover": 200_000,
        "recommended_annual_premium": 3000,
        "existing_annual_premium": 2500,
        "annual_gross_income": 150_000,
    }
    b = compute_projection_bundle("insurance_needs", resolved, insurance_kind="tpd")
    assert b["projection_data"]["insuranceKind"] == "tpd"
    line_titles = [c.get("title") or "" for c in b["charts"] if c.get("type") == "line"]
    assert any("TPD" in t for t in line_titles)
