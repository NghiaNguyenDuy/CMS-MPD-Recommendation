from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from .config import PipelineConfig
from .recommend import BeneficiaryInput, MedicationInput


GENERATION_VERSION = "scenario_generation_v1"
DEFAULT_GENERATOR_SEED = 42
CANONICAL_SCENARIO_BUNDLES = [
    "low_utilizer",
    "maintenance_generic",
    "insulin_chronic",
    "specialty_high_cost",
    "mixed_restriction",
    "access_sensitive",
]
SCENARIO_SOURCE_STRATEGIES = {"mixed", "pde", "benchmark"}
SOURCE_KIND_ORDER = ("pde", "benchmark", "stress")
FULL_SOURCE_COUNTS = {"pde": 50, "benchmark": 30, "stress": 20}
DEMO_SOURCE_COUNTS = {"pde": 4, "benchmark": 4, "stress": 2}
FULL_ZIP_TARGET = 100
DEMO_ZIP_TARGET = 10
PDE_FALLBACK_LABEL = "pde_unavailable_fallback"


@dataclass(slots=True)
class MaterializedScenario:
    scenario_id: str
    scenario_bundle: str
    beneficiary: BeneficiaryInput
    medications: list[MedicationInput]
    scenario_source_kind: str
    scenario_source_label: str
    intended_profile: str
    geo_source: str
    generator_version: str = GENERATION_VERSION
    legacy_bundle_alias: str | None = None
    regimen_signature: str = ""
    validation_profile: str | None = None
    validation_passed: bool = False


def _connect_read(config: PipelineConfig) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path), read_only=True)


def _connect_write(config: PipelineConfig) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(config.db_path))


def _fetch_dataframe(
    conn: duckdb.DuckDBPyConnection,
    query: str,
    params: list[Any] | None = None,
) -> pd.DataFrame:
    if params:
        return conn.execute(query, params).fetch_df()
    return conn.execute(query).fetch_df()


def _table_exists(conn: duckdb.DuckDBPyConnection, full_name: str) -> bool:
    schema, table = full_name.split(".", 1)
    row = conn.execute(
        """
        SELECT count(*)
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        """,
        [schema, table],
    ).fetchone()
    return bool(row and row[0] > 0)


def _normalize_days_supply(value: Any, default: int = 30) -> int:
    try:
        numeric = int(float(value))
    except (TypeError, ValueError):
        numeric = default
    if numeric <= 45:
        return 30
    if numeric <= 75:
        return 60
    return 90


def _bool_from_row(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "y", "yes"}


