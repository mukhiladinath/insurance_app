"""
extract_factfind_fields.py — LLM node: extract factfind field values from document text.

Given extracted_document_context (raw text from an uploaded document), this node
uses the LLM to map document content to canonical factfind field paths.

Output: factfind_draft_changes — { "personal.age": { value, confidence, evidence } }
        factfind_proposal_id   — created via factfind_repository.add_proposal()

State reads:  extracted_document_context, factfind_snapshot, client_id, attached_files
State writes: factfind_draft_changes, factfind_proposal_id
"""

import json
import logging
import re

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.workspace_state import WorkspaceState
from app.core.llm import get_chat_model
from app.db.mongo import get_db
from app.db.repositories.factfind_repository import FactfindRepository

logger = logging.getLogger(__name__)

_SCHEMA_DESCRIPTION = """\
personal:
  age (int), date_of_birth (ISO date), gender (str), smoker (bool),
  occupation (str), occupation_class (str — A|B|C|D|E),
  residency_status (str), state (str), dependants (int)

financial:
  annual_gross_income (float), monthly_income (float), monthly_expenses (float),
  super_balance (float), investment_assets (float), other_assets (float),
  mortgage_balance (float), other_debts (float), net_worth (float)

insurance:
  existing_life_cover (float), existing_tpd_cover (float),
  existing_ip_cover (float), existing_trauma_cover (float),
  current_insurer (str), fund_type (str — "MySuper"|"Choice"),
  ip_waiting_period_days (int), ip_benefit_period (str),
  life_policy_in_super (bool), tpd_policy_in_super (bool)

health:
  health_conditions (list[str]), medications (list[str]),
  family_history (list[str]), height_cm (int), weight_kg (int),
  bmi (float)

goals:
  primary_goal (str), retirement_age (int), risk_tolerance (str),
  lifestyle_protection (bool), estate_planning (bool)
"""

_EXTRACT_SYSTEM = """\
You are an insurance data extraction specialist. Given a document, extract all \
available client fact-find fields. Only extract fields you can clearly identify \
from the document.

## FACTFIND FIELD SCHEMA
{schema}

## RULES
1. Map extracted values to the exact field names listed above.
2. Use the section prefix: "personal.age", "financial.super_balance", etc.
3. Provide confidence (0.0-1.0) and a brief evidence snippet per field.
4. If a value is ambiguous or inferred, set confidence < 0.7.
5. Do NOT make up values. Only extract what is explicitly stated.
6. Return ONLY valid JSON.

## OUTPUT SCHEMA
{{
  "extracted": {{
    "personal.age": {{
      "value": 42,
      "confidence": 0.95,
      "evidence": "...exact text from document..."
    }},
    ...
  }}
}}
"""

_EXTRACT_HUMAN = """\
## DOCUMENT TEXT
{document_text}

## ALREADY KNOWN FIELDS (do not re-extract unless document has an update)
{known_fields}

Extract all available factfind fields from the document now.
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


async def extract_factfind_fields(state: WorkspaceState) -> dict:
    """
    Extract factfind field values from uploaded document text.

    Reads:  extracted_document_context, factfind_snapshot, client_id, attached_files
    Writes: factfind_draft_changes, factfind_proposal_id
    """
    doc_text = state.get("extracted_document_context")
    if not doc_text:
        logger.warning("extract_factfind_fields: no document context in state")
        return {"factfind_draft_changes": {}, "factfind_proposal_id": None}

    factfind_snapshot = state.get("factfind_snapshot", {})
    client_id = state.get("client_id", "")
    attached_files = state.get("attached_files", [])

    known_fields_str = (
        "\n".join(f"  {k}: {v}" for k, v in factfind_snapshot.items())
        if factfind_snapshot else "(none)"
    )

    try:
        llm = get_chat_model(temperature=0.0)
        response = await llm.ainvoke([
            SystemMessage(content=_EXTRACT_SYSTEM.format(schema=_SCHEMA_DESCRIPTION)),
            HumanMessage(content=_EXTRACT_HUMAN.format(
                document_text=str(doc_text)[:6000],
                known_fields=known_fields_str,
            )),
        ])
        raw = response.content if hasattr(response, "content") else str(response)
        parsed = _extract_json(raw)
        extracted: dict = parsed.get("extracted", {})

    except Exception as exc:
        logger.exception("extract_factfind_fields: LLM extraction failed: %s", exc)
        extracted = {}

    if not extracted:
        return {"factfind_draft_changes": {}, "factfind_proposal_id": None}

    # Determine source_document_id from first attached file
    source_doc_id = ""
    if attached_files:
        source_doc_id = attached_files[0].get("storage_ref", "")

    # Save as a pending proposal on the factfind
    proposal_id: str | None = None
    if client_id and extracted:
        try:
            db = get_db()
            repo = FactfindRepository(db)
            proposal_id = await repo.add_proposal(
                client_id=client_id,
                source_document_id=source_doc_id,
                proposed_fields=extracted,
            )
            logger.info(
                "extract_factfind_fields: created proposal %s with %d fields for client=%s",
                proposal_id, len(extracted), client_id,
            )
        except Exception as exc:
            logger.warning("extract_factfind_fields: proposal save failed: %s", exc)

    return {
        "factfind_draft_changes": extracted,
        "factfind_proposal_id": proposal_id,
    }
