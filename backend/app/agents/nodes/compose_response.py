"""
compose_response.py — Node: compose the final assistant response.

If a tool was executed:
  - Summarise the tool result using the LLM for natural language explanation.
  - Attach the structured tool result payload for the frontend to render.

If no tool was executed (direct response or error):
  - Use the LLM to compose a helpful contextual response.
"""

import logging
import json
import os
from pathlib import Path
from app.agents.state import AgentState
from app.core.constants import Intent
from app.core.llm import get_chat_model

logger = logging.getLogger(__name__)

# Knowledge base directory — relative to this file's location
_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "knowledge" / "products"

_KNOWLEDGE_FILES = {
    "purchase_retain_life_tpd_policy":           "life-cover-comparison.md",
    # Inside-super questions get the super fund product guide (group cover, fund options, BMI/underwriting,
    # split strategy) rather than the retail provider comparison.
    "purchase_retain_life_insurance_in_super":   "super-fund-insurance.md",
    "purchase_retain_income_protection_policy":  "income-protection-comparison.md",
    "purchase_retain_ip_in_super":               "income-protection-comparison.md",
    "tpd_policy_assessment":                     "tpd-cover-comparison.md",
    "purchase_retain_trauma_ci_policy":          "trauma-cover-comparison.md",
    "purchase_retain_tpd_in_super":              "super-fund-insurance.md",
}


# Static base regulations that always apply for each tool.
# These are shown in every response regardless of what the tool computed.
_BASE_REGULATIONS: dict[str, list[str]] = {
    "purchase_retain_life_insurance_in_super": [
        "SIS Act 1993 s 52 — trustee covenant: must formulate and give effect to an insurance strategy",
        "SIS Act 1993 s 68AAA — inactivity switch-off: no insurance if account inactive ≥ 16 continuous months (unless member elects)",
        "SIS Act 1993 s 68AAB — low-balance switch-off: no insurance if balance < $6,000 (unless member elects)",
        "SIS Act 1993 s 68AAC — under-25 switch-off: no insurance for members under age 25 (unless member elects)",
        "Protecting Your Super (PYS) Act 2019 — commencement 1 Nov 2019",
        "Putting Members' Interests First (PMIF) Act 2019",
        "Corporations Regulations 7.9.44B–C — prescribed inactivity notice content and timing (9/12/15-month triggers)",
        "APRA SPS 250 (Insurance in Superannuation) — insurance management framework obligations",
    ],
    "purchase_retain_tpd_in_super": [
        "SIS Act 1993 s 52 — trustee covenant: pursue claims with reasonable prospect of success",
        "SIS Act 1993 s 68AAA — inactivity switch-off (≥ 16 months inactive)",
        "SIS Act 1993 s 68AAB — low-balance switch-off (balance < $6,000)",
        "SIS Act 1993 s 68AAC — under-25 switch-off",
        "SIS Reg 4.07C — Automatic Acceptance Limit (AAL) ~$100,000 for group TPD cover",
        "SIS Reg 4.07D — own-occupation TPD definition prohibited in super for new policies post-1 July 2014",
        "Protecting Your Super (PYS) Act 2019",
        "Corporations Regulations 7.9.44B–C — inactivity notice obligations",
        "APRA SPS 250 — insurance strategy and cost-not-to-erode-retirement-income obligation",
        "ASIC REP 633 — TPD claims handling practices (any-occ ~80% approval, own-occ ~88%)",
    ],
    "purchase_retain_ip_in_super": [
        "SIS Act 1993 s 68A — income stream benefits from super; IP inside super must be salary continuance",
        "SIS Act 1993 ss 68AAA–68AAC — PYS inactivity / low-balance / under-25 switch-off triggers",
        "SIS Reg 6.15 — condition of release: gainful employment ≥ 20 hrs/week for default IP cover",
        "APRA SPS 250 (effective 1 July 2022) — Insurance in Superannuation governance",
        "APRA IDII Sustainability Reforms (Oct 2021) — replacement ratio cap 70%, benefit period and step-down rules",
        "Protecting Your Super (PYS) Act 2019",
    ],
    "purchase_retain_life_tpd_policy": [
        "Life Insurance Act 1995 — minimum standards for life insurance contracts",
        "ASIC RG 175 — Licensing: Financial product advisers — conduct and disclosure",
        "ASIC RG 90 — Example Statement of Advice (SOA) guidance",
        "APRA LPS 360 — life insurance product design requirements",
        "ASIC REP 633 — TPD claims handling benchmarks (claim approval rates by definition)",
    ],
    "purchase_retain_income_protection_policy": [
        "Life Insurance Act 1995 — minimum standards for disability income insurance",
        "ASIC RG 175 — adviser conduct and disclosure obligations",
        "APRA IDII Sustainability Reforms (Oct 2021) — agreed-value IP abolished; replacement ratio capped at 70%; own-occ step-down to any-occ after 2 years on claim",
        "APRA LPS 360 — disability income product design",
        "ASIC RG 90 — SOA and advice documentation requirements",
    ],
    "tpd_policy_assessment": [
        "SIS Reg 4.07C — Automatic Acceptance Limit ~$100,000 (no health questions below this threshold)",
        "SIS Reg 4.07D — own-occupation TPD banned in super for new policies post-1 July 2014",
        "APRA SPS 250 — insurance in superannuation governance framework",
        "ASIC REP 633 — TPD claims review: approval rates any-occ ~80%, own-occ ~88%, ADL ~40%",
        "ASIC REP 498 — life insurance claims and disputes data",
        "AFCA jurisdiction — maximum TPD claim dispute: $3,000,000",
        "Life Insurance Act 1995 — contestability period 2 years; reinstatement window 3 years",
    ],
    "purchase_retain_trauma_ci_policy": [
        "SIS Act 1993 / Life Insurance Act 1995 — trauma/CI cover CANNOT be purchased inside super for new policies after 1 July 2014 (SIS Act prohibition)",
        "FSC Life Insurance Code of Practice (2017) s 3.2 — minimum conditions: cancer, heart attack, stroke must be covered",
        "Life Insurance Act 1995 — minimum product standards; 14-day cooling-off period (industry: 30 days)",
        "ASIC RG 175 — adviser disclosure and conduct obligations",
        "APRA LICAT — capital adequacy factor 15% of CI sum insured",
    ],
}


