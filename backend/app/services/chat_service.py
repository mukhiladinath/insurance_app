"""
chat_service.py — Orchestrates the full chat message flow.

Called by POST /api/chat/message.
Sequence:
  1. get_or_create conversation
  2. save user message
  3. create agent_run (status=running)
  4. optionally start tool_call record (if tool_hint provided)
  5. invoke LangGraph agent
  6. return structured ChatMessageResponse
"""

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.tool_call_repository import ToolCallRepository
from app.services.conversation_service import ConversationService
from app.agents.graph import run_agent
from app.agents.state import AgentState
from app.schemas.chat import (
    ChatMessageRequest, ChatMessageResponse,
    ConversationOut, UserMessageOut, AssistantMessageOut, AgentRunSummary, ToolResultEnvelope,
)
from app.core.constants import MessageRole
from app.tools.registry import get_tool

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._conv_repo = ConversationRepository(db)
        self._msg_repo = MessageRepository(db)
        self._run_repo = AgentRunRepository(db)
        self._tc_repo = ToolCallRepository(db)
        self._conv_service = ConversationService(db)

    async def handle_message(self, req: ChatMessageRequest) -> ChatMessageResponse:
        # ----------------------------------------------------------------
        # 1. Get or create conversation
        # ----------------------------------------------------------------
        conv = await self._conv_service.get_or_create_conversation(
            user_id=req.user_id,
            conversation_id=req.conversation_id,
            first_message=req.message,
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
        # 3. Create agent run
        # ----------------------------------------------------------------
        agent_run = await self._run_repo.create(
            conversation_id=conversation_id,
            user_message_id=user_msg["id"],
        )
        agent_run_id = agent_run["id"]

        # ----------------------------------------------------------------
        # 4. Optionally pre-log a tool_call start (if tool_hint given)
        # ----------------------------------------------------------------
        tool_call_started = None
        if req.tool_hint and get_tool(req.tool_hint):
            tool_obj = get_tool(req.tool_hint)
            tool_call_started = await self._tc_repo.start(
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
                tool_name=tool_obj.name,
                tool_version=tool_obj.version,
                input_payload=req.tool_input or {},
            )

        # ----------------------------------------------------------------
        # 5. Build initial agent state and invoke the graph
        # ----------------------------------------------------------------
        initial_state: AgentState = {
            "user_id": req.user_id,
            "conversation_id": conversation_id,
            "agent_run_id": agent_run_id,
            "user_message": req.message,
            "user_message_id": user_msg["id"],   # needed by update_memory for field_meta
            "tool_hint": req.tool_hint,
            "tool_input_override": req.tool_input,
            "recent_messages": [],
            "client_memory": {},
            "attached_files": [f.model_dump() for f in req.attached_files],
            "document_context": None,
            "tool_warnings": [],
            "errors": [],
        }

        try:
            final_state = await run_agent(initial_state)
        except Exception as exc:
            logger.exception("Agent graph failed: %s", exc)
            # Fail the agent run
            await self._run_repo.fail(agent_run_id, error=str(exc))
            raise RuntimeError(f"Agent execution failed: {exc}") from exc

        # ----------------------------------------------------------------
        # 6. Fetch the persisted assistant message
        # ----------------------------------------------------------------
        assistant_message_id = final_state.get("assistant_message_id")
        if assistant_message_id:
            assistant_msg_doc = await self._msg_repo.list_by_conversation(
                conversation_id, limit=1, skip=0
            )
            # Get the latest assistant message directly
            recent = await self._msg_repo.get_recent(conversation_id, n=1)
            assistant_msg_raw = recent[0] if recent else None
        else:
            assistant_msg_raw = None

        # Fallback if something went wrong with persistence
        if not assistant_msg_raw:
            from app.utils.timestamps import utc_now
            assistant_msg_raw = {
                "id": "unknown",
                "role": MessageRole.ASSISTANT,
                "content": final_state.get("final_response", ""),
                "structured_payload": final_state.get("structured_response_payload"),
                "created_at": utc_now(),
                "conversation_id": conversation_id,
            }

        # ----------------------------------------------------------------
        # 7. Fetch the updated agent run
        # ----------------------------------------------------------------
        updated_run = await self._run_repo.get_by_id(agent_run_id)

        # ----------------------------------------------------------------
        # 8. Build the tool result envelope (if applicable)
        # ----------------------------------------------------------------
        tool_result_out: ToolResultEnvelope | None = None
        tool_result_data = final_state.get("tool_result")
        selected_tool = final_state.get("selected_tool")

        if tool_result_data and selected_tool:
            tool_obj = get_tool(selected_tool)
            tool_result_out = ToolResultEnvelope(
                tool_name=selected_tool,
                tool_version=tool_obj.version if tool_obj else "unknown",
                status="completed" if not final_state.get("tool_error") else "failed",
                payload=tool_result_data,
                warnings=final_state.get("tool_warnings", []),
            )

        # ----------------------------------------------------------------
        # 9. Assemble and return response
        # ----------------------------------------------------------------
        updated_conv = await self._conv_repo.get_by_id(conversation_id)

        return ChatMessageResponse(
            conversation=ConversationOut(
                id=updated_conv["id"],
                title=updated_conv["title"],
                user_id=updated_conv["user_id"],
                status=updated_conv["status"],
                created_at=updated_conv["created_at"],
                updated_at=updated_conv["updated_at"],
            ),
            user_message=UserMessageOut(
                id=user_msg["id"],
                content=user_msg["content"],
                created_at=user_msg["created_at"],
            ),
            assistant_message=AssistantMessageOut(
                id=assistant_msg_raw["id"],
                content=assistant_msg_raw["content"],
                structured_payload=assistant_msg_raw.get("structured_payload"),
                created_at=assistant_msg_raw["created_at"],
            ),
            agent_run=AgentRunSummary(
                id=agent_run_id,
                intent=updated_run.get("intent") if updated_run else None,
                selected_tool=updated_run.get("selected_tool") if updated_run else None,
                status=updated_run.get("status", "unknown") if updated_run else "unknown",
            ),
            tool_result=tool_result_out,
        )
