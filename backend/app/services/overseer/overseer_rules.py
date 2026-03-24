"""
overseer_rules.py — Deterministic pre-checks for the Overseer Agent.

These rules run BEFORE any LLM call.  They are cheap, fast, and reliable.
A rule that fires short-circuits the LLM evaluation entirely.

Rule priority order:
  1. tool_error → retry_tool  (validation errors → retry_extraction instead)
  2. tool_result is None or empty dict → proceed_with_caution
  3. Critical input fields missing for this tool → ask_user
  4. Expected output keys absent from tool_result → proceed_with_caution
  5. No rule fires → return None  (caller should invoke LLM evaluation)
"""

from __future__ import annotations

from app.services.overseer.overseer_models import (
    MissingField,
    OverseerVerdict,
    OverseerRequest,
)

# ---------------------------------------------------------------------------
# Tool-specific critical INPUT fields
#
# Format: tool_name → list of (dotted_input_path, description, question)
#
# Only fields that, if missing, would make the tool output meaningless.
# ---------------------------------------------------------------------------

_CRITICAL_INPUT_FIELDS: dict[str, list[tuple[str, str, str]]] = {
    "purchase_retain_life_insurance_in_super": [
        (
            "member.age",
            "Member age is required for PYS under-25 switch-off and mortality calculations.",
            "What is the member's age?",
        ),
        (
            "member.annualIncome",
            "Annual income drives the insurance needs estimate.",
            "What is the member's annual income?",
        ),
    ],
    "purchase_retain_life_tpd_policy": [
        (
            "client.age",
            "Client age is required for life/TPD premium and needs calculations.",
            "What is the client's age?",
        ),
        (
            "client.annualGrossIncome",
            "Annual income is required for income-replacement needs calculation.",
            "What is the client's annual income?",
        ),
    ],
    "purchase_retain_income_protection_policy": [
        (
            "client.age",
            "Client age is required for IP premium calculations.",
            "What is the client's age?",
        ),
        (
            "client.annualGrossIncome",
            "Annual income is the primary input for income protection cover sizing.",
            "What is the client's annual income?",
        ),
    ],
    "purchase_retain_ip_in_super": [
        (
            "member.age",
            "Member age is required for PYS switch-off and IP premium calculations.",
            "What is the member's age?",
        ),
        (
            "member.annualGrossIncome",
            "Annual income drives the IP replacement ratio calculation.",
            "What is the member's annual income?",
        ),
    ],
    "purchase_retain_trauma_ci_policy": [
        (
            "client.age",
            "Client age drives trauma/CI premium calculations.",
            "What is the client's age?",
        ),
    ],
    "tpd_policy_assessment": [
        (
            "client.age",
            "Client age is required for TPD premium and claims-approval projections.",
            "What is the client's age?",
        ),
    ],
    "purchase_retain_tpd_in_super": [
        (
            "member.age",
            "Member age is required for PYS switch-off and TPD needs assessment.",
            "What is the member's age?",
        ),
    ],
}

# ---------------------------------------------------------------------------
# Tool-specific expected OUTPUT keys
#
# If any of these top-level keys are absent from tool_result the output is
# considered incomplete → proceed_with_caution.
# ---------------------------------------------------------------------------

_EXPECTED_OUTPUT_KEYS: dict[str, list[str]] = {
    "purchase_retain_life_insurance_in_super": ["recommendation"],
    "purchase_retain_life_tpd_policy":         ["recommendation"],
    "purchase_retain_income_protection_policy": ["recommendation"],
    "purchase_retain_ip_in_super":             ["recommendation"],
    "purchase_retain_trauma_ci_policy":        ["recommendation"],
    "tpd_policy_assessment":                   ["recommendation"],
    "purchase_retain_tpd_in_super":            ["recommendation"],
}

# Strings in tool_error that indicate a validation problem (input was bad)
_VALIDATION_ERROR_MARKERS: tuple[str, ...] = (
    "validation error",
    "validationerror",
    "required field",
    "missing field",
    "invalid input",
    "input validation",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_nested(d: dict, dotted_path: str):
    """
    Navigate a dotted path in a nested dict.
    Returns the value if found, None otherwise.
    E.g. _get_nested(d, "member.annualIncome") → d["member"]["annualIncome"]
    """
    parts = dotted_path.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _is_validation_error(error: str) -> bool:
    lower = error.lower()
    return any(marker in lower for marker in _VALIDATION_ERROR_MARKERS)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_deterministic_rules(req: OverseerRequest) -> OverseerVerdict | None:
    """
    Apply deterministic pre-checks.

    Returns an OverseerVerdict if a rule fires, None if no rule matches
    (caller should proceed to LLM evaluation).
    """

    # ------------------------------------------------------------------
    # Rule 1 — Tool error present
    # ------------------------------------------------------------------
    if req.tool_error:
        if _is_validation_error(req.tool_error):
            return OverseerVerdict(
                status="retry_extraction",
                reason=f"Tool input validation error: {req.tool_error}",
                overseer_source="deterministic",
            )
        return OverseerVerdict(
            status="retry_tool",
            reason=f"Tool execution error: {req.tool_error}",
            overseer_source="deterministic",
        )

    # ------------------------------------------------------------------
    # Rule 2 — Null or empty tool result
    # ------------------------------------------------------------------
    if not req.tool_result:
        return OverseerVerdict(
            status="proceed_with_caution",
            reason="Tool returned no output; response will be based on general knowledge.",
            caution_notes=["Tool did not produce a structured result for this query."],
            overseer_source="deterministic",
        )

    # ------------------------------------------------------------------
    # Rule 3 — Critical input fields missing
    # ------------------------------------------------------------------
    tool_input = req.extracted_tool_input or {}
    required = _CRITICAL_INPUT_FIELDS.get(req.tool_name, [])
    missing: list[MissingField] = []

    for path, description, question in required:
        value = _get_nested(tool_input, path)
        if value is None:
            missing.append(MissingField(field=path, description=description, question=question))

    if missing:
        # Build a combined clarifying question from the first missing field
        primary = missing[0]
        return OverseerVerdict(
            status="ask_user",
            reason=f"Critical input field(s) missing: {', '.join(m.field for m in missing)}",
            missing_fields=missing,
            suggested_question=primary.question,
            overseer_source="deterministic",
        )

    # ------------------------------------------------------------------
    # Rule 4 — Expected output keys absent
    # ------------------------------------------------------------------
    expected_keys = _EXPECTED_OUTPUT_KEYS.get(req.tool_name, [])
    absent = [k for k in expected_keys if k not in req.tool_result]

    if absent:
        return OverseerVerdict(
            status="proceed_with_caution",
            reason=f"Tool output missing expected keys: {', '.join(absent)}",
            caution_notes=[f"Incomplete tool output — missing: {', '.join(absent)}"],
            overseer_source="deterministic",
        )

    # No rule fired
    return None
