"""
insurance_tool_input_requirements.py — Single source of truth for insurance tool inputs.

Derived from reading each tool implementation under app/tools/implementations/:
  - *_validate() → fields that populate `errors` (blocking before meaningful run)
  - warnings / missingInfoQuestions → advisory gaps (tool may still run)
  - Trauma: `_build_missing_info_questions` → `blocking_questions` (no hard _validate)

Use ORCHESTRATOR_CRITICAL_FIELDS with build-tool-input to pause the AI-bar orchestrator
until canonical facts (or memory hints / user overrides) supply the mapped values.

Human-readable tables: docs/04-tools/insurance-tool-input-requirements.md
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Orchestrator pre-run gate (used by POST .../build-tool-input)
#
# Each entry:
#   path      — dotted path on the *nested tool_input* dict after build_tool_input_from_memory
#   canonical — factfind section.field used for overrides + memory merge (see memory_merge_service)
#   label     — UI prompt
#   input_type — "number" | "text" | "boolean"
# ---------------------------------------------------------------------------

ORCHESTRATOR_CRITICAL_FIELDS: dict[str, list[dict[str, Any]]] = {
    # life_insurance_in_super.py _validate: blocking errors only member.age/DOB (income is Q-010 non-blocking)
    "purchase_retain_life_insurance_in_super": [
        {
            "path": "member.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
    ],
    "purchase_retain_life_tpd_policy": [
        {
            "path": "client.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
        {
            "path": "client.annualGrossIncome",
            "canonical": "financial.annual_gross_income",
            "label": "Annual Gross Income ($)",
            "input_type": "number",
        },
    ],
    "purchase_retain_income_protection_policy": [
        {
            "path": "client.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
        {
            "path": "client.annualGrossIncome",
            "canonical": "financial.annual_gross_income",
            "label": "Annual Gross Income ($)",
            "input_type": "number",
        },
    ],
    # ip_in_super.py _validate: errors on member.age + fund.fundType (income is warning-only)
    "purchase_retain_ip_in_super": [
        {
            "path": "member.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
        {
            "path": "fund.fundType",
            "canonical": "financial.fund_type",
            "label": "Super fund type (e.g. choice, mysuper, smsf)",
            "input_type": "text",
        },
    ],
    "tpd_policy_assessment": [
        {
            "path": "client.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
    ],
    # trauma: no _validate errors; blocking_questions require age, income, hasExistingPolicy
    "purchase_retain_trauma_ci_policy": [
        {
            "path": "client.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
        {
            "path": "client.annualGrossIncome",
            "canonical": "financial.annual_gross_income",
            "label": "Annual Gross Income ($)",
            "input_type": "number",
        },
        {
            "path": "existingPolicy.hasExistingPolicy",
            "canonical": "insurance.has_existing_policy",
            "label": "Does the client have an existing trauma/CI policy? (yes/no)",
            "input_type": "boolean",
        },
    ],
    # tpd_in_super.py _validate: blocking errors only member.age
    "purchase_retain_tpd_in_super": [
        {
            "path": "member.age",
            "canonical": "personal.age",
            "label": "Client Age (years)",
            "input_type": "number",
        },
    ],
}


# ---------------------------------------------------------------------------
# Rich spec for documentation + future checks (warnings, optional, schemas)
# ---------------------------------------------------------------------------

INSURANCE_TOOL_SPECS: dict[str, dict[str, Any]] = {
    "purchase_retain_life_insurance_in_super": {
        "title": "Life insurance in super",
        "implementation": "app/tools/implementations/life_insurance_in_super.py",
        "top_level_keys": ["member", "fund", "product", "elections", "employerException", "adviceContext", "health", "evaluationDate"],
        "validate_blocking_paths": ["member.age or member.dateOfBirth"],
        "validate_warning_paths": ["fund.fundType", "product.coverTypesPresent"],
        "validate_non_blocking_questions": [
            "member.annualIncome (needs analysis)",
            "adviceContext.yearsToRetirement (if age unknown)",
            "liquid assets / split strategy (Q-012/013)",
        ],
        "notes": "Engine uses age for PYS under-25 and triggers; income improves needs estimate but is not a validation error.",
    },
    "purchase_retain_life_tpd_policy": {
        "title": "Life & TPD (retail)",
        "implementation": "app/tools/implementations/life_tpd_policy.py",
        "top_level_keys": ["client", "existingPolicy", "newPolicy", "health", "financialPosition", "goals", "evaluationDate"],
        "validate_blocking_paths": ["client.age or client.dateOfBirth", "client.annualGrossIncome"],
        "validate_warning_paths": ["existingPolicy sums if hasExistingPolicy"],
        "validate_non_blocking_questions": ["health block empty → optional health questions"],
        "notes": "Need analysis uses income, debts, dependants; many fields default if omitted.",
    },
    "purchase_retain_income_protection_policy": {
        "title": "Income protection (retail)",
        "implementation": "app/tools/implementations/income_protection_policy.py",
        "top_level_keys": ["client", "existingPolicy", "proposedPolicy", "health", "goals", "financialPosition", "evaluationDate"],
        "validate_blocking_paths": ["client.age (from age or DOB)", "client.annualGrossIncome"],
        "validate_warning_paths": ["occupationClass UNKNOWN", "existing policy benefit/WP if hasExistingPolicy", "health"],
        "validate_non_blocking_questions": [
            "IPQ-006: if not hasExistingPolicy and no proposedPolicy → blocking question in output (errors list still empty)",
        ],
        "notes": "Tool returns is_valid True if only age+income present; intent question appears in missingInfoQuestions.",
    },
    "purchase_retain_ip_in_super": {
        "title": "Income protection in super",
        "implementation": "app/tools/implementations/ip_in_super.py",
        "top_level_keys": ["member", "fund", "existingCover", "elections", "adviceContext", "evaluationDate"],
        "validate_blocking_paths": ["member.age or DOB", "fund.fundType"],
        "validate_warning_paths": ["employmentStatus UNKNOWN (work test)", "annualGrossIncome", "accountBalance"],
        "validate_non_blocking_questions": ["yearsToRetirement", "existing IP monthly benefit if cover exists"],
        "notes": "SIS Reg 6.15 work test uses employment + hours; fund type required for legal structure checks.",
    },
    "purchase_retain_trauma_ci_policy": {
        "title": "Trauma / critical illness",
        "implementation": "app/tools/implementations/trauma_critical_illness_policy.py",
        "top_level_keys": ["client", "existingPolicy", "proposedPolicy", "health", "financialPosition", "goals"],
        "validate_blocking_paths": [],
        "missing_info_blocking": [
            "existingPolicy.hasExistingPolicy must be true/false",
            "client.age",
            "client.annualGrossIncome (>0)",
            "existingPolicy.sumInsured if hasExistingPolicy",
        ],
        "notes": "No ToolValidationError path; execute() always returns payload with missing_info_questions.blocking_questions.",
    },
    "tpd_policy_assessment": {
        "title": "TPD policy assessment",
        "implementation": "app/tools/implementations/tpd_policy_assessment.py",
        "top_level_keys": ["client", "existingPolicy", "proposedPolicy", "health", "financialPosition", "goals", "evaluationDate"],
        "validate_blocking_paths": [],
        "notes": "No _validate(); runs with defaults (e.g. yearsToRetirement inferred). Age strongly affects tax/claims modules.",
    },
    "purchase_retain_tpd_in_super": {
        "title": "TPD in super",
        "implementation": "app/tools/implementations/tpd_in_super.py",
        "top_level_keys": ["member", "fund", "existingCover", "health", "financialPosition", "adviceContext", "evaluationDate"],
        "validate_blocking_paths": ["member.age or DOB"],
        "validate_warning_paths": ["fund.fundType", "member.annualGrossIncome", "accountBalance", "inactivity flags"],
        "notes": "Only age is a hard error; income and balance needed for lump-sum need and PYS checks.",
    },
}


def get_at_path(d: dict, dotpath: str) -> Any:
    """Return nested value for dotted path, or None."""
    cur: Any = d
    for key in dotpath.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _is_blank_fund_type(val: Any) -> bool:
    return val is None or (isinstance(val, str) and val.strip() == "")


def _critical_field_missing(tool_name: str, tool_input: dict[str, Any], crit: dict[str, Any]) -> bool:
    """True if this orchestrator gate field is still absent / invalid on tool_input."""
    path = crit["path"]

    if path == "member.age":
        m = tool_input.get("member") or {}
        return m.get("age") is None and not m.get("dateOfBirth")

    if path == "client.age":
        c = tool_input.get("client") or {}
        return c.get("age") is None and not c.get("dateOfBirth")

    if path == "fund.fundType":
        f = tool_input.get("fund") or {}
        return _is_blank_fund_type(f.get("fundType"))

    if path == "client.annualGrossIncome":
        c = tool_input.get("client") or {}
        v = c.get("annualGrossIncome")
        if v is None:
            return True
        if tool_name == "purchase_retain_trauma_ci_policy":
            try:
                return float(v) <= 0
            except (TypeError, ValueError):
                return True
        return False

    if path == "member.annualGrossIncome":
        m = tool_input.get("member") or {}
        return m.get("annualGrossIncome") is None

    if path == "member.annualIncome":
        m = tool_input.get("member") or {}
        return m.get("annualIncome") is None

    if path == "existingPolicy.hasExistingPolicy":
        ep = tool_input.get("existingPolicy") or {}
        return ep.get("hasExistingPolicy") is None

    val = get_at_path(tool_input, path)
    return val is None


def compute_missing_critical_fields(
    tool_name: str,
    tool_input: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Subset of ORCHESTRATOR_CRITICAL_FIELDS still missing on the built tool_input.

    Used by POST /client-context/.../build-tool-input (orchestrator pause / overrides flow).
    """
    critical = ORCHESTRATOR_CRITICAL_FIELDS.get(tool_name, [])
    return [crit for crit in critical if _critical_field_missing(tool_name, tool_input, crit)]


def list_orchestrator_missing(
    tool_name: str,
    tool_input: dict[str, Any],
) -> list[dict[str, Any]]:
    """Alias for compute_missing_critical_fields (readable name for tests/callers)."""
    return compute_missing_critical_fields(tool_name, tool_input)


def all_insurance_tool_names() -> list[str]:
    return sorted(ORCHESTRATOR_CRITICAL_FIELDS.keys())
