"""
workspace_summarize.py — Synthesise step results into a final adviser response.

Adapted from orchestrator_nodes/summarize_node.py.
Reads factfind_snapshot (flat dict) instead of client_memory.

State reads:  step_results, tool_plan, user_message, factfind_snapshot,
              recent_messages, extracted_document_context, data_cards, advisory_notes
State writes: final_response, structured_response_payload
"""

import json
import logging
from pathlib import Path

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.workspace_state import WorkspaceState
from app.core.llm import get_chat_model

logger = logging.getLogger(__name__)

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
    seen: set[str] = set()
    chunks: list[str] = []
    for name in tool_names:
        fname = _KNOWLEDGE_FILES.get(name)
        if fname and fname not in seen:
            seen.add(fname)
            fpath = _KNOWLEDGE_DIR / fname
            if fpath.exists():
                try:
                    chunks.append(fpath.read_text(encoding="utf-8"))
                except Exception:
                    pass
    return "\n\n---\n\n".join(chunks) if chunks else ""


def _format_factfind(factfind_snapshot: dict) -> str:
    if not factfind_snapshot:
        return "No client facts on record."
    return "\n".join(f"  {path}: {value}" for path, value in factfind_snapshot.items())


def _format_step_results(step_results: list[dict]) -> str:
    if not step_results:
        return "(no tool steps were executed)"
    lines: list[str] = []
    for r in step_results:
        status = r.get("status", "unknown")
        tool = r.get("tool_name", "unknown")
        step_id = r.get("step_id", "?")
        if status in ("completed", "cached") and r.get("output"):
            output_str = json.dumps(r["output"], indent=2)
            if len(output_str) > 3000:
                output_str = output_str[:3000] + "\n... (truncated)"
            lines.append(f"[{step_id} — {tool}] STATUS: {status}\n{output_str}")
        elif status == "skipped":
            lines.append(f"[{step_id} — {tool}] STATUS: skipped ({r.get('error', '')})")
        else:
            lines.append(f"[{step_id} — {tool}] STATUS: {status} ERROR: {r.get('error', 'unknown')}")
    return "\n\n".join(lines)


def _format_recent(recent_messages: list[dict], n: int = 4) -> str:
    tail = recent_messages[-n:] if len(recent_messages) > n else recent_messages
    if not tail:
        return "(no prior conversation)"
    return "\n".join(
        f"  {m.get('role', 'unknown').upper()}: {str(m.get('content', ''))[:400]}"
        for m in tail
    )


_SYSTEM_WITH_TOOLS = """\
You are an expert insurance financial adviser. You have just run one or more \
analysis tools on behalf of a client and must now deliver a clear, professional \
summary of the findings.

Guidelines:
- Integrate results from ALL completed steps into a single coherent response.
- Use plain English — no raw JSON or code blocks.
- Reference specific numbers (sums insured, premiums, waiting periods) where available.
- Note any steps that failed or were skipped and explain implications briefly.
- End with clear, actionable next steps.
- Format using markdown headings and bullet points for readability.

PRODUCT KNOWLEDGE (use as background):
{knowledge}
"""

_SYSTEM_DIRECT = """\
You are an expert insurance financial adviser in Australia. Answer the client's \
question clearly and professionally. Use the client facts and conversation history \
as context. Format your response with markdown headings and bullets where helpful.
"""

_HUMAN_WITH_TOOLS = """\
## Client Facts
{known_facts}

## Tool Execution Results
{step_results}

## Client's Original Request
{user_message}

Write the adviser summary now.
"""

_HUMAN_DIRECT = """\
## Client Facts
{known_facts}

## Recent Conversation
{recent_messages}

## Document Context
{document_context}

## Client's Question
{user_message}

Answer now.
"""


def _build_fallback_response(step_results: list[dict], user_message: str) -> str:
    completed = [r for r in step_results if r.get("status") in ("completed", "cached")]
    failed = [r for r in step_results if r.get("status") == "failed"]
    parts = [f"## Analysis Results\n\nI've completed the analysis for: *{user_message}*\n"]
    if completed:
        parts.append(f"**Completed:** {', '.join(r['tool_name'] for r in completed)}")
    if failed:
        parts.append(f"**Could not complete:** {', '.join(r['tool_name'] + ' — ' + (r.get('error') or '') for r in failed)}")
    parts.append("\nPlease review the data cards above for detailed results.")
    return "\n".join(parts)


async def workspace_summarize(state: WorkspaceState) -> dict:
    """
    Synthesise all step results into a natural-language adviser response.
    """
    step_results: list[dict] = state.get("step_results", [])
    tool_plan: list[dict] = state.get("tool_plan", [])
    user_message = state.get("user_message", "")
    factfind_snapshot = state.get("factfind_snapshot", {})
    recent_messages = state.get("recent_messages", [])
    doc_context = state.get("extracted_document_context") or "(none)"
    data_cards = state.get("data_cards", [])

    known_facts = _format_factfind(factfind_snapshot)

    tool_steps_ran = any(
        r.get("status") in ("completed", "cached") and r.get("tool_name") != "direct_response"
        for r in step_results
    )
    tool_names_used = [s["tool_name"] for s in tool_plan if s.get("tool_name") != "direct_response"]

    try:
        llm = get_chat_model(temperature=0.3)
        if tool_steps_ran:
            knowledge = _load_knowledge(tool_names_used)
            system_msg = SystemMessage(content=_SYSTEM_WITH_TOOLS.format(knowledge=knowledge or "(none)"))
            human_msg = HumanMessage(content=_HUMAN_WITH_TOOLS.format(
                known_facts=known_facts,
                step_results=_format_step_results(step_results),
                user_message=user_message,
            ))
        else:
            system_msg = SystemMessage(content=_SYSTEM_DIRECT)
            human_msg = HumanMessage(content=_HUMAN_DIRECT.format(
                known_facts=known_facts,
                recent_messages=_format_recent(recent_messages),
                document_context=str(doc_context)[:800],
                user_message=user_message,
            ))

        response = await llm.ainvoke([system_msg, human_msg])
        final_response = response.content if hasattr(response, "content") else str(response)

    except Exception as exc:
        logger.exception("workspace_summarize LLM call failed: %s", exc)
        final_response = _build_fallback_response(step_results, user_message)

    structured_payload = {
        "type": "workspace_run",
        "plan_steps": tool_plan,
        "step_results": [
            {"step_id": r["step_id"], "tool_name": r["tool_name"],
             "description": r.get("description", ""), "status": r["status"],
             "error": r.get("error"), "cache_source_run_id": r.get("cache_source_run_id")}
            for r in step_results
        ],
        "data_cards": data_cards,
    }

    logger.info(
        "workspace_summarize: %d chars response, %d data cards",
        len(final_response), len(data_cards),
    )

    return {"final_response": final_response, "structured_response_payload": structured_payload}
