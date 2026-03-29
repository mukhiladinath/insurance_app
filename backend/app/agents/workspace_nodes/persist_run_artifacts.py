"""
persist_run_artifacts.py — Persist all workspace run artifacts to MongoDB.

Saves:
  - Assistant message (final_response + structured_payload)
  - AgentRun record (completed, with tool_plan)
  - RunStep records (one per step, in run_steps collection)
  - Workspace context snapshot
  - Optionally: SavedToolRun (if save_run_as or auto-save logic)
  - Advisory notes (client-scoped, in client_workspaces)

State reads:  run_id, client_id, workspace_id, conversation_id,
              tool_plan, step_results, data_cards, final_response,
              structured_response_payload, factfind_snapshot, ai_context_hierarchy,
              save_run_as, user_id
State writes: assistant_message_id, saved_run_id, context_snapshot_id
"""

import logging
from datetime import timezone, datetime
from typing import Any

from app.agents.workspace_state import WorkspaceState
from app.core.constants import MessageRole, ToolCallStatus
from app.db.mongo import get_db
from app.db.repositories.agent_run_repository import AgentRunRepository
from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.db.repositories.saved_tool_run_repository import RunStepRepository, SavedToolRunRepository
from app.utils.timestamps import utc_now

# Reuse the advisory extractors from distill_advisory_node
from app.agents.orchestrator_nodes.distill_advisory_node import _EXTRACTORS, _generic_extract

logger = logging.getLogger(__name__)


async def persist_run_artifacts(state: WorkspaceState) -> dict:
    """
    Persist all run artifacts.

    Reads:  run_id, client_id, workspace_id, conversation_id, tool_plan,
            step_results, data_cards, final_response, structured_response_payload,
            factfind_snapshot, ai_context_hierarchy, save_run_as, user_id
    Writes: assistant_message_id, saved_run_id, context_snapshot_id
    """
    db = get_db()
    run_id = state.get("run_id", "")
    client_id = state.get("client_id", "")
    workspace_id = state.get("workspace_id", "")
    conversation_id = state.get("conversation_id", "")
    user_id = state.get("user_id", "")
    tool_plan: list[dict] = state.get("tool_plan", [])
    step_results: list[dict] = state.get("step_results", [])
    data_cards: list[dict] = state.get("data_cards", [])
    final_response = state.get("final_response", "")
    structured_payload = state.get("structured_response_payload")
    save_run_as = state.get("save_run_as")
    factfind_snapshot = state.get("factfind_snapshot", {})
    ai_context_hierarchy = state.get("ai_context_hierarchy", {})

    result: dict[str, Any] = {}
    now = utc_now()

    try:
        # ---- 1. Save assistant message ----
        msg_repo = MessageRepository(db)
        assistant_msg = await msg_repo.create(
            conversation_id=conversation_id,
            role=MessageRole.ASSISTANT,
            content=final_response,
            agent_run_id=run_id,
            structured_payload=structured_payload,
        )
        result["assistant_message_id"] = assistant_msg["id"]

        # ---- 2. Complete agent run ----
        completed_tools = [
            r["tool_name"] for r in step_results
            if r.get("status") in ("completed", "cached")
            and r.get("tool_name") != "direct_response"
        ]
        intent = ",".join(completed_tools) if completed_tools else "direct_response"

        run_repo = AgentRunRepository(db)
        await run_repo.complete(
            run_id=run_id,
            final_response=final_response,
            intent=intent,
            selected_tool=completed_tools[0] if len(completed_tools) == 1 else None,
            tool_result_summary=f"Workspace run: {len(completed_tools)} tool(s)",
            metadata={
                "workspace_mode": True,
                "client_id": client_id,
                "workspace_id": workspace_id,
                "plan_step_count": len(tool_plan),
                "completed_steps": len(completed_tools),
                "active_mode": state.get("active_mode"),
            },
        )

        # ---- 3. Save run steps ----
        inputs_by_step = {s["step_id"]: s.get("inputs", {}) for s in tool_plan}
        step_docs = []
        for r in step_results:
            step_docs.append({
                "run_id": run_id,
                "client_id": client_id,
                "step_id": r["step_id"],
                "tool_name": r["tool_name"],
                "inputs": inputs_by_step.get(r["step_id"], {}),
                "output": r.get("output"),
                "data_card": r.get("data_card"),
                "status": r["status"],
                "cache_source_run_id": r.get("cache_source_run_id"),
                "started_at": now,
                "completed_at": now,
                "error": r.get("error"),
            })
        if step_docs:
            step_repo = RunStepRepository(db)
            await step_repo.bulk_insert(step_docs)

        # ---- 4. Save workspace context snapshot ----
        ws_repo = WorkspaceRepository(db)
        snapshot_id = await ws_repo.save_context_snapshot(
            client_id=client_id,
            workspace_id=workspace_id,
            run_id=run_id,
            context_tree={
                "factfind_flat": factfind_snapshot,
                "ai_context_layers": {
                    k: {"label": v.get("label"), "data": v.get("data")}
                    for k, v in ai_context_hierarchy.items()
                },
                "tool_plan": tool_plan,
            },
        )
        result["context_snapshot_id"] = snapshot_id

        # ---- 5. Persist advisory notes (client-scoped) ----
        iso_now = datetime.now(timezone.utc).isoformat()
        for r in step_results:
            if r.get("status") not in ("completed", "cached"):
                continue
            tool_name = r.get("tool_name", "")
            if tool_name in ("direct_response", ""):
                continue
            output = r.get("output") or {}
            extractor = _EXTRACTORS.get(tool_name, _generic_extract)
            try:
                note = extractor(output)
            except Exception:
                note = _generic_extract(output)
            note["analysed_at"] = iso_now
            note["agent_run_id"] = run_id
            await ws_repo.upsert_advisory_note(
                client_id=client_id,
                tool_name=tool_name,
                note=note,
            )

        # ---- 6. Save as named tool run (if requested) ----
        if save_run_as:
            saved_repo = SavedToolRunRepository(db)
            tool_names = list({r["tool_name"] for r in step_results if r.get("tool_name") != "direct_response"})
            inputs_snapshot = {
                "factfind_snapshot": factfind_snapshot,
                "tool_plan": tool_plan,
            }
            saved_run = await saved_repo.save(
                client_id=client_id,
                workspace_id=workspace_id,
                run_id=run_id,
                name=save_run_as,
                tool_names=tool_names,
                inputs_snapshot=inputs_snapshot,
                step_results=step_results,
                data_cards=data_cards,
                summary=final_response[:500],
                saved_by=user_id,
            )
            result["saved_run_id"] = saved_run["id"]
            # Attach comparison_envelope to each completed step (canonical normalized facts).
            from app.insurance_comparison.envelope import enrich_step_results_with_envelopes

            enriched = enrich_step_results_with_envelopes(
                step_results,
                client_id=client_id,
                saved_run_id=saved_run["id"],
            )
            await saved_repo.update_step_results(saved_run["id"], enriched)
            logger.info("persist_run_artifacts: saved run as '%s' (id=%s)", save_run_as, saved_run["id"])

        # ---- 7. Touch conversation ----
        conv_repo = ConversationRepository(db)
        await conv_repo.touch(conversation_id, last_message_at=now)

        logger.info(
            "persist_run_artifacts: run=%s client=%s saved msg=%s snapshot=%s",
            run_id, client_id, result.get("assistant_message_id"), snapshot_id,
        )

    except Exception as exc:
        logger.exception("persist_run_artifacts error: %s", exc)
        result["errors"] = state.get("errors", []) + [f"Persist error: {exc}"]

    return result
