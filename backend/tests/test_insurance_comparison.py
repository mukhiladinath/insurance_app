"""Tests for insurance comparison normalizers and engine."""

from __future__ import annotations

from app.insurance_comparison.engine import compare_normalized, determine_comparison_mode
from app.insurance_comparison.registry import (
    has_normalizer,
    normalize_tool_output,
    unwrap_tool_execution_envelope,
)
from app.insurance_comparison.scoring import compare_weighted_scores


def test_has_normalizer_for_all_registry_tools():
    names = [
        "purchase_retain_life_insurance_in_super",
        "purchase_retain_life_tpd_policy",
        "purchase_retain_income_protection_policy",
        "purchase_retain_ip_in_super",
        "purchase_retain_tpd_in_super",
        "purchase_retain_trauma_ci_policy",
        "tpd_policy_assessment",
    ]
    for n in names:
        assert has_normalizer(n)


def test_normalize_life_in_super_from_tool_api_envelope():
    """Orchestrator persists full ToolExecutionResult from POST /api/tools/.../run."""
    inner = {
        "legal_status": "ALLOWED_AND_ACTIVE",
        "placement_assessment": {
            "recommendation": "INSIDE_SUPER",
            "reasoning": ["inside super ok"],
            "risks": [],
        },
        "coverage_needs_analysis": {
            "needs_analysis_available": True,
            "total_need_low": 400_000,
            "total_need_high": 600_000,
            "recommendation_summary": "summary",
        },
        "retirement_drag_estimate": {"annual_premium": 1200},
        "validation": {"warnings": []},
    }
    wrapped = {
        "tool_name": "purchase_retain_life_insurance_in_super",
        "tool_version": "1.0.0",
        "status": "completed",
        "input_payload": {},
        "output_payload": inner,
        "warnings": [],
    }
    out = normalize_tool_output(
        "purchase_retain_life_insurance_in_super",
        wrapped,
        tool_run_id="x:step_1",
        client_id="c1",
        generated_at="2026-01-01T00:00:00Z",
    )
    assert out is not None
    assert out["cover"]["life"] == 500_000.0
    assert out["premiums"]["annual"] == 1200.0


def test_unwrap_envelope_passes_through_bare_tool_output():
    bare = {"placement_assessment": {"recommendation": "INSIDE_SUPER"}, "validation": {"warnings": []}}
    assert unwrap_tool_execution_envelope(bare) is bare


def test_normalize_life_in_super_minimal():
    raw = {
        "legal_status": "ALLOWED_AND_ACTIVE",
        "placement_assessment": {
            "recommendation": "INSIDE_SUPER",
            "reasoning": ["r1"],
            "risks": [],
        },
        "coverage_needs_analysis": {
            "needs_analysis_available": True,
            "total_need_low": 400_000,
            "total_need_high": 600_000,
            "recommendation_summary": "summary",
        },
        "retirement_drag_estimate": {"annual_premium": 1200},
        "validation": {"warnings": []},
    }
    out = normalize_tool_output(
        "purchase_retain_life_insurance_in_super",
        raw,
        tool_run_id="x:step_1",
        client_id="c1",
        generated_at="2026-01-01T00:00:00Z",
    )
    assert out is not None
    assert out["toolName"] == "purchase_retain_life_insurance_in_super"
    assert out["cover"]["life"] == 500_000.0
    assert out["premiums"]["annual"] == 1200.0


def test_compare_engine_two_life_outputs():
    left = normalize_tool_output(
        "purchase_retain_life_insurance_in_super",
        {
            "legal_status": "ALLOWED_AND_ACTIVE",
            "placement_assessment": {"recommendation": "INSIDE_SUPER", "reasoning": [], "risks": []},
            "coverage_needs_analysis": {
                "needs_analysis_available": True,
                "total_need_low": 400_000,
                "total_need_high": 400_000,
            },
            "retirement_drag_estimate": {"annual_premium": 1000},
            "validation": {"warnings": []},
        },
        tool_run_id="a:s1",
        client_id="c",
        generated_at="t",
    )
    right = normalize_tool_output(
        "purchase_retain_life_insurance_in_super",
        {
            "legal_status": "ALLOWED_AND_ACTIVE",
            "placement_assessment": {"recommendation": "OUTSIDE_SUPER", "reasoning": [], "risks": []},
            "coverage_needs_analysis": {
                "needs_analysis_available": True,
                "total_need_low": 500_000,
                "total_need_high": 500_000,
            },
            "retirement_drag_estimate": {"annual_premium": 2000},
            "validation": {"warnings": []},
        },
        tool_run_id="b:s1",
        client_id="c",
        generated_at="t",
    )
    comp = compare_normalized(left, right, left_tool_name="purchase_retain_life_insurance_in_super", right_tool_name="purchase_retain_life_insurance_in_super")
    assert comp["comparisonMode"] in ("direct", "partial")
    prem_rows = [r for r in comp["factsTable"] if r["key"] == "annual_premium"]
    assert prem_rows
    assert prem_rows[0]["betterSide"] == "left"


def test_determine_mode_scenario_different_tools():
    m = determine_comparison_mode("purchase_retain_life_insurance_in_super", "purchase_retain_trauma_ci_policy", 3, 10)
    assert m == "scenario"


def test_weighted_scores_partial():
    left = {"suitability": {"affordabilityScore": 5.0, "adequacyScore": 6.0}}
    right = {"suitability": {"affordabilityScore": 7.0, "adequacyScore": 5.0}}
    b = compare_weighted_scores(left, right)
    assert b["weightedTotals"]["left"] is not None
    assert b["weightedTotals"]["right"] is not None
