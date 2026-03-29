"""
planner_service.py — LLM planning + summarization for the finobi-style orchestrator.

The planner receives a natural-language instruction plus context and returns one of:
  - confirmation_required  → structured plan with tool steps for user to confirm
  - clarification_needed   → ambiguous instruction, needs user input
  - qna_answer             → can be answered directly from memory/context
  - no_plan                → unrecognised or out-of-scope instruction

The summarizer generates a human-readable prose summary from tool execution results.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.llm import get_chat_model_fresh

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PLANNER_SYSTEM_PROMPT
# ---------------------------------------------------------------------------

PLANNER_SYSTEM_PROMPT = """\
You are an AI orchestrator for an insurance advisory platform.
Your job is to analyse a natural-language instruction from an insurance adviser and
return a structured plan that the system can execute.

## TOOLS AVAILABLE

You may plan steps using ONLY these tool IDs:

### Client & Factfind
- get_client_factfind       Read the client's factfind data. Use for income, age, assets, insurance details, goals.
                            Parameters: { clientId: string, section?: "personal"|"financial"|"insurance"|"health"|"goals" }
- update_client_factfind    Update specific fields in the client's factfind.
                            Parameters: { clientId: string, changes: Record<string, unknown> }
- get_client_profile        Read the client's basic profile (name, DOB, contact info).
                            Parameters: { clientId: string }
- list_clients              List all available clients.
                            Parameters: {}

### AI Memory
- read_client_memory        Read a specific memory category for a client.
                            Use for: goals, risk profile, health, estate planning, employment context, adviser notes.
                            Use BOTH this and get_client_factfind for comprehensive answers.
                            Parameters: { clientId: string, category: "profile"|"employment-income"|"financial-position"|"insurance"|"goals-risk-profile"|"tax-structures"|"estate-planning"|"health"|"interactions" }
- search_client_memory      Search across all memory categories for a client.
                            Parameters: { clientId: string, query: string }

### Insurance Analysis Tools
- life_insurance_in_super   Analyse life insurance inside superannuation (purchase/retain decision).
                            Parameters: { clientId: string }
- life_tpd_policy           Analyse life and TPD (Total & Permanent Disability) combined policy.
                            Parameters: { clientId: string }
- income_protection_policy  Analyse income protection insurance policy (purchase/retain decision).
                            Parameters: { clientId: string }
- ip_in_super               Analyse income protection insurance inside superannuation.
                            Parameters: { clientId: string }
- trauma_critical_illness   Analyse trauma / critical illness insurance policy.
                            Parameters: { clientId: string }
- tpd_policy_assessment     Assess a standalone TPD policy (detailed assessment).
                            Parameters: { clientId: string }
- tpd_in_super              Analyse TPD insurance inside superannuation (purchase/retain decision).
                            Parameters: { clientId: string }

### Documents & SOA
- extract_factfind_from_document   Extract client data from an uploaded document and auto-fill the factfind.
                            Use this when the user uploads a file (storage_ref is provided in context) and wants
                            to fill or update the factfind from the document. NEVER use update_client_factfind
                            for document-based updates — always use this tool instead.
                            Parameters: { clientId: string, storage_ref: string }
- generate_soa              Generate a Statement of Advice document for the client.
                            Parameters: { clientId: string }

## CONTEXT RULES

1. If a clientId is available in context (selectedClientId), use it in tool parameters.
2. For insurance analysis tools, ALWAYS first check if a clientId is available.
   If not, return clarification_needed asking which client.
3. You may chain steps: e.g., step 0 reads factfind, step 1 runs analysis using same clientId.
4. Use {{stepN.fieldName}} notation to reference a prior step's output (e.g., {{step0.clientId}}).

## QNA RULES (Rule 10)

If the instruction is a QUESTION about a client (not an action), and can be answered from:
  - Client memory (read_client_memory with appropriate category)
  - Factfind data (get_client_factfind)
...return type "qna_answer" with a single tool step to fetch the data.

Examples of QnA questions:
  - "What is this client's risk profile?" → read_client_memory, category: goals-risk-profile
  - "What insurance does John have?" → get_client_factfind, section: insurance
  - "What are the client's goals?" → read_client_memory, category: goals-risk-profile
  - "What is John's annual income?" → get_client_factfind, section: financial

## COMPARING TWO INSURANCE ANALYSES

