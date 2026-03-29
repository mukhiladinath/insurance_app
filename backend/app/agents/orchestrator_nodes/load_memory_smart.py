"""
load_memory_smart.py — Section-selective client memory + advisory notes loader.

Replaces the legacy load_memory node in the orchestrator graph.

Instead of loading the full client_facts document every time, this node:
  1. Loads ONLY the sections specified in context_requirements.memory_sections.
     Other sections are represented by a stub {"_available": True} so the
     planner knows the data exists but doesn't have it in-context.
  2. Optionally loads prior advisory conclusions (advisory_notes) when
     context_requirements.load_advisory_notes is True.
  3. Optionally loads the scratch pad (agent working notes) — always tiny.

This keeps the planning prompt compact and focused. The planner can always
set clarification_needed if it discovers it needs a section that wasn't loaded.

State reads:  conversation_id, context_requirements
State writes: client_memory, advisory_notes, scratch_pad_entries
"""

import logging

from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.advisory_notes_repository import AdvisoryNotesRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository

logger = logging.getLogger(__name__)

_ALL_SECTIONS = ["personal", "financial", "insurance", "health", "goals"]

# Always load all sections — selective loading was causing silent information
# loss when the planner needed facts from sections that weren't in the query
# keywords. The extra tokens are far cheaper than wrong advice.
_ALWAYS_LOAD_ALL = True


def _filter_memory(full_memory: dict, sections_needed: list[str]) -> dict:
    """
    Return a copy of full_memory where client_facts contains only the
    requested sections. Sections not requested are replaced with a stub
    {"_available": True} so the planner can see they exist without getting
    all their values.
    """
    if not full_memory:
        return {}

    full_facts: dict = full_memory.get("client_facts", {})
    filtered_facts: dict = {}

    for section in _ALL_SECTIONS:
        if section in sections_needed:
            # Full detail
            filtered_facts[section] = full_facts.get(section, {})
        elif full_facts.get(section):
            # Stub — planner knows data is there if it needs it
            non_null = {k: v for k, v in full_facts[section].items() if v is not None and v != ""}
            if non_null:
                filtered_facts[section] = {"_available": True, "_fields": list(non_null.keys())}
        # If the section has no data at all, omit entirely

    # Keep all non-client_facts fields intact (version, turn_count, summary_memory, etc.)
    return {**full_memory, "client_facts": filtered_facts}


async def load_memory_smart(state: AgentState) -> dict:
    """
    Load selectively filtered client memory + optional advisory notes.

    Reads:  conversation_id, context_requirements
    Writes: client_memory, advisory_notes, scratch_pad_entries
    """
    conversation_id = state.get("conversation_id")
    if not conversation_id:
        return {"client_memory": {}, "advisory_notes": {}, "scratch_pad_entries": []}

    requirements = state.get("context_requirements", {})
    # Always load all sections so the planner never operates on partial data.
    # Stubs are only used when _ALWAYS_LOAD_ALL is False.
    sections_needed: list[str] = _ALL_SECTIONS if _ALWAYS_LOAD_ALL else requirements.get("memory_sections", ["personal", "financial"])
    load_advisory: bool = requirements.get("load_advisory_notes", True)  # always load advisory notes

    result: dict = {}

    try:
        db = get_db()
        mem_repo = ConversationMemoryRepository(db)
        full_memory = await mem_repo.get_by_conversation_id(conversation_id)

        if full_memory is None:
            logger.debug("load_memory_smart: no memory yet for %s", conversation_id)
            result["client_memory"] = {}
        else:
            filtered = _filter_memory(full_memory, sections_needed)
            result["client_memory"] = filtered

            loaded_section_names = [
                s for s in sections_needed
                if full_memory.get("client_facts", {}).get(s)
            ]
            stub_sections = [
                s for s in _ALL_SECTIONS
                if s not in sections_needed
                and full_memory.get("client_facts", {}).get(s)
            ]
            logger.info(
                "load_memory_smart: full sections=%s stubs=%s (conv=%s)",
                loaded_section_names, stub_sections, conversation_id,
            )

    except Exception as exc:
        logger.error("load_memory_smart: memory load error: %s", exc)
        result["client_memory"] = {}
        result["errors"] = state.get("errors", []) + [f"Memory load error: {exc}"]

    # ---- Advisory notes ----
    advisory_notes: dict = {}
    if load_advisory:
        try:
            adv_repo = AdvisoryNotesRepository(db)
            advisory_doc = await adv_repo.get_by_conversation(conversation_id)
            if advisory_doc:
                advisory_notes = advisory_doc.get("advisory_notes", {})
                scratch_pad = advisory_doc.get("scratch_pad", [])
                logger.info(
                    "load_memory_smart: loaded %d advisory note(s), %d scratch pad entries",
                    len(advisory_notes), len(scratch_pad),
                )
            else:
                scratch_pad = []
        except Exception as exc:
            logger.warning("load_memory_smart: advisory load error: %s", exc)
            scratch_pad = []
    else:
        # Always load scratch pad (it's tiny — just agent working notes)
        try:
            adv_repo = AdvisoryNotesRepository(db)
            advisory_doc = await adv_repo.get_by_conversation(conversation_id)
            scratch_pad = advisory_doc.get("scratch_pad", []) if advisory_doc else []
        except Exception:
            scratch_pad = []

    result["advisory_notes"] = advisory_notes
    result["scratch_pad_entries"] = scratch_pad

    return result
