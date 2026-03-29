"""
propose_factfind_patch.py — Build UI actions for the frontend to present a factfind proposal.

After extract_factfind_fields saves a pending proposal, this node:
  1. Compares proposed values against the current factfind_snapshot.
  2. Builds the proposed_factfind_patches response object.
  3. Adds ui_actions to open the factfind panel and show the proposal.
  4. Sets final_response to a summary of what was found.

State reads:  factfind_draft_changes, factfind_proposal_id, factfind_snapshot,
              factfind_full, attached_files
State writes: ui_actions, final_response, structured_response_payload
"""

import logging

from app.agents.workspace_state import WorkspaceState

logger = logging.getLogger(__name__)

# Human-readable labels for common field paths
_FIELD_LABELS: dict[str, str] = {
    "personal.age": "Age",
    "personal.date_of_birth": "Date of Birth",
    "personal.gender": "Gender",
    "personal.smoker": "Smoker",
    "personal.occupation": "Occupation",
    "personal.occupation_class": "Occupation Class",
    "personal.dependants": "Number of Dependants",
    "financial.annual_gross_income": "Annual Gross Income",
    "financial.monthly_income": "Monthly Income",
    "financial.monthly_expenses": "Monthly Expenses",
    "financial.super_balance": "Superannuation Balance",
    "financial.mortgage_balance": "Mortgage Balance",
    "financial.other_debts": "Other Debts",
    "insurance.existing_life_cover": "Existing Life Cover",
    "insurance.existing_tpd_cover": "Existing TPD Cover",
    "insurance.existing_ip_cover": "Existing IP Cover",
    "insurance.existing_trauma_cover": "Existing Trauma Cover",
    "insurance.current_insurer": "Current Insurer",
    "insurance.fund_type": "Fund Type",
}


async def propose_factfind_patch(state: WorkspaceState) -> dict:
    """
    Build the proposal response for the frontend.

    Reads:  factfind_draft_changes, factfind_proposal_id, factfind_snapshot, attached_files
    Writes: ui_actions, final_response, structured_response_payload
    """
    draft_changes: dict = state.get("factfind_draft_changes", {})
    proposal_id = state.get("factfind_proposal_id")
    factfind_snapshot = state.get("factfind_snapshot", {})
    attached_files = state.get("attached_files", [])

    if not draft_changes:
        return {
            "final_response": "I couldn't extract any recognisable fact-find fields from the document. Please try uploading a clearer document or enter the details manually.",
            "ui_actions": [],
        }

    # Build field comparison list
    proposed_fields = []
    for field_path, field_data in draft_changes.items():
        if not isinstance(field_data, dict):
            continue
        current_value = factfind_snapshot.get(field_path)
        label = _FIELD_LABELS.get(field_path, field_path.replace(".", " ").replace("_", " ").title())
        proposed_fields.append({
            "field_path": field_path,
            "label": label,
            "current_value": current_value,
            "proposed_value": field_data.get("value"),
            "confidence": field_data.get("confidence", 0.8),
            "evidence": field_data.get("evidence", ""),
        })

    # Sort by confidence descending
    proposed_fields.sort(key=lambda f: f["confidence"], reverse=True)

    high_confidence = [f for f in proposed_fields if f["confidence"] >= 0.8]
    low_confidence = [f for f in proposed_fields if f["confidence"] < 0.8]

    # Build the response text
    doc_name = attached_files[0].get("filename", "the document") if attached_files else "the document"
    lines = [
        f"I found **{len(proposed_fields)} fact-find field(s)** in {doc_name}.",
        "",
    ]
    if high_confidence:
        lines.append(f"**High confidence ({len(high_confidence)} fields):** " + ", ".join(f["label"] for f in high_confidence[:5]))
    if low_confidence:
        lines.append(f"**Lower confidence ({len(low_confidence)} fields):** " + ", ".join(f["label"] for f in low_confidence[:5]))
    lines += [
        "",
        "Review the proposed values in the Fact Find panel and accept or reject them.",
    ]
    final_response = "\n".join(lines)

    # UI actions
    ui_actions = []
    if proposal_id:
        ui_actions.append({
            "type": "open_factfind_panel",
            "payload": {"proposal_id": proposal_id, "tab": "proposals"},
        })

    source_doc_id = attached_files[0].get("storage_ref", "") if attached_files else ""
    structured_payload = {
        "type": "factfind_proposal",
        "proposal_id": proposal_id,
        "source_document_id": source_doc_id,
        "fields": proposed_fields,
    }

    logger.info(
        "propose_factfind_patch: %d fields proposed (proposal_id=%s)",
        len(proposed_fields), proposal_id,
    )

    return {
        "final_response": final_response,
        "ui_actions": ui_actions,
        "structured_response_payload": structured_payload,
    }
