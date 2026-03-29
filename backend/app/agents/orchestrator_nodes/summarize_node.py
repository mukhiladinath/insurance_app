"""
summarize_node.py — Orchestrator node: synthesise all step results into a final response.

After execute_steps runs all tool calls, this node:
  1. Collects all completed step outputs.
  2. Uses the LLM to compose a coherent, advisorially appropriate natural-language
     response that integrates the results of every step.
  3. For direct-response plans (no tools executed), generates a direct LLM answer
     using client context and conversation history.
  4. Sets final_response and structured_response_payload on state.

State reads:
  user_message, step_results, plan_steps, recent_messages, client_memory,
  document_context, data_cards

State writes:
  final_response, structured_response_payload
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import AgentState
from app.core.llm import get_chat_model

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Knowledge base loader (same as compose_response.py)
# ---------------------------------------------------------------------------

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "knowledge" / "products"

_KNOWLEDGE_FILES: dict[str, str] = {
    "purchase_retain_life_tpd_policy":          "life-cover-comparison.md",
    "purchase_retain_life_insurance_in_super":  "super-fund-insurance.md",
    "purchase_retain_income_protection_policy": "income-protection-comparison.md",
    "purchase_retain_ip_in_super":              "income-protection-comparison.md",
    "tpd_policy_assessment":                    "tpd-cover-comparison.md",
    "purchase_retain_trauma_ci_policy":         "trauma-cover-comparison.md",
    "purchase_retain_tpd_in_super":             "super-fund-insurance.md",
}


def _load_knowledge(tool_names: list[str]) -> str:
    """Load and deduplicate knowledge-base files for the tools used."""
    seen_files: set[str] = set()
    chunks: list[str] = []
    for name in tool_names:
        fname = _KNOWLEDGE_FILES.get(name)
        if fname and fname not in seen_files:
            seen_files.add(fname)
            fpath = _KNOWLEDGE_DIR / fname
            if fpath.exists():
                try:
                    chunks.append(fpath.read_text(encoding="utf-8"))
                except Exception:
                    pass
    return "\n\n---\n\n".join(chunks) if chunks else ""


# ---------------------------------------------------------------------------
# Step result formatter for the LLM prompt
# ---------------------------------------------------------------------------

def _format_step_results(step_results: list[dict]) -> str:
    if not step_results:
        return "(no tool steps were executed)"
    lines: list[str] = []
    for r in step_results:
        status = r.get("status", "unknown")
        tool = r.get("tool_name", "unknown")
        step_id = r.get("step_id", "?")
        if status == "completed" and r.get("output"):
            # Truncate very large outputs to avoid prompt overflow
            output_str = json.dumps(r["output"], indent=2)
            if len(output_str) > 3000:
                output_str = output_str[:3000] + "\n... (truncated)"
            lines.append(f"[{step_id} — {tool}] STATUS: completed\n{output_str}")
        elif status == "skipped":
            desc = r.get("description", "")
            err = r.get("error", "")
            lines.append(f"[{step_id} — {tool}] STATUS: skipped ({err or desc})")
        else:
            lines.append(
                f"[{step_id} — {tool}] STATUS: {status} "
                f"ERROR: {r.get('error', 'unknown error')}"
            )
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Summarise prompt templates
# ---------------------------------------------------------------------------

_SYSTEM_WITH_TOOLS = """\
You are an expert insurance financial adviser. You have just run one or more \
analysis tools on behalf of a client and must now deliver a clear, professional \
summary of the findings.

Guidelines:
- Integrate results from ALL completed steps into a single coherent response.
- Use plain English — no raw JSON or code blocks.
- Reference specific numbers (sums insured, premiums, waiting periods) where \
  available in the tool outputs.
- Note any steps that failed or were skipped and explain the implication briefly.
- End with clear, actionable next steps for the client.
- Format using markdown headings and bullet points for readability.

PRODUCT KNOWLEDGE (use as background, do not repeat verbatim):
{knowledge}
"""

_SYSTEM_DIRECT = """\
You are an expert insurance financial adviser in Australia. Answer the client's \
question clearly and professionally. Use the client facts and conversation history \
as context. Format your response with markdown headings and bullets where helpful.
"""

_HUMAN_WITH_TOOLS = """\
## Client Context
{known_facts}

## Tool Execution Results
{step_results}

