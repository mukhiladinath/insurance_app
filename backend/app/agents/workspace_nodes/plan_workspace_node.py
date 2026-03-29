"""
plan_workspace_node.py — Workspace-aware planning node.

Adapted from orchestrator_nodes/plan_node.py with these key changes:
  - Reads factfind_snapshot (flat dict) instead of client_memory
  - Reads ai_context_hierarchy for assumptions and advisory notes
  - Outputs dependency_graph alongside tool_plan
  - missing_fields is a list of dicts (not just dot-paths)

State reads:  user_message, factfind_snapshot, ai_context_hierarchy,
              recent_messages, extracted_document_context, advisory_notes, scratch_pad
State writes: tool_plan, dependency_graph, clarification_needed,
              clarification_question, missing_fields, final_response (if clarification)
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.workspace_state import WorkspaceState
from app.core.llm import get_chat_model
from app.tools.registry import list_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool catalog (same hints as the original plan_node)
# ---------------------------------------------------------------------------

_TOOL_INPUT_HINTS: dict[str, str] = {
    "purchase_retain_life_insurance_in_super": (
        "Key inputs: member.age, member.date_of_birth, member.smoker, member.account_inactive,\n"
        "  member.balance_below_6k, member.under_25, member.dependants, fund.balance, fund.type,\n"
        "  product.cover_types, adviceContext.mortgage_balance, adviceContext.annual_income\n"
        "Key outputs: legal_status, placement_assessment.recommendation, coverage_needs.recommended_sum_insured"
    ),
    "purchase_retain_life_tpd_policy": (
        "Key inputs: client_age, annual_income, super_balance, dependants, mortgage_balance,\n"
        "  existing_life_cover, existing_tpd_cover, smoker, occupation_class, replacement_policy,\n"
        "  current_insurer, fund_type\n"
        "Key outputs: recommendation.type, life_need.recommended_sum, tpd_need.recommended_sum"
    ),
    "purchase_retain_income_protection_policy": (
        "Key inputs: client_age, annual_income, occupation_class, waiting_period_days,\n"
        "  benefit_period, monthly_expenses, existing_ip_cover, smoker\n"
        "Key outputs: recommendation.waiting_period, recommendation.benefit_period, monthly_benefit_need"
    ),
    "purchase_retain_ip_in_super": (
        "Key inputs: client_age, annual_income, super_balance, fund_type, occupation_class,\n"
        "  waiting_period_days, benefit_period, monthly_expenses\n"
        "Key outputs: sis_compliant, recommendation.type, benefit_need"
    ),
    "purchase_retain_trauma_ci_policy": (
        "Key inputs: client_age, annual_income, mortgage_balance, dependants, smoker,\n"
        "  sum_insured, existing_trauma_cover\n"
        "Key outputs: recommendation.type, recommended_sum_insured, affordability_assessment"
    ),
    "tpd_policy_assessment": (
        "Key inputs: client_age, occupation_class, existing_tpd_sum_insured, annual_income,\n"
        "  debts, super_balance, tpd_definition, fund_type\n"
        "Key outputs: adequacy_verdict, gap_analysis.shortfall, recommendation"
    ),
    "purchase_retain_tpd_in_super": (
        "Key inputs: client_age, super_balance, fund_type, occupation_class, annual_income,\n"
        "  debts, existing_tpd_cover\n"
        "Key outputs: sis_compliant, legal_status, recommended_sum_insured"
    ),
}


def _build_tool_catalog() -> str:
    tools = list_tools()
    lines: list[str] = []
    for t in tools:
        hints = _TOOL_INPUT_HINTS.get(t.name, "")
        lines.append(f"TOOL: {t.name}\nPURPOSE: {t.description}\n{hints}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Context formatters
# ---------------------------------------------------------------------------

def _format_factfind(factfind_snapshot: dict) -> str:
    if not factfind_snapshot:
        return "No client facts on record."
    return "\n".join(f"  {path}: {value}" for path, value in factfind_snapshot.items())


def _format_advisory(advisory_notes: dict) -> str:
    if not advisory_notes:
        return "(no prior analyses)"
    return "\n".join(
        f"  [{tool}]: verdict={note.get('verdict')} — {note.get('recommendation', '')} "
        f"(analysed {str(note.get('analysed_at', ''))[:10]})"
        for tool, note in advisory_notes.items()
    )


def _format_assumptions(ai_context_hierarchy: dict) -> str:
    assumptions = ai_context_hierarchy.get("assumptions", {}).get("data", {})
    if not assumptions:
        return "(default assumptions)"
    return "\n".join(f"  {k}: {v}" for k, v in assumptions.items())


def _format_recent(recent_messages: list[dict], n: int = 6) -> str:
    tail = recent_messages[-n:] if len(recent_messages) > n else recent_messages
    if not tail:
        return "(no prior conversation)"
    return "\n".join(
        f"  {m.get('role', 'unknown').upper()}: {str(m.get('content', ''))[:300]}"
        for m in tail
    )


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_PLANNING_SYSTEM = """\
You are an insurance advisory planning agent. Analyse the request and produce a \
structured JSON execution plan.

