"""
Deterministic insurance projection and comparison helpers.

No LLM math — only structured numeric outputs for dashboards.
"""

from __future__ import annotations

from typing import Any

ALLOWED_PROJECTION_HORIZONS: tuple[int, ...] = (10, 15, 20, 25)


def _nz(x: float | None) -> float:
    return float(x) if x is not None else 0.0


def normalize_projection_horizon(years: int | float | None) -> int:
    """Default 15 years; snap to nearest allowed 10/15/20/25."""
    if years is None:
        return 15
    try:
        y = int(round(float(years)))
    except (TypeError, ValueError):
        return 15
    if y in ALLOWED_PROJECTION_HORIZONS:
        return y
    return min(ALLOWED_PROJECTION_HORIZONS, key=lambda a: abs(a - y))


def build_yearly_insurance_projection(
    *,
    horizon_years: int,
    required_cover_year0: float,
    existing_cover: float | None,
    recommended_cover: float | None,
    mortgage_balance: float | None = None,
    debt_payoff_years: int | None = None,
    dependent_support_decay_years: int | None = None,
    income_support_years: int | None = None,
    dependants_count: float | None = None,
    annual_income: float | None = None,
    monthly_living_expense: float | None = None,
    premium_annual_existing: float | None = None,
    premium_annual_recommended: float | None = None,
    premium_tolerance_ratio: float | None = None,
) -> dict[str, Any]:
    """
    Year 0 .. H inclusive rows with deterministic decay models.

    When optional inputs are missing, assumptions are recorded and simple splits apply.
    """
    H = max(1, int(horizon_years))
    R0 = max(0.0, float(required_cover_year0))
    ex = float(existing_cover) if existing_cover is not None else None
    rec = float(recommended_cover) if recommended_cover is not None else None

    assumptions: list[str] = []

    # --- Debt trajectory ---
    debt0 = _nz(mortgage_balance) if mortgage_balance is not None else 0.0
    t_debt = int(debt_payoff_years) if debt_payoff_years is not None and debt_payoff_years > 0 else None
    if debt0 > 0 and t_debt is None:
        t_debt = H
        assumptions.append(f"Debt payoff period not provided — amortised linearly over projection horizon ({H} years).")

    # --- Dependent vs income need split (sum to R0 at year 0) ---
    t_dep = int(dependent_support_decay_years) if dependent_support_decay_years and dependent_support_decay_years > 0 else None
    if t_dep is None:
        t_dep = H
        assumptions.append("Dependent support duration not provided — need tapers to zero over the full horizon.")

    t_inc = int(income_support_years) if income_support_years and income_support_years > 0 else None
    if t_inc is None:
        t_inc = H
        assumptions.append("Income support horizon not provided — income replacement need tapers over the full horizon.")

    if R0 <= 0:
        dep0, inc0 = 0.0, 0.0
        assumptions.append("Required cover at year 0 is zero — projection rows are zero.")
    elif dependants_count is not None and float(dependants_count) <= 0:
        dep0 = 0.0
        inc0 = R0
        assumptions.append("No dependants — treating full need as income/living expense support (no dependent-specific decay).")
    else:
        dep0 = 0.45 * R0
        inc0 = R0 - dep0
        assumptions.append("Split need 45% dependent support / 55% income support (illustrative — override via controls when available).")

    tol = premium_tolerance_ratio if premium_tolerance_ratio is not None else 0.08

    rows: list[dict[str, Any]] = []
    for y in range(H + 1):
        dep_need = dep0 * max(0.0, 1.0 - (y / float(t_dep))) if t_dep > 0 else 0.0
        inc_need = inc0 * max(0.0, 1.0 - (y / float(t_inc))) if t_inc > 0 else 0.0
        req = max(0.0, dep_need + inc_need)

        if debt0 > 0 and t_debt and t_debt > 0:
            o_debt = debt0 * max(0.0, 1.0 - (y / float(t_debt)))
        elif debt0 > 0:
            o_debt = debt0
        else:
            o_debt = None

        ex_c = ex if ex is not None else None
        # Recommended sum insured held constant (advised level); default to initial need if missing
        rec_c = rec if rec is not None else R0

        sf_ex = max(0.0, req - _nz(ex_c)) if ex_c is not None else None
        sf_rec = max(0.0, req - rec_c)

        ad_ex = (ex_c / req) if ex_c is not None and req > 0 else None
        ad_rec = (rec_c / req) if req > 0 else None

        row: dict[str, Any] = {
            "year": y,
            "requiredCover": round(req, 2),
            "existingCover": round(ex_c, 2) if ex_c is not None else None,
            "recommendedCover": round(rec_c, 2),
            "shortfallExisting": round(sf_ex, 2) if sf_ex is not None else None,
            "shortfallRecommended": round(sf_rec, 2),
            "adequacyRatioExisting": round(ad_ex, 4) if ad_ex is not None else None,
            "adequacyRatioRecommended": round(ad_rec, 4) if ad_rec is not None else None,
            "outstandingDebt": round(o_debt, 2) if o_debt is not None else None,
            "dependentSupportNeed": round(dep_need, 2),
            "incomeSupportNeed": round(inc_need, 2),
            "premiumAnnualExisting": round(premium_annual_existing, 2) if premium_annual_existing is not None else None,
            "premiumAnnualRecommended": round(premium_annual_recommended, 2)
            if premium_annual_recommended is not None
            else None,
        }

        if annual_income and annual_income > 0:
            if premium_annual_existing is not None:
                row["premiumAffordabilityRatioExisting"] = round(premium_annual_existing / annual_income, 4)
            else:
                row["premiumAffordabilityRatioExisting"] = None
            if premium_annual_recommended is not None:
                row["premiumAffordabilityRatioRecommended"] = round(premium_annual_recommended / annual_income, 4)
            else:
                row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = (
                row.get("premiumAffordabilityRatioExisting") is not None
                and row["premiumAffordabilityRatioExisting"] <= tol
            )
            row["premiumAffordabilityVsToleranceRecommended"] = (
                row.get("premiumAffordabilityRatioRecommended") is not None
                and row["premiumAffordabilityRatioRecommended"] <= tol
            )
        else:
            row["premiumAffordabilityRatioExisting"] = None
            row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = None
            row["premiumAffordabilityVsToleranceRecommended"] = None

        rows.append(row)

    if monthly_living_expense is None and annual_income:
        assumptions.append("Monthly expenses not provided — premium affordability uses income only.")

    return {
        "horizonYears": H,
        "yearlySeries": rows,
        "projectionAssumptions": assumptions,
        "premiumToleranceRatio": tol,
        "allowedHorizons": list(ALLOWED_PROJECTION_HORIZONS),
    }


