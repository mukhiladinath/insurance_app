"""
route_request.py — Entry node: classify the request and set active_mode.

Decision priority:
  1. resume_token present            → resume_after_clarification
  2. rerun_from_saved_run_id present → rerun_patched
  3. attached_files present          → extract_factfind_from_document
  4. LLM-classify user_message:
       - factfind update intent      → update_factfind
       - AI context intent           → inspect_ai_context / edit_ai_context
       - tool run (default)          → plan_tool_subflow

State reads:  resume_token, rerun_from_saved_run_id, attached_files, user_message
State writes: active_mode
"""

import logging
import re

from app.agents.workspace_state import WorkspaceState, ActiveMode

logger = logging.getLogger(__name__)

# Keywords that signal factfind update intent (no tool needed)
_FACTFIND_UPDATE_PATTERNS = [
    r"\b(update|change|set|edit|correct|fix|modify)\b.*\b(fact.?find|fact find|client detail|client info|client data|personal detail|financial detail)\b",
    r"\b(client|his|her|their)\b.{0,30}\b(income|age|salary|balance|dob|date of birth|occupation|smoker|dependan)\b.{0,20}\b(is|are|was|=)\b",
    r"\bupdate.{0,20}\b(age|income|salary|balance|super|occupation)\b",
]

_FACTFIND_INSPECT_PATTERNS = [
    r"\b(show|view|display|what|check).{0,20}\b(fact.?find|client detail|client info|client data)\b",
    r"\bwhat.{0,15}(do we know|have we got|is on file)\b",
]

_CONTEXT_PATTERNS = [
    r"\b(show|view|display|what|check|edit|update|change).{0,20}\b(ai context|context|what the agent|what claude)\b",
    r"\b(context panel|agent context|context layer)\b",
]

_COMPILED_FACTFIND_UPDATE = [re.compile(p, re.IGNORECASE) for p in _FACTFIND_UPDATE_PATTERNS]
_COMPILED_FACTFIND_INSPECT = [re.compile(p, re.IGNORECASE) for p in _FACTFIND_INSPECT_PATTERNS]
_COMPILED_CONTEXT = [re.compile(p, re.IGNORECASE) for p in _CONTEXT_PATTERNS]


def _classify_message(message: str) -> ActiveMode:
    for pat in _COMPILED_CONTEXT:
        if pat.search(message):
            # Distinguish inspect vs edit
            if re.search(r"\b(edit|update|change|set|override)\b", message, re.IGNORECASE):
                return "edit_ai_context"
            return "inspect_ai_context"

    for pat in _COMPILED_FACTFIND_UPDATE:
        if pat.search(message):
            return "update_factfind"

    return "plan_tool_subflow"


async def route_request(state: WorkspaceState) -> dict:
    """
    Classify the request and set active_mode.

    Priority:
      resume_token           → resume_after_clarification
      rerun_from_saved_run_id → rerun_patched
      attached_files         → extract_factfind_from_document
      message classification → plan_tool_subflow | update_factfind | *_ai_context
    """
    resume_token = state.get("resume_token")
    rerun_saved_id = state.get("rerun_from_saved_run_id")
    attached = state.get("attached_files", [])
    message = state.get("user_message", "")

    if resume_token:
        mode: ActiveMode = "resume_after_clarification"
    elif rerun_saved_id:
        mode = "rerun_patched"
    elif attached:
        mode = "extract_factfind_from_document"
    else:
        mode = _classify_message(message)

    logger.info("route_request: active_mode=%s for client=%s", mode, state.get("client_id"))
    return {"active_mode": mode}
