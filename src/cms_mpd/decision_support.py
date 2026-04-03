"""Decision-support contracts and UI-facing helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import uuid

import pandas as pd

from .recommend import PlanRecommendation


DEFAULT_RESEARCH_SEED = 42
RECOMMENDATION_SCHEMA_COLUMNS = [
    "run_id",
    "PLAN_KEY",
    "PLAN_NAME",
    "eligibility_status",
    "comparison_only",
    "recommendation_tier",
    "coverage_status",
    "coverage_pct_requested",
    "estimated_annual_oop",
    "estimated_total_annual_cost",
    "cost_breakdown",
    "access_summary",
    "warning_flags",
    "decision_score",
    "heuristic_score",
    "rules_score",
    "ml_score",
    "ranking_source",
    "confidence_band",
    "confidence_score",
    "stability_score",
    "evidence_gaps",
    "feature_version",
    "contract_year",
    "benefit_design",
    "priced_drug_count",
    "channel_switch_count",
    "simulation_policy",
]

CONFIDENCE_SCORE_MAP = {
    "High": 100.0,
    "Medium": 78.0,
    "Low": 52.0,
    "Exploratory": 24.0,
}

PREFERENCE_PRESETS = {
    "Balanced recommendation": {
        "cost_priority": 5,
        "coverage_priority": 5,
        "access_priority": 4,
        "minimum_coverage_pct": 100,
    },
    "Lowest annual cost": {
        "cost_priority": 5,
        "coverage_priority": 4,
        "access_priority": 3,
        "minimum_coverage_pct": 85,
    },
    "Safest medication coverage": {
        "cost_priority": 3,
        "coverage_priority": 5,
        "access_priority": 3,
        "minimum_coverage_pct": 100,
    },
    "Easiest pharmacy access": {
        "cost_priority": 3,
        "coverage_priority": 4,
        "access_priority": 5,
        "minimum_coverage_pct": 85,
    },
    "Conservative compare and verify": {
        "cost_priority": 4,
        "coverage_priority": 5,
        "access_priority": 4,
        "minimum_coverage_pct": 100,
    },
}


@dataclass(frozen=True)
class ProfileInput:
    persona: str
    zipcode: str
    age_band: str
    lis_status: str
    pharmacy_preference: str
    chronic_condition_flags: list[str]
    top_n: int


@dataclass(frozen=True)
class MedicationListItem:
    drug_name: str
    rxcui: str | None
    ndc: str | None
    tier_family: str | None
    day_supply: int
    quantity_override: float | None
    fills_per_year_override: int | None


@dataclass(frozen=True)
class PreferenceWeights:
    primary_goal: str
    minimum_coverage_pct: float
    allow_comparison_plans: bool
    max_comparison_distance_miles: int
    ranking_mode: str


@dataclass(frozen=True)
class RecommendationAudit:
    run_id: str
    generated_at: str
    model_version: str
    data_snapshot: str
    user_input_summary: dict
    feature_coverage: dict
    top_k_outputs: list[dict]


def recommend_preference_preset(persona: str, primary_goal: str, has_medications: bool) -> dict:
    preset = dict(PREFERENCE_PRESETS.get(primary_goal, PREFERENCE_PRESETS["Balanced recommendation"]))
    persona_key = str(persona or "").strip().lower()
    if "caregiver" in persona_key:
        preset["access_priority"] = min(5, int(preset["access_priority"]) + 1)
        preset["coverage_priority"] = min(5, int(preset["coverage_priority"]) + 1)
    elif "counselor" in persona_key or "navigator" in persona_key:
        preset["coverage_priority"] = min(5, int(preset["coverage_priority"]) + 1)
    if not has_medications:
        preset["minimum_coverage_pct"] = 0
    return preset


def _coverage_pct(recommendation: PlanRecommendation) -> float:
    requested = max(1, len(recommendation.drug_breakdowns))
    covered = sum(1 for item in recommendation.drug_breakdowns if item.coverage_status == "covered")
    return round(100.0 * covered / requested, 2)


def _access_summary(recommendation: PlanRecommendation, comparison_only: bool) -> dict:
    return {
        "comparison_only": bool(comparison_only),
        "network_flag": recommendation.network_flag,
        "nearest_preferred_miles": recommendation.nearest_preferred_distance_miles,
        "mail_order_dependency_count": recommendation.mail_order_dependency_count,
        "channel_diversity_count": recommendation.channel_diversity_count,
        "channel_switch_count": recommendation.channel_switch_count,
        "channel_mix": recommendation.best_channel_mix,
    }


def _warning_flags(recommendation: PlanRecommendation, comparison_only: bool) -> list[str]:
    warnings = list(recommendation.key_watchouts)
    if comparison_only:
        warnings.insert(0, "Outside the selected service area; shown for comparison only.")
    if recommendation.network_flag == "limited_preferred_retail":
        warnings.append("Preferred retail access is limited.")
    elif recommendation.network_flag == "no_preferred_retail":
        warnings.append("No preferred retail access was identified.")
    if recommendation.uncovered_drug_count > 0:
        warnings.append("At least one requested drug is not fully covered.")
    deduped: list[str] = []
    for warning in warnings:
        if warning and warning not in deduped:
            deduped.append(warning)
    return deduped


def _evidence_gaps(recommendation: PlanRecommendation, comparison_only: bool) -> list[str]:
    gaps: list[str] = []
    approximate_matches = sum(
        1 for item in recommendation.resolved_medications if item.match_confidence != "exact"
    )
    if approximate_matches > 0:
        gaps.append(f"{approximate_matches} medication match(es) are approximate.")
    if recommendation.model_score is None:
        gaps.append("Hybrid reranker score not available for this result.")
    requested_count = max(1, len(recommendation.drug_breakdowns))
    if recommendation.priced_drug_count < requested_count:
        gaps.append(
            f"Only {recommendation.priced_drug_count} of {requested_count} entered medication(s) were fully priceable."
        )
    if recommendation.nearest_preferred_distance_miles is None:
        gaps.append("Nearest preferred pharmacy distance is not available.")
    if comparison_only:
        gaps.append("This plan is not eligible in the selected service area.")
    return gaps


def classify_confidence_band(recommendation: PlanRecommendation, comparison_only: bool = False) -> str:
    if comparison_only:
        return "Exploratory"
    if recommendation.uncovered_drug_count > 0 or recommendation.network_flag == "no_preferred_retail":
        return "Low"
    approximate_matches = sum(
        1 for item in recommendation.resolved_medications if item.match_confidence != "exact"
    )
    if approximate_matches > 0 or recommendation.network_flag == "limited_preferred_retail":
        return "Medium"
    return "High"


def classify_recommendation_tier(
    recommendation: PlanRecommendation,
    minimum_coverage_pct: float = 0.0,
    comparison_only: bool = False,
) -> str:
    if comparison_only:
        return "Comparison only"
    coverage_pct = _coverage_pct(recommendation)
    confidence_band = classify_confidence_band(recommendation, comparison_only=comparison_only)
    if coverage_pct < float(minimum_coverage_pct or 0.0):
        return "Needs verification"
    if confidence_band == "Low" or recommendation.coverage_status != "full":
        return "Needs verification"
    if confidence_band == "High":
        return "Ready to shortlist"
    return "Worth comparing"


def compute_heuristic_score(recommendation: PlanRecommendation) -> float:
    penalty = 0.0
    penalty += recommendation.annual_total_cost / 50.0
    penalty += 20.0 * recommendation.uncovered_drug_count
    penalty += 8.0 * recommendation.restriction_count
    penalty += 6.0 * recommendation.mail_order_dependency_count
    penalty += 8.0 * recommendation.channel_switch_count
    penalty += 15.0 if recommendation.network_flag == "no_preferred_retail" else 0.0
    penalty += 6.0 if recommendation.network_flag == "limited_preferred_retail" else 0.0
    if recommendation.nearest_preferred_distance_miles is not None:
        penalty += min(float(recommendation.nearest_preferred_distance_miles), 40.0)
    return round(max(0.0, 100.0 - penalty), 2)


def recommendations_to_dataframe(
    recommendations: list[PlanRecommendation],
    *,
    run_id: str | None = None,
    comparison_only: bool = False,
    minimum_coverage_pct: float = 0.0,
) -> pd.DataFrame:
    if not recommendations:
        return pd.DataFrame(columns=RECOMMENDATION_SCHEMA_COLUMNS)

    run_id = run_id or uuid.uuid4().hex[:12]
    rows: list[dict] = []
    for recommendation in recommendations:
        coverage_pct = _coverage_pct(recommendation)
        confidence_band = classify_confidence_band(recommendation, comparison_only=comparison_only)
        access_summary = _access_summary(recommendation, comparison_only=comparison_only)
        warning_flags = _warning_flags(recommendation, comparison_only=comparison_only)
        evidence_gaps = _evidence_gaps(recommendation, comparison_only=comparison_only)
        row = {
            "run_id": run_id,
            "PLAN_KEY": recommendation.plan_key,
            "PLAN_NAME": recommendation.plan_name,
            "eligibility_status": (
                "Comparison only - outside selected service area"
                if comparison_only
                else "Eligible"
            ),
            "comparison_only": bool(comparison_only),
            "recommendation_tier": classify_recommendation_tier(
                recommendation,
                minimum_coverage_pct=minimum_coverage_pct,
                comparison_only=comparison_only,
            ),
            "coverage_status": recommendation.coverage_status,
            "coverage_pct_requested": coverage_pct,
            "estimated_annual_oop": round(float(recommendation.annual_drug_oop), 2),
            "estimated_total_annual_cost": round(float(recommendation.annual_total_cost), 2),
            "cost_breakdown": {
                "annual_premium": round(float(recommendation.annual_premium), 2),
                "estimated_oop": round(float(recommendation.annual_drug_oop), 2),
                "estimated_total_annual_cost": round(float(recommendation.annual_total_cost), 2),
                "monthly_total": round(float(recommendation.monthly_cost_estimate), 2),
            },
            "access_summary": access_summary,
            "warning_flags": warning_flags,
            "decision_score": round(float(recommendation.fit_score), 2),
            "heuristic_score": compute_heuristic_score(recommendation),
            "rules_score": round(float(recommendation.rules_score), 4),
            "ml_score": recommendation.model_score,
            "ranking_source": recommendation.ranking_source,
            "confidence_band": confidence_band,
            "confidence_score": CONFIDENCE_SCORE_MAP[confidence_band],
            "stability_score": round(float(recommendation.fit_metrics.stability_score), 2),
            "evidence_gaps": evidence_gaps,
            "feature_version": recommendation.feature_version,
            "contract_year": recommendation.contract_year,
            "benefit_design": recommendation.benefit_design,
            "priced_drug_count": recommendation.priced_drug_count,
            "channel_switch_count": recommendation.channel_switch_count,
            "simulation_policy": recommendation.simulation_policy,
            "selected_channel_mix": recommendation.best_channel_mix,
            "network_flag": recommendation.network_flag,
            "nearest_preferred_distance_miles": recommendation.nearest_preferred_distance_miles,
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    return frame[RECOMMENDATION_SCHEMA_COLUMNS + [col for col in frame.columns if col not in RECOMMENDATION_SCHEMA_COLUMNS]]


def summarize_feature_coverage(
    eligible_recommendations: list[PlanRecommendation],
    comparison_recommendations: list[PlanRecommendation] | None = None,
) -> dict:
    comparison_recommendations = comparison_recommendations or []
    all_recommendations = list(eligible_recommendations) + list(comparison_recommendations)
    return {
        "candidate_plans": len(all_recommendations),
        "eligible_plans": len(eligible_recommendations),
        "comparison_only_plans": len(comparison_recommendations),
        "plans_with_model_score": sum(1 for item in all_recommendations if item.model_score is not None),
        "plans_with_distance": sum(
            1 for item in all_recommendations if item.nearest_preferred_distance_miles is not None
        ),
        "plans_with_full_coverage": sum(1 for item in eligible_recommendations if item.coverage_status == "full"),
        "contract_years": sorted({int(item.contract_year) for item in all_recommendations if item.contract_year is not None}),
        "benefit_designs": sorted({str(item.benefit_design) for item in all_recommendations if item.benefit_design}),
        "simulation_policies": sorted({str(item.simulation_policy) for item in all_recommendations if item.simulation_policy}),
    }


def serialize_nested_columns(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    columns = columns or ["cost_breakdown", "access_summary", "warning_flags", "evidence_gaps"]
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].apply(
                lambda value: json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value
            )
    return out


def create_run_audit(
    user_input_summary: dict,
    model_version: str,
    data_snapshot: str,
    feature_coverage: dict,
    recommendations: pd.DataFrame,
    run_id: str | None = None,
) -> RecommendationAudit:
    run_id = run_id or uuid.uuid4().hex[:12]
    top_k = []
    if len(recommendations) > 0:
        export_cols = [
            "PLAN_KEY",
            "PLAN_NAME",
            "eligibility_status",
            "comparison_only",
            "recommendation_tier",
            "coverage_status",
            "coverage_pct_requested",
            "estimated_annual_oop",
            "estimated_total_annual_cost",
            "decision_score",
            "rules_score",
            "ml_score",
            "confidence_band",
            "stability_score",
            "contract_year",
            "benefit_design",
            "priced_drug_count",
            "channel_switch_count",
            "simulation_policy",
            "selected_channel_mix",
        ]
        top_k = serialize_nested_columns(recommendations[export_cols].head(10)).to_dict("records")
    return RecommendationAudit(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        model_version=model_version,
        data_snapshot=data_snapshot,
        user_input_summary=user_input_summary,
        feature_coverage=feature_coverage,
        top_k_outputs=top_k,
    )


def as_public_types(
    profile: ProfileInput,
    medications: list[MedicationListItem],
    preferences: PreferenceWeights,
) -> dict:
    return {
        "Profile": asdict(profile),
        "MedicationList": [asdict(item) for item in medications],
        "PreferenceWeights": asdict(preferences),
    }
