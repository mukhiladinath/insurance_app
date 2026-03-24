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
    # Input (additional — set before graph invocation)
    # -------------------------------------------------------------------------
    user_message_id: str | None         # MongoDB id of the saved user message
    attached_files: list[dict]          # [{filename, content_type, size_bytes, storage_ref}, ...]

    # -------------------------------------------------------------------------
    # Context (populated by load_context node)
    # -------------------------------------------------------------------------
    recent_messages: list[dict]         # [{role, content}, ...] for LLM context

    # -------------------------------------------------------------------------
    # Structured memory (populated by load_memory node, updated by update_memory)
    # -------------------------------------------------------------------------
    client_memory: dict                 # conversation_memory document (canonical facts)

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
    # Document context (populated by load_documents node)
    # -------------------------------------------------------------------------
    document_context: str | None        # concatenated extracted text from uploaded documents

    # -------------------------------------------------------------------------
    # Overseer verdict (populated by overseer_quality_gate node)
    # -------------------------------------------------------------------------
    overseer_status:         str          # e.g. "proceed", "ask_user", "proceed_with_caution"
    overseer_reason:         str          # one-line explanation
    overseer_caution_notes:  list[str]    # optional caveats for compose_response
    overseer_question:       str | None   # clarifying question when status == "ask_user"
    overseer_retry_count:    int          # number of overseer-directed retries consumed
    overseer_missing_fields: list[dict]   # serialised MissingField list

    # -------------------------------------------------------------------------
    # Error tracking
    # -------------------------------------------------------------------------
    errors: list[str]
