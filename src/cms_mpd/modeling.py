from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .config import PipelineConfig


logger = logging.getLogger(__name__)

DATASET_SCHEMA_VERSION = "request_features_v4"
WEAK_LABEL_VERSION = "weak_label_v2"
TREE_MODEL_TYPE = "tree"
LINEAR_MODEL_TYPE = "linear"
NETWORK_RISK_MAP = {
    "adequate": 0.0,
    "limited_preferred_retail": 1.0,
    "no_preferred_retail": 2.0,
}
BASE_SCENARIO_COUNT = {
    "demo": 6,
    "full": 12,
}
EVALUATION_SPLIT_SEED = 42
EVALUATION_TEST_FRACTION = 0.3

MODEL_NUMERIC_COLUMNS = [
    "current_rules_rank",
    "current_rules_score",
    "fit_score",
    "cost_score",
    "premium_score",
    "coverage_score",
    "access_score",
    "stability_score",
    "annual_premium",
    "annual_drug_oop",
    "annual_total_cost",
    "requested_drug_count",
    "covered_drug_count_request",
    "covered_drug_share",
    "priced_drug_share",
    "uncovered_drug_count",
    "uncovered_drug_share",
    "priced_drug_count",
    "restriction_count",
    "deductible_exposure_total",
    "initial_coverage_oop_total",
    "lis_adjusted_oop_total",
    "negotiated_price_total",
    "oop_cap_savings_total",
    "excluded_drug_count",
    "excluded_drug_share",
    "missing_price_drug_count",
    "missing_price_drug_share",
    "channel_unavailable_count",
    "channel_unavailable_share",
    "mail_order_dependency_flag",
    "mail_order_dependency_share",
    "monthly_drug_oop_variance",
    "monthly_total_variance",
    "channel_switch_count",
    "insulin_risk_flag",
    "insulin_nonpreferred_dependency_count",
    "insulin_nonpreferred_dependency_share",
    "approximate_match_count",
    "preferred_match_count",
    "exact_match_count",
    "in_area_pharmacies",
    "preferred_retail_count",
    "preferred_mail_count",
    "covered_drug_count",
    "insulin_drug_count",
    "pa_rate",
    "st_rate",
    "ql_rate",
    "excluded_rate",
    "deductible",
    "served_counties",
    "beneficiary_chronic_condition_count",
    "zipcode_density_score",
    "nearest_preferred_distance_bucket",
    "network_risk_score",
]

MODEL_CATEGORICAL_COLUMNS = [
    "coverage_status",
    "network_flag",
    "lis_status",
    "age_band",
    "pharmacy_preference",
    "zip_density_category",
    "scenario_bundle",
]

FEATURE_SUBSETS = {
    "cost_only": {
        "numeric": [
            "current_rules_rank",
            "current_rules_score",
            "annual_premium",
            "annual_drug_oop",
            "annual_total_cost",
            "deductible_exposure_total",
            "initial_coverage_oop_total",
            "lis_adjusted_oop_total",
            "negotiated_price_total",
            "oop_cap_savings_total",
            "deductible",
            "requested_drug_count",
            "covered_drug_count_request",
        ],
        "categorical": ["coverage_status", "lis_status", "age_band", "pharmacy_preference"],
    },
    "cost_plus_restrictions": {
        "numeric": [
            "current_rules_rank",
            "current_rules_score",
            "annual_premium",
            "annual_drug_oop",
            "annual_total_cost",
            "deductible_exposure_total",
            "initial_coverage_oop_total",
            "lis_adjusted_oop_total",
            "negotiated_price_total",
            "oop_cap_savings_total",
            "deductible",
            "requested_drug_count",
            "covered_drug_count_request",
            "covered_drug_share",
            "priced_drug_share",
            "uncovered_drug_count",
            "uncovered_drug_share",
            "restriction_count",
            "excluded_drug_count",
            "excluded_drug_share",
            "missing_price_drug_count",
            "missing_price_drug_share",
            "channel_unavailable_count",
            "channel_unavailable_share",
            "monthly_drug_oop_variance",
            "monthly_total_variance",
            "insulin_risk_flag",
            "insulin_nonpreferred_dependency_count",
            "insulin_nonpreferred_dependency_share",
            "approximate_match_count",
            "preferred_match_count",
            "exact_match_count",
            "beneficiary_chronic_condition_count",
        ],
        "categorical": ["coverage_status", "lis_status", "age_band", "pharmacy_preference", "scenario_bundle"],
    },
    "cost_plus_restrictions_network": {
        "numeric": [
            "current_rules_rank",
            "current_rules_score",
            "annual_premium",
            "annual_drug_oop",
            "annual_total_cost",
            "deductible_exposure_total",
            "initial_coverage_oop_total",
            "lis_adjusted_oop_total",
            "negotiated_price_total",
            "oop_cap_savings_total",
            "deductible",
            "requested_drug_count",
            "covered_drug_count_request",
            "covered_drug_share",
            "priced_drug_share",
            "uncovered_drug_count",
            "uncovered_drug_share",
            "restriction_count",
            "excluded_drug_count",
            "excluded_drug_share",
            "missing_price_drug_count",
            "missing_price_drug_share",
            "channel_unavailable_count",
            "channel_unavailable_share",
            "monthly_drug_oop_variance",
            "monthly_total_variance",
            "insulin_risk_flag",
            "insulin_nonpreferred_dependency_count",
            "insulin_nonpreferred_dependency_share",
            "approximate_match_count",
            "preferred_match_count",
            "exact_match_count",
            "beneficiary_chronic_condition_count",
            "mail_order_dependency_flag",
            "mail_order_dependency_share",
            "in_area_pharmacies",
            "preferred_retail_count",
            "preferred_mail_count",
            "zipcode_density_score",
            "nearest_preferred_distance_bucket",
            "network_risk_score",
        ],
        "categorical": [
            "coverage_status",
            "network_flag",
            "lis_status",
            "age_band",
            "pharmacy_preference",
            "zip_density_category",
            "scenario_bundle",
        ],
    },
    "full": {
        "numeric": MODEL_NUMERIC_COLUMNS,
        "categorical": MODEL_CATEGORICAL_COLUMNS,
    },
}


@dataclass(slots=True)
class ScenarioSpec:
    scenario_id: str
    scenario_bundle: str
    beneficiary: Any
    medications: list[Any]


