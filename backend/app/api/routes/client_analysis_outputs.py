"""
client_analysis_outputs.py — CRUD for persisted analysis LLM outputs per client.

POST   /api/clients/{client_id}/analysis-outputs  — create (from Next after tool run)
GET    /api/clients/{client_id}/analysis-outputs  — list newest first
PATCH  /api/clients/{client_id}/analysis-outputs/{output_id} — edit saved markdown
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.mongo import get_db
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.client_analysis_output_repository import (
    ClientAnalysisOutputRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["client-analysis-outputs"])


class StructuredStepResultIn(BaseModel):
    """One completed insurance tool row from the orchestrator (short tool_id + raw output)."""

    tool_id: str
    status: str = "completed"
    output: dict[str, Any] | None = None


class AnalysisOutputCreate(BaseModel):
    instruction: str = ""
    tool_ids: list[str] = Field(default_factory=list)
    step_labels: list[str] = Field(default_factory=list)
    content: str = ""
    source: str = "manual"
    structured_step_results: list[StructuredStepResultIn] = Field(default_factory=list)


class AnalysisOutputPatch(BaseModel):
    content: str


class AnalysisOutputOut(BaseModel):
    id: str
    client_id: str
    instruction: str
    tool_ids: list[str]
    step_labels: list[str]
    content: str
    source: str = "manual"
    created_at: Any
    updated_at: Any


class AnalysisOutputListOut(BaseModel):
    client_id: str
    outputs: list[AnalysisOutputOut]


def _to_out(doc: dict) -> AnalysisOutputOut:
    ca = doc.get("created_at")
    ua = doc.get("updated_at")
    return AnalysisOutputOut(
        id=doc["id"],
        client_id=doc["client_id"],
        instruction=doc.get("instruction", ""),
        tool_ids=doc.get("tool_ids") or [],
        step_labels=doc.get("step_labels") or [],
        content=doc.get("content", ""),
        source=doc.get("source") or "manual",
        created_at=ca.isoformat() if hasattr(ca, "isoformat") else ca,
        updated_at=ua.isoformat() if hasattr(ua, "isoformat") else ua,
    )


async def _require_client(client_id: str) -> None:
    db = get_db()
    repo = ClientRepository(db)
    if not await repo.get_by_id(client_id):
        raise HTTPException(status_code=404, detail="Client not found.")


@router.post("/{client_id}/analysis-outputs", response_model=AnalysisOutputOut, status_code=201)
async def create_analysis_output(client_id: str, body: AnalysisOutputCreate):
    await _require_client(client_id)
    db = get_db()
    repo = ClientAnalysisOutputRepository(db)
    structured = [s.model_dump() for s in body.structured_step_results]
    doc = await repo.create(
        client_id=client_id,
        instruction=body.instruction,
        tool_ids=body.tool_ids,
        step_labels=body.step_labels,
        content=body.content,
        source=body.source if body.source in ("manual", "automated") else "manual",
        structured_step_results=structured,
    )
    return _to_out(doc)


@router.get("/{client_id}/analysis-outputs", response_model=AnalysisOutputListOut)
async def list_analysis_outputs(client_id: str):
    await _require_client(client_id)
    db = get_db()
    repo = ClientAnalysisOutputRepository(db)
    docs = await repo.list_for_client(client_id)
    return AnalysisOutputListOut(
        client_id=client_id,
        outputs=[_to_out(d) for d in docs],
    )


@router.patch("/{client_id}/analysis-outputs/{output_id}", response_model=AnalysisOutputOut)
async def patch_analysis_output(client_id: str, output_id: str, body: AnalysisOutputPatch):
    await _require_client(client_id)
    db = get_db()
    repo = ClientAnalysisOutputRepository(db)
    doc = await repo.update_content(output_id, client_id, body.content)
    if not doc:
        raise HTTPException(status_code=404, detail="Analysis output not found.")
    return _to_out(doc)
