"""
clients.py — Client management API routes.

GET  /api/clients               → list clients for a user
POST /api/clients               → create a new client (also creates workspace + factfind)
GET  /api/clients/{client_id}   → get client detail
PATCH /api/clients/{client_id}  → update client profile fields
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.mongo import get_db
from app.db.repositories.client_repository import ClientRepository
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.schemas.workspace_schemas import (
    ClientOut,
    ClientListOut,
    CreateClientRequest,
    WorkspaceOut,
)

router = APIRouter(prefix="/clients", tags=["clients"])
logger = logging.getLogger(__name__)


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


@router.get("", response_model=ClientListOut)
async def list_clients(
    user_id: str = Query(..., description="Filter by adviser user_id"),
    status: str = Query("active", description="Filter by status: active | archived"),
):
    """
    List all clients for a given adviser user.
    """
    db = get_db()
    repo = ClientRepository(db)
    try:
        docs = await repo.list_by_user(user_id=user_id, status=status)
        return ClientListOut(clients=[_to_client_out(d) for d in docs])
    except Exception as exc:
        logger.exception("list_clients error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to list clients.")


@router.post("", response_model=ClientOut, status_code=201)
async def create_client(req: CreateClientRequest):
    """
    Create a new client record, initialise their workspace and empty factfind.
    """
    db = get_db()
    client_repo = ClientRepository(db)
    workspace_repo = WorkspaceRepository(db)
    factfind_repo = FactfindRepository(db)

    try:
        client = await client_repo.create(
            user_id=req.user_id,
            name=req.name,
            email=req.email,
            phone=req.phone,
            date_of_birth=req.date_of_birth,
        )
        client_id = client["id"]

        # Initialise workspace and factfind in parallel
        import asyncio
        await asyncio.gather(
            workspace_repo.get_or_create(client_id=client_id, user_id=req.user_id),
            factfind_repo.get_or_create(client_id=client_id),
        )

        logger.info("create_client: created client=%s name=%s", client_id, req.name)
        return _to_client_out(client)

    except Exception as exc:
        logger.exception("create_client error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to create client.")


@router.get("/{client_id}", response_model=ClientOut)
async def get_client(client_id: str):
    """Get a single client by ID."""
    db = get_db()
    repo = ClientRepository(db)
    try:
        client = await repo.get_by_id(client_id)
        if not client:
            raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found.")
        return _to_client_out(client)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("get_client error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to get client.")


@router.patch("/{client_id}", response_model=ClientOut)
async def update_client(client_id: str, fields: dict[str, Any]):
    """Update mutable client profile fields (name, email, phone, date_of_birth)."""
    allowed = {"name", "email", "phone", "date_of_birth"}
    invalid = set(fields.keys()) - allowed
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unknown fields: {invalid}")

    db = get_db()
    repo = ClientRepository(db)
    try:
        updated = await repo.update(client_id, fields)
        if not updated:
            raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found.")
        return _to_client_out(updated)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("update_client error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update client.")


# ─────────────────────────────────────────────────────────────────────────────
# Factfind sub-routes
# ─────────────────────────────────────────────────────────────────────────────

import json
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.core.llm import get_chat_model
from app.db.repositories.document_repository import DocumentRepository
from app.schemas.workspace_schemas import FactfindOut, PatchFactfindRequest, AcceptProposalRequest
from app.db.repositories.factfind_repository import FactfindRepository
from pydantic import BaseModel


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
    from app.schemas.workspace_schemas import FactfindProposalOut
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


@router.get("/{client_id}/factfind", response_model=FactfindOut)
async def get_factfind(client_id: str):
    """Get the canonical factfind for a client."""
    db = get_db()
    repo = FactfindRepository(db)
    try:
        doc = await repo.get_or_create(client_id)
        return _to_factfind_out(doc)
    except Exception as exc:
        logger.exception("get_factfind error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to load factfind.")


@router.patch("/{client_id}/factfind", response_model=FactfindOut)
async def patch_factfind(client_id: str, req: PatchFactfindRequest):
    """
    Apply manual or AI-extracted field changes to the factfind.
    Body: { "changes": { "personal.age": 42, "financial.super_balance": 150000 }, "source": "manual" }
    """
    if not req.changes:
        raise HTTPException(status_code=422, detail="changes must not be empty.")

    db = get_db()
    repo = FactfindRepository(db)
    try:
        # Validate source
        allowed_sources = {"manual", "ai_extracted", "document_extracted"}
        source = req.source if req.source in allowed_sources else "manual"

        updated = await repo.patch_fields(
            client_id=client_id,
            changes=req.changes,
            source=source,
            source_ref="api_direct",
            changed_by="user",
        )
        return _to_factfind_out(updated)
    except Exception as exc:
        logger.exception("patch_factfind error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to update factfind.")


@router.post("/{client_id}/factfind/proposals/{proposal_id}/accept", response_model=FactfindOut)
async def accept_factfind_proposal(
    client_id: str,
    proposal_id: str,
    req: AcceptProposalRequest,
):
    """Accept all or specific fields from a document extraction proposal."""
    db = get_db()
    repo = FactfindRepository(db)
    try:
        updated = await repo.accept_proposal(
            client_id=client_id,
            proposal_id=proposal_id,
            field_paths=req.field_paths,
            changed_by="user",
        )
        return _to_factfind_out(updated)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("accept_factfind_proposal error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to accept proposal.")


_FACTFIND_EXTRACT_SYSTEM = """\
You are an insurance data extraction specialist. Given document text, extract all \
available client fact-find fields.