@dataclass(slots=True)
class HybridRerankerArtifact:
    snapshot_quarter: str
    build_profile: str
    model_type: str
    feature_names: list[str]
    numeric_columns: list[str]
    categorical_columns: list[str]
    dataset_schema_version: str
    weak_label_version: str
    feature_version: str
    feature_subset: str
    metadata: dict[str, Any]
    means: list[float] | None = None
    scales: list[float] | None = None
    weights: list[float] | None = None
    intercept: float | None = None
    base_value: float | None = None
    learning_rate: float | None = None
    trees: list[dict[str, Any]] = field(default_factory=list)
    alpha: float | None = None

    def predict(self, frame: pd.DataFrame) -> np.ndarray:
        matrix, _ = _encode_feature_frame(
            frame,
            self.numeric_columns,
            self.categorical_columns,
            feature_names=self.feature_names,
        )
        if self.model_type == LINEAR_MODEL_TYPE:
            means = np.array(self.means or [], dtype=float)
            scales = np.array(self.scales or [], dtype=float)
            weights = np.array(self.weights or [], dtype=float)
            standardized = (matrix - means) / scales
            return standardized @ weights + float(self.intercept or 0.0)
        return _predict_tree_ensemble(
            matrix,
            self.trees,
            float(self.base_value or 0.0),
            float(self.learning_rate or 0.1),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _connect(config: PipelineConfig) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=True)


def _fetch_dataframe(
    conn: duckdb.DuckDBPyConnection, query: str, params: list[Any] | None = None
) -> pd.DataFrame:
    if params:
        return conn.execute(query, params).fetch_df()
    return conn.execute(query).fetch_df()


def _density_score(category: str) -> float:
    mapping = {"rural": 0.0, "suburban": 1.0, "urban": 2.0}
    return mapping.get(category, 1.0)


def _distance_bucket(distance: float | None) -> float:
    if distance is None or math.isnan(distance):
        return 3.0
    if distance <= 5:
        return 0.0
    if distance <= 15:
        return 1.0
    if distance <= 30:
        return 2.0
    return 3.0


def _dataset_metadata_path(path: Path) -> Path:
    return path.with_suffix(".metadata.json")


def _artifact_path(config: PipelineConfig, model_type: str) -> Path:
    return config.model_dir / f"hybrid_reranker_{model_type}.json"


def _evaluation_report_path(config: PipelineConfig, model_type: str) -> Path:
    return config.training_dir / f"hybrid_reranker_evaluation_{model_type}.json"


def _research_report_path(config: PipelineConfig) -> Path:
    return (
        config.training_dir
        / "research"
        / f"{DATASET_SCHEMA_VERSION}__{WEAK_LABEL_VERSION}"
        / "evaluation.json"
    )


def _weak_label_score(row: pd.Series) -> float:
    coverage_bonus = 1000.0 if row["coverage_status"] == "full" else 0.0
    network_penalty = 20.0 * float(row["network_risk_score"])
    return (
        coverage_bonus
        + float(row["current_rules_score"])
        - float(row["annual_total_cost"])
        - 250.0 * float(row["uncovered_drug_count"])
        - 125.0 * float(row["excluded_drug_count"])
        - 110.0 * float(row["missing_price_drug_count"])
        - 90.0 * float(row["channel_unavailable_count"])
        - 25.0 * float(row["restriction_count"])
        - 20.0 * float(row["approximate_match_count"])
        - 18.0 * float(row["mail_order_dependency_flag"])
        - 15.0 * float(row["insulin_risk_flag"])
        - 12.0 * float(row["insulin_nonpreferred_dependency_count"])
        - network_penalty
    )


def _heuristic_score(row: pd.Series) -> float:
    return (
        (500.0 if row["coverage_status"] == "full" else 0.0)
        + float(row["current_rules_score"])
        - float(row["annual_total_cost"])
        - 200.0 * float(row["uncovered_drug_count"])
        - 30.0 * float(row["restriction_count"])
        - 10.0 * float(row["network_risk_score"])
    )


def _scenario_relevance(group: pd.DataFrame) -> pd.DataFrame:
    ordered = group.sort_values(["weak_label_score", "annual_total_cost"], ascending=[False, True]).copy()
    ordered["weak_label_rank"] = np.arange(1, len(ordered) + 1)
    ordered["weak_label_relevance"] = np.maximum(0, 6 - ordered["weak_label_rank"])
    return ordered[["scenario_id", "plan_key", "weak_label_rank", "weak_label_relevance"]]


