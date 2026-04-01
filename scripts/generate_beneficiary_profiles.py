from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cms_mpd.config import PipelineConfig


DEFAULT_SEED = 42


def _connect(config: PipelineConfig) -> duckdb.DuckDBPyConnection:
    if not config.db_path.exists():
        raise FileNotFoundError(
            f"DuckDB database not found at {config.db_path}. Run `python -m cms_mpd build` first."
        )
    return duckdb.connect(str(config.db_path))


def _query_df(conn: duckdb.DuckDBPyConnection, sql: str, params: list | None = None) -> pd.DataFrame:
    if params:
        return conn.execute(sql, params).fetch_df()
    return conn.execute(sql).fetch_df()


def assign_risk_segment(cost_series: pd.Series) -> pd.Series:
    risk = pd.cut(
        pd.to_numeric(cost_series, errors="coerce").fillna(0.0),
        bins=[-np.inf, 2000.0, 5000.0, np.inf],
        labels=["LOW", "MED", "HIGH"],
    )
    return risk.astype(str).replace({"nan": "MED"})


def load_rxcui_reference(config: PipelineConfig) -> pd.DataFrame:
    files = sorted(config.rxcui_dir.glob("*.csv"))
    if not files:
        return pd.DataFrame(columns=["rxcui", "drug_name", "drug_synonym", "tty"])

    frames = []
    wanted_cols = {"rxcui", "name", "synonym", "tty", "language", "suppress"}
    for file_path in files:
        df = pd.read_csv(
            file_path,
            dtype=str,
            usecols=lambda col: str(col).strip().lower() in wanted_cols,
        )
        df.columns = [str(col).strip().lower() for col in df.columns]
        frames.append(df)

    ref = pd.concat(frames, ignore_index=True)
    for col in ["rxcui", "name", "synonym", "tty", "language", "suppress"]:
        if col not in ref.columns:
            ref[col] = ""
        ref[col] = ref[col].fillna("").astype(str).str.strip()

    ref = ref[
        (ref["rxcui"] != "")
        & ((ref["language"] == "") | (ref["language"].str.upper() == "ENG"))
        & (ref["suppress"].str.upper() != "Y")
    ].copy()
    ref["name_len"] = ref["name"].str.len().fillna(9999).astype(int)
    ref = ref.sort_values(["rxcui", "name_len", "name"]).drop_duplicates("rxcui", keep="first")
    return ref.rename(columns={"name": "drug_name", "synonym": "drug_synonym"})[
        ["rxcui", "drug_name", "drug_synonym", "tty"]
    ].copy()


def load_formulary_drug_pool(conn: duckdb.DuckDBPyConnection, max_drugs: int | None = 5000) -> pd.DataFrame:
    limit_clause = f"LIMIT {int(max_drugs)}" if max_drugs and int(max_drugs) > 0 else ""
    sql = f"""
        WITH ndc_agg AS (
            SELECT
                ndc,
                any_value(rxcui) AS rxcui,
                min(tier_level_value) AS tier_level,
                max(CASE WHEN has_prior_auth THEN 1 ELSE 0 END) AS has_prior_auth,
                max(CASE WHEN has_step_therapy THEN 1 ELSE 0 END) AS has_step_therapy,
                max(CASE WHEN has_quantity_limit THEN 1 ELSE 0 END) AS has_quantity_limit,
                max(CASE WHEN is_insulin THEN 1 ELSE 0 END) AS is_insulin,
                count(DISTINCT plan_key) AS formulary_coverage,
                median(unit_cost) FILTER (WHERE unit_cost IS NOT NULL) AS typical_unit_cost
            FROM silver.fact_plan_drug_coverage
            WHERE ndc IS NOT NULL
            GROUP BY 1
        )
        SELECT
            ndc,
            rxcui,
            coalesce(tier_level, 4) AS tier_level,
            has_prior_auth,
            has_step_therapy,
            has_quantity_limit,
            is_insulin,
            formulary_coverage,
            coalesce(typical_unit_cost, 0.0) AS typical_unit_cost
        FROM ndc_agg
        ORDER BY formulary_coverage DESC, ndc
        {limit_clause}
    """
    pool = _query_df(conn, sql)
    if pool.empty:
        raise RuntimeError("No formulary drug pool found in silver.fact_plan_drug_coverage.")
    return pool