## AVAILABLE TOOLS
{tool_catalog}

## RULES
1. Extract inputs directly from CLIENT FACTS below. Do not ask for information already known.
2. NEVER use "direct_response" when the user asks for insurance analysis, a recommendation, \
   coverage needs, adequacy assessment, or any calculation — even if some inputs are missing.
3. Use "direct_response" ONLY for: greetings, purely factual questions (e.g. "what is TPD?"), \
   or requests that provably require no calculation whatsoever.
4. If CLIENT FACTS is empty or missing fields required by the relevant tool(s), you MUST set \
   clarification_needed=true. Ask for ALL required fields in one friendly, conversational \
   intake message. Do NOT fall back to direct_response.
5. When you have enough facts, choose the most appropriate tool(s) and build the plan.
6. Order steps logically. Use "depends_on": ["step_X"] when a step needs another step's output. \
   Use {{{{step_N.field_path}}}} syntax for chaining values between steps.
7. When clarification_needed=true, list EVERY missing field in missing_fields as objects:
   {{"field_path": "personal.age", "label": "Client Age", "section": "personal", "required": true}}
8. Always return valid JSON — no markdown fences, no prose outside the JSON.

## MINIMUM FIELDS FOR INSURANCE ANALYSIS
If the user requests any insurance analysis and these fields are absent, ask for them:
- personal.age (or personal.date_of_birth)
- personal.gender
- personal.smoker
- personal.occupation
- financial.annual_income
- financial.super_balance
- financial.dependants
- financial.mortgage_balance

## OUTPUT SCHEMA
{{
  "clarification_needed": bool,
  "clarification_question": "string | null",
  "missing_fields": [{{"field_path": "...", "label": "...", "section": "...", "required": true}}],
  "steps": [
    {{
      "step_id": "step_1",
      "tool_name": "tool_name_or_direct_response",
      "description": "what this step does",
      "inputs": {{}},
      "depends_on": [],
      "rationale": "why this step is needed"
    }}
  ]
}}
"""

_PLANNING_HUMAN = """\
## CLIENT FACTS (confirmed and inferred)
{known_facts}

{empty_factfind_notice}\
## ASSUMPTIONS
{assumptions}

## PRIOR ADVISORY CONCLUSIONS
{advisory_notes}

## AGENT WORKING NOTES
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
# Helpers
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    raise ValueError(f"Could not extract JSON from planning LLM output: {text[:300]}")


def _fallback_plan(factfind_snapshot: dict, user_message: str) -> list[dict]:
    # Even on LLM failure, don't silently use direct_response for analysis requests
    forced = _force_intake_clarification(factfind_snapshot, user_message)
    if forced:
        return []   # clarification will be set separately
    return [{
        "step_id": "step_1",
        "tool_name": "direct_response",
        "description": "Respond directly to the user's question",
        "inputs": {},
        "depends_on": [],
        "rationale": "Fallback: planning LLM unavailable or returned invalid output",
    }]


def _build_dependency_graph(steps: list[dict]) -> dict:
    """Build a reverse dependency map: step_id → list of steps that depend on it."""
    graph: dict[str, list[str]] = {}
    for step in steps:
        for dep in step.get("depends_on", []):
            graph.setdefault(dep, []).append(step["step_id"])
    return graph