When the user wants to **compare** two different insurance product analyses (phrases like "compare", "versus", "vs", "side by side", "which is better", "difference between"):
- Return **confirmation_required** with **exactly two** steps.
- Each step must be one of the insurance analysis tools (`life_insurance_in_super`, `life_tpd_policy`, `income_protection_policy`, `ip_in_super`, `trauma_critical_illness`, `tpd_policy_assessment`, `tpd_in_super`) chosen to match what they asked about.
- Use the same `clientId` from context for both steps.
- Do **not** add extra steps unless the user explicitly asked for factfind or memory first; two analysis tools are enough for a compare request.

Examples:
- "Compare life in super and income protection" → `life_insurance_in_super` then `income_protection_policy`
- "Run TPD in super vs standalone TPD and compare" → `tpd_in_super` then `tpd_policy_assessment`

## TOOL SELECTION GUIDE (Rule 11)

When deciding which tool to use for a question:
  - Financial data (income, assets, super balance, liabilities) → get_client_factfind
  - Insurance policy details (cover amounts, premiums) → get_client_factfind, section: insurance
  - Goals, risk tolerance, investment horizon → read_client_memory, category: goals-risk-profile
  - Health conditions, medical history → read_client_memory, category: health
  - Estate planning (wills, POA) → read_client_memory, category: estate-planning
  - Employment history, business income → read_client_memory, category: employment-income
  - Past decisions, meeting notes, adviser observations → read_client_memory, category: interactions
  - Run insurance analysis → use the appropriate insurance tool (life_insurance_in_super, etc.)

## CLARIFICATION RULES

Return clarification_needed when:
  - The instruction mentions a client but no clientId is in context AND the instruction is ambiguous
  - The instruction is unclear or could mean multiple things
  - A required parameter is missing and cannot be inferred

Do NOT ask for clarification if:
  - A clientId is already in context (selectedClientId) — just use it
  - The instruction clearly maps to a tool

## OUTPUT FORMAT

You MUST return ONLY a valid JSON object in one of these formats:

### confirmation_required (for actions that need user approval)
{
  "type": "confirmation_required",
  "explanation": "One sentence explaining what will happen",
  "step_labels": ["Human-readable label for step 0", "Human-readable label for step 1"],
  "steps": [
    {
      "tool_id": "tool_name",
      "parameters": { "clientId": "abc123", "section": "financial" }
    }
  ]
}

### qna_answer (for questions — fetches data, no confirmation needed)
{
  "type": "qna_answer",
  "explanation": "I'll look up the client's risk profile from their memory.",
  "step_labels": ["Read goals & risk profile"],
  "steps": [
    {
      "tool_id": "read_client_memory",
      "parameters": { "clientId": "abc123", "category": "goals-risk-profile" }
    }
  ]
}

### clarification_needed
{
  "type": "clarification_needed",
  "question": "Which client would you like to analyse?",
  "options": ["Select from the client list", "Type the client name"]
}

### no_plan
{
  "type": "no_plan",
  "message": "I can only help with insurance analysis, client factfind, and advisory tasks."
}

## IMPORTANT RULES
- Return ONLY the JSON object. No markdown, no explanation outside the JSON.
- Never invent tool IDs not listed above.
- Use the exact tool_id strings as listed.
- For multi-step plans, keep steps to 3 or fewer unless clearly necessary.
- Prefer qna_answer over confirmation_required for pure information queries.
"""

SUMMARIZER_SYSTEM_PROMPT = """\
You are an insurance advisory assistant. You have just executed one or more tools on behalf of an adviser.

