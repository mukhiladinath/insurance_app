"""
persist_node.py — Orchestrator node: persist all multi-step run results to MongoDB.

Saves:
  - Assistant message (final_response + structured_payload)
  - AgentRun record (completed, with plan metadata)
  - One ToolCall record per executed step
  - Conversation touch (updated_at / last_message_at)

This is the orchestrator equivalent of the legacy persist_results node.
It handles multiple tool calls per run (one per plan step) instead of the
legacy single-tool-per-run model.

State reads:
  conversation_id, agent_run_id, final_response, structured_response_payload,
  plan_steps, step_results, user_message_id

State writes:
  assistant_message_id
"""

import logging

from app.agents.state import AgentState
from app.core.constants import MessageRole, ToolCallStatus
from app.db.mongo import get_db
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.tool_call_repository import ToolCallRepository
from app.tools.registry import get_tool
from app.utils.timestamps import utc_now

logger = logging.getLogger(__name__)


async def orchestrate_persist(state: AgentState) -> dict:
    """
    Persist the full orchestrator run to MongoDB.

    Reads:  conversation_id, agent_run_id, final_response,
            structured_response_payload, plan_steps, step_results
    Writes: assistant_message_id
    """
    db = get_db()
    conversation_id = state["conversation_id"]
    agent_run_id = state["agent_run_id"]
    final_response = state.get("final_response", "")
    structured_payload = state.get("structured_response_payload")
    plan_steps: list[dict] = state.get("plan_steps", [])
    step_results: list[dict] = state.get("step_results", [])

    try:
        now = utc_now()

        # ---- 1. Save assistant message ----
        msg_repo = MessageRepository(db)
        assistant_msg = await msg_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_response,
            agent_run_id=agent_run_id,
            structured_payload=structured_payload,
        )

        # ---- 2. Complete agent run ----
        run_repo = AgentRunRepository(db)

        # Summarise what tools ran for the run record
        completed_tools = [
            r["tool_name"]
            for r in step_results
            if r.get("status") == "completed" and r.get("tool_name") != "direct_response"
        ]
        clarification = state.get("clarification_needed", False)
        intent = "clarification_needed" if clarification else (
            ",".join(completed_tools) if completed_tools else "direct_response"
        )

        await run_repo.complete(
            run_id=agent_run_id,
            final_response=final_response,
            intent=intent,
            selected_tool=completed_tools[0] if len(completed_tools) == 1 else None,
            tool_result_summary=(
                f"Orchestrator: {len(completed_tools)} tool(s) — {intent}"
            ),
            metadata={
                "orchestrator_mode": True,
                "plan_step_count": len(plan_steps),
                "completed_steps": len(completed_tools),
                "clarification_needed": clarification,
                "structured_payload_keys": list(structured_payload.keys()) if structured_payload else [],
            },
        )

        # ---- 3. Persist one ToolCall record per executed step ----
        tool_call_repo = ToolCallRepository(db)

        # Build a lookup from step_id → plan inputs
        inputs_by_step = {s["step_id"]: s.get("inputs", {}) for s in plan_steps}

        for result in step_results:
            tool_name = result.get("tool_name", "")
            if tool_name == "direct_response":
                continue  # no tool call record for informational steps

            tool_obj = get_tool(tool_name)
            version = tool_obj.version if tool_obj else "unknown"
            step_id = result["step_id"]
            status = result.get("status", "unknown")

            tc = await tool_call_repo.start(
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
                tool_name=tool_name,
                tool_version=version,
                input_payload=inputs_by_step.get(step_id, {}),
            )

            if status == "completed" and result.get("output"):
                await tool_call_repo.complete(
                    tool_call_id=tc["id"],
                    output_payload=result["output"],
                    warnings=[],
                )
            elif status == "failed":
                await tool_call_repo.fail(
                    tc["id"],
                    error=result.get("error", "Step failed"),
                )
            # skipped steps: leave as "started" (best effort)

        # ---- 4. Touch conversation ----
        conv_repo = ConversationRepository(db)
        await conv_repo.touch(conversation_id, last_message_at=now)

        logger.info(
            "orchestrate_persist: saved message %s for run %s (%d steps)",
            assistant_msg["id"], agent_run_id, len(step_results),
        )
        return {"assistant_message_id": assistant_msg["id"]}

    except Exception as exc:
        logger.exception("orchestrate_persist error: %s", exc)
        return {
            "assistant_message_id": None,
            "errors": state.get("errors", []) + [f"Persist error: {exc}"],
        }
