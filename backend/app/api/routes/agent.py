"""
agent.py — Agent workspace API routes.

POST /api/agent/run
  Receives a user instruction, runs the full orchestrator graph (plan →
  execute_steps → summarize → persist), and returns a structured response
  containing the execution plan, per-step results, data cards, and the
  adviser's synthesised text response.

This endpoint replaces the legacy /api/chat/message for the new agent
workspace UI.  The legacy endpoint remains available for backwards compatibility.
"""

import logging

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db.mongo import get_db
from app.db.repositories.advisory_notes_repository import AdvisoryNotesRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.schemas.agent_schemas import AgentRunRequest, AgentRunResponse
from app.services.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/agent", tags=["agent"])
logger = logging.getLogger(__name__)


@router.post("/run", response_model=AgentRunResponse)
async def run_agent(req: AgentRunRequest):
    """
    Execute a user instruction through the orchestrator agent workspace.

    - Creates a conversation if conversation_id is omitted.
    - Saves the user message to MongoDB.
    - Runs the planning LLM to decompose the instruction into steps.
    - Executes all steps sequentially (with {{step_N.field}} chaining).
    - Synthesises a natural-language adviser response.
    - Persists all results and returns a structured AgentRunResponse.

    When the agent cannot proceed due to missing information, the response
    will have clarification_needed=True and a clarification_question.
    The frontend should display the question and re-submit with the answer.
    """
    db = get_db()
    service = OrchestratorService(db)

    try:
        return await service.run(req)
    except ValueError as exc:
        logger.warning("Agent run validation error: %s", exc)
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Agent run runtime error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("Unexpected error in agent run endpoint: %s", exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


@router.get("/workspace/{conversation_id}")
async def get_workspace(conversation_id: str):
    """
    Return the full client workspace data for a conversation.

    Used by the client profile UI to display:
      - client_facts (personal, financial, insurance, health, goals)
      - advisory_notes (structured conclusions from prior tool runs)
      - summary (rolling prose summary of the conversation)
      - turn_count (number of turns so far)
    """
    db = get_db()
    try:
        mem_repo = ConversationMemoryRepository(db)
        adv_repo = AdvisoryNotesRepository(db)

        memory = await mem_repo.get_by_conversation_id(conversation_id)
        workspace = await adv_repo.get_by_conversation(conversation_id)

        client_facts = memory.get("client_facts", {}) if memory else {}
        summary_memory = memory.get("summary_memory", {}) if memory else {}

        return {
            "client_facts": client_facts,
            "advisory_notes": workspace.get("advisory_notes", {}) if workspace else {},
            "scratch_pad": workspace.get("scratch_pad", []) if workspace else [],
            "summary": summary_memory.get("text", ""),
            "turn_count": memory.get("turn_count", 0) if memory else 0,
        }
    except Exception as exc:
        logger.exception("Error fetching workspace for %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail="Failed to load client workspace.")


class PatchFactsRequest(BaseModel):
    facts: dict[str, dict[str, Any]]


@router.patch("/workspace/{conversation_id}/facts", status_code=200)
async def patch_facts(conversation_id: str, req: PatchFactsRequest):
    """
    Manually update specific client_facts fields for a conversation.

    Body: { "facts": { "personal": { "age": 35 }, "financial": { "super_balance": 150000 } } }
    A null value for any field removes it from memory.
    """
    allowed_sections = {"personal", "financial", "insurance", "health", "goals"}
    invalid = set(req.facts.keys()) - allowed_sections
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown sections: {invalid}")

    db = get_db()
    try:
        mem_repo = ConversationMemoryRepository(db)
        await mem_repo.patch_facts(conversation_id, req.facts)
        return {"ok": True}
    except Exception as exc:
        logger.exception("Error patching facts for %s: %s", conversation_id, exc)
        raise HTTPException(status_code=500, detail="Failed to update client facts.")
