from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from typing import Any

import duckdb
import pandas as pd

from .config import PipelineConfig


logger = logging.getLogger(__name__)

SUPPORTED_DAYS_SUPPLY = (30, 60, 90)
FULL_LIS_GENERIC_COPAY = 4.90
FULL_LIS_BRAND_COPAY = 12.15
PARTIAL_LIS_DISCOUNT_FACTOR = 0.75
PARTIAL_LIS_GENERIC_CAP = 12.00
PARTIAL_LIS_BRAND_CAP = 35.00
ANNUAL_OOP_CAP = 2000.00
NETWORK_PRIORITY = {
    "adequate": 0,
    "limited_preferred_retail": 1,
    "no_preferred_retail": 2,
}
FEATURE_VERSION = "research_v2"
FOCUS_WEIGHTS = {
    "balanced": {
        "cost": 0.28,
        "premium": 0.12,
        "coverage": 0.25,
        "access": 0.15,
        "stability": 0.20,
    },
    "lowest_total_cost": {
        "cost": 0.50,
        "premium": 0.10,
        "coverage": 0.18,
        "access": 0.10,
        "stability": 0.12,
    },
    "lowest_monthly_premium": {
        "cost": 0.18,
        "premium": 0.42,
        "coverage": 0.20,
        "access": 0.05,
        "stability": 0.15,
    },
    "coverage_first": {
        "cost": 0.18,
        "premium": 0.05,
        "coverage": 0.42,
        "access": 0.10,
        "stability": 0.25,
    },
    "pharmacy_access": {
        "cost": 0.15,
        "premium": 0.05,
        "coverage": 0.25,
        "access": 0.40,
        "stability": 0.15,
    },
    "low_friction": {
        "cost": 0.10,
        "premium": 0.10,
        "coverage": 0.25,
        "access": 0.20,
        "stability": 0.35,
    },
}
ROLE_WEIGHT_ADJUSTMENTS = {
    "beneficiary": {
        "cost": 0.0,
        "premium": 0.0,
        "coverage": 0.0,
        "access": 0.0,
        "stability": 0.0,
    },
    "caregiver": {
        "cost": -0.04,
        "premium": -0.03,
        "coverage": 0.02,
        "access": 0.03,
        "stability": 0.05,
    },
    "counselor": {
        "cost": -0.06,
        "premium": -0.04,
        "coverage": 0.05,
        "access": 0.02,
        "stability": 0.03,
    },
}
NETWORK_ACCESS_BASE = {
    "adequate": 100.0,
    "limited_preferred_retail": 76.0,
    "no_preferred_retail": 52.0,
}
CHANNEL_LABELS = {
    "pref_retail": "preferred retail",
    "nonpref_retail": "non-preferred retail",
    "pref_mail": "preferred mail",
    "nonpref_mail": "non-preferred mail",
    "unavailable": "unavailable",
}
DECISION_FOCUS_LABELS = {
    "balanced": "balanced fit",
    "lowest_total_cost": "lowest total cost",
    "lowest_monthly_premium": "lowest monthly premium",
    "coverage_first": "coverage protection",
    "pharmacy_access": "pharmacy access",
    "low_friction": "lower-friction use",
}


@dataclass(slots=True)
class BeneficiaryInput:
    zipcode: str
    age_band: str = "65-74"
    lis_status: str = "none"
    chronic_condition_flags: list[str] | None = None
    pharmacy_preference: str = "auto"
    top_n: int = 5
    user_role: str = "beneficiary"
    decision_focus: str = "balanced"


@dataclass(slots=True)
class MedicationInput:
    drug_name: str | None = None
    rxcui: str | None = None
    ndc: str | None = None
    tier_family: str | None = None
    day_supply: int = 30
    quantity_override: float | None = None
    fills_per_year_override: int | None = None


@dataclass(slots=True)
class MedicationMatch:
    medication_id: str
    requested_value: str
    requested_drug_name: str | None
    resolved_drug_name: str
    rxcui: str
    ndc: str
    match_source: str
    match_confidence: str
    normalized_day_supply: int
    tier_family: str


@dataclass(slots=True)
class ExplanationItem:
    code: str
    message: str
    related_drug: str | None = None
    related_channel: str | None = None
    coverage_phase: str | None = None
    severity: str = "info"


@dataclass(slots=True)
class PlanExplanationGroups:
    coverage_issues: list[str]
    utilization_management_issues: list[str]
    insulin_considerations: list[str]
    pharmacy_access_issues: list[str]
    deductible_issues: list[str]
    cost_logic_issues: list[str]


@dataclass(slots=True)
class PlanExplanationDetailGroups:
    coverage_issues: list[ExplanationItem]
    utilization_management_issues: list[ExplanationItem]
    insulin_considerations: list[ExplanationItem]
    pharmacy_access_issues: list[ExplanationItem]
    deductible_issues: list[ExplanationItem]
    cost_logic_issues: list[ExplanationItem]


@dataclass(slots=True)
class DrugFillTrace:
    fill_number: int
    day_offset: int
    selected_channel: str
    coverage_phase: str
    pricing_status: str
    negotiated_price: float
    deductible_before: float
    deductible_applied: float
    deductible_after: float
    base_oop: float
    initial_coverage_oop: float
    lis_adjusted_oop: float
    final_oop: float
    oop_before: float
    oop_after: float
    oop_cap_applied: bool


@dataclass(slots=True)
class FillCostResult:
    total_oop: float
    base_oop: float
    lis_adjusted_oop: float
    deductible_exposure: float
    initial_coverage_oop: float
    negotiated_price: float
    coverage_phase: str
    pricing_status: str
    deductible_before: float
    deductible_after: float
    oop_before: float
    oop_after: float
    oop_cap_applied: bool


@dataclass(slots=True)
class PlanFitMetrics:
    cost_score: float
    premium_score: float
    coverage_score: float
    access_score: float
    stability_score: float


@dataclass(slots=True)
class PlanDrugBreakdown:
    medication_id: str
    plan_key: str
    requested_drug_name: str | None
    drug_name: str
    tier: int | None
    requested_day_supply: int
    selected_channel: str
    per_fill_oop: float | None
    annual_oop: float | None
    deductible_exposure: float
    initial_coverage_oop: float
    lis_adjusted_oop: float
    negotiated_price_total: float
    oop_cap_savings: float
    pa_flag: bool
    st_flag: bool
    ql_flag: bool
    insulin_flag: bool
    coverage_gap_flag: bool
    coverage_status: str
    pricing_status: str
    coverage_phases: list[str]
    match_source: str
    match_confidence: str
    explanations: list[str]
    fill_traces: list[DrugFillTrace]


@dataclass(slots=True)
class PlanRecommendation:
    plan_key: str
    plan_name: str
    annual_drug_oop: float
    estimated_annual_oop: float
    annual_premium: float
    annual_total_cost: float
    monthly_cost_estimate: float
    coverage_status: str
    best_channel_mix: str
    network_flag: str
    network_access_summary: str
    insulin_flag: bool
    restriction_summary: str
    explanations: list[str]
    explanation_groups: PlanExplanationGroups
    explanation_detail_groups: PlanExplanationDetailGroups
    resolved_medications: list[MedicationMatch]
    plan_rank: int
    uncovered_drug_count: int
    restriction_count: int
    ranking_source: str
    model_score: float | None
    model_confidence_bucket: str | None
    rules_score: float
    fit_score: float
    fit_label: str
    fit_summary: str
    fit_metrics: PlanFitMetrics
    key_strengths: list[str]
    key_watchouts: list[str]
    mail_order_dependency_count: int
    channel_diversity_count: int
    nearest_preferred_distance_miles: float | None
    service_area_eligible: bool
    comparison_only: bool
    feature_version: str
    drug_breakdowns: list[PlanDrugBreakdown]