def build_yearly_tpd_projection(
    *,
    horizon_years: int,
    lump_sum_need_year0: float,
    existing_tpd_cover: float | None,
    recommended_tpd_cover: float | None,
    annual_income: float | None,
    income_support_years: int | None = None,
    premium_annual_existing: float | None = None,
    premium_annual_recommended: float | None = None,
    premium_tolerance_ratio: float | None = None,
) -> dict[str, Any]:
    """
    TPD lump-sum need (flat) plus illustrative income-replacement need decay.
    Functional outcome: years of pre-disability income represented by lump sums.
    """
    H = max(1, int(horizon_years))
    R0 = max(0.0, float(lump_sum_need_year0))
    ex = float(existing_tpd_cover) if existing_tpd_cover is not None else None
    rec = float(recommended_tpd_cover) if recommended_tpd_cover is not None else None
    rec_c = rec if rec is not None else R0
    ai = _nz(annual_income) if annual_income is not None else 0.0


    t_inc = int(income_support_years) if income_support_years and income_support_years > 0 else None
    if t_inc is None:
        t_inc = H
    assumptions: list[str] = [
        "TPD lump-sum need held constant at the advised net TPD need (illustrative).",
        "Income replacement need (annual $) tapers linearly — override income support years when available.",
    ]

    tol = premium_tolerance_ratio if premium_tolerance_ratio is not None else 0.08

    rows: list[dict[str, Any]] = []
    for y in range(H + 1):
        inc_repl = 0.0
        if ai > 0:
            inc_repl = ai * 0.65 * max(0.0, 1.0 - (y / float(t_inc))) if t_inc > 0 else 0.0
        lump_sum_need = lump = R0
        required_cover = lump_sum_need

        ex_c = ex
        sf_ex = max(0.0, required_cover - _nz(ex_c)) if ex_c is not None else None
        sf_rec = max(0.0, required_cover - rec_c)

        ad_ex = (ex_c / required_cover) if ex_c is not None and required_cover > 0 else None
        ad_rec = (rec_c / required_cover) if required_cover > 0 else None

        y_ie = (_nz(ex_c) / ai) if ai > 0 and ex_c is not None else None
        y_ir = (rec_c / ai) if ai > 0 else None

        row: dict[str, Any] = {
            "year": y,
            "requiredCover": round(required_cover, 2),
            "existingCover": round(ex_c, 2) if ex_c is not None else None,
            "recommendedCover": round(rec_c, 2),
            "shortfallExisting": round(sf_ex, 2) if sf_ex is not None else None,
            "shortfallRecommended": round(sf_rec, 2),
            "adequacyRatioExisting": round(ad_ex, 4) if ad_ex is not None else None,
            "adequacyRatioRecommended": round(ad_rec, 4) if ad_rec is not None else None,
            "incomeReplacementNeed": round(inc_repl, 2),
            "lumpSumNeed": round(lump_sum_need, 2),
            "yearsOfIncomeCoveredExisting": round(y_ie, 3) if y_ie is not None else None,
            "yearsOfIncomeCoveredRecommended": round(y_ir, 3) if y_ir is not None else None,
            "functionalOutcomeYears": round(y_ir, 3) if y_ir is not None else None,
            "premiumAnnualExisting": round(premium_annual_existing, 2) if premium_annual_existing is not None else None,
            "premiumAnnualRecommended": round(premium_annual_recommended, 2)
            if premium_annual_recommended is not None
            else None,
        }

        if ai > 0:
            if premium_annual_existing is not None:
                row["premiumAffordabilityRatioExisting"] = round(premium_annual_existing / ai, 4)
            else:
                row["premiumAffordabilityRatioExisting"] = None
            if premium_annual_recommended is not None:
                row["premiumAffordabilityRatioRecommended"] = round(premium_annual_recommended / ai, 4)
            else:
                row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = (
                row.get("premiumAffordabilityRatioExisting") is not None
                and row["premiumAffordabilityRatioExisting"] <= tol
            )
            row["premiumAffordabilityVsToleranceRecommended"] = (
                row.get("premiumAffordabilityRatioRecommended") is not None
                and row["premiumAffordabilityRatioRecommended"] <= tol
            )
        else:
            row["premiumAffordabilityRatioExisting"] = None
            row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = None
            row["premiumAffordabilityVsToleranceRecommended"] = None

        rows.append(row)

    if annual_income is None or ai <= 0:
        assumptions.append("Annual income not available — years-of-income equivalents omitted.")

    return {
        "horizonYears": H,
        "yearlySeries": rows,
        "projectionAssumptions": assumptions,
        "premiumToleranceRatio": tol,
        "allowedHorizons": list(ALLOWED_PROJECTION_HORIZONS),
    }


