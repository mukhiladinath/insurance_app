"""
load_documents.py — LangGraph node: load uploaded document context into state.

Runs after load_memory, before classify_intent.

Responsibilities:
  1. For each attached file that has a storage_ref, fetch its document record from MongoDB.
  2. Concatenate extracted_text from all documents → set state["document_context"].
  3. For any documents whose facts have not yet been merged into conversation_memory
     (facts_merged=False), merge them now and persist to DB.
  4. Update state["client_memory"] to include the freshly merged document facts
     so classify_intent and the tool input builder can use them.

This handles the case where a document was uploaded before a conversation existed
(conversation_id was None at upload time).

Non-fatal: on any error, the node returns empty document_context and leaves
client_memory unchanged.
"""

from __future__ import annotations

import logging

from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.services.memory_merge_service import merge_delta

logger = logging.getLogger(__name__)


async def load_documents(state: AgentState) -> dict:
    """
    Load document text and merge any pending document facts into client_memory.
    """
    attached_files: list[dict] = state.get("attached_files") or []
    conversation_id: str = state.get("conversation_id", "")

    if not attached_files:
        return {"document_context": None}

    try:
        db = get_db()
        doc_repo = DocumentRepository(db)
        mem_repo = ConversationMemoryRepository(db)

        text_parts: list[str] = []
        client_memory: dict = state.get("client_memory") or {}
        memory_updated = False

        for attachment in attached_files:
            storage_ref = attachment.get("storage_ref") if isinstance(attachment, dict) else None
            if not storage_ref:
                continue

            doc = await doc_repo.get_by_id(storage_ref)
            if not doc:
                logger.warning("load_documents: document %s not found in DB", storage_ref)
                continue

            # Link document to conversation if it was uploaded before the chat started
            if not doc.get("conversation_id") and conversation_id:
                await doc_repo.attach_conversation(storage_ref, conversation_id)

            # Collect text for document_context
            extracted_text = doc.get("extracted_text", "")
            if extracted_text.strip():
                filename = doc.get("filename", storage_ref)
                text_parts.append(f"=== Uploaded Document: {filename} ===\n{extracted_text}")

            # Merge facts if not yet merged
            if not doc.get("facts_merged") and doc.get("extracted_facts"):
                try:
                    facts = doc["extracted_facts"]

                    # Merge into conversation_memory in DB
                    current_db_memory = await mem_repo.get_or_create(conversation_id)
                    updated_db_memory, _events = merge_delta(
                        current_db_memory,
                        facts,
                        source_message_id=f"document:{storage_ref}",
                    )
                    await mem_repo.upsert(updated_db_memory)
                    await doc_repo.mark_merged(storage_ref)

                    # Also merge into the in-memory state dict so classify_intent sees it
                    client_memory, _ = merge_delta(
                        client_memory,
                        facts,
                        source_message_id=f"document:{storage_ref}",
                    )
                    memory_updated = True

                    logger.info(
                        "load_documents: merged facts from doc=%s into conv=%s",
                        storage_ref,
                        conversation_id,
                    )
                except Exception as exc:
                    logger.warning("load_documents: fact merge failed for %s: %s", storage_ref, exc)

        document_context = "\n\n".join(text_parts) if text_parts else None

        result: dict = {"document_context": document_context}
        if memory_updated:
            result["client_memory"] = client_memory

        if document_context:
            logger.info(
                "load_documents: loaded %d document(s), context length=%d chars",
                len(text_parts),
                len(document_context),
            )

        return result

    except Exception as exc:
        logger.exception("load_documents: unexpected error: %s", exc)
        return {"document_context": None}