def _choose_drug(conn: duckdb.DuckDBPyConnection, where_sql: str) -> dict[str, Any] | None:
    df = _fetch_dataframe(
        conn,
        f"""
        SELECT DISTINCT drug_name, ndc, tier_family, is_insulin, days_supply
        FROM gold.plan_drug_cost_basis
        WHERE drug_name IS NOT NULL
          AND ndc IS NOT NULL
          AND {where_sql}
        ORDER BY drug_name
        LIMIT 1
        """
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def _query_scenario_inputs(
    conn: duckdb.DuckDBPyConnection, config: PipelineConfig
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    zipcode_limit = BASE_SCENARIO_COUNT["demo" if config.is_demo_profile else "full"]
    zip_df = _fetch_dataframe(
        conn,
        f"""
        SELECT DISTINCT
            psa.zip_code,
            coalesce(z.density_category, 'suburban') AS density_category
        FROM gold.plan_service_area psa
        LEFT JOIN silver.dim_zipcode z ON psa.zip_code = z.zip_code
        ORDER BY psa.zip_code
        LIMIT {zipcode_limit}
        """
    )
    if zip_df.empty:
        raise ValueError("No ZIP codes available in gold.plan_service_area for training scenarios.")

    generic_drug = _choose_drug(conn, "tier_family = 'generic'")
    brand_drug = _choose_drug(conn, "tier_family = 'brand' AND is_insulin = FALSE")
    insulin_drug = _choose_drug(conn, "is_insulin = TRUE")
    fallback_drug = generic_drug or brand_drug or insulin_drug or _choose_drug(conn, "TRUE")
    generic_drug = generic_drug or fallback_drug
    brand_drug = brand_drug or fallback_drug
    insulin_drug = insulin_drug or brand_drug or fallback_drug
    drugs = [item for item in [generic_drug, brand_drug, insulin_drug] if item]
    if not drugs:
        raise ValueError("No eligible drugs found in gold.plan_drug_cost_basis for scenario generation.")
    return drugs, zip_df


def _build_default_scenarios(config: PipelineConfig) -> list[ScenarioSpec]:
    from .recommend import BeneficiaryInput, MedicationInput

    conn = _connect(config)
    drugs, zip_df = _query_scenario_inputs(conn, config)
    conn.close()

    generic_drug = drugs[0]
    brand_drug = drugs[1] if len(drugs) > 1 else drugs[0]
    insulin_drug = drugs[2] if len(drugs) > 2 else brand_drug
    approximate_name = str(generic_drug["drug_name"]).split()[0]
    scenarios: list[ScenarioSpec] = []
    templates = [
        (
            "generic_only",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="65-74", lis_status="none", pharmacy_preference="auto", top_n=1000),
                [MedicationInput(drug_name=str(generic_drug["drug_name"]), tier_family="generic", day_supply=30)],
            ),
        ),
        (
            "mixed_brand_generic",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="75-84", lis_status="none", pharmacy_preference="auto", top_n=1000),
                [
                    MedicationInput(drug_name=str(generic_drug["drug_name"]), tier_family="generic", day_supply=30),
                    MedicationInput(drug_name=str(brand_drug["drug_name"]), tier_family=str(brand_drug["tier_family"]), day_supply=30),
                ],
            ),
        ),
        (
            "insulin_heavy",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="65-74",
                    lis_status="partial",
                    pharmacy_preference="auto",
                    chronic_condition_flags=["diabetes"],
                    top_n=1000,
                ),
                [
                    MedicationInput(drug_name=str(insulin_drug["drug_name"]), tier_family="brand", day_supply=30),
                    MedicationInput(drug_name=str(generic_drug["drug_name"]), tier_family="generic", day_supply=30),
                ],
            ),
        ),
        (
            "mail_order_favored",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="75-84", lis_status="none", pharmacy_preference="mail", top_n=1000),
                [MedicationInput(drug_name=str(brand_drug["drug_name"]), tier_family=str(brand_drug["tier_family"]), day_supply=90)],
            ),
        ),
        (
            "high_deductible",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="85+", lis_status="none", pharmacy_preference="retail", top_n=1000),
                [
                    MedicationInput(drug_name=str(brand_drug["drug_name"]), tier_family=str(brand_drug["tier_family"]), day_supply=30),
                    MedicationInput(drug_name=str(generic_drug["drug_name"]), tier_family="generic", day_supply=30),
                ],
            ),
        ),
        (
            "partial_coverage",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="75-84", lis_status="none", pharmacy_preference="auto", top_n=1000),
                [
                    MedicationInput(drug_name=str(brand_drug["drug_name"]), tier_family=str(brand_drug["tier_family"]), day_supply=30),
                    MedicationInput(drug_name=str(insulin_drug["drug_name"]), tier_family="brand", day_supply=30),
                ],
            ),
        ),
        (
            "approximate_match",
            lambda zipcode: (
                BeneficiaryInput(zipcode=zipcode, age_band="65-74", lis_status="full", pharmacy_preference="auto", top_n=1000),
                [MedicationInput(drug_name=approximate_name, tier_family="generic", day_supply=30)],
            ),
        ),
        (
            "multi_drug_chronic_regimen",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="75-84",
                    lis_status="partial",
                    pharmacy_preference="auto",
                    chronic_condition_flags=["diabetes", "copd", "heart_failure"],
                    top_n=1000,
                ),
                [
                    MedicationInput(drug_name=str(generic_drug["drug_name"]), tier_family="generic", day_supply=30),
                    MedicationInput(drug_name=str(brand_drug["drug_name"]), tier_family=str(brand_drug["tier_family"]), day_supply=30),
                    MedicationInput(drug_name=str(insulin_drug["drug_name"]), tier_family="brand", day_supply=30),
                ],
            ),
        ),
    ]

    for zip_row in zip_df.to_dict("records"):
        zipcode = str(zip_row["zip_code"])
        for bundle_name, factory in templates:
            beneficiary, meds = factory(zipcode)
            scenarios.append(
                ScenarioSpec(
                    scenario_id=f"{bundle_name}_{zipcode}",
                    scenario_bundle=bundle_name,
                    beneficiary=beneficiary,
                    medications=meds,
                )
            )
    return scenarios


def _filter_scenarios(
    scenarios: list[ScenarioSpec], scenario_bundles: list[str] | None
) -> list[ScenarioSpec]:
    if not scenario_bundles:
        return scenarios
    requested = {bundle.strip() for bundle in scenario_bundles if bundle.strip()}
    return [scenario for scenario in scenarios if scenario.scenario_bundle in requested]


def _table_exists(conn: duckdb.DuckDBPyConnection, full_name: str) -> bool:
    schema, table = full_name.split(".", 1)
    result = conn.execute(
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    ).fetchone()
    return bool(result and result[0] > 0)


def _tier_family_from_level(tier_level: float | int | None) -> str:
    try:
        value = int(float(tier_level))
    except (TypeError, ValueError):
        value = 3
    if value <= 2:
        return "generic"
    if value >= 5:
        return "specialty"
    return "brand"


def _build_synthetic_scenarios(
    conn: duckdb.DuckDBPyConnection,
    config: PipelineConfig,
) -> list[ScenarioSpec]:
    from .recommend import BeneficiaryInput, MedicationInput

    if not (
        _table_exists(conn, "synthetic.syn_beneficiary")
        and _table_exists(conn, "synthetic.syn_beneficiary_prescriptions")
    ):
        return []

    bene_limit = 40 if config.is_demo_profile else 200
    synthetic_df = _fetch_dataframe(
        conn,
        f"""
        SELECT
            b.bene_synth_id,
            b.zip_code,
            b.risk_segment,
            b.insulin_user_flag,
            p.ndc,
            p.rxcui,
            p.drug_name,
            p.days_supply_mode,
            p.qty_per_fill,
            p.fills_per_year,
            p.tier_level,
            p.source_mode
        FROM synthetic.syn_beneficiary b
        JOIN synthetic.syn_beneficiary_prescriptions p
          ON b.bene_synth_id = p.bene_synth_id
        WHERE b.zip_code IS NOT NULL
        ORDER BY b.bene_synth_id, p.ndc
        LIMIT {bene_limit * 8}
        """,
    )
    if synthetic_df.empty:
        return []

    scenarios: list[ScenarioSpec] = []
    for bene_id, group in synthetic_df.groupby("bene_synth_id"):
        first = group.iloc[0]
        zipcode = str(first["zip_code"]).strip()
        if not zipcode:
            continue
        insulin_user = int(first.get("insulin_user_flag", 0) or 0) == 1
        risk_segment = str(first.get("risk_segment", "MED")).strip().lower()
        source_mode = str(first.get("source_mode", "synthetic")).strip().lower() or "synthetic"
        medications = [
            MedicationInput(
                drug_name=(str(row["drug_name"]).strip() or None),
                rxcui=(str(row["rxcui"]).strip() or None),
                ndc=(str(row["ndc"]).strip() or None),
                tier_family=_tier_family_from_level(row["tier_level"]),
                day_supply=int(row["days_supply_mode"]),
                quantity_override=float(row["qty_per_fill"]) if not pd.isna(row["qty_per_fill"]) else None,
                fills_per_year_override=int(row["fills_per_year"]) if not pd.isna(row["fills_per_year"]) else None,
            )
            for _, row in group.iterrows()
        ]
        beneficiary = BeneficiaryInput(
            zipcode=zipcode,
            age_band="75-84" if risk_segment == "high" else "65-74",
            lis_status="partial" if source_mode == "pde" and insulin_user else "none",
            chronic_condition_flags=["diabetes"] if insulin_user else None,
            pharmacy_preference="auto",
            top_n=1000,
            user_role="counselor",
            decision_focus="coverage_first" if insulin_user else "balanced",
        )
        scenario_bundle = (
            "pde"
            if source_mode == "pde"
            else ("synthetic_insulin" if insulin_user else f"synthetic_{risk_segment}")
        )
        scenarios.append(
            ScenarioSpec(
                scenario_id=str(bene_id),
                scenario_bundle=scenario_bundle,
                beneficiary=beneficiary,
                medications=medications,
            )
        )
        if len(scenarios) >= bene_limit:
            break
    return scenarios