def _normalize_days_supply(day_supply: int) -> int:
    if day_supply in SUPPORTED_DAYS_SUPPLY:
        return day_supply
    if day_supply >= 75:
        return 90
    if day_supply >= 45:
        return 60
    return 30


def _normalize_zipcode(zipcode: str) -> str:
    return zipcode.strip().zfill(5)


def _connect(config: PipelineConfig | None) -> duckdb.DuckDBPyConnection:
    active_config = config or PipelineConfig()
    return duckdb.connect(str(active_config.db_path), read_only=True)


def _fetch_dataframe(
    conn: duckdb.DuckDBPyConnection, query: str, params: list[Any] | None = None
) -> pd.DataFrame:
    if params:
        return conn.execute(query, params).fetch_df()
    return conn.execute(query).fetch_df()


def _append_unique(target: list[str], message: str) -> None:
    if message and message not in target:
        target.append(message)


def _append_explanation(
    target_strings: list[str],
    target_details: list[ExplanationItem],
    code: str,
    message: str,
    *,
    related_drug: str | None = None,
    related_channel: str | None = None,
    coverage_phase: str | None = None,
    severity: str = "info",
) -> None:
    _append_unique(target_strings, message)
    if any(
        item.code == code
        and item.message == message
        and item.related_drug == related_drug
        and item.related_channel == related_channel
        and item.coverage_phase == coverage_phase
        for item in target_details
    ):
        return
    target_details.append(
        ExplanationItem(
            code=code,
            message=message,
            related_drug=related_drug,
            related_channel=related_channel,
            coverage_phase=coverage_phase,
            severity=severity,
        )
    )


def _flatten_explanation_groups(groups: PlanExplanationGroups) -> list[str]:
    return (
        groups.coverage_issues
        + groups.utilization_management_issues
        + groups.insulin_considerations
        + groups.pharmacy_access_issues
        + groups.deductible_issues
        + groups.cost_logic_issues
    )


def _truncate_group_strings(values: list[str], limit: int = 5) -> list[str]:
    return values[:limit]


def _truncate_group_details(values: list[ExplanationItem], limit: int = 5) -> list[ExplanationItem]:
    return values[:limit]


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _relative_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 100.0
    return _clamp(100.0 * (high - value) / (high - low))


def _normalize_decision_focus(decision_focus: str) -> str:
    normalized = decision_focus.strip().lower()
    return normalized if normalized in FOCUS_WEIGHTS else "balanced"


def _normalize_user_role(user_role: str) -> str:
    normalized = user_role.strip().lower()
    return normalized if normalized in ROLE_WEIGHT_ADJUSTMENTS else "beneficiary"


def _resolve_fit_weights(beneficiary: BeneficiaryInput) -> dict[str, float]:
    focus = _normalize_decision_focus(beneficiary.decision_focus)
    role = _normalize_user_role(beneficiary.user_role)
    combined = {
        component: FOCUS_WEIGHTS[focus][component] + ROLE_WEIGHT_ADJUSTMENTS[role][component]
        for component in FOCUS_WEIGHTS[focus]
    }
    total = sum(max(weight, 0.0) for weight in combined.values())
    if total <= 0:
        return FOCUS_WEIGHTS["balanced"].copy()
    return {
        component: max(weight, 0.0) / total
        for component, weight in combined.items()
    }


def _fit_label(score: float) -> str:
    if score >= 85:
        return "strong fit"
    if score >= 70:
        return "good fit"
    if score >= 55:
        return "mixed fit"
    return "higher tradeoff"


def _network_access_summary(network_flag: str, distance_miles: float | None) -> str:
    if network_flag == "no_preferred_retail":
        return "No preferred retail pharmacy access was identified."
    if network_flag == "limited_preferred_retail":
        if distance_miles is None:
            return "Preferred retail access is limited."
        return f"Preferred retail access is limited; nearest preferred estimate is {distance_miles:.1f} miles."
    if distance_miles is None:
        return "Preferred retail access appears adequate."
    return f"Preferred retail access appears adequate; nearest preferred estimate is {distance_miles:.1f} miles."


def _distance_penalty(distance_miles: float | None) -> float:
    if distance_miles is None:
        return 0.0
    if distance_miles <= 5:
        return 0.0
    if distance_miles <= 15:
        return 8.0
    if distance_miles <= 30:
        return 18.0
    return 28.0


def _preferred_channel_penalty(
    pharmacy_preference: str,
    mail_order_dependency_count: int,
    retail_dependency_count: int,
    requested_drug_count: int,
) -> float:
    if requested_drug_count <= 0 or pharmacy_preference == "auto":
        return 0.0
    dependency_share = (
        mail_order_dependency_count / requested_drug_count
        if pharmacy_preference == "retail"
        else retail_dependency_count / requested_drug_count
    )
    return dependency_share * 20.0


def _deductible_pressure_penalty(deductible_exposure_total: float, annual_total_cost: float) -> float:
    if annual_total_cost <= 0:
        return 0.0
    return _clamp((deductible_exposure_total / annual_total_cost) * 35.0, upper=35.0)


def _top_component_names(metrics: PlanFitMetrics, weights: dict[str, float]) -> list[str]:
    component_pairs = {
        "cost": metrics.cost_score * weights["cost"],
        "premium": metrics.premium_score * weights["premium"],
        "coverage": metrics.coverage_score * weights["coverage"],
        "access": metrics.access_score * weights["access"],
        "stability": metrics.stability_score * weights["stability"],
    }
    ordered = sorted(component_pairs.items(), key=lambda item: item[1], reverse=True)
    return [name for name, weighted_value in ordered if weighted_value > 0][:2]


def _build_strengths(
    recommendation: PlanRecommendation,
    weights: dict[str, float],
) -> list[str]:
    strengths: list[str] = []
    top_components = _top_component_names(recommendation.fit_metrics, weights)
    component_strengths = {
        "coverage": "Full coverage across the entered medications.",
        "cost": f"Estimated annual total cost stays around ${recommendation.annual_total_cost:,.0f}.",
        "premium": f"Monthly premium estimate is about ${recommendation.annual_premium / 12:,.0f}.",
        "access": "Pharmacy access is relatively favorable for this ZIP and channel mix.",
        "stability": "Expected cost-sharing looks comparatively steady across the year.",
    }
    for component in top_components:
        _append_unique(strengths, component_strengths[component])

    if recommendation.restriction_count == 0:
        _append_unique(strengths, "No major utilization-management restrictions were flagged.")
    if recommendation.channel_diversity_count <= 1 and recommendation.mail_order_dependency_count == 0:
        _append_unique(strengths, "The projected fill path is simple and does not depend on mail order.")
    if recommendation.coverage_status == "full":
        _append_unique(strengths, "All entered medications were priced within the simulated benefit design.")
    return strengths[:3]


