"""
classify_intent.py — Node: determine intent and select tool (if any).

Classification strategy (rule-first, LLM-assisted):
  1. If caller provided a tool_input_override → use it directly.
  2. If caller provided a tool_hint → validate and use it.
  3. Apply keyword/pattern rules (cheap, deterministic, fast).
  4. Fall back to LLM classification only when rules are insufficient.

The intent output is one of:
  - "direct_response"
  - "purchase_retain_life_insurance_in_super"
  - "purchase_retain_life_tpd_policy"
  - "purchase_retain_income_protection_policy"
  - "purchase_retain_ip_in_super"
  - "purchase_retain_trauma_ci_policy"
  - "tpd_policy_assessment"
  - "clarification_needed"
"""

import logging
import json
from app.agents.state import AgentState
from app.core.constants import Intent, ToolName
from app.tools.registry import tool_exists

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Keyword rule sets (lowercase patterns → tool name)
# Ordered from most specific to least. First match wins.
# ---------------------------------------------------------------------------

_LIFE_SUPER_KEYWORDS = [
    "life insurance in super", "insurance in super", "inside super", "switch off",
    "opt in", "opt-in", "pys", "protecting your super", "low balance", "inactivity",
    "s68aaa", "mysuper", "retain insurance", "keep insurance in super",
    "purchase insurance in super", "super fund insurance",
    # Broader super fund + insurance phrases
    "super fund", "my super", "through super", "via super", "in super",
    "super insurance", "super premium", "super with insurance",
    "insurance through my super", "insurance in my super",
]

# Compound rule: message contains "super" AND one of these → life_insurance_in_super
_SUPER_COMPOUND_TRIGGERS = [
    "insurance", "premium", "cover", "retain", "policy", "insured",
]

_LIFE_TPD_KEYWORDS = [
    "life insurance", "tpd", "total and permanent", "total permanent disability",
    "replace policy", "retain policy", "replacement policy", "new policy",
    "purchase life", "purchase tpd", "existing policy", "sum insured",
    "income replacement", "death cover", "trauma", "income protection",
    "underwriting", "policy comparison", "retain vs replace",
    "retain or replace", "life cover", "cover gap",
    # "premium" removed — too generic, collides with super premium context
]

# IP INSIDE SUPER — checked BEFORE standalone IP keywords (more specific)
_IP_IN_SUPER_KEYWORDS = [
    "ip in super", "income protection in super", "income protection inside super",
    "ip inside super", "ip inside my super", "ip through super",
    "salary continuance super", "salary continuance in super",
    "group ip", "group income protection", "ip via super",
    "ip super fund", "super fund ip", "ip through my fund",
    "ip smsf", "smsf income protection", "income protection smsf",
    "sps 250", "sps250", "insurance management framework",
    "temporary incapacity", "temporary incapacity super",
    "portability ip", "port ip cover", "port my ip",
    "ip portability", "income protection portability",
    "retain ip super", "purchase ip super", "ip in superannuation",
    "salary continuance", "retain salary continuance",
]

# Compound rule: "ip" or "income protection" + super → ip_in_super
_IP_SUPER_COMPOUND_LEFT  = ["ip", "income protection", "salary continuance", "disability cover"]
_IP_SUPER_COMPOUND_RIGHT = ["super", "superannuation", "fund", "smsf", "mysuper"]

# STANDALONE IP — only matches if NOT already matched as IP-in-super
_INCOME_PROTECTION_KEYWORDS = [
    "income protection", "ip policy", "disability income", "disability insurance",
    "income protection policy", "ip cover", "income replacement",
    "waiting period", "deferred period", "benefit period", "monthly benefit",
    "own occupation", "any occupation", "occupation definition", "step down",
    "waiver of premium", "premium waiver", "indexation", "cpi indexation",
    "rpi indexation", "partial disability", "rehab benefit", "return to work",
    "sick pay", "employer sick pay", "income protection claim", "disability claim",
    "purchase income protection", "retain income protection", "replace income protection",
    "ip shortfall", "income gap", "replace ip", "ip replacement",
    "idii", "individual disability income insurance",
]