def _summarize_matches(matches: list[Any]) -> dict[str, float]:
    approximate = sum(1 for item in matches if item.match_confidence != "exact")
    exact = sum(1 for item in matches if item.match_confidence == "exact")
    preferred = sum(1 for item in matches if item.match_source in {"ndc", "rxcui", "exact_name", "synonym"})
    return {
        "approximate_match_count": float(approximate),
        "exact_match_count": float(exact),
        "preferred_match_count": float(preferred),
    }


def _monthly_cost_variance_features(recommendation: Any) -> dict[str, float]:
    monthly_drug_oop = np.zeros(12, dtype=float)
    monthly_premium = float(recommendation.annual_premium) / 12.0
    for breakdown in recommendation.drug_breakdowns:
        for trace in getattr(breakdown, "fill_traces", []):
            month_index = max(0, min(11, int(float(trace.day_offset) // 30)))
            monthly_drug_oop[month_index] += float(trace.final_oop)
    monthly_total = monthly_drug_oop + monthly_premium
    requested_drug_count = max(1, len(recommendation.drug_breakdowns))
    return {
        "priced_drug_share": float(recommendation.priced_drug_count / requested_drug_count),
        "monthly_drug_oop_variance": float(np.var(monthly_drug_oop)),
        "monthly_total_variance": float(np.var(monthly_total)),
    }


def _recommendations_to_feature_rows(
    conn: duckdb.DuckDBPyConnection,
    recommendations: list[Any],
    beneficiary: Any,
    scenario_id: str,
    scenario_bundle: str,
) -> list[dict[str, Any]]:
    if not recommendations:
        return []

    plan_keys = [recommendation.plan_key for recommendation in recommendations]
    placeholders = ", ".join("?" for _ in plan_keys)
    rec_features = _fetch_dataframe(
        conn,
        f"SELECT * FROM gold.recommendation_features WHERE plan_key IN ({placeholders})",
        plan_keys,
    )
    zip_df = _fetch_dataframe(
        conn,
        """
        SELECT coalesce(density_category, 'suburban') AS density_category
        FROM silver.dim_zipcode
        WHERE zip_code = ?
        LIMIT 1
        """,
        [beneficiary.zipcode.strip().zfill(5)],
    )
    zip_density_category = str(zip_df.iloc[0]["density_category"]) if not zip_df.empty else "suburban"
    rec_feature_lookup = {
        str(row["plan_key"]): row for row in rec_features.to_dict("records")
    }

    rows: list[dict[str, Any]] = []
    for recommendation in recommendations:
        feature_row = rec_feature_lookup.get(recommendation.plan_key, {})
        breakdowns = recommendation.drug_breakdowns
        requested_drug_count = max(1, len(breakdowns))
        covered_drug_count_request = sum(1 for item in breakdowns if item.coverage_status == "covered")
        excluded_count = sum(1 for item in breakdowns if item.coverage_status == "excluded")
        missing_price_count = sum(1 for item in breakdowns if item.coverage_status == "missing_price")
        channel_unavailable_count = sum(1 for item in breakdowns if item.coverage_status == "channel_unavailable")
        deductible_exposure_total = sum(float(item.deductible_exposure or 0.0) for item in breakdowns)
        initial_coverage_oop_total = sum(float(item.initial_coverage_oop or 0.0) for item in breakdowns)
        lis_adjusted_oop_total = sum(float(item.lis_adjusted_oop or 0.0) for item in breakdowns)
        negotiated_price_total = sum(float(item.negotiated_price_total or 0.0) for item in breakdowns)
        oop_cap_savings_total = sum(float(item.oop_cap_savings or 0.0) for item in breakdowns)
        mail_order_count = sum(1 for item in breakdowns if item.selected_channel in {"pref_mail", "nonpref_mail"})
        insulin_nonpreferred_dependency_count = sum(
            1
            for item in breakdowns
            if item.insulin_flag and item.selected_channel in {"nonpref_retail", "nonpref_mail"}
        )
        match_summary = _summarize_matches(recommendation.resolved_medications)
        monthly_variance = _monthly_cost_variance_features(recommendation)
        row = {
            "scenario_id": scenario_id,
            "scenario_bundle": scenario_bundle,
            "plan_key": recommendation.plan_key,
            "plan_name": recommendation.plan_name,
            "current_rules_rank": float(recommendation.plan_rank),
            "current_rules_score": float(recommendation.rules_score),
            "fit_score": float(recommendation.fit_score),
            "cost_score": float(recommendation.fit_metrics.cost_score),
            "premium_score": float(recommendation.fit_metrics.premium_score),
            "coverage_score": float(recommendation.fit_metrics.coverage_score),
            "access_score": float(recommendation.fit_metrics.access_score),
            "stability_score": float(recommendation.fit_metrics.stability_score),
            "annual_premium": float(recommendation.annual_premium),
            "annual_drug_oop": float(recommendation.annual_drug_oop),
            "annual_total_cost": float(recommendation.annual_total_cost),
            "coverage_status": recommendation.coverage_status,
            "requested_drug_count": float(requested_drug_count),
            "covered_drug_count_request": float(covered_drug_count_request),
            "covered_drug_share": float(covered_drug_count_request / requested_drug_count),
            "priced_drug_share": monthly_variance["priced_drug_share"],
            "uncovered_drug_count": float(recommendation.uncovered_drug_count),
            "uncovered_drug_share": float(recommendation.uncovered_drug_count / requested_drug_count),
            "priced_drug_count": float(recommendation.priced_drug_count),
            "restriction_count": float(recommendation.restriction_count),
            "deductible_exposure_total": float(deductible_exposure_total),
            "initial_coverage_oop_total": float(initial_coverage_oop_total),
            "lis_adjusted_oop_total": float(lis_adjusted_oop_total),
            "negotiated_price_total": float(negotiated_price_total),
            "oop_cap_savings_total": float(oop_cap_savings_total),
            "excluded_drug_count": float(excluded_count),
            "excluded_drug_share": float(excluded_count / requested_drug_count),
            "missing_price_drug_count": float(missing_price_count),
            "missing_price_drug_share": float(missing_price_count / requested_drug_count),
            "channel_unavailable_count": float(channel_unavailable_count),
            "channel_unavailable_share": float(channel_unavailable_count / requested_drug_count),
            "mail_order_dependency_flag": float(1 if mail_order_count > 0 else 0),
            "mail_order_dependency_share": float(mail_order_count / requested_drug_count),
            "monthly_drug_oop_variance": monthly_variance["monthly_drug_oop_variance"],
            "monthly_total_variance": monthly_variance["monthly_total_variance"],
            "channel_switch_count": float(recommendation.channel_switch_count),
            "insulin_risk_flag": float(1 if recommendation.insulin_flag else 0),
            "insulin_nonpreferred_dependency_count": float(insulin_nonpreferred_dependency_count),
            "insulin_nonpreferred_dependency_share": float(insulin_nonpreferred_dependency_count / requested_drug_count),
            "approximate_match_count": match_summary["approximate_match_count"],
            "exact_match_count": match_summary["exact_match_count"],
            "preferred_match_count": match_summary["preferred_match_count"],
            "network_flag": recommendation.network_flag,
            "network_risk_score": NETWORK_RISK_MAP.get(recommendation.network_flag, 1.0),
            "lis_status": beneficiary.lis_status,
            "age_band": beneficiary.age_band,
            "pharmacy_preference": beneficiary.pharmacy_preference,
            "zip_density_category": zip_density_category,
            "zipcode_density_score": _density_score(zip_density_category),
            "beneficiary_chronic_condition_count": float(len(beneficiary.chronic_condition_flags or [])),
            "nearest_preferred_distance_bucket": _distance_bucket(recommendation.nearest_preferred_distance_miles),
            "in_area_pharmacies": float(feature_row.get("in_area_pharmacies") or 0.0),
            "preferred_retail_count": float(feature_row.get("preferred_retail_count") or 0.0),
            "preferred_mail_count": float(feature_row.get("preferred_mail_count") or 0.0),
            "covered_drug_count": float(feature_row.get("covered_drug_count") or 0.0),
            "insulin_drug_count": float(feature_row.get("insulin_drug_count") or 0.0),
            "pa_rate": float(feature_row.get("pa_rate") or 0.0),
            "st_rate": float(feature_row.get("st_rate") or 0.0),
            "ql_rate": float(feature_row.get("ql_rate") or 0.0),
            "excluded_rate": float(feature_row.get("excluded_rate") or 0.0),
            "deductible": float(feature_row.get("deductible") or 0.0),
            "served_counties": float(feature_row.get("served_counties") or 0.0),
            "contract_year": float(recommendation.contract_year or 0.0),
            "benefit_design": recommendation.benefit_design,
            "simulation_policy": recommendation.simulation_policy,
            "feature_version": recommendation.feature_version,
        }
        rows.append(row)
    return rows


def build_training_dataset(
    config: PipelineConfig | None = None,
    output_path: Path | None = None,
    scenario_bundles: list[str] | None = None,
) -> Path:
    from .recommend import recommend_plans

    active_config = config or PipelineConfig()
    active_config.ensure_directories()
    conn = _connect(active_config)
    synthetic_scenarios = _filter_scenarios(_build_synthetic_scenarios(conn, active_config), scenario_bundles)
    fallback_scenarios = _filter_scenarios(_build_default_scenarios(active_config), scenario_bundles)
    scenarios = synthetic_scenarios if synthetic_scenarios else fallback_scenarios
    rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        recommendations = recommend_plans(
            scenario.beneficiary,
            scenario.medications,
            config=active_config,
            ranking_mode="rules",
        )
        rows.extend(
            _recommendations_to_feature_rows(
                conn,
                recommendations,
                scenario.beneficiary,
                scenario.scenario_id,
                scenario.scenario_bundle,
            )
        )
    conn.close()

    if not rows:
        raise ValueError("No rows were generated for the hybrid reranker dataset.")

    frame = pd.DataFrame(rows)
    frame["weak_label_score"] = frame.apply(_weak_label_score, axis=1)
    frame["heuristic_score"] = frame.apply(_heuristic_score, axis=1)
    relevance_frames: list[pd.DataFrame] = []
    for _, group in frame.groupby("scenario_id"):
        relevance_frames.append(_scenario_relevance(group))
    relevance_df = pd.concat(relevance_frames, ignore_index=True)
    frame = frame.merge(relevance_df, on=["scenario_id", "plan_key"], how="left")
    frame = frame.sort_values(["scenario_id", "current_rules_rank"]).reset_index(drop=True)

    path = output_path or active_config.training_dataset_path
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)

    metadata = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "weak_label_version": WEAK_LABEL_VERSION,
        "feature_version": str(frame["feature_version"].iloc[0]) if "feature_version" in frame.columns else "unknown",
        "rows": int(len(frame)),
        "scenario_count": int(frame["scenario_id"].nunique()),
        "scenario_bundles": sorted(frame["scenario_bundle"].unique().tolist()),
        "snapshot_quarter": active_config.snapshot_quarter,
        "build_profile": active_config.build_profile,
        "scenario_source": "synthetic" if synthetic_scenarios else "default",
    }
    metadata_path = _dataset_metadata_path(path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("wrote hybrid training dataset rows=%s path=%s", len(frame), path)
    return path


def _feature_subset_columns(feature_subset: str) -> tuple[list[str], list[str]]:
    subset = FEATURE_SUBSETS.get(feature_subset)
    if subset is None:
        raise ValueError(f"Unsupported feature subset: {feature_subset}")
    return subset["numeric"], subset["categorical"]


def _encode_feature_frame(
    frame: pd.DataFrame,
    numeric_columns: list[str],
    categorical_columns: list[str],
    feature_names: list[str] | None = None,
) -> tuple[np.ndarray, list[str]]:
    numeric = frame.reindex(columns=numeric_columns, fill_value=0.0).fillna(0.0).astype(float)
    categorical = pd.get_dummies(
        frame.reindex(columns=categorical_columns, fill_value="missing").fillna("missing"),
        prefix=categorical_columns,
    )
    combined = pd.concat([numeric, categorical], axis=1)
    if feature_names is None:
        feature_names = combined.columns.tolist()
    else:
        combined = combined.reindex(columns=feature_names, fill_value=0.0)
    return combined.to_numpy(dtype=float), combined.columns.tolist()


def _fit_ridge_regression(matrix: np.ndarray, targets: np.ndarray, alpha: float) -> tuple[np.ndarray, float]:
    intercept_column = np.ones((matrix.shape[0], 1), dtype=float)
    design = np.hstack([intercept_column, matrix])
    penalty = alpha * np.eye(design.shape[1], dtype=float)
    penalty[0, 0] = 0.0
    solution = np.linalg.pinv(design.T @ design + penalty) @ design.T @ targets
    intercept = float(solution[0])
    weights = solution[1:].astype(float)
    return weights, intercept


def _fit_linear_artifact(
    frame: pd.DataFrame,
    config: PipelineConfig,
    feature_subset: str,
    alpha: float,
) -> HybridRerankerArtifact:
    numeric_columns, categorical_columns = _feature_subset_columns(feature_subset)
    matrix, feature_names = _encode_feature_frame(frame, numeric_columns, categorical_columns)
    means = matrix.mean(axis=0)
    scales = matrix.std(axis=0)
    scales[scales == 0] = 1.0
    standardized = (matrix - means) / scales
    targets = frame["weak_label_score"].to_numpy(dtype=float)
    weights, intercept = _fit_ridge_regression(standardized, targets, alpha=alpha)
    return HybridRerankerArtifact(
        snapshot_quarter=config.snapshot_quarter,
        build_profile=config.build_profile,
        model_type=LINEAR_MODEL_TYPE,
        feature_names=feature_names,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        weak_label_version=WEAK_LABEL_VERSION,
        feature_version=str(frame["feature_version"].iloc[0]),
        feature_subset=feature_subset,
        metadata={
            "training_rows": int(len(frame)),
            "scenario_count": int(frame["scenario_id"].nunique()),
        },
        means=means.tolist(),
        scales=scales.tolist(),
        weights=weights.tolist(),
        intercept=intercept,
        alpha=alpha,
    )


def _target_sse(values: np.ndarray) -> float:
    if values.size == 0:
        return 0.0
    mean = float(values.mean())
    diff = values - mean
    return float(diff @ diff)


def _candidate_thresholds(values: np.ndarray) -> np.ndarray:
    unique = np.unique(values)
    if unique.size <= 1:
        return np.array([], dtype=float)
    if unique.size <= 16:
        return (unique[:-1] + unique[1:]) / 2.0
    quantiles = np.unique(np.quantile(unique, np.linspace(0.1, 0.9, 9)))
    return quantiles.astype(float)


def _fit_regression_tree(
    matrix: np.ndarray,
    targets: np.ndarray,
    depth: int,
    min_samples_leaf: int,
) -> dict[str, Any]:
    node_value = float(targets.mean()) if targets.size else 0.0
    if depth <= 0 or targets.size < max(2 * min_samples_leaf, 4) or np.allclose(targets, targets[:1]):
        return {"value": node_value}

    best_feature = None
    best_threshold = None
    best_loss = math.inf
    best_left = None
    best_right = None
    for feature_index in range(matrix.shape[1]):
        feature_values = matrix[:, feature_index]
        for threshold in _candidate_thresholds(feature_values):
            left_mask = feature_values <= threshold
            right_mask = ~left_mask
            if left_mask.sum() < min_samples_leaf or right_mask.sum() < min_samples_leaf:
                continue
            loss = _target_sse(targets[left_mask]) + _target_sse(targets[right_mask])
            if loss < best_loss:
                best_loss = loss
                best_feature = feature_index
                best_threshold = float(threshold)
                best_left = left_mask
                best_right = right_mask

    if best_feature is None or best_left is None or best_right is None:
        return {"value": node_value}

    return {
        "feature_index": int(best_feature),
        "threshold": float(best_threshold),
        "value": node_value,
        "left": _fit_regression_tree(matrix[best_left], targets[best_left], depth - 1, min_samples_leaf),
        "right": _fit_regression_tree(matrix[best_right], targets[best_right], depth - 1, min_samples_leaf),
    }


def _predict_tree(tree: dict[str, Any], matrix: np.ndarray) -> np.ndarray:
    if "left" not in tree or "right" not in tree:
        return np.full(matrix.shape[0], float(tree["value"]), dtype=float)
    feature_index = int(tree["feature_index"])
    threshold = float(tree["threshold"])
    left_mask = matrix[:, feature_index] <= threshold
    right_mask = ~left_mask
    predictions = np.empty(matrix.shape[0], dtype=float)
    predictions[left_mask] = _predict_tree(tree["left"], matrix[left_mask])
    predictions[right_mask] = _predict_tree(tree["right"], matrix[right_mask])
    return predictions


def _predict_tree_ensemble(
    matrix: np.ndarray,
    trees: list[dict[str, Any]],
    base_value: float,
    learning_rate: float,
) -> np.ndarray:
    predictions = np.full(matrix.shape[0], base_value, dtype=float)
    for tree in trees:
        predictions += learning_rate * _predict_tree(tree, matrix)
    return predictions


def _fit_tree_ensemble(
    matrix: np.ndarray,
    targets: np.ndarray,
    *,
    learning_rate: float,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
) -> tuple[list[dict[str, Any]], float]:
    base_value = float(targets.mean()) if targets.size else 0.0
    predictions = np.full(targets.shape[0], base_value, dtype=float)
    trees: list[dict[str, Any]] = []
    for _ in range(n_estimators):
        residuals = targets - predictions
        tree = _fit_regression_tree(matrix, residuals, max_depth, min_samples_leaf)
        tree_pred = _predict_tree(tree, matrix)
        if np.allclose(tree_pred, 0.0):
            break
        predictions += learning_rate * tree_pred
        trees.append(tree)
    return trees, base_value


def _fit_tree_artifact(
    frame: pd.DataFrame,
    config: PipelineConfig,
    feature_subset: str,
    *,
    learning_rate: float,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
) -> HybridRerankerArtifact:
    numeric_columns, categorical_columns = _feature_subset_columns(feature_subset)
    matrix, feature_names = _encode_feature_frame(frame, numeric_columns, categorical_columns)
    targets = frame["weak_label_score"].to_numpy(dtype=float)
    trees, base_value = _fit_tree_ensemble(
        matrix,
        targets,
        learning_rate=learning_rate,
        n_estimators=n_estimators,
        max_depth=max_depth,
        min_samples_leaf=min_samples_leaf,
    )
    return HybridRerankerArtifact(
        snapshot_quarter=config.snapshot_quarter,
        build_profile=config.build_profile,
        model_type=TREE_MODEL_TYPE,
        feature_names=feature_names,
        numeric_columns=numeric_columns,
        categorical_columns=categorical_columns,
        dataset_schema_version=DATASET_SCHEMA_VERSION,
        weak_label_version=WEAK_LABEL_VERSION,
        feature_version=str(frame["feature_version"].iloc[0]),
        feature_subset=feature_subset,
        metadata={
            "training_rows": int(len(frame)),
            "scenario_count": int(frame["scenario_id"].nunique()),
            "tree_count": int(len(trees)),
            "max_depth": int(max_depth),
            "min_samples_leaf": int(min_samples_leaf),
        },
        base_value=base_value,
        learning_rate=learning_rate,
        trees=trees,
    )


def train_hybrid_reranker(
    config: PipelineConfig | None = None,
    dataset_path: Path | None = None,
    output_path: Path | None = None,
    *,
    model_type: str = TREE_MODEL_TYPE,
    feature_subset: str = "full",
    alpha: float = 5.0,
    learning_rate: float = 0.12,
    n_estimators: int = 40,
    max_depth: int = 3,
    min_samples_leaf: int = 5,
) -> Path:
    active_config = config or PipelineConfig()
    active_config.ensure_directories()
    path = dataset_path or active_config.training_dataset_path
    if not path.exists():
        path = build_training_dataset(active_config, output_path=path)
    frame = pd.read_csv(path)
    if model_type == LINEAR_MODEL_TYPE:
        artifact = _fit_linear_artifact(frame, active_config, feature_subset, alpha)
    else:
        artifact = _fit_tree_artifact(
            frame,
            active_config,
            feature_subset,
            learning_rate=learning_rate,
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_leaf=min_samples_leaf,
        )
    artifact_path = output_path or _artifact_path(active_config, model_type)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(artifact.to_dict(), indent=2), encoding="utf-8")
    logger.info("trained hybrid reranker rows=%s artifact=%s", len(frame), artifact_path)
    return artifact_path


def load_hybrid_reranker(artifact_path: Path) -> HybridRerankerArtifact:
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    return HybridRerankerArtifact(**payload)


def _ndcg_at_k(relevances: list[float], k: int) -> float:
    actual = np.array(relevances[:k], dtype=float)
    if actual.size == 0:
        return 0.0
    discounts = 1.0 / np.log2(np.arange(2, actual.size + 2))
    dcg = float(np.sum((2 ** actual - 1) * discounts))
    ideal = np.sort(actual)[::-1]
    idcg = float(np.sum((2 ** ideal - 1) * discounts))
    return dcg / idcg if idcg else 0.0


def _top_overlap(ordering: list[str], truth: list[str], k: int) -> float:
    top_pred = set(ordering[:k])
    top_truth = set(truth[:k])
    denom = max(1, min(k, len(top_truth)))
    return len(top_pred & top_truth) / denom


def _summarize_metric_frames(metric_frames: dict[str, list[dict[str, float]]]) -> dict[str, dict[str, float]]:
    summary: dict[str, dict[str, float]] = {}
    for system_name, metrics in metric_frames.items():
        metric_frame = pd.DataFrame(metrics)
        summary[system_name] = {column: float(metric_frame[column].mean()) for column in metric_frame.columns}
    return summary


def _split_frame_by_scenario(
    frame: pd.DataFrame,
    *,
    test_fraction: float = EVALUATION_TEST_FRACTION,
    seed: int = EVALUATION_SPLIT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    scenario_ids = sorted(frame["scenario_id"].dropna().astype(str).unique().tolist())
    if len(scenario_ids) < 2:
        raise ValueError("Need at least two scenarios for held-out evaluation.")

    shuffled = np.array(scenario_ids, dtype=object)
    np.random.default_rng(seed).shuffle(shuffled)
    test_count = max(1, int(math.ceil(len(shuffled) * test_fraction)))
    if test_count >= len(shuffled):
        test_count = len(shuffled) - 1
    test_scenarios = sorted(str(item) for item in shuffled[:test_count].tolist())
    test_scenario_set = set(test_scenarios)
    scenario_labels = frame["scenario_id"].astype(str)
    test_frame = frame.loc[scenario_labels.isin(test_scenario_set)].copy()
    train_frame = frame.loc[~scenario_labels.isin(test_scenario_set)].copy()
    if train_frame.empty or test_frame.empty:
        raise ValueError("Unable to create non-empty train/test scenario splits for evaluation.")
    train_scenarios = sorted(train_frame["scenario_id"].astype(str).unique().tolist())
    return train_frame, test_frame, train_scenarios, test_scenarios


def _collect_system_metrics(
    frame: pd.DataFrame,
    orderings_by_system: dict[str, str],
) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, dict[str, float]]]]:
    overall: dict[str, list[dict[str, float]]] = {name: [] for name in orderings_by_system}
    by_bundle: dict[str, dict[str, list[dict[str, float]]]] = {}
    for _, group in frame.groupby("scenario_id"):
        truth = group.sort_values(["weak_label_score", "annual_total_cost"], ascending=[False, True])
        truth_plan_keys = truth["plan_key"].tolist()
        truth_relevance_map = {
            str(row.plan_key): float(row.weak_label_relevance) for row in truth.itertuples()
        }
        bundle = str(group.iloc[0]["scenario_bundle"])
        by_bundle.setdefault(bundle, {name: [] for name in orderings_by_system})
        for system_name, score_column in orderings_by_system.items():
            if score_column == "current_rules_rank":
                ordered = group.sort_values(["current_rules_rank", "annual_total_cost"]).copy()
            elif score_column == "heuristic_score":
                ordered = group.sort_values(["coverage_status", "heuristic_score"], ascending=[True, False]).copy()
            else:
                ordered = group.sort_values(["coverage_status", score_column], ascending=[True, False]).copy()
            ordered_keys = ordered["plan_key"].tolist()
            relevances = [truth_relevance_map[key] for key in ordered_keys]
            top5 = ordered.head(5)
            top10 = ordered.head(10)
            metrics = {
                "top1_agreement": 1.0 if ordered_keys[:1] == truth_plan_keys[:1] else 0.0,
                "top5_overlap": _top_overlap(ordered_keys, truth_plan_keys, 5),
                "top10_overlap": _top_overlap(ordered_keys, truth_plan_keys, 10),
                "ndcg_5": _ndcg_at_k(relevances, 5),
                "ndcg_10": _ndcg_at_k(relevances, 10),
                "top5_full_coverage_rate": float((top5["coverage_status"] == "full").mean()) if not top5.empty else 0.0,
                "top10_full_coverage_rate": float((top10["coverage_status"] == "full").mean()) if not top10.empty else 0.0,
                "top5_avg_total_cost": float(top5["annual_total_cost"].mean()) if not top5.empty else 0.0,
                "top10_avg_total_cost": float(top10["annual_total_cost"].mean()) if not top10.empty else 0.0,
                "top5_avg_uncovered": float(top5["uncovered_drug_count"].mean()) if not top5.empty else 0.0,
            }
            overall[system_name].append(metrics)
            by_bundle[bundle][system_name].append(metrics)
    overall_summary = _summarize_metric_frames(overall)
    bundle_summary = {
        bundle: _summarize_metric_frames(system_metrics)
        for bundle, system_metrics in by_bundle.items()
    }
    return overall_summary, bundle_summary


