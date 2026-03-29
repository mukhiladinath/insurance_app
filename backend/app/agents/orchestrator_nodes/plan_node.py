"""
plan_node.py — Orchestrator node: decompose user intent into a multi-step execution plan.

This is the brain of the agent workspace. Given:
  - The user's instruction
  - Layered context (recent messages, structured client memory, document text)
  - A catalog of available tools with their input schemas

The LLM produces a structured JSON plan:
  - One or more PlanSteps, each naming a tool and pre-populated inputs
  - Inputs drawn from client memory wherever possible
  - {{step_N.field}} chain references when step N's output feeds step M
  - clarification_needed=True if critical info is absent and cannot be inferred

The node writes to state:
  plan_steps, clarification_needed, clarification_question, missing_context
  and also sets final_response (= clarification question) so that the
  clarification path can go straight to persist without an extra node.
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import AgentState
from app.core.llm import get_chat_model
from app.tools.registry import list_tools

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool catalog builder
# ---------------------------------------------------------------------------

# Compact, human-readable description of key inputs per tool.
# Keeps the planning prompt concise while giving the LLM enough signal.
_TOOL_INPUT_HINTS: dict[str, str] = {
    "purchase_retain_life_insurance_in_super": (
        "Key inputs (map from client context):\n"
        "  member.age (int), member.date_of_birth (ISO str), member.smoker (bool),\n"
        "  member.account_inactive (bool — inactive ≥16 months),\n"
        "  member.balance_below_6k (bool — super balance < $6,000),\n"
        "  member.under_25 (bool), member.dependants (int),\n"
        "  fund.balance (float — super balance AUD), fund.type ('MySuper'|'Choice'),\n"
        "  product.cover_types (list of 'DEATH_COVER'|'TPD'|'INCOME_PROTECTION'),\n"
        "  adviceContext.mortgage_balance (float), adviceContext.annual_income (float)\n"
        "Key outputs you can chain: legal_status, placement_assessment.recommendation, "
        "coverage_needs.recommended_sum_insured"
    ),
    "purchase_retain_life_tpd_policy": (
        "Key inputs:\n"
        "  client_age (int), annual_income (float), super_balance (float),\n"
        "  dependants (int), mortgage_balance (float), existing_life_cover (float),\n"
        "  existing_tpd_cover (float), smoker (bool), occupation_class (str),\n"
        "  replacement_policy (bool), current_insurer (str), fund_type (str)\n"
        "Key outputs: recommendation.type, life_need.recommended_sum, tpd_need.recommended_sum"
    ),
    "purchase_retain_income_protection_policy": (
        "Key inputs:\n"
        "  client_age (int), annual_income (float), occupation_class (str),\n"
        "  waiting_period_days (int — 14|30|60|90|180|365|730),\n"
        "  benefit_period (str — '2yr'|'5yr'|'to65'|'to70'),\n"
        "  monthly_expenses (float), existing_ip_cover (float), smoker (bool)\n"
        "Key outputs: recommendation.waiting_period, recommendation.benefit_period, "
        "monthly_benefit_need, replacement_ratio"
    ),
    "purchase_retain_ip_in_super": (
        "Key inputs:\n"
        "  client_age (int), annual_income (float), super_balance (float),\n"
        "  fund_type (str), occupation_class (str), waiting_period_days (int),\n"
        "  benefit_period (str), monthly_expenses (float)\n"
        "Key outputs: sis_compliant, recommendation.type, benefit_need"
    ),
    "purchase_retain_trauma_ci_policy": (
        "Key inputs:\n"
        "  client_age (int), annual_income (float), mortgage_balance (float),\n"
        "  dependants (int), smoker (bool), sum_insured (float), existing_trauma_cover (float)\n"
        "Key outputs: recommendation.type, recommended_sum_insured, affordability_assessment"
    ),
    "tpd_policy_assessment": (
        "Key inputs:\n"
        "  client_age (int), occupation_class (str), existing_tpd_sum_insured (float),\n"
        "  annual_income (float), debts (float), super_balance (float),\n"
        "  tpd_definition (str — 'any_occupation'|'own_occupation'), fund_type (str)\n"
        "Key outputs: adequacy_verdict, gap_analysis.shortfall, recommendation"
    ),
    "purchase_retain_tpd_in_super": (
        "Key inputs:\n"
        "  client_age (int), super_balance (float), fund_type (str),\n"
        "  occupation_class (str), annual_income (float), debts (float),\n"
        "  existing_tpd_cover (float)\n"
        "Key outputs: sis_compliant, legal_status, recommended_sum_insured"
    ),
}


def _build_tool_catalog() -> str:
    """Return a compact, LLM-friendly catalog of all registered tools."""
    tools = list_tools()
    lines: list[str] = []
    for t in tools:
        hints = _TOOL_INPUT_HINTS.get(t.name, "")
        lines.append(
            f"TOOL: {t.name}\n"
            f"PURPOSE: {t.description}\n"
            f"{hints}\n"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Client memory formatter
# ---------------------------------------------------------------------------

def _format_memory(client_memory: dict) -> str:
    """Return a flat, readable list of known client facts (non-null values only)."""
    facts = client_memory.get("client_facts", {})
    if not facts:
        return "No client facts on record."

    lines: list[str] = []
    for section, fields in facts.items():
        if not isinstance(fields, dict):
            continue
        for field, value in fields.items():
            if value is None or value == "" or value == []:
                continue
            lines.append(f"  {section}.{field}: {value}")

    return "\n".join(lines) if lines else "No client facts on record."


# ---------------------------------------------------------------------------
# Recent messages formatter
# ---------------------------------------------------------------------------

def _format_recent(recent_messages: list[dict], n: int = 4) -> str:
    """Return the last n messages as a compact dialogue string."""
    tail = recent_messages[-n:] if len(recent_messages) > n else recent_messages
    if not tail:
        return "(no prior conversation)"
    return "\n".join(
        f"  {m.get('role', 'unknown').upper()}: {str(m.get('content', ''))[:300]}"
        for m in tail
    )


# ---------------------------------------------------------------------------
# Planning prompt
# ---------------------------------------------------------------------------

_PLANNING_SYSTEM = """\
You are an insurance advisory planning agent. Your job is to analyse a user's \
request and produce a structured JSON execution plan.

