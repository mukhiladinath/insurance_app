"""
workspace_orchestrator_service.py — Service layer for POST /api/workspace/{client_id}/run.

Sequence:
  1. Validate client exists
  2. Get or create client workspace
  3. Get or create conversation (scoped to client)
  4. Save user message
  5. Create agent_run record (with client_id + workspace_id)
  6. Build initial WorkspaceState
  7. Invoke the workspace graph
  8. Assemble and return WorkspaceRunResponse
"""

import logging
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.agents.workspace_graph import run_workspace_graph
from app.agents.workspace_state import WorkspaceState
from app.core.constants import MessageRole
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.saved_tool_run_repository import SavedToolRunRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.schemas.workspace_schemas import (
    WorkspaceRunRequest,
    WorkspaceRunResponse,
    DataCardOut,
    MissingFieldOut,
    PlanStepOut,
    StepResultOut,
    UiActionOut,
)
from app.services.conversation_service import ConversationService

logger = logging.getLogger(__name__)


class WorkspaceOrchestratorService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._client_repo = ClientRepository(db)
        self._workspace_repo = WorkspaceRepository(db)
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)
        self._run_repo = AgentRunRepository(db)
        self._saved_repo = SavedToolRunRepository(db)
        self._conv_service = ConversationService(db)

    async def run(self, client_id: str, req: WorkspaceRunRequest) -> WorkspaceRunResponse:
        # ----------------------------------------------------------------
        # 1. Validate client
        # ----------------------------------------------------------------
        client = await self._client_repo.get_by_id(client_id)
        if not client:
            raise ValueError(f"Client '{client_id}' not found.")

        # ----------------------------------------------------------------
        # 2. Get or create workspace
        # ----------------------------------------------------------------
        workspace = await self._workspace_repo.get_or_create(
            client_id=client_id,
            user_id=req.user_id,
        )
        workspace_id = workspace["id"]

        # ----------------------------------------------------------------
        # 3. Get or create conversation (scoped to client)
        # ----------------------------------------------------------------
        conv = await self._conv_service.get_or_create_conversation(
            user_id=req.user_id,
            conversation_id=req.conversation_id,
            first_message=req.message,
            title=client.get("name"),
        )
        conversation_id = conv["id"]

        # Link conversation to workspace if needed
        if workspace.get("active_conversation_id") != conversation_id:
            await self._workspace_repo.set_active_conversation(client_id, conversation_id)

        # ----------------------------------------------------------------
        # 4. Save user message
        # ----------------------------------------------------------------
        user_msg = await self._msg_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.USER,
            content=req.message,
        )

        # ----------------------------------------------------------------
        # 5. Create agent_run
        # ----------------------------------------------------------------
        agent_run = await self._run_repo.create(
            conversation_id=conversation_id,
            user_message_id=user_msg["id"],
        )
        run_id = agent_run["id"]

        # ----------------------------------------------------------------
        # 6. Build initial WorkspaceState
        # ----------------------------------------------------------------
        initial_state: WorkspaceState = {
            "user_id": req.user_id,
            "client_id": client_id,
            "workspace_id": workspace_id,
            "conversation_id": conversation_id,
            "run_id": run_id,

            "user_message": req.message,
            "user_message_id": user_msg["id"],
            "attached_files": [f.model_dump() for f in req.attached_files],

            "resume_token": req.resume_token,
            "clarification_answer": req.clarification_answer,

            "rerun_from_saved_run_id": req.rerun_from_saved_run_id,
            "patched_inputs": req.patched_inputs,

            "save_run_as": req.save_run_as,

            # Initialise empty — loaded by load_workspace_context
            "recent_messages": [],
            "factfind_snapshot": {},
            "factfind_full": {},
            "ai_context_hierarchy": {},
            "ai_context_overrides": {},
            "extracted_document_context": None,

            "tool_plan": [],
            "dependency_graph": {},
            "step_results": [],
            "cached_step_results": {},
            "invalidated_steps": [],

            "clarification_needed": False,
            "clarification_question": None,
            "missing_fields": [],

            "advisory_notes": {},
            "scratch_pad": [],
            "factfind_draft_changes": {},
            "factfind_proposal_id": None,

            "final_response": "",
            "structured_response_payload": None,
            "data_cards": [],
            "ui_actions": [],
            "assistant_message_id": None,
            "saved_run_id": None,
            "context_snapshot_id": None,
            "errors": [],
        }

        # ----------------------------------------------------------------
        # 7. Run the workspace graph
        # ----------------------------------------------------------------
        try:
            final_state = await run_workspace_graph(initial_state)
        except Exception as exc:
            logger.exception("Workspace graph failed for client=%s: %s", client_id, exc)
            await self._run_repo.fail(run_id, error=str(exc))
            raise RuntimeError(f"Workspace agent execution failed: {exc}") from exc

        # ----------------------------------------------------------------
        # 8. Assemble response
        # ----------------------------------------------------------------
        clarification_needed = final_state.get("clarification_needed", False)

        # Determine run status
        if clarification_needed:
            run_status = "awaiting_clarification"
        elif final_state.get("errors"):
            run_status = "partial"
        else:
            run_status = "completed"

        # Resume token: read from state (written by persist_pending_clarification node)
        resume_token: str | None = final_state.get("pending_resume_token")

        # Plan steps
        plan_steps = [
            PlanStepOut(
                step_id=s["step_id"],
                tool_name=s["tool_name"],
                description=s.get("description", ""),
                depends_on=s.get("depends_on", []),
                rationale=s.get("rationale", ""),
            )
            for s in final_state.get("tool_plan", [])
        ]

        # Step results
        step_results = [
            StepResultOut(
                step_id=r["step_id"],
                tool_name=r["tool_name"],
                description=r.get("description", ""),
                status=r["status"],
                error=r.get("error"),
                cache_source_run_id=r.get("cache_source_run_id"),
            )
            for r in final_state.get("step_results", [])
        ]

        # Data cards
        data_cards = []
        for card in final_state.get("data_cards", []):
            try:
                data_cards.append(DataCardOut(
                    step_id=card.get("step_id", ""),
                    tool_name=card.get("tool_name", ""),
                    type=card.get("type", "generic"),
                    title=card.get("title", "Result"),
                    display_hint=card.get("display_hint", "table"),
                    data=card.get("data", {}),
                ))
            except Exception as e:
                logger.warning("Skipping malformed data card: %s", e)

        # Missing fields
        missing_fields = [
            MissingFieldOut(
                field_path=f.get("field_path", ""),
                label=f.get("label", f.get("field_path", "")),
                section=f.get("section", ""),
                required=f.get("required", True),
            )
            for f in final_state.get("missing_fields", [])
        ]

        # UI actions
        ui_actions = [
            UiActionOut(type=a.get("type", ""), payload=a.get("payload", {}))
            for a in final_state.get("ui_actions", [])
        ]

        # Proposed factfind patches
        proposed_patches = None
        structured_payload = final_state.get("structured_response_payload")
        if structured_payload and structured_payload.get("type") == "factfind_proposal":
            from app.schemas.workspace_schemas import ProposedPatchOut, ProposedFieldOut
            proposal_id = structured_payload.get("proposal_id") or ""
            fields_data = structured_payload.get("fields", [])
            if fields_data and proposal_id:  # only emit if we have a valid proposal_id
                proposed_patches = ProposedPatchOut(
                    proposal_id=proposal_id,
                    source_document_id=structured_payload.get("source_document_id") or "",
                    fields=[
                        ProposedFieldOut(
                            field_path=f["field_path"],
                            label=f["label"],
                            current_value=f.get("current_value"),
                            proposed_value=f.get("proposed_value"),
                            confidence=f.get("confidence", 0.8),
                            evidence=f.get("evidence", ""),
                        )
                        for f in fields_data
                    ],
                )
            elif fields_data and not proposal_id:
                logger.warning(
                    "workspace_orchestrator: factfind_proposal has fields but no proposal_id "
                    "(add_proposal likely failed) — skipping proposed_patches for client=%s",
                    client_id,
                )

        # Context summary
        factfind_flat = final_state.get("factfind_snapshot", {})
        context_summary = {
            "factfind_field_count": len(factfind_flat),
            "advisory_notes_count": len(final_state.get("advisory_notes", {})),
            "message_history_depth": len(final_state.get("recent_messages", [])),
            "active_mode": final_state.get("active_mode"),
        }

        return WorkspaceRunResponse(
            run_id=run_id,
            client_id=client_id,
            workspace_id=workspace_id,
            conversation_id=conversation_id,
            user_message_id=user_msg["id"],
            assistant_message_id=final_state.get("assistant_message_id"),
            run_status=run_status,
            assistant_content=final_state.get("final_response", ""),
            clarification_needed=clarification_needed,
            clarification_question=final_state.get("clarification_question"),
            missing_fields=missing_fields,
            resume_token=resume_token,
            plan_steps=plan_steps,
            step_results=step_results,
            data_cards=data_cards,
            proposed_factfind_patches=proposed_patches,
            saved_run_id=final_state.get("saved_run_id"),
            ui_actions=ui_actions,
            context_snapshot_id=final_state.get("context_snapshot_id"),
            context_summary=context_summary,
            errors=final_state.get("errors", []),
        )
