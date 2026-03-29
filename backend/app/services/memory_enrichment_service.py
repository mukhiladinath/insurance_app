"""
memory_enrichment_service.py — Enrich client AI memory from uploaded documents or factfind.

Mirrors finobi's client_context.py enrichment pipeline but uses MongoDB instead of S3.

Pipeline:
  1. Extract text from file (reuses document_extractor.py)
  2. Extract structured facts per category using LLM
  3. Merge new facts into existing category markdown docs using LLM
  4. Upsert updated docs back to MongoDB client_memories collection
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Any

from app.core.llm import get_chat_model_fresh
from app.db.repositories.client_memory_repository import (
    MEMORY_CATEGORIES,
    CATEGORY_LABELS,
    get_all_memories,
    get_memory,
    upsert_memory,
    initialize_empty_memories,
)
from app.services.document_extractor import extract_text, extract_client_facts

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CATEGORY_FACT_EXTRACTION_PROMPT = """\
You are a data-extraction assistant for an insurance advisory platform.

Read the document text and extract client facts organised into the following categories:
- profile: Personal details (name, age, DOB, gender, occupation, employment status, smoker, state, family)
- employment-income: Salary, wages, business income, super contributions, employer, industry
- financial-position: Assets, liabilities, investments, super balance, net worth, cash, property, debts
- insurance: Existing policies (life, TPD, income protection, trauma), cover amounts, insurers, premiums, policy numbers
- goals-risk-profile: Financial goals, risk tolerance, investment horizon, retirement age, priorities
- tax-structures: Tax bracket, tax file number notes, SMSF, trusts, tax strategies
- estate-planning: Will status, powers of attorney, beneficiary nominations, estate instructions
- health: Medical conditions, height/weight, medications, hazardous activities, family health history
- interactions: Key decisions made, action items, adviser observations, meeting outcomes

Return a JSON object where keys are category names from the list above, and values are arrays of fact strings.
Only include categories that have relevant facts. Omit categories with no facts found.
For each fact, be specific and include numbers/dates where present.

Return ONLY valid JSON. No markdown fences. No explanation.

Example:
{
  "profile": ["Full name: John Smith", "Age: 42", "Occupation: Software Engineer"],
  "financial-position": ["Annual income: $120,000", "Super balance: $280,000"],
  "insurance": ["Life cover: $500,000 with AIA", "Premium: $1,200/year"]
}
"""

_CATEGORY_MERGE_PROMPT = """\
You are an AI assistant maintaining a client memory file for an insurance adviser.

Below is the EXISTING content of the "{category_label}" section and NEW facts extracted from a document.
Your task is to merge the new facts into the existing content.

Rules:
- Preserve ALL existing content unless directly contradicted by new facts
- Add new facts in the appropriate sub-heading, creating sub-headings if needed
- If a new fact contradicts existing content, keep both with a note like "[Updated: {date}]"
- Add a source attribution line: "Source: {source_name} ({date})"
- Keep formatting clean with markdown sub-headings and bullet points
- Never remove facts — only add or update

EXISTING CONTENT:
{existing_content}

NEW FACTS:
{new_facts}

SOURCE: {source_name}
DATE: {date}

Return the complete updated markdown content for this section only. No explanation.
"""

_FACTFIND_TO_MEMORY_PROMPT = """\
You are an AI assistant converting a structured factfind JSON into a readable memory entry.

Convert the following factfind section data into clear, well-formatted markdown bullet points.
Use sub-headings where appropriate. Include all non-null values.
Format numbers as currency or percentages where appropriate.

CATEGORY: {category_label}
FACTFIND DATA:
{factfind_data}