def build_yearly_ip_projection(
    *,
    horizon_years: int,
    monthly_benefit_need_year0: float,
    existing_monthly_benefit: float | None,
    recommended_monthly_benefit: float | None,
    annual_income: float | None,
    income_support_years: int | None = None,
    premium_annual_existing: float | None = None,
    premium_annual_recommended: float | None = None,
    premium_tolerance_ratio: float | None = None,
) -> dict[str, Any]:
    """
    Income protection: annual benefit need (monthly × 12) with taper; adequacy vs existing/recommended.
    """
    H = max(1, int(horizon_years))
    m0 = max(0.0, float(monthly_benefit_need_year0))
    need0_annual = m0 * 12.0
    ex_m = float(existing_monthly_benefit) if existing_monthly_benefit is not None else None
    rec_m = float(recommended_monthly_benefit) if recommended_monthly_benefit is not None else None
    ex_a = ex_m * 12.0 if ex_m is not None else None
    rec_a = rec_m * 12.0 if rec_m is not None else None
    rec_a = rec_a if rec_a is not None else need0_annual

    t_inc = int(income_support_years) if income_support_years and income_support_years > 0 else None
    if t_inc is None:
        t_inc = H
    assumptions: list[str] = [
        "IP annual benefit need tapers from the initial monthly benefit × 12 (illustrative pre-retirement horizon).",
    ]
    tol = premium_tolerance_ratio if premium_tolerance_ratio is not None else 0.08
    ai = _nz(annual_income) if annual_income is not None else 0.0

    rows: list[dict[str, Any]] = []
    for y in range(H + 1):
        factor = max(0.0, 1.0 - (y / float(t_inc))) if t_inc > 0 else 0.0
        req_annual = need0_annual * factor

        sf_ex = max(0.0, req_annual - _nz(ex_a)) if ex_a is not None else None
        sf_rec = max(0.0, req_annual - _nz(rec_a))

        ad_ex = (ex_a / req_annual) if ex_a is not None and req_annual > 0 else None
        ad_rec = (rec_a / req_annual) if rec_a is not None and req_annual > 0 else None

        row: dict[str, Any] = {
            "year": y,
            "requiredCover": round(req_annual, 2),
            "existingCover": round(ex_a, 2) if ex_a is not None else None,
            "recommendedCover": round(rec_a, 2),
            "shortfallExisting": round(sf_ex, 2) if sf_ex is not None else None,
            "shortfallRecommended": round(sf_rec, 2),
            "adequacyRatioExisting": round(ad_ex, 4) if ad_ex is not None else None,
            "adequacyRatioRecommended": round(ad_rec, 4) if ad_rec is not None else None,
            "monthlyBenefitNeed": round(m0 * factor, 2),
            "premiumAnnualExisting": round(premium_annual_existing, 2) if premium_annual_existing is not None else None,
            "premiumAnnualRecommended": round(premium_annual_recommended, 2)
            if premium_annual_recommended is not None
            else None,
        }

        if ai > 0:
            if premium_annual_existing is not None:
                row["premiumAffordabilityRatioExisting"] = round(premium_annual_existing / ai, 4)
            else:
                row["premiumAffordabilityRatioExisting"] = None
            if premium_annual_recommended is not None:
                row["premiumAffordabilityRatioRecommended"] = round(premium_annual_recommended / ai, 4)
            else:
                row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = (
                row.get("premiumAffordabilityRatioExisting") is not None
                and row["premiumAffordabilityRatioExisting"] <= tol
            )
            row["premiumAffordabilityVsToleranceRecommended"] = (
                row.get("premiumAffordabilityRatioRecommended") is not None
                and row["premiumAffordabilityRatioRecommended"] <= tol
            )
        else:
            row["premiumAffordabilityRatioExisting"] = None
            row["premiumAffordabilityRatioRecommended"] = None
            row["premiumAffordabilityVsToleranceExisting"] = None
            row["premiumAffordabilityVsToleranceRecommended"] = None

        rows.append(row)

    return {
        "horizonYears": H,
        "yearlySeries": rows,
        "projectionAssumptions": assumptions,
        "premiumToleranceRatio": tol,
        "allowedHorizons": list(ALLOWED_PROJECTION_HORIZONS),
    }


