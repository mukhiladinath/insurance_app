"""
health.py — Health check routes.

GET /api/health        → simple alive check
GET /api/health/db     → verifies MongoDB connectivity
"""

from fastapi import APIRouter
from app.db.mongo import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health():
    return {"status": "ok", "service": "insurance-advisory-backend"}


@router.get("/db")
async def health_db():
    try:
        db = get_db()
        await db.command("ping")
        return {"status": "ok", "mongodb": "connected"}
    except Exception as exc:
        return {"status": "error", "mongodb": "disconnected", "detail": str(exc)}
