"""
persist_results.py — Node: persist all results to MongoDB.

Saves:
  - assistant message (with structured payload)
  - completes the agent_run record
  - completes the tool_call record (if a tool was executed)
  - touches the conversation (updated_at / last_message_at)
"""

import logging
from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.tool_call_repository import ToolCallRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.core.constants import MessageRole, ToolCallStatus
from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


async def persist_results(state: AgentState) -> dict:
    """Persist assistant message, agent run, tool call, and conversation touch."""
    db = get_db()
    conversation_id = state["conversation_id"]
    agent_run_id = state["agent_run_id"]
    selected_tool = state.get("selected_tool")
    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    final_response = state.get("final_response", "")
    structured_payload = state.get("structured_response_payload")

    try:
        now = utc_now()

        # 1. Save assistant message
        msg_repo = MessageRepository(db)
        assistant_msg = await msg_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_response,
            agent_run_id=agent_run_id,
            structured_payload=structured_payload,
        )

        # 2. Complete agent run
        run_repo = AgentRunRepository(db)
        tool_result_summary = None
        if tool_result and selected_tool:
            if selected_tool == "purchase_retain_life_insurance_in_super":
                legal = tool_result.get("legal_status", "UNKNOWN")
                placement = tool_result.get("placement_assessment", {}).get("recommendation", "UNKNOWN")
                tool_result_summary = f"Legal status: {legal}. Placement: {placement}."
            elif selected_tool == "purchase_retain_life_tpd_policy":
                rec = tool_result.get("recommendation", {}).get("type", "UNKNOWN")
                tool_result_summary = f"Recommendation: {rec}."

        await run_repo.complete(
            run_id=agent_run_id,
            final_response=final_response,
            intent=state.get("intent"),
            selected_tool=selected_tool,
            tool_result_summary=tool_result_summary,
            metadata={"structured_payload_keys": list(structured_payload.keys()) if structured_payload else []},
        )

        # 3. Persist tool call if tool was executed
        if selected_tool:
            tool_call_repo = ToolCallRepository(db)
            from app.tools.registry import get_tool
            tool_obj = get_tool(selected_tool)
            version = tool_obj.version if tool_obj else "unknown"

            # Find the most recent started tool_call for this run
            existing_calls = await tool_call_repo.list_by_run(agent_run_id)
            started_call = next(
                (c for c in reversed(existing_calls) if c["status"] == "started"), None
            )

            if started_call:
                if tool_error:
                    await tool_call_repo.fail(started_call["id"], error=tool_error)
                else:
                    await tool_call_repo.complete(
                        tool_call_id=started_call["id"],
                        output_payload=tool_result or {},
                        warnings=state.get("tool_warnings", []),
                    )
            else:
                # Create and immediately close a tool call record
                tc = await tool_call_repo.start(
                    agent_run_id=agent_run_id,
                    conversation_id=conversation_id,
                    tool_name=selected_tool,
                    tool_version=version,
                    input_payload=state.get("extracted_tool_input") or {},
                )
                if tool_error:
                    await tool_call_repo.fail(tc["id"], error=tool_error)
                else:
                    await tool_call_repo.complete(
                        tool_call_id=tc["id"],
                        output_payload=tool_result or {},
                        warnings=state.get("tool_warnings", []),
                    )

        # 4. Touch conversation
        conv_repo = ConversationRepository(db)
        await conv_repo.touch(conversation_id, last_message_at=now)

        logger.info("persist_results: saved assistant message %s for run %s", assistant_msg["id"], agent_run_id)
        return {"assistant_message_id": assistant_msg["id"]}

    except Exception as exc:
        logger.exception("persist_results error: %s", exc)
        return {
            "assistant_message_id": None,
            "errors": state.get("errors", []) + [f"Persist error: {exc}"],
        }
