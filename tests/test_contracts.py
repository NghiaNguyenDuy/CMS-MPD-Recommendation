from __future__ import annotations

import pandas as pd

from cms_mpd.app_support import (
    append_medication_row,
    build_medication_row_from_catalog,
    build_counselor_note,
    build_side_by_side_frame,
    format_drug_catalog_option,
    parse_medication_frame,
    search_drug_catalog,
    summarize_evidence_gaps,
)
from cms_mpd.config import PipelineConfig
from cms_mpd.decision_support import (
    MedicationListItem,
    PreferenceWeights,
    ProfileInput,
    as_public_types,
    create_run_audit,
    recommendations_to_dataframe,
    summarize_feature_coverage,
)
from cms_mpd.recommend import (
    DrugFillTrace,
    ExplanationItem,
    MedicationMatch,
    PlanDrugBreakdown,
    PlanExplanationDetailGroups,
    PlanExplanationGroups,
    PlanFitMetrics,
    PlanRecommendation,
)


def _sample_recommendation(
    *,
    plan_key: str,
    plan_name: str,
    annual_total_cost: float,
    annual_premium: float,
    annual_drug_oop: float,
    coverage_status: str = "full",
    uncovered_drug_count: int = 0,
    restriction_count: int = 0,
    network_flag: str = "adequate",
    model_score: float | None = 0.91,
    nearest_distance_miles: float | None = 3.5,
    comparison_only: bool = False,
) -> PlanRecommendation:
    fill_trace = DrugFillTrace(
        fill_number=1,
        day_offset=0,
        selected_channel="pref_retail",
        coverage_phase="initial_coverage",
        pricing_status="priced",
        negotiated_price=25.0,
        deductible_before=100.0,
        deductible_applied=0.0,
        deductible_after=100.0,
        base_oop=10.0,
        initial_coverage_oop=10.0,
        lis_adjusted_oop=10.0,
        final_oop=10.0,
        oop_before=0.0,
        oop_after=10.0,
        oop_cap_applied=False,
    )
    explanation_groups = PlanExplanationGroups(
        coverage_issues=[] if uncovered_drug_count == 0 else ["One entered drug is not fully covered."],
        utilization_management_issues=["Insulin glargine requires prior authorization."]
        if restriction_count
        else [],
        insulin_considerations=["Insulin cost-sharing should be reviewed."]
        if restriction_count
        else [],
        pharmacy_access_issues=["Preferred retail access is limited."]
        if network_flag != "adequate"
        else [],
        deductible_issues=["Deductible applies before standard cost sharing."]
        if annual_premium > 0
        else [],
        cost_logic_issues=["Hybrid reranker score not available."]
        if model_score is None
        else [],
    )
    explanation_detail_groups = PlanExplanationDetailGroups(
        coverage_issues=[
            ExplanationItem(
                code="coverage_gap",
                message="One entered drug is not fully covered.",
                related_drug="insulin glargine",
                severity="warning",
            )
        ]
        if uncovered_drug_count
        else [],
        utilization_management_issues=[
            ExplanationItem(
                code="prior_authorization",
                message="Insulin glargine requires prior authorization.",
                related_drug="insulin glargine",
                severity="warning",
            )
        ]
        if restriction_count
        else [],
        insulin_considerations=[
            ExplanationItem(
                code="insulin_review",
                message="Insulin cost-sharing should be reviewed.",
                related_drug="insulin glargine",
            )
        ]
        if restriction_count
        else [],
        pharmacy_access_issues=[
            ExplanationItem(
                code="network_access",
                message="Preferred retail access is limited.",
                severity="warning",
            )
        ]
        if network_flag != "adequate"
        else [],
        deductible_issues=[
            ExplanationItem(
                code="deductible",
                message="Deductible applies before standard cost sharing.",
            )
        ]
        if annual_premium > 0
        else [],
        cost_logic_issues=[
            ExplanationItem(
                code="model_gap",
                message="Hybrid reranker score not available.",
            )
        ]
        if model_score is None
        else [],
    )
    medication_match = MedicationMatch(
        medication_id=f"{plan_key}_rx_1",
        requested_value="insulin glargine",
        requested_drug_name="insulin glargine",
        resolved_drug_name="insulin glargine",
        rxcui="222222",
        ndc="00000000002",
        match_source="exact_name",
        match_confidence="exact",
        normalized_day_supply=30,
        tier_family="brand",
    )
    drug_breakdown = PlanDrugBreakdown(
        medication_id=f"{plan_key}_rx_1",
        plan_key=plan_key,
        requested_drug_name="insulin glargine",
        drug_name="insulin glargine",
        tier=3,
        requested_day_supply=30,
        selected_channel="pref_retail",
        per_fill_oop=10.0,
        annual_oop=annual_drug_oop,
        deductible_exposure=0.0,
        initial_coverage_oop=annual_drug_oop,
        coverage_gap_oop=0.0,
        catastrophic_oop=0.0,
        lis_adjusted_oop=annual_drug_oop,
        negotiated_price_total=120.0,
        oop_cap_savings=0.0,
        pa_flag=restriction_count > 0,
        st_flag=False,
        ql_flag=False,
        insulin_flag=True,
        coverage_gap_flag=False,
        coverage_status="covered" if uncovered_drug_count == 0 else "excluded",
        pricing_status="priced",
        coverage_phases=["initial_coverage"],
        match_source="exact_name",
        match_confidence="exact",
        explanations=["Insulin glargine priced successfully."],
        fill_traces=[fill_trace],
    )
    return PlanRecommendation(
        plan_key=plan_key,
        plan_name=plan_name,
        annual_drug_oop=annual_drug_oop,
        estimated_annual_oop=annual_drug_oop,
        annual_premium=annual_premium,
        annual_total_cost=annual_total_cost,
        monthly_cost_estimate=round(annual_total_cost / 12.0, 2),
        coverage_status=coverage_status,
        best_channel_mix="pref_retail:1",
        network_flag=network_flag,
        network_access_summary="Preferred retail access appears adequate."
        if network_flag == "adequate"
        else "Preferred retail access is limited.",
        insulin_flag=True,
        restriction_summary="1 utilization management rule" if restriction_count else "no major restrictions",
        explanations=["Insulin cost-sharing should be reviewed."],
        explanation_groups=explanation_groups,
        explanation_detail_groups=explanation_detail_groups,
        resolved_medications=[medication_match],
        plan_rank=1,
        uncovered_drug_count=uncovered_drug_count,
        restriction_count=restriction_count,
        ranking_source="hybrid_reranker" if model_score is not None else "rules_only",
        model_score=model_score,
        model_confidence_bucket="high" if model_score is not None else None,
        rules_score=92.5 if uncovered_drug_count == 0 else 65.0,
        fit_score=88.0 if uncovered_drug_count == 0 else 61.0,
        fit_label="strong fit" if uncovered_drug_count == 0 else "mixed fit",
        fit_summary="Strong overall fit for the entered medication list."
        if uncovered_drug_count == 0
        else "Coverage tradeoffs need review.",
        fit_metrics=PlanFitMetrics(
            cost_score=85.0,
            premium_score=74.0,
            coverage_score=100.0 if uncovered_drug_count == 0 else 40.0,
            access_score=91.0 if network_flag == "adequate" else 58.0,
            stability_score=87.0,
        ),
        key_strengths=["Estimated annual total cost is competitive."],
        key_watchouts=["Review insulin prior authorization."]
        if restriction_count
        else ["Verify pharmacy preference with the beneficiary."],
        mail_order_dependency_count=0,
        channel_diversity_count=1,
        nearest_preferred_distance_miles=nearest_distance_miles,
        service_area_eligible=not comparison_only,
        comparison_only=comparison_only,
        feature_version="research_v3",
        drug_breakdowns=[drug_breakdown],
        contract_year=2025,
        benefit_design="2025_redesign",
    )


