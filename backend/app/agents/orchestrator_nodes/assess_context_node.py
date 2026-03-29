"""
assess_context_node.py — Orchestrator node: decide what context is needed for this query.

This is the FIRST node in the orchestrator graph. It runs a fast, rule-based
analysis on the raw user message (plus the last 3 messages for follow-up signals)
to determine a ContextRequirements spec. All subsequent loading nodes use this
spec to load exactly what they need — no more.

WHY this matters
----------------
Loading all 20 messages + all memory sections + all documents for every query is:
  • Expensive (token cost)
  • Noisy (irrelevant context degrades LLM decision quality)
  • Slow (unnecessary DB reads)

This node does zero LLM calls. It is purely rule-based so it adds <1ms latency.
When uncertain it errs on the side of loading MORE (false positives are safe,
false negatives cause information loss).

ContextRequirements fields written to state
-------------------------------------------
context_requirements: {
    message_history_depth: int       # 3 | 8 | 15 messages to load
    memory_sections:       list[str] # subset of [personal, financial, insurance, health, goals]
    load_advisory_notes:   bool      # load prior advisory conclusions?
    load_documents:        bool      # load uploaded document text?
    load_scratch_pad:      bool      # load agent working notes? (always True for now)
    reasoning:             str       # logged explanation of each decision
}
"""

import logging
import re

from app.agents.state import AgentState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain → required memory sections
# ---------------------------------------------------------------------------

# Each entry: (patterns, sections_to_load)
# Evaluated top-to-bottom; first full match wins for sections; ALL matching
# sections are unioned (a query may span multiple domains).

_DOMAIN_RULES: list[tuple[list[str], list[str]]] = [
    # SOA / comprehensive advice — load everything
    (
        ["statement of advice", "soa", "full report", "full advice", "comprehensive advice",
         "advice document", "generate report"],
        ["personal", "financial", "insurance", "health", "goals"],
    ),
    # Income protection (most context-hungry — needs health)
    (
        ["income protection", " ip ", "ip cover", "ip policy", "salary continuance",
         "disability income", "waiting period", "benefit period", "ip in super",
         "income protection in super", "ip through super"],
        ["personal", "financial", "insurance", "health"],
    ),
    # Life + TPD (retail policy)
    (
        ["life insurance", "life cover", "tpd", "total and permanent",
         "total permanent disability", "death cover", "life tpd",
         "retail policy", "retail life", "replace policy", "new policy",
         "existing policy", "sum insured", "underwriting", "retain or replace"],
        ["personal", "financial", "insurance"],
    ),
    # Life insurance in super
    (
        ["life insurance in super", "insurance in super", "inside super",
         "super fund insurance", "super insurance", "mysuper",
         "low balance", "inactivity", "switch off", "opt in",
         "protecting your super", "pys"],
        ["personal", "financial"],
    ),
    # TPD standalone / in super
    (
        ["tpd policy", "tpd assessment", "tpd in super", "tpd cover",
         "total permanent disability cover"],
        ["personal", "financial", "insurance"],
    ),
    # Trauma / critical illness
    (
        ["trauma", "critical illness", "ci cover", "trauma cover",
         "trauma policy", "trauma insurance"],
        ["personal", "financial", "insurance"],
    ),
    # Super / retirement / fund questions (general)
    (
        ["super balance", "superannuation", "my super", "super fund",
         "contribution", "retirement savings", "fund type"],
        ["personal", "financial"],
    ),
    # Premium / affordability
    (
        ["premium", "afford", "cost of", "monthly cost", "annual premium"],
        ["personal", "financial", "insurance"],
    ),
]

_DEFAULT_SECTIONS = ["personal", "financial"]  # always-safe minimum

# ---------------------------------------------------------------------------
# History depth triggers
# ---------------------------------------------------------------------------

# Load 15 messages when the user is explicitly referencing earlier conversation
_HISTORY_DEEP_TRIGGERS = [
    "earlier", "previously", "before", "last time", "what did we",
    "you said", "we discussed", "remind me", "what was", "go back",
    "revisit", "i mentioned", "you mentioned", "refer back",
]

# Load 8 messages for follow-up signals
_HISTORY_MEDIUM_TRIGGERS = [
    "also", "additionally", "and what about", "continue", "follow up",
    "follow-up", "as well", "furthermore", "next", "moving on",
    "what else", "anything else",
]

