"""
overseer_models.py — Typed Pydantic contracts for the Overseer Agent.

OverseerRequest  : inputs passed to run_overseer()
OverseerVerdict  : structured output returned by run_overseer()
MissingField     : one missing / inadequate field with a suggested question
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Status codes
# ---------------------------------------------------------------------------

OverseerStatus = Literal[
    "proceed",              # output is good; compose normally
    "proceed_with_caution", # output has gaps / caveats; compose with warnings
    "ask_user",             # critical data missing; ask user before composing
    "retry_extraction",     # tool input was bad; re-run classify_intent
    "retry_tool",           # transient tool error; re-run execute_tool
    "reset_context",        # fundamental topic shift or confusion; reset
]


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class OverseerRequest(BaseModel):
    """All context the overseer needs to evaluate a tool execution turn."""

    tool_name: str
    tool_result: dict | None = None
    tool_error: str | None = None
    extracted_tool_input: dict | None = None
    intent: str
    user_message: str
    recent_messages: list[dict] = Field(default_factory=list)
    retry_count: int = 0  # number of overseer-directed retries already consumed


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------

class MissingField(BaseModel):
    """A field that was absent or invalid, with a suggested clarifying question."""

    field: str           # dotted path e.g. "member.annualIncome"
    description: str     # human-readable explanation of why it's needed
    question: str        # suggested question to surface to the user


# ---------------------------------------------------------------------------
# Verdict model
# ---------------------------------------------------------------------------

class OverseerVerdict(BaseModel):
    """Typed output from run_overseer()."""

    status: OverseerStatus
    reason: str                          # short explanation for logs / compose
    missing_fields: list[MissingField] = Field(default_factory=list)
    caution_notes: list[str] = Field(default_factory=list)
    suggested_question: str | None = None  # populated when status == "ask_user"
    overseer_source: Literal["deterministic", "llm", "fallback"] = "deterministic"
