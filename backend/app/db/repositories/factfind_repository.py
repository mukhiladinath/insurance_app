"""
factfind_repository.py — CRUD for the factfinds and factfind_change_log collections.

factfinds document shape:
  _id              : ObjectId
  client_id        : str  (unique index)
  version          : int
  sections         : dict — personal / financial / insurance / health / goals
    Each field in a section is a dict:
      value       : Any
      status      : "confirmed" | "inferred" | "proposed" | "rejected" | "missing"
      source      : "manual" | "ai_extracted" | "document_extracted" | "clarification_response"
      source_ref  : str  (message_id or document_id)
      confidence  : float  (0.0–1.0)
      updated_at  : datetime
      updated_by  : str  ("user" or "agent")
  pending_proposals: list[dict]
    proposal_id        : str
    source_document_id : str
    proposed_fields    : dict  field_path → {value, confidence, evidence}
    status             : "pending" | "accepted" | "rejected" | "partial"
    created_at         : datetime
  created_at       : datetime
  updated_at       : datetime

factfind_change_log document shape:
  _id           : ObjectId
  client_id     : str
  field_path    : str  e.g. "personal.age"
  old_value     : Any
  new_value     : Any
  source        : str
  source_ref    : str
  changed_by    : str
  changed_at    : datetime
"""

import logging
import uuid
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db import collections as col
from app.utils.timestamps import utc_now
from app.utils.ids import to_object_id
from app.utils.factfind_changes import count_valid_factfind_paths, normalize_factfind_changes
from app.services.factfind_conversation_memory_sync import sync_factfind_changes_to_conversation_memory

logger = logging.getLogger(__name__)

_ALL_SECTIONS = ["personal", "financial", "insurance", "health", "goals"]


def _serialize(doc: dict) -> dict:
    if doc is None:
        return doc
    doc["id"] = str(doc.pop("_id"))
    return doc


def _empty_factfind(client_id: str) -> dict:
    now = utc_now()
    return {
        "client_id": client_id,
        "version": 0,
        "sections": {s: {} for s in _ALL_SECTIONS},
        "pending_proposals": [],
        "created_at": now,
        "updated_at": now,
    }


