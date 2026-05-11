from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import json
import logging
import math
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .config import PipelineConfig
from .scenario_generation import (
    DEFAULT_GENERATOR_SEED,
    GENERATION_VERSION,
    generate_training_scenarios,
    load_materialized_scenarios,
)


logger = logging.getLogger(__name__)

DATASET_SCHEMA_VERSION = "request_features_v4"
WEAK_LABEL_VERSION = "weak_label_v2"
TREE_MODEL_TYPE = "tree"
LINEAR_MODEL_TYPE = "linear"
NETWORK_RISK_MAP = {
    "adequate": 0.0,
    "limited_preferred_retail": 1.0,
    "no_preferred_retail": 2.0,
    "unknown": 1.5,
}
BASE_SCENARIO_COUNT = {
    "demo": 6,
    "full": 50,
}
SCENARIO_PRECISION_TARGET = 300
EVALUATION_SPLIT_SEED = 42
EVALUATION_TEST_FRACTION = 0.3
DEFAULT_SCENARIO_SOURCE_STRATEGY = "mixed"
DEFAULT_TEACHER_FEATURE_POLICY = "student_safe"
SUPPORTED_TEACHER_FEATURE_POLICIES = {"student_safe", "teacher_features"}
DEFAULT_FULL_DATASET_BUILD_WORKERS = 4
DEFAULT_DEMO_DATASET_BUILD_WORKERS = 2
DEFAULT_DATASET_CHUNK_SIZE = 10
DEFAULT_WORKER_MAX_TASKS_PER_CHILD = 1
DEFAULT_STALE_CHUNK_HOURS = 6
DATASET_CHUNK_MANIFEST_VERSION = "dataset_chunks_v2"
TEACHER_NUMERIC_COLUMNS = [
    "current_rules_rank",
    "current_rules_score",
    "fit_score",
    "cost_score",
    "premium_score",
    "coverage_score",
    "access_score",
    "stability_score",
]

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
    "match_review_required_flag",
    "unknown_network_data_flag",
    "unsafe_reason_count",
    "candidate_plan_count_service_area",
    "candidate_plan_count_ranked",
    "plans_with_unknown_network_count",
    "plans_dropped_due_to_missing_data",
]

