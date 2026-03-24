"""
soa_service.py — SOA section generation from conversation memory + history.

Approach:
  - Load client facts from conversation memory (canonical schema)
  - Use recent messages as the conversation context (includes tool output summaries)
  - Call LLM with the 7 SOA templates as system context
  - LLM identifies which templates apply, fills each section, marks missing values
  - Returns structured sections + any missing questions

Missing value format (inline): [[MISSING: question text]]
Missing questions are also returned as a separate list for the panel UI.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SOA template reference for the LLM
# ---------------------------------------------------------------------------

_SOA_TEMPLATES_PROMPT = """\
You are an Australian financial adviser SOA writer. Generate insurance strategy sections
for a formal Statement of Advice using the templates below.

=== 7 SOA INSURANCE TEMPLATES ===

TEMPLATE 1 — Purchase/Retain Life Insurance Policy in Superannuation
Our Recommendation: State the life cover amount inside super, features (premium relief / accidental death / top-up cover), premium type (stepped/level). Include super rollover for premium if relevant.
Why Appropriate: Life pays lump sum on death/terminal illness; inside super is tax-effective, premiums auto-deducted, does not impact disposable income; binding death nomination controls proceeds.
What to Consider: Premiums reduce super balance; suicide exclusion on new cover; trustee discretion if no nomination; cooling-off period; review regularly.
More Information: Personal Insurances; Life Insurance; Superannuation Death Benefits flyers. PDS dated [date].

TEMPLATE 2 — Purchase/Retain Life & TPD Policy (outside super)
Our Recommendation: Life cover amount + linked/standalone TPD amount. TPD features (any/own occupation/ADL/premium relief/death buy back). Premium type (stepped/level/hybrid).
Why Appropriate: TPD pays lump sum on permanent disablement; outside super = no SIS release rules, tax-free proceeds, not counted toward Transfer Balance Cap; linked cover is cost-effective.
What to Consider: Premiums from disposable income; linked cover reduces life cover after TPD claim; cooling-off period; review regularly.
More Information: Personal Insurances; Life Insurance; TPD flyers. PDS dated [date].

TEMPLATE 3 — Purchase/Retain Life & TPD Insurance Policy in Superannuation
Our Recommendation: Life cover amount + linked TPD amount inside super. Features for each. Premium type (stepped/level). Include super rollover if relevant.
Why Appropriate: Combined life + TPD in super; tax-effective; automatic premium deduction; super-linked TPD improves release of proceeds.
What to Consider: Premiums reduce super balance; SIS release rules affect TPD access; linked cover reduces life after TPD claim; trustee discretion without binding nomination; review regularly.
More Information: Personal Insurances; Life Insurance; TPD flyers. PDS dated [date].

TEMPLATE 4 — Purchase/Retain TPD Insurance Policy (outside super)
Our Recommendation: TPD cover amount. TPD definition (any/own occupation/ADL). Linked or standalone. Premium type.
Why Appropriate: TPD lump sum on total/permanent disablement; outside super = tax-free, no SIS dependency; complements income protection.
What to Consider: Premiums from disposable income; waiting period may apply; own/any occupation definition matters; review regularly.
More Information: Personal Insurances; TPD flyers. PDS dated [date].

TEMPLATE 5 — Purchase/Retain Income Protection Policy (outside super)
Our Recommendation: Monthly benefit amount, waiting period (weeks), benefit period (e.g. to age 65). Agreed or indemnity value. Features (increasing claim, super top-up, indexation). Standalone or linked. Premium type.
Why Appropriate: Replaces up to 75% of income if unable to work; covers living costs and debt; premiums outside super may be tax-deductible; waiting period matches available sick leave/liquid assets.
What to Consider: Benefits are assessable income; waiting period must be self-funded; agreed vs indemnity value implications; review regularly; cooling-off period.
More Information: Personal Insurances; Income Protection flyers. PDS dated [date].

TEMPLATE 6 — Purchase/Retain Income Protection Policy in Superannuation
Our Recommendation: Monthly benefit, waiting period, benefit period inside superannuation. Agreed or indemnity. Features (increasing claim, super link, indexation). Premium type.
Why Appropriate: Replaces income if unable to work; premiums from super preserve disposable income; may be combined with salary sacrifice strategy.
What to Consider: Premiums reduce super balance; benefits are assessable income; waiting period still applies; review regularly.
More Information: Personal Insurances; Income Protection flyers. PDS dated [date].