class FactfindRepository:
    def __init__(self, db: AsyncIOMotorDatabase):
        self._db = db
        self._col = db[col.FACTFINDS]
        self._log = db[col.FACTFIND_CHANGE_LOG]

    # ----------------------------------------------------------------
    # Read
    # ----------------------------------------------------------------

    async def get_by_client(self, client_id: str) -> dict | None:
        doc = await self._col.find_one({"client_id": client_id})
        return _serialize(doc) if doc else None

    async def get_or_create(self, client_id: str) -> dict:
        empty = _empty_factfind(client_id)
        result = await self._col.find_one_and_update(
            {"client_id": client_id},
            {"$setOnInsert": empty},
            upsert=True,
            return_document=True,
        )
        return _serialize(result)

    # ----------------------------------------------------------------
    # Write individual field changes
    # ----------------------------------------------------------------

    async def patch_fields(
        self,
        client_id: str,
        changes: dict[str, Any],
        source: str,
        source_ref: str,
        changed_by: str,
    ) -> dict:
        """
        Apply field-level changes to the factfind.
        changes: { "personal.age": 42, "financial.super_balance": 150000 }
        Nested section dicts (e.g. {"financial": {"super_balance": 1}}) are normalized first.
        Each change becomes a confirmed field entry with full metadata.
        Also writes a factfind_change_log entry per field.
        """
        now = utc_now()
        existing = await self.get_or_create(client_id)

        normalized = normalize_factfind_changes(changes)
        if count_valid_factfind_paths(normalized) == 0:
            raise ValueError(
                "No valid factfind field paths in changes. Use dotted keys like "
                '"financial.annual_gross_income" or nest under section names.'
            )

        set_ops: dict[str, Any] = {"updated_at": now}
        log_entries: list[dict] = []

        for field_path, new_value in normalized.items():
            parts = field_path.split(".", 1)
            if len(parts) != 2:
                logger.warning("factfind_repository: invalid field_path %s", field_path)
                continue
            section, field = parts[0], parts[1]

            # Get old value for change log
            old_field = (
                existing.get("sections", {})
                .get(section, {})
                .get(field, {})
            )
            old_value = old_field.get("value") if isinstance(old_field, dict) else old_field

            set_ops[f"sections.{section}.{field}"] = {
                "value": new_value,
                "status": "confirmed",
                "source": source,
                "source_ref": source_ref,
                "confidence": 1.0 if source == "manual" else 0.9,
                "updated_at": now,
                "updated_by": changed_by,
            }

            log_entries.append({
                "client_id": client_id,
                "field_path": field_path,
                "old_value": old_value,
                "new_value": new_value,
                "source": source,
                "source_ref": source_ref,
                "changed_by": changed_by,
                "changed_at": now,
            })

        set_ops["version"] = existing.get("version", 0) + 1

        doc = await self._col.find_one_and_update(
            {"client_id": client_id},
            {"$set": set_ops},
            upsert=True,
            return_document=True,
        )

        if log_entries:
            await self._log.insert_many(log_entries)

        await sync_factfind_changes_to_conversation_memory(
            self._db, client_id, normalized
        )

        return _serialize(doc)

    # ----------------------------------------------------------------
    # Proposal management
    # ----------------------------------------------------------------

    async def add_proposal(
        self,
        client_id: str,
        source_document_id: str,
        proposed_fields: dict,
    ) -> str:
        """
        Add a document-extraction proposal. Returns the proposal_id.
        proposed_fields: { "personal.age": { value, confidence, evidence } }
        """
        # Ensure the factfind document exists first (avoids $push/$setOnInsert
        # path conflict on the same 'pending_proposals' field in a single upsert)
        await self.get_or_create(client_id)

        proposal_id = str(uuid.uuid4())
        proposal = {
            "proposal_id": proposal_id,
            "source_document_id": source_document_id,
            "proposed_fields": proposed_fields,
            "status": "pending",
            "created_at": utc_now(),
        }
        await self._col.update_one(
            {"client_id": client_id},
            {
                "$push": {"pending_proposals": proposal},
                "$set": {"updated_at": utc_now()},
            },
        )
        return proposal_id

    async def accept_proposal(
        self,
        client_id: str,
        proposal_id: str,
        field_paths: list[str] | None,
        changed_by: str,
    ) -> dict:
        """
        Accept all or specific fields from a proposal. Writes them as confirmed.
        field_paths=None means accept all.
        """
        doc = await self.get_or_create(client_id)

        proposal = next(
            (p for p in doc.get("pending_proposals", []) if p["proposal_id"] == proposal_id),
            None,
        )
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposed_fields: dict = proposal.get("proposed_fields", {})
        to_accept = field_paths if field_paths is not None else list(proposed_fields.keys())

        changes = {
            fp: proposed_fields[fp]["value"]
            for fp in to_accept
            if fp in proposed_fields
        }

        updated = await self.patch_fields(
            client_id=client_id,
            changes=changes,
            source="document_extracted",
            source_ref=proposal.get("source_document_id", ""),
            changed_by=changed_by,
        )

        # Update proposal status
        all_fields = set(proposed_fields.keys())
        accepted = set(to_accept)
        new_status = "accepted" if accepted >= all_fields else "partial"

        await self._col.update_one(
            {"client_id": client_id, "pending_proposals.proposal_id": proposal_id},
            {"$set": {"pending_proposals.$.status": new_status}},
        )

        return updated

    async def reject_proposal(self, client_id: str, proposal_id: str) -> None:
        await self._col.update_one(
            {"client_id": client_id, "pending_proposals.proposal_id": proposal_id},
            {
                "$set": {
                    "pending_proposals.$.status": "rejected",
                    "updated_at": utc_now(),
                }
            },
        )

    # ----------------------------------------------------------------
    # Change log
    # ----------------------------------------------------------------

    async def get_change_log(
        self, client_id: str, limit: int = 50
    ) -> list[dict]:
        from pymongo import DESCENDING
        cursor = (
            self._log.find({"client_id": client_id})
            .sort("changed_at", DESCENDING)
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [_serialize(d) for d in docs]

    # ----------------------------------------------------------------
    # Flat snapshot for agent context
    # ----------------------------------------------------------------

    def flatten_for_context(self, factfind: dict) -> dict[str, Any]:
        """
        Return a flat {section.field: value} dict of all confirmed/inferred fields.
        Used for populating planner context.
        """
        result: dict[str, Any] = {}
        for section, fields in factfind.get("sections", {}).items():
            for field_name, field_data in fields.items():
                if not isinstance(field_data, dict):
                    continue
                status = field_data.get("status", "missing")
                if status in ("confirmed", "inferred"):
                    v = field_data.get("value")
                    if v is not None and v != "" and v != []:
                        result[f"{section}.{field_name}"] = v
        return result