## Client's Original Request
{user_message}

Write the adviser summary now.
"""

_HUMAN_DIRECT = """\
## Client Context
{known_facts}

## Recent Conversation
{recent_messages}

## Document Context
{document_context}

## Client's Question
{user_message}

Answer now.
"""


# ---------------------------------------------------------------------------
# Memory formatter (shared helper)
# ---------------------------------------------------------------------------

def _format_memory(client_memory: dict) -> str:
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


def _format_recent(recent_messages: list[dict], n: int = 4) -> str:
    tail = recent_messages[-n:] if len(recent_messages) > n else recent_messages
    if not tail:
        return "(no prior conversation)"
    return "\n".join(
        f"  {m.get('role', 'unknown').upper()}: {str(m.get('content', ''))[:400]}"
        for m in tail
    )


# ---------------------------------------------------------------------------
# Fallback response builder (no LLM)
# ---------------------------------------------------------------------------

def _build_fallback_response(step_results: list[dict], user_message: str) -> str:
    completed = [r for r in step_results if r.get("status") == "completed"]
    failed = [r for r in step_results if r.get("status") == "failed"]

    parts = [f"## Analysis Results\n\nI've completed the analysis for: *{user_message}*\n"]
    if completed:
        parts.append(f"**Completed:** {', '.join(r['tool_name'] for r in completed)}")
    if failed:
        parts.append(
            f"**Could not complete:** "
            f"{', '.join(r['tool_name'] + ' — ' + (r.get('error') or '') for r in failed)}"
        )
    parts.append("\nPlease review the data cards above for detailed results.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def orchestrate_summarize(state: AgentState) -> dict:
    """
    Synthesise all step results into a natural-language adviser response.

    Reads:  step_results, plan_steps, user_message, client_memory,
            recent_messages, document_context, data_cards
    Writes: final_response, structured_response_payload
    """
    step_results: list[dict] = state.get("step_results", [])
    plan_steps: list[dict] = state.get("plan_steps", [])
    user_message = state.get("user_message", "")
    client_memory = state.get("client_memory", {})
    recent_messages = state.get("recent_messages", [])
    document_context = state.get("document_context") or "(none)"
    data_cards = state.get("data_cards", [])

    known_facts = _format_memory(client_memory)

    # Determine if any tool steps actually ran (vs pure direct_response plan)
    tool_steps_ran = any(
        r.get("status") == "completed" and r.get("tool_name") != "direct_response"
        for r in step_results
    )

    tool_names_used = [
        s["tool_name"] for s in plan_steps if s.get("tool_name") != "direct_response"
    ]

    try:
        llm = get_chat_model(temperature=0.3)

        if tool_steps_ran:
            knowledge = _load_knowledge(tool_names_used)
            system_msg = SystemMessage(
                content=_SYSTEM_WITH_TOOLS.format(knowledge=knowledge or "(none available)")
            )
            human_msg = HumanMessage(
                content=_HUMAN_WITH_TOOLS.format(
                    known_facts=known_facts,
                    step_results=_format_step_results(step_results),
                    user_message=user_message,
                )
            )
        else:
            system_msg = SystemMessage(content=_SYSTEM_DIRECT)
            human_msg = HumanMessage(
                content=_HUMAN_DIRECT.format(
                    known_facts=known_facts,
                    recent_messages=_format_recent(recent_messages),
                    document_context=document_context[:800],
                    user_message=user_message,
                )
            )

        response = await llm.ainvoke([system_msg, human_msg])
        final_response = response.content if hasattr(response, "content") else str(response)

    except Exception as exc:
        logger.exception("orchestrate_summarize LLM call failed: %s", exc)
        final_response = _build_fallback_response(step_results, user_message)

    structured_payload = {
        "type": "orchestrator_run",
        "plan_steps": plan_steps,
        "step_results": [
            {
                "step_id": r["step_id"],
                "tool_name": r["tool_name"],
                "description": r.get("description", ""),
                "status": r["status"],
                "error": r.get("error"),
                # Don't include raw output here — it's in data_cards
            }
            for r in step_results
        ],
        "data_cards": data_cards,
    }

    logger.info(
        "orchestrate_summarize: response composed (%d chars), %d data cards",
        len(final_response), len(data_cards),
    )

    return {
        "final_response": final_response,
        "structured_response_payload": structured_payload,
    }
