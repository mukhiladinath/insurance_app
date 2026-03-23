"""
tools.py — Tool registry and direct execution routes.

GET  /api/tools                  → list all registered tools with metadata
POST /api/tools/{tool_name}/run  → directly execute a tool (for testing)
"""

from fastapi import APIRouter, HTTPException
from app.services.tool_service import ToolService
from app.schemas.tool import ToolInfo, ToolExecutionResult

router = APIRouter(prefix="/tools", tags=["tools"])

_tool_service = ToolService()


@router.get("", response_model=list[ToolInfo])
async def list_tools():
    """Return all registered tools with name, version, description, and input schema."""
    return _tool_service.list_tools()


@router.post("/{tool_name}/run", response_model=ToolExecutionResult)
async def run_tool(tool_name: str, input_data: dict):
    """
    Directly execute a named tool with the provided input payload.
    Intended for testing and manual invocation.
    Does NOT persist to MongoDB — use POST /api/chat/message for full persistence.
    """
    from app.tools.registry import tool_exists
    if not tool_exists(tool_name):
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found.")

    result = _tool_service.run_tool(tool_name, input_data)
    return result