# Compound rule: "income" + one of these → standalone income_protection
_IP_COMPOUND_TRIGGERS = [
    "protection", "replace", "retain", "disability", "policy", "benefit", "claim",
]

_DIRECT_KEYWORDS = [
    "hello", "hi ", "thanks", "thank you", "what can you", "help me",
    "who are you", "what are you", "tell me about",
]

# TRAUMA / CRITICAL ILLNESS — checked BEFORE life/TPD (more specific)
_TRAUMA_CI_KEYWORDS = [
    "trauma", "trauma insurance", "trauma policy", "trauma cover",
    "critical illness", "ci policy", "ci cover", "ci insurance",
    "critical illness insurance", "critical illness policy",
    "crisis recovery", "crisis cover",
    "trauma benefit", "ci benefit", "lump sum illness",
    "cancer cover", "heart attack cover", "stroke cover",
    "purchase trauma", "retain trauma", "replace trauma",
    "trauma waiting period", "trauma survival period",
    "trauma sum insured", "ci sum insured",
    "trauma underwriting", "ci underwriting",
    "advancement benefit", "partial benefit ci", "double ci",
    "multi claim ci", "trauma rider", "ci rider",
    "life code minimum", "life code conditions",
    "trauma cooling off", "ci cooling off",
    "trauma affordability", "ci affordability",
    "trauma premium", "ci premium",
    "trauma claim", "ci claim",
    "trauma exclusion", "ci exclusion",
    "serious illness", "dread disease",
    "trauma vs tpd", "ci vs tpd",
    "trauma and tpd", "ci and tpd",
]

# Compound rule: "critical" + illness-related term → trauma_ci
_TRAUMA_CI_COMPOUND_LEFT  = ["critical", "trauma", "crisis"]
_TRAUMA_CI_COMPOUND_RIGHT = ["illness", "cover", "policy", "insurance", "benefit", "claim", "sum insured"]

# TPD POLICY ASSESSMENT — deep TPD-specific analysis (definition, super placement, claims, tax)
# Checked BEFORE the generic life/TPD tool so specific TPD queries get the deeper tool
_TPD_ASSESSMENT_KEYWORDS = [
    "own occupation tpd", "any occupation tpd", "own occ tpd", "any occ tpd",
    "tpd definition", "tpd own occupation", "tpd any occupation",
    "activities of daily living", "adl tpd", "adl definition",
    "tpd claim", "tpd claims", "tpd claim eligibility",
    "tpd decline", "tpd declined",
    "permanent incapacity", "permanent disability", "permanently disabled",
    "tpd inside super", "tpd in super", "tpd super",
    "tpd outside super", "tpd retail",
    "tpd grandfathered", "grandfathered tpd",
    "tpd placement", "tpd super placement",
    "sis reg 4.07", "reg 4.07c", "reg 4.07d", "sps 250 tpd",
    "auto acceptance limit", "automatic acceptance limit", "aal tpd",
    "tpd tax", "tpd tax treatment", "tpd lump sum tax",
    "tpd super tax", "div 295 tpd", "taxable component tpd",
    "tpd lapse", "tpd reinstatement", "reinstate tpd",
    "tpd exclusion", "tpd exclusions",
    "tpd underwriting", "tpd premium structure",
    "stepped tpd", "level tpd", "tpd premium",
    "afca tpd", "idr tpd", "tpd dispute",
    "mysuper tpd", "default tpd cover",
    "tpd eligibility", "tpd assessment",
    "asic rep 633", "rep 633",
    "total and permanent disability",
    "total permanent disability",
    "tpd shortfall", "tpd gap",
]