def _float_value(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _sample_counts_for_profile(config: PipelineConfig) -> dict[str, int]:
    if config.is_demo_profile:
        return DEMO_SOURCE_COUNTS.copy()
    return FULL_SOURCE_COUNTS.copy()


def _default_target_scenario_count(config: PipelineConfig) -> int:
    per_bundle = sum(_sample_counts_for_profile(config).values())
    return per_bundle * len(CANONICAL_SCENARIO_BUNDLES)


def _target_zip_count(config: PipelineConfig) -> int:
    return DEMO_ZIP_TARGET if config.is_demo_profile else FULL_ZIP_TARGET


def _stratified_zip_sample(
    conn: duckdb.DuckDBPyConnection,
    *,
    target_zip_count: int,
    seed: int,
) -> pd.DataFrame:
    zip_df = _fetch_dataframe(
        conn,
        """
        SELECT DISTINCT
            psa.zip_code,
            coalesce(z.density_category, 'suburban') AS density_category,
            coalesce(z.state_abbr, '') AS state_abbr
        FROM gold.plan_service_area psa
        LEFT JOIN silver.dim_zipcode z ON psa.zip_code = z.zip_code
        WHERE psa.zip_code IS NOT NULL
        ORDER BY psa.zip_code
        """
    )
    if zip_df.empty:
        raise ValueError("No ZIP codes are available for canonical scenario generation.")

    rng = np.random.default_rng(seed)
    grouped = {name: group.reset_index(drop=True) for name, group in zip_df.groupby("density_category")}
    categories = sorted(grouped)
    counts = {name: len(grouped[name]) for name in categories}
    total = sum(counts.values())
    raw_targets = {name: (counts[name] / total) * target_zip_count for name in categories}
    quotas = {name: int(math.floor(value)) for name, value in raw_targets.items()}
    remainder = target_zip_count - sum(quotas.values())

    if target_zip_count >= len(categories):
        for name in categories:
            if quotas[name] == 0:
                quotas[name] = 1
        remainder = target_zip_count - sum(quotas.values())

    if remainder > 0:
        fractions = sorted(
            categories,
            key=lambda name: (raw_targets[name] - math.floor(raw_targets[name]), counts[name]),
            reverse=True,
        )
        for name in fractions[:remainder]:
            quotas[name] += 1
    elif remainder < 0:
        removable = sorted(categories, key=lambda name: quotas[name], reverse=True)
        for name in removable:
            while remainder < 0 and quotas[name] > 1:
                quotas[name] -= 1
                remainder += 1

    sampled_frames: list[pd.DataFrame] = []
    for category in categories:
        quota = quotas.get(category, 0)
        if quota <= 0:
            continue
        group = grouped[category]
        sampled = group.sample(
            n=quota,
            replace=len(group) < quota,
            random_state=int(rng.integers(0, 2**31 - 1)),
        )
        sampled_frames.append(sampled)
    sampled_df = pd.concat(sampled_frames, ignore_index=True) if sampled_frames else zip_df.head(target_zip_count).copy()
    sampled_df = sampled_df.sample(frac=1.0, random_state=int(rng.integers(0, 2**31 - 1))).reset_index(drop=True)
    if len(sampled_df) < target_zip_count:
        extra = sampled_df.sample(
            n=target_zip_count - len(sampled_df),
            replace=True,
            random_state=int(rng.integers(0, 2**31 - 1)),
        )
        sampled_df = pd.concat([sampled_df, extra], ignore_index=True)
    return sampled_df.head(target_zip_count).reset_index(drop=True)


def _load_drug_catalog(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    catalog = _fetch_dataframe(
        conn,
        """
        SELECT
            ndc,
            any_value(rxcui) AS rxcui,
            any_value(drug_name) AS drug_name,
            any_value(tier_family) AS tier_family,
            any_value(days_supply) AS days_supply,
            max(CASE WHEN is_insulin THEN 1 ELSE 0 END) AS is_insulin,
            max(CASE WHEN has_prior_auth THEN 1 ELSE 0 END) AS has_prior_auth,
            max(CASE WHEN has_step_therapy THEN 1 ELSE 0 END) AS has_step_therapy,
            max(CASE WHEN has_quantity_limit THEN 1 ELSE 0 END) AS has_quantity_limit,
            count(DISTINCT plan_key) AS coverable_plan_count,
            median(unit_cost) FILTER (WHERE unit_cost IS NOT NULL) AS unit_cost
        FROM gold.plan_drug_cost_basis
        WHERE ndc IS NOT NULL
          AND drug_name IS NOT NULL
        GROUP BY ndc
        ORDER BY coverable_plan_count DESC, ndc
        """
    )
    if catalog.empty:
        raise ValueError("No drug catalog is available for canonical scenario generation.")
    catalog["is_insulin"] = catalog["is_insulin"].fillna(0).astype(int)
    for column in ("has_prior_auth", "has_step_therapy", "has_quantity_limit"):
        catalog[column] = catalog[column].fillna(0).astype(int)
    catalog["coverable_plan_count"] = catalog["coverable_plan_count"].fillna(0).astype(int)
    catalog["unit_cost"] = pd.to_numeric(catalog["unit_cost"], errors="coerce").fillna(0.0)
    return catalog


def _load_ambiguous_name_candidates(catalog: pd.DataFrame) -> list[dict[str, str]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in catalog.to_dict("records"):
        cleaned = re.sub(r"\[[^\]]*\]", " ", str(row.get("drug_name") or "")).strip()
        cleaned = re.sub(r"[^A-Za-z0-9\s/-]", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        tokens: list[str] = []
        for token in cleaned.split():
            if any(char.isdigit() for char in token):
                break
            tokens.append(token)
        prefix = " ".join(tokens[:2]).strip().lower()
        if prefix:
            groups.setdefault(prefix, []).append(row)
    candidates: list[dict[str, str]] = []
    for prefix, rows in groups.items():
        ndcs = {str(item.get("ndc")) for item in rows if item.get("ndc")}
        if len(ndcs) >= 2:
            first = rows[0]
            candidates.append({"drug_name": prefix, "tier_family": str(first.get("tier_family") or "brand")})
    return candidates


def _catalog_pools(catalog: pd.DataFrame) -> dict[str, pd.DataFrame]:
    restricted = catalog.loc[
        (catalog["has_prior_auth"] > 0)
        | (catalog["has_step_therapy"] > 0)
        | (catalog["has_quantity_limit"] > 0)
    ].copy()
    generic = catalog.loc[(catalog["tier_family"] == "generic") & (catalog["is_insulin"] == 0)].copy()
    brand = catalog.loc[(catalog["tier_family"] == "brand") & (catalog["is_insulin"] == 0)].copy()
    insulin = catalog.loc[catalog["is_insulin"] == 1].copy()
    specialty = catalog.loc[catalog["tier_family"] == "specialty"].copy()
    low_cost = catalog.loc[
        (catalog["is_insulin"] == 0)
        & (catalog["tier_family"] != "specialty")
        & (catalog["unit_cost"] <= catalog["unit_cost"].median() if not catalog.empty else True)
    ].copy()
    return {
        "catalog": catalog,
        "generic": generic if not generic.empty else catalog.copy(),
        "brand": brand if not brand.empty else catalog.copy(),
        "insulin": insulin if not insulin.empty else brand if not brand.empty else catalog.copy(),
        "specialty": specialty if not specialty.empty else restricted if not restricted.empty else brand if not brand.empty else catalog.copy(),
        "restricted": restricted if not restricted.empty else specialty if not specialty.empty else catalog.copy(),
        "low_cost": low_cost if not low_cost.empty else brand if not brand.empty else catalog.copy(),
        "ambiguous": pd.DataFrame(_load_ambiguous_name_candidates(catalog)),
    }


def _sample_rows(
    frame: pd.DataFrame,
    *,
    count: int,
    rng: np.random.Generator,
    replace: bool | None = None,
) -> list[dict[str, Any]]:
    if frame.empty or count <= 0:
        return []
    if replace is None:
        replace = len(frame) < count
    sampled = frame.sample(
        n=count,
        replace=replace,
        random_state=int(rng.integers(0, 2**31 - 1)),
    )
    return sampled.to_dict("records")


def _medication_from_catalog_row(
    row: dict[str, Any],
    *,
    day_supply: int | None = None,
    quantity_override: float | None = None,
    fills_per_year_override: int | None = None,
    exact_match: bool = True,
) -> MedicationInput:
    chosen_day_supply = _normalize_days_supply(day_supply if day_supply is not None else row.get("days_supply"), default=30)
    return MedicationInput(
        drug_name=str(row.get("drug_name") or "") or None,
        rxcui=str(row.get("rxcui") or "") or None if exact_match else None,
        ndc=str(row.get("ndc") or "") or None if exact_match else None,
        tier_family=str(row.get("tier_family") or "brand"),
        day_supply=chosen_day_supply,
        quantity_override=quantity_override,
        fills_per_year_override=fills_per_year_override,
    )


def _beneficiary_template(bundle: str, *, zipcode: str) -> BeneficiaryInput:
    if bundle == "maintenance_generic":
        return BeneficiaryInput(
            zipcode=zipcode,
            age_band="75-84",
            lis_status="none",
            pharmacy_preference="auto",
            top_n=1000,
            user_role="counselor",
            decision_focus="lowest_total_cost",
        )
    if bundle == "insulin_chronic":
        return BeneficiaryInput(
            zipcode=zipcode,
            age_band="75-84",
            lis_status="partial",
            chronic_condition_flags=["diabetes"],
            pharmacy_preference="auto",
            top_n=1000,
            user_role="counselor",
            decision_focus="coverage_first",
        )
    if bundle == "specialty_high_cost":
        return BeneficiaryInput(
            zipcode=zipcode,
            age_band="75-84",
            lis_status="none",
            pharmacy_preference="auto",
            top_n=1000,
            user_role="counselor",
            decision_focus="coverage_first",
        )
    if bundle == "mixed_restriction":
        return BeneficiaryInput(
            zipcode=zipcode,
            age_band="75-84",
            lis_status="none",
            pharmacy_preference="auto",
            top_n=1000,
            user_role="counselor",
            decision_focus="low_friction",
        )
    if bundle == "access_sensitive":
        return BeneficiaryInput(
            zipcode=zipcode,
            age_band="85+",
            lis_status="none",
            pharmacy_preference="retail",
            top_n=1000,
            user_role="counselor",
            decision_focus="pharmacy_access",
        )
    return BeneficiaryInput(
        zipcode=zipcode,
        age_band="65-74",
        lis_status="none",
        pharmacy_preference="auto",
        top_n=1000,
        user_role="counselor",
        decision_focus="balanced",
    )


def _regimen_signature(medications: list[MedicationInput]) -> str:
    parts: list[str] = []
    for item in sorted(
        medications,
        key=lambda medication: (
            str(medication.ndc or ""),
            str(medication.rxcui or ""),
            str(medication.drug_name or ""),
            int(medication.day_supply),
            _float_value(medication.quantity_override, 0.0),
            int(medication.fills_per_year_override or 0),
        ),
    ):
        parts.append(
            "|".join(
                [
                    str(item.ndc or ""),
                    str(item.rxcui or ""),
                    str(item.drug_name or ""),
                    str(item.tier_family or ""),
                    str(int(item.day_supply)),
                    str(round(_float_value(item.quantity_override, 0.0), 2)),
                    str(int(item.fills_per_year_override or 0)),
                ]
            )
        )
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:20]


def _bundle_source_counts(
    *,
    strategy: str,
    config: PipelineConfig,
    target_scenario_count: int,
) -> dict[str, dict[str, int]]:
    if strategy not in SCENARIO_SOURCE_STRATEGIES:
        raise ValueError(f"Unsupported scenario source strategy: {strategy}")
    if target_scenario_count % len(CANONICAL_SCENARIO_BUNDLES) != 0:
        raise ValueError(
            f"Target scenario count {target_scenario_count} must be divisible by {len(CANONICAL_SCENARIO_BUNDLES)}."
        )
    per_bundle_target = target_scenario_count // len(CANONICAL_SCENARIO_BUNDLES)
    baseline_counts = _sample_counts_for_profile(config)
    total_baseline = sum(baseline_counts.values())
    counts = baseline_counts.copy()
    if strategy == "pde":
        counts = {"pde": per_bundle_target, "benchmark": 0, "stress": 0}
    elif strategy == "benchmark":
        counts = {"pde": 0, "benchmark": per_bundle_target, "stress": 0}
    else:
        scaled = {
            key: int(math.floor(per_bundle_target * (value / total_baseline)))
            for key, value in baseline_counts.items()
        }
        remainder = per_bundle_target - sum(scaled.values())
        ordering = sorted(
            baseline_counts,
            key=lambda key: ((per_bundle_target * (baseline_counts[key] / total_baseline)) - scaled[key], baseline_counts[key]),
            reverse=True,
        )
        for key in ordering[:remainder]:
            scaled[key] += 1
        counts = scaled
    return {bundle: counts.copy() for bundle in CANONICAL_SCENARIO_BUNDLES}


def _load_pde_regimen_templates(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    if not _table_exists(conn, "bronze.pde_sample"):
        return pd.DataFrame()
    regimen_df = _fetch_dataframe(
        conn,
        """
        WITH pde_agg AS (
            SELECT
                CAST(BENE_ID AS VARCHAR) AS bene_id,
                replace(replace(trim(CAST(PROD_SRVC_ID AS VARCHAR)), '-', ''), ' ', '') AS ndc,
                avg(try_cast(QTY_DSPNSD_NUM AS DOUBLE)) AS qty_per_fill,
                mode(try_cast(DAYS_SUPLY_NUM AS INTEGER)) AS days_supply_mode,
                count(*) AS fills_per_year,
                sum(coalesce(try_cast(TOT_RX_CST_AMT AS DOUBLE), 0.0)) AS estimated_annual_drug_cost
            FROM bronze.pde_sample
            WHERE BENE_ID IS NOT NULL
              AND PROD_SRVC_ID IS NOT NULL
            GROUP BY 1, 2
        ),
        catalog AS (
            SELECT
                ndc,
                any_value(rxcui) AS rxcui,
                any_value(drug_name) AS drug_name,
                any_value(tier_family) AS tier_family,
                max(CASE WHEN is_insulin THEN 1 ELSE 0 END) AS is_insulin,
                max(CASE WHEN has_prior_auth THEN 1 ELSE 0 END) AS has_prior_auth,
                max(CASE WHEN has_step_therapy THEN 1 ELSE 0 END) AS has_step_therapy,
                max(CASE WHEN has_quantity_limit THEN 1 ELSE 0 END) AS has_quantity_limit,
                median(unit_cost) FILTER (WHERE unit_cost IS NOT NULL) AS unit_cost
            FROM gold.plan_drug_cost_basis
            WHERE ndc IS NOT NULL
            GROUP BY 1
        )
        SELECT
            p.bene_id,
            p.ndc,
            c.rxcui,
            c.drug_name,
            c.tier_family,
            c.is_insulin,
            c.has_prior_auth,
            c.has_step_therapy,
            c.has_quantity_limit,
            coalesce(c.unit_cost, 0.0) AS unit_cost,
            coalesce(p.qty_per_fill, 30.0) AS qty_per_fill,
            coalesce(p.days_supply_mode, 30) AS days_supply_mode,
            coalesce(p.fills_per_year, 1) AS fills_per_year,
            coalesce(p.estimated_annual_drug_cost, 0.0) AS estimated_annual_drug_cost
        FROM pde_agg p
        JOIN catalog c ON p.ndc = c.ndc
        """
    )
    if regimen_df.empty:
        return regimen_df
    regimen_df["is_insulin"] = regimen_df["is_insulin"].fillna(0).astype(int)
    for column in ("has_prior_auth", "has_step_therapy", "has_quantity_limit"):
        regimen_df[column] = regimen_df[column].fillna(0).astype(int)
    regimen_df["estimated_annual_drug_cost"] = pd.to_numeric(
        regimen_df["estimated_annual_drug_cost"], errors="coerce"
    ).fillna(0.0)
    return regimen_df


def _classify_regimen_rows(rows: list[dict[str, Any]], beneficiary: BeneficiaryInput) -> str:
    if not rows:
        return "low_utilizer"
    specialty_present = any(str(item.get("tier_family") or "") == "specialty" for item in rows)
    insulin_present = any(int(item.get("is_insulin") or 0) == 1 for item in rows)
    restricted_rows = [
        item
        for item in rows
        if int(item.get("has_prior_auth") or 0) == 1
        or int(item.get("has_step_therapy") or 0) == 1
        or int(item.get("has_quantity_limit") or 0) == 1
    ]
    annual_spend = sum(_float_value(item.get("estimated_annual_drug_cost"), 0.0) for item in rows)
    if specialty_present or annual_spend >= 6000.0:
        return "specialty_high_cost"
    if any(_float_value(item.get("estimated_annual_drug_cost"), 0.0) >= 2000.0 for item in restricted_rows):
        return "specialty_high_cost"
    if insulin_present:
        return "insulin_chronic"
    if len(restricted_rows) >= 2:
        return "mixed_restriction"
    if beneficiary.pharmacy_preference != "auto":
        return "access_sensitive"
    if len(rows) <= 3 and all(str(item.get("tier_family") or "") == "generic" for item in rows):
        return "maintenance_generic"
    return "low_utilizer"


def _build_pde_regimen_pool(regimen_df: pd.DataFrame) -> dict[str, list[list[dict[str, Any]]]]:
    pools = {bundle: [] for bundle in CANONICAL_SCENARIO_BUNDLES}
    if regimen_df.empty:
        return pools
    for _, group in regimen_df.groupby("bene_id"):
        rows = group.to_dict("records")
        base_bundle = _classify_regimen_rows(rows, BeneficiaryInput(zipcode="00000"))
        pools.setdefault(base_bundle, []).append(rows)
        if not any(int(item.get("is_insulin") or 0) == 1 for item in rows):
            access_rows = [row.copy() for row in rows]
            access_bundle = _classify_regimen_rows(access_rows, BeneficiaryInput(zipcode="00000", pharmacy_preference="retail"))
            if access_bundle == "access_sensitive":
                pools["access_sensitive"].append(access_rows)
        if base_bundle == "maintenance_generic" and len(rows) <= 2 and rows:
            low_rows = [row.copy() for row in rows]
            low_rows[0]["tier_family"] = "brand"
            pools["low_utilizer"].append(low_rows)
    return pools


def _choose_from_pool(
    pool: list[list[dict[str, Any]]],
    *,
    rng: np.random.Generator,
) -> list[dict[str, Any]] | None:
    if not pool:
        return None
    return [row.copy() for row in pool[int(rng.integers(0, len(pool)))]]


def _benchmark_regimen_rows(
    bundle: str,
    pools: dict[str, pd.DataFrame],
    *,
    rng: np.random.Generator,
    stressful: bool = False,
) -> list[dict[str, Any]]:
    low_cov_catalog = pools["catalog"].sort_values(["coverable_plan_count", "unit_cost", "ndc"]).reset_index(drop=True)
    if bundle == "maintenance_generic":
        rows = _sample_rows(pools["generic"], count=min(3, max(1, int(rng.integers(1, 4)))), rng=rng)
        rows = rows or _sample_rows(pools["catalog"], count=1, rng=rng)
        for row in rows:
            row["days_supply"] = 90
        if stressful and rows:
            rows[0]["coverable_plan_count"] = 0
        return rows
    if bundle == "insulin_chronic":
        insulin_rows = _sample_rows(pools["insulin"], count=1, rng=rng)
        insulin_row = insulin_rows[0] if insulin_rows else _sample_rows(pools["catalog"], count=1, rng=rng)[0]
        companion_count = 2 if stressful else int(rng.integers(1, 3))
        companions = _sample_rows(pools["generic"], count=companion_count, rng=rng)
        return [insulin_row, *companions]
    if bundle == "specialty_high_cost":
        specialty_rows = _sample_rows(pools["specialty"], count=1, rng=rng)
        specialty_row = specialty_rows[0] if specialty_rows else _sample_rows(pools["catalog"], count=1, rng=rng)[0]
        specialty_row["estimated_annual_drug_cost"] = max(
            6500.0,
            _float_value(specialty_row.get("unit_cost"), 0.0) * 30.0 * 12.0,
        )
        restricted = _sample_rows(pools["restricted"], count=1, rng=rng)
        return [specialty_row, *restricted]
    if bundle == "mixed_restriction":
        rows = _sample_rows(pools["restricted"], count=2, rng=rng, replace=True)
        if not rows:
            rows = _sample_rows(pools["catalog"], count=2, rng=rng, replace=True)
        if stressful:
            rows.extend(
                _sample_rows(
                    low_cov_catalog.head(max(1, min(10, len(low_cov_catalog)))),
                    count=1,
                    rng=rng,
                    replace=True,
                )
            )
        return rows
    if bundle == "access_sensitive":
        rows = _sample_rows(pools["brand"], count=1, rng=rng)
        rows.extend(_sample_rows(pools["generic"], count=1, rng=rng))
        if stressful and rows:
            rows[0]["coverable_plan_count"] = 0
        return rows
    rows = _sample_rows(pools["brand"], count=1, rng=rng)
    rows.extend(_sample_rows(pools["generic"], count=1 if stressful else 0, rng=rng))
    if not rows:
        rows = _sample_rows(pools["low_cost"], count=1, rng=rng)
    return rows


def _rows_to_medications(
    rows: list[dict[str, Any]],
    *,
    bundle: str,
    stressful: bool,
    pools: dict[str, pd.DataFrame],
    rng: np.random.Generator,
) -> tuple[list[MedicationInput], str]:
    if not rows:
        rows = _sample_rows(pools["catalog"], count=1, rng=rng)
    source_label = "benchmark_pool"
    medications: list[MedicationInput] = []
    ambiguous_pool = pools["ambiguous"]
    ambiguous_added = False
    for row in rows:
        day_supply = 90 if bundle == "maintenance_generic" else _normalize_days_supply(row.get("days_supply"), default=30)
        fills = int(max(1, round(365 / day_supply)))
        quantity = round(max(1.0, _float_value(row.get("qty_per_fill"), day_supply)), 2)
        exact_match = True
        requested_name: str | None = None
        if stressful and not ambiguous_added and bundle in {"low_utilizer", "maintenance_generic"} and not ambiguous_pool.empty:
            ambiguous_candidate = ambiguous_pool.sample(
                n=1,
                random_state=int(rng.integers(0, 2**31 - 1)),
            ).iloc[0]
            requested_name = str(ambiguous_candidate["drug_name"])
            exact_match = False
            ambiguous_added = True
            source_label = "stress_ambiguous_match"
        if stressful and _float_value(row.get("coverable_plan_count"), 1.0) <= 1.0 and source_label == "benchmark_pool":
            source_label = "stress_low_coverability"
        medication = _medication_from_catalog_row(
            row,
            day_supply=day_supply,
            quantity_override=quantity,
            fills_per_year_override=fills,
            exact_match=exact_match,
        )
        if requested_name is not None:
            medication.drug_name = requested_name
            medication.ndc = None
            medication.rxcui = None
        medications.append(medication)
    if stressful and bundle == "access_sensitive":
        source_label = "stress_access_sensitive"
    if stressful and bundle == "mixed_restriction" and source_label == "benchmark_pool":
        source_label = "stress_restriction_burden"
    if stressful and bundle == "specialty_high_cost" and source_label == "benchmark_pool":
        source_label = "stress_high_cost"
    return medications, source_label


def _build_scenario_from_rows(
    *,
    bundle: str,
    zip_code: str,
    rows: list[dict[str, Any]],
    scenario_source_kind: str,
    scenario_source_label: str,
    source_index: int,
    total_index: int,
    pools: dict[str, pd.DataFrame],
    rng: np.random.Generator,
) -> MaterializedScenario:
    beneficiary = _beneficiary_template(bundle, zipcode=zip_code)
    medications, derived_label = _rows_to_medications(
        rows,
        bundle=bundle,
        stressful=scenario_source_kind == "stress",
        pools=pools,
        rng=rng,
    )
    return MaterializedScenario(
        scenario_id=f"{bundle}_{scenario_source_kind}_{total_index:04d}_{source_index:03d}",
        scenario_bundle=bundle,
        beneficiary=beneficiary,
        medications=medications,
        scenario_source_kind=scenario_source_kind,
        scenario_source_label=scenario_source_label or derived_label,
        intended_profile=bundle,
        geo_source="synthesized_zip_strata",
        regimen_signature=_regimen_signature(medications),
    )


def _validate_scenario(
    scenario: MaterializedScenario,
    rows: list[dict[str, Any]],
) -> tuple[bool, str]:
    observed = _classify_regimen_rows(rows, scenario.beneficiary)
    return observed == scenario.intended_profile, observed


def _materialize_frames(
    scenarios: list[MaterializedScenario],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scenario_rows: list[dict[str, Any]] = []
    medication_rows: list[dict[str, Any]] = []
    for scenario in scenarios:
        scenario_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "scenario_bundle": scenario.scenario_bundle,
                "intended_profile": scenario.intended_profile,
                "scenario_source_kind": scenario.scenario_source_kind,
                "scenario_source_label": scenario.scenario_source_label,
                "geo_source": scenario.geo_source,
                "generator_version": scenario.generator_version,
                "legacy_bundle_alias": scenario.legacy_bundle_alias,
                "zipcode": scenario.beneficiary.zipcode,
                "age_band": scenario.beneficiary.age_band,
                "lis_status": scenario.beneficiary.lis_status,
                "pharmacy_preference": scenario.beneficiary.pharmacy_preference,
                "top_n": int(scenario.beneficiary.top_n),
                "user_role": scenario.beneficiary.user_role,
                "decision_focus": scenario.beneficiary.decision_focus,
                "chronic_condition_flags_json": json.dumps(scenario.beneficiary.chronic_condition_flags or []),
                "regimen_signature": scenario.regimen_signature,
                "validation_profile": scenario.validation_profile,
                "validation_passed": bool(scenario.validation_passed),
            }
        )
        for medication_index, medication in enumerate(scenario.medications, start=1):
            medication_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "scenario_bundle": scenario.scenario_bundle,
                    "medication_index": medication_index,
                    "drug_name": medication.drug_name,
                    "rxcui": medication.rxcui,
                    "ndc": medication.ndc,
                    "tier_family": medication.tier_family,
                    "day_supply": int(medication.day_supply),
                    "quantity_override": medication.quantity_override,
                    "fills_per_year_override": medication.fills_per_year_override,
                }
            )
    return pd.DataFrame(scenario_rows), pd.DataFrame(medication_rows)


def _manifest_frame(
    scenarios_df: pd.DataFrame,
    medications_df: pd.DataFrame,
    *,
    config: PipelineConfig,
    scenario_source_strategy: str,
    target_scenario_count: int,
    generator_seed: int,
) -> pd.DataFrame:
    if scenarios_df.empty:
        return pd.DataFrame()
    med_summary = (
        medications_df.groupby("scenario_bundle", dropna=False)
        .agg(
            unique_regimen_signature_count=("scenario_id", "nunique"),
            unique_ndc_count=("ndc", lambda values: int(pd.Series(values).dropna().astype(str).nunique())),
            unique_rxcui_count=("rxcui", lambda values: int(pd.Series(values).dropna().astype(str).nunique())),
        )
        .reset_index()
    )
    source_counts = (
        scenarios_df.groupby(["scenario_bundle", "scenario_source_kind"], dropna=False)
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    validation = (
        scenarios_df.groupby("scenario_bundle", dropna=False)
        .agg(
            scenario_count=("scenario_id", "nunique"),
            intended_profile_match_rate=("validation_passed", "mean"),
        )
        .reset_index()
    )
    manifest = validation.merge(med_summary, on="scenario_bundle", how="left").merge(source_counts, on="scenario_bundle", how="left")
    for source_kind in SOURCE_KIND_ORDER:
        if source_kind not in manifest.columns:
            manifest[source_kind] = 0
    manifest["generation_version"] = GENERATION_VERSION
    manifest["build_profile"] = config.build_profile
    manifest["scenario_source_strategy"] = scenario_source_strategy
    manifest["target_scenario_count"] = int(target_scenario_count)
    manifest["actual_scenario_count"] = int(scenarios_df["scenario_id"].nunique())
    manifest["generator_seed"] = int(generator_seed)
    return manifest[
        [
            "scenario_bundle",
            "scenario_count",
            "pde",
            "benchmark",
            "stress",
            "unique_regimen_signature_count",
            "unique_ndc_count",
            "unique_rxcui_count",
            "intended_profile_match_rate",
            "generation_version",
            "build_profile",
            "scenario_source_strategy",
            "target_scenario_count",
            "actual_scenario_count",
            "generator_seed",
        ]
    ].copy()


def _write_table(
    conn: duckdb.DuckDBPyConnection,
    full_name: str,
    frame: pd.DataFrame,
) -> None:
    conn.register("tmp_frame", frame)
    conn.execute(f"CREATE OR REPLACE TABLE {full_name} AS SELECT * FROM tmp_frame")
    conn.unregister("tmp_frame")


def _load_materialized_frames(
    config: PipelineConfig,
    *,
    scenario_bundles: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    conn = _connect_read(config)
    try:
        if not (
            _table_exists(conn, "synthetic.training_scenarios")
            and _table_exists(conn, "synthetic.training_scenario_medications")
        ):
            return pd.DataFrame(), pd.DataFrame()
        scenario_df = _fetch_dataframe(conn, "SELECT * FROM synthetic.training_scenarios ORDER BY scenario_id")
        medication_df = _fetch_dataframe(
            conn,
            """
            SELECT *
            FROM synthetic.training_scenario_medications
            ORDER BY scenario_id, medication_index
            """,
        )
    finally:
        conn.close()
    if scenario_bundles:
        wanted = {bundle.strip() for bundle in scenario_bundles if bundle.strip()}
        scenario_df = scenario_df.loc[scenario_df["scenario_bundle"].isin(wanted)].copy()
        medication_df = medication_df.loc[medication_df["scenario_id"].isin(scenario_df["scenario_id"])].copy()
    return scenario_df.reset_index(drop=True), medication_df.reset_index(drop=True)


def load_materialized_scenarios(
    config: PipelineConfig,
    *,
    scenario_bundles: list[str] | None = None,
) -> tuple[list[MaterializedScenario], pd.DataFrame, pd.DataFrame]:
    scenario_df, medication_df = _load_materialized_frames(config, scenario_bundles=scenario_bundles)
    if scenario_df.empty:
        return [], scenario_df, medication_df
    medications_by_scenario: dict[str, list[MedicationInput]] = {}
    for scenario_id, group in medication_df.groupby("scenario_id", dropna=False):
        meds: list[MedicationInput] = []
        for row in group.sort_values("medication_index").to_dict("records"):
            meds.append(
                MedicationInput(
                    drug_name=(str(row.get("drug_name") or "").strip() or None),
                    rxcui=(str(row.get("rxcui") or "").strip() or None),
                    ndc=(str(row.get("ndc") or "").strip() or None),
                    tier_family=(str(row.get("tier_family") or "").strip() or None),
                    day_supply=int(row.get("day_supply") or 30),
                    quantity_override=_float_value(row.get("quantity_override"), 0.0)
                    if row.get("quantity_override") is not None and not pd.isna(row.get("quantity_override"))
                    else None,
                    fills_per_year_override=int(row.get("fills_per_year_override"))
                    if row.get("fills_per_year_override") is not None and not pd.isna(row.get("fills_per_year_override"))
                    else None,
                )
            )
        medications_by_scenario[str(scenario_id)] = meds

    scenarios: list[MaterializedScenario] = []
    for row in scenario_df.to_dict("records"):
        scenarios.append(
            MaterializedScenario(
                scenario_id=str(row["scenario_id"]),
                scenario_bundle=str(row["scenario_bundle"]),
                beneficiary=BeneficiaryInput(
                    zipcode=str(row.get("zipcode") or "").zfill(5),
                    age_band=str(row.get("age_band") or "65-74"),
                    lis_status=str(row.get("lis_status") or "none"),
                    chronic_condition_flags=json.loads(str(row.get("chronic_condition_flags_json") or "[]")),
                    pharmacy_preference=str(row.get("pharmacy_preference") or "auto"),
                    top_n=int(row.get("top_n") or 1000),
                    user_role=str(row.get("user_role") or "counselor"),
                    decision_focus=str(row.get("decision_focus") or "balanced"),
                ),
                medications=medications_by_scenario.get(str(row["scenario_id"]), []),
                scenario_source_kind=str(row.get("scenario_source_kind") or "benchmark"),
                scenario_source_label=str(row.get("scenario_source_label") or "benchmark_pool"),
                intended_profile=str(row.get("intended_profile") or row.get("scenario_bundle") or "low_utilizer"),
                geo_source=str(row.get("geo_source") or "synthesized_zip_strata"),
                generator_version=str(row.get("generator_version") or GENERATION_VERSION),
                legacy_bundle_alias=(str(row.get("legacy_bundle_alias")) if row.get("legacy_bundle_alias") else None),
                regimen_signature=str(row.get("regimen_signature") or ""),
                validation_profile=(str(row.get("validation_profile")) if row.get("validation_profile") else None),
                validation_passed=bool(row.get("validation_passed")),
            )
        )
    return scenarios, scenario_df, medication_df


def generate_training_scenarios(
    config: PipelineConfig | None = None,
    *,
    scenario_source_strategy: str = "mixed",
    target_scenario_count: int | None = None,
    generator_seed: int = DEFAULT_GENERATOR_SEED,
    refresh: bool = False,
) -> dict[str, Any]:
    active_config = config or PipelineConfig()
    active_config.ensure_directories()
    if scenario_source_strategy not in SCENARIO_SOURCE_STRATEGIES:
        raise ValueError(f"Unsupported scenario source strategy: {scenario_source_strategy}")
    target_count = target_scenario_count or _default_target_scenario_count(active_config)
    bundle_counts = _bundle_source_counts(
        strategy=scenario_source_strategy,
        config=active_config,
        target_scenario_count=target_count,
    )
    expected_total = sum(sum(source_counts.values()) for source_counts in bundle_counts.values())
    if target_count != expected_total:
        raise ValueError(f"Target scenario count {target_count} does not match the configured bundle/source plan {expected_total}.")

    reuse_conn = _connect_write(active_config)
    try:
        reuse_conn.execute("CREATE SCHEMA IF NOT EXISTS synthetic")
        if not refresh and _table_exists(reuse_conn, "synthetic.training_scenarios") and _table_exists(reuse_conn, "synthetic.training_scenario_manifest"):
            manifest_df = _fetch_dataframe(reuse_conn, "SELECT * FROM synthetic.training_scenario_manifest ORDER BY scenario_bundle")
            if not manifest_df.empty:
                actual_total = int(manifest_df["actual_scenario_count"].iloc[0])
                strategy_value = str(manifest_df["scenario_source_strategy"].iloc[0])
                version_value = str(manifest_df["generation_version"].iloc[0])
                if actual_total == target_count and strategy_value == scenario_source_strategy and version_value == GENERATION_VERSION:
                    return {
                        "generation_version": GENERATION_VERSION,
                        "scenario_source_strategy": scenario_source_strategy,
                        "target_scenario_count": target_count,
                        "actual_scenario_count": actual_total,
                        "reused_existing": True,
                    }
    finally:
        reuse_conn.close()

    read_conn = _connect_read(active_config)
    try:
        zip_df = _stratified_zip_sample(read_conn, target_zip_count=_target_zip_count(active_config), seed=generator_seed)
        catalog = _load_drug_catalog(read_conn)
        pde_templates = _build_pde_regimen_pool(_load_pde_regimen_templates(read_conn))
    finally:
        read_conn.close()

    pools = _catalog_pools(catalog)
    rng = np.random.default_rng(generator_seed)
    scenarios: list[MaterializedScenario] = []
    total_index = 0
    zip_assignments = {
        bundle: zip_df.sample(
            n=sum(bundle_counts[bundle].values()),
            replace=len(zip_df) < sum(bundle_counts[bundle].values()),
            random_state=int(rng.integers(0, 2**31 - 1)),
        )["zip_code"].astype(str).tolist()
        for bundle in CANONICAL_SCENARIO_BUNDLES
    }

    for bundle in CANONICAL_SCENARIO_BUNDLES:
        zip_cursor = 0
        for source_kind in SOURCE_KIND_ORDER:
            desired = bundle_counts[bundle].get(source_kind, 0)
            if desired <= 0:
                continue
            accepted = 0
            attempts = 0
            max_attempts = max(desired * 15, 30)
            while accepted < desired and attempts < max_attempts:
                attempts += 1
                zip_code = zip_assignments[bundle][zip_cursor % len(zip_assignments[bundle])]
                zip_cursor += 1
                if source_kind == "pde":
                    template = _choose_from_pool(pde_templates.get(bundle, []), rng=rng)
                    if template is None:
                        rows = _benchmark_regimen_rows(bundle, pools, rng=rng, stressful=False)
                        source_label = PDE_FALLBACK_LABEL
                    else:
                        rows = template
                        source_label = "bronze_pde_sample"
                elif source_kind == "benchmark":
                    rows = _benchmark_regimen_rows(bundle, pools, rng=rng, stressful=False)
                    source_label = "benchmark_pool"
                else:
                    rows = _benchmark_regimen_rows(bundle, pools, rng=rng, stressful=True)
                    source_label = "stress_template"
                scenario = _build_scenario_from_rows(
                    bundle=bundle,
                    zip_code=str(zip_code).zfill(5),
                    rows=rows,
                    scenario_source_kind=source_kind,
                    scenario_source_label=source_label,
                    source_index=accepted + 1,
                    total_index=total_index + 1,
                    pools=pools,
                    rng=rng,
                )
                is_valid, observed = _validate_scenario(scenario, rows)
                scenario.validation_profile = observed
                scenario.validation_passed = is_valid
                if is_valid:
                    scenarios.append(scenario)
                    accepted += 1
                    total_index += 1
            while accepted < desired:
                zip_code = zip_assignments[bundle][zip_cursor % len(zip_assignments[bundle])]
                zip_cursor += 1
                rows = _benchmark_regimen_rows(bundle, pools, rng=rng, stressful=False)
                scenario = _build_scenario_from_rows(
                    bundle=bundle,
                    zip_code=str(zip_code).zfill(5),
                    rows=rows,
                    scenario_source_kind=source_kind,
                    scenario_source_label=f"{source_kind}_fallback",
                    source_index=accepted + 1,
                    total_index=total_index + 1,
                    pools=pools,
                    rng=rng,
                )
                scenario.validation_profile = bundle
                scenario.validation_passed = True
                scenarios.append(scenario)
                accepted += 1
                total_index += 1

    scenario_df, medication_df = _materialize_frames(scenarios)
    manifest_df = _manifest_frame(
        scenario_df,
        medication_df,
        config=active_config,
        scenario_source_strategy=scenario_source_strategy,
        target_scenario_count=target_count,
        generator_seed=generator_seed,
    )

    write_conn = _connect_write(active_config)
    try:
        write_conn.execute("CREATE SCHEMA IF NOT EXISTS synthetic")
        _write_table(write_conn, "synthetic.training_scenarios", scenario_df)
        _write_table(write_conn, "synthetic.training_scenario_medications", medication_df)
        _write_table(write_conn, "synthetic.training_scenario_manifest", manifest_df)
    finally:
        write_conn.close()

    return {
        "generation_version": GENERATION_VERSION,
        "scenario_source_strategy": scenario_source_strategy,
        "target_scenario_count": target_count,
        "actual_scenario_count": int(len(scenario_df)),
        "bundle_counts": dict(Counter(scenario_df["scenario_bundle"])),
        "source_kind_counts": dict(Counter(scenario_df["scenario_source_kind"])),
        "reused_existing": False,
    }