# Fields we need before any insurance tool can run
_INTAKE_FIELDS: list[dict] = [
    {"field_path": "personal.age",             "label": "Age",                    "section": "personal",  "required": True},
    {"field_path": "personal.date_of_birth",   "label": "Date of Birth",           "section": "personal",  "required": True},
    {"field_path": "personal.gender",          "label": "Gender",                  "section": "personal",  "required": True},
    {"field_path": "personal.smoker",          "label": "Smoker",                  "section": "personal",  "required": True},
    {"field_path": "personal.occupation",      "label": "Occupation",              "section": "personal",  "required": True},
    {"field_path": "financial.annual_income",  "label": "Annual Income",           "section": "financial", "required": True},
    {"field_path": "financial.super_balance",  "label": "Superannuation Balance",  "section": "financial", "required": True},
    {"field_path": "financial.dependants",     "label": "Number of Dependants",    "section": "financial", "required": True},
    {"field_path": "financial.mortgage_balance","label": "Mortgage Balance",       "section": "financial", "required": True},
]

_INTAKE_QUESTION = (
    "To run a proper insurance analysis I need a few details about your client. "
    "Please provide:\n\n"
    "- **Age** (or date of birth)\n"
    "- **Gender**\n"
    "- **Smoker** (yes / no)\n"
    "- **Occupation**\n"
    "- **Annual income**\n"
    "- **Superannuation balance**\n"
    "- **Number of dependants**\n"
    "- **Mortgage / outstanding debt balance** (enter 0 if none)\n"
)

# Phrases that clearly signal an analysis / tool-run request
_ANALYSIS_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(analys|assess|recommend|review|calculat|check|run|look at|advise)\b",
        r"\b(life|tpd|income.?protect|trauma|super|insurance|cover)\b",
        r"\b(how much|what.*need|should.*have|is.*adequate|enough cover)\b",
    ]
]


def _is_analysis_request(message: str) -> bool:
    return any(p.search(message) for p in _ANALYSIS_PATTERNS)


def _force_intake_clarification(factfind_snapshot: dict, user_message: str) -> dict | None:
    """
    If the factfind is too sparse to run any tool AND the user is asking for analysis,
    return a pre-built clarification response without calling the LLM.
    """
    # Check which intake fields are already present
    missing = [
        f for f in _INTAKE_FIELDS
        if not factfind_snapshot.get(f["field_path"])
    ]
    # If at least half the intake fields are missing AND this looks like an analysis request
    if len(missing) >= len(_INTAKE_FIELDS) // 2 and _is_analysis_request(user_message):
        return {
            "clarification_needed": True,
            "clarification_question": _INTAKE_QUESTION,
            "missing_fields": missing,
            "steps": [],
        }
    return None


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