# Compound rule: "tpd" + placement/definition/claim term → tpd_assessment
_TPD_ASSESSMENT_COMPOUND_LEFT  = ["tpd", "total and permanent", "total permanent", "permanently disabled"]
_TPD_ASSESSMENT_COMPOUND_RIGHT = [
    "definition", "own occupation", "any occupation", "adl", "activities",
    "super", "retail", "claim", "tax", "grandfathered", "placement",
    "decline", "lapse", "reinstate", "exclusion", "premium", "eligibility",
    "assessment", "compliance", "sis", "sps",
]


def _classify_by_rules(message: str) -> str | None:
    """Apply deterministic keyword rules. Returns intent string or None."""
    lower = message.lower()

    # --- TIER 0: TPD policy assessment — checked FIRST because "tpd", "own occupation",
    #     "disability claim", and "adl" keywords collide with IP and super tiers below.
    #     Gate: message contains "tpd" or "total and permanent disability" and is NOT a
    #     combined life+TPD query (those still fall to the life/TPD tier at the bottom). ---
    _is_combined_life_tpd = "life insurance" in lower and "tpd" in lower
    _has_tpd_signal = "tpd" in lower or "total and permanent disability" in lower or "total permanent disability" in lower
    if _has_tpd_signal and not _is_combined_life_tpd:
        if any(kw in lower for kw in _TPD_ASSESSMENT_KEYWORDS):
            return Intent.TOOL_TPD_POLICY_ASSESSMENT
        # Compound: "tpd"/"permanently disabled" + placement/definition/claim term
        if (any(left in lower for left in _TPD_ASSESSMENT_COMPOUND_LEFT) and
                any(right in lower for right in _TPD_ASSESSMENT_COMPOUND_RIGHT)):
            return Intent.TOOL_TPD_POLICY_ASSESSMENT
        # Plain "tpd" query without "life insurance" context → deep TPD tool
        if "tpd" in lower:
            return Intent.TOOL_TPD_POLICY_ASSESSMENT

    # --- TIER 1: IP inside super (most specific — checked first) ---
    if any(kw in lower for kw in _IP_IN_SUPER_KEYWORDS):
        return Intent.TOOL_IP_IN_SUPER

    # Compound rule: "ip"/"income protection" + "super"/"fund" → ip_in_super
    if (any(left in lower for left in _IP_SUPER_COMPOUND_LEFT) and
            any(right in lower for right in _IP_SUPER_COMPOUND_RIGHT)):
        return Intent.TOOL_IP_IN_SUPER

    # --- TIER 2: Life insurance inside super (explicit super terms) ---
    if any(kw in lower for kw in _LIFE_SUPER_KEYWORDS):
        return Intent.TOOL_LIFE_INSURANCE_IN_SUPER

    # Compound rule: "super" + any insurance-related term → life_insurance_in_super
    # (only if not already matched as IP-in-super above)
    if "super" in lower and any(trigger in lower for trigger in _SUPER_COMPOUND_TRIGGERS):
        return Intent.TOOL_LIFE_INSURANCE_IN_SUPER

    # --- TIER 3: Standalone income protection (outside super) ---
    if any(kw in lower for kw in _INCOME_PROTECTION_KEYWORDS):
        return Intent.TOOL_INCOME_PROTECTION_POLICY

    # Compound rule: "income" + IP-related term → standalone income_protection
    if "income" in lower and any(trigger in lower for trigger in _IP_COMPOUND_TRIGGERS):
        return Intent.TOOL_INCOME_PROTECTION_POLICY

    # --- TIER 4: Trauma / Critical Illness (checked before generic life/TPD) ---
    if any(kw in lower for kw in _TRAUMA_CI_KEYWORDS):
        return Intent.TOOL_TRAUMA_CI_POLICY

    # Compound rule: "critical"/"trauma"/"crisis" + illness/cover → trauma_ci
    if (any(left in lower for left in _TRAUMA_CI_COMPOUND_LEFT) and
            any(right in lower for right in _TRAUMA_CI_COMPOUND_RIGHT)):
        return Intent.TOOL_TRAUMA_CI_POLICY

    # --- TIER 5: TPD assessment fallback (catches remaining total/permanent disability queries
    #     that did not trigger TIER 0 — e.g. no "tpd" abbreviation used) ---
    if any(kw in lower for kw in _TPD_ASSESSMENT_KEYWORDS):
        return Intent.TOOL_TPD_POLICY_ASSESSMENT

    # --- TIER 6: Life / TPD policy (combined need analysis — combined life+TPD queries) ---
    if any(kw in lower for kw in _LIFE_TPD_KEYWORDS):
        return Intent.TOOL_LIFE_TPD_POLICY

    if any(kw in lower for kw in _DIRECT_KEYWORDS):
        return Intent.DIRECT_RESPONSE

    return None


