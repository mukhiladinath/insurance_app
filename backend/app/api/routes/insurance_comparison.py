"""
Insurance comparison API — structured compare across saved tool steps.

GET  /api/insurance-comparison/tool-runs?client_id=
POST /api/insurance-comparison/compare
POST /api/insurance-comparison/save
GET  /api/insurance-comparison/list?client_id=
GET  /api/insurance-comparison/{comparison_id}
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.db.mongo import get_db
from app.db.repositories.insurance_comparison_repository import InsuranceComparisonRepository
from app.insurance_comparison.schemas import (
    CompareRequestModel,
    InsuranceComparisonResultModel,
    SaveComparisonRequestModel,
    SavedComparisonSummaryModel,
    ToolRunListItemModel,
)
from app.insurance_comparison.service import (
    list_compare_eligible_steps,
    run_compare,
    save_comparison_record,
)

router = APIRouter(prefix="/insurance-comparison", tags=["insurance-comparison"])
logger = logging.getLogger(__name__)


@router.get("/tool-runs", response_model=list[ToolRunListItemModel])
async def list_tool_runs(
    client_id: str = Query(..., description="Client id"),
    limit: int = Query(100, le=200),
):
    db = get_db()
    try:
        rows = await list_compare_eligible_steps(db, client_id, limit=limit)
        return [ToolRunListItemModel(**r) for r in rows]
    except Exception as exc:
        logger.exception("list_tool_runs: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list tool runs.") from exc


@router.post("/compare", response_model=InsuranceComparisonResultModel)
async def compare(req: CompareRequestModel):
    db = get_db()
    try:
        result = await run_compare(
            db,
            client_id=req.clientId,
            left_tool_run_id=req.leftToolRunId,
            right_tool_run_id=req.rightToolRunId,
            weights=req.weights,
            fact_find_version=req.factFindVersion,
        )
        return InsuranceComparisonResultModel(**result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("compare: %s", exc)
        raise HTTPException(status_code=500, detail="Comparison failed.") from exc


@router.post("/save")
async def save_comparison(req: SaveComparisonRequestModel):
    db = get_db()
    try:
        doc = await save_comparison_record(
            db,
            client_id=req.clientId,
            left_tool_run_id=req.leftToolRunId,
            right_tool_run_id=req.rightToolRunId,
            comparison_type=req.comparisonType,
            comparison_result=req.comparisonResult,
            fact_find_version=req.factFindVersion,
            created_by=req.createdBy,
        )
        return {"ok": True, "id": doc["id"]}
    except Exception as exc:
        logger.exception("save_comparison: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to save comparison.") from exc


@router.get("/list", response_model=list[SavedComparisonSummaryModel])
async def list_comparisons(
    client_id: str = Query(..., description="Client id"),
    limit: int = Query(50, le=100),
):
    db = get_db()
    repo = InsuranceComparisonRepository(db)
    try:
        docs = await repo.list_by_client(client_id, limit=limit)
        out: list[SavedComparisonSummaryModel] = []
        for d in docs:
            out.append(
                SavedComparisonSummaryModel(
                    id=d["id"],
                    clientId=d.get("client_id", ""),
                    leftToolRunId=d.get("left_tool_run_id", ""),
                    rightToolRunId=d.get("right_tool_run_id", ""),
                    leftToolName=d.get("left_tool_name", ""),
                    rightToolName=d.get("right_tool_name", ""),
                    comparisonMode=d.get("comparison_mode", ""),
                    createdAt=d.get("created_at").isoformat() if d.get("created_at") else None,
                )
            )
        return out
    except Exception as exc:
        logger.exception("list_comparisons: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list comparisons.") from exc


@router.get("/{comparison_id}")
async def get_comparison(comparison_id: str):
    db = get_db()
    repo = InsuranceComparisonRepository(db)
    doc = await repo.get_by_id(comparison_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Comparison not found.")
    return {
        "id": doc["id"],
        "client_id": doc.get("client_id"),
        "left_tool_run_id": doc.get("left_tool_run_id"),
        "right_tool_run_id": doc.get("right_tool_run_id"),
        "left_tool_name": doc.get("left_tool_name"),
        "right_tool_name": doc.get("right_tool_name"),
        "comparison_type": doc.get("comparison_type"),
        "comparison_mode": doc.get("comparison_mode"),
        "comparison_result": doc.get("comparison_result"),
        "fact_find_version": doc.get("fact_find_version"),
        "created_by": doc.get("created_by"),
        "created_at": doc.get("created_at").isoformat() if doc.get("created_at") else None,
        "updated_at": doc.get("updated_at").isoformat() if doc.get("updated_at") else None,
    }
