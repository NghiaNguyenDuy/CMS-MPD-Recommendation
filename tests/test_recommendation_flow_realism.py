from __future__ import annotations

import duckdb

from cms_mpd.recommend import (
    DrugFillTrace,
    FillCostResult,
    MedicationMatch,
    PlanDrugBreakdown,
    PlanExplanationDetailGroups,
    PlanExplanationGroups,
    PlanFitMetrics,
    PlanRecommendation,
    _build_scheduled_fill_events,
    _candidate_plan_query,
    _rules_ranking_sort_key,
    _scheduled_fill_sort_key,
    _select_best_channel_result,
)

from cms_mpd.modeling import _monthly_cost_variance_features


def _channel_summary() -> dict[str, float | bool]:
    return {
        "has_pref_retail": True,
        "has_nonpref_retail": True,
        "has_pref_mail": True,
        "has_nonpref_mail": False,
        "pref_retail_generic_fee_30": 0.0,
        "nonpref_retail_generic_fee_30": 0.0,
        "pref_mail_generic_fee_30": 0.0,
        "pref_retail_floor": 0.0,
        "nonpref_retail_floor": 0.0,
        "pref_mail_floor": 0.0,
    }


def _basis(*, deductible_applies: bool, unit_cost: float) -> dict[str, float | bool | int | str]:
    return {
        "tier_family": "generic",
        "days_supply": 30,
        "deductible_applies": deductible_applies,
        "unit_cost": unit_cost,
    }


def _medication(medication_id: str) -> dict[str, float | int | str]:
    return {
        "medication_id": medication_id,
        "quantity": 30.0,
        "fills_per_year": 1,
    }


def _fill_result(total_oop: float) -> FillCostResult:
    return FillCostResult(
        total_oop=total_oop,
        base_oop=total_oop,
        lis_adjusted_oop=total_oop,
        deductible_exposure=0.0,
        initial_coverage_oop=total_oop,
        coverage_gap_oop=0.0,
        catastrophic_oop=0.0,
        negotiated_price=40.0,
        coverage_phase="initial_coverage",
        pricing_status="priced",
        deductible_before=0.0,
        deductible_after=0.0,
        oop_before=0.0,
        oop_after=total_oop,
        oop_cap_applied=False,
    )


def _drug_breakdown(index: int, *, priced: bool) -> PlanDrugBreakdown:
    return PlanDrugBreakdown(
        medication_id=f"med_{index}",
        plan_key="P",
        requested_drug_name=f"Drug {index}",
        drug_name=f"Drug {index}",
        tier=1,
        requested_day_supply=30,
        selected_channel="pref_retail" if priced else "unavailable",
        per_fill_oop=12.0 if priced else None,
        annual_oop=120.0 if priced else None,
        deductible_exposure=0.0,
        initial_coverage_oop=120.0 if priced else 0.0,
        coverage_gap_oop=0.0,
        catastrophic_oop=0.0,
        lis_adjusted_oop=120.0 if priced else 0.0,
        negotiated_price_total=300.0 if priced else 0.0,
        oop_cap_savings=0.0,
        pa_flag=False,
        st_flag=False,
        ql_flag=False,
        insulin_flag=False,
        coverage_gap_flag=False,
        coverage_status="covered" if priced else "channel_unavailable",
        pricing_status="priced" if priced else "channel_unavailable",
        coverage_phases=["initial_coverage"] if priced else [],
        match_source="exact_name",
        match_confidence="exact",
        explanations=[],
        fill_traces=[],
    )


