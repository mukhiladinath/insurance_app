"""
common.py — Shared Pydantic base models and primitives.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class AppError(BaseModel):
    """Structured error returned by all API error responses."""
    code: str
    message: str
    detail: dict | None = None


class PaginationMeta(BaseModel):
    total: int
    limit: int
    skip: int


class TimestampedModel(BaseModel):
    """Base for models that carry created_at / updated_at."""
    created_at: datetime
    updated_at: datetime | None = None
