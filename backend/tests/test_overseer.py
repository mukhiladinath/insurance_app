"""
test_overseer.py — Unit and scenario tests for the Overseer Agent.

Tests cover:
  Deterministic rules:
    1.  tool_error (non-validation) → retry_tool
    2.  tool_error (validation)     → retry_extraction
    3.  empty tool_result           → proceed_with_caution
    4.  None tool_result            → proceed_with_caution
    5.  critical input missing      → ask_user  (member.age absent)
    6.  critical input missing      → ask_user  (member.annualIncome absent)
    7.  expected output key missing → proceed_with_caution
    8.  all fields present          → None (no rule fires, LLM path)

  Service-level:
    9.  LLM failure falls back to proceed_with_caution
    10. LLM returns valid JSON proceed → verdict accepted
    11. LLM returns invalid status   → fallback proceed_with_caution
    12. LLM returns invalid JSON     → fallback proceed_with_caution

  Retry enforcement (node level):
    13. retry_tool with retry_count=0 → status remains retry_tool, count incremented
    14. retry_tool with retry_count=1 → downgraded to proceed_with_caution
    15. retry_extraction with retry_count=1 → downgraded to proceed_with_caution

  Scenario tests:
    16. Good tool result, all fields present → proceed (or proceed_with_caution)
    17. Validation error string             → retry_extraction
    18. IP tool, income missing             → ask_user
    19. Trauma tool, age missing            → ask_user
    20. Tool result has no 'recommendation' → proceed_with_caution

  Models:
    21. OverseerRequest validates correctly
    22. OverseerVerdict model defaults
    23. MissingField model

  Logging helper:
    24. log_verdict does not raise

  Prompt builder:
    25. build_overseer_user_prompt includes tool name and user message
"""

import asyncio
import json
import sys
import os

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# We patch get_chat_model_fresh before importing overseer_service so the
# module-level import doesn't fail in environments without Azure credentials.
# ---------------------------------------------------------------------------
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# Helpers
# ============================================================

def _make_request(**kwargs):
    from app.services.overseer.overseer_models import OverseerRequest
    defaults = dict(
        tool_name="purchase_retain_life_insurance_in_super",
        tool_result={"recommendation": {"type": "INSIDE_SUPER"}, "switch_off_triggers": []},
        tool_error=None,
        extracted_tool_input={
            "member": {"age": 35, "annualIncome": 90000},
        },
        intent="purchase_retain_life_insurance_in_super",
        user_message="What should John do about his life insurance in super?",
        recent_messages=[],
        retry_count=0,
    )
    defaults.update(kwargs)
    return OverseerRequest(**defaults)


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ============================================================
# 1. tool_error (non-validation) → retry_tool
# ============================================================
def test_tool_error_non_validation_gives_retry_tool():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(tool_error="Unexpected tool error: connection timeout", tool_result=None)
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "retry_tool"
    assert verdict.overseer_source == "deterministic"
    print("PASS test_tool_error_non_validation_gives_retry_tool")


# ============================================================
# 2. tool_error (validation) → retry_extraction
# ============================================================
def test_tool_error_validation_gives_retry_extraction():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(tool_error="Tool input validation error: missing field 'age'", tool_result=None)
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "retry_extraction"
    print("PASS test_tool_error_validation_gives_retry_extraction")


# ============================================================
# 3. empty tool_result dict → proceed_with_caution
# ============================================================
def test_empty_tool_result_gives_proceed_with_caution():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(tool_result={})
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "proceed_with_caution"
    print("PASS test_empty_tool_result_gives_proceed_with_caution")


# ============================================================
# 4. None tool_result → proceed_with_caution
# ============================================================
def test_none_tool_result_gives_proceed_with_caution():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(tool_result=None, tool_error=None)
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "proceed_with_caution"
    print("PASS test_none_tool_result_gives_proceed_with_caution")