MODEL_CATEGORICAL_COLUMNS = [
    "coverage_status",
    "network_flag",
    "lis_status",
    "age_band",
    "pharmacy_preference",
    "zip_density_category",
    "scenario_bundle",
    "scenario_profile",
    "fallback_group",
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
    teacher_feature_policy: str = DEFAULT_TEACHER_FEATURE_POLICY
    metadata: dict[str, Any] = field(default_factory=dict)
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


def _choose_drug(
    conn: duckdb.DuckDBPyConnection,
    where_sql: str,
    *,
    order_by: str = "drug_name",
) -> dict[str, Any] | None:
    df = _fetch_dataframe(
        conn,
        f"""
        SELECT
            drug_name,
            ndc,
            rxcui,
            tier_family,
            is_insulin,
            days_supply,
            has_prior_auth,
            has_step_therapy,
            has_quantity_limit,
            unit_cost
        FROM gold.plan_drug_cost_basis
        WHERE drug_name IS NOT NULL
          AND ndc IS NOT NULL
          AND {where_sql}
        ORDER BY {order_by}
        LIMIT 1
        """
    )
    if df.empty:
        return None
    return df.iloc[0].to_dict()


def _query_scenario_inputs(
    conn: duckdb.DuckDBPyConnection, config: PipelineConfig
) -> tuple[dict[str, dict[str, Any]], pd.DataFrame]:
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
    specialty_drug = _choose_drug(conn, "tier_family = 'specialty'", order_by="coalesce(unit_cost, 0) DESC, drug_name")
    restricted_drug = _choose_drug(
        conn,
        "has_prior_auth = TRUE OR has_step_therapy = TRUE OR has_quantity_limit = TRUE",
        order_by="coalesce(unit_cost, 0) DESC, drug_name",
    )
    fallback_drug = generic_drug or brand_drug or insulin_drug or specialty_drug or restricted_drug or _choose_drug(conn, "TRUE")
    generic_drug = generic_drug or fallback_drug
    brand_drug = brand_drug or fallback_drug
    insulin_drug = insulin_drug or brand_drug or fallback_drug
    specialty_drug = specialty_drug or restricted_drug or brand_drug or insulin_drug or fallback_drug
    restricted_drug = restricted_drug or specialty_drug or brand_drug or insulin_drug or fallback_drug
    archetypes = {
        "generic": generic_drug,
        "brand": brand_drug,
        "insulin": insulin_drug,
        "specialty": specialty_drug,
        "restricted": restricted_drug,
    }
    if not any(archetypes.values()):
        raise ValueError("No eligible drugs found in gold.plan_drug_cost_basis for scenario generation.")
    return archetypes, zip_df


def _build_default_scenarios(config: PipelineConfig) -> list[ScenarioSpec]:
    from .recommend import BeneficiaryInput, MedicationInput

    conn = _connect(config)
    archetypes, zip_df = _query_scenario_inputs(conn, config)
    conn.close()

    generic_drug = archetypes["generic"]
    brand_drug = archetypes["brand"]
    insulin_drug = archetypes["insulin"]
    specialty_drug = archetypes["specialty"]
    restricted_drug = archetypes["restricted"]

    def _scenario_day_supply(drug: dict[str, Any] | None, default: int = 30) -> int:
        try:
            value = int(float((drug or {}).get("days_supply") or default))
        except (TypeError, ValueError):
            value = default
        return value if value in {30, 60, 90} else default

    def _medication_from_drug(
        drug: dict[str, Any] | None,
        *,
        tier_family: str | None = None,
        day_supply: int | None = None,
    ) -> MedicationInput:
        if not drug:
            raise ValueError("Scenario generation could not find a reference drug.")
        return MedicationInput(
            drug_name=str(drug.get("drug_name") or ""),
            rxcui=str(drug.get("rxcui") or "") or None,
            ndc=str(drug.get("ndc") or "") or None,
            tier_family=str(tier_family or drug.get("tier_family") or "brand"),
            day_supply=day_supply or _scenario_day_supply(drug),
        )

    scenarios: list[ScenarioSpec] = []
    templates = [
        (
            "low_generic",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="65-74",
                    lis_status="none",
                    pharmacy_preference="auto",
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="balanced",
                ),
                [_medication_from_drug(generic_drug, tier_family="generic", day_supply=30)],
            ),
        ),
        (
            "maintenance_brand",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="75-84",
                    lis_status="none",
                    pharmacy_preference="auto",
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="coverage_first",
                ),
                [_medication_from_drug(brand_drug, day_supply=90)],
            ),
        ),
        (
            "insulin_only",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="65-74",
                    lis_status="partial",
                    pharmacy_preference="auto",
                    chronic_condition_flags=["diabetes"],
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="coverage_first",
                ),
                [_medication_from_drug(insulin_drug, tier_family="brand", day_supply=30)],
            ),
        ),
        (
            "insulin_plus_chronic",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="75-84",
                    lis_status="partial",
                    pharmacy_preference="auto",
                    chronic_condition_flags=["diabetes", "heart_failure"],
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="coverage_first",
                ),
                [
                    _medication_from_drug(insulin_drug, tier_family="brand", day_supply=30),
                    _medication_from_drug(generic_drug, tier_family="generic", day_supply=30),
                    _medication_from_drug(brand_drug, day_supply=30),
                ],
            ),
        ),
        (
            "specialty_high_cost",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="75-84",
                    lis_status="none",
                    pharmacy_preference="auto",
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="coverage_first",
                ),
                [
                    _medication_from_drug(specialty_drug, tier_family="specialty", day_supply=30),
                    _medication_from_drug(restricted_drug, day_supply=30),
                ],
            ),
        ),
        (
            "rural_access_sensitive",
            lambda zipcode: (
                BeneficiaryInput(
                    zipcode=zipcode,
                    age_band="85+",
                    lis_status="none",
                    pharmacy_preference="retail",
                    top_n=1000,
                    user_role="counselor",
                    decision_focus="coverage_first",
                ),
                [
                    _medication_from_drug(brand_drug, day_supply=30),
                    _medication_from_drug(generic_drug, tier_family="generic", day_supply=30),
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


def _fallback_group_for_recommendation(recommendation: Any) -> str:
    if recommendation.coverage_status == "full":
        return "full_coverage"
    unsafe_reasons = {str(value) for value in getattr(recommendation, "unsafe_reasons", [])}
    if recommendation.network_flag == "unknown" or "unknown_network_data" in unsafe_reasons:
        return "network_unknown"
    if (
        recommendation.network_flag in {"no_preferred_retail", "limited_preferred_retail"}
        or "long_preferred_distance" in unsafe_reasons
        or "no_usable_channel" in unsafe_reasons
    ):
        return "access_blocked"
    if recommendation.priced_drug_count == 0 or recommendation.uncovered_drug_count >= len(recommendation.drug_breakdowns):
        return "never_local_coverable"
    return "not_jointly_coverable"


def _recommendations_to_feature_rows(
    conn: duckdb.DuckDBPyConnection,
    recommendations: list[Any],
    beneficiary: Any,
    scenario_id: str,
    scenario_bundle: str,
    *,
    regimen_signature: str = "",
    scenario_source_kind: str = "benchmark",
    scenario_source_label: str = "benchmark_pool",
    intended_profile: str = "",
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
    candidate_plan_count_service_area = float(len(recommendations))
    candidate_plan_count_ranked = float(len(recommendations))
    plans_with_unknown_network_count = float(sum(1 for item in recommendations if item.network_flag == "unknown"))
    plans_dropped_due_to_missing_data = max(0.0, candidate_plan_count_service_area - candidate_plan_count_ranked)

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
            "scenario_source_kind": scenario_source_kind,
            "scenario_source_label": scenario_source_label,
            "intended_profile": intended_profile or scenario_bundle,
            "beneficiary_zipcode": beneficiary.zipcode,
            "regimen_signature": regimen_signature,
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
            "scenario_profile": str(getattr(recommendation, "scenario_profile", "") or "low_utilizer"),
            "fallback_group": _fallback_group_for_recommendation(recommendation),
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
            "match_review_required_flag": float(1 if getattr(recommendation, "match_review_required", False) else 0),
            "unknown_network_data_flag": float(1 if recommendation.network_flag == "unknown" else 0),
            "unsafe_reason_count": float(len(getattr(recommendation, "unsafe_reasons", []) or [])),
            "candidate_plan_count_service_area": candidate_plan_count_service_area,
            "candidate_plan_count_ranked": candidate_plan_count_ranked,
            "plans_with_unknown_network_count": plans_with_unknown_network_count,
            "plans_dropped_due_to_missing_data": plans_dropped_due_to_missing_data,
        }
        rows.append(row)
    return rows


def build_training_dataset(
    config: PipelineConfig | None = None,
    output_path: Path | None = None,
    scenario_bundles: list[str] | None = None,
    *,
    scenario_source_strategy: str = DEFAULT_SCENARIO_SOURCE_STRATEGY,
    target_scenario_count: int | None = None,
    generator_seed: int = DEFAULT_GENERATOR_SEED,
    refresh_scenarios: bool = False,
    max_workers: int | None = None,
    chunk_size: int = DEFAULT_DATASET_CHUNK_SIZE,
    resume_chunks: bool = True,
    stale_chunk_hours: int = DEFAULT_STALE_CHUNK_HOURS,
) -> Path:
    active_config = config or PipelineConfig()
    active_config.ensure_directories()
    generation_summary = generate_training_scenarios(
        active_config,
        scenario_source_strategy=scenario_source_strategy,
        target_scenario_count=target_scenario_count,
        generator_seed=generator_seed,
        refresh=refresh_scenarios,
    )
    scenarios, scenario_df, medication_df = load_materialized_scenarios(
        active_config,
        scenario_bundles=scenario_bundles,
    )
    if not scenarios:
        raise ValueError("No canonical training scenarios are available after materialization.")
    worker_count = _normalized_dataset_worker_count(max_workers, active_config)
    path = output_path or active_config.training_dataset_path
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk_summary = _materialize_dataset_chunks(
        active_config,
        scenarios,
        output_path=path,
        max_workers=worker_count,
        chunk_size=chunk_size,
        resume_chunks=resume_chunks,
        stale_chunk_hours=stale_chunk_hours,
    )
    frame = _load_chunked_dataset_frame(path)
    if frame.empty:
        raise ValueError("No rows were generated for the hybrid reranker dataset.")
    frame["weak_label_score"] = frame.apply(_weak_label_score, axis=1)
    frame["heuristic_score"] = frame.apply(_heuristic_score, axis=1)
    relevance_frames: list[pd.DataFrame] = []
    for _, group in frame.groupby("scenario_id"):
        relevance_frames.append(_scenario_relevance(group))
    relevance_df = pd.concat(relevance_frames, ignore_index=True)
    frame = frame.merge(relevance_df, on=["scenario_id", "plan_key"], how="left")
    frame = frame.sort_values(["scenario_id", "current_rules_rank"]).reset_index(drop=True)

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
        "scenario_source": scenario_source_strategy,
        "generation_version": GENERATION_VERSION,
        "scenario_source_strategy": scenario_source_strategy,
        "bundle_counts": {
            str(key): int(value)
            for key, value in scenario_df.groupby("scenario_bundle")["scenario_id"].nunique().to_dict().items()
        },
        "source_kind_counts": {
            str(key): int(value)
            for key, value in scenario_df.groupby("scenario_source_kind")["scenario_id"].nunique().to_dict().items()
        },
        "zip_count": int(scenario_df["zipcode"].astype(str).nunique()) if not scenario_df.empty else 0,
        "regimen_signature_count": int(scenario_df["regimen_signature"].astype(str).nunique()) if not scenario_df.empty else 0,
        "unique_ndc_count": int(medication_df["ndc"].dropna().astype(str).nunique()) if not medication_df.empty else 0,
        "teacher_feature_policy": DEFAULT_TEACHER_FEATURE_POLICY,
        "generator_seed": int(generator_seed),
        "reused_scenarios": bool(generation_summary.get("reused_existing", False)),
        "chunk_size": int(chunk_size),
        "chunk_count": int(chunk_summary["chunk_count"]),
        "completed_chunk_count": int(chunk_summary["completed_chunk_count"]),
        "resumed_chunk_count": int(chunk_summary["resumed_chunk_count"]),
        "chunk_dir": str(chunk_summary["chunk_dir"]),
        "manifest_version": DATASET_CHUNK_MANIFEST_VERSION,
        "stale_chunk_hours": int(stale_chunk_hours),
        "zip_grouped_chunks": True,
    }
    metadata_path = _dataset_metadata_path(path)
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    logger.info("wrote hybrid training dataset rows=%s path=%s", len(frame), path)
    return path


def _normalized_dataset_worker_count(max_workers: int | None, config: PipelineConfig | None = None) -> int:
    if max_workers is None:
        active_config = config or PipelineConfig()
        return DEFAULT_DEMO_DATASET_BUILD_WORKERS if active_config.is_demo_profile else DEFAULT_FULL_DATASET_BUILD_WORKERS
    return max(1, int(max_workers))


@dataclass(slots=True)
class ReplayZipCache:
    zipcode: str
    candidate_plans: pd.DataFrame
    plan_keys: list[str]
    channel_df: pd.DataFrame
    nearest_distances: dict[str, float | None]


@dataclass(slots=True)
class ReplayZipDrugCache:
    zipcode: str
    drug_pairs: tuple[tuple[str, int], ...]
    basis_df: pd.DataFrame
    local_drug_metadata: dict[str, dict[str, Any]]


class ReplayWorkerContext:
    def __init__(self, config: PipelineConfig) -> None:
        from .recommend import (
            build_default_input_lookups,
            build_drug_reference_cache,
            build_tier_lookup,
        )

        self.config = config
        self.conn = _connect(config)
        self.reference_cache = build_drug_reference_cache(self.conn)
        self.defaults_specific_lookup, self.defaults_fallback_lookup = build_default_input_lookups(self.conn)
        self.tier_lookup = build_tier_lookup(self.conn)
        self.zip_cache: dict[str, ReplayZipCache] = {}
        self.zip_drug_cache: dict[tuple[str, tuple[tuple[str, int], ...]], ReplayZipDrugCache] = {}

    def close(self) -> None:
        self.conn.close()

    def warm_chunk(self, scenarios: list[Any]) -> None:
        zip_pairs: dict[str, set[tuple[str, int]]] = {}
        for scenario in scenarios:
            zipcode = _scenario_zipcode(scenario)
            self.zip_context(zipcode)
            zip_pairs.setdefault(zipcode, set()).update(_scenario_known_drug_pairs(scenario))
        for zipcode, pairs in zip_pairs.items():
            self.zip_drug_context(zipcode, pairs)

    def zip_context(self, zipcode: str) -> ReplayZipCache:
        from .recommend import fetch_candidate_plans, fetch_channel_summaries, _lookup_nearest_preferred_distance

        if zipcode not in self.zip_cache:
            candidate_plans = fetch_candidate_plans(self.conn, zipcode)
            plan_keys = candidate_plans["plan_key"].astype(str).tolist() if not candidate_plans.empty else []
            channel_df = fetch_channel_summaries(self.conn, plan_keys)
            nearest_distances = _lookup_nearest_preferred_distance(self.conn, zipcode, plan_keys)
            self.zip_cache[zipcode] = ReplayZipCache(
                zipcode=zipcode,
                candidate_plans=candidate_plans,
                plan_keys=plan_keys,
                channel_df=channel_df,
                nearest_distances=nearest_distances,
            )
        return self.zip_cache[zipcode]

    def zip_drug_context(
        self,
        zipcode: str,
        drug_pairs: set[tuple[str, int]] | tuple[tuple[str, int], ...],
    ) -> ReplayZipDrugCache:
        from .recommend import build_local_drug_metadata_from_basis, fetch_basis_rows

        normalized_pairs = tuple(sorted({(str(ndc), int(days_supply)) for ndc, days_supply in drug_pairs if ndc}))
        cache_key = (zipcode, normalized_pairs)
        if cache_key not in self.zip_drug_cache:
            zip_context = self.zip_context(zipcode)
            ndcs = sorted({ndc for ndc, _ in normalized_pairs})
            basis_df = fetch_basis_rows(self.conn, zip_context.plan_keys, ndcs)
            self.zip_drug_cache[cache_key] = ReplayZipDrugCache(
                zipcode=zipcode,
                drug_pairs=normalized_pairs,
                basis_df=basis_df,
                local_drug_metadata=build_local_drug_metadata_from_basis(basis_df),
            )
        return self.zip_drug_cache[cache_key]

    def query_context_for_scenario(self, scenario: Any) -> Any:
        from .recommend import RecommendationQueryContext

        zipcode = _scenario_zipcode(scenario)
        zip_context = self.zip_context(zipcode)
        zip_drug_context = self.zip_drug_context(zipcode, _scenario_known_drug_pairs(scenario))
        return RecommendationQueryContext(
            candidate_plans=zip_context.candidate_plans,
            channel_df=zip_context.channel_df,
            nearest_distances=zip_context.nearest_distances,
            basis_df=zip_drug_context.basis_df,
            reference_cache=self.reference_cache,
            local_drug_metadata=zip_drug_context.local_drug_metadata,
            defaults_specific_lookup=self.defaults_specific_lookup,
            defaults_fallback_lookup=self.defaults_fallback_lookup,
            tier_lookup=self.tier_lookup,
        )


def _scenario_zipcode(scenario: Any) -> str:
    return str(getattr(scenario.beneficiary, "zipcode", "")).strip().zfill(5)


def _scenario_known_drug_pairs(scenario: Any) -> set[tuple[str, int]]:
    from .recommend import _normalize_days_supply

    pairs: set[tuple[str, int]] = set()
    for medication in getattr(scenario, "medications", []):
        if not getattr(medication, "ndc", None):
            continue
        ndc = str(medication.ndc).strip().zfill(11)
        day_supply = _normalize_days_supply(int(getattr(medication, "day_supply", 30) or 30))
        pairs.add((ndc, day_supply))
    return pairs


def _materialize_dataset_chunks(
    config: PipelineConfig,
    scenarios: list[Any],
    *,
    output_path: Path,
    max_workers: int,
    chunk_size: int,
    resume_chunks: bool,
    stale_chunk_hours: int,
) -> dict[str, Any]:
    chunk_dir = _dataset_chunk_dir(output_path)
    build_signature = _dataset_chunk_build_signature(config, scenarios)
    _prepare_dataset_chunk_dir(
        chunk_dir,
        build_signature=build_signature,
        resume_chunks=resume_chunks,
    )
    scenario_batches = _scenario_batches(scenarios, chunk_size=chunk_size)
    chunk_specs = [
        _chunk_spec(
            chunk_dir,
            build_signature=build_signature,
            chunk_index=index,
            scenarios=batch,
        )
        for index, batch in enumerate(scenario_batches)
    ]
    _cleanup_stale_started_chunks(chunk_specs, stale_chunk_hours=stale_chunk_hours)
    chunk_records: list[dict[str, Any]] = []
    pending_specs: list[dict[str, Any]] = []
    resumed_count = 0
    for spec in chunk_specs:
        existing = _load_chunk_meta(spec["meta_path"])
        if existing is not None and _chunk_meta_matches_spec(existing, spec) and str(existing.get("status")) == "completed":
            chunk_records.append(existing)
            resumed_count += 1
            continue
        pending_record = _pending_chunk_record(spec)
        _write_chunk_meta(spec["meta_path"], pending_record)
        chunk_records.append(pending_record)
        pending_specs.append(spec)

    total = len(scenarios)
    completed_scenarios = sum(
        int(item.get("scenario_count") or 0)
        for item in chunk_records
        if str(item.get("status")) == "completed"
    )
    _write_dataset_chunk_manifest(
        chunk_dir,
        _chunk_manifest_payload(
            build_signature=build_signature,
            chunk_size=chunk_size,
            stale_chunk_hours=stale_chunk_hours,
            chunk_records=chunk_records,
        ),
    )

    if pending_specs:
        logger.info(
            "building dataset chunks scenarios=%s chunks=%s workers=%s resumed_chunks=%s",
            total,
            len(chunk_specs),
            max_workers,
            resumed_count,
        )
    else:
        logger.info("reusing all completed dataset chunks scenarios=%s chunks=%s", total, len(chunk_specs))

    if pending_specs and max_workers > 1:
        context = mp.get_context("spawn")
        try:
            with ProcessPoolExecutor(
                max_workers=max_workers,
                mp_context=context,
                max_tasks_per_child=DEFAULT_WORKER_MAX_TASKS_PER_CHILD,
            ) as executor:
                futures = [
                    executor.submit(_materialize_dataset_chunk, config, spec)
                    for spec in pending_specs
                ]
                for future in as_completed(futures):
                    result = future.result()
                    _replace_chunk_record(chunk_records, result)
                    completed_scenarios += int(result.get("scenario_count") or 0)
                    _write_dataset_chunk_manifest(
                        chunk_dir,
                        _chunk_manifest_payload(
                            build_signature=build_signature,
                            chunk_size=chunk_size,
                            stale_chunk_hours=stale_chunk_hours,
                            chunk_records=chunk_records,
                        ),
                    )
                    _log_chunk_warnings(result)
                    logger.info(
                        "dataset chunk completed chunk=%s/%s scenarios=%s/%s rows=%s",
                        int(result.get("chunk_index") or 0) + 1,
                        len(chunk_specs),
                        completed_scenarios,
                        total,
                        int(result.get("row_count") or 0),
                    )
        except (PermissionError, OSError) as exc:
            logger.warning(
                "dataset process pool unavailable (%s); falling back to sequential chunk replay",
                exc,
            )
            pending_specs = sorted(pending_specs, key=lambda item: int(item["chunk_index"]))
            for spec in pending_specs:
                result = _materialize_dataset_chunk(config, spec)
                _replace_chunk_record(chunk_records, result)
                completed_scenarios += int(result.get("scenario_count") or 0)
                _write_dataset_chunk_manifest(
                    chunk_dir,
                    _chunk_manifest_payload(
                        build_signature=build_signature,
                        chunk_size=chunk_size,
                        stale_chunk_hours=stale_chunk_hours,
                        chunk_records=chunk_records,
                    ),
                )
                _log_chunk_warnings(result)
                logger.info(
                    "dataset chunk completed chunk=%s/%s scenarios=%s/%s rows=%s",
                    int(result.get("chunk_index") or 0) + 1,
                    len(chunk_specs),
                    completed_scenarios,
                    total,
                    int(result.get("row_count") or 0),
                )
    elif pending_specs:
        pending_specs = sorted(pending_specs, key=lambda item: int(item["chunk_index"]))
        for spec in pending_specs:
            result = _materialize_dataset_chunk(config, spec)
            _replace_chunk_record(chunk_records, result)
            completed_scenarios += int(result.get("scenario_count") or 0)
            _write_dataset_chunk_manifest(
                chunk_dir,
                _chunk_manifest_payload(
                    build_signature=build_signature,
                    chunk_size=chunk_size,
                    stale_chunk_hours=stale_chunk_hours,
                    chunk_records=chunk_records,
                ),
            )
            _log_chunk_warnings(result)
            logger.info(
                "dataset chunk completed chunk=%s/%s scenarios=%s/%s rows=%s",
                int(result.get("chunk_index") or 0) + 1,
                len(chunk_specs),
                completed_scenarios,
                total,
                int(result.get("row_count") or 0),
            )

    completed_count = sum(1 for item in chunk_records if str(item.get("status")) == "completed")
    if completed_count != len(chunk_specs):
        raise ValueError("Dataset chunk materialization did not complete for every chunk.")
    return {
        "chunk_dir": chunk_dir,
        "chunk_count": len(chunk_specs),
        "completed_chunk_count": completed_count,
        "resumed_chunk_count": resumed_count,
    }


def _dataset_chunk_dir(output_path: Path) -> Path:
    return output_path.parent / f"{output_path.stem}.chunks"


def _dataset_chunk_build_signature(
    config: PipelineConfig,
    scenarios: list[Any],
) -> str:
    payload = {
        "snapshot_quarter": config.snapshot_quarter,
        "build_profile": config.build_profile,
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "weak_label_version": WEAK_LABEL_VERSION,
        "generation_version": GENERATION_VERSION,
        "scenario_ids": [str(getattr(scenario, "scenario_id", "")) for scenario in scenarios],
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _prepare_dataset_chunk_dir(
    chunk_dir: Path,
    *,
    build_signature: str,
    resume_chunks: bool,
) -> None:
    manifest_path = chunk_dir / "build_manifest.json"
    if chunk_dir.exists():
        existing_signature = None
        if manifest_path.exists():
            try:
                existing_signature = json.loads(manifest_path.read_text(encoding="utf-8")).get("build_signature")
            except json.JSONDecodeError:
                existing_signature = None
        if not resume_chunks or existing_signature != build_signature:
            shutil.rmtree(chunk_dir, ignore_errors=True)
    chunk_dir.mkdir(parents=True, exist_ok=True)


def _cleanup_stale_started_chunks(
    chunk_specs: list[dict[str, Any]],
    *,
    stale_chunk_hours: int,
) -> None:
    threshold = datetime.now(UTC) - timedelta(hours=max(0, int(stale_chunk_hours)))
    for spec in chunk_specs:
        meta = _load_chunk_meta(spec["meta_path"])
        if meta is None or str(meta.get("status")) != "started":
            continue
        started_at_raw = str(meta.get("started_at") or "")
        try:
            started_at = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
        except ValueError:
            started_at = None
        if started_at is not None and started_at > threshold:
            continue
        Path(spec["meta_path"]).unlink(missing_ok=True)
        Path(spec["chunk_path"]).unlink(missing_ok=True)


def _chunk_spec(
    chunk_dir: Path,
    *,
    build_signature: str,
    chunk_index: int,
    scenarios: list[Any],
) -> dict[str, Any]:
    chunk_path = chunk_dir / f"chunk_{chunk_index:04d}.csv"
    meta_path = chunk_dir / f"chunk_{chunk_index:04d}.json"
    return {
        "build_signature": build_signature,
        "chunk_index": int(chunk_index),
        "chunk_path": str(chunk_path),
        "meta_path": str(meta_path),
        "scenario_ids": [str(getattr(scenario, "scenario_id", "")) for scenario in scenarios],
        "zipcodes": sorted({_scenario_zipcode(scenario) for scenario in scenarios}),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def _load_chunk_meta(meta_path_raw: str) -> dict[str, Any] | None:
    meta_path = Path(meta_path_raw)
    if not meta_path.exists():
        return None
    try:
        payload = json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if str(payload.get("status")) == "completed":
        chunk_path = Path(str(payload.get("chunk_path") or ""))
        if not chunk_path.exists():
            return None
    return payload


def _chunk_meta_matches_spec(meta: dict[str, Any], spec: dict[str, Any]) -> bool:
    return (
        str(meta.get("build_signature") or "") == str(spec["build_signature"])
        and list(meta.get("scenario_ids") or []) == list(spec["scenario_ids"])
    )


def _pending_chunk_record(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_version": DATASET_CHUNK_MANIFEST_VERSION,
        "build_signature": spec["build_signature"],
        "chunk_index": int(spec["chunk_index"]),
        "chunk_path": str(spec["chunk_path"]),
        "scenario_ids": list(spec["scenario_ids"]),
        "zipcodes": list(spec["zipcodes"]),
        "scenario_count": int(spec["scenario_count"]),
        "row_count": 0,
        "warning_count": 0,
        "warnings": [],
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "failed_at": None,
        "error": None,
    }


def _write_chunk_meta(meta_path_raw: str, payload: dict[str, Any]) -> None:
    meta_path = Path(meta_path_raw)
    tmp_path = Path(f"{meta_path}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(meta_path)


def _write_dataset_chunk_manifest(chunk_dir: Path, payload: dict[str, Any]) -> None:
    manifest_path = chunk_dir / "build_manifest.json"
    tmp_path = chunk_dir / "build_manifest.json.tmp"
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(manifest_path)


def _chunk_manifest_payload(
    *,
    build_signature: str,
    chunk_size: int,
    stale_chunk_hours: int,
    chunk_records: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "manifest_version": DATASET_CHUNK_MANIFEST_VERSION,
        "build_signature": build_signature,
        "chunk_size": int(chunk_size),
        "chunk_count": len(chunk_records),
        "stale_chunk_hours": int(stale_chunk_hours),
        "chunks": sorted(chunk_records, key=lambda item: int(item.get("chunk_index") or 0)),
    }


def _replace_chunk_record(chunk_records: list[dict[str, Any]], updated: dict[str, Any]) -> None:
    target_index = int(updated.get("chunk_index") or 0)
    for index, record in enumerate(chunk_records):
        if int(record.get("chunk_index") or 0) == target_index:
            chunk_records[index] = updated
            return
    chunk_records.append(updated)


def _log_chunk_warnings(result: dict[str, Any]) -> None:
    for warning in result.get("warnings", []):
        logger.warning(
            "skipping scenario %s during dataset build: %s",
            warning["scenario_id"],
            warning["warning"],
        )


def _load_chunked_dataset_frame(output_path: Path) -> pd.DataFrame:
    manifest_path = _dataset_chunk_dir(output_path) / "build_manifest.json"
    if not manifest_path.exists():
        raise ValueError(f"Chunk manifest not found: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    chunk_entries = sorted(
        [
            entry
            for entry in manifest.get("chunks", [])
            if str(entry.get("status")) == "completed"
        ],
        key=lambda item: int(item.get("chunk_index") or 0),
    )
    frames: list[pd.DataFrame] = []
    for entry in chunk_entries:
        chunk_path = Path(str(entry.get("chunk_path") or ""))
        if not chunk_path.exists():
            raise ValueError(f"Missing completed chunk file: {chunk_path}")
        frames.append(pd.read_csv(chunk_path))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _build_dataset_rows_sequential(
    config: PipelineConfig,
    scenarios: list[Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total = len(scenarios)
    logger.info("building dataset sequentially scenarios=%s", total)
    for index, scenario in enumerate(scenarios, start=1):
        result = _build_dataset_rows_for_scenario(config, scenario)
        if result["warning"]:
            logger.warning("skipping scenario %s during dataset build: %s", scenario.scenario_id, result["warning"])
        rows.extend(result["rows"])
        if index == total or index % 25 == 0:
            logger.info("dataset build progress scenarios=%s/%s rows=%s", index, total, len(rows))
    return rows


def _build_dataset_rows_for_scenario(
    config: PipelineConfig,
    scenario: Any,
) -> dict[str, Any]:
    from .recommend import recommend_plans

    conn = _connect(config)
    try:
        recommendations = recommend_plans(
            scenario.beneficiary,
            scenario.medications,
            config=config,
            ranking_mode="rules",
            allow_approximate_match_ranking=True,
        )
    except ValueError as exc:
        conn.close()
        return {
            "scenario_id": getattr(scenario, "scenario_id", ""),
            "rows": [],
            "warning": str(exc),
        }
    try:
        rows = _recommendations_to_feature_rows(
            conn,
            recommendations,
            scenario.beneficiary,
            scenario.scenario_id,
            scenario.scenario_bundle,
            regimen_signature=getattr(scenario, "regimen_signature", ""),
            scenario_source_kind=getattr(scenario, "scenario_source_kind", "benchmark"),
            scenario_source_label=getattr(scenario, "scenario_source_label", "benchmark_pool"),
            intended_profile=getattr(scenario, "intended_profile", scenario.scenario_bundle),
        )
        return {
            "scenario_id": getattr(scenario, "scenario_id", ""),
            "rows": rows,
            "warning": "",
        }
    finally:
        conn.close()


def _build_dataset_rows_for_scenarios(
    config: PipelineConfig,
    scenarios: list[Any],
) -> dict[str, Any]:
    from .recommend import recommend_plans

    worker = ReplayWorkerContext(config)
    rows: list[dict[str, Any]] = []
    warnings: list[dict[str, str]] = []
    try:
        worker.warm_chunk(scenarios)
        for scenario in scenarios:
            try:
                recommendations = recommend_plans(
                    scenario.beneficiary,
                    scenario.medications,
                    config=config,
                    ranking_mode="rules",
                    allow_approximate_match_ranking=True,
                    conn=worker.conn,
                    query_context=worker.query_context_for_scenario(scenario),
                )
            except ValueError as exc:
                warnings.append(
                    {
                        "scenario_id": str(getattr(scenario, "scenario_id", "")),
                        "warning": str(exc),
                    }
                )
                continue
            rows.extend(
                _recommendations_to_feature_rows(
                    worker.conn,
                    recommendations,
                    scenario.beneficiary,
                    scenario.scenario_id,
                    scenario.scenario_bundle,
                    regimen_signature=getattr(scenario, "regimen_signature", ""),
                    scenario_source_kind=getattr(scenario, "scenario_source_kind", "benchmark"),
                    scenario_source_label=getattr(scenario, "scenario_source_label", "benchmark_pool"),
                    intended_profile=getattr(scenario, "intended_profile", scenario.scenario_bundle),
                )
            )
        return {
            "rows": rows,
            "warnings": warnings,
            "scenario_count": len(scenarios),
        }
    finally:
        worker.close()


def _scenario_batches(
    scenarios: list[Any],
    *,
    chunk_size: int,
) -> list[list[Any]]:
    if not scenarios:
        return []
    limit = max(1, int(chunk_size))
    grouped: dict[str, list[Any]] = {}
    for scenario in sorted(scenarios, key=lambda item: (_scenario_zipcode(item), str(getattr(item, "scenario_id", "")))):
        grouped.setdefault(_scenario_zipcode(scenario), []).append(scenario)

    chunks: list[list[Any]] = []
    current_chunk: list[Any] = []
    for zipcode in sorted(grouped):
        group = grouped[zipcode]
        if len(group) > limit:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            for index in range(0, len(group), limit):
                chunks.append(group[index : index + limit])
            continue
        if current_chunk and len(current_chunk) + len(group) > limit:
            chunks.append(current_chunk)
            current_chunk = []
        current_chunk.extend(group)
    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _materialize_dataset_chunk(
    config: PipelineConfig,
    chunk_spec: dict[str, Any],
) -> dict[str, Any]:
    chunk_path = Path(chunk_spec["chunk_path"])
    meta_path = Path(chunk_spec["meta_path"])
    chunk_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)
    _write_chunk_meta(
        str(meta_path),
        {
            **_pending_chunk_record(chunk_spec),
            "status": "started",
            "started_at": started_at.isoformat(),
        },
    )
    try:
        result = _build_dataset_rows_for_scenarios(config, chunk_spec["scenarios"])
        frame = pd.DataFrame(result["rows"])
        tmp_chunk = Path(f"{chunk_path}.tmp")
        frame.to_csv(tmp_chunk, index=False)
        payload = {
            "manifest_version": DATASET_CHUNK_MANIFEST_VERSION,
            "status": "completed",
            "build_signature": chunk_spec["build_signature"],
            "chunk_index": int(chunk_spec["chunk_index"]),
            "chunk_path": str(chunk_path),
            "scenario_ids": list(chunk_spec["scenario_ids"]),
            "zipcodes": list(chunk_spec["zipcodes"]),
            "scenario_count": int(result.get("scenario_count") or 0),
            "row_count": int(len(frame)),
            "warning_count": int(len(result.get("warnings", []))),
            "warnings": result.get("warnings", []),
            "started_at": started_at.isoformat(),
            "completed_at": datetime.now(UTC).isoformat(),
            "failed_at": None,
            "error": None,
        }
        tmp_chunk.replace(chunk_path)
        _write_chunk_meta(str(meta_path), payload)
        return payload
    except Exception as exc:
        failed_payload = {
            **_pending_chunk_record(chunk_spec),
            "status": "failed",
            "started_at": started_at.isoformat(),
            "failed_at": datetime.now(UTC).isoformat(),
            "error": str(exc),
        }
        _write_chunk_meta(str(meta_path), failed_payload)
        raise


def _feature_subset_columns(
    feature_subset: str,
    teacher_feature_policy: str = DEFAULT_TEACHER_FEATURE_POLICY,
) -> tuple[list[str], list[str]]:
    subset = FEATURE_SUBSETS.get(feature_subset)
    if subset is None:
        raise ValueError(f"Unsupported feature subset: {feature_subset}")
    if teacher_feature_policy not in SUPPORTED_TEACHER_FEATURE_POLICIES:
        raise ValueError(f"Unsupported teacher feature policy: {teacher_feature_policy}")
    numeric_columns = list(subset["numeric"])
    if teacher_feature_policy == DEFAULT_TEACHER_FEATURE_POLICY:
        numeric_columns = [column for column in numeric_columns if column not in TEACHER_NUMERIC_COLUMNS]
    return numeric_columns, list(subset["categorical"])


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
    teacher_feature_policy: str,
) -> HybridRerankerArtifact:
    numeric_columns, categorical_columns = _feature_subset_columns(feature_subset, teacher_feature_policy)
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
        teacher_feature_policy=teacher_feature_policy,
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
    teacher_feature_policy: str,
    *,
    learning_rate: float,
    n_estimators: int,
    max_depth: int,
    min_samples_leaf: int,
) -> HybridRerankerArtifact:
    numeric_columns, categorical_columns = _feature_subset_columns(feature_subset, teacher_feature_policy)
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
        teacher_feature_policy=teacher_feature_policy,
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
    teacher_feature_policy: str = DEFAULT_TEACHER_FEATURE_POLICY,
) -> Path:
    active_config = config or PipelineConfig()
    active_config.ensure_directories()
    path = dataset_path or active_config.training_dataset_path
    if not path.exists():
        path = build_training_dataset(active_config, output_path=path)
    frame = pd.read_csv(path)
    if model_type == LINEAR_MODEL_TYPE:
        artifact = _fit_linear_artifact(frame, active_config, feature_subset, alpha, teacher_feature_policy)
    else:
        artifact = _fit_tree_artifact(
            frame,
            active_config,
            feature_subset,
            teacher_feature_policy,
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


def _split_frame_by_key(
    frame: pd.DataFrame,
    split_column: str,
    *,
    test_fraction: float = EVALUATION_TEST_FRACTION,
    seed: int = EVALUATION_SPLIT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    group_ids = sorted(frame[split_column].dropna().astype(str).unique().tolist())
    if len(group_ids) < 2:
        raise ValueError(f"Need at least two values in {split_column} for held-out evaluation.")

    shuffled = np.array(group_ids, dtype=object)
    np.random.default_rng(seed).shuffle(shuffled)
    test_count = max(1, int(math.ceil(len(shuffled) * test_fraction)))
    if test_count >= len(shuffled):
        test_count = len(shuffled) - 1
    test_groups = sorted(str(item) for item in shuffled[:test_count].tolist())
    test_group_set = set(test_groups)
    labels = frame[split_column].astype(str)
    test_frame = frame.loc[labels.isin(test_group_set)].copy()
    train_frame = frame.loc[~labels.isin(test_group_set)].copy()
    if train_frame.empty or test_frame.empty:
        raise ValueError("Unable to create non-empty train/test scenario splits for evaluation.")
    train_groups = sorted(train_frame[split_column].astype(str).unique().tolist())
    return train_frame, test_frame, train_groups, test_groups


def _split_frame_by_scenario(
    frame: pd.DataFrame,
    *,
    test_fraction: float = EVALUATION_TEST_FRACTION,
    seed: int = EVALUATION_SPLIT_SEED,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    return _split_frame_by_key(frame, "scenario_id", test_fraction=test_fraction, seed=seed)


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
            top1 = ordered.head(1)
            top5 = ordered.head(5)
            top10 = ordered.head(10)
            truth_top1 = truth.head(1)
            no_full_coverage_truth = bool((truth["coverage_status"] != "full").all())
            blocker_precision = 1.0
            if no_full_coverage_truth and not top1.empty and not truth_top1.empty:
                blocker_precision = float(top1.iloc[0]["fallback_group"] == truth_top1.iloc[0]["fallback_group"])
            metrics = {
                "top1_agreement": 1.0 if ordered_keys[:1] == truth_plan_keys[:1] else 0.0,
                "top1_full_coverage_rate": float((top1["coverage_status"] == "full").mean()) if not top1.empty else 0.0,
                "top5_overlap": _top_overlap(ordered_keys, truth_plan_keys, 5),
                "top10_overlap": _top_overlap(ordered_keys, truth_plan_keys, 10),
                "ndcg_5": _ndcg_at_k(relevances, 5),
                "ndcg_10": _ndcg_at_k(relevances, 10),
                "top5_full_coverage_rate": float((top5["coverage_status"] == "full").mean()) if not top5.empty else 0.0,
                "top10_full_coverage_rate": float((top10["coverage_status"] == "full").mean()) if not top10.empty else 0.0,
                "top5_avg_total_cost": float(top5["annual_total_cost"].mean()) if not top5.empty else 0.0,
                "top10_avg_total_cost": float(top10["annual_total_cost"].mean()) if not top10.empty else 0.0,
                "top5_avg_uncovered": float(top5["uncovered_drug_count"].mean()) if not top5.empty else 0.0,
                "blocker_classification_precision": blocker_precision,
                "match_review_trigger_rate": float(top5["match_review_required_flag"].mean()) if not top5.empty else 0.0,
                "plans_dropped_due_to_missing_data": float(
                    ordered["plans_dropped_due_to_missing_data"].max()
                )
                if not ordered.empty
                else 0.0,
                "pct_runs_with_unknown_network_data": float(
                    (ordered["unknown_network_data_flag"] > 0).any()
                )
                if not ordered.empty
                else 0.0,
            }
            overall[system_name].append(metrics)
            by_bundle[bundle][system_name].append(metrics)
    overall_summary = _summarize_metric_frames(overall)
    bundle_summary = {
        bundle: _summarize_metric_frames(system_metrics)
        for bundle, system_metrics in by_bundle.items()
    }
    return overall_summary, bundle_summary


def _evaluate_split_mode(
    frame: pd.DataFrame,
    active_config: PipelineConfig,
    *,
    split_column: str,
    split_label: str,
    baseline_only: bool,
    teacher_feature_policy: str,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    train_frame, test_frame, train_groups, test_groups = _split_frame_by_key(frame, split_column)
    evaluation_frame = test_frame.copy()

    linear_artifact = _fit_linear_artifact(
        train_frame,
        active_config,
        "full",
        alpha=5.0,
        teacher_feature_policy=teacher_feature_policy,
    )
    evaluation_frame["predicted_linear_score"] = linear_artifact.predict(evaluation_frame)
    if artifact_path is not None:
        logger.info("evaluation uses held-out train/test fitting and does not reuse artifact=%s", artifact_path)

    ablation_predictions: dict[str, str] = {}
    if not baseline_only:
        tree_artifact = _fit_tree_artifact(
            train_frame,
            active_config,
            "full",
            teacher_feature_policy=teacher_feature_policy,
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
                teacher_feature_policy=teacher_feature_policy,
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
    return {
        "evaluation_mode": split_label,
        "split_column": split_column,
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
        "train_group_count": int(len(train_groups)),
        "test_group_count": int(len(test_groups)),
        "train_groups": train_groups,
        "test_groups": test_groups,
    }


def evaluate_hybrid_reranker(
    config: PipelineConfig | None = None,
    dataset_path: Path | None = None,
    artifact_path: Path | None = None,
    output_path: Path | None = None,
    *,
    scenario_bundles: list[str] | None = None,
    baseline_only: bool = False,
    teacher_feature_policy: str = DEFAULT_TEACHER_FEATURE_POLICY,
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

    split_reports = {
        "held_out_by_scenario": _evaluate_split_mode(
            frame,
            active_config,
            split_column="scenario_id",
            split_label="held_out_by_scenario",
            baseline_only=baseline_only,
            teacher_feature_policy=teacher_feature_policy,
            artifact_path=artifact_path,
        ),
        "held_out_by_zip": _evaluate_split_mode(
            frame,
            active_config,
            split_column="beneficiary_zipcode",
            split_label="held_out_by_zip",
            baseline_only=baseline_only,
            teacher_feature_policy=teacher_feature_policy,
        ),
        "held_out_by_regimen_signature": _evaluate_split_mode(
            frame,
            active_config,
            split_column="regimen_signature",
            split_label="held_out_by_regimen_signature",
            baseline_only=baseline_only,
            teacher_feature_policy=teacher_feature_policy,
        ),
    }
    primary = split_reports["held_out_by_scenario"]
    summary: dict[str, Any] = {
        "dataset_schema_version": DATASET_SCHEMA_VERSION,
        "weak_label_version": WEAK_LABEL_VERSION,
        "evaluation_mode": primary["evaluation_mode"],
        "split_seed": EVALUATION_SPLIT_SEED,
        "test_fraction": EVALUATION_TEST_FRACTION,
        "systems": primary["systems"],
        "scenario_bundle_metrics": primary["scenario_bundle_metrics"],
        "acceptance": primary["acceptance"],
        "dataset_rows": primary["dataset_rows"],
        "scenario_count": primary["scenario_count"],
        "train_rows": primary["train_rows"],
        "test_rows": primary["test_rows"],
        "train_scenario_count": primary["train_group_count"],
        "test_scenario_count": primary["test_group_count"],
        "train_scenarios": primary["train_groups"],
        "test_scenarios": primary["test_groups"],
        "teacher_feature_policy": teacher_feature_policy,
        "evaluation_modes": split_reports,
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
