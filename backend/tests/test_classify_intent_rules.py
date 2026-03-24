"""
test_classify_intent_rules.py — Rule-level intent classification tests.
"""

import sys
import os
import pytest

# Ensure backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.nodes.classify_intent import _classify_by_rules, classify_intent
from app.core.constants import Intent


def test_income_protection_outside_super_routes_to_standalone_ip():
    message = "James has no income protection at all. What do you recommend for standalone IP outside super?"
    intent = _classify_by_rules(message)
    assert intent == Intent.TOOL_INCOME_PROTECTION_POLICY


def test_income_protection_inside_super_routes_to_ip_in_super():
    message = "Can you assess income protection inside super for James?"
    intent = _classify_by_rules(message)
    assert intent == Intent.TOOL_IP_IN_SUPER


@pytest.mark.asyncio
async def test_correction_rerun_prefers_explicit_requested_tool_over_last_tool():
    state = {
        "user_message": "Actually his super balance is $235,000 not $220,000. Can you recalculate the life insurance in super with the correct balance?",
        "recent_messages": [
            {"role": "assistant", "content": "Income protection analysis: waiting period, benefit period, and occupation definition."}
        ],
        "client_memory": {
            "client_facts": {
                "personal": {"age": 43},
                "financial": {"annual_gross_income": 145000, "super_balance": 220000},
                "insurance": {"has_existing_policy": True, "life_sum_insured": 350000},
                "health": {},
                "goals": {},
            }
        },
    }

    result = await classify_intent(state)
    assert result["selected_tool"] == Intent.TOOL_LIFE_INSURANCE_IN_SUPER