def _build_watchouts(
    recommendation: PlanRecommendation,
    beneficiary: BeneficiaryInput,
    approximate_match_count: int,
) -> list[str]:
    watchouts: list[str] = []
    if recommendation.uncovered_drug_count > 0:
        _append_unique(
            watchouts,
            f"{recommendation.uncovered_drug_count} entered medication(s) are not fully covered or could not be priced.",
        )
    if recommendation.mail_order_dependency_count > 0 and beneficiary.pharmacy_preference != "mail":
        _append_unique(
            watchouts,
            f"{recommendation.mail_order_dependency_count} medication(s) are cheapest through mail order.",
        )
    if recommendation.restriction_count > 0:
        _append_unique(
            watchouts,
            f"Utilization management remains present: {recommendation.restriction_summary}.",
        )
    if recommendation.nearest_preferred_distance_miles is not None and recommendation.nearest_preferred_distance_miles > 15:
        _append_unique(
            watchouts,
            f"Nearest preferred retail pharmacy is about {recommendation.nearest_preferred_distance_miles:.1f} miles away.",
        )
    if recommendation.channel_diversity_count > 1:
        _append_unique(watchouts, "The projected lowest-cost path mixes more than one pharmacy channel.")
    if approximate_match_count > 0:
        _append_unique(watchouts, "At least one medication match is approximate and should be reviewed.")
    return watchouts[:3]


def _build_fit_summary(
    recommendation: PlanRecommendation,
    beneficiary: BeneficiaryInput,
) -> str:
    focus_label = DECISION_FOCUS_LABELS[_normalize_decision_focus(beneficiary.decision_focus)]
    coverage_phrase = "full medication coverage" if recommendation.coverage_status == "full" else "some coverage tradeoffs"
    access_phrase = (
        "good access" if recommendation.fit_metrics.access_score >= 70 else "access watchouts"
    )
    stability_phrase = (
        "steady cost-sharing" if recommendation.fit_metrics.stability_score >= 70 else "more variable cost-sharing"
    )
    if _normalize_decision_focus(beneficiary.decision_focus) == "lowest_monthly_premium":
        return (
            f"Prioritizes {focus_label} with {coverage_phrase}, about ${recommendation.annual_premium / 12:,.0f}/month in premium, "
            f"and {access_phrase}."
        )
    if _normalize_decision_focus(beneficiary.decision_focus) == "pharmacy_access":
        return (
            f"Prioritizes {focus_label} with {access_phrase}, {coverage_phrase}, and about ${recommendation.annual_total_cost:,.0f} annual total cost."
        )
    return (
        f"Best for {focus_label}: {coverage_phrase}, about ${recommendation.annual_total_cost:,.0f} annual total cost, and {stability_phrase}."
    )


