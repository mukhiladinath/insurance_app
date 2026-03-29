"""
Insurance dashboard generation and persistence.

POST   /api/clients/{client_id}/insurance-dashboards/generate
GET    /api/clients/{client_id}/insurance-dashboards
GET    /api/clients/{client_id}/insurance-dashboards/{dashboard_id}
PATCH  /api/clients/{client_id}/insurance-dashboards/{dashboard_id}  — regenerate with new overrides
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.db.mongo import get_db
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.client_insurance_dashboard_repository import ClientInsuranceDashboardRepository
from app.services.insurance_dashboard.input_resolution import (
    build_resolved_inputs,
    detect_insurance_types_present,
    flat_resolved_to_override_paths,
    infer_dashboard_type,
)
from app.services.insurance_dashboard.projection_engine import normalize_projection_horizon
from app.services.insurance_dashboard.service import (
    DashboardGenerationError,
    compute_projection_bundle,
    generate_insurance_dashboard,
    insurance_kind_label,
)
from app.services.insurance_dashboard.spec_builder import build_dashboard_spec

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clients", tags=["insurance-dashboards"])


class GenerateDashboardBody(BaseModel):
    instruction: str | None = None
    dashboard_type: str | None = Field(None, description="auto | insurance_needs | premium_affordability | ...")
    analysis_output_id: str | None = None
    step_index: int | None = None
    second_analysis_output_id: str | None = None
    second_step_index: int | None = None
    session_token: str | None = None
    overrides: dict[str, Any] = Field(default_factory=dict)


class RegenerateBody(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)


class DashboardOut(BaseModel):
    id: str
    client_id: str
    title: str
    dashboard_type: str
    dashboard_spec: dict[str, Any]
    projection_data: dict[str, Any]
    resolved_inputs: dict[str, Any]
    assumptions: dict[str, Any]
    version: int
    status: str
    created_at: Any
    updated_at: Any


class DashboardListOut(BaseModel):
    client_id: str
    dashboards: list[DashboardOut]


def _to_out(doc: dict) -> DashboardOut:
    return DashboardOut(
        id=doc["id"],
        client_id=doc["client_id"],
        title=doc.get("title", ""),
        dashboard_type=doc.get("dashboard_type", ""),
        dashboard_spec=doc.get("dashboard_spec") or {},
        projection_data=doc.get("projection_data") or {},
        resolved_inputs=doc.get("resolved_inputs") or {},
        assumptions=doc.get("assumptions") or {},
        version=int(doc.get("version") or 1),
        status=doc.get("status", "active"),
        created_at=doc.get("created_at"),
        updated_at=doc.get("updated_at"),
    )


async def _require_client(client_id: str) -> None:
    db = get_db()
    repo = ClientRepository(db)
    if not await repo.get_by_id(client_id):
        raise HTTPException(status_code=404, detail="Client not found.")


@router.post("/{client_id}/insurance-dashboards/generate")
async def generate_dashboard(client_id: str, body: GenerateDashboardBody):
    await _require_client(client_id)
    db = get_db()
    try:
        result = await generate_insurance_dashboard(
            db,
            client_id=client_id,
            user_id=None,
            instruction=body.instruction,
            dashboard_type=body.dashboard_type,
            analysis_output_id=body.analysis_output_id,
            step_index=body.step_index,
            second_analysis_output_id=body.second_analysis_output_id,
            second_step_index=body.second_step_index,
            session_token=body.session_token,
            overrides=body.overrides or {},
        )
        return result
    except DashboardGenerationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("generate_dashboard: %s", exc)
        raise HTTPException(status_code=500, detail="Dashboard generation failed.") from exc


@router.get("/{client_id}/insurance-dashboards", response_model=DashboardListOut)
async def list_dashboards(client_id: str, limit: int = Query(50, ge=1, le=200)):
    await _require_client(client_id)
    db = get_db()
    repo = ClientInsuranceDashboardRepository(db)
    docs = await repo.list_for_client(client_id, limit=limit)
    return DashboardListOut(client_id=client_id, dashboards=[_to_out(d) for d in docs])


@router.get("/{client_id}/insurance-dashboards/{dashboard_id}", response_model=DashboardOut)
async def get_dashboard(client_id: str, dashboard_id: str):
    await _require_client(client_id)
    db = get_db()
    repo = ClientInsuranceDashboardRepository(db)
    doc = await repo.get(dashboard_id, client_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    return _to_out(doc)


@router.patch("/{client_id}/insurance-dashboards/{dashboard_id}", response_model=DashboardOut)
async def regenerate_dashboard(client_id: str, dashboard_id: str, body: RegenerateBody):
    await _require_client(client_id)
    db = get_db()
    repo = ClientInsuranceDashboardRepository(db)
    existing = await repo.get(dashboard_id, client_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    dtype = infer_dashboard_type(None, existing.get("dashboard_type"))
    merged_flat = {**(existing.get("resolved_inputs") or {}), **(body.overrides or {})}
    am = existing.get("assumptions") or {}
    override_paths = flat_resolved_to_override_paths(merged_flat)
    for k, v in (body.overrides or {}).items():
        if "." in k or k.startswith("dashboard."):
            override_paths[k] = v

    resolved = await build_resolved_inputs(
        db,
        client_id,
        analysis_output_id=am.get("primary_analysis_output_id"),
        step_index=am.get("primary_step_index"),
        second_analysis_output_id=am.get("second_analysis_output_id"),
        second_step_index=am.get("second_step_index"),
        overrides=override_paths,
    )

    kinds = detect_insurance_types_present(resolved.get("primary_normalized"), resolved)
    if not kinds:
        kinds = ["life"]

    bundles_by_kind: dict[str, Any] = {}
    projection_by_kind: dict[str, Any] = {}
    try:
        for k in kinds:
            b = compute_projection_bundle(dtype, resolved, insurance_kind=k)
            projection_by_kind[k] = b.pop("projection_data")
            bundles_by_kind[k] = b
    except DashboardGenerationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    first_kind = kinds[0]
    bundle = bundles_by_kind[first_kind]
    projection_data = {**projection_by_kind[first_kind], "insuranceDashboards": projection_by_kind}

    client_repo = ClientRepository(db)
    client_doc = await client_repo.get_by_id(client_id)
    client_name = client_doc.get("name") if client_doc else None

    resolved = dict(resolved)
    horizon_disp = normalize_projection_horizon(resolved.get("projection_horizon"))
    ypa: list[str] = []
    for _k in kinds:
        ypa.extend((projection_by_kind[_k].get("yearlyProjection") or {}).get("projectionAssumptions") or [])
    resolved["assumptions_table"] = [
        {"label": "Annual gross income", "value": resolved.get("annual_gross_income"), "format": "currency"},
        {"label": "Dependants", "value": resolved.get("dependants_count"), "format": "number"},
        {"label": "Projection horizon (years)", "value": resolved.get("projection_horizon") or horizon_disp, "format": "number"},
        {"label": "Years to independence (taper fallback)", "value": resolved.get("years_independence_horizon"), "format": "number"},
        {"label": "Dependent support taper (years)", "value": resolved.get("dependent_support_decay_years"), "format": "number"},
        {"label": "Income support taper (years)", "value": resolved.get("income_support_years"), "format": "number"},
        {"label": "Debt payoff (years)", "value": resolved.get("debt_payoff_years"), "format": "number"},
        {"label": "Premium tolerance (of income)", "value": resolved.get("premium_tolerance_ratio"), "format": "ratio"},
        *[{"label": f"Note {i + 1}", "value": text, "format": "text"} for i, text in enumerate(ypa)],
    ]

    title = (existing.get("dashboard_spec") or {}).get("title") or "Insurance dashboard"
    spec = build_dashboard_spec(
        title=title,
        dashboard_type=dtype,
        client_name=client_name,
        source_label="Regenerated",
        resolved=resolved,
        projections=bundle,
    )
    spec["insuranceDashboards"] = {
        k: build_dashboard_spec(
            title=f"{title} — {insurance_kind_label(k)}",
            dashboard_type=dtype,
            client_name=client_name,
            source_label="Regenerated",
            resolved=resolved,
            projections=bundles_by_kind[k],
        )
        for k in kinds
    }

    assumptions = {
        "years_independence_horizon": resolved.get("years_independence_horizon"),
        "projection_horizon": horizon_disp,
        "dependency_decay": True,
        "primary_analysis_output_id": am.get("primary_analysis_output_id"),
        "primary_step_index": am.get("primary_step_index"),
        "second_analysis_output_id": am.get("second_analysis_output_id"),
        "second_step_index": am.get("second_step_index"),
        "yearly_series_length": len(projection_data.get("yearlySeries") or []),
        "insurance_kinds": kinds,
    }
    updated = await repo.update_regeneration(
        dashboard_id,
        client_id,
        assumptions=assumptions,
        resolved_inputs={
            k: v
            for k, v in resolved.items()
            if not k.endswith("_normalized") and not k.endswith("_meta")
        },
        projection_data=projection_data,
        dashboard_spec=spec,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    return _to_out(updated)