# ---------------------------------------------------------------------------
# Tool input field schemas (used by the extraction prompt)
# ---------------------------------------------------------------------------

_TOOL_INPUT_SCHEMAS = {
    "purchase_retain_ip_in_super": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "member": {
    "age": <integer>,
    "employmentStatus": <"EMPLOYED_FULL_TIME"|"EMPLOYED_PART_TIME"|"SELF_EMPLOYED"|"UNEMPLOYED"|"ON_CLAIM"|"UNKNOWN">,
    "weeklyHoursWorked": <number — weekly hours worked, needed for part-time work test>,
    "annualGrossIncome": <AUD number>,
    "marginalTaxRate": <decimal e.g. 0.37>,
    "employmentCeasedDate": <ISO date YYYY-MM-DD — when member left employment>
  },
  "fund": {
    "fundType": <"mysuper"|"choice"|"smsf"|"defined_benefit">,
    "accountBalance": <AUD number>,
    "receivedAmountInLast16Months": <true|false — whether super contributions received in last 16 months>
  },
  "existingCover": {
    "hasExistingIPCover": <true|false>,
    "monthlyBenefit": <AUD number>,
    "waitingPeriodDays": <integer: 30, 60, or 90>,
    "benefitPeriodMonths": <integer: 0=to-age-65, 24, 60>,
    "annualPremium": <AUD number — use when user mentions "premium" or "super premium">,
    "occupationDefinition": <"OWN_OCCUPATION"|"ANY_OCCUPATION"|"UNKNOWN">,
    "portabilityClauseAvailable": <true|false>
  },
  "newCoverProposal": {
    "monthlyBenefit": <AUD number>,
    "waitingPeriodDays": <integer>,
    "annualPremium": <AUD number>
  },
  "elections": {
    "optedInToRetainInsurance": <true|false>,
    "optedOutOfInsurance": <true|false>
  },
  "adviceContext": {
    "yearsToRetirement": <number>,
    "needForOwnOccupationDefinition": <true|false>,
    "retirementPriorityHigh": <true|false>,
    "contributionCapPressure": <true|false>
  }
}""",
    "purchase_retain_income_protection_policy": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "client": {
    "age": <integer>,
    "annualGrossIncome": <annual gross income AUD as number>,
    "annualNetIncome": <annual net income AUD as number>,
    "occupationClass": <"CLASS_1_WHITE_COLLAR"|"CLASS_2_LIGHT_BLUE"|"CLASS_3_BLUE_COLLAR"|"CLASS_4_HAZARDOUS"|"UNKNOWN">,
    "occupation": <free-text occupation description>,
    "isSmoker": <true|false>,
    "dateOfBirth": <ISO date string YYYY-MM-DD>
  },
  "existingPolicy": {
    "hasExistingPolicy": <true|false>,
    "insurerName": <string>,
    "waitingPeriodWeeks": <integer: 2, 4, 8, 13, 26, or 52>,
    "benefitPeriodMonths": <integer: 0=to-age-65, 12, 24, or 60>,
    "monthlyBenefit": <AUD monthly benefit as number>,
    "annualPremium": <AUD annual premium as number — use when user mentions "premium" or "IP premium">,
    "occupationDefinition": <"OWN_OCCUPATION"|"ANY_OCCUPATION"|"ACTIVITIES_OF_DAILY_LIVING"|"UNKNOWN">,
    "stepDownApplies": <true|false>,
    "hasIndexation": <true|false>,
    "hasPremiumWaiver": <true|false>
  },
  "proposedPolicy": {
    "insurerName": <string>,
    "waitingPeriodWeeks": <integer>,
    "benefitPeriodMonths": <integer>,
    "monthlyBenefit": <AUD number>,
    "annualPremium": <AUD number>,
    "occupationDefinition": <string>,
    "hasIndexation": <true|false>,
    "hasPremiumWaiver": <true|false>
  },
  "goals": {
    "wantsReplacement": <true|false>,
    "wantsRetention": <true|false>,
    "affordabilityIsConcern": <true|false>,
    "employerSickPayWeeks": <integer — weeks of employer sick pay available>,
    "wantsOwnOccupationDefinition": <true|false>,
    "wantsLongBenefitPeriod": <true|false>,
    "wantsIndexation": <true|false>
  },
  "financialPosition": {
    "monthlyExpenses": <AUD monthly expenses as number>,
    "liquidAssets": <AUD number>,
    "mortgageBalance": <AUD number>
  }
}""",
    "purchase_retain_life_tpd_policy": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "client": {
    "age": <integer>,
    "annualGrossIncome": <annual gross income AUD as number>,
    "numberOfDependants": <integer>,
    "dateOfBirth": <ISO date string YYYY-MM-DD>
  },
  "existingPolicy": {
    "hasExistingPolicy": <true|false>,
    "lifeSumInsured": <AUD number>,
    "tpdSumInsured": <AUD number>,
    "annualPremium": <AUD number — use this when user mentions "premium" or "insurance premium">,
    "insurerName": <string>,
    "tpdDefinition": <"OWN_OCCUPATION"|"ANY_OCCUPATION"|"ACTIVITIES_OF_DAILY_LIVING">
  },
  "proposedPolicy": {
    "lifeSumInsured": <AUD number>,
    "tpdSumInsured": <AUD number>,
    "annualPremium": <AUD number>
  },
  "financialPosition": {
    "totalLiabilities": <AUD number>,
    "liquidAssets": <AUD number>
  },
  "health": {
    "height": <metres as float e.g. 1.75>,
    "weight": <kg as float>,
    "isSmoker": <true|false>,
    "conditions": [<string>, ...]
  }
}""",
    "purchase_retain_life_insurance_in_super": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "member": {
    "age": <integer>,
    "superBalance": <AUD number>,
    "annualIncome": <AUD number>,
    "annualPremium": <AUD number — use this when user mentions "insurance premium" or "premium">,
    "employmentStatus": <"EMPLOYED_FULL_TIME"|"EMPLOYED_PART_TIME"|"SELF_EMPLOYED"|"UNEMPLOYED">,
    "accountInactiveMonths": <integer>
  },
  "fund": {
    "fundName": <string>,
    "isMySuperProduct": <true|false>
  }
}""",
    "tpd_policy_assessment": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "client": {
    "age": <integer>,
    "annualGrossIncome": <annual gross income AUD as number>,
    "occupationClass": <"CLASS_1_WHITE_COLLAR"|"CLASS_2_LIGHT_BLUE"|"CLASS_3_BLUE_COLLAR"|"CLASS_4_HAZARDOUS"|"UNKNOWN">,
    "occupation": <free-text occupation description>,
    "isSmoker": <true|false>,
    "yearsToRetirement": <number — years until planned retirement>
  },
  "existingPolicy": {
    "hasExistingPolicy": <true|false>,
    "insurerName": <string>,
    "tpdSumInsured": <AUD sum insured as number>,
    "annualPremium": <AUD annual premium as number — use when user mentions "TPD premium" or "premium">,
    "premiumType": <"STEPPED"|"LEVEL"|"UNKNOWN">,
    "tpdDefinition": <"OWN_OCCUPATION"|"MODIFIED_OWN_OCCUPATION"|"ANY_OCCUPATION"|"ACTIVITIES_OF_DAILY_LIVING"|"HOME_DUTIES"|"UNKNOWN">,
    "inSuper": <true|false — is the TPD cover held inside superannuation?>,
    "fundType": <"MYSUPER"|"CHOICE"|"SMSF"|"DEFINED_BENEFIT"|"UNKNOWN">,
    "isMySuperProduct": <true|false>,
    "isGrandfathered": <true|false — pre-1 July 2014 cover grandfathered under SIS Reg 4.07D>,
    "policyLapsed": <true|false>,
    "monthsSinceLapse": <integer>,
    "policyAgeYears": <number — how long the policy has been in force>,
    "accountInactiveMonths": <integer — months since last super contribution>,
    "hasOptedIn": <true|false — PYS opt-in election lodged>,
    "taxableComponentPct": <number 0.0-1.0 — taxable fraction of super benefit>
  },
  "proposedPolicy": {
    "insurerName": <string>,
    "tpdSumInsured": <AUD number>,
    "annualPremium": <AUD number>,
    "premiumType": <"STEPPED"|"LEVEL"|"UNKNOWN">,
    "tpdDefinition": <string>,
    "inSuper": <true|false>
  },
  "health": {
    "existingMedicalConditions": [<string>, ...],
    "hazardousActivities": [<string>, ...],
    "isSmoker": <true|false>
  },
  "financialPosition": {
    "mortgageBalance": <AUD number>,
    "otherDebts": <AUD number>,
    "liquidAssets": <AUD number>,
    "monthlyExpenses": <AUD number>
  },
  "goals": {
    "wantsReplacement": <true|false>,
    "wantsRetention": <true|false>,
    "wantsOwnOccupation": <true|false>,
    "affordabilityIsConcern": <true|false>,
    "prioritisesDefinitionQuality": <true|false>,
    "includeCaresCosts": <true|false>
  }
}""",
    "purchase_retain_trauma_ci_policy": """\
