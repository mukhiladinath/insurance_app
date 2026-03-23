"""
tool_service.py — Direct tool execution service (used by /api/tools routes).

The agent uses tools through the graph. This service provides a direct
execution path for testing and manual invocation via the tools API.
"""

from app.tools.registry import get_tool, list_tools
from app.tools.base import ToolValidationError, ToolExecutionError
from app.schemas.tool import ToolExecutionResult, ToolInfo
from app.core.constants import ToolCallStatus


class ToolService:
    def list_tools(self) -> list[ToolInfo]:
        return [
            ToolInfo(
                name=t.name,
                version=t.version,
                description=t.description,
                input_schema=t.get_input_schema(),
            )
            for t in list_tools()
        ]

    def run_tool(self, tool_name: str, input_data: dict) -> ToolExecutionResult:
        tool = get_tool(tool_name)
        if not tool:
            return ToolExecutionResult(
                tool_name=tool_name,
                tool_version="unknown",
                status=ToolCallStatus.FAILED,
                input_payload=input_data,
                error=f"Tool '{tool_name}' not found.",
            )

        try:
            output = tool.safe_execute(input_data)
            warnings = []
            if isinstance(output.get("validation"), dict):
                warnings = [w.get("message", str(w)) for w in output["validation"].get("warnings", [])]

            return ToolExecutionResult(
                tool_name=tool.name,
                tool_version=tool.version,
                status=ToolCallStatus.COMPLETED,
                input_payload=input_data,
                output_payload=output,
                warnings=warnings,
            )

        except ToolValidationError as exc:
            return ToolExecutionResult(
                tool_name=tool.name,
                tool_version=tool.version,
                status=ToolCallStatus.VALIDATION_ERROR,
                input_payload=input_data,
                error=str(exc),
            )

        except ToolExecutionError as exc:
            return ToolExecutionResult(
                tool_name=tool.name,
                tool_version=tool.version,
                status=ToolCallStatus.FAILED,
                input_payload=input_data,
                error=str(exc),
            )