def _extract_regulatory_citations(tool_name: str, tool_result: dict) -> dict:
    """
    Build a structured regulatory citations block from static base regulations
    plus dynamic flags and triggered rules from the tool result.
    Returns a dict with 'base_regulations', 'triggered_rules', and 'compliance_flags'.
    """
    # 1. Static base regulations for this tool
    base = _BASE_REGULATIONS.get(tool_name, [])

    # 2. Triggered switch-off rules (inside-super tools)
    triggered_rules = []
    for trigger in tool_result.get("switch_off_triggers", []):
        if trigger.get("triggered") or trigger.get("effectively_active"):
            triggered_rules.append({
                "rule": trigger.get("trigger", ""),
                "detail": trigger.get("reason", ""),
            })

    # 3. TPD definition compliance (tpd_in_super specific)
    defn = tool_result.get("tpd_definition_assessment") or {}
    if defn.get("compliance_breach"):
        triggered_rules.append({
            "rule": "SIS Reg 4.07D VIOLATION",
            "detail": defn.get("compliance_note", "Own-occupation TPD in super — non-compliant post-July 2014."),
        })

    # 4. Dynamic compliance flags from tools that produce them (tpd_policy_assessment, trauma_ci)
    compliance_flags = []
    for flag in tool_result.get("compliance_flags", []):
        severity = flag.get("severity", "INFO")
        if severity in ("CRITICAL", "WARNING"):
            compliance_flags.append({
                "severity": severity,
                "code": flag.get("code", ""),
                "detail": flag.get("message", ""),
            })

    # 5. Regulatory notes formatted as human-readable citations (tpd_policy_assessment)
    reg_notes = tool_result.get("regulatory_notes") or {}
    formatted_notes = []
    _note_labels = {
        "sis_reg_407c_aal_aud":            "SIS Reg 4.07C — AAL threshold: ${:,.0f}",
        "sis_reg_407d_cutoff":             "SIS Reg 4.07D — own-occ TPD ban cutoff date: {}",
        "super_tpd_tax_under_60_pct":      "SIS Act — TPD benefit tax (under 60): {}%",
        "super_tpd_tax_over_60_pct":       "SIS Act — TPD benefit tax (over 60): {}% (tax-free)",
        "contestability_years":            "Life Insurance Act — contestability period: {} years",
        "reinstatement_window_years":      "Life Insurance Act — reinstatement window: {} years",
        "afca_max_claim_aud":              "AFCA — maximum dispute claim: ${:,.0f}",
        "inactivity_switch_off_months":    "SIS Act s 68AAA — inactivity threshold: {} months",
        "not_permitted_in_super":          "SIS Act — trauma/CI: NOT permitted inside super (post-July 2014)",
    }
    for key, fmt in _note_labels.items():
        val = reg_notes.get(key)
        if val is not None and val is not False:
            try:
                formatted_notes.append(fmt.format(val))
            except (ValueError, TypeError):
                formatted_notes.append(f"{key}: {val}")

    return {
        "base_regulations": base,
        "triggered_rules": triggered_rules,
        "compliance_flags": compliance_flags,
        "regulatory_notes": formatted_notes,
    }


def _load_knowledge(tool_name: str) -> str:
    """Load the relevant provider comparison knowledge for a tool."""
    filename = _KNOWLEDGE_FILES.get(tool_name)
    if not filename:
        return ""
    path = _KNOWLEDGE_DIR / filename
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not load knowledge file %s: %s", path, exc)
        return ""