TEMPLATE 7 — Purchase/Retain Trauma/Critical Illness Insurance Policy
Our Recommendation: Trauma/CI cover amount. Covered conditions to highlight (cancer, heart attack, stroke, etc.). Features (baby benefit, child trauma, death buy back, premium relief). Standalone or linked. Premium type.
Why Appropriate: Lump sum on diagnosis of serious illness; funds medical costs, mortgage, recovery; complements income protection; amount framed as X years of income.
What to Consider: Premiums from disposable income; trauma definitions vary by insurer; linked cover reduces life cover after claim; review regularly; cooling-off period.
More Information: Personal Insurances; Trauma/Critical Illness flyers. PDS dated [date].

=== INSTRUCTIONS ===

1. Review the conversation history to identify which insurance analyses were performed and what was recommended.
2. Review the client profile to extract all known facts.
3. Select which of the 7 templates apply based on the conversation.
4. For EACH applicable template, generate all 4 sections:
   - our_recommendation
   - why_appropriate
   - what_to_consider
   - more_information
5. Write in second person, addressing the client by first name.
6. Use formal Australian English as used in traditional adviser SOA documents.
7. Where a specific value is unknown or was not discussed, write [[MISSING: brief question]] inline.
8. Also return a separate "missing_questions" list for each [[MISSING:...]] token used.
9. Do NOT invent facts not supported by the client profile or conversation history.
10. Do NOT include placeholder text like [Insert X] — use [[MISSING: ...]] instead.

Return ONLY a valid JSON object in this exact format:
{
  "sections": [
    {
      "template_number": <1-7>,
      "template_name": "<full template name>",
      "title": "<short title for display>",
      "our_recommendation": "<section text>",
      "why_appropriate": "<section text>",
      "what_to_consider": "<section text>",
      "more_information": "<section text>"
    }
  ],
  "missing_questions": [
    {"id": "<snake_case_id>", "question": "<question text for the adviser>"}
  ]
}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _format_client_profile(client_memory: dict) -> str:
    """Convert client_memory.client_facts into a readable profile string."""
    facts = client_memory.get("client_facts") or {}
    lines: list[str] = ["=== CLIENT PROFILE ==="]

    p = facts.get("personal") or {}
    if p:
        lines.append("Personal:")
        for k, v in p.items():
            if v is not None:
                lines.append(f"  {k}: {v}")

    f = facts.get("financial") or {}
    if f:
        lines.append("Financial:")
        for k, v in f.items():
            if v is not None:
                # Format currency fields
                if any(x in k for x in ("income", "balance", "liabilit", "assets", "mortgage", "expenses", "premium")):
                    try:
                        lines.append(f"  {k}: ${float(v):,.0f}")
                    except (ValueError, TypeError):
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {k}: {v}")

    ins = facts.get("insurance") or {}
    if ins:
        lines.append("Insurance:")
        for k, v in ins.items():
            if v is not None and v != [] and v != "":
                if any(x in k for x in ("sum_insured", "premium", "benefit")):
                    try:
                        lines.append(f"  {k}: ${float(v):,.0f}")
                    except (ValueError, TypeError):
                        lines.append(f"  {k}: {v}")
                else:
                    lines.append(f"  {k}: {v}")

    h = facts.get("health") or {}
    if h:
        lines.append("Health:")
        for k, v in h.items():
            if v is not None and v != []:
                lines.append(f"  {k}: {v}")

    g = facts.get("goals") or {}
    if g:
        lines.append("Goals/Preferences:")
        for k, v in g.items():
            if v is not None:
                lines.append(f"  {k}: {v}")

    summary = (client_memory.get("summary_memory") or {}).get("text")
    if summary:
        lines.append(f"\n=== SESSION SUMMARY ===\n{summary}")

    return "\n".join(lines)


def _format_conversation(recent_messages: list[dict]) -> str:
    """Format recent messages as a readable conversation excerpt."""
    lines = ["=== CONVERSATION HISTORY (most recent first) ==="]
    for msg in reversed(recent_messages[-20:]):
        role = msg.get("role", "").upper()
        content = msg.get("content", "").strip()
        if content:
            # Truncate very long messages
            if len(content) > 1500:
                content = content[:1500] + "...[truncated]"
            lines.append(f"\n{role}:\n{content}")
    return "\n".join(lines)