def evaluate_hybrid_reranker(
    config: PipelineConfig | None = None,
    dataset_path: Path | None = None,
    artifact_path: Path | None = None,
    output_path: Path | None = None,
    *,
    scenario_bundles: list[str] | None = None,
    baseline_only: bool = False,
) -> dict[str, Any]:
    active_config = config or PipelineConfig()
    dataset = dataset_path or active_config.training_dataset_path
    if not dataset.exists():
        dataset = build_training_dataset(active_config, output_path=dataset, scenario_bundles=scenario_bundles)

    frame = pd.read_csv(dataset)
    if scenario_bundles:
        frame = frame[frame["scenario_bundle"].isin(scenario_bundles)].copy()
    if frame.empty:
        raise ValueError("No rows available for evaluation after scenario-bundle filtering.")

    train_frame, test_frame, train_scenarios, test_scenarios = _split_frame_by_scenario(frame)
    evaluation_frame = test_frame.copy()

    linear_artifact = _fit_linear_artifact(train_frame, active_config, "full", alpha=5.0)
    evaluation_frame["predicted_linear_score"] = linear_artifact.predict(evaluation_frame)
    if artifact_path is not None:
        logger.info("evaluation uses held-out train/test fitting and does not reuse artifact=%s", artifact_path)

    ablation_predictions: dict[str, str] = {}
    if not baseline_only:
        tree_artifact = _fit_tree_artifact(
            train_frame,
            active_config,
            "full",
            learning_rate=0.12,
            n_estimators=40,
            max_depth=3,
            min_samples_leaf=5,
        )
        evaluation_frame["predicted_tree_score"] = tree_artifact.predict(evaluation_frame)
        for subset in ("cost_only", "cost_plus_restrictions", "cost_plus_restrictions_network", "full"):
            ablation_artifact = _fit_tree_artifact(
                train_frame,
                active_config,
                subset,
                learning_rate=0.12,
                n_estimators=30,
                max_depth=3,
                min_samples_leaf=5,
            )
            column_name = f"predicted_ablation_{subset}"
            evaluation_frame[column_name] = ablation_artifact.predict(evaluation_frame)
            ablation_predictions[subset] = column_name

    orderings_by_system = {
        "rules_only": "current_rules_rank",
        "heuristic_baseline": "heuristic_score",
        "linear_reranker": "predicted_linear_score",
    }
    if not baseline_only:
        orderings_by_system["tree_reranker"] = "predicted_tree_score"
        orderings_by_system.update(
            {
                f"ablation_{subset}": column_name
                for subset, column_name in ablation_predictions.items()
            }
        )

    systems_summary, bundle_summary = _collect_system_metrics(evaluation_frame, orderings_by_system)
    rules_metrics = systems_summary["rules_only"]
    comparison_target = systems_summary["tree_reranker"] if not baseline_only else systems_summary["linear_reranker"]
    summary: dict[str, Any] = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "weak_label_version": WEAK_LABEL_VERSION,
        "evaluation_mode": "held_out_by_scenario",
        "split_seed": EVALUATION_SPLIT_SEED,
        "test_fraction": EVALUATION_TEST_FRACTION,
        "systems": systems_summary,
        "scenario_bundle_metrics": bundle_summary,
        "acceptance": {
            "top5_improved": comparison_target["top5_overlap"] >= rules_metrics["top5_overlap"],
            "top10_improved": comparison_target["top10_overlap"] >= rules_metrics["top10_overlap"],
            "uncovered_not_worse": comparison_target["top5_avg_uncovered"] <= rules_metrics["top5_avg_uncovered"],
        },
        "dataset_rows": int(len(frame)),
        "scenario_count": int(frame["scenario_id"].nunique()),
        "train_rows": int(len(train_frame)),
        "test_rows": int(len(evaluation_frame)),
        "train_scenario_count": int(len(train_scenarios)),
        "test_scenario_count": int(len(test_scenarios)),
        "train_scenarios": train_scenarios,
        "test_scenarios": test_scenarios,
    }

    report_path = output_path or _evaluation_report_path(active_config, TREE_MODEL_TYPE if not baseline_only else LINEAR_MODEL_TYPE)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    research_report_path = _research_report_path(active_config)
    research_report_path.parent.mkdir(parents=True, exist_ok=True)
    research_report_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("evaluated hybrid reranker report=%s", report_path)
    return summary


