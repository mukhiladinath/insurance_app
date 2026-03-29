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

    # =========================================================================
    # Orchestrator fields (populated when running in orchestrator mode)
    # =========================================================================

    # Flag: True when the new orchestrator graph is running instead of the
    # legacy single-tool graph.
    orchestrator_mode: bool

    # ---- Dynamic context requirements (set by assess_context node) ----
    # Drives all smart loading nodes — what to load and how much.
    # Schema:
    #   message_history_depth: int       — number of recent messages to load
    #   memory_sections:       list[str] — client_facts sections to load fully
    #   load_advisory_notes:   bool
    #   load_documents:        bool
    #   load_scratch_pad:      bool
    #   reasoning:             str       — logged explanation
    context_requirements: dict

    # ---- Advisory memory (set by load_memory_smart when load_advisory_notes=True) ----
    # Structured conclusions from prior tool runs (keyed by tool_name).
    # Injected into the planning prompt so the planner knows what was decided.
    advisory_notes: dict

    # ---- Scratch pad (set by load_memory_smart, always loaded) ----
    # Agent working notes from prior runs (lightweight list of dicts).
    scratch_pad_entries: list[dict]

    # ---- Planning ----
    # List of PlanStep dicts produced by the plan_node.
    # Schema per step:
    #   step_id: str             — "step_1", "step_2", …
    #   tool_name: str           — registered tool name OR "direct_response"
    #   description: str         — human-readable description of what the step does
    #   inputs: dict             — pre-populated inputs; may contain {{step_N.field}} refs
    #   depends_on: list[str]    — step_ids that must complete before this step runs
    #   rationale: str           — why this step is in the plan
    plan_steps: list[dict]

    # True when the planner cannot proceed due to missing critical information.
    clarification_needed: bool

    # The natural-language question to ask the user when clarification_needed is True.
    clarification_question: str | None

    # List of memory field paths the planner identified as missing (e.g. "personal.age").
    missing_context: list[str]

    # ---- Execution ----
    # List of StepResult dicts built during execute_steps.
    # Schema per result:
    #   step_id: str
    #   tool_name: str
    #   status: str              — "completed" | "failed" | "skipped"
    #   output: dict | None
    #   data_card: dict | None   — structured UI card
    #   error: str | None
    step_results: list[dict]

    # Structured UI cards extracted from all successful step results.
    data_cards: list[dict]