def load_zip_pool(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    zip_df = _query_df(
        conn,
        """
        SELECT
            zip_code,
            state_abbr AS state,
            county_code,
            lat,
            lng,
            density,
            coalesce(population, 1.0) AS population
        FROM silver.dim_zipcode
        WHERE zip_code IS NOT NULL
          AND county_code IS NOT NULL
          AND state_abbr IS NOT NULL
          AND lat IS NOT NULL
          AND lng IS NOT NULL
        """,
    )
    if zip_df.empty:
        raise RuntimeError("No ZIP geography found in silver.dim_zipcode.")
    zip_df["population"] = pd.to_numeric(zip_df["population"], errors="coerce").fillna(1.0).clip(lower=1.0)
    return zip_df


def build_rxcui_maps(ref: pd.DataFrame) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    if ref.empty:
        return {}, {}, {}
    key = ref["rxcui"].astype(str)
    return (
        dict(zip(key, ref["drug_name"].astype(str))),
        dict(zip(key, ref["drug_synonym"].astype(str))),
        dict(zip(key, ref["tty"].astype(str))),
    )


def create_synthetic_beneficiaries(num_beneficiaries: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    bene_ids = [f"SYNTH_{idx:06d}" for idx in range(num_beneficiaries)]
    risk_segments = rng.choice(["LOW", "MED", "HIGH"], size=num_beneficiaries, p=[0.5, 0.3, 0.2])
    insulin_flags = rng.choice([0, 1], size=num_beneficiaries, p=[0.85, 0.15])

    unique_drugs = []
    fills_target = []
    total_rx_cost_est = []
    for risk in risk_segments:
        if risk == "LOW":
            drugs = int(rng.integers(1, 4))
            total_cost = float(rng.uniform(500.0, 2000.0))
        elif risk == "MED":
            drugs = int(rng.integers(3, 7))
            total_cost = float(rng.uniform(2000.0, 5000.0))
        else:
            drugs = int(rng.integers(5, 12))
            total_cost = float(rng.uniform(5000.0, 15000.0))
        unique_drugs.append(drugs)
        fills_target.append(int(max(1, drugs * rng.uniform(3.0, 5.0))))
        total_rx_cost_est.append(round(total_cost, 2))

    return pd.DataFrame(
        {
            "bene_synth_id": bene_ids,
            "risk_segment": risk_segments,
            "unique_drugs": unique_drugs,
            "fills_target": fills_target,
            "total_rx_cost_est": total_rx_cost_est,
            "insulin_user_flag": insulin_flags,
        }
    )


def assign_geography(bene_df: pd.DataFrame, zip_pool: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    probs = zip_pool["population"].to_numpy(dtype=float)
    probs = probs / probs.sum()
    sampled_idx = rng.choice(zip_pool.index.to_numpy(), size=len(bene_df), replace=True, p=probs)
    sampled = zip_pool.loc[sampled_idx].reset_index(drop=True)
    assigned = bene_df.reset_index(drop=True).copy()
    assigned["zip_code"] = sampled["zip_code"].astype(str)
    assigned["state"] = sampled["state"].astype(str)
    assigned["county_code"] = sampled["county_code"].astype(str)
    assigned["lat"] = pd.to_numeric(sampled["lat"], errors="coerce")
    assigned["lng"] = pd.to_numeric(sampled["lng"], errors="coerce")
    assigned["density"] = pd.to_numeric(sampled["density"], errors="coerce")
    return assigned


def allocate_fills_across_drugs(fills_target: int, drug_count: int, rng: np.random.Generator) -> np.ndarray:
    if drug_count <= 0:
        return np.array([], dtype=int)
    target = int(max(drug_count, fills_target))
    if drug_count == 1:
        return np.array([target], dtype=int)
    shares = rng.dirichlet(np.ones(drug_count))
    fills = np.maximum(np.floor(shares * target).astype(int), 1)
    while fills.sum() < target:
        fills[int(rng.integers(0, drug_count))] += 1
    while fills.sum() > target:
        candidates = np.where(fills > 1)[0]
        if len(candidates) == 0:
            break
        fills[int(rng.choice(candidates))] -= 1
    return fills


def generate_prescriptions(
    bene_df: pd.DataFrame,
    drug_pool: pd.DataFrame,
    *,
    seed: int,
    rxcui_name_map: dict[str, str],
    rxcui_synonym_map: dict[str, str],
    rxcui_tty_map: dict[str, str],
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    pool = drug_pool.drop_duplicates("ndc").reset_index(drop=True).copy()
    weights = pool["formulary_coverage"].astype(float).to_numpy()
    weights = weights / weights.sum()
    insulin_indices = np.where(pool["is_insulin"].astype(int).to_numpy() == 1)[0]
    insulin_weights = None
    if len(insulin_indices) > 0:
        insulin_weights = weights[insulin_indices]
        insulin_weights = insulin_weights / insulin_weights.sum()

    tier_fill_cost = {1: 15.0, 2: 35.0, 3: 80.0, 4: 160.0, 5: 300.0, 6: 450.0, 7: 600.0}
    rows: list[dict] = []
    for bene in bene_df.itertuples(index=False):
        drug_count = min(int(max(1, bene.unique_drugs)), len(pool))
        selected = rng.choice(len(pool), size=drug_count, replace=False, p=weights)
        if int(bene.insulin_user_flag) == 1 and len(insulin_indices) > 0:
            if len(set(selected) & set(insulin_indices)) == 0:
                selected[0] = int(rng.choice(insulin_indices, p=insulin_weights))
        fills_alloc = allocate_fills_across_drugs(int(bene.fills_target), len(selected), rng)
        for idx, fills_per_year in zip(selected, fills_alloc, strict=False):
            drug = pool.iloc[int(idx)]
            days_supply = int(rng.choice([30, 60, 90], p=[0.7, 0.1, 0.2]))
            qty_per_fill = float(round(max(1.0, rng.normal(days_supply, max(5.0, days_supply * 0.2))), 2))
            tier_level = int(drug["tier_level"])
            median_unit_cost = pd.to_numeric(drug.get("typical_unit_cost"), errors="coerce")
            median_unit_cost = float(median_unit_cost) if not pd.isna(median_unit_cost) else 0.0
            if median_unit_cost <= 0:
                median_unit_cost = tier_fill_cost.get(tier_level, 140.0) / 30.0
            unit_cost = max(0.05, median_unit_cost * float(rng.uniform(0.85, 1.15)))
            annual_cost = round(unit_cost * qty_per_fill * int(fills_per_year), 2)
            rxcui = str(drug["rxcui"] or "").strip()
            drug_name = rxcui_name_map.get(rxcui) or rxcui_synonym_map.get(rxcui) or f"NDC {drug['ndc']}"
            rows.append(
                {
                    "bene_synth_id": bene.bene_synth_id,
                    "ndc": str(drug["ndc"]),
                    "rxcui": rxcui,
                    "drug_name": drug_name,
                    "drug_synonym": rxcui_synonym_map.get(rxcui, ""),
                    "drug_tty": rxcui_tty_map.get(rxcui, ""),
                    "drug_name_source": "rxcui_info" if not str(drug_name).startswith("NDC ") else "fallback_ndc",
                    "fills_per_year": int(fills_per_year),
                    "days_supply_mode": days_supply,
                    "qty_per_fill": qty_per_fill,
                    "tier_level": tier_level,
                    "has_prior_auth": int(drug["has_prior_auth"]),
                    "has_step_therapy": int(drug["has_step_therapy"]),
                    "has_quantity_limit": int(drug["has_quantity_limit"]),
                    "is_insulin": int(drug["is_insulin"]),
                    "estimated_annual_drug_cost": annual_cost,
                    "source_mode": "synthetic",
                }
            )
    return pd.DataFrame(rows)


def create_from_pde(
    conn: duckdb.DuckDBPyConnection,
    config: PipelineConfig,
    *,
    pde_file: Path,
    num_beneficiaries: int | None,
    rxcui_name_map: dict[str, str],
    rxcui_synonym_map: dict[str, str],
    rxcui_tty_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not pde_file.exists():
        raise FileNotFoundError(f"PDE file not found: {pde_file}")

    pde_df = pd.read_csv(
        pde_file,
        delimiter="|",
        usecols=["BENE_ID", "PROD_SRVC_ID", "QTY_DSPNSD_NUM", "DAYS_SUPLY_NUM", "FILL_NUM", "TOT_RX_CST_AMT"],
        dtype={"BENE_ID": str, "PROD_SRVC_ID": str},
    )
    pde_df["ndc"] = (
        pde_df["PROD_SRVC_ID"].astype(str).str.replace("-", "", regex=False).str.replace(" ", "", regex=False).str.strip()
    )
    pde_df = pde_df[pde_df["ndc"] != ""].copy()
    if num_beneficiaries:
        keep = pde_df["BENE_ID"].drop_duplicates().head(int(num_beneficiaries))
        pde_df = pde_df[pde_df["BENE_ID"].isin(keep)].copy()

    rx_df = (
        pde_df.groupby(["BENE_ID", "ndc"], as_index=False)
        .agg(
            fills_per_year=("FILL_NUM", "count"),
            days_supply_mode=("DAYS_SUPLY_NUM", lambda values: int(pd.Series(values).mode().iloc[0]) if len(values) else 30),
            qty_per_fill=("QTY_DSPNSD_NUM", "mean"),
            estimated_annual_drug_cost=("TOT_RX_CST_AMT", "sum"),
        )
        .rename(columns={"BENE_ID": "bene_synth_id"})
    )

    pool = load_formulary_drug_pool(conn, max_drugs=None)
    rx_df = rx_df.merge(
        pool[["ndc", "rxcui", "tier_level", "has_prior_auth", "has_step_therapy", "has_quantity_limit", "is_insulin"]],
        on="ndc",
        how="inner",
    )
    if rx_df.empty:
        raise RuntimeError("No PDE drugs matched the formulary drug pool.")

    rx_df["rxcui"] = rx_df["rxcui"].fillna("").astype(str).str.strip()
    rx_df["drug_name"] = rx_df["rxcui"].map(rxcui_name_map).fillna("")
    empty_name = rx_df["drug_name"].astype(str).str.strip() == ""
    rx_df.loc[empty_name, "drug_name"] = rx_df.loc[empty_name, "rxcui"].map(rxcui_synonym_map).fillna("")
    empty_name = rx_df["drug_name"].astype(str).str.strip() == ""
    rx_df.loc[empty_name, "drug_name"] = "NDC " + rx_df.loc[empty_name, "ndc"].astype(str)
    rx_df["drug_synonym"] = rx_df["rxcui"].map(rxcui_synonym_map).fillna("")
    rx_df["drug_tty"] = rx_df["rxcui"].map(rxcui_tty_map).fillna("")
    rx_df["drug_name_source"] = np.where(
        rx_df["drug_name"].astype(str).str.startswith("NDC "), "fallback_ndc", "rxcui_info"
    )
    rx_df["source_mode"] = "pde"

    bene_df = (
        rx_df.groupby("bene_synth_id", as_index=False)
        .agg(
            unique_drugs=("ndc", "nunique"),
            fills_target=("fills_per_year", "sum"),
            total_rx_cost_est=("estimated_annual_drug_cost", "sum"),
            insulin_user_flag=("is_insulin", "max"),
        )
    )
    bene_df["risk_segment"] = assign_risk_segment(bene_df["total_rx_cost_est"])
    zip_pool = load_zip_pool(conn)
    bene_df = assign_geography(bene_df, zip_pool, DEFAULT_SEED)
    return bene_df, rx_df


def align_beneficiary_summary(bene_df: pd.DataFrame, rx_df: pd.DataFrame) -> pd.DataFrame:
    agg = (
        rx_df.groupby("bene_synth_id", as_index=False)
        .agg(
            unique_drugs=("ndc", "nunique"),
            fills_target=("fills_per_year", "sum"),
            total_rx_cost_est=("estimated_annual_drug_cost", "sum"),
            insulin_user_flag=("is_insulin", "max"),
        )
    )
    agg["risk_segment"] = assign_risk_segment(agg["total_rx_cost_est"])
    passthrough_cols = [
        "bene_synth_id",
        "state",
        "county_code",
        "zip_code",
        "lat",
        "lng",
        "density",
    ]
    return bene_df[passthrough_cols].merge(agg, on="bene_synth_id", how="inner")


def save_to_database(conn: duckdb.DuckDBPyConnection, bene_df: pd.DataFrame, rx_df: pd.DataFrame) -> None:
    conn.execute("CREATE SCHEMA IF NOT EXISTS synthetic")
    conn.execute("DROP TABLE IF EXISTS synthetic.syn_beneficiary")
    conn.execute("DROP TABLE IF EXISTS synthetic.syn_beneficiary_prescriptions")
    conn.register("bene_data", bene_df)
    conn.register("rx_data", rx_df)
    conn.execute(
        """
        CREATE TABLE synthetic.syn_beneficiary AS
        SELECT
            CAST(bene_synth_id AS VARCHAR) AS bene_synth_id,
            CAST(state AS VARCHAR) AS state,
            CAST(county_code AS VARCHAR) AS county_code,
            CAST(zip_code AS VARCHAR) AS zip_code,
            CAST(lat AS DOUBLE) AS lat,
            CAST(lng AS DOUBLE) AS lng,
            CAST(density AS DOUBLE) AS density,
            CAST(risk_segment AS VARCHAR) AS risk_segment,
            CAST(unique_drugs AS INTEGER) AS unique_drugs,
            CAST(fills_target AS INTEGER) AS fills_target,
            CAST(total_rx_cost_est AS DOUBLE) AS total_rx_cost_est,
            CAST(insulin_user_flag AS INTEGER) AS insulin_user_flag,
            CURRENT_TIMESTAMP AS created_at
        FROM bene_data
        """
    )
    conn.execute(
        """
        CREATE TABLE synthetic.syn_beneficiary_prescriptions AS
        SELECT
            CAST(bene_synth_id AS VARCHAR) AS bene_synth_id,
            CAST(ndc AS VARCHAR) AS ndc,
            CAST(rxcui AS VARCHAR) AS rxcui,
            CAST(drug_name AS VARCHAR) AS drug_name,
            CAST(drug_synonym AS VARCHAR) AS drug_synonym,
            CAST(drug_tty AS VARCHAR) AS drug_tty,
            CAST(drug_name_source AS VARCHAR) AS drug_name_source,
            CAST(fills_per_year AS INTEGER) AS fills_per_year,
            CAST(days_supply_mode AS INTEGER) AS days_supply_mode,
            CAST(qty_per_fill AS DOUBLE) AS qty_per_fill,
            CAST(tier_level AS INTEGER) AS tier_level,
            CAST(has_prior_auth AS INTEGER) AS has_prior_auth,
            CAST(has_step_therapy AS INTEGER) AS has_step_therapy,
            CAST(has_quantity_limit AS INTEGER) AS has_quantity_limit,
            CAST(is_insulin AS INTEGER) AS is_insulin,
            CAST(estimated_annual_drug_cost AS DOUBLE) AS estimated_annual_drug_cost,
            CAST(source_mode AS VARCHAR) AS source_mode,
            CURRENT_TIMESTAMP AS created_at
        FROM rx_data
        """
    )
    conn.execute("CREATE INDEX idx_syn_bene_id ON synthetic.syn_beneficiary(bene_synth_id)")
    conn.execute("CREATE INDEX idx_syn_bene_zip ON synthetic.syn_beneficiary(zip_code)")
    conn.execute("CREATE INDEX idx_syn_rx_bene_id ON synthetic.syn_beneficiary_prescriptions(bene_synth_id)")
    conn.execute("CREATE INDEX idx_syn_rx_ndc ON synthetic.syn_beneficiary_prescriptions(ndc)")


def print_summary(bene_df: pd.DataFrame, rx_df: pd.DataFrame) -> None:
    print(f"[OK] synthetic.syn_beneficiary rows: {len(bene_df):,}")
    print(f"[OK] synthetic.syn_beneficiary_prescriptions rows: {len(rx_df):,}")
    print(f"[OK] beneficiaries with insulin: {int(bene_df['insulin_user_flag'].sum()):,}")
    print(f"[OK] average drugs per beneficiary: {rx_df.groupby('bene_synth_id')['ndc'].nunique().mean():.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic beneficiary and prescription tables")
    parser.add_argument("--num-beneficiaries", type=int, default=10000)
    parser.add_argument("--from-pde", action="store_true")
    parser.add_argument("--pde-file", default="")
    parser.add_argument("--max-drugs", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--build-profile", default="full", choices=["full", "demo"])
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--source-data-dir", default="")
    args = parser.parse_args()

    config = PipelineConfig(
        build_profile=args.build_profile,
        data_dir=Path(args.data_dir) if args.data_dir else None,
        source_data_dir=Path(args.source_data_dir) if args.source_data_dir else None,
    )

    conn = _connect(config)
    try:
        rxcui_ref = load_rxcui_reference(config)
        rxcui_name_map, rxcui_synonym_map, rxcui_tty_map = build_rxcui_maps(rxcui_ref)
        if args.from_pde:
            pde_path = Path(args.pde_file) if args.pde_file else (config.reference_dir / "pde.csv")
            bene_df, rx_df = create_from_pde(
                conn,
                config,
                pde_file=pde_path,
                num_beneficiaries=(args.num_beneficiaries if args.num_beneficiaries != 10000 else None),
                rxcui_name_map=rxcui_name_map,
                rxcui_synonym_map=rxcui_synonym_map,
                rxcui_tty_map=rxcui_tty_map,
            )
        else:
            bene_df = create_synthetic_beneficiaries(args.num_beneficiaries, args.seed)
            bene_df = assign_geography(bene_df, load_zip_pool(conn), args.seed)
            rx_df = generate_prescriptions(
                bene_df,
                load_formulary_drug_pool(conn, args.max_drugs),
                seed=args.seed,
                rxcui_name_map=rxcui_name_map,
                rxcui_synonym_map=rxcui_synonym_map,
                rxcui_tty_map=rxcui_tty_map,
            )
            bene_df = align_beneficiary_summary(bene_df, rx_df)

        if bene_df.empty or rx_df.empty:
            raise RuntimeError("Generated synthetic data is empty.")
        save_to_database(conn, bene_df, rx_df)
        print_summary(bene_df, rx_df)
        return 0
    except Exception as exc:  # pragma: no cover - CLI error path
        print(f"[ERROR] {exc}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
