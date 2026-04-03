from __future__ import annotations

import importlib.util
from pathlib import Path

import duckdb
import pandas as pd

from cms_mpd.config import PipelineConfig
from cms_mpd.extract import SourcePaths
from cms_mpd.modeling import (
    build_training_dataset,
    evaluate_hybrid_reranker,
    load_hybrid_reranker,
    train_hybrid_reranker,
)
from cms_mpd.pipeline import build_database, health_check
from cms_mpd.recommend import BeneficiaryInput, MedicationInput, recommend_plans


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


def _load_generator_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate_beneficiary_profiles.py"
    spec = importlib.util.spec_from_file_location("cms_mpd_generate_beneficiary_profiles", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pipeline_build_and_recommendation_smoke(tmp_path):
    root = tmp_path / "repo"
    data_dir = root / "data"
    staging_dir = data_dir / "staging" / "2025-Q3" / "raw"
    refs_dir = data_dir / "references_data"
    rxcui_dir = data_dir / "rxcui_info"

    plan_information = _write(
        staging_dir / "plan_information.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|CONTRACT_NAME|PLAN_NAME|FORMULARY_ID|PREMIUM|DEDUCTIBLE|MA_REGION_CODE|PDP_REGION_CODE|STATE|COUNTY_CODE|SNP|PLAN_SUPPRESSED_YN
        H1000|001|000|Org A|Plan A|FORM1|30.00|100| | |OH|39001|0|N
        S2000|001|000|Org B|Plan B|FORM2|20.00|0| |5| | |0|N
        """,
    )
    basic_formulary = _write(
        staging_dir / "basic_formulary.txt",
        """
        FORMULARY_ID|FORMULARY_VERSION|CONTRACT_YEAR|RXCUI|NDC|TIER_LEVEL_VALUE|QUANTITY_LIMIT_YN|QUANTITY_LIMIT_AMOUNT|QUANTITY_LIMIT_DAYS|PRIOR_AUTHORIZATION_YN|STEP_THERAPY_YN
        FORM1|1|2025|111111|00000000001|1|N|||N|N
        FORM1|1|2025|222222|00000000002|3|Y|1|30|Y|N
        FORM2|1|2025|111111|00000000001|1|N|||N|N
        FORM2|1|2025|222222|00000000002|3|Y|1|30|Y|Y
        """,
    )
    beneficiary_cost = _write(
        staging_dir / "beneficiary_cost.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|COVERAGE_LEVEL|TIER|DAYS_SUPPLY|COST_TYPE_PREF|COST_AMT_PREF|COST_MIN_AMT_PREF|COST_MAX_AMT_PREF|COST_TYPE_NONPREF|COST_AMT_NONPREF|COST_MIN_AMT_NONPREF|COST_MAX_AMT_NONPREF|COST_TYPE_MAIL_PREF|COST_AMT_MAIL_PREF|COST_MIN_AMT_MAIL_PREF|COST_MAX_AMT_MAIL_PREF|COST_TYPE_MAIL_NONPREF|COST_AMT_MAIL_NONPREF|COST_MIN_AMT_MAIL_NONPREF|COST_MAX_AMT_MAIL_NONPREF|TIER_SPECIALTY_YN|DED_APPLIES_YN
        H1000|001|000|0|1|1|1|2|0|999|1|4|0|999|1|2|0|999|1|4|0|999|N|N
        H1000|001|000|1|1|1|1|2|0|999|1|4|0|999|1|2|0|999|1|4|0|999|N|N
        H1000|001|000|0|3|1|2|0.25|0|999|2|0.35|0|999|2|0.20|0|999|2|0.30|0|999|N|Y
        H1000|001|000|1|3|1|2|0.25|0|999|2|0.35|0|999|2|0.20|0|999|2|0.30|0|999|N|Y
        S2000|001|000|0|1|1|1|1.5|0|999|1|3|0|999|1|1|0|999|1|2|0|999|N|N
        S2000|001|000|1|1|1|1|1.5|0|999|1|3|0|999|1|1|0|999|1|2|0|999|N|N
        S2000|001|000|0|3|1|1|15|0|999|1|20|0|999|1|12|0|999|1|18|0|999|N|N
        S2000|001|000|1|3|1|1|15|0|999|1|20|0|999|1|12|0|999|1|18|0|999|N|N
        """,
    )
    insulin_beneficiary_cost = _write(
        staging_dir / "insulin_beneficiary_cost.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|TIER|DAYS_SUPPLY|copay_amt_pref_insln|copay_amt_nonpref_insln|copay_amt_mail_pref_insln|copay_amt_mail_nonpref_insln
        H1000|001|000|3|1|35|35|30|35
        S2000|001|000|3|1|25|35|20|30
        """,
    )
    pricing = _write(
        staging_dir / "pricing.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|NDC|DAYS_SUPPLY|UNIT_COST
        H1000|001|000|00000000001|30|1.00
        H1000|001|000|00000000002|30|5.00
        S2000|001|000|00000000001|30|1.20
        S2000|001|000|00000000002|30|4.00
        """,
    )
    geographic_locator = _write(
        staging_dir / "geographic_locator.txt",
        """
        COUNTY_CODE|STATENAME|COUNTY|MA_REGION_CODE|MA_REGION|PDP_REGION_CODE|PDP_REGION
        39001|Ohio|Alpha|10|OH MA|5|OH PDP
        """,
    )
    excluded_drugs = _write(
        staging_dir / "excluded_drugs.txt",
        """
        CONTRACT_ID|PLAN_ID|RXCUI|TIER|QUANTITY_LIMIT_YN|QUANTITY_LIMIT_AMOUNT|QUANTITY_LIMIT_DAYS|PRIOR_AUTH_YN|STEP_THERAPY_YN|CAPPED_BENEFIT_YN
        S2000|001|222222|3|1|1|30|Y|Y|N
        """,
    )
    indication_coverage = _write(
        staging_dir / "indication_coverage.txt",
        """
        CONTRACT_ID|PLAN_ID|RXCUI|DISEASE
        """,
    )
    pharmacy_part = """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|PHARMACY_NUMBER|PHARMACY_ZIPCODE|PREFERRED_STATUS_RETAIL|PREFERRED_STATUS_MAIL|PHARMACY_RETAIL|PHARMACY_MAIL|IN_AREA_FLAG|FLOOR_PRICE|BRAND_DISPENSING_FEE_30|BRAND_DISPENSING_FEE_60|BRAND_DISPENSING_FEE_90|GENERIC_DISPENSING_FEE_30|GENERIC_DISPENSING_FEE_60|GENERIC_DISPENSING_FEE_90
        H1000|001|000|100000000001|43001|Y|N|Y|N|1|0|1|1|1|0.5|0.5|0.5
        H1000|001|000|100000000002|43001|N|Y|N|Y|1|0|0.8|0.8|0.8|0.4|0.4|0.4
        S2000|001|000|200000000001|43002|N|Y|N|Y|1|0|0.6|0.6|0.6|0.3|0.3|0.3
        H1000|001|000|10
    """
    pharmacy_header = pharmacy_part.strip().splitlines()[0]
    pharmacy_parts = [
        _write(staging_dir / f"pharmacy_network_part_{idx}.txt", pharmacy_part if idx == 1 else pharmacy_header)
        for idx in range(1, 7)
    ]
    insulin_reference = _write(
        refs_dir / "insulin_ref.csv",
        """
        ndc,source,source_year,rxcui,is_insulin,ref_ts
        00000000002,test,2025,222222,1,2026-01-01
        """,
    )
    us_zipcode_geo = _write(
        refs_dir / "us_zipcode_geo.csv",
        """
        zip_code,city,state,county,lat,lng,population,density
        43001,AlphaTown,OH,Alpha County,40.0,-82.0,1000,500
        43002,BetaTown,OH,Alpha County,40.1,-82.1,800,300
        """,
    )
    pde_sample = _write(
        refs_dir / "pde.csv",
        """
        PDE_ID|BENE_ID|SRVC_DT|PD_DT|PRSCRBR_ID_QLFYR_CD|PRSCRBR_ID|RX_SRVC_RFRNC_NUM|PROD_SRVC_ID|PLAN_CNTRCT_REC_ID|PLAN_PBP_REC_NUM|CMPND_CD|DAW_PROD_SLCTN_CD|QTY_DSPNSD_NUM|DAYS_SUPLY_NUM|FILL_NUM|DSPNSNG_STUS_CD|DRUG_CVRG_STUS_CD|ADJSTMT_DLTN_CD|NSTD_FRMT_CD|PRCNG_EXCPTN_CD|CTSTRPHC_CVRG_CD|GDC_BLW_OOPT_AMT|GDC_ABV_OOPT_AMT|PTNT_PAY_AMT|OTHR_TROOP_AMT|LICS_AMT|PLRO_AMT|CVRD_D_PLAN_PD_AMT|NCVRD_PLAN_PD_AMT|TOT_RX_CST_AMT|RX_ORGN_CD|RPTD_GAP_DSCNT_NUM|BRND_GNRC_CD|PHRMCY_SRVC_TYPE_CD|PTNT_RSDNC_CD|SUBMSN_CLR_CD
        1|1|01-Jan-2025|01-Jan-2025|01|1|1|00000000001|Z|001|0|1|30|30|1||| |||||0|0|0|0|0|0|0|0|0|0|0|G|01|01|
        2|1|01-Jan-2025|01-Jan-2025|01|1|2|00000000002|Z|001|0|1|10|30|1||| |||||0|0|0|0|0|0|0|0|0|0|0|B|01|01|
        """,
    )
    rxcui_file = _write(
        rxcui_dir / "rxcui_properties_p1.csv",
        """
        rxcui,name,synonym,tty,language,suppress,umlscui
        111111,albuterol 0.21 MG/ML Inhalation Solution,albuterol,SCD,ENG,N,
        222222,insulin glargine 100 UNT/ML Injectable Solution,insulin glargine,SCD,ENG,N,
        """,
    )

    config = PipelineConfig(project_root=root)
    sources = SourcePaths(
        cms_files={
            "plan_information": plan_information,
            "basic_formulary": basic_formulary,
            "beneficiary_cost": beneficiary_cost,
            "insulin_beneficiary_cost": insulin_beneficiary_cost,
            "pricing": pricing,
            "geographic_locator": geographic_locator,
            "excluded_drugs": excluded_drugs,
            "indication_coverage": indication_coverage,
        },
        pharmacy_network_parts=pharmacy_parts,
        reference_files={
            "insulin_reference": insulin_reference,
            "us_zipcode_geo": us_zipcode_geo,
            "pde_sample": pde_sample,
        },
        rxcui_files=[rxcui_file],
    )

    db_path = build_database(config, sources=sources, rebuild=True)
    assert db_path.exists()

    conn = duckdb.connect(str(db_path), read_only=True)
    assert conn.execute("SELECT count(*) FROM gold.plan_summary").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM gold.plan_summary WHERE contract_year = 2025").fetchone()[0] == 2
    assert conn.execute("SELECT count(*) FROM gold.ui_plan_drug_serving WHERE contract_year = 2025").fetchone()[0] == 4
    formulary_summary = conn.execute(
        """
        SELECT
            plan_key,
            formulary_breadth_pct,
            generic_tier_pct,
            pa_rate,
            st_rate,
            ql_rate,
            excluded_rate,
            insulin_coverage_pct,
            restrictiveness_class
        FROM gold.plan_formulary_summary
        ORDER BY plan_key
        """
    ).fetch_df()
    assert len(formulary_summary) == 2
    assert formulary_summary["formulary_breadth_pct"].round(4).tolist() == [1.0, 1.0]
    assert formulary_summary["generic_tier_pct"].round(2).tolist() == [0.5, 0.5]
    assert formulary_summary["pa_rate"].round(2).tolist() == [0.5, 0.5]
    assert formulary_summary["st_rate"].round(2).tolist() == [0.0, 0.5]
    assert formulary_summary["excluded_rate"].round(2).tolist() == [0.0, 0.5]
    assert formulary_summary["insulin_coverage_pct"].round(2).tolist() == [0.5, 0.5]
    assert formulary_summary["restrictiveness_class"].tolist() == [2, 2]
    assert conn.execute("SELECT count(*) FROM gold.plan_service_area WHERE zip_code = '43001'").fetchone()[0] == 2
    conn.close()

    beneficiary = BeneficiaryInput(zipcode="43001", top_n=2)
    medications = [
        MedicationInput(drug_name="albuterol 0.21 MG/ML Inhalation Solution", tier_family="generic", day_supply=30),
        MedicationInput(drug_name="insulin glargine", tier_family="brand", day_supply=30),
    ]
    recommendations = recommend_plans(beneficiary, medications, config=config)

    assert len(recommendations) == 2
    assert recommendations[0].plan_name == "Plan A"
    assert recommendations[0].coverage_status == "full"
    assert recommendations[1].coverage_status == "partial"
    assert recommendations[0].rules_score > recommendations[1].rules_score
    assert recommendations[0].fit_score >= recommendations[1].fit_score
    assert recommendations[0].fit_label
    assert recommendations[0].fit_summary
    assert recommendations[0].monthly_cost_estimate == round(recommendations[0].annual_total_cost / 12, 2)
    assert recommendations[0].feature_version == "research_v4"
    assert recommendations[0].contract_year == 2025
    assert recommendations[0].benefit_design == "2025_redesign"
    assert recommendations[0].priced_drug_count == 2
    assert recommendations[0].channel_switch_count == 0
    assert recommendations[0].simulation_policy == "cost_realism_v1"
    assert recommendations[1].priced_drug_count == 1
    assert recommendations[0].resolved_medications[0].match_source == "exact_name"
    assert recommendations[0].drug_breakdowns[0].coverage_status == "covered"
    assert recommendations[0].drug_breakdowns[0].medication_id
    assert recommendations[0].drug_breakdowns[0].pricing_status == "priced"
    assert recommendations[0].drug_breakdowns[0].fill_traces
    assert recommendations[0].drug_breakdowns[0].fill_traces[0].coverage_phase
    assert recommendations[0].drug_breakdowns[0].fill_traces[0].sequence_index >= 1
    assert recommendations[0].drug_breakdowns[1].fill_traces[0].sequence_index < recommendations[0].drug_breakdowns[0].fill_traces[0].sequence_index
    assert recommendations[0].drug_breakdowns[0].fill_traces[0].benefit_design == "2025_redesign"
    assert recommendations[0].drug_breakdowns[0].coverage_gap_flag is False
    assert recommendations[1].drug_breakdowns[1].coverage_status == "excluded"
    assert recommendations[1].explanation_groups.coverage_issues

    reversed_recommendations = recommend_plans(beneficiary, list(reversed(medications)), config=config)
    assert [item.plan_key for item in reversed_recommendations] == [item.plan_key for item in recommendations]
    assert [item.annual_total_cost for item in reversed_recommendations] == [item.annual_total_cost for item in recommendations]
    assert [item.priced_drug_count for item in reversed_recommendations] == [item.priced_drug_count for item in recommendations]

    duplicate_medications = [
        MedicationInput(drug_name="insulin glargine", tier_family="brand", day_supply=30),
        MedicationInput(
            drug_name="insulin glargine",
            tier_family="brand",
            day_supply=30,
            quantity_override=20,
            fills_per_year_override=2,
        ),
    ]
    duplicate_recommendations = recommend_plans(beneficiary, duplicate_medications, config=config)
    assert len(duplicate_recommendations[0].drug_breakdowns) == 2
    assert len({item.medication_id for item in duplicate_recommendations[0].drug_breakdowns}) == 2
    assert duplicate_recommendations[0].drug_breakdowns[0].annual_oop != duplicate_recommendations[0].drug_breakdowns[1].annual_oop
    assert round(
        sum(float(item.annual_oop or 0.0) for item in duplicate_recommendations[0].drug_breakdowns),
        2,
    ) == duplicate_recommendations[0].annual_drug_oop

    hybrid_fallback = recommend_plans(beneficiary, medications, config=config, ranking_mode="hybrid")
    assert all(item.ranking_source == "rules_only" for item in hybrid_fallback)
    assert all(item.model_score is None for item in hybrid_fallback)

    generator = _load_generator_module()
    write_conn = duckdb.connect(str(db_path))
    rxcui_ref = generator.load_rxcui_reference(config)
    rxcui_name_map, rxcui_synonym_map, rxcui_tty_map = generator.build_rxcui_maps(rxcui_ref)
    formulary_pool = generator.load_formulary_drug_pool(write_conn, max_drugs=10)
    assert {"ndc", "formulary_coverage", "typical_unit_cost"}.issubset(formulary_pool.columns)
    synthetic_bene = generator.create_synthetic_beneficiaries(10, 42)
    synthetic_bene = generator.assign_geography(synthetic_bene, generator.load_zip_pool(write_conn), 42)
    synthetic_rx = generator.generate_prescriptions(
        synthetic_bene,
        formulary_pool,
        seed=42,
        rxcui_name_map=rxcui_name_map,
        rxcui_synonym_map=rxcui_synonym_map,
        rxcui_tty_map=rxcui_tty_map,
    )
    assert not synthetic_rx.empty
    aligned_bene = generator.align_beneficiary_summary(synthetic_bene, synthetic_rx)
    generator.save_to_database(write_conn, aligned_bene, synthetic_rx)
    assert write_conn.execute("SELECT count(*) FROM synthetic.syn_beneficiary").fetchone()[0] == len(aligned_bene)
    assert (
        write_conn.execute("SELECT count(*) FROM synthetic.syn_beneficiary_prescriptions").fetchone()[0]
        == len(synthetic_rx)
    )
    write_conn.close()

    dataset_path = build_training_dataset(config=config)
    assert dataset_path.exists()
    assert config.training_dataset_metadata_path.exists()
    dataset_frame = pd.read_csv(dataset_path)
    assert {"scenario_id", "plan_key", "weak_label_score", "heuristic_score"}.issubset(dataset_frame.columns)
    assert {"feature_version", "negotiated_price_total", "lis_adjusted_oop_total", "contract_year", "benefit_design"}.issubset(dataset_frame.columns)
    assert len(dataset_frame) > 0

    linear_artifact_path = train_hybrid_reranker(
        config=config,
        dataset_path=dataset_path,
        model_type="linear",
    )
    assert linear_artifact_path.exists()
    artifact_path = train_hybrid_reranker(config=config, dataset_path=dataset_path, model_type="tree")
    assert artifact_path.exists()
    artifact = load_hybrid_reranker(artifact_path)
    assert artifact.metadata["training_rows"] == len(dataset_frame)
    assert artifact.model_type == "tree"
    assert artifact.dataset_schema_version

    evaluation = evaluate_hybrid_reranker(config=config, dataset_path=dataset_path, artifact_path=artifact_path)
    assert "systems" in evaluation
    assert "linear_reranker" in evaluation["systems"]
    assert "tree_reranker" in evaluation["systems"]
    assert "scenario_bundle_metrics" in evaluation
    assert "acceptance" in evaluation
    assert evaluation["evaluation_mode"] == "held_out_by_scenario"
    assert evaluation["train_rows"] + evaluation["test_rows"] == len(dataset_frame)
    assert evaluation["train_scenario_count"] > 0
    assert evaluation["test_scenario_count"] > 0
    assert set(evaluation["train_scenarios"]).isdisjoint(evaluation["test_scenarios"])

    hybrid_recommendations = recommend_plans(beneficiary, medications, config=config, ranking_mode="hybrid")
    assert len(hybrid_recommendations) == 2
    assert all(item.ranking_source == "hybrid_reranker" for item in hybrid_recommendations)
    assert all(item.model_score is not None for item in hybrid_recommendations)
    assert all(item.feature_version == artifact.feature_version for item in hybrid_recommendations)

    status = health_check(config=config)
    assert status["ok"] is True


def test_demo_build_profile_scopes_service_area(tmp_path):
    root = tmp_path / "repo"
    data_dir = root / "data"
    staging_dir = data_dir / "staging" / "2025-Q3" / "raw"
    refs_dir = data_dir / "references_data"
    rxcui_dir = data_dir / "rxcui_info"

    _write(
        staging_dir / "plan_information.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|CONTRACT_NAME|PLAN_NAME|FORMULARY_ID|PREMIUM|DEDUCTIBLE|MA_REGION_CODE|PDP_REGION_CODE|STATE|COUNTY_CODE|SNP|PLAN_SUPPRESSED_YN
        H1000|001|000|Org A|Plan A|FORM1|30.00|100| | |OH|39001|0|N
        H1000|002|000|Org A|Plan B|FORM1|40.00|0| | |OH|39003|0|N
        """,
    )
    _write(
        staging_dir / "basic_formulary.txt",
        """
        FORMULARY_ID|FORMULARY_VERSION|CONTRACT_YEAR|RXCUI|NDC|TIER_LEVEL_VALUE|QUANTITY_LIMIT_YN|QUANTITY_LIMIT_AMOUNT|QUANTITY_LIMIT_DAYS|PRIOR_AUTHORIZATION_YN|STEP_THERAPY_YN
        FORM1|1|2025|111111|00000000001|1|N|||N|N
        """,
    )
    _write(
        staging_dir / "beneficiary_cost.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|COVERAGE_LEVEL|TIER|DAYS_SUPPLY|COST_TYPE_PREF|COST_AMT_PREF|COST_MIN_AMT_PREF|COST_MAX_AMT_PREF|COST_TYPE_NONPREF|COST_AMT_NONPREF|COST_MIN_AMT_NONPREF|COST_MAX_AMT_NONPREF|COST_TYPE_MAIL_PREF|COST_AMT_MAIL_PREF|COST_MIN_AMT_MAIL_PREF|COST_MAX_AMT_MAIL_PREF|COST_TYPE_MAIL_NONPREF|COST_AMT_MAIL_NONPREF|COST_MIN_AMT_MAIL_NONPREF|COST_MAX_AMT_MAIL_NONPREF|TIER_SPECIALTY_YN|DED_APPLIES_YN
        H1000|001|000|1|1|1|1|2|0|999|1|4|0|999|1|2|0|999|1|4|0|999|N|N
        H1000|002|000|1|1|1|1|3|0|999|1|4|0|999|1|2|0|999|1|4|0|999|N|N
        """,
    )
    _write(
        staging_dir / "insulin_beneficiary_cost.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|TIER|DAYS_SUPPLY|copay_amt_pref_insln|copay_amt_nonpref_insln|copay_amt_mail_pref_insln|copay_amt_mail_nonpref_insln
        """,
    )
    _write(
        staging_dir / "pricing.txt",
        """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|NDC|DAYS_SUPPLY|UNIT_COST
        H1000|001|000|00000000001|30|1.00
        H1000|002|000|00000000001|30|1.10
        """,
    )
    _write(
        staging_dir / "geographic_locator.txt",
        """
        COUNTY_CODE|STATENAME|COUNTY|MA_REGION_CODE|MA_REGION|PDP_REGION_CODE|PDP_REGION
        39001|Ohio|Alpha|10|OH MA|5|OH PDP
        39003|Ohio|Beta|10|OH MA|5|OH PDP
        """,
    )
    _write(
        staging_dir / "excluded_drugs.txt",
        """
        CONTRACT_ID|PLAN_ID|RXCUI|TIER|QUANTITY_LIMIT_YN|QUANTITY_LIMIT_AMOUNT|QUANTITY_LIMIT_DAYS|PRIOR_AUTH_YN|STEP_THERAPY_YN|CAPPED_BENEFIT_YN
        """,
    )
    _write(
        staging_dir / "indication_coverage.txt",
        """
        CONTRACT_ID|PLAN_ID|RXCUI|DISEASE
        """,
    )
    pharmacy_part = """
        CONTRACT_ID|PLAN_ID|SEGMENT_ID|PHARMACY_NUMBER|PHARMACY_ZIPCODE|PREFERRED_STATUS_RETAIL|PREFERRED_STATUS_MAIL|PHARMACY_RETAIL|PHARMACY_MAIL|IN_AREA_FLAG|FLOOR_PRICE|BRAND_DISPENSING_FEE_30|BRAND_DISPENSING_FEE_60|BRAND_DISPENSING_FEE_90|GENERIC_DISPENSING_FEE_30|GENERIC_DISPENSING_FEE_60|GENERIC_DISPENSING_FEE_90
        H1000|001|000|100000000001|43001|Y|N|Y|N|1|0|1|1|1|0.5|0.5|0.5
        H1000|002|000|100000000002|99999|Y|N|Y|N|1|0|1|1|1|0.5|0.5|0.5
    """
    pharmacy_header = pharmacy_part.strip().splitlines()[0]
    pharmacy_parts = [
        _write(staging_dir / f"pharmacy_network_part_{idx}.txt", pharmacy_part if idx == 1 else pharmacy_header)
        for idx in range(1, 7)
    ]
    _write(
        refs_dir / "insulin_ref.csv",
        """
        ndc,source,source_year,rxcui,is_insulin,ref_ts
        """,
    )
    _write(
        refs_dir / "us_zipcode_geo.csv",
        """
        zip_code,city,state,county,lat,lng,population,density
        43001,AlphaTown,OH,Alpha County,40.0,-82.0,1000,500
        99999,BetaTown,OH,Beta County,41.0,-83.0,1000,500
        """,
    )
    _write(
        refs_dir / "pde.csv",
        """
        PDE_ID|BENE_ID|SRVC_DT|PD_DT|PRSCRBR_ID_QLFYR_CD|PRSCRBR_ID|RX_SRVC_RFRNC_NUM|PROD_SRVC_ID|PLAN_CNTRCT_REC_ID|PLAN_PBP_REC_NUM|CMPND_CD|DAW_PROD_SLCTN_CD|QTY_DSPNSD_NUM|DAYS_SUPLY_NUM|FILL_NUM|DSPNSNG_STUS_CD|DRUG_CVRG_STUS_CD|ADJSTMT_DLTN_CD|NSTD_FRMT_CD|PRCNG_EXCPTN_CD|CTSTRPHC_CVRG_CD|GDC_BLW_OOPT_AMT|GDC_ABV_OOPT_AMT|PTNT_PAY_AMT|OTHR_TROOP_AMT|LICS_AMT|PLRO_AMT|CVRD_D_PLAN_PD_AMT|NCVRD_PLAN_PD_AMT|TOT_RX_CST_AMT|RX_ORGN_CD|RPTD_GAP_DSCNT_NUM|BRND_GNRC_CD|PHRMCY_SRVC_TYPE_CD|PTNT_RSDNC_CD|SUBMSN_CLR_CD
        1|1|01-Jan-2025|01-Jan-2025|01|1|1|00000000001|Z|001|0|1|30|30|1||| |||||0|0|0|0|0|0|0|0|0|0|0|G|01|01|
        """,
    )
    rxcui_file = _write(
        rxcui_dir / "rxcui_properties_p1.csv",
        """
        rxcui,name,synonym,tty,language,suppress,umlscui
        111111,albuterol 0.21 MG/ML Inhalation Solution,albuterol,SCD,ENG,N,
        """,
    )

    config = PipelineConfig(project_root=root, build_profile="demo", demo_zipcodes=("43001",))
    sources = SourcePaths(
        cms_files={
            "plan_information": staging_dir / "plan_information.txt",
            "basic_formulary": staging_dir / "basic_formulary.txt",
            "beneficiary_cost": staging_dir / "beneficiary_cost.txt",
            "insulin_beneficiary_cost": staging_dir / "insulin_beneficiary_cost.txt",
            "pricing": staging_dir / "pricing.txt",
            "geographic_locator": staging_dir / "geographic_locator.txt",
            "excluded_drugs": staging_dir / "excluded_drugs.txt",
            "indication_coverage": staging_dir / "indication_coverage.txt",
        },
        pharmacy_network_parts=pharmacy_parts,
        reference_files={
            "insulin_reference": refs_dir / "insulin_ref.csv",
            "us_zipcode_geo": refs_dir / "us_zipcode_geo.csv",
            "pde_sample": refs_dir / "pde.csv",
        },
        rxcui_files=[rxcui_file],
    )

    db_path = build_database(config, sources=sources, rebuild=True)
    conn = duckdb.connect(str(db_path), read_only=True)
    assert conn.execute("SELECT count(*) FROM gold.plan_formulary_summary").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM gold.plan_service_area").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM gold.plan_summary").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM gold.ui_plan_comparison_base").fetchone()[0] == 1
    conn.close()

