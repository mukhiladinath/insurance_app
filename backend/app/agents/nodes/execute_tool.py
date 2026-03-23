"""
execute_tool.py — Node: execute the selected tool.

Looks up the tool in the registry, validates input, executes it,
and stores the result (or error) in state.
"""

import logging
from app.agents.state import AgentState
from app.tools.registry import get_tool
from app.tools.base import ToolValidationError, ToolExecutionError

logger = logging.getLogger(__name__)


async def execute_tool(state: AgentState) -> dict:
    """Execute the selected tool and capture the result."""
    tool_name = state.get("selected_tool")
    if not tool_name:
        return {"tool_result": None, "tool_warnings": [], "tool_error": "No tool selected."}

    tool = get_tool(tool_name)
    if not tool:
        error = f"Tool '{tool_name}' not found in registry."
        logger.error(error)
        return {"tool_result": None, "tool_warnings": [], "tool_error": error}

    # Resolve tool input
    tool_input = state.get("extracted_tool_input") or state.get("tool_input_override") or {}

    logger.info("execute_tool: running '%s' with input keys: %s", tool_name, list(tool_input.keys()))

    try:
        result = tool.safe_execute(tool_input)
        warnings = result.get("validation", {}).get("warnings", []) if isinstance(result.get("validation"), dict) else []
        logger.info("execute_tool: '%s' completed successfully", tool_name)
        return {
            "tool_result": result,
            "tool_warnings": [w.get("message", str(w)) for w in warnings] if warnings else [],
            "tool_error": None,
        }

    except ToolValidationError as exc:
        msg = f"Tool input validation error: {exc}"
        logger.warning("execute_tool: %s", msg)
        return {"tool_result": None, "tool_warnings": [], "tool_error": msg}

    except ToolExecutionError as exc:
        msg = f"Tool execution error: {exc}"
        logger.error("execute_tool: %s", msg)
        return {"tool_result": None, "tool_warnings": [], "tool_error": msg}

    except Exception as exc:
        msg = f"Unexpected tool error: {exc}"
        logger.exception("execute_tool unexpected: %s", exc)
        return {"tool_result": None, "tool_warnings": [], "tool_error": msg}
