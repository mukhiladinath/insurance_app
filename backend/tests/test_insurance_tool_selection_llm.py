"""insurance_tool_selection_llm — ordering and JSON parsing."""

import json

import pytest

from app.services.insurance_tool_selection_llm import (
    REGISTRY_TO_PLANNER_TOOL_ID,
    build_summarizer_tool_results,
    order_registry_tools,
)
from app.services import insurance_tool_selection_llm as itsl


def test_order_registry_tools_stable():
    shuffled = [
        "tpd_policy_assessment",
        "purchase_retain_life_tpd_policy",
        "purchase_retain_trauma_ci_policy",
    ]
    ordered = order_registry_tools(shuffled)
    # Order follows INSURANCE_ENGINE_REGISTRY_IDS: life_tpd, …, tpd_assessment, trauma, …
    assert ordered[0] == "purchase_retain_life_tpd_policy"
    assert ordered[1] == "tpd_policy_assessment"
    assert ordered[2] == "purchase_retain_trauma_ci_policy"


def test_parse_tool_ids_json_filters_unknown_preserves_llm_order():
    raw = '{"tool_ids": ["purchase_retain_trauma_ci_policy", "not_a_real_tool", "tpd_policy_assessment"]}'
    out = itsl._parse_tool_ids_json(raw)
    assert out == ["purchase_retain_trauma_ci_policy", "tpd_policy_assessment"]


def test_registry_maps_all_seven_to_planner():
    assert len(REGISTRY_TO_PLANNER_TOOL_ID) == 7


def test_build_summarizer_tool_results():
    runs = [
        {"tool_id": "a", "label": "A", "payload": {"x": 1}},
        {"tool_id": "b", "label": "B", "payload": {"y": 2}, "error": True},
    ]
    tr = build_summarizer_tool_results(runs)
    assert tr[0]["status"] == "completed"
    assert tr[1]["status"] == "failed"