def calculate_cover_adequacy(
    *,
    existing_cover: float | None,
    recommended_cover: float | None,
) -> dict[str, Any]:
    """Cover gap / surplus vs a recommended amount."""
    ex = existing_cover
    rec = recommended_cover
    if rec is None or rec <= 0:
        return {
            "existingCover": ex,
            "recommendedCover": rec,
            "shortfall": None,
            "surplus": None,
            "adequacyRatio": None,
            "status": "unknown",
        }
    if ex is None:
        shortfall = rec
        return {
            "existingCover": None,
            "recommendedCover": rec,
            "shortfall": shortfall,
            "surplus": None,
            "adequacyRatio": 0.0,
            "status": "shortfall",
        }
    gap = rec - ex
    ratio = ex / rec if rec else None
    if gap > 0:
        status = "shortfall"
    elif gap < 0:
        status = "surplus"
    else:
        status = "aligned"
    return {
        "existingCover": ex,
        "recommendedCover": rec,
        "shortfall": gap if gap > 0 else 0.0,
        "surplus": -gap if gap < 0 else 0.0,
        "adequacyRatio": ratio,
        "status": status,
    }


def calculate_premium_impact(
    *,
    current_annual_premium: float | None,
    recommended_annual_premium: float | None,
) -> dict[str, Any]:
    """Annual and monthly delta between two premium points."""
    cur = current_annual_premium
    rec = recommended_annual_premium
    if cur is None and rec is None:
        return {
            "currentAnnual": None,
            "recommendedAnnual": None,
            "deltaAnnual": None,
            "deltaMonthly": None,
        }
    delta = None
    if cur is not None and rec is not None:
        delta = rec - cur
    return {
        "currentAnnual": cur,
        "recommendedAnnual": rec,
        "deltaAnnual": delta,
        "deltaMonthly": (delta / 12.0) if delta is not None else None,
    }


def calculate_protection_gap_over_time(
    *,
    required_cover_year0: float,
    existing_cover: float,
    horizon_years: int,
    dependency_decay: bool = True,
) -> dict[str, Any]:
    """
    Year-by-year required cover vs existing.

    If dependency_decay is True, model required cover as linearly declining from
    year0 to zero at horizon (dependants becoming independent). Otherwise flat need.
    """
    h = max(1, int(horizon_years))
    series: list[dict[str, Any]] = []
    for year in range(h + 1):
        if dependency_decay:
            need = required_cover_year0 * (1.0 - year / float(h)) if h else required_cover_year0
        else:
            need = required_cover_year0
        need = max(0.0, need)
        shortfall = max(0.0, need - existing_cover)
        series.append(
            {
                "year": year,
                "requiredCover": round(need, 2),
                "existingCover": round(existing_cover, 2),
                "shortfall": round(shortfall, 2),
            }
        )
    milestones = [
        {"label": "Start", "year": 0},
        {"label": "Independence horizon", "year": h},
    ]
    return {
        "horizonYears": h,
        "dependencyDecay": dependency_decay,
        "series": series,
        "milestones": milestones,
    }


