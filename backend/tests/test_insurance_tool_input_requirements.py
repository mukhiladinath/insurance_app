"""Tests for insurance_tool_input_requirements orchestrator gate."""

from app.services.insurance_tool_input_requirements import (
    ORCHESTRATOR_CRITICAL_FIELDS,
    compute_missing_critical_fields,
    list_orchestrator_missing,
)


def test_life_in_super_requires_only_age():
    assert "purchase_retain_life_insurance_in_super" in ORCHESTRATOR_CRITICAL_FIELDS
    crit = ORCHESTRATOR_CRITICAL_FIELDS["purchase_retain_life_insurance_in_super"]
    assert len(crit) == 1
    assert crit[0]["path"] == "member.age"

    missing = compute_missing_critical_fields(
        "purchase_retain_life_insurance_in_super",
        {"member": {}},
    )
    assert len(missing) == 1

    ok = compute_missing_critical_fields(
        "purchase_retain_life_insurance_in_super",
        {"member": {"age": 40}},
    )
    assert ok == []


def test_ip_in_super_requires_fund_type():
    missing = compute_missing_critical_fields(
        "purchase_retain_ip_in_super",
        {"member": {"age": 35}, "fund": {}},
    )
    paths = {m["path"] for m in missing}
    assert "fund.fundType" in paths

    ok = compute_missing_critical_fields(
        "purchase_retain_ip_in_super",
        {"member": {"age": 35}, "fund": {"fundType": "choice"}},
    )
    assert ok == []


def test_trauma_requires_income_and_has_existing():
    base = {
        "client": {"age": 40, "annualGrossIncome": 100_000},
        "existingPolicy": {},
    }
    m = compute_missing_critical_fields("purchase_retain_trauma_ci_policy", base)
    assert any(x["path"] == "existingPolicy.hasExistingPolicy" for x in m)

    m2 = list_orchestrator_missing(
        "purchase_retain_trauma_ci_policy",
        {**base, "existingPolicy": {"hasExistingPolicy": True}},
    )
    assert not any(x["path"] == "existingPolicy.hasExistingPolicy" for x in m2)

    m3 = compute_missing_critical_fields(
        "purchase_retain_trauma_ci_policy",
        {"client": {"age": 40}, "existingPolicy": {"hasExistingPolicy": False}},
    )
    assert any(x["path"] == "client.annualGrossIncome" for x in m3)


def test_trauma_income_must_be_positive():
    m = compute_missing_critical_fields(
        "purchase_retain_trauma_ci_policy",
        {
            "client": {"age": 40, "annualGrossIncome": 0},
            "existingPolicy": {"hasExistingPolicy": False},
        },
    )
    assert any(x["path"] == "client.annualGrossIncome" for x in m)
