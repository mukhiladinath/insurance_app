"""
load_workspace_context.py — Load all context for a workspace run in parallel.

Loads:
  - factfind (from factfinds collection, keyed by client_id)
  - client workspace (advisory_notes, scratch_pad, ai_context_overrides)
  - recent conversation messages
  - document text (if attached_files are present)

Produces:
  - factfind_snapshot      (flat dict: "section.field" → value, confirmed/inferred only)
  - factfind_full          (complete factfind doc with per-field metadata)
  - ai_context_hierarchy   (layered context tree for planner + AI context panel)
  - ai_context_overrides   (user-edited overrides from workspace)
  - advisory_notes         (client-scoped)
  - scratch_pad
  - recent_messages
  - extracted_document_context

State reads:  client_id, workspace_id, conversation_id, attached_files
State writes: factfind_snapshot, factfind_full, ai_context_hierarchy,
              ai_context_overrides, advisory_notes, scratch_pad,
              recent_messages, extracted_document_context
"""

import asyncio
import logging

from app.agents.workspace_state import WorkspaceState
from app.db.mongo import get_db
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.workspace_repository import WorkspaceRepository
from app.db.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)

_FACTFIND_SECTIONS = ["personal", "financial", "insurance", "health", "goals"]


def _build_ai_context_hierarchy(
    client: dict,
    factfind: dict,
    factfind_flat: dict,
    advisory_notes: dict,
    scratch_pad: list,
    recent_messages: list,
    doc_context: str | None,
    overrides: dict,
) -> dict:
    """
    Build the full hierarchical AI context tree.
    Each layer describes: label, user_can_view, user_can_edit, system_owned,
    affects_planning, data.
    """
    # Completeness: count non-empty confirmed/inferred fields vs total defined fields
    total_fields = sum(
        len(sec)
        for sec in factfind.get("sections", {}).values()
    )
    filled_fields = len(factfind_flat)
    completeness = round(filled_fields / max(total_fields, 1), 2) if total_fields else 0.0

    # Merge assumptions base with user overrides
    base_assumptions = {
        "inflation_rate": 0.03,
        "investment_return": 0.07,
        "risk_profile": "balanced",
    }
    assumption_overrides = overrides.get("assumptions", {})
    assumptions = {**base_assumptions, **assumption_overrides}

    return {
        "client_profile": {
            "label": "Client Profile",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": {
                "name": client.get("name"),
                "email": client.get("email"),
                "date_of_birth": client.get("date_of_birth"),
                "status": client.get("status"),
            },
        },
        "factfind": {
            "label": "Fact Find",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": factfind.get("sections", {}),
            "completeness_pct": completeness,
            "flat": factfind_flat,
        },
        "assumptions": {
            "label": "Assumptions",
            "user_can_view": True,
            "user_can_edit": True,
            "system_owned": False,
            "affects_planning": True,
            "data": assumptions,
            "overrides": assumption_overrides,
        },
        "current_tool_context": {
            "label": "Current Tool Run",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": {},  # populated later by plan_node
        },
        "advisory_notes": {
            "label": "Prior Analysis Conclusions",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": advisory_notes,
        },
        "document_context": {
            "label": "Uploaded Documents",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": {"text": doc_context or ""},
        },
        "recent_conversation": {
            "label": "Recent Conversation",
            "user_can_view": True,
            "user_can_edit": False,
            "system_owned": True,
            "affects_planning": True,
            "data": {"messages": recent_messages},
        },
        "scratchpad": {
            "label": "Agent Working Notes",
            "user_can_view": True,
            "user_can_edit": True,
            "system_owned": False,
            "affects_planning": True,
            "data": scratch_pad,
            "overrides": overrides.get("scratchpad", []),
        },
    }


async def _load_document_text(attached_files: list[dict]) -> str | None:
    if not attached_files:
        return None
    db = get_db()
    doc_repo = DocumentRepository(db)
    chunks: list[str] = []
    for f in attached_files:
        ref = f.get("storage_ref", "")
        if not ref:
            continue
        try:
            doc = await doc_repo.get_by_id(ref)
            if doc:
                text = doc.get("extracted_text", "")
                if text and text.strip():
                    chunks.append(f"[{f.get('filename', doc.get('filename', 'document'))}]\n{text}")
        except Exception as exc:
            logger.warning("load_workspace_context: doc load error for %s: %s", ref, exc)
    return "\n\n---\n\n".join(chunks) if chunks else None


async def load_workspace_context(state: WorkspaceState) -> dict:
    """
    Load all workspace context in parallel.
    """
    client_id = state.get("client_id", "")
    conversation_id = state.get("conversation_id", "")
    attached_files = state.get("attached_files", [])

    if not client_id:
        logger.error("load_workspace_context: client_id missing from state")
        return {"errors": state.get("errors", []) + ["client_id missing"]}

    db = get_db()
    factfind_repo = FactfindRepository(db)
    workspace_repo = WorkspaceRepository(db)
    msg_repo = MessageRepository(db)

    async def _empty_list() -> list:
        return []

    # Run DB loads in parallel
    results = await asyncio.gather(
        factfind_repo.get_or_create(client_id),
        workspace_repo.get_or_create(client_id, state.get("user_id", "")),
        msg_repo.get_recent(conversation_id, n=12) if conversation_id else _empty_list(),
        _load_document_text(attached_files),
        return_exceptions=True,
    )

    factfind_doc, workspace_doc, recent_msgs, doc_text = results

    # Handle any errors from gather
    if isinstance(factfind_doc, Exception):
        logger.error("load_workspace_context: factfind load failed: %s", factfind_doc)
        factfind_doc = {"sections": {s: {} for s in _FACTFIND_SECTIONS}, "pending_proposals": []}
    if isinstance(workspace_doc, Exception):
        logger.error("load_workspace_context: workspace load failed: %s", workspace_doc)
        workspace_doc = {"advisory_notes": {}, "scratch_pad": [], "ai_context_overrides": {}}
    if isinstance(recent_msgs, Exception):
        recent_msgs = []
    if isinstance(doc_text, Exception):
        doc_text = None

    # Build flat factfind snapshot
    factfind_flat = factfind_repo.flatten_for_context(factfind_doc)

    advisory_notes: dict = workspace_doc.get("advisory_notes", {})
    scratch_pad: list = workspace_doc.get("scratch_pad", [])
    overrides: dict = workspace_doc.get("ai_context_overrides", {})

    # We need client data for the context hierarchy
    # client doc is not loaded here since the service already has it — use a stub
    client_stub = {
        "name": "",
        "email": None,
        "date_of_birth": None,
        "status": "active",
    }

    ai_context = _build_ai_context_hierarchy(
        client=client_stub,
        factfind=factfind_doc,
        factfind_flat=factfind_flat,
        advisory_notes=advisory_notes,
        scratch_pad=scratch_pad,
        recent_messages=recent_msgs or [],
        doc_context=doc_text,
        overrides=overrides,
    )

    logger.info(
        "load_workspace_context: loaded factfind(%d fields) + %d advisory notes + %d messages for client=%s",
        len(factfind_flat), len(advisory_notes), len(recent_msgs or []), client_id,
    )

    return {
        "factfind_snapshot": factfind_flat,
        "factfind_full": factfind_doc,
        "ai_context_hierarchy": ai_context,
        "ai_context_overrides": overrides,
        "advisory_notes": advisory_notes,
        "scratch_pad": scratch_pad,
        "recent_messages": recent_msgs or [],
        "extracted_document_context": doc_text,
    }
