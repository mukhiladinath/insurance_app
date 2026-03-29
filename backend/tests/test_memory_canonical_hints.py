"""Tests for AI memory → canonical facts hints (insurance tool input prep)."""

from app.services.memory_canonical_hints import (
    parse_markdown_for_hints,
    merge_hints_across_memory_categories,
    merge_memory_then_factfind,
    apply_canonical_overrides,
)


def test_parse_age_and_income_from_markdown():
    md = """## Profile
- Age: 44
- Occupation: Engineer

## Income
- Annual gross income: $185,000
"""
    h = parse_markdown_for_hints(md)
    assert h["personal"]["age"] == 44
    assert h["financial"]["annual_gross_income"] == 185000


def test_memory_category_order_first_wins():
    cat = {
        "profile": "Age: 40",
        "employment-income": "Age: 99\nAnnual gross income: 200000",
    }
    h = merge_hints_across_memory_categories(cat)
    assert h["personal"]["age"] == 40
    assert h["financial"]["annual_gross_income"] == 200000


def test_merge_memory_then_factfind_memory_wins():
    memory = {"personal": {"age": 50}, "financial": {}, "insurance": {}, "health": {}, "goals": {}}
    ff = {
        "personal": {"age": 30, "occupation": "X"},
        "financial": {"annual_gross_income": 100000},
        "insurance": {},
        "health": {},
        "goals": {},
    }
    m = merge_memory_then_factfind(memory, ff)
    assert m["personal"]["age"] == 50
    assert m["personal"]["occupation"] == "X"
    assert m["financial"]["annual_gross_income"] == 100000


def test_merge_factfind_fills_when_memory_missing_income():
    memory = {"personal": {"age": 41}, "financial": {}, "insurance": {}, "health": {}, "goals": {}}
    ff = {
        "personal": {"age": 99},
        "financial": {"annual_gross_income": 120000},
        "insurance": {},
        "health": {},
        "goals": {},
    }
    m = merge_memory_then_factfind(memory, ff)
    assert m["personal"]["age"] == 41
    assert m["financial"]["annual_gross_income"] == 120000


def test_overrides_win():
    canonical = {
        "personal": {"age": 40},
        "financial": {"annual_gross_income": 100000},
        "insurance": {},
        "health": {},
        "goals": {},
    }
    apply_canonical_overrides(canonical, {"personal.age": 55, "financial.annual_gross_income": 888888})
    assert canonical["personal"]["age"] == 55
    assert canonical["financial"]["annual_gross_income"] == 888888
