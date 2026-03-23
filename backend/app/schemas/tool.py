"""
tool.py — Pydantic schemas for tools.

Each tool has a generic execution envelope, and tool-specific input schemas
are defined in the tool implementation files. This module provides the
shared contracts used at the API and service layers.
"""

from typing import Any
from pydantic import BaseModel, Field


# -------------------------------------------------------------------------
# Generic tool execution result (used in API responses and agent output)
# -------------------------------------------------------------------------

class ToolExecutionResult(BaseModel):
    tool_name: str
    tool_version: str
    status: str  # "completed" | "failed" | "validation_error"
    input_payload: dict[str, Any]
    output_payload: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


# -------------------------------------------------------------------------
# Tool registry item (returned by GET /api/tools)
# -------------------------------------------------------------------------

class ToolInfo(BaseModel):
    name: str
    version: str
    description: str
    input_schema: dict[str, Any]
