from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import duckdb

from .config import PipelineConfig
from .extract import SourcePaths, extract_sources


logger = logging.getLogger(__name__)


STATE_NAME_MAP = {
    "AL": "Alabama",
    "AK": "Alaska",
    "AZ": "Arizona",
    "AR": "Arkansas",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "DE": "Delaware",
    "FL": "Florida",
    "GA": "Georgia",
    "HI": "Hawaii",
    "ID": "Idaho",
    "IL": "Illinois",
    "IN": "Indiana",
    "IA": "Iowa",
    "KS": "Kansas",
    "KY": "Kentucky",
    "LA": "Louisiana",
    "ME": "Maine",
    "MD": "Maryland",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "MS": "Mississippi",
    "MO": "Missouri",
    "MT": "Montana",
    "NE": "Nebraska",
    "NV": "Nevada",
    "NH": "New Hampshire",
    "NJ": "New Jersey",
    "NM": "New Mexico",
    "NY": "New York",
    "NC": "North Carolina",
    "ND": "North Dakota",
    "OH": "Ohio",
    "OK": "Oklahoma",
    "OR": "Oregon",
    "PA": "Pennsylvania",
    "RI": "Rhode Island",
    "SC": "South Carolina",
    "SD": "South Dakota",
    "TN": "Tennessee",
    "TX": "Texas",
    "UT": "Utah",
    "VT": "Vermont",
    "VA": "Virginia",
    "WA": "Washington",
    "WV": "West Virginia",
    "WI": "Wisconsin",
    "WY": "Wyoming",
    "DC": "District of Columbia",
    "PR": "Puerto Rico",
}


def _sql_literal(path: Path) -> str:
    return path.as_posix().replace("'", "''")


def _csv_scan(path: Path, delim: str = ",", encoding: str = "utf-8") -> str:
    return (
        f"read_csv_auto('{_sql_literal(path)}', header=true, all_varchar=true, "
        f"delim='{delim}', nullstr=['', ' '], ignore_errors=false, encoding='{encoding}')"
    )


def _create_state_lookup(conn: duckdb.DuckDBPyConnection) -> None:
    escaped_values: list[str] = []
    for abbr, name in sorted(STATE_NAME_MAP.items()):
        escaped_name = name.replace("'", "''")
        escaped_values.append(f"('{abbr}', '{escaped_name}')")
    values = ", ".join(escaped_values)
    conn.execute(
        f"""
        CREATE OR REPLACE TABLE silver.state_lookup AS
        SELECT * FROM (VALUES {values}) AS t(state_abbr, state_name)
        """
    )


def _execute_step(
    conn: duckdb.DuckDBPyConnection,
    step_name: str,
    sql: str,
    checkpoint: bool = False,
) -> None:
    start = time.perf_counter()
    logger.info("build start %s", step_name)
    conn.execute(sql)
    if checkpoint:
        conn.execute("CHECKPOINT")
    elapsed = time.perf_counter() - start
    logger.info("build done %s in %.1fs", step_name, elapsed)


def _build_bronze(
    conn: duckdb.DuckDBPyConnection, config: PipelineConfig, sources: SourcePaths
) -> None:
    snapshot_quarter = config.snapshot_quarter.replace("'", "''")

    for table_name, path in sources.cms_files.items():
        _execute_step(
            conn,
            f"bronze.{table_name}",
            f"""
            CREATE OR REPLACE TABLE bronze.{table_name} AS
            SELECT
                *,
                '{path.name}' AS source_file,
                '{snapshot_quarter}' AS snapshot_quarter,
                current_timestamp AS load_ts
            FROM {_csv_scan(path, '|', 'latin-1')}
            """,
            checkpoint=table_name in {"plan_information", "basic_formulary", "pricing"},
        )

    _execute_step(
        conn,
        "bronze.pharmacy_network",
        f"""
        CREATE OR REPLACE VIEW bronze.pharmacy_network AS
        SELECT
            *,
            source_file,
            '{snapshot_quarter}' AS snapshot_quarter,
            current_timestamp AS load_ts
        FROM (
            SELECT *, filename AS source_file
            FROM read_csv_auto(
                [{", ".join(f"'{_sql_literal(path)}'" for path in sources.pharmacy_network_parts)}],
                header=true,
                all_varchar=true,
                delim='|',
                nullstr=['', ' '],
                filename=true,
                encoding='latin-1',
                strict_mode=false,
                null_padding=true,
                ignore_errors=true
            )
        )
        """,
    )

    _execute_step(
        conn,
        "bronze.rxcui_properties",
        f"""
        CREATE OR REPLACE TABLE bronze.rxcui_properties AS
        SELECT
            *,
            source_file,
            '{snapshot_quarter}' AS snapshot_quarter,
            current_timestamp AS load_ts
        FROM (
            SELECT *, filename AS source_file
            FROM read_csv_auto(
                [{", ".join(f"'{_sql_literal(path)}'" for path in sources.rxcui_files)}],
                header=true,
                all_varchar=true,
                delim=',',
                nullstr=['', ' '],
                filename=true
            )
        )
        """,
    )

    for table_name, path in sources.reference_files.items():
        _execute_step(
            conn,
            f"bronze.{table_name}",
            f"""
            CREATE OR REPLACE TABLE bronze.{table_name} AS
            SELECT
                *,
                '{path.name}' AS source_file,
                '{snapshot_quarter}' AS snapshot_quarter,
                current_timestamp AS load_ts
            FROM {_csv_scan(path, '|' if table_name == 'pde_sample' else ',', 'utf-8')}
            """,
        )