# ============================================================
# 5. member.age missing → ask_user
# ============================================================
def test_missing_age_gives_ask_user():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        extracted_tool_input={"member": {"annualIncome": 90000}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "ask_user"
    assert any(m.field == "member.age" for m in verdict.missing_fields)
    assert verdict.suggested_question is not None
    print("PASS test_missing_age_gives_ask_user")


# ============================================================
# 6. member.annualIncome missing → ask_user
# ============================================================
def test_missing_income_gives_ask_user():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        extracted_tool_input={"member": {"age": 40}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "ask_user"
    assert any(m.field == "member.annualIncome" for m in verdict.missing_fields)
    print("PASS test_missing_income_gives_ask_user")


# ============================================================
# 7. expected output key absent → proceed_with_caution
# ============================================================
def test_missing_output_key_gives_proceed_with_caution():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        # Provide valid inputs so we pass rule 3
        extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
        # Tool result missing 'recommendation'
        tool_result={"switch_off_triggers": []},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "proceed_with_caution"
    assert "recommendation" in verdict.reason
    print("PASS test_missing_output_key_gives_proceed_with_caution")


# ============================================================
# 8. all fields present → no deterministic rule fires
# ============================================================
def test_all_fields_present_no_rule_fires():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
        tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is None
    print("PASS test_all_fields_present_no_rule_fires")


# ============================================================
# 9. LLM failure → fallback proceed_with_caution
# ============================================================
def test_llm_failure_falls_back():
    with patch("app.services.overseer.overseer_service.get_chat_model_fresh") as mock_llm_factory:
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(side_effect=RuntimeError("Azure connection refused"))
        mock_llm_factory.return_value = mock_llm

        from app.services.overseer.overseer_service import run_overseer
        req = _make_request(
            extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
            tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
        )
        verdict = run(run_overseer(req))

    assert verdict.status == "proceed_with_caution"
    assert verdict.overseer_source == "fallback"
    print("PASS test_llm_failure_falls_back")


# ============================================================
# 10. LLM returns valid JSON proceed → accepted
# ============================================================
def test_llm_returns_proceed():
    llm_json = json.dumps({
        "status": "proceed",
        "reason": "Tool output is complete and coherent.",
        "caution_notes": [],
        "suggested_question": None,
    })

    with patch("app.services.overseer.overseer_service.get_chat_model_fresh") as mock_llm_factory:
        mock_response = MagicMock()
        mock_response.content = llm_json
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm_factory.return_value = mock_llm

        from app.services.overseer.overseer_service import run_overseer
        req = _make_request(
            extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
            tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
        )
        verdict = run(run_overseer(req))

    assert verdict.status == "proceed"
    assert verdict.overseer_source == "llm"
    print("PASS test_llm_returns_proceed")


# ============================================================
# 11. LLM returns invalid status → fallback
# ============================================================
def test_llm_invalid_status_falls_back():
    llm_json = json.dumps({
        "status": "totally_made_up",
        "reason": "something",
        "caution_notes": [],
    })

    with patch("app.services.overseer.overseer_service.get_chat_model_fresh") as mock_llm_factory:
        mock_response = MagicMock()
        mock_response.content = llm_json
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm_factory.return_value = mock_llm

        from app.services.overseer.overseer_service import run_overseer
        req = _make_request(
            extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
            tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
        )
        verdict = run(run_overseer(req))

    assert verdict.status == "proceed_with_caution"
    assert verdict.overseer_source == "fallback"
    print("PASS test_llm_invalid_status_falls_back")


# ============================================================
# 12. LLM returns invalid JSON → fallback
# ============================================================
def test_llm_invalid_json_falls_back():
    with patch("app.services.overseer.overseer_service.get_chat_model_fresh") as mock_llm_factory:
        mock_response = MagicMock()
        mock_response.content = "This is not JSON at all."
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_llm_factory.return_value = mock_llm

        from app.services.overseer.overseer_service import run_overseer
        req = _make_request(
            extracted_tool_input={"member": {"age": 35, "annualIncome": 90000}},
            tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
        )
        verdict = run(run_overseer(req))

    assert verdict.status == "proceed_with_caution"
    assert verdict.overseer_source == "fallback"
    print("PASS test_llm_invalid_json_falls_back")


# ============================================================
# 13. retry_tool with retry_count=0 → status unchanged, count +1
# ============================================================
def test_retry_tool_first_attempt_preserved():
    """Node-level retry cap: first retry is allowed."""
    import asyncio
    from app.agents.nodes.overseer_quality_gate import overseer_quality_gate

    state = {
        "selected_tool": "purchase_retain_life_insurance_in_super",
        "tool_result": None,
        "tool_error": "Unexpected tool error: timeout",
        "extracted_tool_input": {"member": {"age": 35}},
        "intent": "purchase_retain_life_insurance_in_super",
        "user_message": "Analyse John's insurance.",
        "recent_messages": [],
        "overseer_retry_count": 0,
    }
    result = asyncio.get_event_loop().run_until_complete(overseer_quality_gate(state))

    assert result["overseer_status"] == "retry_tool"
    assert result["overseer_retry_count"] == 1
    print("PASS test_retry_tool_first_attempt_preserved")


# ============================================================
# 14. retry_tool with retry_count=1 → downgraded
# ============================================================
def test_retry_tool_second_attempt_downgraded():
    import asyncio
    from app.agents.nodes.overseer_quality_gate import overseer_quality_gate

    state = {
        "selected_tool": "purchase_retain_life_insurance_in_super",
        "tool_result": None,
        "tool_error": "Unexpected tool error: timeout",
        "extracted_tool_input": {"member": {"age": 35}},
        "intent": "purchase_retain_life_insurance_in_super",
        "user_message": "Analyse John's insurance.",
        "recent_messages": [],
        "overseer_retry_count": 1,  # already retried once
    }
    result = asyncio.get_event_loop().run_until_complete(overseer_quality_gate(state))

    assert result["overseer_status"] == "proceed_with_caution", (
        f"Expected proceed_with_caution, got {result['overseer_status']}"
    )
    print("PASS test_retry_tool_second_attempt_downgraded")


# ============================================================
# 15. retry_extraction with retry_count=1 → downgraded
# ============================================================
def test_retry_extraction_second_attempt_downgraded():
    import asyncio
    from app.agents.nodes.overseer_quality_gate import overseer_quality_gate

    state = {
        "selected_tool": "purchase_retain_life_insurance_in_super",
        "tool_result": None,
        "tool_error": "Tool input validation error: missing field 'age'",
        "extracted_tool_input": {},
        "intent": "purchase_retain_life_insurance_in_super",
        "user_message": "Analyse John's insurance.",
        "recent_messages": [],
        "overseer_retry_count": 1,
    }
    result = asyncio.get_event_loop().run_until_complete(overseer_quality_gate(state))

    assert result["overseer_status"] == "proceed_with_caution"
    print("PASS test_retry_extraction_second_attempt_downgraded")


# ============================================================
# 16. Good tool result, valid inputs → LLM path (mocked proceed)
# ============================================================
def test_scenario_good_result_proceeds():
    llm_json = json.dumps({
        "status": "proceed",
        "reason": "Analysis complete.",
        "caution_notes": [],
        "suggested_question": None,
    })
    with patch("app.services.overseer.overseer_service.get_chat_model_fresh") as mock_factory:
        mock_response = MagicMock()
        mock_response.content = llm_json
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=mock_response)
        mock_factory.return_value = mock_llm

        from app.services.overseer.overseer_service import run_overseer
        req = _make_request(
            extracted_tool_input={"member": {"age": 45, "annualIncome": 120000}},
            tool_result={
                "recommendation": {"type": "INSIDE_SUPER", "summary": "Keep inside super."},
                "switch_off_triggers": [],
            },
        )
        verdict = run(run_overseer(req))

    assert verdict.status in ("proceed", "proceed_with_caution")
    print("PASS test_scenario_good_result_proceeds")


# ============================================================
# 17. Validation error string → retry_extraction (deterministic)
# ============================================================
def test_scenario_validation_error_string():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        tool_error="Tool input validation error: annualIncome is required",
        tool_result=None,
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "retry_extraction"
    print("PASS test_scenario_validation_error_string")


# ============================================================
# 18. IP tool, income missing → ask_user
# ============================================================
def test_scenario_ip_tool_income_missing():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        tool_name="purchase_retain_income_protection_policy",
        intent="purchase_retain_income_protection_policy",
        extracted_tool_input={"client": {"age": 38}},
        tool_result={"recommendation": {"type": "PURCHASE"}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "ask_user"
    assert any("annualGrossIncome" in m.field for m in verdict.missing_fields)
    print("PASS test_scenario_ip_tool_income_missing")


# ============================================================
# 19. Trauma tool, age missing → ask_user
# ============================================================
def test_scenario_trauma_age_missing():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        tool_name="purchase_retain_trauma_ci_policy",
        intent="purchase_retain_trauma_ci_policy",
        extracted_tool_input={"client": {"annualGrossIncome": 80000}},
        tool_result={"recommendation": {"type": "PURCHASE"}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "ask_user"
    assert any("age" in m.field for m in verdict.missing_fields)
    print("PASS test_scenario_trauma_age_missing")


# ============================================================
# 20. Tool result has no 'recommendation' key → proceed_with_caution
# ============================================================
def test_scenario_missing_recommendation_key():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        extracted_tool_input={"member": {"age": 40, "annualIncome": 100000}},
        tool_result={"switch_off_triggers": [], "legal_status": "ALLOWED_AND_ACTIVE"},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is not None
    assert verdict.status == "proceed_with_caution"
    print("PASS test_scenario_missing_recommendation_key")


# ============================================================
# 21. IP-in-super with annualGrossIncome present -> no ask_user
# ============================================================
def test_scenario_ip_in_super_with_annual_gross_income_present():
    from app.services.overseer.overseer_rules import run_deterministic_rules
    req = _make_request(
        tool_name="purchase_retain_ip_in_super",
        intent="purchase_retain_ip_in_super",
        extracted_tool_input={"member": {"age": 40, "annualGrossIncome": 100000}},
        tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
    )
    verdict = run_deterministic_rules(req)
    assert verdict is None
    print("PASS test_scenario_ip_in_super_with_annual_gross_income_present")


# ============================================================
# 22. OverseerRequest validates correctly
# ============================================================
def test_overseer_request_model():
    from app.services.overseer.overseer_models import OverseerRequest
    req = OverseerRequest(
        tool_name="purchase_retain_life_insurance_in_super",
        user_message="Hello",
        intent="purchase_retain_life_insurance_in_super",
    )
    assert req.tool_result is None
    assert req.retry_count == 0
    assert req.recent_messages == []
    print("PASS test_overseer_request_model")


# ============================================================
# 23. OverseerVerdict defaults
# ============================================================
def test_overseer_verdict_defaults():
    from app.services.overseer.overseer_models import OverseerVerdict
    v = OverseerVerdict(status="proceed", reason="ok")
    assert v.missing_fields == []
    assert v.caution_notes == []
    assert v.suggested_question is None
    assert v.overseer_source == "deterministic"
    print("PASS test_overseer_verdict_defaults")


# ============================================================
# 24. MissingField model
# ============================================================
def test_missing_field_model():
    from app.services.overseer.overseer_models import MissingField
    m = MissingField(
        field="member.age",
        description="Age is required.",
        question="What is the member's age?",
    )
    assert m.field == "member.age"
    print("PASS test_missing_field_model")


# ============================================================
# 25. log_verdict does not raise
# ============================================================
def test_log_verdict_does_not_raise():
    from app.services.overseer.overseer_models import OverseerVerdict
    from app.services.overseer.overseer_logging import log_verdict
    v = OverseerVerdict(status="proceed", reason="all good")
    log_verdict(
        tool_name="purchase_retain_life_insurance_in_super",
        intent="purchase_retain_life_insurance_in_super",
        verdict=v,
        retry_count=0,
        latency_ms=12.5,
    )
    print("PASS test_log_verdict_does_not_raise")


# ============================================================
# 26. build_overseer_user_prompt includes key fields
# ============================================================
def test_build_overseer_user_prompt_content():
    from app.services.overseer.overseer_prompt import build_overseer_user_prompt
    result = build_overseer_user_prompt(
        tool_name="purchase_retain_life_insurance_in_super",
        tool_result={"recommendation": {"type": "INSIDE_SUPER"}},
        extracted_tool_input={"member": {"age": 35}},
        intent="purchase_retain_life_insurance_in_super",
        user_message="What should John do?",
    )
    assert "purchase_retain_life_insurance_in_super" in result
    assert "What should John do?" in result
    assert "INSIDE_SUPER" in result
    print("PASS test_build_overseer_user_prompt_content")


# ============================================================
# Runner
# ============================================================

if __name__ == "__main__":
    tests = [
        test_tool_error_non_validation_gives_retry_tool,
        test_tool_error_validation_gives_retry_extraction,
        test_empty_tool_result_gives_proceed_with_caution,
        test_none_tool_result_gives_proceed_with_caution,
        test_missing_age_gives_ask_user,
        test_missing_income_gives_ask_user,
        test_missing_output_key_gives_proceed_with_caution,
        test_all_fields_present_no_rule_fires,
        test_llm_failure_falls_back,
        test_llm_returns_proceed,
        test_llm_invalid_status_falls_back,
        test_llm_invalid_json_falls_back,
        test_retry_tool_first_attempt_preserved,
        test_retry_tool_second_attempt_downgraded,
        test_retry_extraction_second_attempt_downgraded,
        test_scenario_good_result_proceeds,
        test_scenario_validation_error_string,
        test_scenario_ip_tool_income_missing,
        test_scenario_trauma_age_missing,
        test_scenario_missing_recommendation_key,
        test_scenario_ip_in_super_with_annual_gross_income_present,
        test_overseer_request_model,
        test_overseer_verdict_defaults,
        test_missing_field_model,
        test_log_verdict_does_not_raise,
        test_build_overseer_user_prompt_content,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            failed += 1
            errors.append(f"FAIL {test_fn.__name__}: {exc}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed out of {len(tests)} tests")
    if errors:
        for e in errors:
            print(e)
    else:
        print("All tests passed.")
    print('='*60)

    sys.exit(0 if failed == 0 else 1)
