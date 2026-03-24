"""
upload.py — Document upload endpoint.

POST /api/upload
  Accepts a multipart file upload along with user_id and optional conversation_id.

  Steps:
    1. Validate file type and size.
    2. Save file to local uploads/ directory.
    3. Extract text from file (pdfplumber / python-docx / vision).
    4. Extract canonical client facts from text using Azure OpenAI.
    5. Persist document record to MongoDB.
    6. If conversation_id is provided, immediately merge extracted facts
       into that conversation's memory.
    7. Return storage_ref + extraction summary.

Response: DocumentUploadResponse
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.db.mongo import get_db
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.services.document_extractor import extract_text, extract_client_facts, facts_summary
from app.services.memory_merge_service import merge_delta

from fastapi.responses import FileResponse as _FileResponse

router = APIRouter(prefix="/upload", tags=["upload"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Base directory where uploaded files are stored.
# Path is relative to the backend root (where uvicorn is launched from).
_UPLOAD_ROOT = Path("uploads")

_ALLOWED_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
}

_MAX_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class DocumentUploadResponse(BaseModel):
    storage_ref: str            # document _id — passed back in attached_files
    filename: str
    content_type: str
    size_bytes: int
    extracted_text_preview: str  # first 300 chars of extracted text
    facts_found: bool            # whether any client facts were extracted
    facts_summary: str           # short human-readable summary of found facts


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.post("", response_model=DocumentUploadResponse)
async def upload_document(
    file:            UploadFile = File(...),
    user_id:         str        = Form(...),
    conversation_id: str | None = Form(default=None),
):
    """
    Upload a document, extract its text and client facts, persist to DB.
    """
    # ------------------------------------------------------------------
    # 1. Validate
    # ------------------------------------------------------------------
    content_type = file.content_type or ""
    # Normalise .jpg → jpeg
    if content_type == "image/jpg":
        content_type = "image/jpeg"

    if content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {content_type}. Allowed: PDF, DOCX, PNG, JPEG, WEBP.",
        )

    file_bytes = await file.read()
    size_bytes = len(file_bytes)

    if size_bytes > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_bytes // 1024 // 1024} MB). Maximum is 20 MB.",
        )

    if size_bytes == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # ------------------------------------------------------------------
    # 2. Save file to disk
    # ------------------------------------------------------------------
    doc_id = str(uuid.uuid4()).replace("-", "")
    safe_filename = Path(file.filename or "upload").name  # strip directory traversal
    upload_dir = _UPLOAD_ROOT / doc_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / safe_filename

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(file_bytes)

    storage_path = str(file_path)
    logger.info("Saved upload: %s (%d bytes)", file_path, size_bytes)

    # ------------------------------------------------------------------
    # 3. Extract text
    # ------------------------------------------------------------------
    try:
        extracted_text = await extract_text(storage_path, content_type)
    except Exception as exc:
        logger.warning("Text extraction failed: %s", exc)
        extracted_text = ""

    # ------------------------------------------------------------------
    # 4. Extract client facts
    # ------------------------------------------------------------------
    extracted_facts: dict = {}
    try:
        extracted_facts = await extract_client_facts(extracted_text, safe_filename)
    except Exception as exc:
        logger.warning("Fact extraction failed: %s", exc)

    # ------------------------------------------------------------------
    # 5. Persist document record to MongoDB
    # ------------------------------------------------------------------
    db = get_db()
    doc_repo = DocumentRepository(db)

    doc_record = await doc_repo.create(
        user_id=user_id,
        conversation_id=conversation_id,
        filename=safe_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_path=storage_path,
        extracted_text=extracted_text,
        extracted_facts=extracted_facts,
    )
    storage_ref = doc_record["id"]

    # ------------------------------------------------------------------
    # 6. If conversation_id is known, immediately merge facts into memory
    # ------------------------------------------------------------------
    if conversation_id and extracted_facts:
        try:
            mem_repo = ConversationMemoryRepository(db)
            current_memory = await mem_repo.get_or_create(conversation_id)
            updated_memory, events = merge_delta(
                current_memory,
                extracted_facts,
                source_message_id=f"document:{storage_ref}",
            )
            await mem_repo.upsert(updated_memory)
            await doc_repo.mark_merged(storage_ref)
            logger.info(
                "Merged document facts into conversation_memory for conv=%s (fields: %s)",
                conversation_id,
                list(extracted_facts.keys()),
            )
        except Exception as exc:
            logger.warning("Failed to merge document facts into memory: %s", exc)
            # Non-fatal — facts will be merged by load_documents node instead

    # ------------------------------------------------------------------
    # 7. Return response
    # ------------------------------------------------------------------
    preview = (extracted_text[:300] + "…") if len(extracted_text) > 300 else extracted_text
    summary = facts_summary(extracted_facts)

    return DocumentUploadResponse(
        storage_ref=storage_ref,
        filename=safe_filename,
        content_type=content_type,
        size_bytes=size_bytes,
        extracted_text_preview=preview,
        facts_found=bool(extracted_facts),
        facts_summary=summary,
    )


@router.get("/{storage_ref}")
async def serve_document(storage_ref: str):
    """Stream an uploaded document back to the client for viewing/download."""
    db = get_db()
    doc_repo = DocumentRepository(db)
    doc = await doc_repo.get_by_id(storage_ref)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    path = Path(doc["storage_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk.")
    return _FileResponse(
        path=str(path),
        media_type=doc.get("content_type", "application/octet-stream"),
        filename=doc.get("filename", path.name),
    )