def build_inference_feature_frame(
    recommendations: list[Any],
    beneficiary: Any,
    config: PipelineConfig,
) -> pd.DataFrame:
    conn = _connect(config)
    rows = _recommendations_to_feature_rows(
        conn,
        recommendations,
        beneficiary,
        scenario_id="inference",
        scenario_bundle="inference",
    )
    conn.close()
    return pd.DataFrame(rows)


def _confidence_bucket(scores: list[float]) -> list[str]:
    if not scores:
        return []
    top_score = scores[0]
    buckets: list[str] = []
    for score in scores:
        margin = top_score - score
        if margin <= 5:
            buckets.append("high")
        elif margin <= 25:
            buckets.append("medium")
        else:
            buckets.append("low")
    return buckets


def _hybrid_bucket_index(recommendation: Any) -> int:
    requested_drug_count = max(1, len(recommendation.drug_breakdowns))
    if recommendation.coverage_status == "full" and recommendation.priced_drug_count >= requested_drug_count:
        return 0
    if recommendation.priced_drug_count > 0:
        return 1
    return 2


def apply_hybrid_reranking(
    recommendations: list[Any],
    beneficiary: Any,
    config: PipelineConfig | None = None,
    artifact_path: Path | None = None,
) -> list[Any]:
    if not recommendations:
        return []
    active_config = config or PipelineConfig()
    artifact_file = artifact_path or _artifact_path(active_config, TREE_MODEL_TYPE)
    if not artifact_file.exists():
        logger.warning("hybrid reranker artifact missing, falling back to rules-only ranking")
        return recommendations

    artifact = load_hybrid_reranker(artifact_file)
    frame = build_inference_feature_frame(recommendations, beneficiary, active_config)
    if frame.empty:
        return recommendations

    score_lookup = {
        str(plan_key): float(score)
        for plan_key, score in zip(frame["plan_key"].tolist(), artifact.predict(frame), strict=False)
    }

    grouped: dict[int, list[Any]] = {0: [], 1: [], 2: []}
    for recommendation in recommendations:
        recommendation.model_score = score_lookup.get(recommendation.plan_key)
        recommendation.ranking_source = "hybrid_reranker"
        recommendation.feature_version = artifact.feature_version
        grouped[_hybrid_bucket_index(recommendation)].append(recommendation)

    reranked: list[Any] = []
    for bucket_index in (0, 1, 2):
        ordered = sorted(
            grouped[bucket_index],
            key=lambda item: (
                -(item.model_score if item.model_score is not None else float("-inf")),
                -float(item.priced_drug_count),
                -float(item.rules_score),
                item.annual_total_cost,
                item.uncovered_drug_count,
                item.restriction_count,
                item.plan_name,
            ),
        )
        reranked.extend(ordered)

    confidence_lookup = _confidence_bucket([item.model_score or 0.0 for item in reranked])
    for rank, recommendation in enumerate(reranked, start=1):
        recommendation.plan_rank = rank
        recommendation.model_confidence_bucket = confidence_lookup[rank - 1]
    return reranked