def _build_silver(conn: duckdb.DuckDBPyConnection, config: PipelineConfig) -> None:
    _create_state_lookup(conn)

    _execute_step(
        conn,
        "silver.dim_plan",
        """
        CREATE OR REPLACE TABLE silver.dim_plan AS
        WITH ranked AS (
            SELECT
                trim(CONTRACT_ID) AS contract_id,
                trim(PLAN_ID) AS plan_id,
                coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS segment_id,
                trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
                trim(CONTRACT_ID) || trim(PLAN_ID) AS contract_plan_key,
                trim(CONTRACT_NAME) AS contract_name,
                trim(PLAN_NAME) AS plan_name,
                trim(FORMULARY_ID) AS formulary_id,
                try_cast(trim(PREMIUM) AS DOUBLE) AS monthly_premium,
                try_cast(trim(DEDUCTIBLE) AS DOUBLE) AS deductible,
                try_cast(trim(MA_REGION_CODE) AS INTEGER) AS ma_region_code,
                try_cast(trim(PDP_REGION_CODE) AS INTEGER) AS pdp_region_code,
                upper(trim(STATE)) AS state_abbr,
                try_cast(trim(SNP) AS INTEGER) AS snp_flag,
                trim(PLAN_SUPPRESSED_YN) = 'Y' AS is_suppressed,
                substr(trim(CONTRACT_ID), 1, 1) AS plan_type,
                row_number() OVER (
                    PARTITION BY trim(CONTRACT_ID), trim(PLAN_ID), coalesce(nullif(trim(SEGMENT_ID), ''), '000')
                    ORDER BY
                        CASE WHEN trim(COUNTY_CODE) <> '' THEN 0 ELSE 1 END,
                        trim(COUNTY_CODE)
                ) AS rn
            FROM bronze.plan_information
        )
        SELECT
            contract_id,
            plan_id,
            segment_id,
            plan_key,
            contract_plan_key,
            contract_name,
            plan_name,
            formulary_id,
            monthly_premium,
            deductible,
            ma_region_code,
            pdp_region_code,
            state_abbr,
            snp_flag,
            is_suppressed,
            plan_type,
            CASE
                WHEN plan_type = 'S' THEN 'pdp_region'
                ELSE 'county'
            END AS service_area_type
        FROM ranked
        WHERE rn = 1
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "silver.dim_zipcode",
        """
        CREATE OR REPLACE TABLE silver.dim_zipcode AS
        WITH raw_zip AS (
            SELECT
                lpad(trim(zip_code), 5, '0') AS zip_code,
                trim(city) AS city,
                upper(trim(state)) AS state_abbr,
                trim(county) AS county_display,
                upper(regexp_replace(regexp_replace(trim(county), '(?i) county$', ''), '[^A-Za-z0-9 ]', '', 'g')) AS county_name_norm,
                try_cast(trim(lat) AS DOUBLE) AS lat,
                try_cast(trim(lng) AS DOUBLE) AS lng,
                try_cast(trim(population) AS DOUBLE) AS population,
                try_cast(trim(density) AS DOUBLE) AS density
            FROM bronze.us_zipcode_geo
        ),
        geo AS (
            SELECT
                trim(COUNTY_CODE) AS county_code,
                trim(STATENAME) AS state_name,
                upper(regexp_replace(trim(COUNTY), '[^A-Za-z0-9 ]', '', 'g')) AS county_name_norm
            FROM bronze.geographic_locator
        )
        SELECT
            z.zip_code,
            z.city,
            z.state_abbr,
            s.state_name,
            z.county_display,
            g.county_code,
            z.lat,
            z.lng,
            z.population,
            z.density,
            CASE
                WHEN z.density >= 1000 THEN 'urban'
                WHEN z.density >= 250 THEN 'suburban'
                ELSE 'rural'
            END AS density_category
        FROM raw_zip z
        LEFT JOIN silver.state_lookup s ON z.state_abbr = s.state_abbr
        LEFT JOIN geo g
          ON upper(s.state_name) = upper(g.state_name)
         AND z.county_name_norm = g.county_name_norm
        """,
    )

    _execute_step(
        conn,
        "silver.bridge_plan_service_area",
        """
        CREATE OR REPLACE TABLE silver.bridge_plan_service_area AS
        WITH ma_plans AS (
            SELECT DISTINCT
                trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
                trim(CONTRACT_NAME) AS plan_name,
                trim(CONTRACT_ID) || trim(PLAN_ID) AS contract_plan_key,
                substr(trim(CONTRACT_ID), 1, 1) AS plan_type,
                'county' AS service_area_type,
                upper(trim(STATE)) AS state_abbr,
                trim(COUNTY_CODE) AS county_code,
                NULL::INTEGER AS pdp_region_code
            FROM bronze.plan_information
            WHERE substr(trim(CONTRACT_ID), 1, 1) IN ('H', 'R')
              AND trim(COUNTY_CODE) <> ''
        ),
        pdp_plans AS (
            SELECT DISTINCT
                p.plan_key,
                p.plan_name,
                p.contract_plan_key,
                p.plan_type,
                p.service_area_type,
                NULL::VARCHAR AS state_abbr,
                trim(g.COUNTY_CODE) AS county_code,
                p.pdp_region_code
            FROM silver.dim_plan p
            JOIN bronze.geographic_locator g
              ON try_cast(trim(g.PDP_REGION_CODE) AS INTEGER) = p.pdp_region_code
            WHERE p.plan_type = 'S'
        )
        SELECT * FROM ma_plans
        UNION ALL
        SELECT * FROM pdp_plans
        """,
        checkpoint=True,
    )

    demo_zipcode_filter = ", ".join(f"'{zipcode}'" for zipcode in config.normalized_demo_zipcodes)
    if config.is_demo_profile and demo_zipcode_filter:
        scope_sql = f"""
        CREATE OR REPLACE TABLE silver.build_plan_scope AS
        WITH matched AS (
            SELECT DISTINCT b.plan_key
            FROM silver.bridge_plan_service_area b
            JOIN silver.dim_zipcode z
              ON z.county_code = b.county_code
            WHERE z.zip_code IN ({demo_zipcode_filter})
        )
        SELECT DISTINCT plan_key FROM matched
        UNION
        SELECT plan_key
        FROM silver.dim_plan
        WHERE NOT EXISTS (SELECT 1 FROM matched)
        """
    else:
        scope_sql = """
        CREATE OR REPLACE TABLE silver.build_plan_scope AS
        SELECT DISTINCT plan_key
        FROM silver.dim_plan
        """
    _execute_step(
        conn,
        "silver.build_plan_scope",
        scope_sql,
    )

    _execute_step(
        conn,
        "silver.dim_drug_reference",
        """
        CREATE OR REPLACE TABLE silver.dim_drug_reference AS
        WITH formulary_map AS (
            SELECT DISTINCT trim(RXCUI) AS rxcui, lpad(trim(NDC), 11, '0') AS ndc
            FROM bronze.basic_formulary
            WHERE trim(RXCUI) <> '' AND trim(NDC) <> ''
        ),
        insulin_map AS (
            SELECT DISTINCT trim(rxcui) AS rxcui, lpad(trim(ndc), 11, '0') AS ndc
            FROM bronze.insulin_reference
            WHERE trim(ndc) <> ''
        ),
        rxnorm_ranked AS (
            SELECT
                trim(rxcui) AS rxcui,
                trim(name) AS preferred_name,
                trim(synonym) AS synonym,
                trim(tty) AS tty,
                row_number() OVER (
                    PARTITION BY trim(rxcui)
                    ORDER BY
                        CASE WHEN trim(suppress) = 'N' THEN 0 ELSE 1 END,
                        CASE WHEN trim(tty) IN ('SCD', 'SBD') THEN 0 ELSE 1 END,
                        length(trim(name))
                ) AS rn
            FROM bronze.rxcui_properties
            WHERE trim(rxcui) <> ''
        ),
        combined AS (
            SELECT * FROM formulary_map
            UNION
            SELECT * FROM insulin_map
        )
        SELECT
            c.rxcui,
            c.ndc,
            coalesce(r.preferred_name, r.synonym, c.ndc) AS preferred_name,
            r.synonym,
            r.tty,
            CASE WHEN i.ndc IS NOT NULL OR i.rxcui IS NOT NULL THEN TRUE ELSE FALSE END AS is_insulin
        FROM combined c
        LEFT JOIN rxnorm_ranked r
          ON c.rxcui = r.rxcui
         AND r.rn = 1
        LEFT JOIN insulin_map i
          ON c.ndc = i.ndc
          OR c.rxcui = i.rxcui
        """,
    )

    _execute_step(
        conn,
        "silver.drug_utilization_defaults",
        """
        CREATE OR REPLACE TABLE silver.drug_utilization_defaults AS
        WITH ndc_tier AS (
            SELECT
                lpad(trim(NDC), 11, '0') AS ndc,
                avg(try_cast(trim(TIER_LEVEL_VALUE) AS DOUBLE)) AS avg_tier
            FROM bronze.basic_formulary
            WHERE trim(NDC) <> ''
            GROUP BY 1
        ),
        pde_norm AS (
            SELECT
                lpad(trim(PROD_SRVC_ID), 11, '0') AS ndc,
                try_cast(trim(QTY_DSPNSD_NUM) AS DOUBLE) AS quantity,
                CASE
                    WHEN try_cast(trim(DAYS_SUPLY_NUM) AS INTEGER) >= 75 THEN 90
                    WHEN try_cast(trim(DAYS_SUPLY_NUM) AS INTEGER) >= 45 THEN 60
                    ELSE 30
                END AS days_supply,
                upper(trim(BRND_GNRC_CD)) AS brand_generic
            FROM bronze.pde_sample
            WHERE trim(PROD_SRVC_ID) <> ''
              AND try_cast(trim(QTY_DSPNSD_NUM) AS DOUBLE) > 0
        ),
        typed AS (
            SELECT
                p.ndc,
                p.days_supply,
                coalesce(
                    CASE
                        WHEN t.avg_tier <= 2 THEN 'generic'
                        WHEN t.avg_tier >= 5 THEN 'specialty'
                        WHEN t.avg_tier IS NOT NULL THEN 'brand'
                        WHEN p.brand_generic = 'G' THEN 'generic'
                        ELSE 'brand'
                    END,
                    'brand'
                ) AS tier_family,
                p.quantity
            FROM pde_norm p
            LEFT JOIN ndc_tier t ON p.ndc = t.ndc
        ),
        specific AS (
            SELECT
                ndc,
                days_supply,
                tier_family,
                round(median(quantity), 2) AS default_quantity,
                cast(ceil(365.0 / days_supply) AS INTEGER) AS default_fills_per_year,
                count(*) AS observation_count,
                FALSE AS is_fallback
            FROM typed
            GROUP BY 1, 2, 3
        ),
        fallback AS (
            SELECT
                NULL::VARCHAR AS ndc,
                days_supply,
                tier_family,
                round(median(quantity), 2) AS default_quantity,
                cast(ceil(365.0 / days_supply) AS INTEGER) AS default_fills_per_year,
                count(*) AS observation_count,
                TRUE AS is_fallback
            FROM typed
            GROUP BY 2, 3
        )
        SELECT * FROM specific
        UNION ALL
        SELECT * FROM fallback
        """,
    )

    _execute_step(
        conn,
        "silver.fact_plan_drug_coverage",
        """
        CREATE OR REPLACE TABLE silver.fact_plan_drug_coverage AS
        WITH formulary AS (
            SELECT
                p.plan_key,
                p.contract_plan_key,
                p.plan_name,
                p.formulary_id,
                trim(bf.RXCUI) AS rxcui,
                lpad(trim(bf.NDC), 11, '0') AS ndc,
                try_cast(trim(bf.CONTRACT_YEAR) AS INTEGER) AS contract_year,
                try_cast(trim(bf.TIER_LEVEL_VALUE) AS INTEGER) AS tier_level_value,
                CASE
                    WHEN try_cast(trim(bf.TIER_LEVEL_VALUE) AS DOUBLE) <= 2 THEN 'generic'
                    WHEN try_cast(trim(bf.TIER_LEVEL_VALUE) AS DOUBLE) >= 5 THEN 'specialty'
                    ELSE 'brand'
                END AS tier_family,
                trim(bf.QUANTITY_LIMIT_YN) = 'Y' AS has_quantity_limit,
                try_cast(trim(bf.QUANTITY_LIMIT_AMOUNT) AS DOUBLE) AS quantity_limit_amount,
                try_cast(trim(bf.QUANTITY_LIMIT_DAYS) AS INTEGER) AS quantity_limit_days,
                trim(bf.PRIOR_AUTHORIZATION_YN) = 'Y' AS has_prior_auth,
                trim(bf.STEP_THERAPY_YN) = 'Y' AS has_step_therapy
            FROM silver.dim_plan p
            JOIN silver.build_plan_scope scope
              ON p.plan_key = scope.plan_key
            JOIN bronze.basic_formulary bf
              ON p.formulary_id = trim(bf.FORMULARY_ID)
        ),
        pricing AS (
            SELECT
                trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
                lpad(trim(NDC), 11, '0') AS ndc,
                try_cast(trim(DAYS_SUPPLY) AS INTEGER) AS days_supply,
                try_cast(trim(UNIT_COST) AS DOUBLE) AS unit_cost
            FROM bronze.pricing
        ),
        excluded AS (
            SELECT DISTINCT
                trim(CONTRACT_ID) || trim(PLAN_ID) AS contract_plan_key,
                trim(RXCUI) AS rxcui,
                trim(CAPPED_BENEFIT_YN) = 'Y' AS capped_benefit_flag
            FROM bronze.excluded_drugs
        ),
        indication AS (
            SELECT DISTINCT
                trim(CONTRACT_ID) || trim(PLAN_ID) AS contract_plan_key,
                trim(RXCUI) AS rxcui,
                trim(DISEASE) AS disease
            FROM bronze.indication_coverage
        )
        SELECT
            f.plan_key,
            f.rxcui,
            f.ndc,
            f.contract_year,
            f.tier_level_value,
            f.tier_family,
            pr.days_supply,
            pr.unit_cost,
            f.has_quantity_limit,
            f.quantity_limit_amount,
            f.quantity_limit_days,
            f.has_prior_auth,
            f.has_step_therapy,
            CASE WHEN e.rxcui IS NOT NULL THEN TRUE ELSE FALSE END AS is_excluded,
            e.capped_benefit_flag,
            CASE WHEN i.rxcui IS NOT NULL THEN TRUE ELSE FALSE END AS has_indication_restriction,
            i.disease AS indication_disease,
            CASE WHEN d.is_insulin THEN TRUE ELSE FALSE END AS is_insulin
        FROM formulary f
        LEFT JOIN pricing pr
          ON f.plan_key = pr.plan_key
         AND f.ndc = pr.ndc
        LEFT JOIN excluded e
          ON f.contract_plan_key = e.contract_plan_key
         AND f.rxcui = e.rxcui
        LEFT JOIN indication i
          ON f.contract_plan_key = i.contract_plan_key
         AND f.rxcui = i.rxcui
        LEFT JOIN silver.dim_drug_reference d
          ON f.ndc = d.ndc
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "silver.fact_plan_pharmacy",
        """
        CREATE OR REPLACE VIEW silver.fact_plan_pharmacy AS
        SELECT
            trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
            trim(PHARMACY_NUMBER) AS pharmacy_number,
            lpad(trim(PHARMACY_ZIPCODE), 5, '0') AS pharmacy_zipcode,
            trim(PREFERRED_STATUS_RETAIL) = 'Y' AS is_preferred_retail,
            trim(PREFERRED_STATUS_MAIL) = 'Y' AS is_preferred_mail,
            trim(PHARMACY_RETAIL) = 'Y' AS offers_retail,
            trim(PHARMACY_MAIL) = 'Y' AS offers_mail,
            try_cast(trim(IN_AREA_FLAG) AS INTEGER) = 1 AS is_in_area,
            try_cast(trim(FLOOR_PRICE) AS DOUBLE) AS floor_price,
            try_cast(trim(BRAND_DISPENSING_FEE_30) AS DOUBLE) AS brand_fee_30,
            try_cast(trim(BRAND_DISPENSING_FEE_60) AS DOUBLE) AS brand_fee_60,
            try_cast(trim(BRAND_DISPENSING_FEE_90) AS DOUBLE) AS brand_fee_90,
            try_cast(trim(GENERIC_DISPENSING_FEE_30) AS DOUBLE) AS generic_fee_30,
            try_cast(trim(GENERIC_DISPENSING_FEE_60) AS DOUBLE) AS generic_fee_60,
            try_cast(trim(GENERIC_DISPENSING_FEE_90) AS DOUBLE) AS generic_fee_90,
            z.city,
            z.state_abbr,
            z.county_code,
            z.lat,
            z.lng,
            z.population,
            z.density,
            z.density_category
        FROM bronze.pharmacy_network p
        JOIN silver.build_plan_scope scope
          ON trim(p.CONTRACT_ID) || trim(p.PLAN_ID) || coalesce(nullif(trim(p.SEGMENT_ID), ''), '000') = scope.plan_key
        LEFT JOIN silver.dim_zipcode z
          ON lpad(trim(p.PHARMACY_ZIPCODE), 5, '0') = z.zip_code
        WHERE coalesce(trim(p.CONTRACT_ID), '') <> ''
          AND coalesce(trim(p.PLAN_ID), '') <> ''
          AND coalesce(trim(p.PHARMACY_NUMBER), '') <> ''
          AND coalesce(trim(p.PHARMACY_ZIPCODE), '') <> ''
        """,
    )

    _execute_step(
        conn,
        "silver.plan_beneficiary_cost_rules",
        """
        CREATE OR REPLACE TABLE silver.plan_beneficiary_cost_rules AS
        SELECT
            trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
            try_cast(trim(COVERAGE_LEVEL) AS INTEGER) AS coverage_level,
            try_cast(trim(TIER) AS INTEGER) AS tier_level_value,
            CASE try_cast(trim(DAYS_SUPPLY) AS INTEGER)
                WHEN 1 THEN 30
                WHEN 4 THEN 60
                WHEN 2 THEN 90
                ELSE 30
            END AS days_supply,
            trim(DED_APPLIES_YN) IN ('1', 'Y') AS deductible_applies,
            try_cast(trim(COST_TYPE_PREF) AS INTEGER) AS pref_cost_type,
            try_cast(trim(COST_AMT_PREF) AS DOUBLE) AS pref_cost_amt,
            try_cast(trim(COST_MIN_AMT_PREF) AS DOUBLE) AS pref_cost_min,
            try_cast(trim(COST_MAX_AMT_PREF) AS DOUBLE) AS pref_cost_max,
            try_cast(trim(COST_TYPE_NONPREF) AS INTEGER) AS nonpref_cost_type,
            try_cast(trim(COST_AMT_NONPREF) AS DOUBLE) AS nonpref_cost_amt,
            try_cast(trim(COST_MIN_AMT_NONPREF) AS DOUBLE) AS nonpref_cost_min,
            try_cast(trim(COST_MAX_AMT_NONPREF) AS DOUBLE) AS nonpref_cost_max,
            try_cast(trim(COST_TYPE_MAIL_PREF) AS INTEGER) AS mail_pref_cost_type,
            try_cast(trim(COST_AMT_MAIL_PREF) AS DOUBLE) AS mail_pref_cost_amt,
            try_cast(trim(COST_MIN_AMT_MAIL_PREF) AS DOUBLE) AS mail_pref_cost_min,
            try_cast(trim(COST_MAX_AMT_MAIL_PREF) AS DOUBLE) AS mail_pref_cost_max,
            try_cast(trim(COST_TYPE_MAIL_NONPREF) AS INTEGER) AS mail_nonpref_cost_type,
            try_cast(trim(COST_AMT_MAIL_NONPREF) AS DOUBLE) AS mail_nonpref_cost_amt,
            try_cast(trim(COST_MIN_AMT_MAIL_NONPREF) AS DOUBLE) AS mail_nonpref_cost_min,
            try_cast(trim(COST_MAX_AMT_MAIL_NONPREF) AS DOUBLE) AS mail_nonpref_cost_max
        FROM bronze.beneficiary_cost
        WHERE trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') IN (
            SELECT plan_key FROM silver.build_plan_scope
        )
        """,
    )

    _execute_step(
        conn,
        "silver.plan_insulin_cost_rules",
        """
        CREATE OR REPLACE TABLE silver.plan_insulin_cost_rules AS
        SELECT
            trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') AS plan_key,
            CASE WHEN trim(TIER) IN ('', '.') THEN NULL ELSE try_cast(trim(TIER) AS INTEGER) END AS tier_level_value,
            CASE try_cast(trim(DAYS_SUPPLY) AS INTEGER)
                WHEN 1 THEN 30
                WHEN 4 THEN 60
                WHEN 2 THEN 90
                ELSE 30
            END AS days_supply,
            try_cast(trim(copay_amt_pref_insln) AS DOUBLE) AS pref_copay,
            try_cast(trim(copay_amt_nonpref_insln) AS DOUBLE) AS nonpref_copay,
            try_cast(trim(copay_amt_mail_pref_insln) AS DOUBLE) AS mail_pref_copay,
            try_cast(trim(copay_amt_mail_nonpref_insln) AS DOUBLE) AS mail_nonpref_copay
        FROM bronze.insulin_beneficiary_cost
        WHERE trim(CONTRACT_ID) || trim(PLAN_ID) || coalesce(nullif(trim(SEGMENT_ID), ''), '000') IN (
            SELECT plan_key FROM silver.build_plan_scope
        )
        """,
        checkpoint=True,
    )