Extract any of these fields that are explicitly stated in the conversation.
Omit fields that are not mentioned. Return only a JSON object.
{
  "client": {
    "age": <integer>,
    "annualGrossIncome": <annual gross income AUD as number>,
    "isSmoker": <true|false>,
    "occupationClass": <"CLASS_1_WHITE_COLLAR"|"CLASS_2_LIGHT_BLUE"|"CLASS_3_BLUE_COLLAR"|"CLASS_4_HAZARDOUS"|"UNKNOWN">,
    "occupation": <free-text occupation description>,
    "dateOfBirth": <ISO date string YYYY-MM-DD>
  },
  "existingPolicy": {
    "hasExistingPolicy": <true|false>,
    "insurerName": <string>,
    "sumInsured": <AUD sum insured as number>,
    "annualPremium": <AUD annual premium as number — use when user mentions "trauma premium", "CI premium", or "premium">,
    "waitingPeriodDays": <integer — days before CI benefit is payable, typically 90>,
    "survivalPeriodDays": <integer — days client must survive post-diagnosis, typically 14 or 30>,
    "premiumType": <"STEPPED"|"LEVEL"|"UNKNOWN">,
    "coveredConditions": [<string>, ...],
    "hasAdvancementBenefit": <true|false — partial benefit for early-stage events>,
    "hasChildRider": <true|false>,
    "hasFemaleRider": <true|false>,
    "hasMultiClaimRider": <true|false — double CI or multi-claim rider>
  },
  "proposedPolicy": {
    "insurerName": <string>,
    "sumInsured": <AUD number>,
    "annualPremium": <AUD number>,
    "waitingPeriodDays": <integer>,
    "survivalPeriodDays": <integer>,
    "premiumType": <"STEPPED"|"LEVEL"|"UNKNOWN">,
    "coveredConditions": [<string>, ...],
    "hasAdvancementBenefit": <true|false>
  },
  "health": {
    "height": <metres as float e.g. 1.75>,
    "weight": <kg as float>,
    "conditions": [<string>, ...]
  },
  "financialPosition": {
    "totalLiabilities": <AUD number>,
    "liquidAssets": <AUD number>,
    "mortgageBalance": <AUD number>,
    "monthlyExpenses": <AUD number>
  },
  "goals": {
    "wantsReplacement": <true|false>,
    "wantsRetention": <true|false>,
    "affordabilityIsConcern": <true|false>,
    "wantsAdvancementBenefit": <true|false>,
    "wantsMultiClaimRider": <true|false>
  }
}""",
}


async def _extract_tool_inputs(
    tool_name: str, message: str, recent_messages: list[dict]
) -> dict:
    """
    Use the LLM to extract structured tool inputs from the full conversation.
    Pulls data from ALL recent messages so multi-turn Q&A accumulates correctly.
    Returns a (possibly partial) dict; missing fields are simply absent.
    """
    schema = _TOOL_INPUT_SCHEMAS.get(tool_name)
    if not schema:
        return {}

    from app.core.llm import get_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    # Build full conversation context including the current message
    history = "\n".join(
        f"{m['role'].upper()}: {m['content']}" for m in recent_messages[-10:]
    )
    full_context = f"{history}\nUSER: {message}" if history else f"USER: {message}"

    system = f"""You are a data extraction assistant for an insurance advisory system.
{schema}