async def plan_workspace(state: WorkspaceState) -> dict:
    """
    LLM-based planning node for workspace runs.

    Reads:  user_message, factfind_snapshot, ai_context_hierarchy,
            recent_messages, extracted_document_context, advisory_notes, scratch_pad
    Writes: tool_plan, dependency_graph, clarification_needed,
            clarification_question, missing_fields, final_response (if clarification)
    """
    user_message = state.get("user_message", "")
    factfind_snapshot = state.get("factfind_snapshot", {})
    ai_context_hierarchy = state.get("ai_context_hierarchy", {})
    recent_messages = state.get("recent_messages", [])
    doc_context = state.get("extracted_document_context") or "(none)"
    advisory_notes = state.get("advisory_notes", {})
    scratch_pad = state.get("scratch_pad", [])

    # Fast-path: if factfind is too sparse to run tools, skip the LLM and ask for intake
    forced = _force_intake_clarification(factfind_snapshot, user_message)
    if forced:
        logger.info("plan_workspace: forcing intake clarification (factfind too sparse) for client=%s", state.get("client_id"))
        return {
            "tool_plan": [],
            "dependency_graph": {},
            "clarification_needed": True,
            "clarification_question": forced["clarification_question"],
            "missing_fields": forced["missing_fields"],
            "final_response": forced["clarification_question"],
        }

    known_facts = _format_factfind(factfind_snapshot)
    advisory_str = _format_advisory(advisory_notes)
    assumption_str = _format_assumptions(ai_context_hierarchy)
    recent_str = _format_recent(recent_messages)
    scratch_str = (
        "\n".join(f"  [{e.get('category','note')}] {e.get('content','')}" for e in scratch_pad[-5:])
        if scratch_pad else "(empty)"
    )

    # Inject a hard notice when the factfind is empty so the LLM cannot ignore it
    is_factfind_empty = len(factfind_snapshot) < 3
    empty_factfind_notice = (
        "## *** IMPORTANT ***\n"
        "CLIENT FACTS IS EMPTY. You MUST set clarification_needed=true and ask for all "
        "required fields before any analysis can proceed. Do NOT use direct_response.\n\n"
        if is_factfind_empty else ""
    )

    system_prompt = _PLANNING_SYSTEM.format(tool_catalog=_build_tool_catalog())
    human_prompt = _PLANNING_HUMAN.format(
        known_facts=known_facts,
        empty_factfind_notice=empty_factfind_notice,
        assumptions=assumption_str,
        advisory_notes=advisory_str,
        scratch_pad=scratch_str,
        recent_messages=recent_str,
        document_context=str(doc_context)[:1000],
        user_message=user_message,
    )

    try:
        llm = get_chat_model(temperature=0.1)
        response = await llm.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=human_prompt),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        plan_data = _extract_json(raw)

        clarification_needed: bool = bool(plan_data.get("clarification_needed", False))
        clarification_question: str | None = plan_data.get("clarification_question")

        # Normalise missing_fields — accept both list-of-dicts and list-of-strings
        raw_missing = plan_data.get("missing_fields", [])
        missing_fields: list[dict] = []
        for item in raw_missing:
            if isinstance(item, dict):
                missing_fields.append({
                    "field_path": item.get("field_path", item.get("path", "")),
                    "label": item.get("label", item.get("field_path", "")),
                    "section": item.get("section", ""),
                    "required": item.get("required", True),
                })
            elif isinstance(item, str):
                section = item.split(".")[0] if "." in item else ""
                missing_fields.append({
                    "field_path": item,
                    "label": item.replace(".", " ").replace("_", " ").title(),
                    "section": section,
                    "required": True,
                })

        steps: list[dict] = plan_data.get("steps", [])
        valid_steps = [
            {
                "step_id": s["step_id"],
                "tool_name": s["tool_name"],
                "description": s.get("description", ""),
                "inputs": s.get("inputs", {}),
                "depends_on": s.get("depends_on", []),
                "rationale": s.get("rationale", ""),
            }
            for s in steps
            if "step_id" in s and "tool_name" in s
        ]
        if not valid_steps:
            valid_steps = _fallback_plan(factfind_snapshot, user_message)
            clarification_needed = False

        dependency_graph = _build_dependency_graph(valid_steps)

        logger.info(
            "plan_workspace: %d step(s), clarification_needed=%s for client=%s",
            len(valid_steps), clarification_needed, state.get("client_id"),
        )

        update: dict[str, Any] = {
            "tool_plan": valid_steps,
            "dependency_graph": dependency_graph,
            "clarification_needed": clarification_needed,
            "clarification_question": clarification_question,
            "missing_fields": missing_fields,
        }

        if clarification_needed and clarification_question:
            update["final_response"] = clarification_question

        return update

    except Exception as exc:
        logger.exception("plan_workspace failed: %s", exc)
        fallback = _force_intake_clarification(factfind_snapshot, user_message)
        if fallback:
            return {
                "tool_plan": [],
                "dependency_graph": {},
                "clarification_needed": True,
                "clarification_question": fallback["clarification_question"],
                "missing_fields": fallback["missing_fields"],
                "final_response": fallback["clarification_question"],
                "errors": state.get("errors", []) + [f"Planning error: {exc}"],
            }
        return {
            "tool_plan": _fallback_plan(factfind_snapshot, user_message),
            "dependency_graph": {},
            "clarification_needed": False,
            "clarification_question": None,
            "missing_fields": [],
            "errors": state.get("errors", []) + [f"Planning error: {exc}"],
        }
