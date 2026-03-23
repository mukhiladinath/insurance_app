"""
compose_response.py — Node: compose the final assistant response.

If a tool was executed:
  - Summarise the tool result using the LLM for natural language explanation.
  - Attach the structured tool result payload for the frontend to render.

If no tool was executed (direct response or error):
  - Use the LLM to compose a helpful contextual response.
"""

import logging
import json
from app.agents.state import AgentState
from app.core.constants import Intent
from app.core.llm import get_chat_model

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are an expert insurance adviser AI assistant for financial advisers in Australia.
You help advisers analyse insurance scenarios, interpret tool results, and communicate clearly.
Always be professional, precise, and grounded in the facts provided.
Do NOT invent figures, legal rules, or outcomes. If uncertain, say so.
Keep responses concise and well-structured.
Use plain Australian English."""


def _build_tool_summary_prompt(tool_name: str, tool_result: dict, user_message: str) -> str:
    """Build a prompt to summarise a tool result in natural language."""
    # Extract key fields for the summary (keep it concise for the LLM)
    summary_data: dict = {}

    missing_questions = tool_result.get("missing_info_questions", [])
    blocking_questions = [q for q in missing_questions if q.get("blocking")]
    nonblocking_questions = [q for q in missing_questions if not q.get("blocking")]

    if tool_name == "purchase_retain_life_insurance_in_super":
        summary_data = {
            "legal_status": tool_result.get("legal_status"),
            "legal_reasons": tool_result.get("legal_reasons", [])[:3],
            "advice_mode": tool_result.get("advice_mode"),
            "placement_recommendation": tool_result.get("placement_assessment", {}).get("recommendation"),
            "placement_reasoning": tool_result.get("placement_assessment", {}).get("reasoning", [])[:3],
            "beneficiary_tax_risk": tool_result.get("beneficiary_tax_risk", {}).get("risk_level"),
            "top_actions": [a["action"] for a in tool_result.get("member_actions", [])[:2]],
            "blocking_questions": [q["question"] for q in blocking_questions],
            "optional_questions": [q["question"] for q in nonblocking_questions],
        }
    elif tool_name == "purchase_retain_life_tpd_policy":
        rec = tool_result.get("recommendation", {})
        summary_data = {
            "recommendation_type": rec.get("type"),
            "summary": rec.get("summary"),
            "reasons": rec.get("reasons", [])[:3],
            "risks": rec.get("risks", [])[:3],
            "life_shortfall": rec.get("life_need", {}).get("shortfall_level") if rec.get("life_need") else None,
            "tpd_shortfall": rec.get("tpd_need", {}).get("shortfall_level") if rec.get("tpd_need") else None,
            "affordability": rec.get("affordability", {}).get("assessment"),
            "underwriting_risk": rec.get("underwriting_risk", {}).get("overall_risk"),
            "top_actions": [a["action"] for a in rec.get("required_actions", [])[:2]],
            "blocking_questions": [q["question"] for q in blocking_questions],
            "optional_questions": [q["question"] for q in nonblocking_questions],
        }
    elif tool_name == "purchase_retain_income_protection_policy":
        rec = tool_result.get("recommendation", {})
        bn  = rec.get("benefit_need", {})
        wp  = rec.get("waiting_period", {})
        bp  = rec.get("benefit_period", {})
        aff = rec.get("affordability", {})
        uw  = rec.get("underwriting_risk", {})
        summary_data = {
            "recommendation_type":           rec.get("type"),
            "summary":                        rec.get("summary"),
            "reasons":                        rec.get("reasons", [])[:3],
            "risks":                          rec.get("risks", [])[:3],
            "income_shortfall_level":         bn.get("shortfall_level"),
            "monthly_gap":                    bn.get("monthly_gap"),
            "recommended_monthly_benefit":    bn.get("recommended_monthly_benefit"),
            "recommended_waiting_weeks":      wp.get("recommended_waiting_period_weeks"),
            "waiting_period_comparison":      wp.get("comparison"),
            "recommended_benefit_period":     bp.get("recommended_benefit_period_label"),
            "step_down_risk":                 bp.get("step_down_risk"),
            "affordability_band":             aff.get("affordability_band"),
            "underwriting_risk":              uw.get("overall_risk"),
            "advice_mode":                    tool_result.get("advice_mode"),
            "top_actions":                    [a["action"] for a in rec.get("required_actions", [])[:2]],
            "blocking_questions":             [q["question"] for q in blocking_questions],
            "optional_questions":             [q["question"] for q in nonblocking_questions],
        }
    elif tool_name == "purchase_retain_ip_in_super":
        rec  = tool_result.get("recommendation", {})
        tax  = tool_result.get("tax_comparison", {})
        drag = tool_result.get("retirement_drag", {})
        bn   = tool_result.get("benefit_need", {})
        pa   = tool_result.get("placement_assessment", {})
        wt   = tool_result.get("work_test", {})
        port = tool_result.get("portability", {})
        summary_data = {
            "recommendation_type":          rec.get("type"),
            "summary":                      rec.get("summary"),
            "reasons":                      rec.get("reasons", [])[:3],
            "risks":                        rec.get("risks", [])[:3],
            "legal_status":                 tool_result.get("legal_status"),
            "legal_reasons":                tool_result.get("legal_reasons", [])[:2],
            "work_test_passes":             wt.get("passes"),
            "work_test_status":             wt.get("employment_status"),
            "placement_recommendation":     pa.get("recommendation"),
            "inside_score":                 pa.get("inside_score"),
            "outside_score":                pa.get("outside_score"),
            "tax_favours_outside":          tax.get("tax_favours_outside"),
            "tax_summary":                  tax.get("tax_summary"),
            "retirement_drag_estimate":     drag.get("estimated_balance_reduction") if drag else None,
            "monthly_shortfall":            bn.get("monthly_shortfall") if isinstance(bn, dict) else None,
            "portability_status":           port.get("status"),
            "advice_mode":                  tool_result.get("advice_mode"),
            "top_actions":                  [a["action"] for a in tool_result.get("member_actions", [])[:2]],
            "blocking_questions":           [q["question"] for q in blocking_questions],
            "optional_questions":           [q["question"] for q in nonblocking_questions],
        }

    has_blocking = bool(summary_data.get("blocking_questions"))
    missing_instruction = ""
    if has_blocking:
        missing_instruction = (
            "\n- IMPORTANT: blocking_questions lists required information that MUST be provided "
            "before a recommendation can be given. After summarising what you know, explicitly "
            "ask the user for each blocking question, numbered (1. 2. 3. …). "
            "Make it clear you need these answers to complete the analysis."
        )
    elif summary_data.get("optional_questions"):
        missing_instruction = (
            "\n- optional_questions lists data that would improve the analysis. "
            "Mention these as optional follow-up items."
        )

    return f"""The user asked: "{user_message}"