def _extract_missing_questions(sections: list[dict]) -> list[dict]:
    """Scan section text for [[MISSING: ...]] tokens and build the questions list."""
    seen: set[str] = set()
    questions: list[dict] = []
    pattern = re.compile(r'\[\[MISSING:\s*([^\]]+)\]\]')

    for section in sections:
        for field_name in ("our_recommendation", "why_appropriate", "what_to_consider", "more_information"):
            text = section.get(field_name, "")
            for match in pattern.finditer(text):
                question_text = match.group(1).strip()
                q_id = re.sub(r'\W+', '_', question_text.lower())[:40].strip('_')
                if q_id not in seen:
                    seen.add(q_id)
                    questions.append({"id": q_id, "question": question_text})

    return questions


def _apply_answers(sections: list[dict], answers: dict[str, str]) -> list[dict]:
    """Replace [[MISSING: ...]] tokens with user-provided answers where the id matches."""
    if not answers:
        return sections

    # Build a map from token text → answer (case-insensitive prefix match on id)
    pattern = re.compile(r'\[\[MISSING:\s*([^\]]+)\]\]')

    updated = []
    for section in sections:
        section = dict(section)
        for field_name in ("our_recommendation", "why_appropriate", "what_to_consider", "more_information"):
            text = section.get(field_name, "")

            def replacer(m: re.Match) -> str:
                question_text = m.group(1).strip()
                q_id = re.sub(r'\W+', '_', question_text.lower())[:40].strip('_')
                return answers.get(q_id, m.group(0))  # keep original if no answer

            section[field_name] = pattern.sub(replacer, text)
        updated.append(section)

    return updated


# ---------------------------------------------------------------------------
# Main generation function
# ---------------------------------------------------------------------------

async def generate_soa(
    client_memory: dict,
    recent_messages: list[dict],
    answers: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Generate SOA sections using the LLM.

    Args:
        client_memory: Full conversation_memory document from MongoDB
        recent_messages: List of {role, content} dicts from the conversation
        answers: Optional dict of {question_id: answer} to fill previously missing values

    Returns:
        {
            "sections": [...],
            "missing_questions": [...]
        }
        or {"error": "...message"} on failure.
    """
    try:
        from app.core.llm import get_chat_model_fresh
        from langchain_core.messages import SystemMessage, HumanMessage

        client_profile = _format_client_profile(client_memory)
        conversation = _format_conversation(recent_messages)

        user_content = f"""{client_profile}

{conversation}

Based on the client profile and conversation history above, generate the SOA insurance strategy sections.
Remember to return ONLY a valid JSON object — no markdown fences, no explanation."""

        llm = get_chat_model_fresh(temperature=0.1)
        response = await llm.ainvoke([
            SystemMessage(content=_SOA_TEMPLATES_PROMPT),
            HumanMessage(content=user_content),
        ])

        raw = response.content.strip() if hasattr(response, "content") else ""

        # Strip markdown fences if present
        if raw.startswith("```"):
            lines = raw.splitlines()
            raw = "\n".join(l for l in lines if not l.strip().startswith("```")).strip()

        data = json.loads(raw)
        sections: list[dict] = data.get("sections") or []

        # Apply any answers the user provided to fill in [[MISSING:...]] tokens
        if answers:
            sections = _apply_answers(sections, answers)

        # Extract remaining missing questions from section text
        missing_questions = _extract_missing_questions(sections)

        # Merge with any questions returned by the LLM (deduplicate)
        llm_questions = data.get("missing_questions") or []
        existing_ids = {q["id"] for q in missing_questions}
        for q in llm_questions:
            q_id = q.get("id", "")
            if q_id and q_id not in existing_ids:
                missing_questions.append(q)
                existing_ids.add(q_id)

        logger.info(
            "soa_service: generated %d section(s), %d missing question(s)",
            len(sections),
            len(missing_questions),
        )
        return {"sections": sections, "missing_questions": missing_questions}

    except json.JSONDecodeError as exc:
        logger.error("soa_service: JSON parse error: %s", exc)
        return {"error": "The SOA generator returned malformed output. Please try again."}
    except Exception as exc:
        logger.error("soa_service: unexpected error: %s", exc)
        return {"error": f"SOA generation failed: {exc}"}
