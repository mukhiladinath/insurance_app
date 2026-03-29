"""
Insurance comparison layer: canonical normalized facts, per-tool normalizers,
comparison engine, and persistence helpers.
"""

from app.insurance_comparison.registry import normalize_tool_output, has_normalizer

__all__ = ["normalize_tool_output", "has_normalizer"]
