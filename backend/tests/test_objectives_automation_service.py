"""objectives_automation_service — heuristic fallback and LLM wiring."""

import pytest

from app.services.objectives_automation_service import (
    infer_tool_ids_from_objectives_heuristic,
)


def test_heuristic_empty_returns_empty():
    assert infer_tool_ids_from_objectives_heuristic("") == []
    assert infer_tool_ids_from_objectives_heuristic("   ") == []


def test_heuristic_income_protection():
    ids = infer_tool_ids_from_objectives_heuristic(
        "Client wants income protection for salary continuance."
    )
    assert "purchase_retain_income_protection_policy" in ids


def test_heuristic_life_in_super_and_generic_life():
    ids = infer_tool_ids_from_objectives_heuristic("Review life insurance in super and fund fees.")
    assert "purchase_retain_life_insurance_in_super" in ids
    assert "purchase_retain_life_tpd_policy" in ids


def test_heuristic_multiple_tools():
    ids = infer_tool_ids_from_objectives_heuristic("Assess TPD cover and trauma / critical illness needs.")
    assert "tpd_policy_assessment" in ids
    assert "purchase_retain_trauma_ci_policy" in ids


def test_heuristic_stable_order():
    from app.services.objectives_automation_service import _INSURANCE_TOOL_ORDER

    ids = infer_tool_ids_from_objectives_heuristic(
        "TPD, IP, trauma, life cover, super life, ip in super, tpd in super"
    )
    expected_order = [t for t in _INSURANCE_TOOL_ORDER if t in set(ids)]
    assert ids == expected_order


@pytest.mark.asyncio
async def test_infer_uses_llm_when_returns_tools(monkeypatch):
    async def fake_llm(narrative: str, purpose="objectives"):
        return ["purchase_retain_trauma_ci_policy"]

    monkeypatch.setattr(
        "app.services.objectives_automation_service.llm_select_insurance_engine_tools",
        fake_llm,
    )
    from app.services.objectives_automation_service import infer_tool_ids_from_objectives

    out = await infer_tool_ids_from_objectives("any text")
    assert out == ["purchase_retain_trauma_ci_policy"]


@pytest.mark.asyncio
async def test_infer_falls_back_when_llm_empty(monkeypatch):
    async def fake_llm(narrative: str, purpose="objectives"):
        return []

    monkeypatch.setattr(
        "app.services.objectives_automation_service.llm_select_insurance_engine_tools",
        fake_llm,
    )
    from app.services.objectives_automation_service import infer_tool_ids_from_objectives

    out = await infer_tool_ids_from_objectives("Client wants income protection.")
    assert "purchase_retain_income_protection_policy" in out


@pytest.mark.asyncio
async def test_try_generate_insurance_dashboard_after_automation(monkeypatch):
    called: dict[str, str | None] = {}

    async def fake_generate(db, **kwargs):
        called["analysis_output_id"] = kwargs.get("analysis_output_id")
        return {"status": "complete", "dashboard": {"id": "dash_auto_1"}}

    monkeypatch.setattr(
        "app.services.insurance_dashboard.service.generate_insurance_dashboard",
        fake_generate,
    )
    from app.services.objectives_automation_service import (
        _try_generate_insurance_dashboard_after_automation,
    )

    class _DummyDb:
        pass

    out = await _try_generate_insurance_dashboard_after_automation(_DummyDb(), "client_x", "output_y")
    assert out["insurance_dashboard_created"] is True
    assert out["insurance_dashboard_id"] == "dash_auto_1"
    assert called["analysis_output_id"] == "output_y"


@pytest.mark.asyncio
async def test_try_generate_insurance_dashboard_no_id(monkeypatch):
    from app.services.objectives_automation_service import (
        _try_generate_insurance_dashboard_after_automation,
    )

    out = await _try_generate_insurance_dashboard_after_automation(None, "c", None)
    assert out["insurance_dashboard_created"] is False
    assert out["insurance_dashboard_id"] is None