Rules:
- Extract ONLY values explicitly stated in the conversation. Never infer or guess.
- Include a field ONLY if its value is clearly present.
- Monetary values must be plain numbers (300000, not "$300,000").
- Return ONLY valid compact JSON. No explanation, no markdown fences."""

    model = get_chat_model(temperature=0.0)
    try:
        response = await model.ainvoke([
            SystemMessage(content=system),
            HumanMessage(content=f"Conversation:\n{full_context}\n\nReturn extracted JSON:"),
        ])
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
        extracted = json.loads(raw)
        logger.debug("_extract_tool_inputs [%s]: %s", tool_name, list(extracted.keys()))
        return extracted if isinstance(extracted, dict) else {}
    except Exception as exc:
        logger.warning("_extract_tool_inputs failed for %s: %s", tool_name, exc)
        return {}


async def _classify_by_llm(message: str, recent_messages: list[dict]) -> dict:
    """
    Use the configured LLM to classify intent when rules are insufficient.
    Returns {"intent": ..., "selected_tool": ..., "extracted_tool_input": ...}.
    """
    from app.core.llm import get_chat_model
    from langchain_core.messages import HumanMessage, SystemMessage

    model = get_chat_model(temperature=0.0)

    system_prompt = """You are an intent classifier for an insurance advisory AI system.
