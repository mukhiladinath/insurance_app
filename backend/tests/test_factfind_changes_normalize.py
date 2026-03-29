"""Tests for factfind PATCH normalization (planner / UI nested shapes)."""

import pytest

from app.utils.factfind_changes import count_valid_factfind_paths, normalize_factfind_changes


def test_normalize_flattens_section_dicts():
    raw = {
        "financial": {"annual_gross_income": 150000, "super_balance": 200000},
        "personal": {"age": 40},
    }
    out = normalize_factfind_changes(raw)
    assert out == {
        "financial.annual_gross_income": 150000,
        "financial.super_balance": 200000,
        "personal.age": 40,
    }


def test_normalize_preserves_flat_keys():
    raw = {"financial.annual_gross_income": 120000}
    assert normalize_factfind_changes(raw) == raw


def test_normalize_mixed_flat_and_nested():
    raw = {
        "personal.age": 38,
        "financial": {"super_balance": 100},
    }
    out = normalize_factfind_changes(raw)
    assert out["personal.age"] == 38
    assert out["financial.super_balance"] == 100


def test_count_valid_paths():
    assert count_valid_factfind_paths({"financial.annual_gross_income": 1}) == 1
    assert count_valid_factfind_paths({"bad": 1}) == 0


@pytest.mark.asyncio
async def test_patch_fields_raises_when_no_valid_paths_after_normalize():
    from unittest.mock import AsyncMock, MagicMock

    from app.db.repositories.factfind_repository import FactfindRepository

    db = MagicMock()
    repo = FactfindRepository(db)
    repo.get_or_create = AsyncMock(
        return_value={
            "client_id": "c1",
            "version": 0,
            "sections": {
                "personal": {},
                "financial": {},
                "insurance": {},
                "health": {},
                "goals": {},
            },
        }
    )

    with pytest.raises(ValueError, match="No valid factfind field paths"):
        await repo.patch_fields(
            client_id="c1",
            changes={"not_a_section": {"x": 1}},
            source="manual",
            source_ref="t",
            changed_by="u",
        )
