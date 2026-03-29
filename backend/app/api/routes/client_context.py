"""
client_context.py — Client AI memory management routes.

Mirrors finobi's /api/client-context/* endpoints but uses MongoDB instead of S3.

Routes:
  POST /{client_id}/upload-enrich        — Upload document → enrich memory
  POST /{client_id}/enrich-from-factfind — Sync factfind → memory
  GET  /{client_id}/memories             — Get all 9 category docs
  GET  /{client_id}/memories/{category}  — Get single category
  PUT  /{client_id}/memories/{category}  — Overwrite category content
  GET  /{client_id}/search               — Keyword search across memories
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from pydantic import BaseModel

from app.db.repositories.client_memory_repository import (
    MEMORY_CATEGORIES,
    CATEGORY_LABELS,
    get_memory,
    get_all_memories,
    upsert_memory,
    initialize_empty_memories,
    search_memories,
)
from app.db.repositories.factfind_repository import FactfindRepository as _FactfindRepo
from app.db.mongo import get_db
from app.services.memory_enrichment_service import enrich_from_document, enrich_from_factfind
from app.services.memory_merge_service import build_tool_input_from_memory
from app.services.memory_canonical_hints import (
    load_memory_canonical_hints,
    merge_memory_then_factfind,
    apply_canonical_overrides,
)
from app.services.insurance_tool_input_requirements import (
    ORCHESTRATOR_CRITICAL_FIELDS,
    compute_missing_critical_fields,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/client-context", tags=["client-context"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/webp",
    "text/plain",
    "text/csv",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class MemoryDoc(BaseModel):
    client_id: str
    category: str
    category_label: str
    content: str
    last_updated: str | None = None
    fact_count: int = 0
    sources: list[dict[str, Any]] = []


class MemoriesResponse(BaseModel):
    client_id: str
    memories: list[MemoryDoc]


class UpdateMemoryRequest(BaseModel):
    content: str


class EnrichResponse(BaseModel):
    updated_categories: list[str]
    facts_extracted: int
    filename: str | None = None
    source: str | None = None


class SearchResponse(BaseModel):
    client_id: str
    query: str
    results: list[MemoryDoc]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _doc_to_model(doc: dict[str, Any]) -> MemoryDoc:
    last_updated = doc.get("last_updated")
    if hasattr(last_updated, "isoformat"):
        last_updated = last_updated.isoformat()
    return MemoryDoc(
        client_id=doc["client_id"],
        category=doc["category"],
        category_label=CATEGORY_LABELS.get(doc["category"], doc["category"]),
        content=doc.get("content", ""),
        last_updated=last_updated,
        fact_count=doc.get("fact_count", 0),
        sources=doc.get("sources", []),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/{client_id}/upload-enrich", response_model=EnrichResponse)
async def upload_and_enrich(
    client_id: str,
    file: UploadFile = File(...),
):
    """
    Upload a document and enrich the client's AI memory from it.
    Supports: PDF, DOCX, PNG, JPG, WEBP, TXT, CSV (max 20MB).
    """
    content_type = file.content_type or "application/octet-stream"

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, DOCX, images, TXT, CSV.",
        )

    file_bytes = await file.read()

    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(file_bytes) // 1024 // 1024}MB). Max 20MB.",
        )

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")

    result = await enrich_from_document(
        client_id=client_id,
        file_bytes=file_bytes,
        filename=file.filename or "document",
        content_type=content_type,
    )

    return EnrichResponse(**result)


@router.post("/{client_id}/enrich-from-factfind", response_model=EnrichResponse)
async def enrich_from_factfind_route(client_id: str):
    """
    Sync the client's factfind data into their AI memory.
    Converts structured factfind fields into readable markdown memory entries.
    """
    db = get_db()
    repo = _FactfindRepo(db)
    # get_or_create ensures a factfind always exists (even if empty)
    factfind = await repo.get_or_create(client_id)

    sections = factfind.get("sections", {})
    result = await enrich_from_factfind(client_id=client_id, factfind_sections=sections)

    return EnrichResponse(**result)


@router.get("/{client_id}/memories", response_model=MemoriesResponse)
async def get_memories(client_id: str):
    """
    Get all AI memory documents for a client (up to 9 categories).
    Initialises empty stubs if none exist yet.
    """
    await initialize_empty_memories(client_id)
    docs = await get_all_memories(client_id)

    # Sort by canonical category order
    cat_order = {cat: i for i, cat in enumerate(MEMORY_CATEGORIES)}
    docs.sort(key=lambda d: cat_order.get(d.get("category", ""), 99))

    return MemoriesResponse(
        client_id=client_id,
        memories=[_doc_to_model(d) for d in docs],
    )


@router.get("/{client_id}/memories/{category}", response_model=MemoryDoc)
async def get_memory_category(client_id: str, category: str):
    """Get a single memory category document."""
    if category not in MEMORY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Valid: {', '.join(MEMORY_CATEGORIES)}",
        )

    doc = await get_memory(client_id, category)
    if not doc:
        # Return empty stub
        return MemoryDoc(
            client_id=client_id,
            category=category,
            category_label=CATEGORY_LABELS[category],
            content=f"## {CATEGORY_LABELS[category]}\n\nNo information recorded yet.",
            fact_count=0,
            sources=[],
        )

    return _doc_to_model(doc)


@router.put("/{client_id}/memories/{category}", response_model=MemoryDoc)
async def update_memory_category(
    client_id: str,
    category: str,
    body: UpdateMemoryRequest,
):
    """Directly overwrite a memory category's content (for manual editing)."""
    if category not in MEMORY_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Valid: {', '.join(MEMORY_CATEGORIES)}",
        )

    doc = await upsert_memory(
        client_id=client_id,
        category=category,
        content=body.content,
    )

    return _doc_to_model(doc) if doc else MemoryDoc(
        client_id=client_id,
        category=category,
        category_label=CATEGORY_LABELS[category],
        content=body.content,
    )


