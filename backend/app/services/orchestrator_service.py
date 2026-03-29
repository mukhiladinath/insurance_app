"""
orchestrator_service.py — Service layer for the agent workspace orchestrator.

Called by POST /api/agent/run.

Sequence:
  1. get_or_create conversation
  2. save user message
  3. create agent_run (status=running, orchestrator_mode=True)
  4. build initial OrchestratorState and invoke the orchestrator graph
  5. assemble and return AgentRunResponse
"""

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.orchestrator_graph import run_orchestrator
from app.agents.state import AgentState
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.schemas.agent_schemas import (
    AgentRunRequest,
    AgentRunResponse,
    AgentRunOut,
    ConversationOut,
    DataCardOut,
    PlanStepOut,
    StepResultOut,
)
from app.services.conversation_service import ConversationService
from app.core.constants import MessageRole

logger = logging.getLogger(__name__)


class OrchestratorService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)
        self._run_repo = AgentRunRepository(db)
        self._conv_service = ConversationService(db)

    async def run(self, req: AgentRunRequest) -> AgentRunResponse:
        # ----------------------------------------------------------------
        # 1. Get or create conversation
        # ----------------------------------------------------------------
        conv = await self._conv_service.get_or_create_conversation(
            user_id=req.user_id,
            conversation_id=req.conversation_id,
            first_message=req.message,
            title=req.conversation_title,
        )
        conversation_id = conv["id"]

        # ----------------------------------------------------------------
        # 2. Save user message
        # ----------------------------------------------------------------
        user_msg = await self._msg_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=req.message,
        )

        # ----------------------------------------------------------------
        # 3. Create agent run (orchestrator mode)
        # ----------------------------------------------------------------
        agent_run = await self._run_repo.create(
            conversation_id=conversation_id,
            user_message_id=user_msg["id"],
        )
        agent_run_id = agent_run["id"]

        # ----------------------------------------------------------------
        # 4. Build initial state and invoke the orchestrator graph
        # ----------------------------------------------------------------
        initial_state: AgentState = {
            "user_id": req.user_id,
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "user_message": req.message,
            "user_message_id": user_msg["id"],
            "tool_hint": None,
            "tool_input_override": None,
            "attached_files": [f.model_dump() for f in req.attached_files],
            "recent_messages": [],
            "client_memory": {},
            "document_context": None,
            "tool_warnings": [],
            "errors": [],
            # Orchestrator fields
            "orchestrator_mode": True,
            "plan_steps": [],
            "step_results": [],
            "data_cards": [],
            "clarification_needed": False,
            "clarification_question": None,
            "missing_context": [],
            # Dynamic context (populated by assess_context node)
            "context_requirements": {},
            "advisory_notes": {},
            "scratch_pad_entries": [],
        }

        try:
            final_state = await run_orchestrator(initial_state)
        except Exception as exc:
            logger.exception("Orchestrator graph failed: %s", exc)
            await self._run_repo.fail(agent_run_id, error=str(exc))
            raise RuntimeError(f"Agent execution failed: {exc}") from exc

        # ----------------------------------------------------------------
        # 5. Fetch persisted records
        # ----------------------------------------------------------------
        assistant_message_id = final_state.get("assistant_message_id")

        updated_run = await self._run_repo.get_by_id(agent_run_id)
        updated_conv = await self._conv_repo.get_by_id(conversation_id)

        # ----------------------------------------------------------------
        # 6. Assemble response
        # ----------------------------------------------------------------
        plan_steps = [
            PlanStepOut(
                step_id=s["step_id"],
                tool_name=s["tool_name"],
                description=s.get("description", ""),
                depends_on=s.get("depends_on", []),
                rationale=s.get("rationale", ""),
            )
            for s in final_state.get("plan_steps", [])
        ]

        step_results = [
            StepResultOut(
                step_id=r["step_id"],
                tool_name=r["tool_name"],
                description=r.get("description", ""),
                status=r["status"],
                error=r.get("error"),
            )
            for r in final_state.get("step_results", [])
        ]

        data_cards = []
        for card in final_state.get("data_cards", []):
            try:
                data_cards.append(
                    DataCardOut(
                        step_id=card.get("step_id", ""),
                        tool_name=card.get("tool_name", ""),
                        type=card.get("type", "generic"),
                        title=card.get("title", "Result"),
                        display_hint=card.get("display_hint", "table"),
                        data=card.get("data", {}),
                    )
                )
            except Exception as e:
                logger.warning("Skipping malformed data card: %s", e)

        # Build context_loaded summary for frontend display
        ctx_req = final_state.get("context_requirements", {})
        client_memory = final_state.get("client_memory", {})
        facts = client_memory.get("client_facts", {}) if client_memory else {}
        facts_loaded: dict = {}
        for section, data in facts.items():
            if isinstance(data, dict) and not data.get("_available"):
                facts_loaded[section] = [k for k, v in data.items() if v is not None and v != "" and v != []]

        context_loaded = {
            "memory_sections": ctx_req.get("memory_sections", []),
            "history_depth": ctx_req.get("message_history_depth", 0),
            "advisory_notes_loaded": ctx_req.get("load_advisory_notes", False),
            "facts_loaded": facts_loaded,  # section → list of non-null field names
        }

        return AgentRunResponse(
            conversation=ConversationOut(
                id=updated_conv["id"],
                title=updated_conv["title"],
                user_id=updated_conv["user_id"],
                status=updated_conv["status"],
                created_at=updated_conv["created_at"],
                updated_at=updated_conv["updated_at"],
            ),
            user_message_id=user_msg["id"],
            assistant_message_id=assistant_message_id,
            assistant_content=final_state.get("final_response", ""),
            agent_run=AgentRunOut(
                id=agent_run_id,
                intent=updated_run.get("intent") if updated_run else None,
                status=updated_run.get("status", "unknown") if updated_run else "unknown",
            ),
            plan_steps=plan_steps,
            step_results=step_results,
            data_cards=data_cards,
            clarification_needed=final_state.get("clarification_needed", False),
            clarification_question=final_state.get("clarification_question"),
            missing_context=final_state.get("missing_context", []),
            context_loaded=context_loaded,
        )