def _recommendation(
    plan_key: str,
    *,
    coverage_status: str,
    priced_drug_count: int,
    requested_drug_count: int,
) -> PlanRecommendation:
    medication_matches = [
        MedicationMatch(
            medication_id=f"med_{index}",
            requested_value=f"Drug {index}",
            requested_drug_name=f"Drug {index}",
            resolved_drug_name=f"Drug {index}",
            rxcui=f"{index:06d}",
            ndc=f"{index:011d}",
            match_source="exact_name",
            match_confidence="exact",
            normalized_day_supply=30,
            tier_family="generic",
        )
        for index in range(1, requested_drug_count + 1)
    ]
    breakdowns = [
        _drug_breakdown(index, priced=index <= priced_drug_count)
        for index in range(1, requested_drug_count + 1)
    ]
    uncovered_drug_count = requested_drug_count - priced_drug_count
    return PlanRecommendation(
        plan_key=plan_key,
        plan_name=f"Plan {plan_key}",
        annual_drug_oop=120.0,
        estimated_annual_oop=120.0,
        annual_premium=300.0,
        annual_total_cost=420.0,
        monthly_cost_estimate=35.0,
        coverage_status=coverage_status,
        best_channel_mix="pref_retail:1" if priced_drug_count else "no covered fills",
        network_flag="adequate",
        network_access_summary="Preferred retail access appears adequate.",
        insulin_flag=False,
        restriction_summary="no major restrictions flagged",
        explanations=[],
        explanation_groups=PlanExplanationGroups([], [], [], [], [], []),
        explanation_detail_groups=PlanExplanationDetailGroups([], [], [], [], [], []),
        resolved_medications=medication_matches,
        plan_rank=0,
        uncovered_drug_count=uncovered_drug_count,
        restriction_count=0,
        ranking_source="rules_only",
        model_score=None,
        model_confidence_bucket=None,
        rules_score=50.0,
        fit_score=70.0,
        fit_label="good fit",
        fit_summary="Stable fit.",
        fit_metrics=PlanFitMetrics(
            cost_score=70.0,
            premium_score=70.0,
            coverage_score=70.0,
            access_score=70.0,
            stability_score=70.0,
        ),
        key_strengths=[],
        key_watchouts=[],
        mail_order_dependency_count=0,
        channel_diversity_count=1 if priced_drug_count else 0,
        nearest_preferred_distance_miles=1.0,
        service_area_eligible=True,
        comparison_only=False,
        feature_version="research_v4",
        drug_breakdowns=breakdowns,
        contract_year=2025,
        benefit_design="2025_redesign",
        priced_drug_count=priced_drug_count,
        channel_switch_count=0,
        simulation_policy="cost_realism_v1",
    )


def test_fill_scheduling_is_input_order_independent():
    events_one = [
        *_build_scheduled_fill_events(_medication("med_low"), _basis(deductible_applies=True, unit_cost=5.0), _channel_summary(), "auto"),
        *_build_scheduled_fill_events(_medication("med_high"), _basis(deductible_applies=True, unit_cost=15.0), _channel_summary(), "auto"),
    ]
    events_two = [
        *_build_scheduled_fill_events(_medication("med_high"), _basis(deductible_applies=True, unit_cost=15.0), _channel_summary(), "auto"),
        *_build_scheduled_fill_events(_medication("med_low"), _basis(deductible_applies=True, unit_cost=5.0), _channel_summary(), "auto"),
    ]

    ordered_one = [event.medication_id for event in sorted(events_one, key=_scheduled_fill_sort_key)]
    ordered_two = [event.medication_id for event in sorted(events_two, key=_scheduled_fill_sort_key)]

    assert ordered_one == ["med_high", "med_low"]
    assert ordered_two == ordered_one


def test_same_day_sequencing_prioritizes_deductible_applicable_fills():
    events = [
        *_build_scheduled_fill_events(_medication("med_exempt"), _basis(deductible_applies=False, unit_cost=50.0), _channel_summary(), "auto"),
        *_build_scheduled_fill_events(_medication("med_deductible"), _basis(deductible_applies=True, unit_cost=1.0), _channel_summary(), "auto"),
    ]

    ordered = sorted(events, key=_scheduled_fill_sort_key)

    assert [event.medication_id for event in ordered] == ["med_deductible", "med_exempt"]


