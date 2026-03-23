"""
base.py — BaseTool abstraction.

Every tool in the system must subclass BaseTool and implement execute().
Tools are deterministic: same input → same output.
Tools must never call the LLM directly.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolValidationError(Exception):
    """Raised when tool input fails validation before execution."""
    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class ToolExecutionError(Exception):
    """Raised when tool execution fails after validation passes."""


class BaseTool(ABC):
    """
    Abstract base for all insurance advisory tools.

    Subclasses must set:
      name    : unique registry key (e.g. "purchase_retain_life_insurance_in_super")
      version : semver string (e.g. "1.0.0")
      description : one-line human-readable summary

    Subclasses must implement:
      execute(input_data: dict) -> dict
    """

    name: str
    version: str
    description: str

    @abstractmethod
    def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Run the tool with validated input and return a structured result dict.

        Must be deterministic — no randomness, no LLM calls, no side-effects.
        Raises ToolValidationError for bad input.
        Raises ToolExecutionError for runtime failures.
        """

    @abstractmethod
    def get_input_schema(self) -> dict[str, Any]:
        """Return a JSON Schema describing the expected input."""

    def safe_execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Wrapper around execute() that catches known exceptions and
        re-raises them with consistent typing.
        """
        try:
            return self.execute(input_data)
        except (ToolValidationError, ToolExecutionError):
            raise
        except Exception as exc:
            raise ToolExecutionError(
                f"Unexpected error in tool '{self.name}': {exc}"
            ) from exc