Summarise the results in clear, professional prose suitable for an insurance adviser.
Be concise but complete. Use bullet points for key findings.
If the results include a recommendation, state it clearly.
If there are warnings or gaps in client data, mention them.
Do not include raw JSON or technical field names — translate to plain English.
Keep the summary under 300 words unless the data warrants more detail.
"""


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------


async def plan_instruction(
    instruction: str,
    context: dict[str, Any],
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Call LLM with PLANNER_SYSTEM_PROMPT and return the parsed plan result.

    Args:
        instruction: The adviser's natural-language instruction.
        context: Page context dict with keys: currentPage, selectedClientId, selectedClientName.
        messages: Recent conversation history (list of {role, content} dicts).

    Returns:
        Parsed JSON plan object (one of the 4 types above).
    """
    llm = get_chat_model_fresh(temperature=0.1)

    # Build context description for the planner
    ctx_parts: list[str] = []
    if context.get("selectedClientId"):
        ctx_parts.append(f"Selected client: {context.get('selectedClientName', 'Unknown')} (clientId: {context['selectedClientId']})")
    if context.get("currentPage"):
        ctx_parts.append(f"Current page: {context['currentPage']}")

    # Include uploaded file refs so planner knows to use extract_factfind_from_document
    attached_files: list[dict] = context.get("attachedFiles", [])
    if attached_files:
        file_refs = [f.get("storage_ref") for f in attached_files if f.get("storage_ref")]
        if file_refs:
            ctx_parts.append(f"Attached files (storage_refs): {', '.join(file_refs)}")
            ctx_parts.append("NOTE: The user has uploaded document(s). If the instruction is about filling or updating the factfind, plan an extract_factfind_from_document step using the storage_ref above.")

    # Second LLM pass: suggest insurance engines from the instruction (non-binding hints for the planner)
    try:
        from app.services.insurance_tool_selection_llm import (
            llm_select_insurance_engine_tools,
            registry_ids_to_planner_hint,
        )

        suggested = await llm_select_insurance_engine_tools(
            instruction,
            purpose="adviser_instruction",
        )
        hint = registry_ids_to_planner_hint(suggested)
        if hint:
            ctx_parts.append(hint)
    except Exception as exc:
        logger.warning("insurance tool suggestion LLM failed (planner continues without it): %s", exc)

    context_str = "\n".join(ctx_parts) if ctx_parts else "No specific client selected."

    # Build conversation history for context
    history_text = ""
    if messages:
        recent = messages[-6:]  # last 6 messages for context
        history_lines = []
        for msg in recent:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            history_lines.append(f"{role.upper()}: {content}")
        if history_lines:
            history_text = "\nRecent conversation:\n" + "\n".join(history_lines) + "\n"

    user_prompt = f"""\
Context:
{context_str}
{history_text}
Instruction: {instruction}

Return the JSON plan."""

    chat_messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await llm.ainvoke(chat_messages)
        raw = response.content.strip() if hasattr(response, "content") else ""

        # Strip markdown fences if model wraps in ```json
        if raw.startswith("```"):
            lines = [l for l in raw.splitlines() if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        plan = json.loads(raw)

        if not isinstance(plan, dict) or "type" not in plan:
            logger.warning("planner returned invalid structure: %s", raw[:200])
            return {
                "type": "no_plan",
                "message": "I couldn't understand that request. Please try rephrasing.",
            }

        return plan

    except json.JSONDecodeError as exc:
        logger.warning("planner JSON parse error: %s | raw=%s", exc, raw[:300] if "raw" in dir() else "")
        return {
            "type": "no_plan",
            "message": "I couldn't generate a valid plan. Please try rephrasing your request.",
        }
    except Exception as exc:
        logger.error("planner LLM call failed: %s", exc)
        return {
            "type": "no_plan",
            "message": f"Planning failed: {exc}",
        }


# ---------------------------------------------------------------------------
# Summarizer
# ---------------------------------------------------------------------------


async def summarize_results(
    instruction: str,
    tool_results: list[dict[str, Any]],
    messages: list[dict[str, Any]] | None = None,
) -> str:
    """
    Generate a prose summary of tool execution results.

    Args:
        instruction: The original adviser instruction.
        tool_results: List of {tool_id, parameters, result, status} dicts.
        messages: Recent conversation history.

    Returns:
        Human-readable summary string.
    """
    if not tool_results:
        return "No results to summarise."

    llm = get_chat_model_fresh(temperature=0.2)

    # Format results for the prompt
    results_text = json.dumps(tool_results, indent=2, default=str)
    if len(results_text) > 8000:
        results_text = results_text[:8000] + "\n... [truncated]"

    # Build conversation history
    history_text = ""
    if messages:
        recent = messages[-4:]
        history_lines = [f"{m.get('role','').upper()}: {m.get('content','')}" for m in recent]
        if history_lines:
            history_text = "\nRecent conversation:\n" + "\n".join(history_lines) + "\n"

    user_prompt = f"""\
Original instruction: {instruction}
{history_text}
Tool results:
{results_text}

Provide a clear, professional summary for the insurance adviser."""

    chat_messages = [
        {"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        response = await llm.ainvoke(chat_messages)
        return response.content.strip() if hasattr(response, "content") else "Results retrieved successfully."
    except Exception as exc:
        logger.error("summarizer LLM call failed: %s", exc)
        return f"Tool execution completed. ({len(tool_results)} step(s) executed)"
