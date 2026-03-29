"""
main.py — FastAPI application entry point.

Startup sequence:
  1. Connect to MongoDB
  2. Ensure all collection indexes
  3. Pre-compile the LangGraph agent graph
  4. Register API routes

Shutdown:
  1. Disconnect from MongoDB
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.db import mongo
from app.db.collections import ensure_indexes
from app.agents.graph import get_graph
from app.agents.orchestrator_graph import get_orchestrator_graph
from app.agents.workspace_graph import get_workspace_graph
from app.api.routes import health, chat, conversations, tools, upload, soa, agent
from app.api.routes import clients, workspace, insurance_comparison, insurance_dashboard
from app.api.routes import client_context, orchestrator_planner, client_analysis_outputs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # -----------------------------------------------------------------------
    # Startup
    # -----------------------------------------------------------------------
    settings = get_settings()
    logger.info("Starting insurance-advisory backend (env=%s)", settings.app_env)

    # Connect to MongoDB
    await mongo.connect()

    # Ensure indexes
    db = mongo.get_db()
    await ensure_indexes(db)

    # Pre-compile all LangGraph graphs (catches config errors early)
    get_graph()
    get_orchestrator_graph()
    get_workspace_graph()

    logger.info("Backend startup complete.")
    yield

    # -----------------------------------------------------------------------
    # Shutdown
    # -----------------------------------------------------------------------
    await mongo.disconnect()
    logger.info("Backend shutdown complete.")


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Insurance Advisory Backend",
        description="LangGraph-powered insurance advisory AI backend",
        version="1.0.0",
        docs_url=f"{settings.api_prefix}/docs",
        redoc_url=f"{settings.api_prefix}/redoc",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=lifespan,
    )

    # CORS — allow the Next.js dev server during development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    prefix = settings.api_prefix
    app.include_router(health.router, prefix=prefix)
    app.include_router(chat.router, prefix=prefix)
    app.include_router(conversations.router, prefix=prefix)
    app.include_router(tools.router, prefix=prefix)
    app.include_router(upload.router, prefix=prefix)
    app.include_router(soa.router, prefix=prefix)
    app.include_router(agent.router, prefix=prefix)

    # New client-workspace-centric routes
    app.include_router(clients.router, prefix=prefix)
    app.include_router(workspace.router, prefix=prefix)
    app.include_router(insurance_comparison.router, prefix=prefix)

    # AI memory + finobi-style orchestrator planner
    app.include_router(client_context.router, prefix=prefix)
    app.include_router(orchestrator_planner.router, prefix=prefix)
    app.include_router(client_analysis_outputs.router, prefix=prefix)
    app.include_router(insurance_dashboard.router, prefix=prefix)

    return app


app = create_app()