_SYSTEM_PROMPT = """You are an expert insurance adviser AI assistant for financial advisers in Australia.
You help advisers analyse insurance scenarios, interpret tool results, and communicate clearly.
Always be professional, precise, and grounded in the facts provided.
Do NOT invent figures, legal rules, or outcomes. If uncertain, say so.
Keep responses concise and well-structured.
Use plain Australian English.

When the user is correcting or updating a client detail (e.g. "John has 3 kids not 2",
"his age is 46 not 42", "income is $160,000 not $140,000"), respond with a SHORT
acknowledgement only — 1 to 3 sentences. Confirm exactly what was updated, then offer
to recalculate the analysis if relevant. Do NOT repeat or re-summarise the full prior
analysis. Example: "Got it — I've noted John has 3 children (ages 8, 11, and 12).
Would you like me to recalculate the life insurance analysis with this updated information?"
"""


def _build_tool_summary_prompt(tool_name: str, tool_result: dict, user_message: str) -> str:
    """Build a prompt to summarise a tool result in natural language."""
    # Extract key fields for the summary (keep it concise for the LLM)
    summary_data: dict = {}

    missing_questions = tool_result.get("missing_info_questions", [])
    blocking_questions = [q for q in missing_questions if q.get("blocking")]
    nonblocking_questions = [q for q in missing_questions if not q.get("blocking")]

    if tool_name == "purchase_retain_life_insurance_in_super":
        cna = tool_result.get("coverage_needs_analysis") or {}
        placement = tool_result.get("placement_assessment") or {}
        legal_status = tool_result.get("legal_status", "ALLOWED_AND_ACTIVE")
        # Health / underwriting data passed through from client input
        health = tool_result.get("health") or {}
        height_cm = health.get("heightCm")
        weight_kg = health.get("weightKg")
        bmi = round(weight_kg / ((height_cm / 100) ** 2), 1) if height_cm and weight_kg else None
        summary_data = {
            # Coverage adequacy — lead with this, not legal status
            "coverage_needs_analysis_available": cna.get("needs_analysis_available"),
            "total_need_low":  cna.get("total_need_low"),
            "total_need_high": cna.get("total_need_high"),
            "existing_cover":  cna.get("existing_cover"),
            "shortfall_estimate": cna.get("shortfall_estimate"),
            "shortfall_level": cna.get("shortfall_level"),
            "needs_summary": cna.get("recommendation_summary"),
            # Placement strategy
            "placement_recommendation": placement.get("recommendation"),
            "inside_super_score":  placement.get("inside_super_score"),
            "outside_super_score": placement.get("outside_super_score"),
            "placement_reasoning": placement.get("reasoning", [])[:3],
            "placement_risks":     placement.get("risks", [])[:2],
            # Legal status — context only, not the lead
            "legal_status": legal_status,
            "legal_status_note": (
                "Cover is legally permissible inside super under the SIS Act."
                if legal_status == "ALLOWED_AND_ACTIVE" else
                tool_result.get("legal_reasons", [""])[0] if tool_result.get("legal_reasons") else ""
            ),
            # Health / underwriting profile (for AAL and loading assessment)
            "client_bmi": bmi,
            "bmi_category": (
                "Healthy (18.5–24.9)" if bmi and bmi < 25 else
                "Overweight (25–29.9)" if bmi and bmi < 30 else
                "Obese class I (30–34.9)" if bmi and bmi < 35 else
                "Obese class II+ (35+)" if bmi else None
            ),
            "medical_conditions": health.get("existingMedicalConditions", []),
            "current_medications": health.get("currentMedications", []),
            "is_smoker": health.get("isSmoker"),
            "underwriting_note": (
                "Clean health profile — standard group cover rates expected, no loading anticipated."
                if bmi and bmi < 30 and not health.get("existingMedicalConditions") and not health.get("isSmoker")
                else "Health profile requires review against fund underwriting guidelines."
            ),
            "advice_mode": tool_result.get("advice_mode"),
            "top_actions": [a["action"] for a in tool_result.get("member_actions", [])[:3]],
            "optional_questions": [q["question"] for q in nonblocking_questions[:3]],
        }
    elif tool_name == "purchase_retain_life_tpd_policy":
        rec = tool_result.get("recommendation", {})
        summary_data = {
            "recommendation_type": rec.get("type"),
            "summary": rec.get("summary"),
            "reasons": rec.get("reasons", [])[:3],
            "risks": rec.get("risks", [])[:3],
            "life_shortfall": rec.get("life_need", {}).get("shortfall_level") if rec.get("life_need") else None,
            "tpd_shortfall": rec.get("tpd_need", {}).get("shortfall_level") if rec.get("tpd_need") else None,
            "affordability": rec.get("affordability", {}).get("assessment"),
            "underwriting_risk": rec.get("underwriting_risk", {}).get("overall_risk"),
            "top_actions": [a["action"] for a in rec.get("required_actions", [])[:2]],
            "blocking_questions": [q["question"] for q in blocking_questions],
            "optional_questions": [q["question"] for q in nonblocking_questions],
        }
    elif tool_name == "purchase_retain_income_protection_policy":
        rec = tool_result.get("recommendation", {})
        bn  = rec.get("benefit_need", {})
        wp  = rec.get("waiting_period", {})
        bp  = rec.get("benefit_period", {})
        aff = rec.get("affordability", {})
        uw  = rec.get("underwriting_risk", {})
        summary_data = {
            "recommendation_type":           rec.get("type"),
            "summary":                        rec.get("summary"),
            "reasons":                        rec.get("reasons", [])[:3],
            "risks":                          rec.get("risks", [])[:3],
            "income_shortfall_level":         bn.get("shortfall_level"),
            "monthly_gap":                    bn.get("monthly_gap"),
            "recommended_monthly_benefit":    bn.get("recommended_monthly_benefit"),
            "recommended_waiting_weeks":      wp.get("recommended_waiting_period_weeks"),
            "waiting_period_comparison":      wp.get("comparison"),
            "recommended_benefit_period":     bp.get("recommended_benefit_period_label"),
            "step_down_risk":                 bp.get("step_down_risk"),
            "affordability_band":             aff.get("affordability_band"),
            "underwriting_risk":              uw.get("overall_risk"),
            "advice_mode":                    tool_result.get("advice_mode"),
            "top_actions":                    [a["action"] for a in rec.get("required_actions", [])[:2]],
            "blocking_questions":             [q["question"] for q in blocking_questions],
            "optional_questions":             [q["question"] for q in nonblocking_questions],
        }
    elif tool_name == "purchase_retain_ip_in_super":
        rec  = tool_result.get("recommendation", {})
        tax  = tool_result.get("tax_comparison", {})
        drag = tool_result.get("retirement_drag", {})
        bn   = tool_result.get("benefit_need", {})
        pa   = tool_result.get("placement_assessment", {})
        wt   = tool_result.get("work_test", {})
        port = tool_result.get("portability", {})
        summary_data = {
            "recommendation_type":          rec.get("type"),
            "summary":                      rec.get("summary"),
            "reasons":                      rec.get("reasons", [])[:3],
            "risks":                        rec.get("risks", [])[:3],
            "legal_status":                 tool_result.get("legal_status"),
            "legal_reasons":                tool_result.get("legal_reasons", [])[:2],
            "work_test_passes":             wt.get("passes"),
            "work_test_status":             wt.get("employment_status"),
            "placement_recommendation":     pa.get("recommendation"),
            "inside_score":                 pa.get("inside_score"),
            "outside_score":                pa.get("outside_score"),
            "tax_favours_outside":          tax.get("tax_favours_outside"),
            "tax_summary":                  tax.get("tax_summary"),
            "retirement_drag_estimate":     drag.get("estimated_balance_reduction") if drag else None,
            "monthly_shortfall":            bn.get("monthly_shortfall") if isinstance(bn, dict) else None,
            "portability_status":           port.get("status"),
            "advice_mode":                  tool_result.get("advice_mode"),
            "top_actions":                  [a["action"] for a in tool_result.get("member_actions", [])[:2]],
            "blocking_questions":           [q["question"] for q in blocking_questions],
            "optional_questions":           [q["question"] for q in nonblocking_questions],
        }

    elif tool_name == "tpd_policy_assessment":
        rec       = tool_result.get("recommendation", {})
        tpd_need  = tool_result.get("tpd_need", {})
        defn      = tool_result.get("definition_evaluation", {})
        placement = tool_result.get("super_placement", {})
        uw        = tool_result.get("underwriting_risk", {})
        summary_data = {
            "recommendation_type":        rec.get("type"),
            "summary":                    rec.get("summary"),
            "reasons":                    rec.get("reasons", [])[:3],
            "risks":                      rec.get("risks", [])[:3],
            "shortfall_level":            tpd_need.get("shortfall_level"),
            "tpd_need_estimate":          tpd_need.get("tpd_need_estimate"),
            "existing_cover":             tpd_need.get("existing_tpd_cover"),
            "shortfall_estimate":         tpd_need.get("shortfall"),
            "definition_quality":         defn.get("quality_score"),
            "definition_rank":            defn.get("rank"),
            "definition_recommendation":  defn.get("recommendation"),
            "placement_recommendation":   placement.get("recommendation"),
            "super_claims_approval_rate": placement.get("super_claims_approval_rate"),
            "retail_claims_approval_rate": placement.get("retail_claims_approval_rate"),
            "underwriting_risk":          uw.get("overall_risk_level"),
            "top_actions":                [a for a in tool_result.get("member_actions", [])[:3]],
            "blocking_questions":         [q["question"] for q in blocking_questions],
            "optional_questions":         [q["question"] for q in nonblocking_questions],
        }

    elif tool_name == "purchase_retain_trauma_ci_policy":
        rec       = tool_result.get("recommendation", {})
        ci_need   = tool_result.get("ci_need", {})
        gap       = tool_result.get("coverage_gap", {})
        aff       = tool_result.get("affordability", {})
        uw        = tool_result.get("underwriting_risk", {})
        super_elig = tool_result.get("super_eligibility", {})
        summary_data = {
            "recommendation_type":  rec.get("type"),
            "summary":              rec.get("summary"),
            "reasons":              rec.get("reasons", [])[:3],
            "risks":                rec.get("risks", [])[:3],
            "shortfall_level":      gap.get("shortfall_level"),
            "ci_need_estimate":     ci_need.get("ci_need_estimate"),
            "existing_cover":       gap.get("existing_ci_cover"),
            "shortfall_estimate":   gap.get("shortfall"),
            "super_eligible":       super_elig.get("eligible"),
            "super_note":           super_elig.get("note"),
            "affordability_band":   aff.get("affordability_band"),
            "underwriting_risk":    uw.get("overall_risk"),
            "top_actions":          [a for a in tool_result.get("member_actions", [])[:3]],
            "blocking_questions":   [q["question"] for q in blocking_questions],
            "optional_questions":   [q["question"] for q in nonblocking_questions],
        }

    elif tool_name == "purchase_retain_tpd_in_super":
        cna = tool_result.get("coverage_needs_analysis") or {}
        placement = tool_result.get("placement_assessment") or {}
        legal_status = tool_result.get("legal_status", "ALLOWED_AND_ACTIVE")
        health = tool_result.get("health") or {}
        height_cm = health.get("heightCm")
        weight_kg = health.get("weightKg")
        bmi = round(weight_kg / ((height_cm / 100) ** 2), 1) if height_cm and weight_kg else None
        summary_data = {
            "coverage_needs_available": cna.get("needs_analysis_available"),
            "tpd_need_low": cna.get("tpd_need_low"),
            "tpd_need_high": cna.get("tpd_need_high"),
            "existing_cover": cna.get("existing_tpd_cover"),
            "shortfall_estimate": cna.get("shortfall_estimate"),
            "shortfall_level": cna.get("shortfall_level"),
            "needs_summary": cna.get("recommendation_summary"),
            "placement_recommendation": placement.get("recommendation"),
            "inside_super_score": placement.get("inside_super_score"),
            "retail_score": placement.get("retail_score"),
            "placement_reasoning": placement.get("reasoning", [])[:3],
            "tpd_definition_in_super": "ANY_OCCUPATION (own-occupation banned in super post-July 2014 per SIS Reg 4.07D)",
            "super_claims_approval_rate": "~80% (any-occupation definition)",
            "retail_claims_approval_rate": "~88% (own-occupation definition)",
            "legal_status": legal_status,
            "legal_status_note": (
                "TPD cover is legally permissible inside super under the SIS Act."
                if legal_status == "ALLOWED_AND_ACTIVE" else
                tool_result.get("legal_reasons", [""])[0] if tool_result.get("legal_reasons") else ""
            ),
            "client_bmi": bmi,
            "underwriting_note": (
                "Clean health profile — standard group cover rates, no loading expected."
                if bmi and bmi < 30 and not health.get("existingMedicalConditions") and not health.get("isSmoker")
                else "Health profile may require review against fund underwriting guidelines."
            ),
            "retirement_drag_estimate": tool_result.get("retirement_drag_estimate"),
            "beneficiary_tax_risk": tool_result.get("beneficiary_tax_risk"),
            "top_actions": [a["action"] for a in tool_result.get("member_actions", [])[:3]],
            "optional_questions": [q["question"] for q in nonblocking_questions[:3]],
        }

    # Inject regulatory citations into every tool response (applies to all 7 tools)
    summary_data["regulatory_citations"] = _extract_regulatory_citations(tool_name, tool_result)

    has_blocking = bool(summary_data.get("blocking_questions"))
    missing_instruction = ""
    if has_blocking:
        missing_instruction = (
            "\n- IMPORTANT: blocking_questions lists required information that MUST be provided "
            "before a recommendation can be given. After summarising what you know, explicitly "
            "ask the user for each blocking question, numbered (1. 2. 3. …). "
            "Make it clear you need these answers to complete the analysis."
        )
    elif summary_data.get("optional_questions"):
        missing_instruction = (
            "\n- optional_questions lists data that would improve the analysis. "
            "Mention these as optional follow-up items at the end of your response."
        )

    # Tool-specific framing instructions
    lead_instruction = "- Lead with the key outcome (recommendation type / coverage adequacy)."
    if tool_name == "purchase_retain_life_insurance_in_super":
        lead_instruction = (
            "- Lead with the coverage adequacy finding: is the client underinsured? By how much?\n"
            "- Then explain the placement recommendation (inside super / split / outside super) "
            "and WHY it suits the client's situation (cashflow, tax, affordability).\n"
            "- Mention the legal status only as supporting context (e.g. 'cover is legally permissible'), "
            "NOT as the headline. Do NOT say 'legal status undetermined' unless there is a genuine "
            "SIS Act compliance problem.\n"
            "- If the shortfall is SIGNIFICANT or CRITICAL, clearly state the client is materially "
            "underinsured and recommend increasing cover.\n"
            "- If placement_recommendation is INSIDE_SUPER or SPLIT_STRATEGY, explain why keeping "
            "cover inside super (with potential top-up outside) suits a cost-conscious client.\n"
            "- If client_bmi and underwriting_note are present, comment on the client's underwriting "
            "profile: state the BMI, whether standard rates are expected, and that no loading is "
            "anticipated for a clean health profile.\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend specific super fund products. "
            "Reference 2–3 suitable industry funds (e.g. AustralianSuper, CareSuper, Australian Retirement Trust) "
            "based on the client's occupation and cover needs. Explain the recommended two-step approach: "
            "(1) increase cover inside current or preferred fund up to the AAL, "
            "(2) top up with retail cover outside super if the ceiling is insufficient.\n"
            "- Do NOT recommend moving to outside super as the primary recommendation unless "
            "outside_super_score is clearly dominant AND there is a specific reason (e.g. non-dependant "
            "beneficiary, own-occupation definition need)."
        )

    elif tool_name == "purchase_retain_life_tpd_policy":
        lead_instruction = (
            "- Lead with the coverage adequacy finding: is the client underinsured for life / TPD? By how much?\n"
            "- State the shortfall_level clearly (e.g. CRITICAL, SIGNIFICANT) before anything else.\n"
            "- Then explain the underwriting outcome: what risk level was assessed and whether loadings are expected.\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend 2–3 specific retail insurers (e.g. TAL, AIA, Zurich) "
            "with brief reasons for each (claims track record, definition quality, price competitiveness).\n"
            "- Note affordability: state the affordability_band and whether premiums fit the client's budget.\n"
            "- Keep legal/compliance notes brief and factual — do NOT lead with them."
        )
    elif tool_name == "purchase_retain_income_protection_policy":
        lead_instruction = (
            "- Lead with the income replacement need: how much monthly benefit does the client need? "
            "What is the current shortfall?\n"
            "- Then explain the recommended waiting period and benefit period and WHY they suit the client "
            "(e.g. employer sick pay covers the waiting period; benefit period to age 65 for a young client).\n"
            "- Flag any step-down risk (own-occupation to any-occupation after 24 months) if applicable.\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend 2–3 specific insurers for standalone IP, "
            "noting which offer the best definition quality and pricing for the client's occupation class.\n"
            "- State affordability_band clearly. Do NOT lead with legal or compliance detail."
        )
    elif tool_name == "purchase_retain_ip_in_super":
        lead_instruction = (
            "- Lead with the income replacement finding: is the client underinsured for IP? By how much?\n"
            "- Then state the placement recommendation (inside super / outside super / split) and explain "
            "the tax comparison — does inside or outside super produce a better after-tax outcome?\n"
            "- Mention legal status (work test, SIS compliance) as supporting context only, NOT as the headline. "
            "Do NOT say 'legal status undetermined' unless there is a genuine SIS Act compliance breach.\n"
            "- If the placement favours inside super, explain why (tax efficiency, premium from super balance). "
            "If outside super is favoured, explain why (definition quality, benefit taxability).\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend IP products suited to the placement."
        )
    elif tool_name == "tpd_policy_assessment":
        lead_instruction = (
            "- Lead with the coverage adequacy finding: is the client underinsured for TPD? By how much?\n"
            "- Then immediately address definition quality: what rank/quality is the current definition "
            "(own-occupation, any-occupation, ADL)? If it is suboptimal, say so plainly.\n"
            "- State the placement recommendation (retail / super) and contrast the claims approval rates "
            "(e.g. own-occ retail: ~88% vs any-occ super: ~80%).\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend 2–3 specific retail or super fund TPD options "
            "based on definition quality and the client's occupation class.\n"
            "- Keep tax and regulatory notes brief — they are supporting context, not the lead."
        )
    elif tool_name == "purchase_retain_tpd_in_super":
        lead_instruction = (
            "- Lead with coverage adequacy: is the client underinsured for TPD inside super? By how much?\n"
            "- Then immediately address the definition quality issue: inside super only allows any-occupation TPD "
            "(own-occ banned per SIS Reg 4.07D). State this clearly and explain the claims approval rate "
            "difference (any-occ ~80% vs own-occ retail ~88%).\n"
            "- Explain the placement recommendation (inside super / split / retail) and the tax impact "
            "(under 60: ~22% tax on TPD benefit inside super; over 60: tax-free).\n"
            "- If PYS switch-off triggers are present, mention them as action items — NOT as the headline.\n"
            "- Mention legal status as supporting context only. Do NOT say 'legal status undetermined' "
            "unless there is a genuine SIS compliance breach.\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend specific industry super funds with competitive "
            "group TPD cover and high AALs.\n"
            "- Recommend a split strategy where appropriate: any-occ TPD inside super (up to AAL, "
            "cost-efficient) + own-occ retail TPD top-up outside super (for definition quality)."
        )

    elif tool_name == "purchase_retain_trauma_ci_policy":
        lead_instruction = (
            "- Lead with the CI coverage adequacy finding: is the client underinsured? By how much?\n"
            "- Note clearly that trauma/CI CANNOT be purchased inside super for new policies (post-July 2014 "
            "SIS Act prohibition) — this is a fact, not a legal uncertainty.\n"
            "- Then explain the recommended sum insured (3× income + rehab allowance) and why.\n"
            "- Use the PROVIDER KNOWLEDGE BASE to recommend 2–3 retail CI/trauma providers with reasons "
            "(condition breadth, definition quality, premium competitiveness).\n"
            "- State affordability and underwriting outcome. Keep compliance notes factual and brief."
        )

    return f"""The user asked: "{user_message}"

The tool '{tool_name}' returned this structured result:
{json.dumps(summary_data, indent=2)}

Write a clear, professional response for a financial adviser.
{lead_instruction}
- Explain the main reasons in 2-3 sentences.
- Note the top action items if any.{missing_instruction}
- Keep it under 350 words.
- Do NOT make up any numbers not in the data above.

MANDATORY — always end your response with a "## Regulations & Rules Considered" section.
Use the regulatory_citations data in the result to populate it. Structure it as follows:
1. List each item from base_regulations as a bullet point.
2. If triggered_rules is non-empty, add a sub-heading "### Triggered / Violated Rules" and list each with its detail.
3. If compliance_flags is non-empty, add a sub-heading "### Compliance Flags" and list CRITICAL flags first, then WARNING, with their detail.
4. If regulatory_notes is non-empty, add a sub-heading "### Key Regulatory Values" and list each item.
Only include sub-headings that have content. Do NOT invent regulation references not in the data."""