def test_pipeline_config_source_dir_resolution(tmp_path):
    workspace = tmp_path / "workspace"
    project_root = workspace / "CMS-MPD-Recommendation"
    sibling_data_dir = workspace / "Medicare-PartD-Recommendation" / "data"
    sibling_data_dir.mkdir(parents=True)
    (sibling_data_dir / "rxcui_info").mkdir()

    config = PipelineConfig(project_root=project_root, data_dir=project_root / "data")
    assert config.source_data_dir == sibling_data_dir

    explicit_source = workspace / "custom-source-data"
    explicit_source.mkdir(parents=True)
    explicit = PipelineConfig(
        project_root=project_root,
        data_dir=project_root / "data",
        source_data_dir=explicit_source,
    )
    assert explicit.source_data_dir == explicit_source


def test_parse_medication_frame_validates_rows():
    frame = pd.DataFrame(
        [
            {
                "drug_name": "insulin glargine",
                "rxcui": "",
                "ndc": "",
                "tier_family": "brand",
                "day_supply": 30,
                "quantity_override": "",
                "fills_per_year_override": "",
            },
            {
                "drug_name": "albuterol",
                "rxcui": "",
                "ndc": "",
                "tier_family": "generic",
                "day_supply": 45,
                "quantity_override": "",
                "fills_per_year_override": "",
            },
        ]
    )

    medications, contract_rows, errors = parse_medication_frame(frame)

    assert len(medications) == 1
    assert len(contract_rows) == 1
    assert medications[0].drug_name == "insulin glargine"
    assert any("day_supply must be 30, 60, or 90" in message for message in errors)


def test_drug_catalog_search_and_add_row_helpers():
    catalog = pd.DataFrame(
        [
            {
                "drug_name": "insulin glargine",
                "drug_synonym": "Lantus",
                "rxcui": "222222",
                "ndc": "00000000002",
                "tier_family": "brand",
                "default_day_supply": 30,
                "plan_coverage": 120,
                "is_insulin": True,
            },
            {
                "drug_name": "albuterol sulfate",
                "drug_synonym": "albuterol",
                "rxcui": "111111",
                "ndc": "00000000001",
                "tier_family": "generic",
                "default_day_supply": 90,
                "plan_coverage": 98,
                "is_insulin": False,
            },
        ]
    )

    matches = search_drug_catalog(catalog, "insulin", limit=10)
    assert list(matches["drug_name"]) == ["insulin glargine"]

    option_label = format_drug_catalog_option(matches.iloc[0])
    assert "insulin glargine" in option_label
    assert "30-day default" in option_label

    new_row = build_medication_row_from_catalog(matches.iloc[0], day_supply=60, tier_family="brand")
    assert new_row["drug_name"] == "insulin glargine"
    assert new_row["rxcui"] == "222222"
    assert new_row["day_supply"] == 60

    updated_rows = append_medication_row([], new_row)
    assert len(updated_rows) == 1
    assert updated_rows[0]["ndc"] == "00000000002"


