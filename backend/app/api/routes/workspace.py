"""
workspace.py — Client workspace API routes.

GET  /api/workspace/{client_id}              → full workspace overview
POST /api/workspace/{client_id}/run          → AI bar: run agent
GET  /api/workspace/{client_id}/ai-context   → get hierarchical AI context
PATCH /api/workspace/{client_id}/ai-context  → update AI context overrides
GET  /api/workspace/{client_id}/saved-runs   → list saved tool runs
GET  /api/workspace/{client_id}/saved-runs/{id} → get saved run detail
POST /api/workspace/{client_id}/saved-runs/{id}/save → name a run
DELETE /api/workspace/{client_id}/saved-runs/{id}    → delete a saved run
GET  /api/workspace/{client_id}/pending-clarification → get pending clarification
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.db.mongo import get_db
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.db.repositories.pending_clarification_repository import PendingClarificationRepository
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.saved_tool_run_repository import SavedToolRunRepository
from app.schemas.workspace_schemas import (
    AiContextLayerOut,
    AiContextOut,
    ClientOut,
    DataCardOut,
    FactfindOut,
    FactfindProposalOut,
    PatchAiContextRequest,
    PendingClarificationOut,
    MissingFieldOut,
    SavedRunDetailOut,
    SavedRunListOut,
    SavedRunSummaryOut,
    SaveRunRequest,
    StepResultOut,
    WorkspaceOut,
    WorkspaceRunRequest,
    WorkspaceRunResponse,
)
from app.services.workspace_orchestrator_service import WorkspaceOrchestratorService

router = APIRouter(prefix="/workspace", tags=["workspace"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_client_out(doc: dict) -> ClientOut:
    return ClientOut(
        id=doc["id"],
        user_id=doc["user_id"],
        name=doc["name"],
        email=doc.get("email"),
        phone=doc.get("phone"),
        date_of_birth=doc.get("date_of_birth"),
        status=doc.get("status", "active"),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _completeness(factfind: dict) -> float:
    sections = factfind.get("sections", {})
    total = sum(len(fields) for fields in sections.values())
    confirmed = sum(
        1 for fields in sections.values()
        for field_data in fields.values()
        if isinstance(field_data, dict) and field_data.get("status") in ("confirmed", "inferred")
        and field_data.get("value") is not None
    )
    return round(confirmed / max(total, 1), 2)


def _to_factfind_out(doc: dict) -> FactfindOut:
    proposals = [
        FactfindProposalOut(
            proposal_id=p["proposal_id"],
            source_document_id=p.get("source_document_id", ""),
            proposed_fields=p.get("proposed_fields", {}),
            status=p.get("status", "pending"),
            created_at=p["created_at"],
        )
        for p in doc.get("pending_proposals", [])
    ]
    return FactfindOut(
        client_id=doc["client_id"],
        version=doc.get("version", 0),
        sections=doc.get("sections", {}),
        pending_proposals=proposals,
        completeness_pct=_completeness(doc),
        updated_at=doc.get("updated_at"),
    )


def _to_ai_context_out(workspace: dict) -> AiContextOut:
    overrides = workspace.get("ai_context_overrides", {})
    advisory = workspace.get("advisory_notes", {})
    scratch = workspace.get("scratch_pad", [])

    layers = {
        "assumptions": AiContextLayerOut(
            label="Assumptions",
            user_can_view=True,
            user_can_edit=True,
            system_owned=False,
            affects_planning=True,
            data={**{"inflation_rate": 0.03, "investment_return": 0.07, "risk_profile": "balanced"}, **overrides.get("assumptions", {})},
        ),
        "advisory_notes": AiContextLayerOut(
            label="Prior Analysis Conclusions",
            user_can_view=True,
            user_can_edit=False,
            system_owned=True,
            affects_planning=True,
            data=advisory,
        ),
        "scratchpad": AiContextLayerOut(
            label="Agent Working Notes",
            user_can_view=True,
            user_can_edit=True,
            system_owned=False,
            affects_planning=True,
            data=scratch + overrides.get("scratchpad", []),
        ),
    }
    return AiContextOut(layers=layers, overrides=overrides)


def _to_saved_run_summary(doc: dict) -> SavedRunSummaryOut:
    return SavedRunSummaryOut(
        id=doc["id"],
        name=doc["name"],
        tool_names=doc.get("tool_names", []),
        summary=doc.get("summary", ""),
        saved_at=doc["saved_at"],
        tags=doc.get("tags", []),
    )


# ---------------------------------------------------------------------------
# Workspace overview
# ---------------------------------------------------------------------------

@router.get("/{client_id}", response_model=WorkspaceOut)
async def get_workspace(client_id: str):
    """Return the full client workspace overview."""
    db = get_db()
    client_repo = ClientRepository(db)
    workspace_repo = WorkspaceRepository(db)
    factfind_repo = FactfindRepository(db)
    clarif_repo = PendingClarificationRepository(db)
    saved_repo = SavedToolRunRepository(db)

    import asyncio
    try:
        client, workspace, factfind, pending, saved_runs = await asyncio.gather(
            client_repo.get_by_id(client_id),
            workspace_repo.get_or_create(client_id, ""),
            factfind_repo.get_or_create(client_id),
            clarif_repo.get_pending_for_client(client_id),
            saved_repo.list_by_client(client_id, limit=10),
        )
    except Exception as exc:
        logger.exception("get_workspace error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load workspace.")

    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found.")

    pending_out: PendingClarificationOut | None = None
    if pending:
        pending_out = PendingClarificationOut(
            resume_token=pending["resume_token"],
            question=pending["question"],
            missing_fields=[
                MissingFieldOut(
                    field_path=f.get("field_path", ""),
                    label=f.get("label", ""),
                    section=f.get("section", ""),
                    required=f.get("required", True),
                )
                for f in pending.get("missing_fields", [])
            ],
            created_at=pending["created_at"],
        )

    return WorkspaceOut(
        workspace_id=workspace["id"],
        client=_to_client_out(client),
        factfind=_to_factfind_out(factfind),
        advisory_notes=workspace.get("advisory_notes", {}),
        scratch_pad=workspace.get("scratch_pad", []),
        active_conversation_id=workspace.get("active_conversation_id"),
        saved_runs=[_to_saved_run_summary(r) for r in saved_runs],
        ai_context=_to_ai_context_out(workspace),
        pending_clarification=pending_out,
    )


class WorkspaceDocumentOut(BaseModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    facts_found: bool
    facts_summary: str
    created_at: datetime


@router.get("/{client_id}/documents", response_model=list[WorkspaceDocumentOut])
async def list_workspace_documents(client_id: str):
    """
    List uploaded files for this client (AI bar / legacy upload).

    Uses client_id on the document when set, and/or conversation_id matching
    the workspace active conversation so files appear before the first run.
    """
    db = get_db()
    client_repo = ClientRepository(db)
    workspace_repo = WorkspaceRepository(db)
    doc_repo = DocumentRepository(db)

    client = await client_repo.get_by_id(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found.")

    workspace = await workspace_repo.get_by_client(client_id)
    if not workspace:
        workspace = await workspace_repo.get_or_create(client_id, client["user_id"])

    user_id = client["user_id"]
    conversation_id = workspace.get("active_conversation_id")

    docs = await doc_repo.list_for_client(client_id, user_id, conversation_id)

    result: list[WorkspaceDocumentOut] = []
    for d in docs:
        facts = d.get("extracted_facts") or {}
        result.append(
            WorkspaceDocumentOut(
                id=d["id"],
                filename=d.get("filename", "unknown"),
                content_type=d.get("content_type", ""),
                size_bytes=d.get("size_bytes", 0),
                facts_found=bool(facts),
                facts_summary=", ".join(facts.keys()) if facts else "No facts extracted",
                created_at=d.get("created_at")
                or datetime(1970, 1, 1, tzinfo=timezone.utc),
            )
        )
    return result


# ---------------------------------------------------------------------------
# Main AI bar run endpoint
# ---------------------------------------------------------------------------

@router.post("/{client_id}/run", response_model=WorkspaceRunResponse)
async def run_workspace(client_id: str, req: WorkspaceRunRequest):
    """
    Execute a user instruction through the workspace agent.

    Handles all modes:
      - Tool runs (default)
      - Clarification resumes (resume_token)
      - Patch reruns (rerun_from_saved_run_id + patched_inputs)
      - Document extraction (attached_files)
      - Factfind updates (AI bar edits)
    """
    db = get_db()
    service = WorkspaceOrchestratorService(db)
    try:
        return await service.run(client_id=client_id, req=req)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except Exception as exc:
        logger.exception("run_workspace error for client=%s: %s", client_id, exc)
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")


# ---------------------------------------------------------------------------
# AI Context panel
# ---------------------------------------------------------------------------

@router.get("/{client_id}/ai-context", response_model=AiContextOut)
async def get_ai_context(client_id: str):
    """Return the hierarchical AI context for a client workspace."""
    db = get_db()
    repo = WorkspaceRepository(db)
    try:
        workspace = await repo.get_by_client(client_id)
        if not workspace:
            raise HTTPException(status_code=404, detail=f"Workspace for client '{client_id}' not found.")
        return _to_ai_context_out(workspace)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_ai_context error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load AI context.")


@router.patch("/{client_id}/ai-context", response_model=AiContextOut)
async def patch_ai_context(client_id: str, req: PatchAiContextRequest):
    """
    Update AI context overrides for a client workspace.
    Body: { "overrides": { "assumptions.risk_profile": "aggressive" } }
    """
    db = get_db()
    repo = WorkspaceRepository(db)
    try:
        updated = await repo.patch_ai_context_overrides(client_id, req.overrides)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Workspace for client '{client_id}' not found.")
        return _to_ai_context_out(updated)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("patch_ai_context error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update AI context.")


# ---------------------------------------------------------------------------
# Saved tool runs
# ---------------------------------------------------------------------------

@router.get("/{client_id}/saved-runs", response_model=SavedRunListOut)
async def list_saved_runs(
    client_id: str,
    tool_name: str | None = Query(None, description="Filter by tool name"),
    limit: int = Query(20, le=100),
):
    """List saved tool runs for a client."""
    db = get_db()
    repo = SavedToolRunRepository(db)
    try:
        runs = await repo.list_by_client(client_id, tool_name=tool_name, limit=limit)
        return SavedRunListOut(saved_runs=[_to_saved_run_summary(r) for r in runs])
    except Exception as exc:
        logger.exception("list_saved_runs error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list saved runs.")


@router.get("/{client_id}/saved-runs/{saved_run_id}", response_model=SavedRunDetailOut)
async def get_saved_run(client_id: str, saved_run_id: str):
    """Get full detail for a saved tool run."""
    db = get_db()
    repo = SavedToolRunRepository(db)
    try:
        run = await repo.get_by_id(saved_run_id)
        if not run or run.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail=f"Saved run '{saved_run_id}' not found.")

        return SavedRunDetailOut(
            id=run["id"],
            client_id=run["client_id"],
            workspace_id=run.get("workspace_id", ""),
            run_id=run.get("run_id", ""),
            name=run["name"],
            tool_names=run.get("tool_names", []),
            inputs_snapshot=run.get("inputs_snapshot", {}),
            step_results=[
                StepResultOut(
                    step_id=r["step_id"],
                    tool_name=r["tool_name"],
                    description=r.get("description", ""),
                    status=r["status"],
                    error=r.get("error"),
                    cache_source_run_id=r.get("cache_source_run_id"),
                )
                for r in run.get("step_results", [])
            ],
            data_cards=[
                DataCardOut(
                    step_id=c.get("step_id", ""),
                    tool_name=c.get("tool_name", ""),
                    type=c.get("type", "generic"),
                    title=c.get("title", "Result"),
                    display_hint=c.get("display_hint", "table"),
                    data=c.get("data", {}),
                )
                for c in run.get("data_cards", [])
            ],
            summary=run.get("summary", ""),
            saved_at=run["saved_at"],
            tags=run.get("tags", []),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_saved_run error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load saved run.")


@router.post("/{client_id}/saved-runs/{saved_run_id}/save", status_code=200)
async def save_run(client_id: str, saved_run_id: str, req: SaveRunRequest):
    """Update the name and tags of a saved tool run."""
    db = get_db()
    repo = SavedToolRunRepository(db)
    try:
        updated = await repo.update_name(saved_run_id, req.name, req.tags)
        if not updated or updated.get("client_id") != client_id:
            raise HTTPException(status_code=404, detail=f"Saved run '{saved_run_id}' not found.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("save_run error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update saved run.")


@router.delete("/{client_id}/saved-runs/{saved_run_id}", status_code=200)
async def delete_saved_run(client_id: str, saved_run_id: str):
    """Delete a saved tool run."""
    db = get_db()
    repo = SavedToolRunRepository(db)
    try:
        deleted = await repo.delete(saved_run_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Saved run '{saved_run_id}' not found.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("delete_saved_run error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to delete saved run.")


# ---------------------------------------------------------------------------
# Pending clarification
# ---------------------------------------------------------------------------

@router.get("/{client_id}/pending-clarification", response_model=PendingClarificationOut | None)
async def get_pending_clarification(client_id: str):
    """Return the current pending clarification for a client, if any."""
    db = get_db()
    repo = PendingClarificationRepository(db)
    try:
        doc = await repo.get_pending_for_client(client_id)
        if not doc:
            return None
        return PendingClarificationOut(
            resume_token=doc["resume_token"],
            question=doc["question"],
            missing_fields=[
                MissingFieldOut(
                    field_path=f.get("field_path", ""),
                    label=f.get("label", ""),
                    section=f.get("section", ""),
                    required=f.get("required", True),
                )
                for f in doc.get("missing_fields", [])
            ],
            created_at=doc["created_at"],
        )
    except Exception as exc:
        logger.exception("get_pending_clarification error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load pending clarification.")
