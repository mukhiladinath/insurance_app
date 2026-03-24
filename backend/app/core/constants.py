"""
constants.py — Application-wide constants.

These are behavioural constants, not configuration values.
Configuration values (URLs, keys, names) belong in config.py.
"""

# -------------------------------------------------------------------------
# Conversation defaults
# -------------------------------------------------------------------------
DEFAULT_CONVERSATION_TITLE = "New Conversation"
MAX_CONTEXT_MESSAGES = 20  # messages loaded into agent context window

# -------------------------------------------------------------------------
# Agent run statuses
# -------------------------------------------------------------------------
class AgentRunStatus:
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# -------------------------------------------------------------------------
# Tool call statuses
# -------------------------------------------------------------------------
class ToolCallStatus:
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATION_ERROR = "validation_error"


# -------------------------------------------------------------------------
# Message roles
# -------------------------------------------------------------------------
class MessageRole:
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    SYSTEM = "system"


# -------------------------------------------------------------------------
# Intent labels (used by classify_intent node)
# -------------------------------------------------------------------------
class Intent:
    DIRECT_RESPONSE = "direct_response"
    TOOL_LIFE_INSURANCE_IN_SUPER = "purchase_retain_life_insurance_in_super"
    TOOL_LIFE_TPD_POLICY = "purchase_retain_life_tpd_policy"
    TOOL_INCOME_PROTECTION_POLICY = "purchase_retain_income_protection_policy"
    TOOL_IP_IN_SUPER = "purchase_retain_ip_in_super"
    TOOL_TRAUMA_CI_POLICY = "purchase_retain_trauma_ci_policy"
    TOOL_TPD_POLICY_ASSESSMENT = "tpd_policy_assessment"
    TOOL_TPD_IN_SUPER = "purchase_retain_tpd_in_super"
    CLARIFICATION_NEEDED = "clarification_needed"


# -------------------------------------------------------------------------
# Tool names (must match registry keys)
# -------------------------------------------------------------------------
class ToolName:
    LIFE_INSURANCE_IN_SUPER = "purchase_retain_life_insurance_in_super"
    LIFE_TPD_POLICY = "purchase_retain_life_tpd_policy"
    INCOME_PROTECTION_POLICY = "purchase_retain_income_protection_policy"
    IP_IN_SUPER = "purchase_retain_ip_in_super"
    TRAUMA_CI_POLICY = "purchase_retain_trauma_ci_policy"
    TPD_POLICY_ASSESSMENT = "tpd_policy_assessment"
    TPD_IN_SUPER = "purchase_retain_tpd_in_super"


# -------------------------------------------------------------------------
# Conversation statuses
# -------------------------------------------------------------------------
class ConversationStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"
