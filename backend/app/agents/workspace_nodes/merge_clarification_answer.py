"""
merge_clarification_answer.py — Parse the user's clarification answer and merge it.

Given the clarification_answer (natural-language reply from the user) and the
list of missing_fields that were requested, this node:
  1. Uses the LLM to extract the specific field values from the answer.
  2. Patches factfind_snapshot with the extracted values.
  3. Persists the new field values to the factfinds collection.
  4. Marks the pending_clarification as resolved.

After this node, plan_workspace re-runs with the updated factfind_snapshot.
If the answer is sufficient, clarification_needed will be False and execution proceeds.

State reads:  clarification_answer, missing_fields, factfind_snapshot,
              client_id, _pending_clarification_doc, resume_token
State writes: factfind_snapshot (patched), factfind_draft_changes
"""

import json
import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.workspace_state import WorkspaceState
from app.core.llm import get_chat_model
from app.db.mongo import get_db
from app.db.repositories.factfind_repository import FactfindRepository
from app.db.repositories.pending_clarification_repository import PendingClarificationRepository

logger = logging.getLogger(__name__)

_EXTRACT_SYSTEM = """\
You are an insurance data extraction assistant. The user has answered a clarification \
question asking for specific client information. Extract the field values from their answer.

For each requested field, extract the value from the user's reply. If the user did not \
provide a value for a field, omit it from the result.

Return ONLY valid JSON — no prose, no markdown:
{
  "extracted": {
    "field_path": value,
    ...
  }
}
"""

_EXTRACT_HUMAN = """\
## FIELDS REQUESTED
{fields_requested}

## USER'S ANSWER
{answer}

Extract the values now.
"""


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {}


async def merge_clarification_answer(state: WorkspaceState) -> dict:
    """
    Extract field values from the clarification answer and patch factfind_snapshot.

    Reads:  clarification_answer, missing_fields, factfind_snapshot, client_id,
            _pending_clarification_doc, resume_token
    Writes: factfind_snapshot (patched), factfind_draft_changes
    """
    answer = state.get("clarification_answer", "") or state.get("user_message", "")
    missing_fields = state.get("missing_fields", [])
    factfind_snapshot = dict(state.get("factfind_snapshot", {}))
    client_id = state.get("client_id", "")
    resume_token = state.get("resume_token", "")

    if not answer or not missing_fields:
        return {}

    fields_requested = "\n".join(
        f"  - {f.get('field_path')}: {f.get('label', f.get('field_path'))}"
        for f in missing_fields
    )

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM),
            HumanMessage(content=_EXTRACT_HUMAN.format(
                fields_requested=fields_requested,
                answer=answer,
            )),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _extract_json(raw)
        extracted: dict = parsed.get("extracted", {})

    except Exception as exc:
        logger.exception("merge_clarification_answer: LLM extraction failed: %s", exc)
        extracted = {}

    if not extracted:
        logger.warning("merge_clarification_answer: no fields extracted from answer")
        return {}

    # Patch factfind_snapshot
    patched_snapshot = {**factfind_snapshot, **extracted}

    # Persist extracted values to factfind
    if client_id and extracted:
        try:
            db = get_db()
            repo = FactfindRepository(db)
            # source_ref uses run_id since we don't have message_id at this point
            await repo.patch_fields(
                client_id=client_id,
                changes=extracted,
                source="clarification_response",
                source_ref=state.get("run_id", ""),
                changed_by="agent",
            )
        except Exception as exc:
            logger.warning("merge_clarification_answer: factfind persist failed: %s", exc)

    # Mark the pending clarification as resolved
    if resume_token:
        try:
            db = get_db()
            clarif_repo = PendingClarificationRepository(db)
            await clarif_repo.resolve(resume_token, answer)
        except Exception as exc:
            logger.warning("merge_clarification_answer: clarification resolve failed: %s", exc)

    logger.info(
        "merge_clarification_answer: patched %d field(s) for client=%s: %s",
        len(extracted), client_id, list(extracted.keys()),
    )

    return {
        "factfind_snapshot": patched_snapshot,
        "factfind_draft_changes": extracted,
    }