# Default: 3 messages (just enough for conversational continuity)
_HISTORY_DEFAULT = 3

# ---------------------------------------------------------------------------
# Advisory notes triggers (load prior analysis conclusions)
# ---------------------------------------------------------------------------

_ADVISORY_TRIGGERS = [
    "what did we decide", "what did you recommend", "previous analysis",
    "last analysis", "our recommendation", "prior recommendation",
    "what was recommended", "soa", "statement of advice", "summary",
    "review our", "what have we covered", "decisions made",
    "advice so far", "what have we agreed",
]

# ---------------------------------------------------------------------------
# Document triggers
# ---------------------------------------------------------------------------

_DOCUMENT_TRIGGERS = [
    "document", "file", "uploaded", "pdf", "attachment", "attached",
    "you gave me", "i sent", "i uploaded", "in the statement",
    "policy document", "policy schedule", "product disclosure",
    "pds", "policy wording",
]


# ---------------------------------------------------------------------------
# Core analysis function
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return " " + text.lower().strip() + " "


def analyse_query(user_message: str, recent_messages: list[dict]) -> dict:
    """
    Pure function. Returns a ContextRequirements dict.
    Also considers the last 3 messages for follow-up/history signals.
    """
    msg_norm = _normalise(user_message)

    # Include recent messages text for follow-up detection
    recent_text = " ".join(
        m.get("content", "") for m in recent_messages[-3:]
    ).lower()
    combined = msg_norm + " " + recent_text

    reasons: list[str] = []

    # ---- 1. Memory sections ----
    sections: set[str] = set()
    for patterns, domain_sections in _DOMAIN_RULES:
        if any(p in msg_norm for p in patterns):
            sections.update(domain_sections)
            reasons.append(f"domain match → sections {domain_sections}")

    if not sections:
        sections = set(_DEFAULT_SECTIONS)
        reasons.append("no domain match → default sections [personal, financial]")

    # ---- 2. Message history depth ----
    if any(t in combined for t in _HISTORY_DEEP_TRIGGERS):
        history_depth = 15
        reasons.append("deep history trigger → 15 messages")
    elif any(t in combined for t in _HISTORY_MEDIUM_TRIGGERS):
        history_depth = 8
        reasons.append("medium history trigger → 8 messages")
    else:
        history_depth = _HISTORY_DEFAULT
        reasons.append(f"no history trigger → {_HISTORY_DEFAULT} messages")

    # ---- 3. Advisory notes ----
    load_advisory = any(t in combined for t in _ADVISORY_TRIGGERS)
    if load_advisory:
        reasons.append("advisory trigger → load prior conclusions")
        # Advisory queries also benefit from all sections
        sections.update(["personal", "financial", "insurance"])

    # ---- 4. Documents ----
    load_documents = any(t in msg_norm for t in _DOCUMENT_TRIGGERS)
    if load_documents:
        reasons.append("document trigger → load uploaded file text")

    # ---- 5. Scratch pad (always load — it's tiny) ----
    load_scratch_pad = True

    return {
        "message_history_depth": history_depth,
        "memory_sections": sorted(sections),
        "load_advisory_notes": load_advisory,
        "load_documents": load_documents,
        "load_scratch_pad": load_scratch_pad,
        "reasoning": "; ".join(reasons),
    }


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

async def assess_context(state: AgentState) -> dict:
    """
    Analyse the query and determine what context is needed.

    Reads:  user_message, recent_messages (may be empty at this point — uses
            whatever is already in state from a previous turn, not newly loaded)
    Writes: context_requirements
    """
    user_message = state.get("user_message", "")
    # Use whatever recent_messages is already in state (may be empty for first turn).
    # This is just for follow-up signal detection, not full context loading.
    existing_recent = state.get("recent_messages", [])

    requirements = analyse_query(user_message, existing_recent)

    logger.info(
        "assess_context: depth=%d sections=%s advisory=%s docs=%s | %s",
        requirements["message_history_depth"],
        requirements["memory_sections"],
        requirements["load_advisory_notes"],
        requirements["load_documents"],
        requirements["reasoning"],
    )

    return {"context_requirements": requirements}
