"""
collections.py — Collection name registry and index creation.

Centralises all MongoDB collection names. Indexes are created once at startup
via ensure_indexes(), keeping index definitions alongside the collection they belong to.
"""

import logging
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ASCENDING, DESCENDING

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------------
# Collection name constants
# -------------------------------------------------------------------------

CONVERSATIONS = "conversations"
MESSAGES = "messages"
AGENT_RUNS = "agent_runs"
TOOL_CALLS = "tool_calls"
APP_CONFIG = "app_config"
CONVERSATION_MEMORY = "conversation_memory"
MEMORY_EVENTS = "memory_events"
DOCUMENTS = "documents"          # uploaded document records + extracted content
AGENT_WORKSPACE = "agent_workspace"  # advisory_notes + scratch_pad per conversation

# ── New client-workspace-centric collections ──────────────────────────────────

CLIENTS = "clients"                          # canonical client identity records
FACTFINDS = "factfinds"                      # first-class factfind per client
FACTFIND_CHANGE_LOG = "factfind_change_log"  # per-field audit trail
CLIENT_WORKSPACES = "client_workspaces"      # workspace state, advisory notes, overrides
WORKSPACE_CONTEXT_SNAPSHOTS = "workspace_context_snapshots"  # what the agent saw per run
RUN_STEPS = "run_steps"                      # full per-step results (replaces tool_calls for new runs)
SAVED_TOOL_RUNS = "saved_tool_runs"          # curated, named tool run snapshots per client
PENDING_CLARIFICATIONS = "pending_clarifications"  # frozen plan + resume token
DOCUMENT_EXTRACTIONS = "document_extractions"      # extracted text + field proposals

# ── AI memory system ──────────────────────────────────────────────────────────
CLIENT_MEMORIES = "client_memories"   # per-client per-category markdown memory docs

# Persisted LLM summaries from orchestrator analysis tool runs (per client)
CLIENT_ANALYSIS_OUTPUTS = "client_analysis_outputs"

# Saved insurance comparison sessions (structured compare results)
INSURANCE_TOOL_COMPARISONS = "insurance_tool_comparisons"

# Dynamic insurance dashboards + pending resume sessions
CLIENT_INSURANCE_DASHBOARDS = "client_insurance_dashboards"
INSURANCE_DASHBOARD_SESSIONS = "insurance_dashboard_sessions"


# -------------------------------------------------------------------------
# Index definitions
# -------------------------------------------------------------------------