def test_decision_support_exports_and_counselor_note():
    eligible_recommendations = [
        _sample_recommendation(
            plan_key="P1",
            plan_name="Alpha Choice",
            annual_total_cost=1200.0,
            annual_premium=360.0,
            annual_drug_oop=840.0,
            restriction_count=0,
            network_flag="adequate",
            model_score=0.91,
        ),
        _sample_recommendation(
            plan_key="P2",
            plan_name="Beta Saver",
            annual_total_cost=1450.0,
            annual_premium=300.0,
            annual_drug_oop=1150.0,
            coverage_status="partial",
            uncovered_drug_count=1,
            restriction_count=1,
            network_flag="limited_preferred_retail",
            model_score=None,
            nearest_distance_miles=19.0,
        ),
    ]
    comparison_recommendations = [
        _sample_recommendation(
            plan_key="P3",
            plan_name="Gamma Nearby",
            annual_total_cost=1100.0,
            annual_premium=240.0,
            annual_drug_oop=860.0,
            restriction_count=1,
            network_flag="no_preferred_retail",
            model_score=None,
            nearest_distance_miles=None,
            comparison_only=True,
        )
    ]

    eligible_frame = recommendations_to_dataframe(
        eligible_recommendations,
        run_id="run123",
        minimum_coverage_pct=90.0,
    )
    comparison_frame = recommendations_to_dataframe(
        comparison_recommendations,
        run_id="run123",
        comparison_only=True,
        minimum_coverage_pct=90.0,
    )
    combined = pd.DataFrame(
        [*eligible_frame.to_dict("records"), *comparison_frame.to_dict("records")]
    )

    assert "PLAN_NAME" in eligible_frame.columns
    assert eligible_frame.iloc[0]["PLAN_NAME"] == "Alpha Choice"
    assert eligible_frame.iloc[0]["recommendation_tier"] == "Ready to shortlist"
    assert comparison_frame.iloc[0]["eligibility_status"].startswith("Comparison only")
    assert bool(comparison_frame.iloc[0]["comparison_only"]) is True
    assert eligible_frame.iloc[0]["contract_year"] == 2025
    assert eligible_frame.iloc[0]["benefit_design"] == "2025_redesign"

    side_by_side = build_side_by_side_frame(combined, selected_plan_keys=["P1", "P3"])
    assert list(side_by_side.columns) == ["Metric", "Alpha Choice", "Gamma Nearby"]
    assert "Annual total cost" in side_by_side["Metric"].tolist()

    feature_coverage = summarize_feature_coverage(eligible_recommendations, comparison_recommendations)
    assert feature_coverage["candidate_plans"] == 3
    assert feature_coverage["comparison_only_plans"] == 1
    assert feature_coverage["contract_years"] == [2025]
    assert feature_coverage["benefit_designs"] == ["2025_redesign"]

    profile = ProfileInput(
        persona="Counselor",
        zipcode="43004",
        age_band="65-74",
        lis_status="none",
        pharmacy_preference="auto",
        chronic_condition_flags=["diabetes"],
        top_n=5,
    )
    preferences = PreferenceWeights(
        primary_goal="Balanced recommendation",
        minimum_coverage_pct=90.0,
        allow_comparison_plans=True,
        max_comparison_distance_miles=50,
        ranking_mode="rules",
    )
    medications = [
        MedicationListItem(
            drug_name="insulin glargine",
            rxcui="222222",
            ndc="00000000002",
            tier_family="brand",
            day_supply=30,
            quantity_override=None,
            fills_per_year_override=None,
        )
    ]
    input_summary = as_public_types(profile, medications, preferences)
    audit = create_run_audit(
        user_input_summary=input_summary,
        model_version="rules-only",
        data_snapshot="2025-Q3",
        feature_coverage=feature_coverage,
        recommendations=combined,
        run_id="run123",
    )
    note = build_counselor_note(profile, preferences, eligible_frame, comparison_frame)
    gaps = summarize_evidence_gaps(eligible_frame, comparison_frame)

    assert audit.run_id == "run123"
    assert audit.data_snapshot == "2025-Q3"
    assert len(audit.top_k_outputs) == 3
    assert {"PLAN_KEY", "PLAN_NAME", "eligibility_status", "contract_year", "benefit_design"}.issubset(audit.top_k_outputs[0])
    assert "Alpha Choice" in note
    assert "comparison-only" in note
    assert any("Hybrid reranker score not available" in gap for gap in gaps)
