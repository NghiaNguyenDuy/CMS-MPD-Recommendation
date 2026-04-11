from __future__ import annotations

import logging
import math
import re
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
INITIAL_COVERAGE_LIMIT = 5030.00
CATASTROPHIC_TROOP_THRESHOLD = 8000.00
COVERAGE_GAP_GENERIC_COINSURANCE = 0.25
COVERAGE_GAP_BRAND_COINSURANCE = 0.25
BENEFIT_DESIGN_2025 = "2025_redesign"
BENEFIT_DESIGN_2024 = "2024_standard"
NETWORK_PRIORITY = {
    "adequate": 0,
    "limited_preferred_retail": 1,
    "no_preferred_retail": 2,
    "unknown": 3,
}
FEATURE_VERSION = "research_v4"
SIMULATION_POLICY = "cost_realism_v1"
CHANNEL_NEAR_TIE_TOLERANCE = 1.0
CHANNEL_ORDER = ("pref_retail", "nonpref_retail", "pref_mail", "nonpref_mail")
AUTO_SELECT_SCORE_MARGIN = 20.0
SCENARIO_LOW_UTILIZER = "low_utilizer"
SCENARIO_MAINTENANCE_GENERIC = "maintenance_generic"
SCENARIO_INSULIN_CHRONIC = "insulin_chronic"
SCENARIO_SPECIALTY_HIGH_COST = "specialty_high_cost"
SCENARIO_MIXED_RESTRICTION = "mixed_restriction"
SCENARIO_ACCESS_SENSITIVE = "access_sensitive"
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
    "unknown": 40.0,
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
class DrugResolutionCandidate:
    drug_name: str
    rxcui: str
    ndc: str
    match_source: str
    match_confidence: str
    score: float
    local_plan_coverage: int
    available_day_supply_options: list[int]
    available_tier_family_options: list[str]
    is_insulin: bool


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
    sequence_index: int
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
    total_drug_spending_before: float = 0.0
    total_drug_spending_after: float = 0.0
    coverage_gap_exposure: float = 0.0
    troop_before: float = 0.0
    troop_after: float = 0.0
    benefit_design: str = BENEFIT_DESIGN_2025


@dataclass(slots=True)
class FillCostResult:
    total_oop: float
    base_oop: float
    lis_adjusted_oop: float
    deductible_exposure: float
    initial_coverage_oop: float
    coverage_gap_oop: float
    catastrophic_oop: float
    negotiated_price: float
    coverage_phase: str
    pricing_status: str
    deductible_before: float
    deductible_after: float
    oop_before: float
    oop_after: float
    oop_cap_applied: bool
    total_drug_spending_before: float = 0.0
    total_drug_spending_after: float = 0.0
    troop_before: float = 0.0
    troop_after: float = 0.0
    benefit_design: str = BENEFIT_DESIGN_2025


@dataclass(slots=True)
class ScheduledFillEvent:
    medication_id: str
    fill_number: int
    day_offset: int
    deductible_applicable: bool
    negotiated_price_proxy: float
    available_channels: tuple[str, ...]
    medication: dict[str, Any]
    basis: dict[str, Any]


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
    coverage_gap_oop: float
    catastrophic_oop: float
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
    scenario_profile: str
    match_review_required: bool
    unsafe_reasons: list[str]
    feature_version: str
    drug_breakdowns: list[PlanDrugBreakdown]
    contract_year: int | None = None
    benefit_design: str = BENEFIT_DESIGN_2025
    priced_drug_count: int = 0
    channel_switch_count: int = 0
    simulation_policy: str = SIMULATION_POLICY


@dataclass(slots=True)
class RecommendationBundleSummary:
    requested_drug_count: int
    local_candidate_plan_count: int
    local_full_coverage_count: int
    local_partial_count: int
    fallback_reason: str
    scenario_profile: str = SCENARIO_LOW_UTILIZER
    candidate_plan_count_service_area: int = 0
    candidate_plan_count_ranked: int = 0
    plans_with_unknown_network_count: int = 0


@dataclass(slots=True)
class BlockedMedication:
    medication_id: str
    requested_drug_name: str | None
    resolved_drug_name: str
    ndc: str
    rxcui: str
    local_coverable_plan_count: int
    blocker_type: str


@dataclass(slots=True)
class AlternativeSearchTerm:
    medication_id: str
    requested_drug_name: str | None
    resolved_drug_name: str
    search_term: str


@dataclass(slots=True)
class RecommendationBundle:
    summary: RecommendationBundleSummary
    full_coverage_plans: list[PlanRecommendation]
    partial_fallback_plans: list[PlanRecommendation]
    comparison_only_plans: list[PlanRecommendation]
    blocked_medications: list[BlockedMedication]
    alternative_search_terms: list[AlternativeSearchTerm]


@dataclass(slots=True)
class DrugReferenceCache:
    rows: list[dict[str, Any]]
    by_ndc: dict[str, list[dict[str, Any]]]
    by_rxcui: dict[str, list[dict[str, Any]]]


@dataclass(slots=True)
class RecommendationQueryContext:
    candidate_plans: pd.DataFrame | None = None
    channel_df: pd.DataFrame | None = None
    nearest_distances: dict[str, float | None] | None = None
    basis_df: pd.DataFrame | None = None
    reference_cache: DrugReferenceCache | None = None
    local_drug_metadata: dict[str, dict[str, Any]] | None = None
    defaults_specific_lookup: dict[tuple[str, int, str], dict[str, Any]] | None = None
    defaults_fallback_lookup: dict[tuple[int, str], dict[str, Any]] | None = None
    tier_lookup: dict[tuple[str, int], str] | None = None


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