## FACTFIND FIELD SCHEMA
personal:
  age (int), date_of_birth (ISO date str), gender (str), is_smoker (bool),
  occupation (str), occupation_class (str — CLASS_1_WHITE_COLLAR|CLASS_2_LIGHT_BLUE|CLASS_3_BLUE_COLLAR|CLASS_4_HAZARDOUS),
  marital_status (str — single|married|de_facto|divorced|widowed), dependants (int),
  employment_status (str — EMPLOYED_FULL_TIME|EMPLOYED_PART_TIME|SELF_EMPLOYED|UNEMPLOYED),
  weekly_hours_worked (int)

financial:
  annual_gross_income (float), annual_net_income (float), monthly_expenses (float),
  monthly_surplus (float), super_balance (float), fund_type (str — mysuper|choice|smsf|defined_benefit),
  fund_name (str), mortgage_balance (float), liquid_assets (float),
  total_liabilities (float), marginal_tax_rate (float), years_to_retirement (int)

insurance:
  has_existing_policy (bool), life_sum_insured (float), tpd_sum_insured (float),
  ip_monthly_benefit (float), trauma_sum_insured (float),
  insurer_name (str), annual_premium (float), in_super (bool),
  ip_waiting_period_days (int — 30|60|90), ip_benefit_period_months (int — 0 means to age 65),
  tpd_definition (str — OWN_OCCUPATION|ANY_OCCUPATION),
  ip_occupation_definition (str — OWN_OCCUPATION|ANY_OCCUPATION)

health:
  height_cm (int), weight_kg (int),
  medical_conditions (list of str), current_medications (list of str),
  hazardous_activities (list of str)

goals:
  goals_and_objectives (str — free-text narrative: client goals, objectives, priorities,
    time horizon, risk attitude, as stated in SOA "Objectives", fact-find prose, or similar),
  wants_replacement (bool), wants_retention (bool), affordability_is_concern (bool),
  wants_own_occupation (bool), cashflow_pressure (bool)

## RULES
1. Use section prefix: "personal.age", "financial.super_balance", etc.
2. Only extract values clearly stated in the document. Do NOT invent values.
3. For goals_and_objectives, copy or tightly paraphrase the document wording; omit if no narrative goals/objectives appear.
4. Provide confidence (0.0-1.0) per field.
5. Return ONLY valid JSON.