async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    """
    Create all required indexes. Safe to call multiple times (idempotent).
    Called once at application startup after the DB connection is established.
    """

    # conversations
    await db[CONVERSATIONS].create_index(
        [("user_id", ASCENDING), ("updated_at", DESCENDING)]
    )
    await db[CONVERSATIONS].create_index([("status", ASCENDING)])

    # messages
    await db[MESSAGES].create_index(
        [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
    )
    await db[MESSAGES].create_index([("agent_run_id", ASCENDING)])

    # agent_runs
    await db[AGENT_RUNS].create_index([("conversation_id", ASCENDING)])
    await db[AGENT_RUNS].create_index([("status", ASCENDING)])
    await db[AGENT_RUNS].create_index([("started_at", DESCENDING)])

    # tool_calls
    await db[TOOL_CALLS].create_index([("agent_run_id", ASCENDING)])
    await db[TOOL_CALLS].create_index([("conversation_id", ASCENDING)])
    await db[TOOL_CALLS].create_index([("tool_name", ASCENDING)])

    # conversation_memory — unique per conversation, fast lookup
    await db[CONVERSATION_MEMORY].create_index(
        [("conversation_id", ASCENDING)], unique=True
    )

    # memory_events — ordered audit trail per conversation
    await db[MEMORY_EVENTS].create_index(
        [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
    )
    await db[MEMORY_EVENTS].create_index([("event_type", ASCENDING)])

    # documents — lookup by conversation and user; ordering by upload time
    await db[DOCUMENTS].create_index(
        [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
    )
    await db[DOCUMENTS].create_index([("user_id", ASCENDING)])
    await db[DOCUMENTS].create_index([("facts_merged", ASCENDING)])

    # agent_workspace — advisory notes + scratch pad, unique per conversation
    await db[AGENT_WORKSPACE].create_index(
        [("conversation_id", ASCENDING)], unique=True
    )

    # ── New workspace collections ─────────────────────────────────────────────

    # clients — one record per client
    await db[CLIENTS].create_index([("user_id", ASCENDING), ("status", ASCENDING)])
    await db[CLIENTS].create_index([("name", ASCENDING)])

    # factfinds — unique per client
    await db[FACTFINDS].create_index([("client_id", ASCENDING)], unique=True)

    # factfind_change_log — per-client audit trail ordered by time
    await db[FACTFIND_CHANGE_LOG].create_index(
        [("client_id", ASCENDING), ("changed_at", DESCENDING)]
    )
    await db[FACTFIND_CHANGE_LOG].create_index([("field_path", ASCENDING)])

    # client_workspaces — unique per client
    await db[CLIENT_WORKSPACES].create_index([("client_id", ASCENDING)], unique=True)
    await db[CLIENT_WORKSPACES].create_index([("user_id", ASCENDING)])

    # workspace_context_snapshots — ordered per client
    await db[WORKSPACE_CONTEXT_SNAPSHOTS].create_index(
        [("client_id", ASCENDING), ("created_at", DESCENDING)]
    )
    await db[WORKSPACE_CONTEXT_SNAPSHOTS].create_index([("run_id", ASCENDING)])

    # run_steps — ordered per run and searchable per client
    await db[RUN_STEPS].create_index([("run_id", ASCENDING)])
    await db[RUN_STEPS].create_index([("client_id", ASCENDING), ("tool_name", ASCENDING)])

    # saved_tool_runs — per client, ordered by save time
    await db[SAVED_TOOL_RUNS].create_index(
        [("client_id", ASCENDING), ("saved_at", DESCENDING)]
    )
    await db[SAVED_TOOL_RUNS].create_index([("tool_names", ASCENDING)])

    # pending_clarifications — resume_token must be unique; status lookup
    await db[PENDING_CLARIFICATIONS].create_index([("resume_token", ASCENDING)], unique=True)
    await db[PENDING_CLARIFICATIONS].create_index(
        [("client_id", ASCENDING), ("status", ASCENDING)]
    )

    # document_extractions — one per document
    await db[DOCUMENT_EXTRACTIONS].create_index([("document_id", ASCENDING)], unique=True)
    await db[DOCUMENT_EXTRACTIONS].create_index([("client_id", ASCENDING)])

    # client_memories — one doc per client per category (9 categories per client)
    await db[CLIENT_MEMORIES].create_index(
        [("client_id", ASCENDING), ("category", ASCENDING)], unique=True
    )
    await db[CLIENT_MEMORIES].create_index([("client_id", ASCENDING)])

    # client_analysis_outputs — history of analysis narratives per client
    await db[CLIENT_ANALYSIS_OUTPUTS].create_index(
        [("client_id", ASCENDING), ("created_at", DESCENDING)]
    )

    # insurance_tool_comparisons — saved comparison results per client
    await db[INSURANCE_TOOL_COMPARISONS].create_index(
        [("client_id", ASCENDING), ("created_at", DESCENDING)]
    )

    # client_insurance_dashboards — persisted dashboard specs per client
    await db[CLIENT_INSURANCE_DASHBOARDS].create_index(
        [("client_id", ASCENDING), ("created_at", DESCENDING)]
    )

    # insurance_dashboard_sessions — resume tokens for missing-field flow
    await db[INSURANCE_DASHBOARD_SESSIONS].create_index(
        [("session_token", ASCENDING)], unique=True
    )
    await db[INSURANCE_DASHBOARD_SESSIONS].create_index(
        [("client_id", ASCENDING), ("status", ASCENDING)]
    )

    logger.info("MongoDB indexes ensured.")