def _coerce_contract_year(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _snapshot_contract_year(config: PipelineConfig | None) -> int | None:
    active_config = config or PipelineConfig()
    try:
        return int(str(active_config.snapshot_quarter).split('-', 1)[0])
    except (TypeError, ValueError):
        return None


def _resolve_plan_benefit_design(
    contract_year: int | None, config: PipelineConfig | None
) -> tuple[int | None, str]:
    active_config = config or PipelineConfig()
    mode = active_config.benefit_design_mode
    effective_year = contract_year or _snapshot_contract_year(active_config)
    if mode == BENEFIT_DESIGN_2024:
        return effective_year or 2024, BENEFIT_DESIGN_2024
    if mode == BENEFIT_DESIGN_2025:
        return effective_year or 2025, BENEFIT_DESIGN_2025
    if effective_year is not None and effective_year <= 2024:
        return effective_year, BENEFIT_DESIGN_2024
    return effective_year or 2025, BENEFIT_DESIGN_2025


def _connect(config: PipelineConfig | None) -> duckdb.DuckDBPyConnection:
    active_config = config or PipelineConfig()
    return duckdb.connect(str(active_config.db_path), read_only=True)


def _fetch_dataframe(
    conn: duckdb.DuckDBPyConnection, query: str, params: list[Any] | None = None
) -> pd.DataFrame:
    if params:
        return conn.execute(query, params).fetch_df()
    return conn.execute(query).fetch_df()


def _table_has_column(
    conn: duckdb.DuckDBPyConnection,
    table_schema: str,
    table_name: str,
    column_name: str,
) -> bool:
    result = conn.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = ?
          AND table_name = ?
          AND column_name = ?
        LIMIT 1
        """,
        [table_schema, table_name, column_name],
    ).fetchone()
    return result is not None


def _candidate_plan_query(conn: duckdb.DuckDBPyConnection) -> str:
    contract_year_select = (
        "ps.contract_year AS contract_year"
        if _table_has_column(conn, "gold", "plan_summary", "contract_year")
        else "CAST(NULL AS INTEGER) AS contract_year"
    )
    return f"""
        SELECT DISTINCT
            psa.plan_key,
            ps.plan_name,
            {contract_year_select},
            ps.annual_premium,
            ps.deductible,
            coalesce(pns.network_flag, 'unknown') AS network_flag
        FROM gold.plan_service_area psa
        JOIN gold.plan_summary ps ON psa.plan_key = ps.plan_key
        LEFT JOIN gold.plan_network_summary pns ON psa.plan_key = pns.plan_key
        WHERE psa.zip_code = ?
        ORDER BY ps.plan_name
        """


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
    if network_flag == "unknown":
        return "Preferred retail pharmacy data is incomplete for this plan."
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
    if recommendation.channel_switch_count == 0 and recommendation.mail_order_dependency_count == 0:
        _append_unique(strengths, "The projected fill path is stable and does not depend on mail order.")
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
    if recommendation.network_flag == "unknown":
        _append_unique(
            watchouts,
            "Pharmacy network data is incomplete for this plan and should be verified before enrollment.",
        )
    if recommendation.nearest_preferred_distance_miles is not None and recommendation.nearest_preferred_distance_miles > 15:
        _append_unique(
            watchouts,
            f"Nearest preferred retail pharmacy is about {recommendation.nearest_preferred_distance_miles:.1f} miles away.",
        )
    if recommendation.channel_switch_count > 0:
        _append_unique(
            watchouts,
            f"The projected yearly fill path switches pharmacy channels {recommendation.channel_switch_count} time(s).",
        )
    if recommendation.match_review_required or approximate_match_count > 0:
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


def _normalize_drug_search_text(value: str | None) -> str:
    cleaned = re.sub(r"\[[^\]]*\]", " ", str(value or "").lower())
    cleaned = re.sub(r"[^a-z0-9\s/-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    tokens: list[str] = []
    for token in cleaned.split():
        if any(char.isdigit() for char in token):
            break
        tokens.append(token)
    return " ".join(tokens).strip() or cleaned


def _canonical_drug_reference_frame(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    return _fetch_dataframe(
        conn,
        """
        WITH reference_rows AS (
            SELECT
                ndc,
                rxcui,
                preferred_name,
                coalesce(synonym, '') AS synonym,
                is_insulin,
                0 AS source_rank
            FROM silver.dim_drug_reference
            WHERE ndc IS NOT NULL
              AND trim(coalesce(preferred_name, synonym, '')) <> ''

            UNION ALL

            SELECT DISTINCT
                ndc,
                rxcui,
                drug_name AS preferred_name,
                coalesce(drug_name, '') AS synonym,
                is_insulin,
                1 AS source_rank
            FROM gold.plan_drug_cost_basis
            WHERE ndc IS NOT NULL
              AND trim(coalesce(drug_name, '')) <> ''
        ),
        ranked AS (
            SELECT
                ndc,
                rxcui,
                preferred_name,
                synonym,
                is_insulin,
                row_number() OVER (
                    PARTITION BY ndc
                    ORDER BY source_rank, length(coalesce(preferred_name, synonym, ndc)), coalesce(preferred_name, synonym, ndc)
                ) AS rn
            FROM reference_rows
        )
        SELECT ndc, rxcui, preferred_name, synonym, is_insulin
        FROM ranked
        WHERE rn = 1
        """
    )


def build_drug_reference_cache(conn: duckdb.DuckDBPyConnection) -> DrugReferenceCache:
    frame = _canonical_drug_reference_frame(conn)
    rows: list[dict[str, Any]] = []
    by_ndc: dict[str, list[dict[str, Any]]] = {}
    by_rxcui: dict[str, list[dict[str, Any]]] = {}
    for row in frame.to_dict("records"):
        candidate_row = dict(row)
        candidate_row["preferred_name_lower"] = str(candidate_row.get("preferred_name") or "").strip().lower()
        candidate_row["synonym_lower"] = str(candidate_row.get("synonym") or "").strip().lower()
        candidate_row["normalized_name"] = _normalize_drug_search_text(candidate_row.get("preferred_name"))
        candidate_row["normalized_synonym"] = _normalize_drug_search_text(candidate_row.get("synonym"))
        rows.append(candidate_row)
        ndc = str(candidate_row.get("ndc") or "")
        rxcui = str(candidate_row.get("rxcui") or "")
        by_ndc.setdefault(ndc, []).append(candidate_row)
        by_rxcui.setdefault(rxcui, []).append(candidate_row)
    return DrugReferenceCache(rows=rows, by_ndc=by_ndc, by_rxcui=by_rxcui)


def fetch_candidate_plans(
    conn: duckdb.DuckDBPyConnection,
    zipcode: str,
) -> pd.DataFrame:
    return _fetch_dataframe(conn, _candidate_plan_query(conn), [zipcode])


def fetch_basis_rows(
    conn: duckdb.DuckDBPyConnection,
    plan_keys: list[str],
    ndcs: list[str],
) -> pd.DataFrame:
    if not plan_keys or not ndcs:
        return pd.DataFrame()
    placeholders = ", ".join("?" for _ in plan_keys)
    ndc_placeholders = ", ".join("?" for _ in ndcs)
    return _fetch_dataframe(
        conn,
        f"""
        SELECT *
        FROM gold.plan_drug_cost_basis
        WHERE plan_key IN ({placeholders})
          AND ndc IN ({ndc_placeholders})
        """,
        plan_keys + ndcs,
    )


def fetch_channel_summaries(
    conn: duckdb.DuckDBPyConnection,
    plan_keys: list[str],
) -> pd.DataFrame:
    if not plan_keys:
        return pd.DataFrame()
    placeholders = ", ".join("?" for _ in plan_keys)
    return _fetch_dataframe(
        conn,
        f"SELECT * FROM gold.plan_channel_summary WHERE plan_key IN ({placeholders})",
        plan_keys,
    )


def build_local_drug_metadata_from_basis(
    basis_df: pd.DataFrame,
) -> dict[str, dict[str, Any]]:
    if basis_df.empty:
        return {}
    lookup: dict[str, dict[str, Any]] = {}
    for ndc, group in basis_df.groupby("ndc", dropna=False):
        ndc_key = str(ndc or "")
        day_supply_options = sorted(
            {
                int(float(value))
                for value in group["days_supply"].dropna().tolist()
            }
        )
        tier_options = sorted(
            {
                str(value)
                for value in group["tier_family"].dropna().tolist()
            }
        )
        lookup[ndc_key] = {
            "local_plan_coverage": int(group["plan_key"].dropna().astype(str).nunique()),
            "available_day_supply_options": day_supply_options,
            "available_tier_family_options": tier_options,
            "is_insulin": bool(group["is_insulin"].fillna(False).astype(bool).any()),
        }
    return lookup


def build_default_input_lookups(
    conn: duckdb.DuckDBPyConnection,
) -> tuple[dict[tuple[str, int, str], dict[str, Any]], dict[tuple[int, str], dict[str, Any]]]:
    defaults_df = _fetch_dataframe(
        conn,
        """
        SELECT *
        FROM gold.drug_input_defaults
        ORDER BY is_fallback, observation_count DESC, ndc, days_supply, tier_family
        """,
    )
    specific_lookup: dict[tuple[str, int, str], dict[str, Any]] = {}
    fallback_lookup: dict[tuple[int, str], dict[str, Any]] = {}
    for row in defaults_df.to_dict("records"):
        days_supply = int(row.get("days_supply") or 30)
        tier_family = str(row.get("tier_family") or "brand")
        if bool(row.get("is_fallback")):
            fallback_lookup.setdefault((days_supply, tier_family), row)
            continue
        ndc = str(row.get("ndc") or "")
        if ndc:
            specific_lookup.setdefault((ndc, days_supply, tier_family), row)
    return specific_lookup, fallback_lookup


def build_tier_lookup(
    conn: duckdb.DuckDBPyConnection,
) -> dict[tuple[str, int], str]:
    tier_df = _fetch_dataframe(
        conn,
        """
        WITH ranked AS (
            SELECT
                ndc,
                days_supply,
                tier_family,
                count(*) AS match_count,
                row_number() OVER (
                    PARTITION BY ndc, days_supply
                    ORDER BY count(*) DESC, tier_family
                ) AS rn
            FROM gold.plan_drug_cost_basis
            WHERE ndc IS NOT NULL
              AND days_supply IS NOT NULL
              AND tier_family IS NOT NULL
            GROUP BY 1, 2, 3
        )
        SELECT ndc, days_supply, tier_family
        FROM ranked
        WHERE rn = 1
        """,
    )
    return {
        (str(row["ndc"]), int(row["days_supply"])): str(row["tier_family"])
        for row in tier_df.to_dict("records")
    }


def _candidate_local_metadata(
    conn: duckdb.DuckDBPyConnection,
    ndcs: list[str],
    plan_keys: list[str],
) -> dict[str, dict[str, Any]]:
    if not ndcs or not plan_keys:
        return {}
    ndc_placeholders = ", ".join("?" for _ in ndcs)
    plan_placeholders = ", ".join("?" for _ in plan_keys)
    df = _fetch_dataframe(
        conn,
        f"""
        SELECT
            ndc,
            count(DISTINCT plan_key) AS local_plan_coverage,
            list(DISTINCT days_supply) FILTER (WHERE days_supply IS NOT NULL) AS available_day_supply_options,
            list(DISTINCT tier_family) FILTER (WHERE tier_family IS NOT NULL) AS available_tier_family_options,
            max(CASE WHEN is_insulin THEN 1 ELSE 0 END) AS is_insulin
        FROM gold.plan_drug_cost_basis
        WHERE ndc IN ({ndc_placeholders})
          AND plan_key IN ({plan_placeholders})
        GROUP BY 1
        """,
        ndcs + plan_keys,
    )
    lookup: dict[str, dict[str, Any]] = {}
    def _as_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            return [value]
        if hasattr(value, "tolist"):
            converted = value.tolist()
            return converted if isinstance(converted, list) else [converted]
        try:
            return list(value)
        except TypeError:
            return [value]

    for row in df.to_dict("records"):
        raw_day_supply_options = _as_list(row.get("available_day_supply_options"))
        day_supply_options = sorted(
            {
                int(float(value))
                for value in raw_day_supply_options
                if value is not None and not pd.isna(value)
            }
        )
        raw_tier_family_options = _as_list(row.get("available_tier_family_options"))
        tier_family_options = sorted(
            {
                str(value)
                for value in raw_tier_family_options
                if value not in {None, ""}
            }
        )
        lookup[str(row["ndc"])] = {
            "local_plan_coverage": int(row.get("local_plan_coverage") or 0),
            "available_day_supply_options": day_supply_options,
            "available_tier_family_options": tier_family_options,
            "is_insulin": bool(row.get("is_insulin")),
        }
    return lookup


def _score_drug_candidate(
    medication: MedicationInput,
    candidate_row: dict[str, Any],
    requested_day_supply: int,
) -> tuple[float, str, str] | None:
    requested_ndc = str(medication.ndc).strip().zfill(11) if medication.ndc else ""
    requested_rxcui = str(medication.rxcui or "").strip()
    requested_name = str(medication.drug_name or "").strip().lower()
    requested_normalized = _normalize_drug_search_text(medication.drug_name)
    requested_tokens = [token for token in requested_normalized.split() if token]
    drug_name = str(candidate_row["preferred_name"])
    synonym = str(candidate_row.get("synonym") or "")
    normalized_name = str(candidate_row.get("normalized_name") or _normalize_drug_search_text(drug_name))
    normalized_synonym = str(candidate_row.get("normalized_synonym") or _normalize_drug_search_text(synonym))
    exact_name = str(candidate_row.get("preferred_name_lower") or drug_name.strip().lower())
    exact_synonym = str(candidate_row.get("synonym_lower") or synonym.strip().lower())

    if requested_ndc:
        if str(candidate_row["ndc"]) != requested_ndc:
            return None
        base_score = 100.0
        match_source = "ndc"
        match_confidence = "exact"
    elif requested_rxcui:
        if str(candidate_row["rxcui"]) != requested_rxcui:
            return None
        base_score = 95.0
        match_source = "rxcui"
        match_confidence = "exact"
    elif requested_name:
        if exact_name == requested_name:
            base_score = 85.0
            match_source = "exact_name"
            match_confidence = "exact"
        elif exact_synonym == requested_name:
            base_score = 80.0
            match_source = "synonym"
            match_confidence = "exact"
        elif requested_normalized and (
            normalized_name == requested_normalized
            or normalized_synonym == requested_normalized
            or normalized_name.startswith(requested_normalized)
            or normalized_synonym.startswith(requested_normalized)
        ):
            base_score = 65.0
            match_source = "normalized_name"
            match_confidence = "approximate"
        elif requested_tokens and all(
            token in f"{normalized_name} {normalized_synonym}" for token in requested_tokens
        ):
            base_score = 50.0
            match_source = "prefix_match"
            match_confidence = "approximate"
        elif requested_tokens and any(
            text.startswith(requested_tokens[0]) for text in (normalized_name, normalized_synonym) if text
        ):
            base_score = 50.0
            match_source = "prefix_match"
            match_confidence = "approximate"
        else:
            return None
    else:
        return None

    local_plan_coverage = int(candidate_row.get("local_plan_coverage") or 0)
    available_day_supply_options = [
        int(value) for value in (candidate_row.get("available_day_supply_options") or []) if value is not None
    ]
    score = base_score + 0.01 * local_plan_coverage
    if requested_day_supply in available_day_supply_options:
        score += 5.0
    return score, match_source, match_confidence


def resolve_drug_candidates(
    conn: duckdb.DuckDBPyConnection,
    medication: MedicationInput,
    plan_keys: list[str],
    *,
    day_supply: int,
    limit: int = 10,
    reference_cache: DrugReferenceCache | None = None,
    local_metadata_lookup: dict[str, dict[str, Any]] | None = None,
) -> list[DrugResolutionCandidate]:
    cache = reference_cache or build_drug_reference_cache(conn)
    if not cache.rows:
        return []
    if medication.ndc:
        candidate_rows = cache.by_ndc.get(str(medication.ndc).strip().zfill(11), [])
    elif medication.rxcui:
        candidate_rows = cache.by_rxcui.get(str(medication.rxcui or "").strip(), [])
    else:
        candidate_rows = cache.rows
    matched_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        if _score_drug_candidate(medication, row, day_supply) is not None:
            matched_rows.append(dict(row))
    if not matched_rows:
        return []
    metadata_lookup = dict(local_metadata_lookup or {})
    missing_ndcs = sorted({str(row["ndc"]) for row in matched_rows if str(row["ndc"]) not in metadata_lookup})
    if missing_ndcs:
        metadata_lookup.update(
            _candidate_local_metadata(
                conn,
                missing_ndcs,
                plan_keys,
            )
        )
    candidates: list[DrugResolutionCandidate] = []
    for row in matched_rows:
        row["local_plan_coverage"] = metadata_lookup.get(str(row["ndc"]), {}).get("local_plan_coverage", 0)
        row["available_day_supply_options"] = metadata_lookup.get(str(row["ndc"]), {}).get(
            "available_day_supply_options",
            [],
        )
        row["available_tier_family_options"] = metadata_lookup.get(str(row["ndc"]), {}).get(
            "available_tier_family_options",
            [],
        )
        row["is_insulin"] = metadata_lookup.get(str(row["ndc"]), {}).get("is_insulin", bool(row.get("is_insulin")))
        scored = _score_drug_candidate(medication, row, day_supply)
        if scored is None:
            continue
        score, match_source, match_confidence = scored
        candidates.append(
            DrugResolutionCandidate(
                drug_name=str(row["preferred_name"]),
                rxcui=str(row["rxcui"]),
                ndc=str(row["ndc"]),
                match_source=match_source,
                match_confidence=match_confidence,
                score=round(score, 2),
                local_plan_coverage=int(row.get("local_plan_coverage") or 0),
                available_day_supply_options=list(row.get("available_day_supply_options") or []),
                available_tier_family_options=list(row.get("available_tier_family_options") or []),
                is_insulin=bool(row.get("is_insulin")),
            )
        )
    deduped: dict[str, DrugResolutionCandidate] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (
            -float(item.score),
            -int(item.local_plan_coverage),
            item.drug_name,
            item.ndc,
        ),
    ):
        deduped.setdefault(candidate.ndc, candidate)
    return list(deduped.values())[: max(1, limit)]


def select_drug_candidate(
    medication: MedicationInput,
    candidates: list[DrugResolutionCandidate],
) -> tuple[DrugResolutionCandidate | None, bool]:
    if not candidates:
        return None, False
    if medication.ndc or medication.rxcui:
        return candidates[0], False
    if len(candidates) == 1:
        return candidates[0], False
    if float(candidates[0].score) - float(candidates[1].score) >= AUTO_SELECT_SCORE_MARGIN:
        return candidates[0], False
    return None, True


def _resolve_defaults(
    conn: duckdb.DuckDBPyConnection,
    ndc: str,
    day_supply: int,
    tier_family: str,
    *,
    specific_lookup: dict[tuple[str, int, str], dict[str, Any]] | None = None,
    fallback_lookup: dict[tuple[int, str], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if specific_lookup is not None:
        specific = specific_lookup.get((ndc, day_supply, tier_family))
        if specific is not None:
            return specific
    if fallback_lookup is not None:
        fallback = fallback_lookup.get((day_supply, tier_family))
        if fallback is not None:
            return fallback
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
    conn: duckdb.DuckDBPyConnection,
    ndc: str,
    day_supply: int,
    declared_tier_family: str | None,
    *,
    tier_lookup: dict[tuple[str, int], str] | None = None,
) -> str:
    if declared_tier_family:
        return declared_tier_family.lower()
    if tier_lookup is not None:
        cached = tier_lookup.get((ndc, day_supply))
        if cached:
            return str(cached)
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


def _preferred_channel_rank(channel: str) -> int:
    return 0 if channel in {"pref_retail", "pref_mail"} else 1


def _channel_family_rank(channel: str, pharmacy_preference: str) -> int:
    if pharmacy_preference == "retail":
        return 0 if "retail" in channel else 1
    if pharmacy_preference == "mail":
        return 0 if "mail" in channel else 1
    return 0


def _available_channels(channel_summary: dict[str, Any], pharmacy_preference: str) -> tuple[str, ...]:
    return tuple(
        channel
        for channel in CHANNEL_ORDER
        if _channel_available(channel_summary, channel, pharmacy_preference)
    )


def _estimate_channel_negotiated_price(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    channel: str,
    quantity: float,
) -> float | None:
    unit_cost = basis.get("unit_cost")
    if unit_cost is None or pd.isna(unit_cost):
        return None
    fee = _select_fee(channel_summary, channel, str(basis["tier_family"]), int(basis["days_supply"]))
    if fee is None:
        return None
    return max(float(unit_cost) * float(quantity) + fee, _select_floor(channel_summary, channel))


def _estimate_negotiated_price_proxy(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    quantity: float,
    available_channels: tuple[str, ...],
) -> float:
    estimates = [
        estimate
        for channel in available_channels
        if (estimate := _estimate_channel_negotiated_price(basis, channel_summary, channel, quantity)) is not None
    ]
    if not estimates:
        return 0.0
    return min(estimates)


def _build_scheduled_fill_events(
    medication: dict[str, Any],
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    pharmacy_preference: str,
) -> list[ScheduledFillEvent]:
    available_channels = _available_channels(channel_summary, pharmacy_preference)
    negotiated_price_proxy = _estimate_negotiated_price_proxy(
        basis,
        channel_summary,
        float(medication["quantity"]),
        available_channels,
    )
    fills_per_year = max(1, int(medication["fills_per_year"]))
    interval = 365.0 / fills_per_year
    deductible_applicable = bool(basis.get("deductible_applies"))
    return [
        ScheduledFillEvent(
            medication_id=str(medication["medication_id"]),
            fill_number=fill_index + 1,
            day_offset=int(round(fill_index * interval)),
            deductible_applicable=deductible_applicable,
            negotiated_price_proxy=negotiated_price_proxy,
            available_channels=available_channels,
            medication=medication,
            basis=basis,
        )
        for fill_index in range(fills_per_year)
    ]


def _scheduled_fill_sort_key(event: ScheduledFillEvent) -> tuple[Any, ...]:
    return (
        event.day_offset,
        0 if event.deductible_applicable else 1,
        -event.negotiated_price_proxy,
        event.medication_id,
        event.fill_number,
    )


def _select_best_channel_result(
    channel_results: list[tuple[str, FillCostResult]],
    previous_channel: str | None,
    pharmacy_preference: str,
) -> tuple[str | None, FillCostResult | None]:
    if not channel_results:
        return None, None

    lowest_oop = min(result.total_oop for _, result in channel_results)
    near_ties = [
        (channel, result)
        for channel, result in channel_results
        if result.total_oop <= lowest_oop + CHANNEL_NEAR_TIE_TOLERANCE + 1e-9
    ]
    if previous_channel:
        for channel, result in near_ties:
            if channel == previous_channel:
                return channel, result

    ordered = sorted(
        near_ties,
        key=lambda item: (
            _preferred_channel_rank(item[0]),
            _channel_family_rank(item[0], pharmacy_preference),
            item[1].total_oop,
            item[0],
        ),
    )
    return ordered[0]


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


def _compute_coverage_gap_cost(
    negotiated: float, tier_family: str
) -> float:
    """Compute beneficiary cost-sharing in the 2024 coverage gap."""
    coinsurance = (
        COVERAGE_GAP_GENERIC_COINSURANCE
        if tier_family == "generic"
        else COVERAGE_GAP_BRAND_COINSURANCE
    )
    return negotiated * coinsurance


def _compute_catastrophic_cost(
    negotiated: float, tier_family: str
) -> float:
    """Catastrophic beneficiary liability is modeled as $0 in 2024 mode."""
    return 0.0


def _scale_segment_cost(total_cost: float | None, segment_negotiated: float, negotiated_total: float) -> float | None:
    if total_cost is None:
        return None
    if segment_negotiated <= 0 or negotiated_total <= 0:
        return 0.0
    scaled = float(total_cost) * (segment_negotiated / negotiated_total)
    return min(segment_negotiated, max(0.0, scaled))


def _initial_phase_component(
    basis: dict[str, Any],
    negotiated_total: float,
    segment_negotiated: float,
    remaining_deductible: float,
    channel_prefix: str,
    insulin_prefix: str,
) -> tuple[float | None, float, float, float, str]:
    if segment_negotiated <= 0:
        return 0.0, 0.0, 0.0, remaining_deductible, "initial_coverage_rule"

    deductible_before = max(0.0, remaining_deductible)
    if bool(basis["is_insulin"]):
        insulin_value = basis.get(f"insulin_{insulin_prefix}_copay")
        if insulin_value is not None and not pd.isna(insulin_value):
            total_cost = min(float(insulin_value), negotiated_total)
            coverage_phase = "insulin_override"
        else:
            total_cost = _apply_cost_rule(
                negotiated_total,
                basis.get(f"init_{channel_prefix}_cost_type"),
                basis.get(f"init_{channel_prefix}_cost_amt"),
                basis.get(f"init_{channel_prefix}_cost_min"),
                basis.get(f"init_{channel_prefix}_cost_max"),
            )
            coverage_phase = "insulin_initial_coverage_rule"
        segment_cost = _scale_segment_cost(total_cost, segment_negotiated, negotiated_total)
        return segment_cost, 0.0, segment_cost or 0.0, deductible_before, coverage_phase

    init_cost = _apply_cost_rule(
        negotiated_total,
        basis.get(f"init_{channel_prefix}_cost_type"),
        basis.get(f"init_{channel_prefix}_cost_amt"),
        basis.get(f"init_{channel_prefix}_cost_min"),
        basis.get(f"init_{channel_prefix}_cost_max"),
    )
    pre_cost = _apply_cost_rule(
        negotiated_total,
        basis.get(f"pre_{channel_prefix}_cost_type"),
        basis.get(f"pre_{channel_prefix}_cost_amt"),
        basis.get(f"pre_{channel_prefix}_cost_min"),
        basis.get(f"pre_{channel_prefix}_cost_max"),
    )

    if deductible_before > 0 and bool(basis["deductible_applies"]):
        deductible_exposure = min(segment_negotiated, deductible_before)
        deductible_after = max(0.0, deductible_before - deductible_exposure)
        covered_remainder = max(segment_negotiated - deductible_exposure, 0.0)
        remainder_oop = 0.0
        if covered_remainder > 0 and init_cost is not None:
            scaled_init_cost = _scale_segment_cost(init_cost, covered_remainder, negotiated_total)
            remainder_oop = min(covered_remainder, scaled_init_cost or 0.0)
        base_cost = deductible_exposure + remainder_oop
        coverage_phase = (
            "deductible_then_initial_coverage" if covered_remainder > 0 else "deductible_only"
        )
        return base_cost, deductible_exposure, remainder_oop, deductible_after, coverage_phase

    rule_cost = pre_cost if deductible_before > 0 and pre_cost is not None else init_cost
    if rule_cost is None:
        return None, 0.0, 0.0, deductible_before, ""
    segment_cost = _scale_segment_cost(rule_cost, segment_negotiated, negotiated_total)
    coverage_phase = "predeductible_rule" if deductible_before > 0 and pre_cost is not None else "initial_coverage_rule"
    return segment_cost, 0.0, segment_cost or 0.0, deductible_before, coverage_phase


def _simulate_fill_cost_2025(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    channel: str,
    quantity: float,
    remaining_deductible: float,
    oop_accumulated: float,
    lis_status: str,
    total_drug_spending_accumulated: float = 0.0,
) -> FillCostResult | None:
    fee = _select_fee(channel_summary, channel, str(basis["tier_family"]), int(basis["days_supply"]))
    if fee is None or basis["unit_cost"] is None or pd.isna(basis["unit_cost"]):
        return None

    negotiated = max(float(basis["unit_cost"]) * quantity + fee, _select_floor(channel_summary, channel))
    channel_prefix, insulin_prefix = _channel_fields(channel)
    deductible_before = max(0.0, remaining_deductible)
    oop_before = max(0.0, oop_accumulated)
    tds_before = max(0.0, total_drug_spending_accumulated)
    tier_family = str(basis["tier_family"])

    base_cost, deductible_exposure, initial_coverage_oop, deductible_after, coverage_phase = _initial_phase_component(
        basis,
        negotiated,
        negotiated,
        deductible_before,
        channel_prefix,
        insulin_prefix,
    )
    if base_cost is None:
        return None

    lis_adjusted_cost = _apply_lis_adjustment(base_cost, tier_family, lis_status)
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
        coverage_gap_oop=0.0,
        catastrophic_oop=0.0,
        negotiated_price=negotiated,
        coverage_phase=coverage_phase,
        pricing_status="priced",
        deductible_before=deductible_before,
        deductible_after=deductible_after,
        oop_before=oop_before,
        oop_after=oop_before + final_cost,
        oop_cap_applied=oop_cap_applied,
        total_drug_spending_before=tds_before,
        total_drug_spending_after=tds_before + negotiated,
        troop_before=oop_before,
        troop_after=oop_before + final_cost,
        benefit_design=BENEFIT_DESIGN_2025,
    )


def _simulate_fill_cost_2024(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    channel: str,
    quantity: float,
    remaining_deductible: float,
    oop_accumulated: float,
    lis_status: str,
    total_drug_spending_accumulated: float = 0.0,
    troop_accumulated: float = 0.0,
) -> FillCostResult | None:
    fee = _select_fee(channel_summary, channel, str(basis["tier_family"]), int(basis["days_supply"]))
    if fee is None or basis["unit_cost"] is None or pd.isna(basis["unit_cost"]):
        return None

    negotiated = max(float(basis["unit_cost"]) * quantity + fee, _select_floor(channel_summary, channel))
    channel_prefix, insulin_prefix = _channel_fields(channel)
    deductible_before = max(0.0, remaining_deductible)
    oop_before = max(0.0, oop_accumulated)
    troop_before = max(0.0, troop_accumulated)
    tds_before = max(0.0, total_drug_spending_accumulated)
    tds_after = tds_before + negotiated
    tier_family = str(basis["tier_family"])

    if troop_before >= CATASTROPHIC_TROOP_THRESHOLD:
        return FillCostResult(
            total_oop=0.0,
            base_oop=0.0,
            lis_adjusted_oop=0.0,
            deductible_exposure=0.0,
            initial_coverage_oop=0.0,
            coverage_gap_oop=0.0,
            catastrophic_oop=0.0,
            negotiated_price=negotiated,
            coverage_phase="catastrophic",
            pricing_status="priced",
            deductible_before=deductible_before,
            deductible_after=deductible_before,
            oop_before=oop_before,
            oop_after=oop_before,
            oop_cap_applied=False,
            total_drug_spending_before=tds_before,
            total_drug_spending_after=tds_after,
            troop_before=troop_before,
            troop_after=troop_before,
            benefit_design=BENEFIT_DESIGN_2024,
        )

    initial_segment_negotiated = 0.0
    if tds_before < INITIAL_COVERAGE_LIMIT:
        initial_segment_negotiated = min(negotiated, max(0.0, INITIAL_COVERAGE_LIMIT - tds_before))
    remaining_negotiated = max(0.0, negotiated - initial_segment_negotiated)

    base_cost = 0.0
    deductible_exposure = 0.0
    initial_coverage_oop = 0.0
    deductible_after = deductible_before
    initial_phase = ""
    if initial_segment_negotiated > 0:
        initial_cost, deductible_exposure, initial_coverage_oop, deductible_after, initial_phase = _initial_phase_component(
            basis,
            negotiated,
            initial_segment_negotiated,
            deductible_before,
            channel_prefix,
            insulin_prefix,
        )
        if initial_cost is None:
            return None
        base_cost += initial_cost

    gap_full_cost = 0.0
    coverage_gap_oop = 0.0
    catastrophic_oop = 0.0
    entered_catastrophic = False
    if remaining_negotiated > 0:
        gap_full_cost = _compute_coverage_gap_cost(remaining_negotiated, tier_family)
        remaining_troop = max(0.0, CATASTROPHIC_TROOP_THRESHOLD - (troop_before + base_cost))
        coverage_gap_oop = min(gap_full_cost, remaining_troop)
        entered_catastrophic = gap_full_cost > coverage_gap_oop
        catastrophic_oop = _compute_catastrophic_cost(max(0.0, remaining_negotiated), tier_family) if entered_catastrophic else 0.0
        base_cost += coverage_gap_oop + catastrophic_oop

    lis_adjusted_cost = _apply_lis_adjustment(base_cost, tier_family, lis_status)
    if initial_phase:
        if remaining_negotiated <= 0:
            coverage_phase = initial_phase
        elif coverage_gap_oop > 0 and entered_catastrophic:
            coverage_phase = f"{initial_phase}_then_coverage_gap_then_catastrophic"
        elif coverage_gap_oop > 0:
            coverage_phase = f"{initial_phase}_then_coverage_gap"
        else:
            coverage_phase = f"{initial_phase}_then_catastrophic"
    else:
        if coverage_gap_oop > 0 and entered_catastrophic:
            coverage_phase = "coverage_gap_then_catastrophic"
        elif coverage_gap_oop > 0:
            coverage_phase = "coverage_gap"
        else:
            coverage_phase = "catastrophic"

    return FillCostResult(
        total_oop=max(0.0, lis_adjusted_cost),
        base_oop=max(0.0, base_cost),
        lis_adjusted_oop=max(0.0, lis_adjusted_cost),
        deductible_exposure=max(0.0, deductible_exposure),
        initial_coverage_oop=max(0.0, initial_coverage_oop),
        coverage_gap_oop=max(0.0, coverage_gap_oop),
        catastrophic_oop=max(0.0, catastrophic_oop),
        negotiated_price=negotiated,
        coverage_phase=coverage_phase,
        pricing_status="priced",
        deductible_before=deductible_before,
        deductible_after=deductible_after,
        oop_before=oop_before,
        oop_after=oop_before + max(0.0, lis_adjusted_cost),
        oop_cap_applied=False,
        total_drug_spending_before=tds_before,
        total_drug_spending_after=tds_after,
        troop_before=troop_before,
        troop_after=troop_before + max(0.0, base_cost),
        benefit_design=BENEFIT_DESIGN_2024,
    )


def _simulate_fill_cost(
    basis: dict[str, Any],
    channel_summary: dict[str, Any],
    channel: str,
    quantity: float,
    remaining_deductible: float,
    oop_accumulated: float,
    lis_status: str,
    total_drug_spending_accumulated: float = 0.0,
    *,
    benefit_design: str = BENEFIT_DESIGN_2025,
    troop_accumulated: float | None = None,
) -> FillCostResult | None:
    active_troop = max(0.0, troop_accumulated if troop_accumulated is not None else oop_accumulated)
    if benefit_design == BENEFIT_DESIGN_2024:
        return _simulate_fill_cost_2024(
            basis,
            channel_summary,
            channel,
            quantity,
            remaining_deductible,
            oop_accumulated,
            lis_status,
            total_drug_spending_accumulated=total_drug_spending_accumulated,
            troop_accumulated=active_troop,
        )
    return _simulate_fill_cost_2025(
        basis,
        channel_summary,
        channel,
        quantity,
        remaining_deductible,
        oop_accumulated,
        lis_status,
        total_drug_spending_accumulated=total_drug_spending_accumulated,
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


def _recommendation_bucket_index(recommendation: PlanRecommendation) -> int:
    requested_drug_count = max(1, len(recommendation.drug_breakdowns))
    if recommendation.coverage_status == "full" and recommendation.priced_drug_count >= requested_drug_count:
        return 0
    if recommendation.priced_drug_count > 0:
        return 1
    return 2


def _rules_ranking_sort_key(recommendation: PlanRecommendation) -> tuple[Any, ...]:
    return (
        _recommendation_bucket_index(recommendation),
        -int(recommendation.priced_drug_count),
        *_scenario_sort_values(recommendation, recommendation.scenario_profile),
        int(recommendation.uncovered_drug_count),
    )


def _requested_drug_count(recommendation: PlanRecommendation) -> int:
    return max(1, len(recommendation.drug_breakdowns))


def _covered_and_priced_count(recommendation: PlanRecommendation) -> int:
    return sum(
        1
        for item in recommendation.drug_breakdowns
        if item.coverage_status == "covered" and item.pricing_status == "priced"
    )


def _coverage_pct_requested(recommendation: PlanRecommendation) -> float:
    return round(100.0 * _covered_and_priced_count(recommendation) / _requested_drug_count(recommendation), 2)


def _is_full_coverage_plan(recommendation: PlanRecommendation) -> bool:
    return _covered_and_priced_count(recommendation) == _requested_drug_count(recommendation)


def _distance_sort_value(value: float | None) -> float:
    if value is None or pd.isna(value):
        return float("inf")
    return float(value)


def _insulin_nonpreferred_dependency_count(recommendation: PlanRecommendation) -> int:
    return sum(
        1
        for item in recommendation.drug_breakdowns
        if item.insulin_flag and item.selected_channel in {"nonpref_retail", "nonpref_mail"}
    )


def _scenario_sort_values(recommendation: PlanRecommendation, scenario_profile: str) -> tuple[Any, ...]:
    if scenario_profile == SCENARIO_SPECIALTY_HIGH_COST:
        return (
            int(recommendation.restriction_count),
            int(recommendation.channel_switch_count),
            NETWORK_PRIORITY.get(recommendation.network_flag, 99),
            _distance_sort_value(recommendation.nearest_preferred_distance_miles),
            float(recommendation.annual_total_cost),
            -float(recommendation.fit_score),
            recommendation.plan_name,
        )
    if scenario_profile == SCENARIO_INSULIN_CHRONIC:
        return (
            float(recommendation.annual_drug_oop),
            int(_insulin_nonpreferred_dependency_count(recommendation)),
            int(recommendation.channel_switch_count),
            NETWORK_PRIORITY.get(recommendation.network_flag, 99),
            _distance_sort_value(recommendation.nearest_preferred_distance_miles),
            float(recommendation.annual_total_cost),
            -float(recommendation.fit_score),
            recommendation.plan_name,
        )
    if scenario_profile == SCENARIO_ACCESS_SENSITIVE:
        return (
            NETWORK_PRIORITY.get(recommendation.network_flag, 99),
            _distance_sort_value(recommendation.nearest_preferred_distance_miles),
            float(recommendation.annual_total_cost),
            float(recommendation.annual_drug_oop),
            int(recommendation.restriction_count),
            int(recommendation.channel_switch_count),
            -float(recommendation.fit_score),
            recommendation.plan_name,
        )
    if scenario_profile == SCENARIO_MIXED_RESTRICTION:
        return (
            int(recommendation.restriction_count),
            float(recommendation.annual_total_cost),
            float(recommendation.annual_drug_oop),
            NETWORK_PRIORITY.get(recommendation.network_flag, 99),
            _distance_sort_value(recommendation.nearest_preferred_distance_miles),
            int(recommendation.channel_switch_count),
            -float(recommendation.fit_score),
            recommendation.plan_name,
        )
    if scenario_profile == SCENARIO_MAINTENANCE_GENERIC:
        return (
            float(recommendation.annual_total_cost),
            float(recommendation.annual_premium),
            float(recommendation.annual_drug_oop),
            int(recommendation.restriction_count),
            NETWORK_PRIORITY.get(recommendation.network_flag, 99),
            _distance_sort_value(recommendation.nearest_preferred_distance_miles),
            int(recommendation.channel_switch_count),
            -float(recommendation.fit_score),
            recommendation.plan_name,
        )
    return (
        float(recommendation.annual_total_cost),
        float(recommendation.annual_drug_oop),
        int(recommendation.restriction_count),
        NETWORK_PRIORITY.get(recommendation.network_flag, 99),
        _distance_sort_value(recommendation.nearest_preferred_distance_miles),
        int(recommendation.channel_switch_count),
        -float(recommendation.fit_score),
        recommendation.plan_name,
    )


def _full_coverage_compare_sort_key(recommendation: PlanRecommendation) -> tuple[Any, ...]:
    return _scenario_sort_values(recommendation, recommendation.scenario_profile)


def _local_coverable_counts(recommendations: list[PlanRecommendation]) -> dict[str, int]:
    if not recommendations:
        return {}
    requested_medications = recommendations[0].resolved_medications
    local_coverable_counts = {item.medication_id: 0 for item in requested_medications}
    for recommendation in recommendations:
        coverable_ids = {
            item.medication_id
            for item in recommendation.drug_breakdowns
            if item.coverage_status == "covered" and item.pricing_status == "priced"
        }
        for medication_id in coverable_ids:
            if medication_id in local_coverable_counts:
                local_coverable_counts[medication_id] += 1
    return local_coverable_counts


def _fallback_group(recommendation: PlanRecommendation, local_coverable_counts: dict[str, int]) -> str:
    if recommendation.network_flag == "unknown":
        return "network_unknown"
    if any(item.pricing_status == "channel_unavailable" for item in recommendation.drug_breakdowns):
        return "access_blocked"
    if any(
        local_coverable_counts.get(item.medication_id, 0) == 0
        and item.coverage_status != "covered"
        for item in recommendation.drug_breakdowns
    ):
        return "never_local_coverable"
    return "not_jointly_coverable"


def _fallback_group_index(group_name: str) -> int:
    ordering = {
        "never_local_coverable": 0,
        "not_jointly_coverable": 1,
        "access_blocked": 2,
        "network_unknown": 3,
    }
    return ordering.get(group_name, 99)


def _partial_fallback_sort_key(
    recommendation: PlanRecommendation,
    local_coverable_counts: dict[str, int] | None = None,
) -> tuple[Any, ...]:
    blocker_group = _fallback_group(recommendation, local_coverable_counts or {})
    return (
        _fallback_group_index(blocker_group),
        -float(_coverage_pct_requested(recommendation)),
        -int(recommendation.priced_drug_count),
        *_scenario_sort_values(recommendation, recommendation.scenario_profile),
    )


def _unsafe_reasons(recommendation: PlanRecommendation) -> list[str]:
    reasons: list[str] = []
    if recommendation.uncovered_drug_count > 0:
        reasons.append("uncovered_exact_drug")
    if any(item.pricing_status == "missing_price" for item in recommendation.drug_breakdowns):
        reasons.append("exact_drug_missing_price")
    if any(item.pricing_status == "channel_unavailable" for item in recommendation.drug_breakdowns):
        reasons.append("no_usable_channel")
    if recommendation.network_flag == "unknown":
        reasons.append("unknown_network_data")
    if recommendation.nearest_preferred_distance_miles is not None and recommendation.nearest_preferred_distance_miles > 15:
        reasons.append("long_preferred_distance")
    if recommendation.restriction_count >= 2:
        reasons.append("high_um_friction")
    if recommendation.match_review_required:
        reasons.append("approximate_match_unreviewed")
    return reasons


def _determine_scenario_profile(
    recommendations: list[PlanRecommendation],
    beneficiary: BeneficiaryInput,
) -> str:
    if not recommendations:
        return SCENARIO_LOW_UTILIZER
    requested_drug_count = max(1, len(recommendations[0].resolved_medications))
    resolved = recommendations[0].resolved_medications
    if any(str(item.tier_family).lower() == "specialty" for item in resolved):
        return SCENARIO_SPECIALTY_HIGH_COST

    annual_spend_by_medication: dict[str, float] = {}
    restricted_medications: set[str] = set()
    insulin_present = False
    known_distances = [
        float(item.nearest_preferred_distance_miles)
        for item in recommendations
        if item.nearest_preferred_distance_miles is not None and not pd.isna(item.nearest_preferred_distance_miles)
    ]
    for recommendation in recommendations:
        for item in recommendation.drug_breakdowns:
            annual_spend_by_medication[item.medication_id] = max(
                annual_spend_by_medication.get(item.medication_id, 0.0),
                float(item.negotiated_price_total or 0.0),
            )
            if item.pa_flag or item.st_flag or item.ql_flag:
                restricted_medications.add(item.medication_id)
            if item.insulin_flag:
                insulin_present = True
    if sum(annual_spend_by_medication.values()) >= 6000.0:
        return SCENARIO_SPECIALTY_HIGH_COST
    if any(
        annual_spend_by_medication.get(medication_id, 0.0) >= 2000.0
        for medication_id in restricted_medications
    ):
        return SCENARIO_SPECIALTY_HIGH_COST
    if insulin_present:
        return SCENARIO_INSULIN_CHRONIC
    if len(restricted_medications) >= 2:
        return SCENARIO_MIXED_RESTRICTION
    if (
        beneficiary.pharmacy_preference != "auto"
        or (known_distances and min(known_distances) > 15.0)
        or not any(item.network_flag == "adequate" for item in recommendations)
    ):
        return SCENARIO_ACCESS_SENSITIVE
    if requested_drug_count <= 3 and all(str(item.tier_family).lower() == "generic" for item in resolved):
        return SCENARIO_MAINTENANCE_GENERIC
    return SCENARIO_LOW_UTILIZER


def _apply_run_profile(
    recommendations: list[PlanRecommendation],
    beneficiary: BeneficiaryInput,
) -> str:
    scenario_profile = _determine_scenario_profile(recommendations, beneficiary)
    for recommendation in recommendations:
        recommendation.scenario_profile = scenario_profile
        recommendation.unsafe_reasons = _unsafe_reasons(recommendation)
    return scenario_profile


def _assign_plan_ranks(recommendations: list[PlanRecommendation]) -> list[PlanRecommendation]:
    for rank, recommendation in enumerate(recommendations, start=1):
        recommendation.plan_rank = rank
    return recommendations


def _derive_alternative_search_seed(drug_name: str | None) -> str:
    cleaned = re.sub(r"\[[^\]]*\]", " ", str(drug_name or "")).strip()
    cleaned = re.sub(
        r"\b(tablet|capsule|solution|suspension|inhalation|inhaler|injectable|injection|oral|extended|release|hr|actuat|powder|cream|ointment|patch|kit|pack)\b",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^A-Za-z0-9\s/-]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    tokens: list[str] = []
    for token in cleaned.split():
        if any(char.isdigit() for char in token):
            break
        tokens.append(token)
    seed = " ".join(tokens).strip()
    return seed or cleaned


def _build_blocked_medications(recommendations: list[PlanRecommendation]) -> list[BlockedMedication]:
    if not recommendations or any(_is_full_coverage_plan(item) for item in recommendations):
        return []

    requested_medications = recommendations[0].resolved_medications
    local_coverable_counts = _local_coverable_counts(recommendations)

    blocked: list[BlockedMedication] = []
    for match in requested_medications:
        local_coverable_plan_count = int(local_coverable_counts.get(match.medication_id, 0))
        blocker_type = (
            "never_local_coverable" if local_coverable_plan_count == 0 else "not_jointly_coverable"
        )
        blocked.append(
            BlockedMedication(
                medication_id=match.medication_id,
                requested_drug_name=match.requested_drug_name,
                resolved_drug_name=match.resolved_drug_name,
                ndc=match.ndc,
                rxcui=match.rxcui,
                local_coverable_plan_count=local_coverable_plan_count,
                blocker_type=blocker_type,
            )
        )
    return blocked


def _build_alternative_search_terms(
    blocked_medications: list[BlockedMedication],
) -> list[AlternativeSearchTerm]:
    search_terms: list[AlternativeSearchTerm] = []
    for item in blocked_medications:
        seed = _derive_alternative_search_seed(item.resolved_drug_name)
        if not seed:
            continue
        search_terms.append(
            AlternativeSearchTerm(
                medication_id=item.medication_id,
                requested_drug_name=item.requested_drug_name,
                resolved_drug_name=item.resolved_drug_name,
                search_term=seed,
            )
        )
    return search_terms


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
        channel_switch_count = int(recommendation.channel_switch_count)
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
            - 6.0 * channel_switch_count
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
            - 8.0 * channel_switch_count
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


def _generate_recommendations(
    beneficiary: BeneficiaryInput,
    medications: list[MedicationInput],
    config: PipelineConfig | None = None,
    ranking_mode: str = "rules",
    allow_approximate_match_ranking: bool = False,
    conn: duckdb.DuckDBPyConnection | None = None,
    query_context: RecommendationQueryContext | None = None,
) -> list[PlanRecommendation]:
    if not medications:
        raise ValueError("At least one medication is required.")

    active_config = config or PipelineConfig()
    logger.info(
        "recommendation request zipcode=%s medications=%s profile=%s",
        beneficiary.zipcode,
        len(medications),
        active_config.build_profile,
    )
    owns_connection = conn is None
    conn = conn or _connect(active_config)
    zipcode = _normalize_zipcode(beneficiary.zipcode)
    candidate_plans = (
        query_context.candidate_plans.copy()
        if query_context is not None and query_context.candidate_plans is not None
        else fetch_candidate_plans(conn, zipcode)
    )
    if candidate_plans.empty:
        if owns_connection:
            conn.close()
        logger.warning("no candidate plans found for zipcode=%s", zipcode)
        return []

    plan_keys = candidate_plans["plan_key"].tolist()
    resolved_medications: list[dict[str, Any]] = []
    matches: list[MedicationMatch] = []
    for medication_index, medication in enumerate(medications, start=1):
        medication_id = f"med_{medication_index}"
        day_supply = _normalize_days_supply(medication.day_supply)
        candidates = resolve_drug_candidates(
            conn,
            medication,
            plan_keys,
            day_supply=day_supply,
            reference_cache=query_context.reference_cache if query_context is not None else None,
            local_metadata_lookup=query_context.local_drug_metadata if query_context is not None else None,
        )
        selected_candidate, match_review_required = select_drug_candidate(medication, candidates)
        if not candidates:
            if owns_connection:
                conn.close()
            requested_value = medication.ndc or medication.rxcui or medication.drug_name or medication_id
            raise ValueError(f"Could not resolve medication input: {requested_value}")
        if selected_candidate is None:
            if allow_approximate_match_ranking:
                selected_candidate = candidates[0]
                match_review_required = True
            else:
                if owns_connection:
                    conn.close()
                preview = "; ".join(
                    f"{item.drug_name} (NDC {item.ndc}, {item.local_plan_coverage} local plans)"
                    for item in candidates[:3]
                )
                requested_value = medication.drug_name or medication.ndc or medication.rxcui or medication_id
                raise ValueError(
                    f"Medication '{requested_value}' needs manual review before ranking. "
                    f"Top candidates: {preview}. Provide an exact NDC/RXCUI or choose from the drug catalog."
                )

        tier_family = _infer_tier_family(
            conn,
            str(selected_candidate.ndc),
            day_supply,
            medication.tier_family,
            tier_lookup=query_context.tier_lookup if query_context is not None else None,
        )
        defaults = _resolve_defaults(
            conn,
            str(selected_candidate.ndc),
            day_supply,
            tier_family,
            specific_lookup=query_context.defaults_specific_lookup if query_context is not None else None,
            fallback_lookup=query_context.defaults_fallback_lookup if query_context is not None else None,
        )
        requested_value = medication.ndc or medication.rxcui or medication.drug_name or ""
        resolved_match = MedicationMatch(
            medication_id=medication_id,
            requested_value=str(requested_value),
            requested_drug_name=medication.drug_name,
            resolved_drug_name=str(selected_candidate.drug_name),
            rxcui=str(selected_candidate.rxcui),
            ndc=str(selected_candidate.ndc),
            match_source=selected_candidate.match_source,
            match_confidence=selected_candidate.match_confidence,
            normalized_day_supply=day_supply,
            tier_family=tier_family,
        )
        matches.append(resolved_match)
        resolved_medications.append(
            {
                "medication_id": medication_id,
                "input": medication,
                "requested_drug_name": medication.drug_name,
                "drug_name": str(selected_candidate.drug_name),
                "rxcui": str(selected_candidate.rxcui),
                "ndc": str(selected_candidate.ndc),
                "is_insulin": bool(selected_candidate.is_insulin),
                "day_supply": day_supply,
                "tier_family": tier_family,
                "quantity": float(medication.quantity_override or defaults["default_quantity"] or day_supply),
                "fills_per_year": int(
                    medication.fills_per_year_override
                    or defaults["default_fills_per_year"]
                    or max(1, math.ceil(365 / day_supply))
                ),
                "match": resolved_match,
                "resolution_candidates": candidates,
                "match_review_required": bool(match_review_required),
            }
        )

    resolved_ndcs = [str(item["ndc"]) for item in resolved_medications]
    if query_context is not None and query_context.basis_df is not None:
        basis_df = query_context.basis_df.copy()
        cached_ndcs = (
            {str(value) for value in basis_df["ndc"].dropna().astype(str).tolist()}
            if not basis_df.empty and "ndc" in basis_df.columns
            else set()
        )
        missing_ndcs = [ndc for ndc in resolved_ndcs if ndc not in cached_ndcs]
        if missing_ndcs:
            extra_basis = fetch_basis_rows(conn, plan_keys, missing_ndcs)
            if basis_df.empty:
                basis_df = extra_basis
            elif not extra_basis.empty:
                basis_df = pd.concat([basis_df, extra_basis], ignore_index=True)
    else:
        basis_df = fetch_basis_rows(conn, plan_keys, resolved_ndcs)
    channel_df = (
        query_context.channel_df.copy()
        if query_context is not None and query_context.channel_df is not None
        else fetch_channel_summaries(conn, plan_keys)
    )
    nearest_distances = (
        dict(query_context.nearest_distances)
        if query_context is not None and query_context.nearest_distances is not None
        else _lookup_nearest_preferred_distance(conn, zipcode, plan_keys)
    )

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
        contract_year, benefit_design = _resolve_plan_benefit_design(
            _coerce_contract_year(plan.get("contract_year")),
            active_config,
        )
        channel_summary = channel_lookup.get(plan_key, {})
        remaining_deductible = float(plan.get("deductible") or 0.0)
        oop_accumulated = 0.0
        troop_accumulated = 0.0
        total_drug_spending = 0.0
        annual_drug_oop = 0.0
        plan_restriction_flags = {"prior_auth": False, "step_therapy": False, "quantity_limit": False}
        selected_channels: dict[str, int] = {}
        groups = PlanExplanationGroups([], [], [], [], [], [])
        detail_groups = PlanExplanationDetailGroups([], [], [], [], [], [])
        drug_state: dict[str, dict[str, Any]] = {}

        fill_events: list[ScheduledFillEvent] = []
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
                "coverage_gap_oop": 0.0,
                "catastrophic_oop": 0.0,
                "lis_adjusted_oop": 0.0,
                "negotiated_price_total": 0.0,
                "oop_cap_savings": 0.0,
                "fill_oop_values": [],
                "coverage_phases": set(),
                "fill_traces": [],
                "explanations": [],
                "channel_switch_count": 0,
                "last_selected_channel": None,
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
                fill_events.extend(
                    _build_scheduled_fill_events(
                        medication,
                        basis,
                        channel_summary,
                        beneficiary.pharmacy_preference,
                    )
                )
            drug_state[medication_id] = state

        fill_events.sort(key=_scheduled_fill_sort_key)
        for sequence_index, scheduled_event in enumerate(fill_events, start=1):
            medication = scheduled_event.medication
            basis = scheduled_event.basis
            day_offset = scheduled_event.day_offset
            fill_number = scheduled_event.fill_number
            medication_id = str(scheduled_event.medication_id)
            drug_name = str(medication["drug_name"])
            state = drug_state[medication_id]
            channel_results: list[tuple[str, FillCostResult]] = []
            for channel in scheduled_event.available_channels:
                channel_result = _simulate_fill_cost(
                    basis,
                    channel_summary,
                    channel,
                    float(medication["quantity"]),
                    remaining_deductible,
                    oop_accumulated,
                    beneficiary.lis_status,
                    total_drug_spending_accumulated=total_drug_spending,
                    benefit_design=benefit_design,
                    troop_accumulated=troop_accumulated,
                )
                if channel_result is None:
                    continue
                channel_results.append((channel, channel_result))

            best_channel, best_result = _select_best_channel_result(
                channel_results,
                state["last_selected_channel"],
                beneficiary.pharmacy_preference,
            )
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

            previous_channel = state["last_selected_channel"]
            if previous_channel is not None and previous_channel != best_channel:
                state["channel_switch_count"] += 1
            state["last_selected_channel"] = best_channel
            remaining_deductible = best_result.deductible_after
            oop_accumulated = best_result.oop_after
            troop_accumulated = best_result.troop_after
            total_drug_spending = best_result.total_drug_spending_after
            annual_drug_oop += best_result.total_oop
            state["selected_channel"] = best_channel
            state["annual_oop"] += best_result.total_oop
            state["deductible_exposure"] += best_result.deductible_exposure
            state["initial_coverage_oop"] += best_result.initial_coverage_oop
            state["coverage_gap_oop"] += best_result.coverage_gap_oop
            state["catastrophic_oop"] += best_result.catastrophic_oop
            state["lis_adjusted_oop"] += best_result.lis_adjusted_oop
            state["negotiated_price_total"] += best_result.negotiated_price
            state["oop_cap_savings"] += max(0.0, best_result.lis_adjusted_oop - best_result.total_oop)
            state["fill_oop_values"].append(best_result.total_oop)
            state["coverage_phases"].add(best_result.coverage_phase)
            state["fill_traces"].append(
                DrugFillTrace(
                    fill_number=fill_number,
                    day_offset=day_offset,
                    sequence_index=sequence_index,
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
                    total_drug_spending_before=round(best_result.total_drug_spending_before, 2),
                    total_drug_spending_after=round(best_result.total_drug_spending_after, 2),
                    coverage_gap_exposure=round(best_result.coverage_gap_oop, 2),
                    troop_before=round(best_result.troop_before, 2),
                    troop_after=round(best_result.troop_after, 2),
                    benefit_design=best_result.benefit_design,
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
            if "coverage_gap" in best_result.coverage_phase:
                message = f"{drug_name} enters the coverage gap (donut hole) during the simulated year."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.cost_logic_issues,
                    detail_groups.cost_logic_issues,
                    "coverage_gap_phase",
                    message,
                    related_drug=drug_name,
                    coverage_phase=best_result.coverage_phase,
                    severity="warning",
                )
            if "catastrophic" in best_result.coverage_phase:
                message = f"{drug_name} reaches the catastrophic coverage phase, reducing cost sharing significantly."
                _append_unique(state["explanations"], message)
                _append_explanation(
                    groups.cost_logic_issues,
                    detail_groups.cost_logic_issues,
                    "catastrophic_phase",
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
                    coverage_gap_oop=round(float(state["coverage_gap_oop"]), 2),
                    catastrophic_oop=round(float(state["catastrophic_oop"]), 2),
                    lis_adjusted_oop=round(float(state["lis_adjusted_oop"]), 2),
                    negotiated_price_total=round(float(state["negotiated_price_total"]), 2),
                    oop_cap_savings=round(float(state["oop_cap_savings"]), 2),
                    pa_flag=bool(basis["has_prior_auth"]) if basis else False,
                    st_flag=bool(basis["has_step_therapy"]) if basis else False,
                    ql_flag=bool(basis["has_quantity_limit"]) if basis else False,
                    insulin_flag=bool(basis["is_insulin"]) if basis else bool(medication["is_insulin"]),
                    coverage_gap_flag=any("coverage_gap" in str(value) for value in state["coverage_phases"]),
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
        elif plan["network_flag"] == "unknown":
            _append_explanation(
                groups.pharmacy_access_issues,
                detail_groups.pharmacy_access_issues,
                "unknown_network_data",
                "Pharmacy network data is incomplete for this plan and should be verified.",
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
        priced_drug_count = sum(1 for item in breakdowns if item.pricing_status == "priced")
        channel_switch_count = sum(int(state["channel_switch_count"]) for state in drug_state.values())
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
                    f"{channel}:{count}"
                    for channel, count in sorted(
                        selected_channels.items(),
                        key=lambda item: (
                            CHANNEL_ORDER.index(item[0]) if item[0] in CHANNEL_ORDER else len(CHANNEL_ORDER),
                            item[0],
                        ),
                    )
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
                scenario_profile=SCENARIO_LOW_UTILIZER,
                match_review_required=any(
                    bool(item.get("match_review_required")) for item in resolved_medications
                ),
                unsafe_reasons=[],
                feature_version=FEATURE_VERSION,
                drug_breakdowns=breakdowns,
                contract_year=contract_year,
                benefit_design=benefit_design,
                priced_drug_count=priced_drug_count,
                channel_switch_count=channel_switch_count,
                simulation_policy=SIMULATION_POLICY,
            )
        )

    _apply_fit_scoring(recommendations, beneficiary)
    _apply_run_profile(recommendations, beneficiary)
    recommendations.sort(key=_rules_ranking_sort_key)
    for rank, recommendation in enumerate(recommendations, start=1):
        recommendation.plan_rank = rank

    if ranking_mode == "hybrid":
        from .modeling import apply_hybrid_reranking

        recommendations = apply_hybrid_reranking(recommendations, beneficiary, config=active_config)

    if owns_connection:
        conn.close()
    return recommendations


def recommend_plans(
    beneficiary: BeneficiaryInput,
    medications: list[MedicationInput],
    config: PipelineConfig | None = None,
    ranking_mode: str = "rules",
    allow_approximate_match_ranking: bool = False,
    conn: duckdb.DuckDBPyConnection | None = None,
    query_context: RecommendationQueryContext | None = None,
) -> list[PlanRecommendation]:
    recommendations = _generate_recommendations(
        beneficiary,
        medications,
        config=config,
        ranking_mode=ranking_mode,
        allow_approximate_match_ranking=allow_approximate_match_ranking,
        conn=conn,
        query_context=query_context,
    )
    return recommendations[: max(1, beneficiary.top_n)]


def recommend_plan_bundle(
    beneficiary: BeneficiaryInput,
    medications: list[MedicationInput],
    config: PipelineConfig | None = None,
    ranking_mode: str = "rules",
    comparison_only_plans: list[PlanRecommendation] | None = None,
    allow_approximate_match_ranking: bool = False,
    conn: duckdb.DuckDBPyConnection | None = None,
    query_context: RecommendationQueryContext | None = None,
) -> RecommendationBundle:
    recommendations = _generate_recommendations(
        beneficiary,
        medications,
        config=config,
        ranking_mode=ranking_mode,
        allow_approximate_match_ranking=allow_approximate_match_ranking,
        conn=conn,
        query_context=query_context,
    )
    scenario_profile = recommendations[0].scenario_profile if recommendations else SCENARIO_LOW_UTILIZER
    local_coverable_counts = _local_coverable_counts(recommendations)
    shortlist_limit = max(1, beneficiary.top_n)
    full_coverage = sorted(
        [item for item in recommendations if _is_full_coverage_plan(item)],
        key=_full_coverage_compare_sort_key,
    )
    partial_fallback = sorted(
        [item for item in recommendations if not _is_full_coverage_plan(item)],
        key=lambda item: _partial_fallback_sort_key(item, local_coverable_counts),
    )
    displayed_full_coverage = _assign_plan_ranks(full_coverage[:shortlist_limit])
    displayed_partial_fallback: list[PlanRecommendation] = []
    if not full_coverage:
        displayed_partial_fallback = _assign_plan_ranks(partial_fallback[:shortlist_limit])
    blocked_medications = _build_blocked_medications(recommendations)
    alternative_search_terms = _build_alternative_search_terms(blocked_medications)
    displayed_comparison_plans = _assign_plan_ranks(list(comparison_only_plans or [])[:5])
    return RecommendationBundle(
        summary=RecommendationBundleSummary(
            requested_drug_count=len(medications),
            local_candidate_plan_count=len(recommendations),
            local_full_coverage_count=len(full_coverage),
            local_partial_count=len(partial_fallback),
            fallback_reason="none" if full_coverage else "no_local_full_coverage",
            scenario_profile=scenario_profile,
            candidate_plan_count_service_area=len(recommendations),
            candidate_plan_count_ranked=len(recommendations),
            plans_with_unknown_network_count=sum(1 for item in recommendations if item.network_flag == "unknown"),
        ),
        full_coverage_plans=displayed_full_coverage,
        partial_fallback_plans=displayed_partial_fallback,
        comparison_only_plans=displayed_comparison_plans,
        blocked_medications=blocked_medications,
        alternative_search_terms=alternative_search_terms,
    )


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
                "contract_year": recommendation.contract_year,
                "benefit_design": recommendation.benefit_design,
                "priced_drug_count": recommendation.priced_drug_count,
                "channel_switch_count": recommendation.channel_switch_count,
                "simulation_policy": recommendation.simulation_policy,
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
                "contract_year": recommendation.contract_year,
                "benefit_design": recommendation.benefit_design,
                "priced_drug_count": recommendation.priced_drug_count,
                "channel_switch_count": recommendation.channel_switch_count,
                "simulation_policy": recommendation.simulation_policy,
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
