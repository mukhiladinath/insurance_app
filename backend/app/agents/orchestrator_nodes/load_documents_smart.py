"""
load_documents_smart.py — Conditional document loader for the orchestrator.

Replaces the legacy load_documents node.

Only loads document text when context_requirements.load_documents is True
OR when the user has attached files to this specific message.

This avoids injecting potentially large document blobs into every prompt.
The document facts are ALWAYS merged into client_memory (deferred merging),
but the raw text is only passed to the LLM when explicitly needed.

State reads:  attached_files, conversation_id, context_requirements, client_memory
State writes: document_context, client_memory (if facts merged)
"""

import logging

from app.agents.state import AgentState
from app.db.mongo import get_db
from app.db.repositories.conversation_memory_repository import ConversationMemoryRepository
from app.db.repositories.document_repository import DocumentRepository
from app.services.memory_merge_service import merge_delta

logger = logging.getLogger(__name__)


async def load_documents_smart(state: AgentState) -> dict:
    """
    Merge document facts into memory (always) and load text (conditionally).

    The split between fact-merging and text-loading is key:
      • Fact merging: always done so client_memory stays up to date
      • Text loading: only when the query actually references the document

    Reads:  attached_files, conversation_id, context_requirements, client_memory
    Writes: document_context, client_memory (if facts merged)
    """
    attached_files: list[dict] = state.get("attached_files") or []
    conversation_id: str = state.get("conversation_id", "")
    requirements = state.get("context_requirements", {})
    should_load_text: bool = requirements.get("load_documents", False)

    # If files are attached to THIS message, always load their text
    has_new_attachments = bool(attached_files)
    load_text = should_load_text or has_new_attachments

    if not attached_files:
        # No files attached — nothing to do unless text was requested
        # (historical documents were already merged in prior turns)
        return {"document_context": None}

    try:
        db = get_db()
        doc_repo = DocumentRepository(db)
        mem_repo = ConversationMemoryRepository(db)

        text_parts: list[str] = []
        client_memory: dict = state.get("client_memory") or {}
        memory_updated = False

        for attachment in attached_files:
            storage_ref = (
                attachment.get("storage_ref") if isinstance(attachment, dict) else None
            )
            if not storage_ref:
                continue

            doc = await doc_repo.get_by_id(storage_ref)
            if not doc:
                logger.warning("load_documents_smart: doc %s not found", storage_ref)
                continue

            # Link to conversation if needed
            if not doc.get("conversation_id") and conversation_id:
                await doc_repo.attach_conversation(storage_ref, conversation_id)

            # ---- Always: merge facts into memory ----
            if not doc.get("facts_merged") and doc.get("extracted_facts"):
                try:
                    current_db_memory = await mem_repo.get_or_create(conversation_id)
                    updated_db_memory, _events = merge_delta(
                        current_db_memory,
                        doc["extracted_facts"],
                        source_message_id=f"document:{storage_ref}",
                    )
                    await mem_repo.upsert(updated_db_memory)
                    await doc_repo.mark_merged(storage_ref)

                    client_memory, _ = merge_delta(
                        client_memory,
                        doc["extracted_facts"],
                        source_message_id=f"document:{storage_ref}",
                    )
                    memory_updated = True
                    logger.info(
                        "load_documents_smart: merged facts from %s into %s",
                        storage_ref, conversation_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "load_documents_smart: fact merge failed %s: %s", storage_ref, exc
                    )

            # ---- Conditionally: load text for LLM context ----
            if load_text:
                extracted_text = doc.get("extracted_text", "")
                if extracted_text.strip():
                    filename = doc.get("filename", storage_ref)
                    text_parts.append(
                        f"=== Uploaded Document: {filename} ===\n{extracted_text}"
                    )

        document_context = "\n\n".join(text_parts) if text_parts else None

        result: dict = {"document_context": document_context}
        if memory_updated:
            result["client_memory"] = client_memory

        if document_context:
            logger.info(
                "load_documents_smart: injected text from %d doc(s) (%d chars)",
                len(text_parts), len(document_context),
            )
        elif not load_text and attached_files:
            logger.debug(
                "load_documents_smart: facts merged, text skipped "
                "(query did not reference documents)"
            )

        return result

    except Exception as exc:
        logger.exception("load_documents_smart: unexpected error: %s", exc)
        return {"document_context": None}