Return only the markdown content (no outer heading needed, that's added separately).
"""


# ---------------------------------------------------------------------------
# Document enrichment
# ---------------------------------------------------------------------------


async def enrich_from_document(
    client_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: str,
) -> dict[str, Any]:
    """
    Full pipeline: upload file bytes → extract text → extract per-category facts
    → merge into existing memory docs → upsert to MongoDB.

    Returns a summary dict of what was updated.
    """
    # Ensure client has memory stubs
    await initialize_empty_memories(client_id)

    # Write to temp file for extraction
    suffix = _suffix_for_content_type(content_type)
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        # Step 1: Extract text
        text = await extract_text(tmp_path, content_type)
        if not text.strip():
            logger.warning("memory_enrichment: no text extracted from %s", filename)
            return {"updated_categories": [], "facts_extracted": 0, "filename": filename}

        # Step 2: Extract per-category facts using LLM
        category_facts = await _extract_category_facts(text, filename)
        if not category_facts:
            return {"updated_categories": [], "facts_extracted": 0, "filename": filename}

        # Step 3: Merge into existing memory docs
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        updated_categories: list[str] = []
        total_facts = 0

        for category, facts in category_facts.items():
            if category not in MEMORY_CATEGORIES:
                continue
            if not facts:
                continue

            existing_doc = await get_memory(client_id, category)
            existing_content = existing_doc.get("content", f"## {CATEGORY_LABELS[category]}\n") if existing_doc else f"## {CATEGORY_LABELS[category]}\n"

            merged_content = await _merge_facts_into_category(
                category_label=CATEGORY_LABELS[category],
                existing_content=existing_content,
                new_facts=facts,
                source_name=filename,
                date=date_str,
            )

            source_entry = {"filename": filename, "date": date_str, "fact_count": len(facts)}
            await upsert_memory(
                client_id=client_id,
                category=category,
                content=merged_content,
                sources=[source_entry],
                fact_count=(existing_doc or {}).get("fact_count", 0) + len(facts),
            )
            updated_categories.append(category)
            total_facts += len(facts)

        logger.info(
            "memory_enrichment: enriched client=%s from %s — categories=%s facts=%d",
            client_id, filename, updated_categories, total_facts,
        )
        return {
            "updated_categories": updated_categories,
            "facts_extracted": total_facts,
            "filename": filename,
        }

    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _extract_category_facts(text: str, filename: str) -> dict[str, list[str]]:
    """Use LLM to extract facts per memory category from document text."""
    try:
        llm = get_chat_model_fresh(temperature=0.0)

        # Truncate to stay within context
        if len(text) > 8000:
            text = text[:5500] + "\n...[middle truncated]...\n" + text[-2500:]

        messages = [
            {"role": "system", "content": _CATEGORY_FACT_EXTRACTION_PROMPT},
            {"role": "user", "content": f"Document: {filename}\n\n{text}"},
        ]

        response = await llm.ainvoke(messages)
        raw = response.content.strip() if hasattr(response, "content") else ""

        # Strip markdown fences
        if raw.startswith("```"):
            lines = [l for l in raw.splitlines() if not l.strip().startswith("```")]
            raw = "\n".join(lines).strip()

        data = json.loads(raw)
        if not isinstance(data, dict):
            return {}

        # Validate: each value must be a list of strings
        cleaned: dict[str, list[str]] = {}
        for cat, facts in data.items():
            if isinstance(facts, list) and facts:
                cleaned[cat] = [str(f) for f in facts if f]

        return cleaned

    except Exception as exc:
        logger.warning("_extract_category_facts failed for %s: %s", filename, exc)
        return {}


async def _merge_facts_into_category(
    category_label: str,
    existing_content: str,
    new_facts: list[str],
    source_name: str,
    date: str,
) -> str:
    """Use LLM to intelligently merge new facts into existing markdown content."""
    try:
        llm = get_chat_model_fresh(temperature=0.1)

        facts_text = "\n".join(f"- {f}" for f in new_facts)

        prompt = _CATEGORY_MERGE_PROMPT.format(
            category_label=category_label,
            existing_content=existing_content,
            new_facts=facts_text,
            source_name=source_name,
            date=date,
        )

        messages = [{"role": "user", "content": prompt}]
        response = await llm.ainvoke(messages)
        merged = response.content.strip() if hasattr(response, "content") else ""

        if not merged:
            # Fallback: append raw facts
            return existing_content + f"\n\n### From {source_name} ({date})\n" + facts_text

        return merged

    except Exception as exc:
        logger.warning("_merge_facts_into_category failed: %s", exc)
        # Fallback: append raw
        facts_text = "\n".join(f"- {f}" for f in new_facts)
        return existing_content + f"\n\n### From {source_name} ({date})\n" + facts_text


# ---------------------------------------------------------------------------
# Factfind → memory sync
# ---------------------------------------------------------------------------


async def enrich_from_factfind(client_id: str, factfind_sections: dict[str, Any]) -> dict[str, Any]:
    """
    Convert factfind section data into memory docs for the relevant categories.
    Maps factfind sections to memory categories.
    """
    await initialize_empty_memories(client_id)

    FACTFIND_TO_CATEGORY_MAP = {
        "personal": "profile",
        "financial": "financial-position",
        "insurance": "insurance",
        "health": "health",
        "goals": "goals-risk-profile",
    }

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    updated: list[str] = []

    for section_name, category in FACTFIND_TO_CATEGORY_MAP.items():
        section_data = factfind_sections.get(section_name, {})
        if not section_data:
            continue

        # Flatten factfind field objects (each field has {value, status, ...})
        flat: dict[str, Any] = {}
        for field_name, field_data in section_data.items():
            if isinstance(field_data, dict) and "value" in field_data:
                v = field_data["value"]
                if v is not None and v != "" and v != []:
                    flat[field_name] = v
            elif field_data is not None:
                flat[field_name] = field_data

        if not flat:
            continue

        content = await _factfind_section_to_markdown(
            category_label=CATEGORY_LABELS[category],
            factfind_data=flat,
        )

        full_content = f"## {CATEGORY_LABELS[category]}\n\n{content}\n\n_Synced from Fact Find on {date_str}_"

        await upsert_memory(
            client_id=client_id,
            category=category,
            content=full_content,
            sources=[{"filename": "Fact Find", "date": date_str, "fact_count": len(flat)}],
            fact_count=len(flat),
        )
        updated.append(category)

    return {"updated_categories": updated, "facts_extracted": len(updated), "source": "factfind"}


async def _factfind_section_to_markdown(category_label: str, factfind_data: dict[str, Any]) -> str:
    """Convert a flat factfind dict into readable markdown via LLM."""
    try:
        llm = get_chat_model_fresh(temperature=0.0)
        data_str = json.dumps(factfind_data, indent=2, default=str)

        prompt = _FACTFIND_TO_MEMORY_PROMPT.format(
            category_label=category_label,
            factfind_data=data_str,
        )

        messages = [{"role": "user", "content": prompt}]
        response = await llm.ainvoke(messages)
        return response.content.strip() if hasattr(response, "content") else _simple_factfind_markdown(factfind_data)

    except Exception as exc:
        logger.warning("_factfind_section_to_markdown failed: %s", exc)
        return _simple_factfind_markdown(factfind_data)


def _simple_factfind_markdown(data: dict[str, Any]) -> str:
    """Fallback: convert dict to simple bullet list."""
    lines = []
    for key, value in data.items():
        label = key.replace("_", " ").title()
        if isinstance(value, bool):
            val_str = "Yes" if value else "No"
        elif isinstance(value, (int, float)):
            val_str = f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
        else:
            val_str = str(value)
        lines.append(f"- **{label}:** {val_str}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _suffix_for_content_type(content_type: str) -> str:
    mapping = {
        "application/pdf": ".pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/webp": ".webp",
        "text/plain": ".txt",
        "text/csv": ".csv",
    }
    return mapping.get(content_type, ".tmp")
