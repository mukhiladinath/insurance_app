"""
agent.py — Pydantic schemas for agent-layer outputs.

These are internal models used between nodes and services.
They are not exposed directly in API responses (see chat.py for those).
"""

from typing import Any
from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    intent: str
    selected_tool: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    reasoning: str | None = None
    extracted_tool_input: dict[str, Any] | None = None


class AgentRunResult(BaseModel):
    intent: str
    selected_tool: str | None = None
    tool_result: dict[str, Any] | None = None
    tool_warnings: list[str] = Field(default_factory=list)
    tool_error: str | None = None
    final_response: str
    metadata: dict[str, Any] = Field(default_factory=dict)
