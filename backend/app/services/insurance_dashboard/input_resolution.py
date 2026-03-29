"""
Resolve dashboard inputs using:
  1. Saved analyses (structured tool outputs) — first-class source
  2. AI memory canonical hints
  3. Factfind
  4. Caller overrides (user-supplied after prompt)

Order matches product requirement (analyses before memory before factfind).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.client_analysis_output_repository import ClientAnalysisOutputRepository
from app.insurance_comparison.registry import has_normalizer, normalize_tool_output, unwrap_tool_execution_envelope
from app.insurance_comparison.service import ORCHESTRATOR_TO_BACKEND_TOOL
from app.services.memory_canonical_hints import load_memory_canonical_hints, merge_memory_then_factfind

logger = logging.getLogger(__name__)

_FACTFIND_SECTIONS = ("personal", "financial", "insurance", "health", "goals")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = re.sub(r"[^\d.\-]", "", v.replace(",", ""))
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _backend_tool_name(orch_id: str) -> str | None:
    if orch_id in ORCHESTRATOR_TO_BACKEND_TOOL:
        return ORCHESTRATOR_TO_BACKEND_TOOL[orch_id]
    if has_normalizer(orch_id):
        return orch_id
    return None


def _iso_from_doc(doc: dict[str, Any]) -> str:
    ts = doc.get("created_at")
    if hasattr(ts, "isoformat"):
        return ts.isoformat()
    return str(ts or "")


async def _factfind_canonical(db: AsyncIOMotorDatabase, client_id: str) -> dict[str, dict[str, Any]]:
    from app.db.repositories.factfind_repository import FactfindRepository

    repo = FactfindRepository(db)
    factfind = await repo.get_or_create(client_id)
    sections = factfind.get("sections", {})
    canonical: dict[str, dict[str, Any]] = {s: {} for s in _FACTFIND_SECTIONS}
    for section in _FACTFIND_SECTIONS:
        for field, field_data in sections.get(section, {}).items():
            if isinstance(field_data, dict):
                v = field_data.get("value")
                if v is not None:
                    canonical[section][field] = v
    return canonical


def _extract_existing_recommended_from_raw(raw: dict[str, Any], backend_tool: str) -> dict[str, float | None]:
    """Best-effort extraction of existing vs recommended cover metrics from tool JSON."""
    out: dict[str, float | None] = {
        "existing_life_cover": None,
        "recommended_life_cover": None,
        "existing_tpd_cover": None,
        "recommended_tpd_cover": None,
        "existing_ip_monthly_benefit": None,
        "recommended_ip_monthly_benefit": None,
        "existing_annual_premium": None,
        "recommended_annual_premium": None,
    }
    body = unwrap_tool_execution_envelope(raw)
    rec = body.get("recommendation") or {}
    if backend_tool == "purchase_retain_life_tpd_policy":
        life_need = rec.get("life_need") or {}
        tpd_need = rec.get("tpd_need") or {}
        out["recommended_life_cover"] = _num(life_need.get("net_life_insurance_need"))
        out["existing_life_cover"] = _num(life_need.get("existing_sum_insured")) or _num(life_need.get("existing_cover"))
        out["recommended_tpd_cover"] = _num(tpd_need.get("net_tpd_need"))
        out["existing_tpd_cover"] = _num(tpd_need.get("existing_tpd_cover")) or _num(tpd_need.get("existing_cover"))
        aff = rec.get("affordability") or {}
        comp = rec.get("comparison") or {}
        out["recommended_annual_premium"] = _num(aff.get("total_annual_premium"))
        if isinstance(comp, dict) and comp.get("dimensions"):
            for d in comp.get("dimensions") or []:
                if not isinstance(d, dict):
                    continue
                if d.get("dimension") == "Premium":
                    out["existing_annual_premium"] = _num(d.get("existing_value"))
                    if out["recommended_annual_premium"] is None:
                        out["recommended_annual_premium"] = _num(d.get("new_value"))
    elif backend_tool == "purchase_retain_life_insurance_in_super":
        cna = body.get("coverage_needs_analysis") or {}
        low = _num(cna.get("total_need_low"))
        high = _num(cna.get("total_need_high"))
        if low is not None and high is not None:
            out["recommended_life_cover"] = (low + high) / 2.0
        rd = body.get("retirement_drag_estimate") or {}
        out["recommended_annual_premium"] = _num(rd.get("annual_premium")) if isinstance(rd, dict) else None
    elif backend_tool == "purchase_retain_income_protection_policy":
        aff = rec.get("affordability") or {}
        pc = rec.get("policy_comparison") or {}
        bn = rec.get("benefit_need") or {}
        out["recommended_ip_monthly_benefit"] = _num(bn.get("recommended_monthly_benefit"))
        out["existing_ip_monthly_benefit"] = _num(bn.get("existing_monthly_benefit"))
        if out["existing_ip_monthly_benefit"] is None and isinstance(pc, dict):
            out["existing_ip_monthly_benefit"] = _num(pc.get("existing_monthly_benefit"))
        out["recommended_annual_premium"] = _num(aff.get("annual_premium"))
        if isinstance(pc, dict):
            out["existing_annual_premium"] = _num(pc.get("existing_premium"))
            out["recommended_annual_premium"] = (
                out["recommended_annual_premium"] or _num(pc.get("proposed_premium"))
            )
    elif backend_tool == "purchase_retain_tpd_in_super":
        cna = body.get("coverage_needs_analysis") or raw.get("coverage_needs_analysis") or {}
        tpd_low = _num(cna.get("tpd_need_low"))
        tpd_high = _num(cna.get("tpd_need_high"))
        if tpd_low is not None and tpd_high is not None:
            out["recommended_tpd_cover"] = (tpd_low + tpd_high) / 2.0
        else:
            out["recommended_tpd_cover"] = _num(cna.get("shortfall_estimate"))
        out["existing_tpd_cover"] = _num(cna.get("existing_tpd_cover"))
        rd = (body.get("retirement_drag_estimate") or raw.get("retirement_drag_estimate") or {})
        out["recommended_annual_premium"] = _num(rd.get("annual_premium")) if isinstance(rd, dict) else None
    elif backend_tool == "tpd_policy_assessment":
        tpd_need = (body.get("tpd_need") or raw.get("tpd_need") or {})
        out["recommended_tpd_cover"] = _num(tpd_need.get("gap_aud") or tpd_need.get("net_shortfall_aud"))
        out["existing_tpd_cover"] = _num(tpd_need.get("existing_tpd_cover") or tpd_need.get("existing_cover"))
    return out


def _pick_primary_step(
    doc: dict[str, Any],
    *,
    preferred_index: int | None,
) -> tuple[dict[str, Any] | None, int | None, str | None]:
    rows = doc.get("structured_step_results") or []
    if preferred_index is not None and 0 <= preferred_index < len(rows):
        row = rows[preferred_index]
        if row.get("status") == "completed" and isinstance(row.get("output"), dict):
            return row, preferred_index, doc.get("id")
    for i, row in enumerate(rows):
        if row.get("status") != "completed":
            continue
        if not isinstance(row.get("output"), dict):
            continue
        orch = row.get("tool_id") or ""
        if _backend_tool_name(orch):
            return row, i, doc.get("id")
    return None, None, doc.get("id")


async def load_normalized_primary(
    db: AsyncIOMotorDatabase,
    client_id: str,
    *,
    analysis_output_id: str | None,
    step_index: int | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, int | None]:
    """
    Load the newest eligible saved analysis step and return (normalized, raw_row_meta, output_id, idx).
    """
    repo = ClientAnalysisOutputRepository(db)
    if analysis_output_id:
        doc = await repo.get(analysis_output_id, client_id)
        docs = [doc] if doc else []
    else:
        docs = await repo.list_for_client(client_id, limit=30)

    for doc in docs:
        if not doc:
            continue
        row, idx, oid = _pick_primary_step(doc, preferred_index=step_index)
        if not row or idx is None:
            continue
        raw = row.get("output") or {}
        orch = row.get("tool_id") or ""
        tool_name = _backend_tool_name(orch)
        if not tool_name:
            continue
        gen = raw.get("evaluated_at") if isinstance(raw, dict) else None
        if not gen:
            gen = _iso_from_doc(doc)
        tool_run_id = f"analysisoutput:{oid}:{idx}"
        norm = normalize_tool_output(
            tool_name,
            raw,
            tool_run_id=tool_run_id,
            client_id=client_id,
            generated_at=str(gen),
        )
        if not norm:
            continue
        extra = _extract_existing_recommended_from_raw(raw, tool_name)
        meta = {
            "analysis_output_id": oid,
            "step_index": idx,
            "tool_id": orch,
            "backend_tool_name": tool_name,
            "instruction": doc.get("instruction"),
            "extra_from_raw": extra,
        }
        return norm, meta, oid, idx
    return None, None, None, None


async def load_normalized_second(
    db: AsyncIOMotorDatabase,
    client_id: str,
    *,
    primary_output_id: str | None,
    primary_idx: int | None,
    second_analysis_output_id: str | None,
    second_step_index: int | None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Pick a second completed insurance step (different from primary when possible)."""
    repo = ClientAnalysisOutputRepository(db)

    def _normalize_row(doc: dict[str, Any], row: dict[str, Any], idx: int, oid: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        raw = row.get("output") or {}
        orch = row.get("tool_id") or ""
        tool_name = _backend_tool_name(orch)
        if not tool_name or not isinstance(raw, dict):
            return None, None
        gen = raw.get("evaluated_at") if isinstance(raw, dict) else None
        if not gen:
            gen = _iso_from_doc(doc)
        tool_run_id = f"analysisoutput:{oid}:{idx}"
        norm = normalize_tool_output(
            tool_name,
            raw,
            tool_run_id=tool_run_id,
            client_id=client_id,
            generated_at=str(gen),
        )
        if not norm:
            return None, None
        meta = {
            "analysis_output_id": oid,
            "step_index": idx,
            "tool_id": orch,
            "backend_tool_name": tool_name,
        }
        return norm, meta

    if second_analysis_output_id:
        doc = await repo.get(second_analysis_output_id, client_id)
        if not doc:
            return None, None
        row, idx, oid = _pick_primary_step(doc, preferred_index=second_step_index)
        if not row or idx is None:
            return None, None
        n, m = _normalize_row(doc, row, idx, oid or "")
        return (n, m) if n else (None, None)

    docs = await repo.list_for_client(client_id, limit=40)
    for doc in docs:
        oid = doc.get("id")
        rows = doc.get("structured_step_results") or []
        for i, row in enumerate(rows):
            if oid == primary_output_id and primary_idx is not None and i == primary_idx:
                continue
            if row.get("status") != "completed" or not isinstance(row.get("output"), dict):
                continue
            orch = row.get("tool_id") or ""
            if not _backend_tool_name(orch):
                continue
            n, m = _normalize_row(doc, row, i, oid or "")
            if n:
                return n, m
    return None, None


def merge_layers(
    *,
    from_analyses: dict[str, Any],
    memory_then_factfind: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """
    Merge scalar dashboard fields: analysis values win over memory/factfind for insurance metrics.
    """
    merged = dict(from_analyses)
    fin = memory_then_factfind.get("financial") or {}
    per = memory_then_factfind.get("personal") or {}
    ins = memory_then_factfind.get("insurance") or {}
    if merged.get("annual_gross_income") is None:
        merged["annual_gross_income"] = _num(fin.get("annual_gross_income"))
    if merged.get("client_age") is None:
        merged["client_age"] = _num(per.get("age"))
    if merged.get("dependants_count") is None:
        merged["dependants_count"] = _num(per.get("dependants"))
    if merged.get("mortgage_balance") is None:
        merged["mortgage_balance"] = _num(fin.get("mortgage_balance"))
    if merged.get("monthly_living_expense") is None:
        merged["monthly_living_expense"] = _num(fin.get("monthly_expenses"))
    if merged.get("existing_life_cover") is None:
        merged["existing_life_cover"] = _num(ins.get("life_sum_insured"))
    if merged.get("existing_tpd_cover") is None:
        merged["existing_tpd_cover"] = _num(ins.get("tpd_sum_insured"))
    if merged.get("existing_ip_monthly_benefit") is None:
        merged["existing_ip_monthly_benefit"] = _num(ins.get("ip_monthly_benefit"))
    if merged.get("existing_annual_premium") is None:
        merged["existing_annual_premium"] = _num(ins.get("annual_premium"))
    return merged


def analysis_metrics_from_normalized(
    norm: dict[str, Any],
    raw_extra: dict[str, float | None] | None,
) -> dict[str, Any]:
    cover = norm.get("cover") or {}
    prem = norm.get("premiums") or {}
    extra = raw_extra or {}
    rec_life = _num(cover.get("life"))
    ex_life = extra.get("existing_life_cover")
    rec_tpd = _num(cover.get("tpd"))
    ex_tpd = extra.get("existing_tpd_cover")
    rec_ip_m = _num(cover.get("incomeProtectionMonthly"))
    ex_ip_m = extra.get("existing_ip_monthly_benefit")
    rec_prem = _num(prem.get("annual"))
    ex_prem = extra.get("existing_annual_premium")
    if rec_life is None:
        rec_life = extra.get("recommended_life_cover")
    if rec_tpd is None:
        rec_tpd = extra.get("recommended_tpd_cover")
    if rec_ip_m is None:
        rec_ip_m = extra.get("recommended_ip_monthly_benefit")
    if rec_prem is None:
        rec_prem = extra.get("recommended_annual_premium")
    return {
        "recommended_life_cover": rec_life,
        "existing_life_cover": ex_life,
        "recommended_tpd_cover": rec_tpd,
        "existing_tpd_cover": ex_tpd,
        "recommended_ip_monthly_benefit": rec_ip_m,
        "existing_ip_monthly_benefit": ex_ip_m,
        "recommended_annual_premium": rec_prem,
        "existing_annual_premium": ex_prem,
    }


async def build_resolved_inputs(
    db: AsyncIOMotorDatabase,
    client_id: str,
    *,
    analysis_output_id: str | None,
    step_index: int | None,
    second_analysis_output_id: str | None,
    second_step_index: int | None,
    overrides: dict[str, Any],
) -> dict[str, Any]:
    """
    Full pipeline: saved analyses → memory → factfind → apply overrides.
    Returns a flat dict used by projection + spec builder.
    """
    norm, meta, out_id, idx = await load_normalized_primary(
        db, client_id, analysis_output_id=analysis_output_id, step_index=step_index
    )
    raw_extra = (meta or {}).get("extra_from_raw") if meta else None
    from_analyses: dict[str, Any] = {}
    if norm:
        m = analysis_metrics_from_normalized(norm, raw_extra)
        from_analyses.update(
            {
                "primary_normalized": norm,
                "primary_meta": meta,
                "recommended_life_cover": m["recommended_life_cover"],
                "existing_life_cover": m["existing_life_cover"],
                "recommended_tpd_cover": m["recommended_tpd_cover"],
                "existing_tpd_cover": m["existing_tpd_cover"],
                "recommended_ip_monthly_benefit": m["recommended_ip_monthly_benefit"],
                "existing_ip_monthly_benefit": m["existing_ip_monthly_benefit"],
                "recommended_annual_premium": m["recommended_annual_premium"],
                "existing_annual_premium": m["existing_annual_premium"],
            }
        )

    norm2, meta2 = await load_normalized_second(
        db,
        client_id,
        primary_output_id=out_id,
        primary_idx=idx,
        second_analysis_output_id=second_analysis_output_id,
        second_step_index=second_step_index,
    )
    if norm2:
        from_analyses["secondary_normalized"] = norm2
        from_analyses["secondary_meta"] = meta2

    ff = await _factfind_canonical(db, client_id)
    memory = await load_memory_canonical_hints(client_id)
    # Dashboard rule: factfind fills gaps after memory — use merge_memory_then_factfind
    # but product requires analyses first, then memory, then factfind.
    # So: start from factfind, merge memory first (memory wins over factfind for age/income),
    # matching build-tool-input: memory_then_factfind means memory overrides factfind.
    merged_canonical = merge_memory_then_factfind(memory, ff)

    merged = merge_layers(from_analyses=from_analyses, memory_then_factfind=merged_canonical)

    dash_map = {
        "dashboard.recommended_life_cover": "recommended_life_cover",
        "dashboard.existing_life_cover": "existing_life_cover",
        "dashboard.recommended_tpd_cover": "recommended_tpd_cover",
        "dashboard.existing_tpd_cover": "existing_tpd_cover",
        "dashboard.recommended_ip_monthly_benefit": "recommended_ip_monthly_benefit",
        "dashboard.existing_ip_monthly_benefit": "existing_ip_monthly_benefit",
        "dashboard.recommended_annual_premium": "recommended_annual_premium",
        "dashboard.existing_annual_premium": "existing_annual_premium",
        "dashboard.years_independence_horizon": "years_independence_horizon",
        "dashboard.projection_horizon": "projection_horizon",
        "dashboard.dependent_support_decay_years": "dependent_support_decay_years",
        "dashboard.income_support_years": "income_support_years",
        "dashboard.debt_payoff_years": "debt_payoff_years",
        "dashboard.premium_tolerance_ratio": "premium_tolerance_ratio",
    }
    int_dash_keys = frozenset(
        {
            "years_independence_horizon",
            "projection_horizon",
            "dependent_support_decay_years",
            "income_support_years",
            "debt_payoff_years",
        }
    )

    for k, v in overrides.items():
        if k in dash_map:
            key = dash_map[k]
            if key in int_dash_keys:
                merged[key] = int(_num(v) or 0) or None
            elif key == "premium_tolerance_ratio":
                merged[key] = _num(v)
            else:
                merged[key] = _num(v)
            continue
        if k.startswith("dashboard."):
            field = k.split(".", 1)[1]
            merged[field] = _num(v) if field not in ("notes",) else v
            continue
        if "." in k:
            parts = k.split(".", 1)
            if parts[0] == "personal" and parts[1] == "age":
                merged["client_age"] = _num(v) if v is not None else None
            elif parts[0] == "financial" and parts[1] == "annual_gross_income":
                merged["annual_gross_income"] = _num(v)
            elif parts[0] == "personal" and parts[1] == "dependants":
                merged["dependants_count"] = _num(v)
            elif parts[0] == "financial" and parts[1] == "mortgage_balance":
                merged["mortgage_balance"] = _num(v)
            elif parts[0] == "financial" and parts[1] == "monthly_expenses":
                merged["monthly_living_expense"] = _num(v)
            elif parts[0] == "insurance" and parts[1] == "life_sum_insured":
                merged["existing_life_cover"] = _num(v)
            elif parts[0] == "insurance" and parts[1] == "tpd_sum_insured":
                merged["existing_tpd_cover"] = _num(v)
            elif parts[0] == "insurance" and parts[1] == "ip_monthly_benefit":
                merged["existing_ip_monthly_benefit"] = _num(v)
            elif parts[0] == "insurance" and parts[1] == "annual_premium":
                merged["existing_annual_premium"] = _num(v)

    return merged


def detect_insurance_types_present(
    primary_normalized: dict[str, Any] | None,
    resolved: dict[str, Any],
) -> list[str]:
    """
    Ordered list of insurance kinds present in analysis or resolved numeric fields.
    Kinds: life, tpd, income_protection.
    """
    cov = (primary_normalized or {}).get("cover") if isinstance(primary_normalized, dict) else None
    if not isinstance(cov, dict):
        cov = {}
    kinds: list[str] = []

    def add(kind: str) -> None:
        if kind not in kinds:
            kinds.append(kind)

    if cov.get("life") is not None or resolved.get("recommended_life_cover") is not None:
        add("life")
    if cov.get("tpd") is not None or resolved.get("recommended_tpd_cover") is not None:
        add("tpd")
    if cov.get("incomeProtectionMonthly") is not None or resolved.get("recommended_ip_monthly_benefit") is not None:
        add("income_protection")

    order = ("life", "tpd", "income_protection")
    return [k for k in order if k in kinds]


def missing_fields_for_dashboard(
    dashboard_type: str,
    resolved: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return MissingFieldDef-shaped dicts for blocking gaps."""
    missing: list[dict[str, Any]] = []

    def add(canonical: str, label: str, input_type: str = "number") -> None:
        missing.append(
            {
                "path": canonical.replace(".", "_"),
                "canonical": canonical,
                "label": label,
                "input_type": input_type,
            }
        )

    has_primary = resolved.get("primary_normalized") is not None
    has_any_product = any(
        resolved.get(k) is not None
        for k in (
            "recommended_life_cover",
            "recommended_tpd_cover",
            "recommended_ip_monthly_benefit",
        )
    )
    if not has_primary and not has_any_product:
        add(
            "dashboard.recommended_life_cover",
            "At least one of: recommended life cover, TPD cover, or IP monthly benefit — required when no saved analysis is available",
        )

    if dashboard_type in (
        "premium_affordability",
        "protection_gap_time",
        "family_protection_outcome",
        "insurance_needs",
    ):
        if resolved.get("annual_gross_income") is None:
            add("financial.annual_gross_income", "Annual gross income (for affordability metrics)")

    if dashboard_type in ("protection_gap_time", "family_protection_outcome"):
        if resolved.get("dependants_count") is None:
            add("personal.dependants", "Number of financial dependants")
        deps = resolved.get("dependants_count")
        if deps is not None and float(deps) > 0 and resolved.get("years_independence_horizon") is None:
            add(
                "dashboard.years_independence_horizon",
                "Years until dependants are financially independent (used for the time profile)",
            )

    if dashboard_type == "family_protection_outcome":
        if resolved.get("mortgage_balance") is None:
            add("financial.mortgage_balance", "Mortgage / non-mortgage debt to clear (total)")
        if resolved.get("monthly_living_expense") is None and resolved.get("annual_gross_income") is None:
            add("financial.monthly_expenses", "Monthly living expenses (or provide annual income)")

    return missing


def flat_resolved_to_override_paths(flat: dict[str, Any]) -> dict[str, Any]:
    """Map stored flat resolved_inputs back into build_resolved_inputs override paths."""
    o: dict[str, Any] = {}
    if flat.get("annual_gross_income") is not None:
        o["financial.annual_gross_income"] = flat["annual_gross_income"]
    if flat.get("client_age") is not None:
        o["personal.age"] = flat["client_age"]
    if flat.get("dependants_count") is not None:
        o["personal.dependants"] = flat["dependants_count"]
    if flat.get("mortgage_balance") is not None:
        o["financial.mortgage_balance"] = flat["mortgage_balance"]
    if flat.get("monthly_living_expense") is not None:
        o["financial.monthly_expenses"] = flat["monthly_living_expense"]
    if flat.get("recommended_life_cover") is not None:
        o["dashboard.recommended_life_cover"] = flat["recommended_life_cover"]
    if flat.get("existing_life_cover") is not None:
        o["dashboard.existing_life_cover"] = flat["existing_life_cover"]
    if flat.get("recommended_tpd_cover") is not None:
        o["dashboard.recommended_tpd_cover"] = flat["recommended_tpd_cover"]
    if flat.get("existing_tpd_cover") is not None:
        o["dashboard.existing_tpd_cover"] = flat["existing_tpd_cover"]
    if flat.get("recommended_ip_monthly_benefit") is not None:
        o["dashboard.recommended_ip_monthly_benefit"] = flat["recommended_ip_monthly_benefit"]
    if flat.get("existing_ip_monthly_benefit") is not None:
        o["dashboard.existing_ip_monthly_benefit"] = flat["existing_ip_monthly_benefit"]
    if flat.get("recommended_annual_premium") is not None:
        o["dashboard.recommended_annual_premium"] = flat["recommended_annual_premium"]
    if flat.get("existing_annual_premium") is not None:
        o["dashboard.existing_annual_premium"] = flat["existing_annual_premium"]
    if flat.get("years_independence_horizon") is not None:
        o["dashboard.years_independence_horizon"] = flat["years_independence_horizon"]
    if flat.get("projection_horizon") is not None:
        o["dashboard.projection_horizon"] = flat["projection_horizon"]
    if flat.get("dependent_support_decay_years") is not None:
        o["dashboard.dependent_support_decay_years"] = flat["dependent_support_decay_years"]
    if flat.get("income_support_years") is not None:
        o["dashboard.income_support_years"] = flat["income_support_years"]
    if flat.get("debt_payoff_years") is not None:
        o["dashboard.debt_payoff_years"] = flat["debt_payoff_years"]
    if flat.get("premium_tolerance_ratio") is not None:
        o["dashboard.premium_tolerance_ratio"] = flat["premium_tolerance_ratio"]
    return o


def infer_dashboard_type(instruction: str | None, explicit: str | None) -> str:
    if explicit and explicit != "auto":
        return explicit
    text = (instruction or "").lower()
    if "compare" in text or "versus" in text or " vs " in text:
        return "strategy_comparison"
    if "afford" in text and "premium" in text:
        return "premium_affordability"
    if "gap" in text and ("time" in text or "over time" in text or "years" in text):
        return "protection_gap_time"
    if "family" in text and ("event" in text or "outcome" in text or "die" in text or "death" in text):
        return "family_protection_outcome"
    if "premium" in text and ("dashboard" in text or "chart" in text):
        return "premium_affordability"
    return "insurance_needs"