Classify the user's message into exactly one of these intents:
- "purchase_retain_life_insurance_in_super": questions about life insurance inside superannuation, PYS rules, switch-off triggers, MySuper, insurance opt-in/opt-out
- "purchase_retain_life_tpd_policy": questions about life or TPD insurance policies (purchase, retain, replace, supplement), cover needs, policy comparison, underwriting
- "purchase_retain_income_protection_policy": questions about standalone income protection / disability income insurance OUTSIDE of super — waiting periods, benefit periods, monthly benefit amounts, occupation definitions, premium waiver, indexation, IP policy replacement or retention, income replacement gap
- "purchase_retain_ip_in_super": questions about income protection (salary continuance) insurance held INSIDE a superannuation fund — SIS Reg 6.15 work test, group IP in super, portability window, SPS 250 trustee obligations, IP premium from super balance, SMSF insurance, super fund IP claim
- "purchase_retain_trauma_ci_policy": questions about trauma or critical illness (CI) insurance — purchasing, retaining, or replacing a trauma/CI policy; CI sum insured need; covered conditions (cancer, heart attack, stroke); waiting period (90 days); survival period (14–30 days); advancement/partial benefits; Life Code minimum definitions; CI premium affordability; CI underwriting risk; cooling-off period; CI cannot be held in superannuation
- "tpd_policy_assessment": questions specifically about TPD insurance definition quality (own-occupation vs any-occupation vs activities of daily living/ADL), TPD placement in super vs retail, SIS Reg 4.07C/D compliance, grandfathered own-occ TPD, TPD claim eligibility and decline rates (ASIC Rep 633), super TPD tax treatment (ITAA Div. 295), TPD lapse and reinstatement, AFCA TPD disputes, SPS 250 trustee obligations, automatic acceptance limit, permanent incapacity condition of release, TPD premium structure analysis
- "direct_response": general questions, greetings, clarifications not requiring a tool
- "clarification_needed": message is too ambiguous to classify

