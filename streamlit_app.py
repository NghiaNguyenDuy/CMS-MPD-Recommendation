from __future__ import annotations

from dataclasses import asdict, replace
import json
import sys
import uuid
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st


ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cms_mpd import BeneficiaryInput, PipelineConfig, recommend_plan_bundle, recommend_plans
from cms_mpd.app_support import (
    CHRONIC_FLAG_OPTIONS,
    DEFAULT_MEDICATION_ROWS,
    FOCUS_MAP,
    PERSONA_OPTIONS,
    PRIMARY_GOALS,
    ROLE_MAP,
    append_medication_row,
    build_counselor_note,
    build_medication_row_from_catalog,
    build_monthly_timeline_frame,
    build_side_by_side_frame,
    build_what_if_scenarios,
    build_what_if_summary_frame,
    catalog_available_day_supply_options,
    catalog_tier_family_options,
    coerce_zipcode,
    format_drug_catalog_option,
    haversine_miles,
    parse_medication_frame,
    rank_alternative_matches,
    search_drug_catalog,
    summarize_drug_channel_path,
    summarize_evidence_gaps,
    summarize_what_if_findings,
)
from cms_mpd.decision_support import (
    MedicationListItem,
    PreferenceWeights,
    ProfileInput,
    as_public_types,
    create_run_audit,
    recommendation_bundle_to_dataframes,
    recommend_preference_preset,
    recommendations_to_dataframe,
    serialize_nested_columns,
    summarize_feature_coverage,
)
from cms_mpd.research_eval import (
    dataset_diagnostics_frame,
    ensure_research_artifacts,
    scenario_bundle_frames,
    subgroup_frames,
    systems_summary_frame,
)


st.set_page_config(page_title="CMS MPD Recommendation", layout="wide")

SCENARIO_IMPACT_NOTES = {
    "low_utilizer": "This scenario emphasizes full coverage first, then total annual cost and premium friction.",
    "maintenance_generic": "This scenario emphasizes reliable full coverage for a simpler maintenance regimen and then keeps total cost low.",
    "insulin_chronic": "This scenario emphasizes insulin channel stability, drug OOP, and access before secondary cost tradeoffs.",
    "specialty_high_cost": "This scenario emphasizes utilization-management burden, continuity, and access before secondary cost tradeoffs.",
    "mixed_restriction": "This scenario emphasizes blocker clarity and restriction burden before cost tradeoffs.",
    "access_sensitive": "This scenario emphasizes pharmacy network confidence and distance before secondary cost tradeoffs.",
}


