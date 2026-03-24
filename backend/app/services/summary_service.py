"""
summary_service.py — Rolling conversation summary for structured memory.

The summary is a compact ~100-word plain-English snapshot of the known client
profile and the current conversation topic. It is:
  - Injected into the compose_response system prompt for long conversations
    (avoiding the need to include all recent messages).
  - Stored in conversation_memory.summary_memory.
  - Refreshed only every SUMMARY_REFRESH_TURNS turns (not every turn) to
    minimise LLM token spend.

When to refresh:
  - turn_count reaches SUMMARY_REFRESH_TURNS for the first time
  - turn_count - turn_count_at_summary >= SUMMARY_REFRESH_TURNS
  - Called explicitly (e.g. topic change detection — future enhancement)

Summary content:
  - Client demographics (age, gender, occupation, employment)
  - Financial snapshot (income, super, mortgage, assets)
  - Insurance snapshot (existing policies, cover types)
  - Current conversation topic / most recent question
"""

import logging

from app.core.llm import get_chat_model_fresh
from langchain_core.messages import HumanMessage, SystemMessage

logger = logging.getLogger(__name__)

SUMMARY_REFRESH_TURNS = 15  # refresh summary every N turns


def should_refresh_summary(memory: dict) -> bool:
    """Return True if the summary should be regenerated this turn."""
    turn_count = memory.get("turn_count", 0)
    if turn_count < SUMMARY_REFRESH_TURNS:
        return False
    last_at = memory.get("summary_memory", {}).get("turn_count_at_summary", 0)
    return (turn_count - last_at) >= SUMMARY_REFRESH_TURNS


async def generate_summary(
    memory: dict,
    recent_messages: list[dict],
) -> str:
    """
    Generate a compact plain-English summary of the client profile and
    current conversation topic.

    Args:
        memory:          The current conversation_memory document.
        recent_messages: Last N messages for conversational context.

    Returns:
        A ~100-word summary string, or empty string on failure.
    """
    facts = memory.get("client_facts") or {}
    p = facts.get("personal") or {}
    f = facts.get("financial") or {}
    ins = facts.get("insurance") or {}

    # Build a structured fact dump for the summary prompt
    fact_lines = []
    if p.get("age"):
        fact_lines.append(f"Age: {p['age']}")
    if p.get("occupation"):
        fact_lines.append(f"Occupation: {p['occupation']}")
    if p.get("employment_status"):
        fact_lines.append(f"Employment: {p['employment_status']}")
    if p.get("dependants") is not None:
        fact_lines.append(f"Dependants: {p['dependants']}")
    if p.get("is_smoker") is not None:
        fact_lines.append(f"Smoker: {p['is_smoker']}")
    if f.get("annual_gross_income"):
        fact_lines.append(f"Annual income: ${f['annual_gross_income']:,.0f}")
    if f.get("super_balance"):
        fact_lines.append(f"Super balance: ${f['super_balance']:,.0f}")
    if f.get("fund_name"):
        fact_lines.append(f"Super fund: {f['fund_name']}")
    if f.get("mortgage_balance"):
        fact_lines.append(f"Mortgage: ${f['mortgage_balance']:,.0f}")
    if f.get("liquid_assets"):
        fact_lines.append(f"Liquid assets: ${f['liquid_assets']:,.0f}")
    if ins.get("insurer_name"):
        fact_lines.append(f"Insurer: {ins['insurer_name']}")
    if ins.get("life_sum_insured"):
        fact_lines.append(f"Life cover: ${ins['life_sum_insured']:,.0f}")
    if ins.get("tpd_sum_insured"):
        fact_lines.append(f"TPD cover: ${ins['tpd_sum_insured']:,.0f}")
    if ins.get("ip_monthly_benefit"):
        fact_lines.append(f"IP monthly benefit: ${ins['ip_monthly_benefit']:,.0f}")
    if ins.get("annual_premium"):
        fact_lines.append(f"Annual premium: ${ins['annual_premium']:,.0f}")

    known_facts_str = "\n".join(fact_lines) if fact_lines else "No facts recorded yet."

    # Recent messages for topic context (last 4)
    recent_str = "\n".join(
        f"{m['role'].upper()}: {m['content']}"
        for m in recent_messages[-4:]
    )

    system = (
        "You are summarising an insurance advisory chat session for an AI assistant's memory. "
        "Write a single compact paragraph (~80-100 words) covering: "
        "1) client demographics, 2) financial snapshot, 3) insurance snapshot, "
        "4) what is currently being discussed. "
        "Use plain factual language. No headings. No bullet points. No interpretation."
    )
    user_content = (
        f"Known client facts:\n{known_facts_str}\n\n"
        f"Recent conversation:\n{recent_str}\n\n"
        "Write the compact session summary:"
    )

    model = get_chat_model_fresh(temperature=0.1)
    try:
        response = await model.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=user_content),
        ])
        summary = response.content.strip()
        logger.debug("summary_service: generated %d-char summary", len(summary))
        return summary
    except Exception as exc:
        logger.warning("summary_service: generation failed: %s", exc)
        return ""