Respond with a JSON object only:
{"intent": "<intent>", "selected_tool": "<tool_name or null>", "reasoning": "<one sentence>"}

tool_name must be exactly "purchase_retain_life_insurance_in_super" or "purchase_retain_life_tpd_policy" or "purchase_retain_income_protection_policy" or "purchase_retain_ip_in_super" or "purchase_retain_trauma_ci_policy" or "tpd_policy_assessment" or null."""

    context_str = ""
    if recent_messages:
        context_str = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in recent_messages[-4:])

    user_content = f"Conversation context:\n{context_str}\n\nNew message: {message}" if context_str else message

    try:
        response = await model.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_content),
        ])
        raw = response.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        return {
            "intent": result.get("intent", Intent.DIRECT_RESPONSE),
            "selected_tool": result.get("selected_tool"),
            "extracted_tool_input": None,
        }
    except Exception as exc:
        logger.warning("LLM classification failed: %s — defaulting to direct_response", exc)
        return {"intent": Intent.DIRECT_RESPONSE, "selected_tool": None, "extracted_tool_input": None}


async def classify_intent(state: AgentState) -> dict:
    """Classify intent and select the appropriate tool (if any)."""

    # Fast path: caller supplied a full tool input override
    if state.get("tool_input_override") and state.get("tool_hint"):
        tool_name = state["tool_hint"]
        if tool_exists(tool_name):
            return {
                "intent": tool_name,
                "selected_tool": tool_name,
                "extracted_tool_input": state["tool_input_override"],
            }

    # Fast path: caller supplied a tool hint (no pre-built input)
    if state.get("tool_hint") and tool_exists(state["tool_hint"]):
        return {
            "intent": state["tool_hint"],
            "selected_tool": state["tool_hint"],
            "extracted_tool_input": None,
        }

    message = state.get("user_message", "")
    recent = state.get("recent_messages", [])

    # Try rule-based classification first
    rule_intent = _classify_by_rules(message)

    if rule_intent and rule_intent == Intent.DIRECT_RESPONSE:
        return {"intent": Intent.DIRECT_RESPONSE, "selected_tool": None, "extracted_tool_input": None}

    if rule_intent and rule_intent in (
        Intent.TOOL_LIFE_INSURANCE_IN_SUPER,
        Intent.TOOL_LIFE_TPD_POLICY,
        Intent.TOOL_INCOME_PROTECTION_POLICY,
        Intent.TOOL_IP_IN_SUPER,
        Intent.TOOL_TRAUMA_CI_POLICY,
        Intent.TOOL_TPD_POLICY_ASSESSMENT,
    ):
        logger.debug("classify_intent: rule match → %s", rule_intent)
        tool_input = await _extract_tool_inputs(rule_intent, message, recent)
        return {"intent": rule_intent, "selected_tool": rule_intent, "extracted_tool_input": tool_input or None}

    # Fall back to LLM
    logger.debug("classify_intent: no rule match — falling back to LLM")
    result = await _classify_by_llm(message, recent)

    intent = result["intent"]
    selected_tool = result.get("selected_tool")

    # Safety check: ensure selected_tool is in the registry
    if selected_tool and not tool_exists(selected_tool):
        selected_tool = None
        intent = Intent.DIRECT_RESPONSE

    # Extract structured inputs when a tool is selected
    tool_input: dict | None = None
    if selected_tool:
        tool_input = await _extract_tool_inputs(selected_tool, message, recent) or None

    return {
        "intent": intent,
        "selected_tool": selected_tool,
        "extracted_tool_input": tool_input,
    }
