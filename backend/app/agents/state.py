"""
state.py — LangGraph agent state definition.

AgentState is a TypedDict that flows through every node in the graph.
Nodes read from state, return partial updates, and LangGraph merges them.
"""

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    # -------------------------------------------------------------------------
    # Identifiers (set before graph invocation)
    # -------------------------------------------------------------------------
    user_id: str
    conversation_id: str
    agent_run_id: str

    # -------------------------------------------------------------------------
    # Input (set before graph invocation)
    # -------------------------------------------------------------------------
    user_message: str
    tool_hint: str | None               # optional caller-supplied tool name hint
    tool_input_override: dict | None    # caller-supplied pre-structured tool input

    # -------------------------------------------------------------------------
    # Context (populated by load_context node)
    # -------------------------------------------------------------------------
    recent_messages: list[dict]         # [{role, content}, ...] for LLM context

    # -------------------------------------------------------------------------
    # Intent classification (populated by classify_intent node)
    # -------------------------------------------------------------------------
    intent: str                         # one of the Intent constants
    selected_tool: str | None           # tool name, or None for direct response
    extracted_tool_input: dict | None   # tool input extracted from user message

    # -------------------------------------------------------------------------
    # Tool execution (populated by execute_tool node)
    # -------------------------------------------------------------------------
    tool_result: dict | None            # raw tool output dict
    tool_warnings: list[str]
    tool_error: str | None

    # -------------------------------------------------------------------------
    # Response composition (populated by compose_response node)
    # -------------------------------------------------------------------------
    final_response: str
    structured_response_payload: dict | None  # additional structured data for frontend

    # -------------------------------------------------------------------------
    # Persistence metadata (populated by persist_results node)
    # -------------------------------------------------------------------------
    assistant_message_id: str | None

    # -------------------------------------------------------------------------
    # Error tracking
    # -------------------------------------------------------------------------
    errors: list[str]