def _build_overseer_context(state) -> dict:
    """
    Extract overseer verdict fields from state into a single dict.
    Returns safe defaults when the overseer has not run (direct-response path).
    """
    return {
        "status":         state.get("overseer_status")        or "proceed",
        "reason":         state.get("overseer_reason")        or "",
        "caution_notes":  state.get("overseer_caution_notes") or [],
        "question":       state.get("overseer_question"),
        "missing_fields": state.get("overseer_missing_fields") or [],
    }


def _build_memory_context_note(client_memory: dict) -> str:
    """
    Build a short memory context note for the LLM system prompt.
    Only included when a rolling summary exists (long conversations).
    """
    summary = (client_memory.get("summary_memory") or {}).get("text", "")
    if not summary:
        return ""
    return f"\n\nClient session context (from structured memory):\n{summary}"


async def compose_response(state: AgentState) -> dict:
    """Compose the final natural language response and structured payload."""
    intent = state.get("intent", Intent.DIRECT_RESPONSE)
    user_message = state.get("user_message", "")
    tool_result = state.get("tool_result")
    tool_error = state.get("tool_error")
    selected_tool = state.get("selected_tool")
    recent_messages = state.get("recent_messages", [])
    client_memory: dict = state.get("client_memory") or {}
    document_context: str | None = state.get("document_context")

    try:
        model = get_chat_model(temperature=0.3)

        from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

        # Build system prompt — inject memory summary context for long conversations
        memory_context = _build_memory_context_note(client_memory)
        system_prompt = _SYSTEM_PROMPT + memory_context

        # Build message history for context
        lc_messages = [SystemMessage(content=system_prompt)]

        # Inject uploaded document text as a reference context block
        if document_context:
            lc_messages.append(SystemMessage(content=(
                "UPLOADED DOCUMENT CONTENT (use this as a primary source for facts about the client):\n\n"
                + document_context
            )))

        for m in recent_messages[-6:]:  # last 6 messages for context
            if m["role"] == "user":
                lc_messages.append(HumanMessage(content=m["content"]))
            elif m["role"] == "assistant":
                lc_messages.append(AIMessage(content=m["content"]))

        # Read overseer verdict (defaults to "proceed" on the direct-response path)
        overseer = _build_overseer_context(state)
        overseer_status = overseer["status"]

        # ── SOA generation path ─────────────────────────────────────────────
        if intent == Intent.GENERATE_SOA:
            from app.services.soa_service import generate_soa as _generate_soa
            soa_result = await _generate_soa(client_memory, recent_messages)

            if "error" in soa_result:
                final_text = (
                    f"I wasn't able to generate the SOA — {soa_result['error']} "
                    "Please try again or check that the conversation has sufficient client details."
                )
                return {"final_response": final_text, "structured_response_payload": None}

            n_sections = len(soa_result.get("sections", []))
            n_missing = len(soa_result.get("missing_questions", []))

            if n_sections == 0:
                final_text = (
                    "I couldn't identify any insurance recommendations in this conversation to generate an SOA from. "
                    "Please run an insurance analysis first (e.g. 'Analyse life cover for James'), then ask me to generate the SOA."
                )
                return {"final_response": final_text, "structured_response_payload": None}

            if n_missing > 0:
                final_text = (
                    f"I've generated your SOA covering {n_sections} insurance section(s) — it's open in the panel on the right. "
                    f"There are {n_missing} field(s) I couldn't fill automatically. "
                    "Answer the questions shown in the panel to complete it, then edit freely in the editor."
                )
            else:
                final_text = (
                    f"Your SOA is ready in the panel on the right — {n_sections} insurance section(s) generated. "
                    "Review and edit the content as needed."
                )

            payload = {
                "type": "soa_draft",
                "sections": soa_result.get("sections", []),
                "missing_questions": soa_result.get("missing_questions", []),
            }

            # Persist draft to conversation so the panel can be restored on reload
            try:
                from app.db.mongo import get_db
                from app.db.collections import CONVERSATIONS
                from app.utils.ids import to_object_id
                _db = get_db()
                await _db[CONVERSATIONS].update_one(
                    {"_id": to_object_id(state["conversation_id"])},
                    {"$set": {"soa_draft": {
                        "sections": payload["sections"],
                        "missing_questions": payload["missing_questions"],
                    }}},
                )
            except Exception as _save_exc:
                logger.warning("Could not persist SOA draft from compose_response: %s", _save_exc)

            return {
                "final_response": final_text,
                "structured_response_payload": payload,
            }

        # Determine what to compose
        if overseer_status == "ask_user":
            # Overseer determined critical data is missing — ask the user
            question = overseer["question"] or "Could you please provide the missing client details so I can complete the analysis?"
            missing = overseer["missing_fields"]
            if missing:
                missing_list = "\n".join(f"- {m['field']}: {m.get('description', '')}" for m in missing)
                prompt = (
                    f"The user asked: \"{user_message}\"\n\n"
                    f"Before completing the analysis, you need additional information.\n"
                    f"Missing details:\n{missing_list}\n\n"
                    f"Ask the user for this information politely and concisely. "
                    f"Suggested question: {question}"
                )
            else:
                prompt = (
                    f"The user asked: \"{user_message}\"\n\n"
                    f"Ask the user: {question}"
                )
            lc_messages.append(HumanMessage(content=prompt))

        elif overseer_status == "reset_context":
            # Severe topic mismatch — acknowledge and reorient
            prompt = (
                f"The user asked: \"{user_message}\"\n\n"
                f"The system detected that the question may not align with the previous analysis context. "
                f"Acknowledge the user's question, and ask them to clarify what specific insurance scenario "
                f"they would like to analyse so you can provide an accurate response."
            )
            lc_messages.append(HumanMessage(content=prompt))

        elif tool_error:
            # Tool failed — acknowledge and ask for the specific data needed
            prompt = (
                f"The user asked: \"{user_message}\"\n\n"
                f"The tool encountered an error: {tool_error}\n\n"
                "Acknowledge this professionally. "
                "If the error mentions missing fields, list exactly which fields are needed, numbered. "
                "Ask the user to provide them so the analysis can be re-run."
            )
            lc_messages.append(HumanMessage(content=prompt))

        elif tool_result and selected_tool:
            # Tool succeeded — summarise in natural language
            prompt = _build_tool_summary_prompt(selected_tool, tool_result, user_message)

            # Append overseer caution notes when status is proceed_with_caution
            if overseer_status == "proceed_with_caution" and overseer["caution_notes"]:
                caution_text = "\n".join(f"- {n}" for n in overseer["caution_notes"])
                prompt += (
                    f"\n\nOVERSEER CAVEATS (mention these naturally in your response where relevant):\n"
                    f"{caution_text}"
                )

            # Inject provider knowledge base so the LLM can recommend specific products
            knowledge = _load_knowledge(selected_tool)
            if knowledge:
                lc_messages.append(SystemMessage(content=(
                    f"PROVIDER KNOWLEDGE BASE (use this to recommend specific products/insurers):\n\n"
                    f"{knowledge}"
                )))
            lc_messages.append(HumanMessage(content=prompt))

        else:
            # Direct response
            lc_messages.append(HumanMessage(content=user_message))

        response = await model.ainvoke(lc_messages)
        final_response = response.content.strip()

        # Build structured payload if tool ran
        structured_payload: dict | None = None
        if tool_result and selected_tool:
            structured_payload = {
                "tool_name": selected_tool,
                "tool_result": tool_result,
                "tool_warnings": state.get("tool_warnings", []),
                "overseer": {
                    "status":       overseer["status"],
                    "reason":       overseer["reason"],
                    "caution_notes": overseer["caution_notes"],
                },
            }

        return {
            "final_response": final_response,
            "structured_response_payload": structured_payload,
        }

    except Exception as exc:
        logger.exception("compose_response error: %s", exc)
        fallback = (
            "I encountered an issue generating a response. "
            "The tool analysis may have completed successfully — please check the structured result."
            if tool_result else
            "I'm having trouble generating a response right now. Please try again."
        )
        return {
            "final_response": fallback,
            "structured_response_payload": {"tool_name": selected_tool, "tool_result": tool_result} if tool_result else None,
        }