def calculate_family_protection_outcome(
    *,
    life_cover: float | None,
    total_debts: float | None,
    annual_income: float | None,
    monthly_living_expense: float | None,
) -> dict[str, Any]:
    """
    Simplified insured-event outcome: debts cleared, income support years from residual.
    Uses annual income / 12 vs monthly expense when expense missing.
    """
    cover = _nz(life_cover)
    debts = _nz(total_debts)
    income = _nz(annual_income)
    expense = monthly_living_expense
    if expense is None and income > 0:
        expense = income / 12.0 * 0.6
    exp = _nz(expense)
    residual_after_debts = max(0.0, cover - debts)
    annual_exp = exp * 12.0
    years_income_supported = (residual_after_debts / annual_exp) if annual_exp > 0 else None
    shortfall_vs_expense = max(0.0, annual_exp - residual_after_debts) if annual_exp > 0 else None
    stress = "low"
    if shortfall_vs_expense and annual_exp > 0 and shortfall_vs_expense / annual_exp > 0.25:
        stress = "medium"
    if shortfall_vs_expense and annual_exp > 0 and shortfall_vs_expense / annual_exp > 0.5:
        stress = "high"
    return {
        "lifeCoverAvailable": cover,
        "debtsAssumed": debts,
        "debtsCovered": min(cover, debts),
        "residualAfterDebts": residual_after_debts,
        "annualLivingExpenseAssumed": annual_exp,
        "yearsOfIncomeSupportFunded": years_income_supported,
        "firstYearShortfall": shortfall_vs_expense,
        "financialStressRisk": stress,
    }


def compare_insurance_strategies(
    *,
    label_a: str,
    norm_a: dict[str, Any],
    label_b: str,
    norm_b: dict[str, Any],
) -> dict[str, Any]:
    """Side-by-side comparison of two normalized tool outputs."""
    ca = (norm_a.get("cover") or {}) if isinstance(norm_a.get("cover"), dict) else {}
    cb = (norm_b.get("cover") or {}) if isinstance(norm_b.get("cover"), dict) else {}
    pa = (norm_a.get("premiums") or {}) if isinstance(norm_a.get("premiums"), dict) else {}
    pb = (norm_b.get("premiums") or {}) if isinstance(norm_b.get("premiums"), dict) else {}
    sa = (norm_a.get("suitability") or {}) if isinstance(norm_a.get("suitability"), dict) else {}
    sb = (norm_b.get("suitability") or {}) if isinstance(norm_b.get("suitability"), dict) else {}

    def row(metric: str, va: Any, vb: Any) -> dict[str, Any]:
        return {"metric": metric, "A": va, "B": vb}

    rows = [
        row("Life cover", ca.get("life"), cb.get("life")),
        row("TPD cover", ca.get("tpd"), cb.get("tpd")),
        row("IP monthly benefit", ca.get("incomeProtectionMonthly"), cb.get("incomeProtectionMonthly")),
        row("Annual premium", pa.get("annual"), pb.get("annual")),
        row("Affordability score", sa.get("affordabilityScore"), sb.get("affordabilityScore")),
        row("Adequacy score", sa.get("adequacyScore"), sb.get("adequacyScore")),
    ]
    return {
        "labelA": label_a,
        "labelB": label_b,
        "rows": rows,
        "toolNameA": norm_a.get("toolName"),
        "toolNameB": norm_b.get("toolName"),
    }


def compute_affordability_flag(
    *,
    annual_premium: float | None,
    annual_income: float | None,
    threshold: float = 0.08,
) -> dict[str, Any]:
    """Premium as ratio of gross income vs threshold (default 8%)."""
    if annual_premium is None or annual_income is None or annual_income <= 0:
        return {
            "ratio": None,
            "threshold": threshold,
            "affordable": None,
            "status": "unknown",
        }
    ratio = annual_premium / annual_income
    affordable = ratio <= threshold
    return {
        "ratio": round(ratio, 4),
        "threshold": threshold,
        "affordable": affordable,
        "status": "affordable" if affordable else "stretched",
    }