def test_channel_selection_keeps_previous_channel_within_near_tie():
    channel, result = _select_best_channel_result(
        [
            ("pref_retail", _fill_result(10.0)),
            ("pref_mail", _fill_result(10.8)),
            ("nonpref_retail", _fill_result(10.5)),
        ],
        previous_channel="pref_mail",
        pharmacy_preference="retail",
    )

    assert channel == "pref_mail"
    assert result is not None
    assert result.total_oop == 10.8


def test_rules_sort_key_prefers_priceable_plan_over_fallback():
    needs_verification = _recommendation(
        "P1",
        coverage_status="partial",
        priced_drug_count=1,
        requested_drug_count=2,
    )
    fallback_only = _recommendation(
        "P2",
        coverage_status="partial",
        priced_drug_count=0,
        requested_drug_count=2,
    )

    ordered = sorted([fallback_only, needs_verification], key=_rules_ranking_sort_key)

    assert [item.plan_key for item in ordered] == ["P1", "P2"]


def test_candidate_plan_query_falls_back_when_contract_year_column_is_missing():
    conn = duckdb.connect()
    conn.execute("CREATE SCHEMA gold")
    conn.execute("CREATE TABLE gold.plan_service_area(plan_key VARCHAR, zip_code VARCHAR)")
    conn.execute(
        """
        CREATE TABLE gold.plan_summary(
            plan_key VARCHAR,
            plan_name VARCHAR,
            annual_premium DOUBLE,
            deductible DOUBLE,
            contract_id VARCHAR
        )
        """
    )
    conn.execute("CREATE TABLE gold.plan_network_summary(plan_key VARCHAR, network_flag VARCHAR)")
    conn.execute("INSERT INTO gold.plan_service_area VALUES ('P1', '43001')")
    conn.execute("INSERT INTO gold.plan_summary VALUES ('P1', 'Legacy Plan', 240.0, 100.0, 'H1000')")
    conn.execute("INSERT INTO gold.plan_network_summary VALUES ('P1', 'adequate')")

    frame = conn.execute(_candidate_plan_query(conn), ['43001']).fetch_df()

    assert list(frame.columns) == [
        'plan_key',
        'plan_name',
        'contract_year',
        'annual_premium',
        'deductible',
        'network_flag',
    ]
    assert frame.iloc[0]['plan_name'] == 'Legacy Plan'
    assert frame['contract_year'].isna().all()
    conn.close()



def test_monthly_variance_features_capture_priceability_and_timing():
    recommendation = _recommendation(
        "P3",
        coverage_status="partial",
        priced_drug_count=1,
        requested_drug_count=2,
    )
    recommendation.annual_premium = 120.0
    recommendation.drug_breakdowns[0].fill_traces = [
        DrugFillTrace(
            fill_number=1,
            day_offset=0,
            sequence_index=1,
            selected_channel="pref_retail",
            coverage_phase="initial_coverage",
            pricing_status="priced",
            negotiated_price=100.0,
            deductible_before=0.0,
            deductible_applied=0.0,
            deductible_after=0.0,
            base_oop=40.0,
            initial_coverage_oop=40.0,
            lis_adjusted_oop=40.0,
            final_oop=40.0,
            oop_before=0.0,
            oop_after=40.0,
            oop_cap_applied=False,
        ),
        DrugFillTrace(
            fill_number=2,
            day_offset=45,
            sequence_index=2,
            selected_channel="pref_retail",
            coverage_phase="initial_coverage",
            pricing_status="priced",
            negotiated_price=100.0,
            deductible_before=0.0,
            deductible_applied=0.0,
            deductible_after=0.0,
            base_oop=10.0,
            initial_coverage_oop=10.0,
            lis_adjusted_oop=10.0,
            final_oop=10.0,
            oop_before=40.0,
            oop_after=50.0,
            oop_cap_applied=False,
        ),
    ]

    features = _monthly_cost_variance_features(recommendation)

    assert features["priced_drug_share"] == 0.5
    assert features["monthly_drug_oop_variance"] > 0.0
    assert features["monthly_total_variance"] == features["monthly_drug_oop_variance"]