The tool '{tool_name}' returned this structured result:
{json.dumps(summary_data, indent=2)}

Write a clear, professional response for a financial adviser.
- Lead with the key outcome (legal status / recommendation type).
- Explain the main reasons in 2-3 sentences.
- Note the top action items if any.{missing_instruction}
- Keep it under 250 words.
- Do NOT make up any numbers not in the data above."""


async def compose_response(state: AgentState) -> dict:
    """Compose the final natural language response and structured payload."""
    intent = state.get("intent", Intent.DIRECT_RESPONSE)
    user_message = state.get("user_message", "")
    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    selected_tool = state.get("selected_tool")
    recent_messages = state.get("recent_messages", [])

    try:
        model = get_chat_model(temperature=0.3)

        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        # Build message history for context
        lc_messages = [SystemMessage(content=_SYSTEM_PROMPT)]
        for m in recent_messages[-6:]:  # last 6 messages for context
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                lc_messages.append(AIMessage(content=m["content"]))

        # Determine what to compose
        if tool_error:
            # Tool failed — acknowledge and ask for the specific data needed
            prompt = (
                f"The user asked: \"{user_message}\"\n\n"
                f"The tool encountered an error: {tool_error}\n\n"
                "Acknowledge this professionally. "
                "If the error mentions missing fields, list exactly which fields are needed, numbered. "
                "Ask the user to provide them so the analysis can be re-run."
            )
            lc_messages.append(HumanMessage(content=prompt))

        elif tool_result and selected_tool:
            # Tool succeeded — summarise in natural language
            prompt = _build_tool_summary_prompt(selected_tool, tool_result, user_message)
            lc_messages.append(HumanMessage(content=prompt))

        else:
            # Direct response
            lc_messages.append(HumanMessage(content=user_message))

        response = await model.ainvoke(lc_messages)
        final_response = response.content.strip()

        # Build structured payload if tool ran
        structured_payload: dict | None = None
        if tool_result and selected_tool:
            structured_payload = {
                "tool_name": selected_tool,
                "tool_result": tool_result,
                "tool_warnings": state.get("tool_warnings", []),
            }

        return {
            "final_response": final_response,
            "structured_response_payload": structured_payload,
        }

    except Exception as exc:
        logger.exception("compose_response error: %s", exc)
        fallback = (
            "I encountered an issue generating a response. "
            "The tool analysis may have completed successfully — please check the structured result."
            if tool_result else
            "I'm having trouble generating a response right now. Please try again."
        )
        return {
            "final_response": fallback,
            "structured_response_payload": {"tool_name": selected_tool, "tool_result": tool_result} if tool_result else None,
        }