## OUTPUT FORMAT
{
  "extracted": {
    "personal.age": { "value": 42, "confidence": 0.95 },
    "personal.is_smoker": { "value": false, "confidence": 0.9 },
    "financial.annual_gross_income": { "value": 145000, "confidence": 0.9 },
    "insurance.life_sum_insured": { "value": 500000, "confidence": 0.85 },
    "goals.goals_and_objectives": { "value": "Client seeks to protect family income until children finish school and build retirement savings.", "confidence": 0.8 }
  }
}
"""


class ExtractFromUploadRequest(BaseModel):
    storage_ref: str


class ExtractedField(BaseModel):
    field_path: str
    value: Any
    confidence: float


class ExtractFromUploadResponse(BaseModel):
    fields_extracted: int
    fields: list[ExtractedField]
    message: str = ""


def _parse_json_safe(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return {}


@router.post("/{client_id}/factfind/extract-from-upload", response_model=ExtractFromUploadResponse)
async def extract_factfind_from_upload(client_id: str, body: ExtractFromUploadRequest):
    """
    Extract factfind fields from a previously-uploaded document and auto-apply
    them to the client's factfind. Only non-null extracted values are written.
    """
    db = get_db()
    doc_repo = DocumentRepository(db)
    factfind_repo = FactfindRepository(db)

    doc = await doc_repo.get_by_id(body.storage_ref)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Prefer already-extracted text; fall back to reading the file
    text: str = doc.get("extracted_text", "")
    if not text.strip():
        storage_path = doc.get("storage_path", "")
        if storage_path:
            try:
                from app.services.document_extractor import extract_text as _extract_text
                text = await _extract_text(storage_path, doc.get("content_type", "application/octet-stream"))
            except Exception as exc:
                logger.warning("extract_factfind_from_upload: text extraction failed: %s", exc)

    if not text.strip():
        return ExtractFromUploadResponse(
            fields_extracted=0,
            fields=[],
            message="No readable text found in this document.",
        )

    # LLM extraction
    extracted: dict = {}
    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=_FACTFIND_EXTRACT_SYSTEM),
            HumanMessage(content=f"## DOCUMENT TEXT\n{text[:7000]}\n\nExtract all available factfind fields now."),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_json_safe(raw)
        extracted = parsed.get("extracted", {})
    except Exception as exc:
        logger.exception("extract_factfind_from_upload: LLM failed: %s", exc)

    if not extracted:
        return ExtractFromUploadResponse(
            fields_extracted=0,
            fields=[],
            message="No fact-find fields could be extracted from this document.",
        )

    # Build changes dict — only include fields with actual values
    changes: dict = {}
    result_fields: list[ExtractedField] = []
    for field_path, field_data in extracted.items():
        if not isinstance(field_data, dict):
            continue
        value = field_data.get("value")
        confidence = float(field_data.get("confidence", 0.8))
        if value is None:
            continue
        changes[field_path] = value
        result_fields.append(ExtractedField(field_path=field_path, value=value, confidence=confidence))

    if changes:
        await factfind_repo.patch_fields(
            client_id=client_id,
            changes=changes,
            source="document_extracted",
            source_ref=body.storage_ref,
            changed_by="agent",
        )
        logger.info(
            "extract_factfind_from_upload: applied %d fields for client=%s from doc=%s",
            len(changes), client_id, body.storage_ref,
        )

    return ExtractFromUploadResponse(
        fields_extracted=len(changes),
        fields=result_fields,
        message=f"Extracted and saved {len(changes)} field(s) from the document.",
    )


class ObjectivesAutomationRunBody(BaseModel):
    force: bool = False


class ObjectivesAutomationRunOut(BaseModel):
    skipped: bool
    reason: str = ""
    tools_run: list[str] = []
    outputs_created: int = 0


@router.post("/{client_id}/objectives-automation/run", response_model=ObjectivesAutomationRunOut)
async def run_objectives_automation_route(
    client_id: str,
    body: ObjectivesAutomationRunBody = ObjectivesAutomationRunBody(),
):
    """
    If fact-find **Goals & objectives** text is non-empty, infer matching insurance
    tools, run them with current factfind (+ memory hints), and save one analysis
    output per tool with source=automated.

    Skips when objectives text unchanged since last run unless `force` is true.
    """
    from app.services.objectives_automation_service import run_objectives_automation

    db = get_db()
    client_repo = ClientRepository(db)
    if not await client_repo.get_by_id(client_id):
        raise HTTPException(status_code=404, detail="Client not found.")
    try:
        result = await run_objectives_automation(db, client_id, force=body.force)
        return ObjectivesAutomationRunOut(**result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("run_objectives_automation error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to run objectives automation.")


@router.delete("/{client_id}", status_code=200)
async def archive_client(client_id: str):
    """Soft-delete (archive) a client."""
    db = get_db()
    repo = ClientRepository(db)
    try:
        ok = await repo.archive(client_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"Client '{client_id}' not found.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("archive_client error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to archive client.")


@router.post("/{client_id}/factfind/proposals/{proposal_id}/reject", status_code=200)
async def reject_factfind_proposal(client_id: str, proposal_id: str):
    """Reject a document extraction proposal."""
    db = get_db()
    repo = FactfindRepository(db)
    try:
        await repo.reject_proposal(client_id, proposal_id)
        return {"ok": True}
    except Exception as exc:
        logger.exception("reject_factfind_proposal error: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to reject proposal.")