def _resolve_drug_match(
    conn: duckdb.DuckDBPyConnection, medication: MedicationInput
) -> tuple[dict[str, Any], MedicationMatch]:
    requested_value = medication.ndc or medication.rxcui or medication.drug_name or ""
    if medication.ndc:
        df = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM silver.dim_drug_reference
            WHERE ndc = ?
            ORDER BY is_insulin DESC
            LIMIT 1
            """,
            [medication.ndc.strip().zfill(11)],
        )
        match_source = "ndc"
        match_confidence = "exact"
    elif medication.rxcui:
        df = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM silver.dim_drug_reference
            WHERE rxcui = ?
            ORDER BY is_insulin DESC
            LIMIT 1
            """,
            [medication.rxcui.strip()],
        )
        match_source = "rxcui"
        match_confidence = "exact"
    else:
        exact_name = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM silver.dim_drug_reference
            WHERE lower(preferred_name) = lower(?)
            ORDER BY is_insulin DESC
            LIMIT 1
            """,
            [medication.drug_name or ""],
        )
        if not exact_name.empty:
            row = exact_name.iloc[0].to_dict()
            return row, MedicationMatch(
                medication_id="",
                requested_value=requested_value,
                requested_drug_name=medication.drug_name,
                resolved_drug_name=str(row["preferred_name"]),
                rxcui=str(row["rxcui"]),
                ndc=str(row["ndc"]),
                match_source="exact_name",
                match_confidence="exact",
                normalized_day_supply=30,
                tier_family="brand",
            )

        exact_synonym = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM silver.dim_drug_reference
            WHERE lower(coalesce(synonym, '')) = lower(?)
            ORDER BY is_insulin DESC
            LIMIT 1
            """,
            [medication.drug_name or ""],
        )
        if not exact_synonym.empty:
            row = exact_synonym.iloc[0].to_dict()
            return row, MedicationMatch(
                medication_id="",
                requested_value=requested_value,
                requested_drug_name=medication.drug_name,
                resolved_drug_name=str(row["preferred_name"]),
                rxcui=str(row["rxcui"]),
                ndc=str(row["ndc"]),
                match_source="synonym",
                match_confidence="exact",
                normalized_day_supply=30,
                tier_family="brand",
            )

        pattern = (medication.drug_name or "").strip().lower() + "%"
        df = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM silver.dim_drug_reference
            WHERE lower(preferred_name) LIKE ?
               OR lower(coalesce(synonym, '')) LIKE ?
            ORDER BY is_insulin DESC, preferred_name
            LIMIT 1
            """,
            [pattern, pattern],
        )
        match_source = "prefix_match"
        match_confidence = "approximate"

    if df.empty:
        raise ValueError(f"Could not resolve medication input: {requested_value}")

    row = df.iloc[0].to_dict()
    return row, MedicationMatch(
        medication_id="",
        requested_value=requested_value,
        requested_drug_name=medication.drug_name,
        resolved_drug_name=str(row["preferred_name"]),
        rxcui=str(row["rxcui"]),
        ndc=str(row["ndc"]),
        match_source=match_source,
        match_confidence=match_confidence,
        normalized_day_supply=30,
        tier_family="brand",
    )


def _resolve_defaults(
    conn: duckdb.DuckDBPyConnection,
    ndc: str,
    day_supply: int,
    tier_family: str,
) -> dict[str, Any]:
    specific = _fetch_dataframe(
        conn,
        """
        SELECT *
        FROM gold.drug_input_defaults
        WHERE ndc = ?
          AND days_supply = ?
          AND tier_family = ?
          AND is_fallback = FALSE
        ORDER BY observation_count DESC
        LIMIT 1
        """,
        [ndc, day_supply, tier_family],
    )
    if not specific.empty:
        return specific.iloc[0].to_dict()

    fallback = _fetch_dataframe(
        conn,
        """
        SELECT *
        FROM gold.drug_input_defaults
        WHERE ndc IS NULL
          AND days_supply = ?
          AND tier_family = ?
          AND is_fallback = TRUE
        ORDER BY observation_count DESC
        LIMIT 1
        """,
        [day_supply, tier_family],
    )
    if not fallback.empty:
        return fallback.iloc[0].to_dict()
    return {
        "default_quantity": float(day_supply),
        "default_fills_per_year": max(1, math.ceil(365 / day_supply)),
        "observation_count": 0,
    }


def _infer_tier_family(
    conn: duckdb.DuckDBPyConnection, ndc: str, day_supply: int, declared_tier_family: str | None
) -> str:
    if declared_tier_family:
        return declared_tier_family.lower()
    df = _fetch_dataframe(
        conn,
        """
        SELECT tier_family, count(*) AS match_count
        FROM gold.plan_drug_cost_basis
        WHERE ndc = ?
          AND days_supply = ?
        GROUP BY 1
        ORDER BY match_count DESC, tier_family
        LIMIT 1
        """,
        [ndc, day_supply],
    )
    if not df.empty:
        return str(df.iloc[0]["tier_family"])
    return "brand"


def _apply_cost_rule(
    negotiated_price: float,
    cost_type: float | None,
    cost_amt: float | None,
    cost_min: float | None,
    cost_max: float | None,
) -> float | None:
    if cost_type is None or int(cost_type) == 0 or cost_amt is None:
        return None

    if int(cost_type) == 1:
        value = float(cost_amt)
    else:
        value = negotiated_price * float(cost_amt)

    if cost_min is not None and not pd.isna(cost_min):
        value = max(value, float(cost_min))
    if cost_max is not None and not pd.isna(cost_max):
        value = min(value, float(cost_max))
    return min(value, negotiated_price)


def _channel_fields(channel: str) -> tuple[str, str]:
    mapping = {
        "pref_retail": ("pref", "pref"),
        "nonpref_retail": ("nonpref", "nonpref"),
        "pref_mail": ("mail_pref", "pref_mail"),
        "nonpref_mail": ("mail_nonpref", "nonpref_mail"),
    }
    if channel not in mapping:
        raise ValueError(f"Unsupported channel {channel}")
    return mapping[channel]


def _select_fee(channel_summary: dict[str, Any], channel: str, tier_family: str, day_supply: int) -> float | None:
    family_prefix = "generic" if tier_family == "generic" else "brand"
    field = f"{channel}_{family_prefix}_fee_{day_supply}"
    value = channel_summary.get(field)
    if value is None or pd.isna(value):
        return None
    return float(value)


def _select_floor(channel_summary: dict[str, Any], channel: str) -> float:
    field = f"{channel}_floor"
    value = channel_summary.get(field)
    if value is None or pd.isna(value):
        return 0.0
    return float(value)


def _channel_available(channel_summary: dict[str, Any], channel: str, pharmacy_preference: str) -> bool:
    if pharmacy_preference == "retail" and "mail" in channel:
        return False
    if pharmacy_preference == "mail" and "retail" in channel:
        return False

    availability_map = {
        "pref_retail": "has_pref_retail",
        "nonpref_retail": "has_nonpref_retail",
        "pref_mail": "has_pref_mail",
        "nonpref_mail": "has_nonpref_mail",
    }
    return bool(channel_summary.get(availability_map[channel], False))


def _apply_lis_adjustment(amount: float, tier_family: str, lis_status: str) -> float:
    if lis_status == "full":
        lis_cap = FULL_LIS_GENERIC_COPAY if tier_family == "generic" else FULL_LIS_BRAND_COPAY
        return min(amount, lis_cap)
    if lis_status == "partial":
        lis_cap = PARTIAL_LIS_GENERIC_CAP if tier_family == "generic" else PARTIAL_LIS_BRAND_CAP
        return min(amount * PARTIAL_LIS_DISCOUNT_FACTOR, lis_cap)
    return amount


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return radius_miles * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _lookup_nearest_preferred_distance(
    conn: duckdb.DuckDBPyConnection, zipcode: str, plan_keys: list[str]
) -> dict[str, float | None]:
    zip_df = _fetch_dataframe(
        conn,
        "SELECT lat, lng FROM silver.dim_zipcode WHERE zip_code = ? LIMIT 1",
        [zipcode],
    )
    if zip_df.empty or pd.isna(zip_df.iloc[0]["lat"]) or pd.isna(zip_df.iloc[0]["lng"]):
        return {plan_key: None for plan_key in plan_keys}

    user_lat = float(zip_df.iloc[0]["lat"])
    user_lng = float(zip_df.iloc[0]["lng"])
    placeholders = ", ".join("?" for _ in plan_keys)
    pharmacy_df = _fetch_dataframe(
        conn,
        f"""
        SELECT plan_key, lat, lng
        FROM gold.plan_preferred_pharmacy_locations
        WHERE plan_key IN ({placeholders})
        """,
        plan_keys,
    )
    distances: dict[str, float | None] = {plan_key: None for plan_key in plan_keys}
    for plan_key, group in pharmacy_df.groupby("plan_key"):
        distances[plan_key] = min(
            _haversine_miles(user_lat, user_lng, float(row.lat), float(row.lng))
            for row in group.itertuples()
        )
    return distances


def _simulate_fill_cost(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    channel: str,
    quantity: float,
    remaining_deductible: float,
    oop_accumulated: float,
    lis_status: str,
) -> FillCostResult | None:
    fee = _select_fee(channel_summary, channel, str(basis["tier_family"]), int(basis["days_supply"]))
    if fee is None or basis["unit_cost"] is None or pd.isna(basis["unit_cost"]):
        return None

    negotiated = max(float(basis["unit_cost"]) * quantity + fee, _select_floor(channel_summary, channel))
    channel_prefix, insulin_prefix = _channel_fields(channel)
    deductible_before = max(0.0, remaining_deductible)
    oop_before = max(0.0, oop_accumulated)

    if bool(basis["is_insulin"]):
        insulin_value = basis.get(f"insulin_{insulin_prefix}_copay")
        if insulin_value is not None and not pd.isna(insulin_value):
            base_cost = min(float(insulin_value), negotiated)
            coverage_phase = "insulin_override"
        else:
            base_cost = _apply_cost_rule(
                negotiated,
                basis.get(f"init_{channel_prefix}_cost_type"),
                basis.get(f"init_{channel_prefix}_cost_amt"),
                basis.get(f"init_{channel_prefix}_cost_min"),
                basis.get(f"init_{channel_prefix}_cost_max"),
            )
            coverage_phase = "insulin_initial_coverage_rule"
        deductible_exposure = 0.0
        initial_coverage_oop = base_cost or 0.0
        deductible_after = deductible_before
    else:
        init_cost = _apply_cost_rule(
            negotiated,
            basis.get(f"init_{channel_prefix}_cost_type"),
            basis.get(f"init_{channel_prefix}_cost_amt"),
            basis.get(f"init_{channel_prefix}_cost_min"),
            basis.get(f"init_{channel_prefix}_cost_max"),
        )
        pre_cost = _apply_cost_rule(
            negotiated,
            basis.get(f"pre_{channel_prefix}_cost_type"),
            basis.get(f"pre_{channel_prefix}_cost_amt"),
            basis.get(f"pre_{channel_prefix}_cost_min"),
            basis.get(f"pre_{channel_prefix}_cost_max"),
        )

        if deductible_before > 0 and bool(basis["deductible_applies"]):
            deductible_exposure = min(negotiated, deductible_before)
            deductible_after = max(0.0, deductible_before - deductible_exposure)
            covered_remainder = max(negotiated - deductible_exposure, 0.0)
            remainder_oop = 0.0
            if covered_remainder > 0 and init_cost is not None:
                init_ratio = 0.0 if negotiated == 0 else covered_remainder / negotiated
                remainder_oop = min(covered_remainder, init_cost * init_ratio)
            base_cost = deductible_exposure + remainder_oop
            initial_coverage_oop = remainder_oop
            coverage_phase = (
                "deductible_then_initial_coverage" if covered_remainder > 0 else "deductible_only"
            )
        else:
            rule_cost = pre_cost if deductible_before > 0 and pre_cost is not None else init_cost
            if rule_cost is None:
                return None
            base_cost = rule_cost
            deductible_exposure = 0.0
            deductible_after = deductible_before
            initial_coverage_oop = rule_cost
            coverage_phase = "predeductible_rule" if deductible_before > 0 and pre_cost is not None else "initial_coverage_rule"

    if base_cost is None:
        return None

    lis_adjusted_cost = _apply_lis_adjustment(base_cost, str(basis["tier_family"]), lis_status)
    oop_cap_applied = False
    if oop_before >= ANNUAL_OOP_CAP:
        final_cost = 0.0
        oop_cap_applied = True
    else:
        capped_cost = min(lis_adjusted_cost, ANNUAL_OOP_CAP - oop_before)
        final_cost = max(0.0, capped_cost)
        oop_cap_applied = final_cost < lis_adjusted_cost

    return FillCostResult(
        total_oop=final_cost,
        base_oop=max(0.0, base_cost),
        lis_adjusted_oop=max(0.0, lis_adjusted_cost),
        deductible_exposure=max(0.0, deductible_exposure),
        initial_coverage_oop=max(0.0, initial_coverage_oop),
        negotiated_price=negotiated,
        coverage_phase=coverage_phase,
        pricing_status="priced",
        deductible_before=deductible_before,
        deductible_after=deductible_after,
        oop_before=oop_before,
        oop_after=oop_before + final_cost,
        oop_cap_applied=oop_cap_applied,
    )


def _build_coverage_message(coverage_status: str, drug_name: str) -> str:
    if coverage_status == "excluded":
        return f"{drug_name} is excluded from formulary coverage for this plan."
    if coverage_status == "missing_price":
        return f"{drug_name} has no usable pricing record for this plan."
    if coverage_status == "channel_unavailable":
        return f"{drug_name} could not be priced for the chosen pharmacy preference."
    return f"{drug_name} is not covered by this plan."


def _build_restriction_summary(restriction_count: int, flags: dict[str, bool]) -> str:
    if restriction_count == 0:
        return "no major restrictions flagged"
    parts = [
        label
        for label, enabled in (
            ("prior auth", flags["prior_auth"]),
            ("step therapy", flags["step_therapy"]),
            ("quantity limits", flags["quantity_limit"]),
        )
        if enabled
    ]
    return ", ".join(parts) or "restrictions flagged"


def _compute_rules_score(
    coverage_status: str,
    annual_total_cost: float,
    uncovered_drug_count: int,
    restriction_count: int,
    network_flag: str,
) -> float:
    return (
        (10000.0 if coverage_status == "full" else 0.0)
        - float(annual_total_cost)
        - 250.0 * float(uncovered_drug_count)
        - 35.0 * float(restriction_count)
        - 20.0 * float(NETWORK_PRIORITY.get(network_flag, 3))
    )


def _apply_fit_scoring(
    recommendations: list[PlanRecommendation],
    beneficiary: BeneficiaryInput,
) -> None:
    if not recommendations:
        return

    weights = _resolve_fit_weights(beneficiary)
    total_costs = [recommendation.annual_total_cost for recommendation in recommendations]
    premiums = [recommendation.annual_premium for recommendation in recommendations]
    min_total_cost = min(total_costs)
    max_total_cost = max(total_costs)
    min_premium = min(premiums)
    max_premium = max(premiums)
    approximate_match_count = sum(
        1 for item in recommendations[0].resolved_medications if item.match_confidence != "exact"
    )

    for recommendation in recommendations:
        breakdowns = recommendation.drug_breakdowns
        uncovered_only_count = sum(1 for item in breakdowns if item.coverage_status == "uncovered")
        excluded_count = sum(1 for item in breakdowns if item.coverage_status == "excluded")
        missing_price_count = sum(1 for item in breakdowns if item.coverage_status == "missing_price")
        channel_unavailable_count = sum(1 for item in breakdowns if item.coverage_status == "channel_unavailable")
        mail_order_dependency_count = sum(
            1 for item in breakdowns if item.selected_channel in {"pref_mail", "nonpref_mail"}
        )
        retail_dependency_count = sum(
            1 for item in breakdowns if item.selected_channel in {"pref_retail", "nonpref_retail"}
        )
        channel_diversity_count = len(
            {item.selected_channel for item in breakdowns if item.selected_channel != "unavailable"}
        )
        deductible_exposure_total = sum(float(item.deductible_exposure) for item in breakdowns)

        coverage_score = _clamp(
            100.0
            - (22.0 if recommendation.coverage_status != "full" else 0.0)
            - 10.0 * uncovered_only_count
            - 18.0 * excluded_count
            - 14.0 * missing_price_count
            - 12.0 * channel_unavailable_count
        )
        access_score = _clamp(
            NETWORK_ACCESS_BASE.get(recommendation.network_flag, 60.0)
            - _distance_penalty(recommendation.nearest_preferred_distance_miles)
            - 10.0 * max(channel_diversity_count - 1, 0)
            - 6.0 * max(mail_order_dependency_count - 1, 0)
            - _preferred_channel_penalty(
                beneficiary.pharmacy_preference,
                mail_order_dependency_count,
                retail_dependency_count,
                max(1, len(breakdowns)),
            )
        )
        stability_score = _clamp(
            100.0
            - 9.0 * recommendation.restriction_count
            - 8.0 * max(channel_diversity_count - 1, 0)
            - _deductible_pressure_penalty(
                deductible_exposure_total,
                max(recommendation.annual_total_cost, recommendation.annual_drug_oop, 1.0),
            )
            - 4.0 * channel_unavailable_count
        )

        fit_metrics = PlanFitMetrics(
            cost_score=round(_relative_score(recommendation.annual_total_cost, min_total_cost, max_total_cost), 2),
            premium_score=round(_relative_score(recommendation.annual_premium, min_premium, max_premium), 2),
            coverage_score=round(coverage_score, 2),
            access_score=round(access_score, 2),
            stability_score=round(stability_score, 2),
        )
        fit_score = round(
            fit_metrics.cost_score * weights["cost"]
            + fit_metrics.premium_score * weights["premium"]
            + fit_metrics.coverage_score * weights["coverage"]
            + fit_metrics.access_score * weights["access"]
            + fit_metrics.stability_score * weights["stability"],
            2,
        )
        if recommendation.coverage_status == "full":
            fit_score = max(fit_score, round(60.0 + 0.15 * fit_metrics.coverage_score, 2))
        else:
            fit_score = min(fit_score, 59.0)

        recommendation.monthly_cost_estimate = round(recommendation.annual_total_cost / 12.0, 2)
        recommendation.fit_metrics = fit_metrics
        recommendation.fit_score = fit_score
        recommendation.fit_label = _fit_label(fit_score)
        recommendation.mail_order_dependency_count = mail_order_dependency_count
        recommendation.channel_diversity_count = channel_diversity_count
        recommendation.key_strengths = _build_strengths(recommendation, weights)
        recommendation.key_watchouts = _build_watchouts(recommendation, beneficiary, approximate_match_count)
        recommendation.fit_summary = _build_fit_summary(recommendation, beneficiary)


def recommend_plans(
    beneficiary: BeneficiaryInput,
    medications: list[MedicationInput],
    config: PipelineConfig | None = None,
    ranking_mode: str = "rules",
) -> list[PlanRecommendation]:
    if not medications:
        raise ValueError("At least one medication is required.")

    logger.info(
        "recommendation request zipcode=%s medications=%s profile=%s",
        beneficiary.zipcode,
        len(medications),
        (config or PipelineConfig()).build_profile,
    )
    conn = _connect(config)
    zipcode = _normalize_zipcode(beneficiary.zipcode)
    candidate_plans = _fetch_dataframe(
        conn,
        """
        SELECT DISTINCT
            psa.plan_key,
            ps.plan_name,
            ps.annual_premium,
            ps.deductible,
            pns.network_flag
        FROM gold.plan_service_area psa
        JOIN gold.plan_summary ps ON psa.plan_key = ps.plan_key
        JOIN gold.plan_network_summary pns ON psa.plan_key = pns.plan_key
        WHERE psa.zip_code = ?
        ORDER BY ps.plan_name
        """,
        [zipcode],
    )
    if candidate_plans.empty:
        conn.close()
        logger.warning("no candidate plans found for zipcode=%s", zipcode)
        return []

    resolved_medications: list[dict[str, Any]] = []
    matches: list[MedicationMatch] = []
    for medication_index, medication in enumerate(medications, start=1):
        medication_id = f"med_{medication_index}"
        drug_row, match = _resolve_drug_match(conn, medication)
        day_supply = _normalize_days_supply(medication.day_supply)
        tier_family = _infer_tier_family(
            conn, str(drug_row["ndc"]), day_supply, medication.tier_family
        )
        defaults = _resolve_defaults(conn, str(drug_row["ndc"]), day_supply, tier_family)
        resolved_match = MedicationMatch(
            medication_id=medication_id,
            requested_value=match.requested_value,
            requested_drug_name=medication.drug_name,
            resolved_drug_name=match.resolved_drug_name,
            rxcui=match.rxcui,
            ndc=match.ndc,
            match_source=match.match_source,
            match_confidence=match.match_confidence,
            normalized_day_supply=day_supply,
            tier_family=tier_family,
        )
        matches.append(resolved_match)
        resolved_medications.append(
            {
                "medication_id": medication_id,
                "input": medication,
                "requested_drug_name": medication.drug_name,
                "drug_name": str(drug_row["preferred_name"]),
                "rxcui": str(drug_row["rxcui"]),
                "ndc": str(drug_row["ndc"]),
                "is_insulin": bool(drug_row["is_insulin"]),
                "day_supply": day_supply,
                "tier_family": tier_family,
                "quantity": float(medication.quantity_override or defaults["default_quantity"] or day_supply),
                "fills_per_year": int(
                    medication.fills_per_year_override
                    or defaults["default_fills_per_year"]
                    or max(1, math.ceil(365 / day_supply))
                ),
                "match": resolved_match,
            }
        )

    plan_keys = candidate_plans["plan_key"].tolist()
    placeholders = ", ".join("?" for _ in plan_keys)
    basis_df = _fetch_dataframe(
        conn,
        f"""
        SELECT *
        FROM gold.plan_drug_cost_basis
        WHERE plan_key IN ({placeholders})
          AND ndc IN ({", ".join("?" for _ in resolved_medications)})
        """,
        plan_keys + [item["ndc"] for item in resolved_medications],
    )
    channel_df = _fetch_dataframe(
        conn,
        f"SELECT * FROM gold.plan_channel_summary WHERE plan_key IN ({placeholders})",
        plan_keys,
    )
    nearest_distances = _lookup_nearest_preferred_distance(conn, zipcode, plan_keys)

    basis_lookup: dict[tuple[str, str, int], dict[str, Any]] = {}
    for row in basis_df.to_dict("records"):
        key = (str(row["plan_key"]), str(row["ndc"]), int(row["days_supply"]))
        existing = basis_lookup.get(key)
        if existing is None or (pd.isna(existing.get("unit_cost")) and not pd.isna(row.get("unit_cost"))):
            basis_lookup[key] = row

    channel_lookup = {str(row["plan_key"]): row for row in channel_df.to_dict("records")}
    recommendations: list[PlanRecommendation] = []

    for plan in candidate_plans.to_dict("records"):
        plan_key = str(plan["plan_key"])
        channel_summary = channel_lookup.get(plan_key, {})
        remaining_deductible = float(plan.get("deductible") or 0.0)
        oop_accumulated = 0.0
        annual_drug_oop = 0.0
        plan_restriction_flags = {"prior_auth": False, "step_therapy": False, "quantity_limit": False}
        selected_channels: dict[str, int] = {}
        groups = PlanExplanationGroups([], [], [], [], [], [])
        detail_groups = PlanExplanationDetailGroups([], [], [], [], [], [])
        drug_state: dict[str, dict[str, Any]] = {}

        fill_events: list[tuple[float, int, dict[str, Any], dict[str, Any]]] = []
        for medication in resolved_medications:
            medication_id = str(medication["medication_id"])
            drug_name = str(medication["drug_name"])
            basis = basis_lookup.get((plan_key, medication["ndc"], medication["day_supply"]))
            state = {
                "medication": medication,
                "basis": basis,
                "coverage_status": "covered",
                "pricing_status": "priced",
                "selected_channel": "unavailable",
                "annual_oop": 0.0,
                "deductible_exposure": 0.0,
                "initial_coverage_oop": 0.0,
                "lis_adjusted_oop": 0.0,
                "negotiated_price_total": 0.0,
                "oop_cap_savings": 0.0,
                "fill_oop_values": [],
                "coverage_phases": set(),
                "fill_traces": [],
                "explanations": [],
            }
            if basis is None:
                state["coverage_status"] = "uncovered"
                state["pricing_status"] = "uncovered"
                message = _build_coverage_message("uncovered", drug_name)
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.coverage_issues,
                    detail_groups.coverage_issues,
                    "uncovered_drug",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            elif bool(basis.get("is_excluded")):
                state["coverage_status"] = "excluded"
                state["pricing_status"] = "excluded"
                message = _build_coverage_message("excluded", drug_name)
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.coverage_issues,
                    detail_groups.coverage_issues,
                    "excluded_drug",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            elif basis.get("unit_cost") is None or pd.isna(basis.get("unit_cost")):
                state["coverage_status"] = "missing_price"
                state["pricing_status"] = "missing_price"
                message = _build_coverage_message("missing_price", drug_name)
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.coverage_issues,
                    detail_groups.coverage_issues,
                    "missing_price",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            else:
                interval = 365.0 / max(1, medication["fills_per_year"])
                for fill_index in range(medication["fills_per_year"]):
                    fill_events.append((fill_index * interval, fill_index + 1, medication, basis))
            drug_state[medication_id] = state

        fill_events.sort(key=lambda item: item[0])
        for day_offset, fill_number, medication, basis in fill_events:
            medication_id = str(medication["medication_id"])
            drug_name = str(medication["drug_name"])
            state = drug_state[medication_id]
            best_channel: str | None = None
            best_result: FillCostResult | None = None
            for channel in ("pref_retail", "nonpref_retail", "pref_mail", "nonpref_mail"):
                if not _channel_available(channel_summary, channel, beneficiary.pharmacy_preference):
                    continue
                channel_result = _simulate_fill_cost(
                    basis,
                    channel_summary,
                    channel,
                    float(medication["quantity"]),
                    remaining_deductible,
                    oop_accumulated,
                    beneficiary.lis_status,
                )
                if channel_result is None:
                    continue
                if best_result is None or channel_result.total_oop < best_result.total_oop:
                    best_result = channel_result
                    best_channel = channel

            if best_channel is None or best_result is None:
                state["coverage_status"] = "channel_unavailable"
                state["pricing_status"] = "channel_unavailable"
                message = _build_coverage_message("channel_unavailable", drug_name)
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.coverage_issues,
                    detail_groups.coverage_issues,
                    "channel_unavailable",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
                continue

            remaining_deductible = best_result.deductible_after
            oop_accumulated = best_result.oop_after
            annual_drug_oop += best_result.total_oop
            state["selected_channel"] = best_channel
            state["annual_oop"] += best_result.total_oop
            state["deductible_exposure"] += best_result.deductible_exposure
            state["initial_coverage_oop"] += best_result.initial_coverage_oop
            state["lis_adjusted_oop"] += best_result.lis_adjusted_oop
            state["negotiated_price_total"] += best_result.negotiated_price
            state["oop_cap_savings"] += max(0.0, best_result.lis_adjusted_oop - best_result.total_oop)
            state["fill_oop_values"].append(best_result.total_oop)
            state["coverage_phases"].add(best_result.coverage_phase)
            state["fill_traces"].append(
                DrugFillTrace(
                    fill_number=fill_number,
                    day_offset=int(round(day_offset)),
                    selected_channel=best_channel,
                    coverage_phase=best_result.coverage_phase,
                    pricing_status=best_result.pricing_status,
                    negotiated_price=round(best_result.negotiated_price, 2),
                    deductible_before=round(best_result.deductible_before, 2),
                    deductible_applied=round(best_result.deductible_exposure, 2),
                    deductible_after=round(best_result.deductible_after, 2),
                    base_oop=round(best_result.base_oop, 2),
                    initial_coverage_oop=round(best_result.initial_coverage_oop, 2),
                    lis_adjusted_oop=round(best_result.lis_adjusted_oop, 2),
                    final_oop=round(best_result.total_oop, 2),
                    oop_before=round(best_result.oop_before, 2),
                    oop_after=round(best_result.oop_after, 2),
                    oop_cap_applied=best_result.oop_cap_applied,
                )
            )
            selected_channels[best_channel] = selected_channels.get(best_channel, 0) + 1

            if bool(basis["has_prior_auth"]):
                plan_restriction_flags["prior_auth"] = True
                message = f"{drug_name} requires prior authorization."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.utilization_management_issues,
                    detail_groups.utilization_management_issues,
                    "prior_authorization",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            if bool(basis["has_step_therapy"]):
                plan_restriction_flags["step_therapy"] = True
                message = f"{drug_name} has step therapy restrictions."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.utilization_management_issues,
                    detail_groups.utilization_management_issues,
                    "step_therapy",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            if bool(basis["has_quantity_limit"]):
                plan_restriction_flags["quantity_limit"] = True
                message = f"{drug_name} has quantity limit rules."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.utilization_management_issues,
                    detail_groups.utilization_management_issues,
                    "quantity_limit",
                    message,
                    related_drug=drug_name,
                    severity="warning",
                )
            if bool(basis["is_insulin"]) and best_channel not in {"pref_retail", "pref_mail"}:
                message = f"{drug_name} insulin savings depend on a non-preferred channel."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.insulin_considerations,
                    detail_groups.insulin_considerations,
                    "insulin_nonpreferred_dependency",
                    message,
                    related_drug=drug_name,
                    related_channel=best_channel,
                    severity="warning",
                )
            if best_result.deductible_exposure > 0:
                message = f"{drug_name} adds about ${best_result.deductible_exposure:.2f} of deductible exposure."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.deductible_issues,
                    detail_groups.deductible_issues,
                    "deductible_exposure",
                    message,
                    related_drug=drug_name,
                    coverage_phase=best_result.coverage_phase,
                )
            if beneficiary.lis_status != "none" and best_result.lis_adjusted_oop < best_result.base_oop:
                message = f"{drug_name} receives {beneficiary.lis_status} LIS cost-sharing relief."
                _append_explanation(
                    groups.cost_logic_issues,
                    detail_groups.cost_logic_issues,
                    "lis_adjustment",
                    message,
                    related_drug=drug_name,
                    coverage_phase=best_result.coverage_phase,
                )
            if best_result.oop_cap_applied:
                message = f"{drug_name} hits the annual OOP cap during the simulated year."
                _append_explanation(
                    groups.cost_logic_issues,
                    detail_groups.cost_logic_issues,
                    "annual_oop_cap",
                    message,
                    related_drug=drug_name,
                    coverage_phase=best_result.coverage_phase,
                )
            if best_result.coverage_phase in {"deductible_only", "deductible_then_initial_coverage"}:
                message = f"{drug_name} spends time in the deductible phase before standard cost sharing applies."
                _append_explanation(
                    groups.cost_logic_issues,
                    detail_groups.cost_logic_issues,
                    "deductible_phase",
                    message,
                    related_drug=drug_name,
                    coverage_phase=best_result.coverage_phase,
                )

        uncovered_count = 0
        annual_premium = float(plan.get("annual_premium") or 0.0)
        breakdowns: list[PlanDrugBreakdown] = []
        for medication in resolved_medications:
            medication_id = str(medication["medication_id"])
            drug_name = str(medication["drug_name"])
            state = drug_state[medication_id]
            basis = state["basis"]
            coverage_state = str(state["coverage_status"])
            if coverage_state != "covered":
                uncovered_count += 1
            average_fill_oop = None
            if state["fill_oop_values"]:
                average_fill_oop = sum(state["fill_oop_values"]) / len(state["fill_oop_values"])
            if state["selected_channel"] in {"pref_mail", "nonpref_mail"}:
                _append_explanation(
                    groups.pharmacy_access_issues,
                    detail_groups.pharmacy_access_issues,
                    "mail_order_cheapest",
                    f"{drug_name} is cheapest through mail-order fulfillment.",
                    related_drug=drug_name,
                    related_channel=str(state["selected_channel"]),
                )
            breakdowns.append(
                PlanDrugBreakdown(
                    medication_id=medication_id,
                    plan_key=plan_key,
                    requested_drug_name=medication["requested_drug_name"],
                    drug_name=drug_name,
                    tier=int(basis["tier_level_value"]) if basis and basis.get("tier_level_value") is not None else None,
                    requested_day_supply=int(medication["day_supply"]),
                    selected_channel=str(state["selected_channel"]),
                    per_fill_oop=round(float(average_fill_oop), 2) if average_fill_oop is not None else None,
                    annual_oop=round(float(state["annual_oop"]), 2)
                    if state["annual_oop"] is not None
                    else None,
                    deductible_exposure=round(float(state["deductible_exposure"]), 2),
                    initial_coverage_oop=round(float(state["initial_coverage_oop"]), 2),
                    lis_adjusted_oop=round(float(state["lis_adjusted_oop"]), 2),
                    negotiated_price_total=round(float(state["negotiated_price_total"]), 2),
                    oop_cap_savings=round(float(state["oop_cap_savings"]), 2),
                    pa_flag=bool(basis["has_prior_auth"]) if basis else False,
                    st_flag=bool(basis["has_step_therapy"]) if basis else False,
                    ql_flag=bool(basis["has_quantity_limit"]) if basis else False,
                    insulin_flag=bool(basis["is_insulin"]) if basis else bool(medication["is_insulin"]),
                    coverage_gap_flag=coverage_state != "covered",
                    coverage_status=coverage_state,
                    pricing_status=str(state["pricing_status"]),
                    coverage_phases=sorted(str(value) for value in state["coverage_phases"]),
                    match_source=medication["match"].match_source,
                    match_confidence=medication["match"].match_confidence,
                    explanations=state["explanations"],
                    fill_traces=state["fill_traces"],
                )
            )

        nearest_distance = nearest_distances.get(plan_key)
        if plan["network_flag"] in {"no_preferred_retail", "limited_preferred_retail"}:
            _append_explanation(
                groups.pharmacy_access_issues,
                detail_groups.pharmacy_access_issues,
                "limited_preferred_retail",
                "Preferred retail pharmacy access is limited for this ZIP.",
                severity="warning",
            )
        if nearest_distance is not None and nearest_distance > 15:
            _append_explanation(
                groups.pharmacy_access_issues,
                detail_groups.pharmacy_access_issues,
                "preferred_retail_distance",
                f"Nearest preferred retail pharmacy is about {nearest_distance:.1f} miles away.",
                severity="warning",
            )

        coverage_status = "full" if uncovered_count == 0 else "partial"
        restriction_count = sum(int(value) for value in plan_restriction_flags.values())
        restriction_summary = _build_restriction_summary(restriction_count, plan_restriction_flags)
        explanation_groups = PlanExplanationGroups(
            coverage_issues=_truncate_group_strings(groups.coverage_issues),
            utilization_management_issues=_truncate_group_strings(groups.utilization_management_issues),
            insulin_considerations=_truncate_group_strings(groups.insulin_considerations),
            pharmacy_access_issues=_truncate_group_strings(groups.pharmacy_access_issues),
            deductible_issues=_truncate_group_strings(groups.deductible_issues),
            cost_logic_issues=_truncate_group_strings(groups.cost_logic_issues),
        )
        explanation_detail_groups = PlanExplanationDetailGroups(
            coverage_issues=_truncate_group_details(detail_groups.coverage_issues),
            utilization_management_issues=_truncate_group_details(detail_groups.utilization_management_issues),
            insulin_considerations=_truncate_group_details(detail_groups.insulin_considerations),
            pharmacy_access_issues=_truncate_group_details(detail_groups.pharmacy_access_issues),
            deductible_issues=_truncate_group_details(detail_groups.deductible_issues),
            cost_logic_issues=_truncate_group_details(detail_groups.cost_logic_issues),
        )
        explanations = _flatten_explanation_groups(explanation_groups)[:8]
        total_cost = round(annual_premium + annual_drug_oop, 2)
        rules_score = _compute_rules_score(
            coverage_status,
            total_cost,
            uncovered_count,
            restriction_count,
            str(plan["network_flag"]),
        )

        recommendations.append(
            PlanRecommendation(
                plan_key=plan_key,
                plan_name=str(plan["plan_name"]),
                annual_drug_oop=round(annual_drug_oop, 2),
                estimated_annual_oop=round(annual_drug_oop, 2),
                annual_premium=round(annual_premium, 2),
                annual_total_cost=total_cost,
                monthly_cost_estimate=round(total_cost / 12.0, 2),
                coverage_status=coverage_status,
                best_channel_mix=", ".join(
                    f"{channel}:{count}" for channel, count in sorted(selected_channels.items())
                )
                or "no covered fills",
                network_flag=str(plan["network_flag"]),
                network_access_summary=_network_access_summary(
                    str(plan["network_flag"]),
                    round(float(nearest_distance), 2) if nearest_distance is not None else None,
                ),
                insulin_flag=bool(explanation_groups.insulin_considerations),
                restriction_summary=restriction_summary,
                explanations=explanations,
                explanation_groups=explanation_groups,
                explanation_detail_groups=explanation_detail_groups,
                resolved_medications=matches,
                plan_rank=0,
                uncovered_drug_count=uncovered_count,
                restriction_count=restriction_count,
                ranking_source="rules_only",
                model_score=None,
                model_confidence_bucket=None,
                rules_score=round(rules_score, 4),
                fit_score=0.0,
                fit_label="",
                fit_summary="",
                fit_metrics=PlanFitMetrics(
                    cost_score=0.0,
                    premium_score=0.0,
                    coverage_score=0.0,
                    access_score=0.0,
                    stability_score=0.0,
                ),
                key_strengths=[],
                key_watchouts=[],
                mail_order_dependency_count=0,
                channel_diversity_count=0,
                nearest_preferred_distance_miles=round(float(nearest_distance), 2)
                if nearest_distance is not None
                else None,
                service_area_eligible=True,
                comparison_only=False,
                feature_version=FEATURE_VERSION,
                drug_breakdowns=breakdowns,
            )
        )

    _apply_fit_scoring(recommendations, beneficiary)
    recommendations.sort(
        key=lambda item: (
            1 if item.coverage_status != "full" else 0,
            -item.fit_score,
            item.annual_total_cost,
            item.uncovered_drug_count,
            item.restriction_count,
            NETWORK_PRIORITY.get(item.network_flag, 99),
            item.plan_name,
        )
    )
    for rank, recommendation in enumerate(recommendations, start=1):
        recommendation.plan_rank = rank

    if ranking_mode == "hybrid":
        from .modeling import apply_hybrid_reranking

        recommendations = apply_hybrid_reranking(recommendations, beneficiary, config=config)

    conn.close()
    return recommendations[: max(1, beneficiary.top_n)]


def recommendations_to_frame(recommendations: list[PlanRecommendation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "plan_rank": recommendation.plan_rank,
                "plan_key": recommendation.plan_key,
                "plan_name": recommendation.plan_name,
                "fit_label": recommendation.fit_label,
                "fit_score": recommendation.fit_score,
                "fit_summary": recommendation.fit_summary,
                "annual_premium": recommendation.annual_premium,
                "annual_drug_oop": recommendation.annual_drug_oop,
                "estimated_annual_oop": recommendation.estimated_annual_oop,
                "annual_total_cost": recommendation.annual_total_cost,
                "monthly_cost_estimate": recommendation.monthly_cost_estimate,
                "coverage_status": recommendation.coverage_status,
                "uncovered_drug_count": recommendation.uncovered_drug_count,
                "restriction_count": recommendation.restriction_count,
                "ranking_source": recommendation.ranking_source,
                "model_score": recommendation.model_score,
                "model_confidence_bucket": recommendation.model_confidence_bucket,
                "rules_score": recommendation.rules_score,
                "coverage_score": recommendation.fit_metrics.coverage_score,
                "access_score": recommendation.fit_metrics.access_score,
                "stability_score": recommendation.fit_metrics.stability_score,
                "feature_version": recommendation.feature_version,
                "best_channel_mix": recommendation.best_channel_mix,
                "network_flag": recommendation.network_flag,
                "network_access_summary": recommendation.network_access_summary,
                "mail_order_dependency_count": recommendation.mail_order_dependency_count,
                "channel_diversity_count": recommendation.channel_diversity_count,
                "nearest_preferred_distance_miles": recommendation.nearest_preferred_distance_miles,
                "service_area_eligible": recommendation.service_area_eligible,
                "comparison_only": recommendation.comparison_only,
                "key_strengths": " | ".join(recommendation.key_strengths),
                "key_watchouts": " | ".join(recommendation.key_watchouts),
                "coverage_issues": " | ".join(recommendation.explanation_groups.coverage_issues),
                "utilization_issues": " | ".join(
                    recommendation.explanation_groups.utilization_management_issues
                ),
                "pharmacy_access_issues": " | ".join(
                    recommendation.explanation_groups.pharmacy_access_issues
                ),
                "cost_logic_issues": " | ".join(recommendation.explanation_groups.cost_logic_issues),
            }
            for recommendation in recommendations
        ]
    )


def recommendations_to_comparison_frame(recommendations: list[PlanRecommendation]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "plan_rank": recommendation.plan_rank,
                "plan_name": recommendation.plan_name,
                "fit_score": recommendation.fit_score,
                "fit_label": recommendation.fit_label,
                "annual_premium": recommendation.annual_premium,
                "annual_drug_oop": recommendation.annual_drug_oop,
                "estimated_annual_oop": recommendation.estimated_annual_oop,
                "annual_total_cost": recommendation.annual_total_cost,
                "monthly_cost_estimate": recommendation.monthly_cost_estimate,
                "coverage_status": recommendation.coverage_status,
                "network_flag": recommendation.network_flag,
                "network_access_summary": recommendation.network_access_summary,
                "ranking_source": recommendation.ranking_source,
                "model_score": recommendation.model_score,
                "rules_score": recommendation.rules_score,
                "coverage_score": recommendation.fit_metrics.coverage_score,
                "access_score": recommendation.fit_metrics.access_score,
                "stability_score": recommendation.fit_metrics.stability_score,
                "restriction_summary": recommendation.restriction_summary,
                "channel_mix": recommendation.best_channel_mix,
                "service_area_eligible": recommendation.service_area_eligible,
                "comparison_only": recommendation.comparison_only,
                "watchouts": " | ".join(recommendation.key_watchouts),
            }
            for recommendation in recommendations
        ]
    )


def recommendations_to_ui_payload(recommendations: list[PlanRecommendation]) -> list[dict[str, Any]]:
    return [asdict(recommendation) for recommendation in recommendations]
