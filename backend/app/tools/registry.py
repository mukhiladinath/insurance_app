"""
registry.py — Tool registry.

All tools are registered here at module import time.
The agent uses the registry to look up and execute tools by name.
"""

from app.tools.base import BaseTool
from app.tools.implementations.life_insurance_in_super import LifeInsuranceInSuperTool
from app.tools.implementations.life_tpd_policy import LifeTPDPolicyTool
from app.tools.implementations.income_protection_policy import IncomeProtectionPolicyTool
from app.tools.implementations.ip_in_super import IPInSuperTool
from app.tools.implementations.trauma_critical_illness_policy import TraumaCIPolicyTool
from app.tools.implementations.tpd_policy_assessment import TPDPolicyAssessmentTool
from app.tools.implementations.tpd_in_super import TPDInSuperTool

# -------------------------------------------------------------------------
# Registry — maps tool name → tool instance
# -------------------------------------------------------------------------

_REGISTRY: dict[str, BaseTool] = {}


def _register(tool: BaseTool) -> None:
    _REGISTRY[tool.name] = tool


# Register all tools at import time
_register(LifeInsuranceInSuperTool())
_register(LifeTPDPolicyTool())
_register(IncomeProtectionPolicyTool())
_register(IPInSuperTool())
_register(TraumaCIPolicyTool())
_register(TPDPolicyAssessmentTool())
_register(TPDInSuperTool())


# -------------------------------------------------------------------------
# Public API
# -------------------------------------------------------------------------

def get_tool(name: str) -> BaseTool | None:
    """Return the tool instance for the given name, or None."""
    return _REGISTRY.get(name)


def list_tools() -> list[BaseTool]:
    """Return all registered tools."""
    return list(_REGISTRY.values())


def tool_exists(name: str) -> bool:
    return name in _REGISTRY