## AVAILABLE TOOLS
{tool_catalog}

## RULES
1. Extract as many inputs as possible directly from CLIENT FACTS below. Do not \
   ask for information that is already known.
2. Use "direct_response" as tool_name when the question is general/educational \
   and no calculation tool is needed.
3. For multi-step analyses, order steps logically. Use "depends_on": ["step_X"] \
   when a step needs another step's output.
4. Reference a previous step's output field with {{{{step_N.field_path}}}} syntax \
   (e.g. {{{{step_1.coverage_needs.recommended_sum_insured}}}}).
5. Only set clarification_needed=true if critical information is genuinely missing \
   and cannot be reasonably inferred. Be specific in clarification_question — tell \
   the user EXACTLY which fields are needed and why.
6. When clarification_needed=true, list EVERY missing field in missing_context using \
   dot-notation: "section.field_name" (e.g. "personal.age", "financial.annual_gross_income"). \
   These must match the canonical schema field names exactly so the UI can highlight them.
7. Always return valid JSON — no markdown fences, no prose outside the JSON.

## OUTPUT SCHEMA
{{
  "clarification_needed": bool,
  "clarification_question": "string | null — friendly message asking the user to fill in specific fields",
  "missing_context": ["section.field_name", ...],
  "steps": [
    {{
      "step_id": "step_1",
      "tool_name": "tool_name_or_direct_response",
      "description": "what this step does",
      "inputs": {{ /* pre-populated from context; may contain {{{{step_N.field}}}} */ }},
      "depends_on": [],
      "rationale": "why this step is needed"
    }}
  ]
}}
"""

_PLANNING_HUMAN = """\
## CLIENT FACTS (known from conversation so far)
{known_facts}

## PRIOR ADVISORY CONCLUSIONS (from previous analyses this conversation)
{advisory_notes}

## AGENT WORKING NOTES (scratch pad)
{scratch_pad}

## RECENT CONVERSATION
{recent_messages}

## DOCUMENT CONTEXT
{document_context}

## USER REQUEST
{user_message}

Produce the JSON execution plan now.
"""


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Extract the first valid JSON object from LLM output."""
    # Strip markdown fences if present
    text = re.sub(r"```(?:json)?", "", text).strip()

    # Try parsing the whole string first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the first {...} block
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract JSON from LLM output: {text[:300]}")