def _build_gold(conn: duckdb.DuckDBPyConnection, config: PipelineConfig) -> None:
    zip_scope_filter = ""
    if config.is_demo_profile and config.normalized_demo_zipcodes:
        zip_values = ", ".join(f"'{zipcode}'" for zipcode in config.normalized_demo_zipcodes)
        zip_scope_filter = f" AND z.zip_code IN ({zip_values})"

    _execute_step(
        conn,
        "gold.plan_service_area",
        f"""
        CREATE OR REPLACE TABLE gold.plan_service_area AS
        SELECT DISTINCT
            z.zip_code,
            z.state_abbr,
            z.county_code,
            b.plan_key,
            p.plan_name,
            p.plan_type,
            p.service_area_type
        FROM silver.dim_zipcode z
        JOIN silver.bridge_plan_service_area b
          ON z.county_code = b.county_code
        JOIN silver.dim_plan p
          ON b.plan_key = p.plan_key
        WHERE p.is_suppressed = FALSE
          AND z.county_code IS NOT NULL
          {zip_scope_filter}
        """,
    )

    _execute_step(
        conn,
        "gold.plan_channel_summary",
        """
        CREATE OR REPLACE TABLE gold.plan_channel_summary AS
        WITH metrics AS (
            SELECT
                plan_key,
                count(*) AS total_pharmacies,
                count(*) FILTER (WHERE is_in_area) AS in_area_pharmacies,
                count(*) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS preferred_retail_count,
                count(*) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS standard_retail_count,
                count(*) FILTER (WHERE offers_mail AND is_preferred_mail) AS preferred_mail_count,
                count(*) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS standard_mail_count,
                min(floor_price) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_floor,
                min(floor_price) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_floor,
                min(floor_price) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_floor,
                min(floor_price) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_floor,
                min(brand_fee_30) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_brand_fee_30,
                min(brand_fee_60) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_brand_fee_60,
                min(brand_fee_90) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_brand_fee_90,
                min(generic_fee_30) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_generic_fee_30,
                min(generic_fee_60) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_generic_fee_60,
                min(generic_fee_90) FILTER (WHERE is_in_area AND offers_retail AND is_preferred_retail) AS pref_retail_generic_fee_90,
                min(brand_fee_30) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_brand_fee_30,
                min(brand_fee_60) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_brand_fee_60,
                min(brand_fee_90) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_brand_fee_90,
                min(generic_fee_30) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_generic_fee_30,
                min(generic_fee_60) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_generic_fee_60,
                min(generic_fee_90) FILTER (WHERE is_in_area AND offers_retail AND NOT is_preferred_retail) AS nonpref_retail_generic_fee_90,
                min(brand_fee_30) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_brand_fee_30,
                min(brand_fee_60) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_brand_fee_60,
                min(brand_fee_90) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_brand_fee_90,
                min(generic_fee_30) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_generic_fee_30,
                min(generic_fee_60) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_generic_fee_60,
                min(generic_fee_90) FILTER (WHERE offers_mail AND is_preferred_mail) AS pref_mail_generic_fee_90,
                min(brand_fee_30) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_brand_fee_30,
                min(brand_fee_60) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_brand_fee_60,
                min(brand_fee_90) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_brand_fee_90,
                min(generic_fee_30) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_generic_fee_30,
                min(generic_fee_60) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_generic_fee_60,
                min(generic_fee_90) FILTER (WHERE offers_mail AND NOT is_preferred_mail) AS nonpref_mail_generic_fee_90
            FROM silver.fact_plan_pharmacy
            GROUP BY 1
        )
        SELECT
            *,
            preferred_retail_count > 0 AS has_pref_retail,
            standard_retail_count > 0 AS has_nonpref_retail,
            preferred_mail_count > 0 AS has_pref_mail,
            standard_mail_count > 0 AS has_nonpref_mail
        FROM metrics
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.plan_preferred_pharmacy_locations",
        """
        CREATE OR REPLACE TABLE gold.plan_preferred_pharmacy_locations AS
        SELECT DISTINCT
            plan_key,
            pharmacy_number,
            pharmacy_zipcode,
            lat,
            lng
        FROM silver.fact_plan_pharmacy
        WHERE is_in_area = TRUE
          AND offers_retail = TRUE
          AND is_preferred_retail = TRUE
          AND lat IS NOT NULL
          AND lng IS NOT NULL
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.plan_formulary_summary",
        """
        CREATE OR REPLACE TABLE gold.plan_formulary_summary AS
        WITH universe AS (
            SELECT count(DISTINCT ndc) AS total_distinct_ndc
            FROM silver.fact_plan_drug_coverage
        ),
        metrics AS (
            SELECT
                plan_key,
                count(DISTINCT ndc) AS covered_drug_count,
                count(DISTINCT ndc) FILTER (WHERE is_insulin) AS insulin_drug_count,
                avg(CASE WHEN tier_family = 'generic' THEN 1.0 ELSE 0.0 END) AS generic_tier_pct,
                avg(CASE WHEN tier_family = 'specialty' THEN 1.0 ELSE 0.0 END) AS specialty_tier_pct,
                avg(CASE WHEN has_prior_auth THEN 1.0 ELSE 0.0 END) AS pa_rate,
                avg(CASE WHEN has_step_therapy THEN 1.0 ELSE 0.0 END) AS st_rate,
                avg(CASE WHEN has_quantity_limit THEN 1.0 ELSE 0.0 END) AS ql_rate,
                avg(CASE WHEN is_excluded THEN 1.0 ELSE 0.0 END) AS excluded_rate,
                avg(CASE WHEN is_insulin THEN 1.0 ELSE 0.0 END) AS insulin_coverage_pct
            FROM silver.fact_plan_drug_coverage
            GROUP BY 1
        )
        SELECT
            m.plan_key,
            m.covered_drug_count,
            m.insulin_drug_count,
            CASE
                WHEN u.total_distinct_ndc > 0
                THEN m.covered_drug_count::DOUBLE / u.total_distinct_ndc::DOUBLE
                ELSE 0.0
            END AS formulary_breadth_pct,
            round(m.generic_tier_pct, 4) AS generic_tier_pct,
            round(m.specialty_tier_pct, 4) AS specialty_tier_pct,
            round(m.pa_rate, 4) AS pa_rate,
            round(m.st_rate, 4) AS st_rate,
            round(m.ql_rate, 4) AS ql_rate,
            round(m.excluded_rate, 4) AS excluded_rate,
            round(m.insulin_coverage_pct, 4) AS insulin_coverage_pct,
            CASE
                WHEN (coalesce(m.pa_rate, 0.0) + coalesce(m.st_rate, 0.0) + coalesce(m.ql_rate, 0.0)) >= 0.60 THEN 2
                WHEN (coalesce(m.pa_rate, 0.0) + coalesce(m.st_rate, 0.0) + coalesce(m.ql_rate, 0.0)) >= 0.30 THEN 1
                ELSE 0
            END AS restrictiveness_class
        FROM metrics m
        CROSS JOIN universe u
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.plan_network_summary",
        """
        CREATE OR REPLACE TABLE gold.plan_network_summary AS
        SELECT
            plan_key,
            total_pharmacies,
            in_area_pharmacies,
            preferred_retail_count,
            standard_retail_count,
            preferred_mail_count,
            standard_mail_count,
            has_pref_retail,
            has_nonpref_retail,
            has_pref_mail,
            has_nonpref_mail,
            CASE
                WHEN preferred_retail_count = 0 THEN 'no_preferred_retail'
                WHEN preferred_retail_count < 10 THEN 'limited_preferred_retail'
                ELSE 'adequate'
            END AS network_flag
        FROM gold.plan_channel_summary
        """,
    )

    _execute_step(
        conn,
        "gold.plan_drug_cost_basis",
        """
        CREATE OR REPLACE TABLE gold.plan_drug_cost_basis AS
        WITH initial_rules AS (
            SELECT * FROM silver.plan_beneficiary_cost_rules WHERE coverage_level = 1
        ),
        predeductible_rules AS (
            SELECT * FROM silver.plan_beneficiary_cost_rules WHERE coverage_level = 0
        )
        SELECT
            c.plan_key,
            c.rxcui,
            c.ndc,
            c.contract_year,
            coalesce(d_ndc.preferred_name, d_rx.preferred_name) AS drug_name,
            c.days_supply,
            c.tier_level_value,
            c.tier_family,
            c.unit_cost,
            c.is_insulin,
            c.is_excluded,
            c.has_prior_auth,
            c.has_step_therapy,
            c.has_quantity_limit,
            c.quantity_limit_amount,
            c.quantity_limit_days,
            coalesce(i.deductible_applies, pre.deductible_applies, FALSE) AS deductible_applies,
            pre.pref_cost_type AS pre_pref_cost_type,
            pre.pref_cost_amt AS pre_pref_cost_amt,
            pre.pref_cost_min AS pre_pref_cost_min,
            pre.pref_cost_max AS pre_pref_cost_max,
            pre.nonpref_cost_type AS pre_nonpref_cost_type,
            pre.nonpref_cost_amt AS pre_nonpref_cost_amt,
            pre.nonpref_cost_min AS pre_nonpref_cost_min,
            pre.nonpref_cost_max AS pre_nonpref_cost_max,
            pre.mail_pref_cost_type AS pre_mail_pref_cost_type,
            pre.mail_pref_cost_amt AS pre_mail_pref_cost_amt,
            pre.mail_pref_cost_min AS pre_mail_pref_cost_min,
            pre.mail_pref_cost_max AS pre_mail_pref_cost_max,
            pre.mail_nonpref_cost_type AS pre_mail_nonpref_cost_type,
            pre.mail_nonpref_cost_amt AS pre_mail_nonpref_cost_amt,
            pre.mail_nonpref_cost_min AS pre_mail_nonpref_cost_min,
            pre.mail_nonpref_cost_max AS pre_mail_nonpref_cost_max,
            i.pref_cost_type AS init_pref_cost_type,
            i.pref_cost_amt AS init_pref_cost_amt,
            i.pref_cost_min AS init_pref_cost_min,
            i.pref_cost_max AS init_pref_cost_max,
            i.nonpref_cost_type AS init_nonpref_cost_type,
            i.nonpref_cost_amt AS init_nonpref_cost_amt,
            i.nonpref_cost_min AS init_nonpref_cost_min,
            i.nonpref_cost_max AS init_nonpref_cost_max,
            i.mail_pref_cost_type AS init_mail_pref_cost_type,
            i.mail_pref_cost_amt AS init_mail_pref_cost_amt,
            i.mail_pref_cost_min AS init_mail_pref_cost_min,
            i.mail_pref_cost_max AS init_mail_pref_cost_max,
            i.mail_nonpref_cost_type AS init_mail_nonpref_cost_type,
            i.mail_nonpref_cost_amt AS init_mail_nonpref_cost_amt,
            i.mail_nonpref_cost_min AS init_mail_nonpref_cost_min,
            i.mail_nonpref_cost_max AS init_mail_nonpref_cost_max,
            insulin.pref_copay AS insulin_pref_copay,
            insulin.nonpref_copay AS insulin_nonpref_copay,
            insulin.mail_pref_copay AS insulin_mail_pref_copay,
            insulin.mail_nonpref_copay AS insulin_mail_nonpref_copay
        FROM silver.fact_plan_drug_coverage c
        LEFT JOIN silver.dim_drug_reference d_ndc
          ON c.ndc = d_ndc.ndc
        LEFT JOIN (
            SELECT rxcui, any_value(preferred_name) AS preferred_name
            FROM silver.dim_drug_reference
            GROUP BY 1
        ) d_rx
          ON c.rxcui = d_rx.rxcui
        LEFT JOIN initial_rules i
          ON c.plan_key = i.plan_key
         AND c.tier_level_value = i.tier_level_value
         AND c.days_supply = i.days_supply
        LEFT JOIN predeductible_rules pre
          ON c.plan_key = pre.plan_key
         AND c.tier_level_value = pre.tier_level_value
         AND c.days_supply = pre.days_supply
        LEFT JOIN silver.plan_insulin_cost_rules insulin
          ON c.plan_key = insulin.plan_key
         AND c.days_supply = insulin.days_supply
         AND (insulin.tier_level_value IS NULL OR c.tier_level_value = insulin.tier_level_value)
        WHERE c.days_supply IN (30, 60, 90)
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.plan_summary",
        """
        CREATE OR REPLACE TABLE gold.plan_summary AS
        WITH service_counts AS (
            SELECT plan_key, count(DISTINCT county_code) AS served_counties
            FROM silver.bridge_plan_service_area
            GROUP BY 1
        ),
        contract_years AS (
            SELECT plan_key, max(contract_year) AS contract_year
            FROM gold.plan_drug_cost_basis
            GROUP BY 1
        )
        SELECT
            p.plan_key,
            p.contract_id,
            p.plan_id,
            p.segment_id,
            p.plan_name,
            p.contract_name,
            p.plan_type,
            p.service_area_type,
            cy.contract_year,
            p.state_abbr,
            p.ma_region_code,
            p.pdp_region_code,
            p.monthly_premium,
            round(p.monthly_premium * 12, 2) AS annual_premium,
            p.deductible,
            p.is_suppressed,
            s.served_counties,
            f.covered_drug_count,
            f.insulin_drug_count,
            round(f.formulary_breadth_pct, 4) AS formulary_breadth_pct,
            round(f.generic_tier_pct, 4) AS generic_tier_pct,
            round(f.specialty_tier_pct, 4) AS specialty_tier_pct,
            round(f.pa_rate, 4) AS pa_rate,
            round(f.st_rate, 4) AS st_rate,
            round(f.ql_rate, 4) AS ql_rate,
            round(f.excluded_rate, 4) AS excluded_rate,
            round(f.insulin_coverage_pct, 4) AS insulin_coverage_pct,
            f.restrictiveness_class
        FROM silver.dim_plan p
        JOIN silver.build_plan_scope scope
          ON p.plan_key = scope.plan_key
        LEFT JOIN gold.plan_formulary_summary f ON p.plan_key = f.plan_key
        LEFT JOIN service_counts s ON p.plan_key = s.plan_key
        LEFT JOIN contract_years cy ON p.plan_key = cy.plan_key
        WHERE p.is_suppressed = FALSE
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.drug_input_defaults",
        "CREATE OR REPLACE TABLE gold.drug_input_defaults AS SELECT * FROM silver.drug_utilization_defaults",
    )

    _execute_step(
        conn,
        "gold.recommendation_features",
        """
        CREATE OR REPLACE TABLE gold.recommendation_features AS
        SELECT
            p.plan_key,
            p.plan_name,
            p.plan_type,
            p.service_area_type,
            p.contract_year,
            p.annual_premium,
            p.deductible,
            p.served_counties,
            p.covered_drug_count,
            p.insulin_drug_count,
            p.formulary_breadth_pct,
            p.generic_tier_pct,
            p.specialty_tier_pct,
            p.pa_rate,
            p.st_rate,
            p.ql_rate,
            p.excluded_rate,
            p.insulin_coverage_pct,
            p.restrictiveness_class,
            n.in_area_pharmacies,
            n.preferred_retail_count,
            n.standard_retail_count,
            n.preferred_mail_count,
            n.standard_mail_count,
            n.network_flag
        FROM gold.plan_summary p
        LEFT JOIN gold.plan_network_summary n ON p.plan_key = n.plan_key
        """,
        checkpoint=True,
    )

    _execute_step(
        conn,
        "gold.ui_plan_drug_serving",
        """
        CREATE OR REPLACE VIEW gold.ui_plan_drug_serving AS
        SELECT
            basis.plan_key,
            summary.plan_name,
            summary.contract_year,
            summary.annual_premium,
            summary.deductible,
            network.network_flag,
            basis.rxcui,
            basis.ndc,
            basis.drug_name,
            basis.days_supply,
            basis.tier_level_value,
            basis.tier_family,
            basis.unit_cost,
            basis.is_insulin,
            basis.is_excluded,
            basis.has_prior_auth,
            basis.has_step_therapy,
            basis.has_quantity_limit,
            basis.deductible_applies
        FROM gold.plan_drug_cost_basis basis
        LEFT JOIN gold.plan_summary summary ON basis.plan_key = summary.plan_key
        LEFT JOIN gold.plan_network_summary network ON basis.plan_key = network.plan_key
        """,
    )

    _execute_step(
        conn,
        "gold.ui_plan_comparison_base",
        """
        CREATE OR REPLACE VIEW gold.ui_plan_comparison_base AS
        SELECT
            summary.plan_key,
            summary.plan_name,
            summary.plan_type,
            summary.service_area_type,
            summary.contract_year,
            summary.annual_premium,
            summary.deductible,
            summary.covered_drug_count,
            summary.insulin_drug_count,
            summary.formulary_breadth_pct,
            summary.generic_tier_pct,
            summary.specialty_tier_pct,
            summary.pa_rate,
            summary.st_rate,
            summary.ql_rate,
            summary.excluded_rate,
            summary.insulin_coverage_pct,
            summary.restrictiveness_class,
            network.in_area_pharmacies,
            network.preferred_retail_count,
            network.preferred_mail_count,
            network.network_flag
        FROM gold.plan_summary summary
        LEFT JOIN gold.plan_network_summary network ON summary.plan_key = network.plan_key
        """,
    )


def _write_manifest(config: PipelineConfig, sources: SourcePaths) -> None:
    manifest_path = config.staging_dir / "manifest.json"
    payload = {
        "snapshot_quarter": config.snapshot_quarter,
        "build_profile": config.build_profile,
        "benefit_design_mode": config.benefit_design_mode,
        "demo_zipcodes": list(config.normalized_demo_zipcodes),
        "cms_files": {key: str(value) for key, value in sources.cms_files.items()},
        "pharmacy_network_parts": [str(value) for value in sources.pharmacy_network_parts],
        "reference_files": {key: str(value) for key, value in sources.reference_files.items()},
        "rxcui_files": [str(value) for value in sources.rxcui_files],
    }
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_database(
    config: PipelineConfig, sources: SourcePaths | None = None, rebuild: bool = True
) -> Path:
    config.ensure_directories()
    if sources is None:
        sources = extract_sources(config)
    _write_manifest(config, sources)
    logger.info(
        "starting build profile=%s snapshot=%s db=%s",
        config.build_profile,
        config.snapshot_quarter,
        config.db_path,
    )

    if rebuild and config.db_path.exists():
        config.db_path.unlink()

    conn = duckdb.connect(str(config.db_path))
    temp_dir = config.staging_dir / "duckdb_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    conn.execute(f"SET temp_directory = '{_sql_literal(temp_dir)}'")
    conn.execute(f"PRAGMA threads={max(1, os.cpu_count() or 4)}")
    conn.execute("SET preserve_insertion_order = false")
    conn.execute("SET enable_object_cache = true")
    conn.execute("PRAGMA enable_progress_bar=false")
    conn.execute("CREATE SCHEMA IF NOT EXISTS bronze")
    conn.execute("CREATE SCHEMA IF NOT EXISTS silver")
    conn.execute("CREATE SCHEMA IF NOT EXISTS gold")
    conn.execute("CREATE SCHEMA IF NOT EXISTS synthetic")

    _build_bronze(conn, config, sources)
    _build_silver(conn, config)
    _build_gold(conn, config)
    conn.close()
    logger.info("build complete db=%s", config.db_path)
    return config.db_path


def health_check(config: PipelineConfig | None = None) -> dict[str, object]:
    active_config = config or PipelineConfig()
    payload: dict[str, object] = {
        "build_profile": active_config.build_profile,
        "db_path": str(active_config.db_path),
        "ok": False,
        "checks": [],
    }
    if not active_config.db_path.exists():
        payload["checks"] = [
            {
                "name": "database_exists",
                "ok": False,
                "detail": "DuckDB database file is missing.",
            }
        ]
        return payload

    conn = duckdb.connect(str(active_config.db_path), read_only=True)
    checks: list[dict[str, object]] = []
    available_objects = {
        f"{row[0]}.{row[1]}"
        for row in conn.execute(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            UNION ALL
            SELECT table_schema, table_name
            FROM information_schema.views
            """
        ).fetchall()
    }
    for table_name in (
        "gold.plan_summary",
        "gold.plan_formulary_summary",
        "gold.plan_service_area",
        "gold.plan_drug_cost_basis",
        "gold.ui_plan_comparison_base",
    ):
        if table_name not in available_objects:
            checks.append(
                {
                    "name": table_name,
                    "ok": False,
                    "detail": "Missing from catalog. The database appears unbuilt or partially built.",
                }
            )
            continue
        try:
            row_count = conn.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0]
            checks.append(
                {
                    "name": table_name,
                    "ok": row_count > 0,
                    "row_count": int(row_count),
                }
            )
        except duckdb.Error as exc:
            checks.append(
                {
                    "name": table_name,
                    "ok": False,
                    "detail": str(exc),
                }
            )
    conn.close()
    payload["checks"] = checks
    payload["ok"] = all(bool(check["ok"]) for check in checks)
    return payload


def run_pipeline(config: PipelineConfig | None = None, rebuild: bool = True) -> Path:
    active_config = config or PipelineConfig()
    sources = extract_sources(active_config)
    return build_database(active_config, sources=sources, rebuild=rebuild)