@router.get("/{client_id}/search", response_model=SearchResponse)
async def search_client_memories(
    client_id: str,
    query: str = Query(..., min_length=1),
):
    """Keyword search across all memory documents for a client."""
    docs = await search_memories(client_id=client_id, query=query)

    return SearchResponse(
        client_id=client_id,
        query=query,
        results=[_doc_to_model(d) for d in docs],
    )


# ---------------------------------------------------------------------------
# Build tool input — memory + factfind → nested per-tool input schema
# ---------------------------------------------------------------------------

# Insurance tool critical fields: single source in insurance_tool_input_requirements.py
_FACTFIND_SECTIONS = ["personal", "financial", "insurance", "health", "goals"]


class BuildToolInputRequest(BaseModel):
    tool_name: str
    overrides: dict[str, Any] = {}  # canonical "section.field" → user-supplied value


class MissingFieldDef(BaseModel):
    path: str        # path inside the tool input (e.g. "member.age")
    canonical: str   # canonical fact path (e.g. "personal.age")
    label: str       # human-readable label
    input_type: str  # "number" | "text" | "boolean"


class BuildToolInputResponse(BaseModel):
    tool_input: dict[str, Any]
    missing_fields: list[MissingFieldDef]


@router.post("/{client_id}/build-tool-input", response_model=BuildToolInputResponse)
async def build_tool_input_for_client(client_id: str, body: BuildToolInputRequest):
    """
    Build the nested per-tool input dict for a backend insurance tool (or other
    tool_name supported by build_tool_input_from_memory).

    Precedence for canonical client_facts (personal / financial / …):
      1. AI memory (client_memories markdown) — deterministic hints for age & annual income
      2. Structured factfind — fills any fields still missing after memory
      3. Request `overrides` — adviser values from the missing-field resume UI (wins over both)

    Returns partial tool_input plus missing_fields for critical paths still absent
    (frontend then pauses the orchestrator for user input).
    """
    db = get_db()
    repo = _FactfindRepo(db)
    factfind = await repo.get_or_create(client_id)
    sections = factfind.get("sections", {})

    # Extract canonical facts from factfind value fields
    canonical_facts: dict[str, dict] = {s: {} for s in _FACTFIND_SECTIONS}
    for section in _FACTFIND_SECTIONS:
        for field, field_data in sections.get(section, {}).items():
            if isinstance(field_data, dict):
                v = field_data.get("value")
                if v is not None:
                    canonical_facts[section][field] = v

    # Insurance tools: memory markdown first, then factfind gaps
    if body.tool_name in ORCHESTRATOR_CRITICAL_FIELDS:
        memory_hints = await load_memory_canonical_hints(client_id)
        canonical_facts = merge_memory_then_factfind(memory_hints, canonical_facts)

    apply_canonical_overrides(canonical_facts, body.overrides)

    # Build nested tool input using existing mapping logic
    tool_input = build_tool_input_from_memory(body.tool_name, {"client_facts": canonical_facts})

    missing_raw = compute_missing_critical_fields(body.tool_name, tool_input)
    missing = [MissingFieldDef(**c) for c in missing_raw]

    return BuildToolInputResponse(tool_input=tool_input, missing_fields=missing)