# ---------------------------------------------------------------------------
# Fallback plan (when LLM fails)
# ---------------------------------------------------------------------------

def _fallback_plan(user_message: str) -> list[dict]:
    """Return a single direct_response step so the agent always has a plan."""
    return [
        {
            "step_id": "step_1",
            "tool_name": "direct_response",
            "description": "Respond directly to the user's question",
            "inputs": {},
            "depends_on": [],
            "rationale": "Fallback: planning LLM unavailable or returned invalid output",
        }
    ]


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def plan_execution(state: AgentState) -> dict:
    """
    LLM-based planning node.

    Reads:
      user_message, recent_messages, client_memory, document_context

    Writes:
      plan_steps, clarification_needed, clarification_question,
      missing_context, final_response (if clarification)
    """
    user_message = state.get("user_message", "")
    recent_messages = state.get("recent_messages", [])
    client_memory = state.get("client_memory", {})
    document_context = state.get("document_context") or "(none)"
    advisory_notes: dict = state.get("advisory_notes") or {}
    scratch_pad_entries: list[dict] = state.get("scratch_pad_entries") or []

    tool_catalog = _build_tool_catalog()
    known_facts = _format_memory(client_memory)
    recent_str = _format_recent(recent_messages)

    # Format advisory notes for the prompt
    if advisory_notes:
        advisory_str = "\n".join(
            f"  [{tool}]: verdict={note.get('verdict')} — {note.get('recommendation', '')} "
            f"(analysed {note.get('analysed_at', '')[:10]})"
            for tool, note in advisory_notes.items()
        )
    else:
        advisory_str = "(no prior analyses this conversation)"

    # Format scratch pad
    if scratch_pad_entries:
        scratch_str = "\n".join(
            f"  [{e.get('category', 'note')}] {e.get('content', '')}"
            for e in scratch_pad_entries[-5:]  # last 5 entries only
        )
    else:
        scratch_str = "(empty)"

    system_prompt = _PLANNING_SYSTEM.format(tool_catalog=tool_catalog)
    human_prompt = _PLANNING_HUMAN.format(
        known_facts=known_facts,
        advisory_notes=advisory_str,
        scratch_pad=scratch_str,
        recent_messages=recent_str,
        document_context=document_context[:1000],  # cap doc context for prompt
        user_message=user_message,
    )

    try:
        llm = get_chat_model(temperature=0.1)
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ]
        response = await llm.ainvoke(messages)
        raw = response.content if hasattr(response, "content") else str(response)
        plan_data = _extract_json(raw)

        clarification_needed: bool = bool(plan_data.get("clarification_needed", False))
        clarification_question: str | None = plan_data.get("clarification_question")
        missing_context: list[str] = plan_data.get("missing_context", [])
        steps: list[dict] = plan_data.get("steps", [])

        # Validate steps have required fields; drop malformed ones
        valid_steps = []
        for s in steps:
            if "step_id" in s and "tool_name" in s:
                valid_steps.append({
                    "step_id": s["step_id"],
                    "tool_name": s["tool_name"],
                    "description": s.get("description", ""),
                    "inputs": s.get("inputs", {}),
                    "depends_on": s.get("depends_on", []),
                    "rationale": s.get("rationale", ""),
                })

        if not valid_steps:
            valid_steps = _fallback_plan(user_message)
            clarification_needed = False

        logger.info(
            "plan_execution: %d step(s), clarification_needed=%s",
            len(valid_steps), clarification_needed,
        )

        update: dict[str, Any] = {
            "plan_steps": valid_steps,
            "clarification_needed": clarification_needed,
            "clarification_question": clarification_question,
            "missing_context": missing_context,
        }

        # If clarification is needed, pre-set final_response so the clarification
        # path (→ persist_results → END) doesn't need an extra compose node.
        if clarification_needed and clarification_question:
            update["final_response"] = clarification_question
            update["structured_response_payload"] = {
                "type": "clarification",
                "missing_context": missing_context,
            }

        return update

    except Exception as exc:
        logger.exception("plan_execution failed: %s", exc)
        return {
            "plan_steps": _fallback_plan(user_message),
            "clarification_needed": False,
            "clarification_question": None,
            "missing_context": [],
            "errors": state.get("errors", []) + [f"Planning error: {exc}"],
        }