def _inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
          --ink: #12263a;
          --muted: #4a5d73;
          --line: rgba(18, 38, 58, 0.12);
          --teal: #0f766e;
          --amber: #a16207;
          --rose: #be123c;
        }
        .stApp {
          background:
            radial-gradient(circle at top left, rgba(204, 251, 241, 0.55), transparent 26%),
            radial-gradient(circle at top right, rgba(254, 240, 138, 0.42), transparent 24%),
            linear-gradient(180deg, #f8fafc 0%, #eef6ff 100%);
        }
        .hero, .panel, .metric-card {
          background: rgba(255, 255, 255, 0.92);
          border: 1px solid var(--line);
          border-radius: 20px;
          box-shadow: 0 12px 30px rgba(15, 23, 42, 0.07);
        }
        .hero {
          padding: 1.3rem 1.4rem;
          margin-bottom: 1rem;
          background: linear-gradient(135deg, rgba(15,118,110,0.92), rgba(18,38,58,0.96));
          color: white;
        }
        .hero-kicker {
          text-transform: uppercase;
          letter-spacing: 0.12em;
          font-size: 0.78rem;
          color: rgba(255,255,255,0.75);
          margin-bottom: 0.3rem;
        }
        .hero-title {
          font-size: 2rem;
          font-weight: 700;
          margin-bottom: 0.45rem;
        }
        .hero-copy {
          line-height: 1.55;
          color: rgba(255,255,255,0.88);
          max-width: 62rem;
        }
        .panel {
          padding: 0.95rem 1rem;
          margin-bottom: 0.85rem;
        }
        .panel-title {
          text-transform: uppercase;
          letter-spacing: 0.06em;
          font-size: 0.76rem;
          color: var(--teal);
          font-weight: 700;
          margin-bottom: 0.3rem;
        }
        .metric-card {
          padding: 0.8rem 0.9rem;
        }
        .metric-label {
          text-transform: uppercase;
          letter-spacing: 0.06em;
          font-size: 0.72rem;
          color: var(--muted);
        }
        .metric-value {
          color: var(--ink);
          font-size: 1.25rem;
          font-weight: 700;
          margin-top: 0.25rem;
        }
        .chip {
          display: inline-block;
          padding: 0.28rem 0.6rem;
          border-radius: 999px;
          background: rgba(15,118,110,0.09);
          color: var(--teal);
          font-size: 0.78rem;
          font-weight: 700;
          margin-right: 0.35rem;
          margin-bottom: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource
def get_config() -> PipelineConfig:
    return PipelineConfig()


@st.cache_resource
def get_connection(db_path: str) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


@st.cache_data(show_spinner=False)
def get_drug_catalog(db_path: str) -> pd.DataFrame:
    conn = get_connection(db_path)
    return conn.execute(
        """
        WITH coverage AS (
            SELECT
                ndc,
                any_value(rxcui) AS rxcui,
                max(CASE WHEN is_insulin THEN 1 ELSE 0 END) AS is_insulin,
                count(DISTINCT plan_key) AS plan_coverage
            FROM silver.fact_plan_drug_coverage
            WHERE ndc IS NOT NULL
            GROUP BY 1
        ),
        tier_mode AS (
            SELECT
                ndc,
                tier_family
            FROM (
                SELECT
                    ndc,
                    tier_family,
                    count(*) AS tier_count,
                    row_number() OVER (
                        PARTITION BY ndc
                        ORDER BY
                            count(*) DESC,
                            CASE tier_family
                                WHEN 'generic' THEN 1
                                WHEN 'brand' THEN 2
                                ELSE 3
                            END
                    ) AS rn
                FROM silver.fact_plan_drug_coverage
                WHERE ndc IS NOT NULL
                  AND tier_family IS NOT NULL
                GROUP BY 1, 2
            )
            WHERE rn = 1
        ),
        tier_options AS (
            SELECT
                ndc,
                list(DISTINCT tier_family) AS available_tier_family_options
            FROM silver.fact_plan_drug_coverage
            WHERE ndc IS NOT NULL
              AND tier_family IS NOT NULL
            GROUP BY 1
        ),
        defaults_ranked AS (
            SELECT
                ndc,
                days_supply,
                observation_count,
                row_number() OVER (
                    PARTITION BY ndc
                    ORDER BY
                        CASE WHEN is_fallback THEN 1 ELSE 0 END,
                        observation_count DESC,
                        days_supply
                ) AS rn
            FROM gold.drug_input_defaults
            WHERE ndc IS NOT NULL
        ),
        day_supply_options AS (
            SELECT
                ndc,
                list(DISTINCT days_supply) AS available_day_supply_options
            FROM gold.drug_input_defaults
            WHERE ndc IS NOT NULL
              AND days_supply IS NOT NULL
            GROUP BY 1
        ),
        reference_ranked AS (
            SELECT
                ndc,
                rxcui,
                preferred_name AS drug_name,
                coalesce(synonym, '') AS drug_synonym,
                is_insulin,
                row_number() OVER (
                    PARTITION BY ndc
                    ORDER BY length(coalesce(preferred_name, synonym, ndc)), coalesce(preferred_name, synonym, ndc)
                ) AS rn
            FROM silver.dim_drug_reference
            WHERE ndc IS NOT NULL
              AND trim(coalesce(preferred_name, synonym, '')) <> ''
        )
        SELECT
            ref.drug_name,
            ref.drug_synonym,
            coalesce(cov.rxcui, ref.rxcui) AS rxcui,
            ref.ndc,
            coalesce(tm.tier_family, 'brand') AS tier_family,
            coalesce(defs.days_supply, 30) AS default_day_supply,
            dso.available_day_supply_options,
            topts.available_tier_family_options,
            coalesce(cov.plan_coverage, 0) AS plan_coverage,
            CAST(coalesce(cov.is_insulin, ref.is_insulin, FALSE) AS BOOLEAN) AS is_insulin
        FROM reference_ranked ref
        JOIN coverage cov
          ON ref.ndc = cov.ndc
        LEFT JOIN tier_mode tm
          ON ref.ndc = tm.ndc
        LEFT JOIN tier_options topts
          ON ref.ndc = topts.ndc
        LEFT JOIN defaults_ranked defs
          ON ref.ndc = defs.ndc
         AND defs.rn = 1
        LEFT JOIN day_supply_options dso
          ON ref.ndc = dso.ndc
        WHERE ref.rn = 1
        ORDER BY plan_coverage DESC, ref.drug_name, ref.ndc
        """
    ).fetch_df()


def _lookup_zip_context(config: PipelineConfig, zip_code: str) -> dict | None:
    conn = get_connection(str(config.db_path))
    row = conn.execute(
        """
        SELECT zip_code, city, state_abbr, state_name, county_display, county_code, lat, lng
        FROM silver.dim_zipcode
        WHERE zip_code = ?
        LIMIT 1
        """,
        [zip_code],
    ).fetchone()
    if row is None:
        return None
    return {
        "zip_code": row[0],
        "city": row[1],
        "state_abbr": row[2],
        "state_name": row[3],
        "county": row[4],
        "county_code": row[5],
        "lat": row[6],
        "lng": row[7],
    }


def _find_comparison_zipcodes(
    config: PipelineConfig,
    zip_context: dict,
    max_distance_miles: int,
    limit: int = 4,
) -> list[dict]:
    conn = get_connection(str(config.db_path))
    zip_df = conn.execute(
        """
        SELECT DISTINCT zip_code, county_code, state_abbr, lat, lng
        FROM silver.dim_zipcode
        WHERE zip_code IS NOT NULL
          AND lat IS NOT NULL
          AND lng IS NOT NULL
          AND county_code IS NOT NULL
        """
    ).fetch_df()
    if zip_df.empty:
        return []

    origin_lat = float(zip_context["lat"])
    origin_lng = float(zip_context["lng"])
    zip_df["distance_miles"] = zip_df.apply(
        lambda row: haversine_miles(origin_lat, origin_lng, float(row["lat"]), float(row["lng"])),
        axis=1,
    )
    nearby = zip_df[
        (zip_df["zip_code"] != zip_context["zip_code"])
        & (zip_df["county_code"] != zip_context["county_code"])
        & (zip_df["distance_miles"] <= float(max_distance_miles))
    ].copy()
    if nearby.empty:
        return []
    nearby = nearby.sort_values("distance_miles").drop_duplicates("county_code").head(limit)
    return nearby.to_dict("records")


def _comparison_recommendations(
    config: PipelineConfig,
    beneficiary: BeneficiaryInput,
    medications: list,
    *,
    max_distance_miles: int,
    local_plan_keys: set[str],
) -> list:
    zip_context = _lookup_zip_context(config, beneficiary.zipcode)
    if zip_context is None or zip_context["lat"] is None or zip_context["lng"] is None:
        return []

    comparison_rows: list = []
    for nearby in _find_comparison_zipcodes(config, zip_context, max_distance_miles=max_distance_miles):
        nearby_bene = replace(beneficiary, zipcode=str(nearby["zip_code"]))
        candidate_rows = recommend_plans(nearby_bene, medications, config=config, ranking_mode="rules")
        for row in candidate_rows:
            if row.plan_key in local_plan_keys:
                continue
            row.service_area_eligible = False
            row.comparison_only = True
            comparison_rows.append(row)
        if len(comparison_rows) >= 5:
            break

    deduped: dict[str, object] = {}
    for row in comparison_rows:
        deduped.setdefault(row.plan_key, row)
    result = list(deduped.values())[:5]
    for idx, row in enumerate(result, start=1):
        row.plan_rank = idx
    return result


def _beneficiary_from_contracts(
    profile_contract: ProfileInput,
    preference_contract: PreferenceWeights,
) -> BeneficiaryInput:
    return BeneficiaryInput(
        zipcode=profile_contract.zipcode,
        age_band=profile_contract.age_band,
        lis_status=profile_contract.lis_status,
        chronic_condition_flags=profile_contract.chronic_condition_flags or None,
        pharmacy_preference=profile_contract.pharmacy_preference,
        top_n=profile_contract.top_n,
        user_role=ROLE_MAP[profile_contract.persona],
        decision_focus=FOCUS_MAP[preference_contract.primary_goal],
    )


def _run_what_if_scenarios(
    config: PipelineConfig,
    scenario_specs: list,
    medications: list,
) -> list[dict[str, object]]:
    scenario_runs: list[dict[str, object]] = []
    for scenario in scenario_specs:
        beneficiary = _beneficiary_from_contracts(scenario.profile, scenario.preferences)
        recommendations = recommend_plans(
            beneficiary,
            medications,
            config=config,
            ranking_mode=scenario.preferences.ranking_mode,
        )
        frame = recommendations_to_dataframe(
            recommendations,
            run_id=uuid.uuid4().hex[:12],
            comparison_only=False,
            minimum_coverage_pct=scenario.preferences.minimum_coverage_pct,
        )
        scenario_runs.append(
            {
                "key": scenario.key,
                "label": scenario.label,
                "description": scenario.description,
                "profile": scenario.profile,
                "preferences": scenario.preferences,
                "recommendations": recommendations,
                "frame": frame,
                "note": build_counselor_note(
                    scenario.profile,
                    scenario.preferences,
                    frame,
                    pd.DataFrame(),
                ),
            }
        )
    return scenario_runs


def _render_what_if_section(
    config: PipelineConfig,
    profile_contract: ProfileInput,
    preference_contract: PreferenceWeights,
    medications: list,
    baseline_frame: pd.DataFrame,
) -> None:
    st.markdown("#### Beneficiary what-if scenarios")
    scenario_specs = build_what_if_scenarios(
        profile_contract,
        preference_contract,
        has_medications=bool(medications),
    )
    if not scenario_specs:
        st.caption("No alternate what-if scenarios are available for the current beneficiary inputs.")
        return

    scenario_lookup = {scenario.key: scenario for scenario in scenario_specs}
    selected_keys = st.multiselect(
        "Compare alternate beneficiary assumptions",
        options=list(scenario_lookup.keys()),
        key="what_if_selected_scenarios",
        format_func=lambda key: scenario_lookup[key].label,
        help="Run the same medication list against alternate beneficiary assumptions or shortlist postures.",
    )
    selected_scenarios = [scenario_lookup[key] for key in selected_keys if key in scenario_lookup]
    if selected_scenarios:
        st.caption(
            " | ".join(
                f"{scenario.label}: {scenario.description}" for scenario in selected_scenarios
            )
        )
        if st.button("Run what-if scenarios", use_container_width=True):
            with st.spinner("Running beneficiary what-if scenarios..."):
                scenario_runs = _run_what_if_scenarios(config, selected_scenarios, medications)
            st.session_state["what_if_runs"] = scenario_runs
            st.session_state["what_if_summary_df"] = build_what_if_summary_frame(
                baseline_frame,
                [(scenario_lookup[run["key"]], run["frame"]) for run in scenario_runs],
            )
            st.session_state["what_if_note"] = summarize_what_if_findings(
                st.session_state["what_if_summary_df"]
            )
            st.session_state["what_if_run_keys"] = list(selected_keys)
    else:
        st.caption("Pick one or more scenarios to see how the shortlist shifts under alternate assumptions.")

    stored_keys = st.session_state.get("what_if_run_keys", [])
    selection_changed = list(selected_keys) != list(stored_keys)
    scenario_runs = st.session_state.get("what_if_runs", [])
    summary_frame = st.session_state.get("what_if_summary_df", pd.DataFrame())
    what_if_note = st.session_state.get("what_if_note", "")

    if selection_changed and scenario_runs:
        st.caption("Scenario selection changed. Run the what-if analysis again to refresh the comparison.")
        return
    if summary_frame is None or summary_frame.empty:
        return

    if what_if_note:
        st.info(what_if_note)
    st.dataframe(summary_frame, use_container_width=True, hide_index=True)

    tabs = st.tabs([run["label"] for run in scenario_runs])
    for tab, run in zip(tabs, scenario_runs, strict=False):
        with tab:
            st.caption(str(run["description"]))
            if run.get("note"):
                st.info(str(run["note"]))
            frame = run.get("frame")
            recommendations = run.get("recommendations") or []
            if frame is None or frame.empty:
                st.warning("No eligible plans were returned for this scenario.")
                continue
            st.dataframe(frame.head(5), use_container_width=True, hide_index=True)
            preview_keys = frame["PLAN_KEY"].head(3).tolist()
            scenario_side_by_side = build_side_by_side_frame(frame, preview_keys)
            if not scenario_side_by_side.empty:
                st.markdown("**Scenario side-by-side**")
                st.dataframe(scenario_side_by_side, use_container_width=True, hide_index=True)
            if recommendations:
                st.markdown("**Top scenario plan details**")
                _render_plan_details(recommendations[:1])


def _render_metric_cards(frame: pd.DataFrame) -> None:
    if frame.empty:
        return
    top = frame.iloc[0]
    cols = st.columns(4)
    metrics = [
        ("Top plan", str(top["PLAN_NAME"])),
        ("Annual total", f"${float(top['estimated_total_annual_cost']):,.0f}"),
        ("Estimated OOP", f"${float(top['estimated_annual_oop']):,.0f}"),
        ("Confidence", str(top["confidence_band"])),
    ]
    for column, (label, value) in zip(cols, metrics, strict=False):
        column.markdown(
            f"""
            <div class="metric-card">
              <div class="metric-label">{label}</div>
              <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _clear_result_state() -> None:
    for key in [
        "result_bundle",
        "result_summary_df",
        "result_df",
        "full_result_df",
        "partial_fallback_df",
        "comparison_df",
        "blocked_medications_df",
        "alternative_search_terms_df",
        "audit",
        "public_contract",
        "recommendations",
        "full_coverage_recommendations",
        "partial_fallback_recommendations",
        "comparison_recommendations",
        "counselor_note",
    ]:
        st.session_state.pop(key, None)
    st.session_state["what_if_runs"] = []
    st.session_state["what_if_summary_df"] = pd.DataFrame()
    st.session_state["what_if_note"] = ""
    st.session_state["what_if_run_keys"] = []


def _apply_catalog_alternative(
    medication_id: str,
    catalog_row: pd.Series,
    *,
    day_supply: int,
    tier_family: str,
) -> None:
    try:
        medication_index = int(str(medication_id).split("_")[-1]) - 1
    except (TypeError, ValueError):
        st.session_state["alternative_notice"] = "Could not map the blocked medication back to the editor row."
        return

    medication_rows = [dict(row) for row in st.session_state.get("medication_editor_rows", DEFAULT_MEDICATION_ROWS)]
    if medication_index < 0 or medication_index >= len(medication_rows):
        st.session_state["alternative_notice"] = "The blocked medication row is no longer available in the editor."
        return

    existing_row = medication_rows[medication_index]
    replacement = build_medication_row_from_catalog(
        catalog_row,
        day_supply=day_supply,
        tier_family=tier_family,
    )
    replacement["quantity_override"] = existing_row.get("quantity_override")
    replacement["fills_per_year_override"] = existing_row.get("fills_per_year_override")
    medication_rows[medication_index] = replacement
    st.session_state["medication_editor_rows"] = medication_rows
    st.session_state["alternative_notice"] = (
        f"Updated {medication_id} to {replacement['drug_name']}. Run decision support again to rescore the shortlist."
    )
    _clear_result_state()


def _render_monthly_timeline_charts(timeline_frame: pd.DataFrame) -> None:
    if timeline_frame.empty:
        return
    month_order = timeline_frame["Month"].tolist()
    cash_flow_frame = timeline_frame[["Month", "Month number", "Drug OOP", "Projected monthly total"]].melt(
        id_vars=["Month", "Month number"],
        value_vars=["Drug OOP", "Projected monthly total"],
        var_name="Metric",
        value_name="Amount",
    )
    cumulative_frame = timeline_frame[["Month", "Month number", "Cumulative drug OOP", "Cumulative total"]].melt(
        id_vars=["Month", "Month number"],
        value_vars=["Cumulative drug OOP", "Cumulative total"],
        var_name="Metric",
        value_name="Amount",
    )
    x_encoding = alt.X("Month:N", sort=month_order, title="Month")
    cash_flow_chart = (
        alt.Chart(cash_flow_frame)
        .mark_bar()
        .encode(
            x=x_encoding,
            y=alt.Y("Amount:Q", title="Dollars"),
            color=alt.Color("Metric:N", title="Series"),
            xOffset="Metric:N",
            tooltip=["Month", "Metric", alt.Tooltip("Amount:Q", format=",.2f")],
        )
    )
    cumulative_chart = (
        alt.Chart(cumulative_frame)
        .mark_line(point=True)
        .encode(
            x=x_encoding,
            y=alt.Y("Amount:Q", title="Dollars"),
            color=alt.Color("Metric:N", title="Series"),
            tooltip=["Month", "Metric", alt.Tooltip("Amount:Q", format=",.2f")],
        )
    )
    chart_cols = st.columns(2)
    chart_cols[0].altair_chart(cash_flow_chart, use_container_width=True)
    chart_cols[1].altair_chart(cumulative_chart, use_container_width=True)


def _render_plan_details(recommendations: list) -> None:
    for recommendation in recommendations[:5]:
        with st.expander(
            f"{recommendation.plan_name} | {recommendation.fit_label} | {recommendation.ranking_source}"
        ):
            metric_cols = st.columns(4)
            metric_cols[0].metric("Annual total", f"${recommendation.annual_total_cost:,.0f}")
            metric_cols[1].metric("Annual OOP", f"${recommendation.estimated_annual_oop:,.0f}")
            metric_cols[2].metric("Annual premium", f"${recommendation.annual_premium:,.0f}")
            metric_cols[3].metric("Fit score", f"{recommendation.fit_score:,.1f}")
            timeline_cols = st.columns(4)
            timeline_cols[0].metric("Priced meds", f"{recommendation.priced_drug_count}")
            timeline_cols[1].metric("Channel switches", f"{recommendation.channel_switch_count}")
            timeline_cols[2].metric("Benefit design", recommendation.benefit_design)
            timeline_cols[3].metric("Simulation policy", recommendation.simulation_policy)
            st.write(recommendation.fit_summary)
            st.write(recommendation.network_access_summary)
            if recommendation.key_strengths:
                st.markdown("**Key strengths**")
                for item in recommendation.key_strengths:
                    st.write(f"- {item}")
            if recommendation.key_watchouts:
                st.markdown("**Key watchouts**")
                for item in recommendation.key_watchouts:
                    st.write(f"- {item}")

            grouped_sections = [
                ("Coverage issues", recommendation.explanation_groups.coverage_issues),
                (
                    "Utilization management",
                    recommendation.explanation_groups.utilization_management_issues,
                ),
                ("Insulin considerations", recommendation.explanation_groups.insulin_considerations),
                ("Pharmacy access", recommendation.explanation_groups.pharmacy_access_issues),
                ("Deductible issues", recommendation.explanation_groups.deductible_issues),
                ("Cost logic", recommendation.explanation_groups.cost_logic_issues),
            ]
            for label, items in grouped_sections:
                if items:
                    st.markdown(f"**{label}**")
                    for item in items:
                        st.write(f"- {item}")

            timeline_frame = build_monthly_timeline_frame(recommendation)
            if not timeline_frame.empty:
                st.markdown("**Monthly cash-flow view**")
                st.caption("Month buckets are relative to the simulated plan year and combine premium plus projected drug cost-sharing.")
                _render_monthly_timeline_charts(timeline_frame)
                st.dataframe(
                    timeline_frame.drop(columns=["Month number"]),
                    use_container_width=True,
                    hide_index=True,
                )

            drug_rows = pd.DataFrame(
                [
                    {
                        "Drug": breakdown.drug_name,
                        "Requested day supply": breakdown.requested_day_supply,
                        "Selected channel": breakdown.selected_channel,
                        "Coverage status": breakdown.coverage_status,
                        "Pricing status": breakdown.pricing_status,
                        "Annual OOP": breakdown.annual_oop,
                        "Channel path": summarize_drug_channel_path(breakdown),
                        "Prior auth": breakdown.pa_flag,
                        "Step therapy": breakdown.st_flag,
                        "Quantity limit": breakdown.ql_flag,
                        "Insulin": breakdown.insulin_flag,
                        "Notes": " | ".join(breakdown.explanations),
                    }
                    for breakdown in recommendation.drug_breakdowns
                ]
            )
            if not drug_rows.empty:
                st.markdown("**Drug-by-drug view**")
                st.dataframe(drug_rows, use_container_width=True, hide_index=True)


def _render_research_mode(config: PipelineConfig) -> None:
    st.subheader("Research / Evaluation")
    scenario_bundle = st.text_input("Scenario bundle filter", value="")
    baseline_only = st.checkbox("Baseline only", value=False)
    if st.button("Run research evaluation", type="primary"):
        bundles = [scenario_bundle.strip()] if scenario_bundle.strip() else None
        with st.spinner("Building or loading dataset and evaluation artifacts..."):
            frame, report = ensure_research_artifacts(
                config,
                scenario_bundles=bundles,
                baseline_only=baseline_only,
            )
        st.session_state["research_frame"] = frame
        st.session_state["research_report"] = report

    report = st.session_state.get("research_report")
    frame = st.session_state.get("research_frame")
    if report is None or frame is None:
        st.info("Run the evaluation to inspect model-vs-rules performance and subgroup summaries.")
        return

    systems_df = systems_summary_frame(report)
    st.markdown("#### Systems summary")
    st.dataframe(systems_df, use_container_width=True, hide_index=True)
    if not systems_df.empty:
        chart = systems_df.set_index("system")[
            [col for col in ["top5_overlap", "top10_overlap", "ndcg_5", "ndcg_10"] if col in systems_df.columns]
        ]
        if not chart.empty:
            st.bar_chart(chart)

    st.markdown("#### Dataset diagnostics")
    st.dataframe(dataset_diagnostics_frame(frame), use_container_width=True, hide_index=True)

    bundle_frames = scenario_bundle_frames(report)
    if bundle_frames:
        st.markdown("#### Scenario bundles")
        tabs = st.tabs(list(bundle_frames))
        for tab, bundle_name in zip(tabs, bundle_frames, strict=False):
            with tab:
                st.dataframe(bundle_frames[bundle_name], use_container_width=True, hide_index=True)

    subgroup_map = subgroup_frames(frame)
    if subgroup_map:
        st.markdown("#### Subgroup slices")
        subgroup_tabs = st.tabs(list(subgroup_map))
        for tab, name in zip(subgroup_tabs, subgroup_map, strict=False):
            with tab:
                st.dataframe(subgroup_map[name], use_container_width=True, hide_index=True)

    st.download_button(
        "Download research dataset (CSV)",
        data=frame.to_csv(index=False),
        file_name="cms_mpd_research_dataset.csv",
        mime="text/csv",
    )
    st.download_button(
        "Download evaluation report (JSON)",
        data=json.dumps(report, indent=2),
        file_name="cms_mpd_research_report.json",
        mime="application/json",
    )


def main() -> None:
    _inject_styles()
    config = get_config()
    st.markdown(
        """
        <div class="hero">
          <div class="hero-kicker">CMS MPD Recommendation</div>
          <div class="hero-title">Counselor-first Medicare Part D decision support</div>
          <div class="hero-copy">This workspace combines a DuckDB medallion pipeline, a rules-first OOP engine, a hybrid reranker, and counselor-facing outputs so beneficiaries, caregivers, and navigators can compare plans with clearer cost, access, and medication-fit explanations.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not config.db_path.exists():
        st.error(
            f"DuckDB database not found at `{config.db_path}`. Run `python -m cms_mpd build --build-profile {config.build_profile}` first."
        )
        return

    st.sidebar.markdown("### Workspace")
    st.sidebar.caption(f"Build profile: `{config.build_profile}`")
    st.sidebar.caption(f"Data dir: `{config.data_dir}`")
    st.sidebar.caption(f"Source data dir: `{config.source_data_dir}`")
    mode = st.sidebar.radio("Mode", ["Decision Support", "Research / Evaluation"], index=0)

    if mode == "Research / Evaluation":
        _render_research_mode(config)
        return

    for key, value in {
        "profile_persona": "Counselor",
        "profile_zipcode": "43004",
        "profile_age_band": "65-74",
        "profile_lis_status": "none",
        "profile_pharmacy_preference": "auto",
        "profile_chronic_flags": ["diabetes"],
        "profile_top_n": 5,
        "preference_primary_goal": PRIMARY_GOALS[0],
        "preference_allow_comparison": False,
        "preference_max_distance": 50,
        "preference_min_coverage": 100,
        "preference_ranking_mode": "rules",
        "medication_editor_seed": DEFAULT_MEDICATION_ROWS,
        "medication_editor_rows": DEFAULT_MEDICATION_ROWS,
        "medication_search_query": "",
        "alternative_notice": "",
        "what_if_selected_scenarios": [],
        "what_if_run_keys": [],
        "what_if_runs": [],
        "what_if_summary_df": pd.DataFrame(),
        "what_if_note": "",
    }.items():
        st.session_state.setdefault(key, value)

    profile_tab, meds_tab, preference_tab, results_tab = st.tabs(
        ["1. Profile", "2. Medications", "3. Preferences", "4. Results"]
    )

    with profile_tab:
        st.subheader("1. Profile")
        st.caption("Start with who you are helping and the beneficiary ZIP code. Eligibility and service area come first.")
        persona = st.radio("Who are you helping?", PERSONA_OPTIONS, horizontal=True, key="profile_persona")
        col1, col2, col3 = st.columns(3)
        zipcode = col1.text_input("ZIP code", key="profile_zipcode", max_chars=5)
        age_band = col2.selectbox("Age band", ["65-74", "75-84", "85+"], key="profile_age_band")
        lis_status = col3.selectbox("LIS status", ["none", "partial", "full"], key="profile_lis_status")
        col4, col5 = st.columns(2)
        pharmacy_preference = col4.selectbox(
            "Pharmacy preference",
            ["auto", "retail", "mail"],
            key="profile_pharmacy_preference",
        )
        top_n = col5.slider("How many plans to return", min_value=3, max_value=10, key="profile_top_n")
        chronic_flags = st.multiselect(
            "Chronic condition flags",
            CHRONIC_FLAG_OPTIONS,
            key="profile_chronic_flags",
        )
        zip_context = None
        clean_zip = coerce_zipcode(zipcode)
        if len(clean_zip) == 5:
            zip_context = _lookup_zip_context(config, clean_zip)
            if zip_context:
                st.success(
                    f"ZIP lookup: {zip_context['city']}, {zip_context['state_name']} | {zip_context['county']}"
                )
            else:
                st.warning("ZIP lookup did not resolve in the current build.")
        profile_contract = ProfileInput(
            persona=persona,
            zipcode=clean_zip,
            age_band=age_band,
            lis_status=lis_status,
            pharmacy_preference=pharmacy_preference,
            chronic_condition_flags=chronic_flags,
            top_n=int(top_n),
        )
        st.session_state["profile_contract"] = profile_contract
        st.session_state["profile_zip_context"] = zip_context

    with meds_tab:
        st.subheader("2. Medications")
        st.caption("Capture drug name, RXCUI, or NDC. The closer this list is to the real regimen, the better the plan explanations will be.")
        if st.session_state.get("alternative_notice"):
            st.success(str(st.session_state.get("alternative_notice")))
            st.session_state["alternative_notice"] = ""
        st.markdown("#### Search available drugs")
        st.caption("Search the system catalog and add a matched drug directly into the medication list.")
        drug_catalog = get_drug_catalog(str(config.db_path))
        search_col, limit_col = st.columns([3, 1])
        search_query = search_col.text_input(
            "Search by drug name, synonym, RXCUI, or NDC",
            key="medication_search_query",
            placeholder="Try insulin glargine, albuterol, 222222, or an NDC",
        )
        result_limit = limit_col.selectbox("Results", options=[10, 25, 50], index=1, key="medication_search_limit")
        matches = search_drug_catalog(drug_catalog, search_query, limit=result_limit)
        if search_query.strip():
            if matches.empty:
                st.info("No matching drugs were found in the current system catalog.")
            else:
                option_labels = [format_drug_catalog_option(row) for _, row in matches.iterrows()]
                selected_label = st.selectbox(
                    "Matching catalog drugs",
                    options=option_labels,
                    key="medication_catalog_match",
                )
                selected_index = option_labels.index(selected_label)
                selected_row = matches.iloc[selected_index]
                picker_cols = st.columns([1, 1, 1.2])
                default_day_supply = int(selected_row.get("default_day_supply") or 30)
                day_supply_options = [30, 60, 90]
                try:
                    default_day_supply_index = day_supply_options.index(default_day_supply)
                except ValueError:
                    default_day_supply_index = 0
                selected_day_supply = picker_cols[0].selectbox(
                    "Day supply for add",
                    options=day_supply_options,
                    index=default_day_supply_index,
                    key="medication_catalog_day_supply",
                )
                tier_family_options = catalog_tier_family_options(selected_row)
                default_tier_family = str(selected_row.get("tier_family") or tier_family_options[0]).strip().lower()
                try:
                    default_tier_family_index = tier_family_options.index(default_tier_family)
                except ValueError:
                    default_tier_family_index = 0
                selected_tier_family = picker_cols[1].selectbox(
                    "Tier family for add",
                    options=tier_family_options,
                    index=default_tier_family_index,
                    key="medication_catalog_tier_family",
                    disabled=len(tier_family_options) == 1,
                )
                if picker_cols[2].button("Add selected drug", use_container_width=True):
                    st.session_state["medication_editor_rows"] = append_medication_row(
                        list(st.session_state.get("medication_editor_rows", DEFAULT_MEDICATION_ROWS)),
                        build_medication_row_from_catalog(
                            selected_row,
                            day_supply=selected_day_supply,
                            tier_family=selected_tier_family,
                        ),
                    )
                available_day_supply = ", ".join(
                    f"{value}-day" for value in catalog_available_day_supply_options(selected_row)
                )
                available_tiers = ", ".join(tier_family_options)
                st.caption(
                    f"Available in {int(selected_row.get('plan_coverage') or 0):,} plans. "
                    f"Observed day-supply options: {available_day_supply}. "
                    f"Available tier families: {available_tiers}."
                )

        editor_source = pd.DataFrame(st.session_state.get("medication_editor_rows", DEFAULT_MEDICATION_ROWS))
        med_editor = st.data_editor(
            editor_source,
            key="medication_editor",
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "drug_name": st.column_config.TextColumn("Drug name"),
                "rxcui": st.column_config.TextColumn("RXCUI"),
                "ndc": st.column_config.TextColumn("NDC"),
                "tier_family": st.column_config.SelectboxColumn(
                    "Tier family",
                    options=["generic", "brand", "specialty"],
                    required=False,
                ),
                "day_supply": st.column_config.SelectboxColumn("Day supply", options=[30, 60, 90]),
                "quantity_override": st.column_config.NumberColumn("Quantity override", min_value=0.0, step=1.0),
                "fills_per_year_override": st.column_config.NumberColumn("Fills / year", min_value=1, step=1),
            },
        )
        st.session_state["medication_editor_rows"] = med_editor.to_dict("records")
        medications, medication_contract_rows, med_errors = parse_medication_frame(med_editor)
        if med_errors:
            for error in med_errors:
                st.warning(error)
        st.session_state["medications"] = medications
        st.session_state["medication_contract_rows"] = medication_contract_rows

    with preference_tab:
        st.subheader("3. Preferences")
        st.caption("Choose the decision posture. This controls how conservative the shortlist should be and whether nearby out-of-area plans should appear for comparison.")
        has_medications = bool(st.session_state.get("medications"))
        primary_goal = st.selectbox("Primary goal", PRIMARY_GOALS, key="preference_primary_goal")
        preset = recommend_preference_preset(
            st.session_state.get("profile_persona", "Counselor"),
            primary_goal,
            has_medications,
        )
        st.markdown(
            f"""
            <div class="panel">
              <div class="panel-title">Suggested posture</div>
              <div>Cost priority {preset['cost_priority']}/5, medication-fit priority {preset['coverage_priority']}/5, access priority {preset['access_priority']}/5.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        allow_comparison = st.checkbox(
            "Allow nearby out-of-area comparison plans",
            key="preference_allow_comparison",
        )
        max_distance = st.slider(
            "Nearby comparison radius (miles)",
            min_value=10,
            max_value=100,
            step=10,
            key="preference_max_distance",
            disabled=not allow_comparison,
        )
        min_coverage = st.slider(
            "Minimum requested-drug coverage (%)",
            min_value=0,
            max_value=100,
            step=5,
            key="preference_min_coverage",
            value=int(preset["minimum_coverage_pct"]),
            disabled=not has_medications,
        )
        ranking_options = ["rules", "hybrid"] if config.model_artifact_path.exists() else ["rules"]
        ranking_mode = st.selectbox("Ranking mode", ranking_options, key="preference_ranking_mode")
        preference_contract = PreferenceWeights(
            primary_goal=primary_goal,
            minimum_coverage_pct=float(min_coverage),
            allow_comparison_plans=bool(allow_comparison),
            max_comparison_distance_miles=int(max_distance),
            ranking_mode=ranking_mode,
        )
        st.session_state["preference_contract"] = preference_contract

    with results_tab:
        st.subheader("4. Results")
        st.caption("Run the end-to-end decision support flow once the first three steps are ready.")
        if st.button("Run decision support", type="primary", use_container_width=True):
            profile_contract: ProfileInput = st.session_state.get("profile_contract")
            medications: list[MedicationInput] = st.session_state.get("medications", [])
            preference_contract: PreferenceWeights = st.session_state.get("preference_contract")
            zip_context = st.session_state.get("profile_zip_context")
            errors: list[str] = []
            if profile_contract is None or len(profile_contract.zipcode) != 5:
                errors.append("Enter a valid 5-digit ZIP code.")
            if profile_contract is not None and zip_context is None:
                errors.append("The ZIP code was not found in the built service-area data.")
            if not medications:
                errors.append("Add at least one medication row.")
            if preference_contract is None:
                errors.append("Preference step is incomplete.")
            if errors:
                for error in errors:
                    st.error(error)
            else:
                beneficiary = _beneficiary_from_contracts(profile_contract, preference_contract)
                try:
                    with st.spinner("Running recommendation engine and comparison workflow..."):
                        bundle = recommend_plan_bundle(
                            beneficiary,
                            medications,
                            config=config,
                            ranking_mode=preference_contract.ranking_mode,
                        )
                        comparison_recs = []
                        local_plan_keys = {
                            row.plan_key
                            for row in (bundle.full_coverage_plans + bundle.partial_fallback_plans)
                        }
                        if preference_contract.allow_comparison_plans and local_plan_keys:
                            comparison_recs = _comparison_recommendations(
                                config,
                                beneficiary,
                                medications,
                                max_distance_miles=preference_contract.max_comparison_distance_miles,
                                local_plan_keys=local_plan_keys,
                            )
                            bundle = replace(bundle, comparison_only_plans=comparison_recs[:5])
                except ValueError as exc:
                    _clear_result_state()
                    st.error(str(exc))
                    return

                run_id = uuid.uuid4().hex[:12]
                bundle_frames = recommendation_bundle_to_dataframes(
                    bundle,
                    run_id=run_id,
                    minimum_coverage_pct=preference_contract.minimum_coverage_pct,
                )
                summary_df = bundle_frames["summary"]
                full_result_df = bundle_frames["full_coverage_plans"]
                partial_fallback_df = bundle_frames["partial_fallback_plans"]
                comparison_df = bundle_frames["comparison_only_plans"]
                blocked_medications_df = bundle_frames["blocked_medications"]
                alternative_search_terms_df = bundle_frames["alternative_search_terms"]
                local_result_df = (
                    full_result_df if not full_result_df.empty else partial_fallback_df
                )
                local_display_recommendations = (
                    bundle.full_coverage_plans
                    if bundle.full_coverage_plans
                    else bundle.partial_fallback_plans
                )
                feature_coverage = summarize_feature_coverage(local_display_recommendations, comparison_recs)
                feature_coverage["candidate_plans"] = int(bundle.summary.local_candidate_plan_count) + len(comparison_recs)
                feature_coverage["eligible_plans"] = int(bundle.summary.local_candidate_plan_count)
                feature_coverage["comparison_only_plans"] = len(comparison_recs)
                feature_coverage["plans_with_full_coverage"] = int(bundle.summary.local_full_coverage_count)
                public_contract = as_public_types(
                    profile_contract,
                    [MedicationListItem(**row) for row in st.session_state.get("medication_contract_rows", [])],
                    preference_contract,
                )
                combined_sections = [
                    frame
                    for frame in (full_result_df, partial_fallback_df, comparison_df)
                    if frame is not None and not frame.empty
                ]
                combined_frame = (
                    pd.concat(combined_sections, ignore_index=True)
                    if combined_sections
                    else pd.DataFrame()
                )
                audit = create_run_audit(
                    user_input_summary=public_contract,
                    model_version=(
                        config.model_artifact_path.name
                        if config.model_artifact_path.exists()
                        else "rules-only"
                    ),
                    data_snapshot=config.snapshot_quarter,
                    feature_coverage=feature_coverage,
                    recommendations=combined_frame,
                    run_id=run_id,
                )
                st.session_state["result_bundle"] = bundle
                st.session_state["result_summary_df"] = summary_df
                st.session_state["result_df"] = local_result_df
                st.session_state["full_result_df"] = full_result_df
                st.session_state["partial_fallback_df"] = partial_fallback_df
                st.session_state["comparison_df"] = comparison_df
                st.session_state["blocked_medications_df"] = blocked_medications_df
                st.session_state["alternative_search_terms_df"] = alternative_search_terms_df
                st.session_state["audit"] = asdict(audit)
                st.session_state["public_contract"] = public_contract
                st.session_state["recommendations"] = local_display_recommendations
                st.session_state["full_coverage_recommendations"] = bundle.full_coverage_plans
                st.session_state["partial_fallback_recommendations"] = bundle.partial_fallback_plans
                st.session_state["comparison_recommendations"] = comparison_recs
                st.session_state["counselor_note"] = build_counselor_note(
                    profile_contract,
                    preference_contract,
                    local_result_df,
                    comparison_df,
                )
                st.session_state["what_if_runs"] = []
                st.session_state["what_if_summary_df"] = pd.DataFrame()
                st.session_state["what_if_note"] = ""
                st.session_state["what_if_run_keys"] = []

        result_bundle = st.session_state.get("result_bundle")
        result_summary_df = st.session_state.get("result_summary_df", pd.DataFrame())
        result_df = st.session_state.get("result_df", pd.DataFrame())
        full_result_df = st.session_state.get("full_result_df", pd.DataFrame())
        partial_fallback_df = st.session_state.get("partial_fallback_df", pd.DataFrame())
        comparison_df = st.session_state.get("comparison_df", pd.DataFrame())
        blocked_medications_df = st.session_state.get("blocked_medications_df", pd.DataFrame())
        alternative_search_terms_df = st.session_state.get("alternative_search_terms_df", pd.DataFrame())
        audit = st.session_state.get("audit")
        public_contract = st.session_state.get("public_contract")
        recommendations = st.session_state.get("recommendations", [])
        full_coverage_recommendations = st.session_state.get("full_coverage_recommendations", [])
        partial_fallback_recommendations = st.session_state.get("partial_fallback_recommendations", [])
        comparison_recommendations = st.session_state.get("comparison_recommendations", [])
        counselor_note = st.session_state.get("counselor_note")
        current_profile_contract: ProfileInput | None = st.session_state.get("profile_contract")
        current_preference_contract: PreferenceWeights | None = st.session_state.get("preference_contract")
        current_medications = st.session_state.get("medications", [])
        if result_bundle is None:
            st.info("Complete the first three steps, then run decision support to generate a shortlist.")
            return

        if not result_df.empty:
            _render_metric_cards(result_df)
        if not result_summary_df.empty:
            summary_row = result_summary_df.iloc[0]
            scenario_profile = str(summary_row.get("scenario_profile") or "").strip()
            if scenario_profile:
                scenario_label = scenario_profile.replace("_", " ")
                st.caption(
                    f"Scenario profile: `{scenario_profile}`. "
                    f"{SCENARIO_IMPACT_NOTES.get(scenario_profile, scenario_label.capitalize())}"
                )
            if (
                str(summary_row.get("fallback_reason") or "") == "no_local_full_coverage"
                and int(summary_row.get("local_candidate_plan_count") or 0) > 0
            ):
                st.warning(
                    "No local ZIP-eligible plan fully covers every entered drug exactly as entered. "
                    "Showing the best local fallback plans and the exact blockers instead."
                )
            elif int(summary_row.get("local_candidate_plan_count") or 0) == 0:
                st.warning("No local ZIP-eligible plans were found for the selected ZIP code.")

        st.markdown("#### Local full-coverage plans")
        if full_result_df.empty:
            st.caption("No local full-coverage plans were found for the exact entered regimen.")
        else:
            st.dataframe(full_result_df.head(10), use_container_width=True, hide_index=True)

        st.markdown("#### Best local fallback plans")
        if partial_fallback_df.empty:
            st.caption("Fallback plans are only shown when no local full-coverage plan exists.")
        else:
            st.dataframe(partial_fallback_df.head(10), use_container_width=True, hide_index=True)

        if not comparison_df.empty:
            st.markdown("#### Nearby comparison-only plans")
            st.dataframe(comparison_df.head(5), use_container_width=True, hide_index=True)

        st.markdown("#### Blocked exact drugs and alternative search")
        if blocked_medications_df.empty:
            st.caption("No blocked exact drugs were identified for the current local shortlist.")
        else:
            st.dataframe(blocked_medications_df, use_container_width=True, hide_index=True)
            st.caption(
                "Search seeds below are derived from the blocked exact products. Choosing an alternative updates "
                "the medication list, but does not auto-substitute or rerun recommendations."
            )
            blocked_ndc_lookup = (
                blocked_medications_df.set_index("medication_id")["ndc"].astype(str).to_dict()
                if "medication_id" in blocked_medications_df.columns
                else {}
            )
            blocked_rxcui_lookup = (
                blocked_medications_df.set_index("medication_id")["rxcui"].astype(str).to_dict()
                if "medication_id" in blocked_medications_df.columns
                else {}
            )
            drug_catalog = get_drug_catalog(str(config.db_path))
            current_rows = [dict(row) for row in st.session_state.get("medication_editor_rows", DEFAULT_MEDICATION_ROWS)]
            scenario_profile = (
                str(result_bundle.summary.scenario_profile or "")
                if result_bundle is not None
                else ""
            )
            for alternative_row in alternative_search_terms_df.to_dict("records"):
                medication_id = str(alternative_row.get("medication_id") or "")
                search_term = str(alternative_row.get("search_term") or "").strip()
                resolved_drug_name = str(alternative_row.get("resolved_drug_name") or medication_id)
                st.markdown(f"**{resolved_drug_name}**")
                st.caption(f"Suggested search seed: `{search_term}`")
                search_matches = search_drug_catalog(drug_catalog, search_term, limit=10)
                blocked_ndc = blocked_ndc_lookup.get(medication_id)
                if blocked_ndc:
                    search_matches = search_matches[
                        search_matches["ndc"].fillna("").astype(str) != str(blocked_ndc)
                    ].reset_index(drop=True)
                try:
                    medication_index = int(medication_id.split("_")[-1]) - 1
                except (TypeError, ValueError):
                    medication_index = -1
                existing_row = current_rows[medication_index] if 0 <= medication_index < len(current_rows) else {}
                search_matches = rank_alternative_matches(
                    search_matches,
                    blocked_drug_name=resolved_drug_name,
                    current_row=existing_row,
                    blocked_rxcui=blocked_rxcui_lookup.get(medication_id),
                    limit=10,
                )
                if search_matches.empty:
                    st.caption("No alternative products matched this search seed in the local drug catalog.")
                    continue
                option_labels = [format_drug_catalog_option(row) for _, row in search_matches.iterrows()]
                selected_label = st.selectbox(
                    f"Alternative products for {resolved_drug_name}",
                    options=option_labels,
                    key=f"alternative_picker_{medication_id}",
                )
                selected_row = search_matches.iloc[option_labels.index(selected_label)]
                selected_plan_coverage = int(selected_row.get("plan_coverage") or 0)
                selected_is_insulin = bool(selected_row.get("is_insulin"))
                prior_is_insulin = "insulin" in str(existing_row.get("drug_name") or resolved_drug_name).lower()
                prior_tier_family = str(existing_row.get("tier_family") or "").strip().lower()
                selected_tier_family_from_row = str(
                    selected_row.get("tier_family") or existing_row.get("tier_family") or ""
                ).strip().lower()
                preserves_insulin = selected_is_insulin == prior_is_insulin
                preserves_specialty = (
                    (prior_tier_family == "specialty") == (selected_tier_family_from_row == "specialty")
                )
                st.caption(
                    f"Local plan coverage: {selected_plan_coverage} plans. "
                    f"Scenario impact: {SCENARIO_IMPACT_NOTES.get(scenario_profile, 'Review the new product before rerunning the shortlist.')}"
                )
                st.caption(
                    "Preserves insulin status: "
                    f"{'yes' if preserves_insulin else 'no'}; preserves specialty status: "
                    f"{'yes' if preserves_specialty else 'no'}."
                )
                picker_cols = st.columns([1, 1, 1.2])
                day_supply_options = catalog_available_day_supply_options(selected_row)
                default_day_supply = int(existing_row.get("day_supply") or day_supply_options[0])
                try:
                    default_day_supply_index = day_supply_options.index(default_day_supply)
                except ValueError:
                    default_day_supply_index = 0
                selected_day_supply = picker_cols[0].selectbox(
                    "Day supply",
                    options=day_supply_options,
                    index=default_day_supply_index,
                    key=f"alternative_day_supply_{medication_id}",
                )
                tier_family_options = catalog_tier_family_options(selected_row)
                default_tier_family = (
                    str(existing_row.get("tier_family") or selected_row.get("tier_family") or tier_family_options[0])
                    .strip()
                    .lower()
                )
                try:
                    default_tier_family_index = tier_family_options.index(default_tier_family)
                except ValueError:
                    default_tier_family_index = 0
                selected_tier_family = picker_cols[1].selectbox(
                    "Tier family",
                    options=tier_family_options,
                    index=default_tier_family_index,
                    key=f"alternative_tier_{medication_id}",
                    disabled=len(tier_family_options) == 1,
                )
                if picker_cols[2].button(
                    "Use selected alternative in medication list",
                    key=f"apply_alternative_{medication_id}",
                    use_container_width=True,
                ):
                    _apply_catalog_alternative(
                        medication_id,
                        selected_row,
                        day_supply=int(selected_day_supply),
                        tier_family=str(selected_tier_family),
                    )
                    st.rerun()

        combined_sections = [
            frame for frame in (full_result_df, partial_fallback_df, comparison_df) if not frame.empty
        ]
        combined_frame = (
            pd.concat(combined_sections, ignore_index=True)
            if combined_sections
            else pd.DataFrame()
        )
        if not combined_frame.empty:
            plan_lookup = combined_frame.drop_duplicates("PLAN_KEY").set_index("PLAN_KEY")
            default_compare = plan_lookup.index.tolist()[: min(3, len(plan_lookup))]
            selected_plan_keys = st.multiselect(
                "Choose plans for side-by-side comparison",
                options=plan_lookup.index.tolist(),
                default=default_compare,
                format_func=lambda plan_key: (
                    f"{plan_lookup.loc[plan_key, 'PLAN_NAME']} "
                    f"({'comparison only' if bool(plan_lookup.loc[plan_key, 'comparison_only']) else 'eligible'})"
                ),
            )
            side_by_side = build_side_by_side_frame(combined_frame, selected_plan_keys)
            if not side_by_side.empty:
                st.markdown("#### Side-by-side comparison")
                st.dataframe(side_by_side, use_container_width=True, hide_index=True)

        if counselor_note:
            st.markdown("#### Counselor note")
            st.info(counselor_note)

        if current_profile_contract is not None and current_preference_contract is not None:
            _render_what_if_section(
                config,
                current_profile_contract,
                current_preference_contract,
                current_medications,
                result_df,
            )

        evidence_gaps = summarize_evidence_gaps(result_df, comparison_df)
        if evidence_gaps:
            st.markdown("#### Trust and evidence gaps")
            for gap in evidence_gaps:
                st.write(f"- {gap}")

        if full_coverage_recommendations:
            st.markdown("#### Local full-coverage plan details")
            _render_plan_details(full_coverage_recommendations)
        if partial_fallback_recommendations:
            st.markdown("#### Local fallback plan details")
            _render_plan_details(partial_fallback_recommendations)
        if comparison_recommendations:
            st.markdown("#### Comparison-only plan details")
            _render_plan_details(comparison_recommendations)
        if not combined_frame.empty:
            st.download_button(
                "Download recommendation report (CSV)",
                data=serialize_nested_columns(combined_frame).to_csv(index=False),
                file_name="cms_mpd_recommendations.csv",
                mime="text/csv",
            )
        if audit is not None:
            st.download_button(
                "Download audit record (JSON)",
                data=json.dumps(audit, indent=2),
                file_name="cms_mpd_recommendation_audit.json",
                mime="application/json",
            )
        with st.expander("Structured input contract"):
            st.json(public_contract)
        with st.expander("Audit payload"):
            st.json(audit)


if __name__ == "__main__":
    main()
