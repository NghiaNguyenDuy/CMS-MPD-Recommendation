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

from cms_mpd import BeneficiaryInput, PipelineConfig, recommend_plans
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
    catalog_available_day_supply_options,
    catalog_tier_family_options,
    coerce_zipcode,
    format_drug_catalog_option,
    haversine_miles,
    parse_medication_frame,
    search_drug_catalog,
    summarize_drug_channel_path,
    summarize_evidence_gaps,
)
from cms_mpd.decision_support import (
    MedicationListItem,
    PreferenceWeights,
    ProfileInput,
    as_public_types,
    create_run_audit,
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
                beneficiary = BeneficiaryInput(
                    zipcode=profile_contract.zipcode,
                    age_band=profile_contract.age_band,
                    lis_status=profile_contract.lis_status,
                    chronic_condition_flags=profile_contract.chronic_condition_flags or None,
                    pharmacy_preference=profile_contract.pharmacy_preference,
                    top_n=profile_contract.top_n,
                    user_role=ROLE_MAP[profile_contract.persona],
                    decision_focus=FOCUS_MAP[preference_contract.primary_goal],
                )
                with st.spinner("Running recommendation engine and comparison workflow..."):
                    recommendations = recommend_plans(
                        beneficiary,
                        medications,
                        config=config,
                        ranking_mode=preference_contract.ranking_mode,
                    )
                    comparison_recs = []
                    if preference_contract.allow_comparison_plans and recommendations:
                        comparison_recs = _comparison_recommendations(
                            config,
                            beneficiary,
                            medications,
                            max_distance_miles=preference_contract.max_comparison_distance_miles,
                            local_plan_keys={row.plan_key for row in recommendations},
                        )

                run_id = uuid.uuid4().hex[:12]
                result_df = recommendations_to_dataframe(
                    recommendations,
                    run_id=run_id,
                    comparison_only=False,
                    minimum_coverage_pct=preference_contract.minimum_coverage_pct,
                )
                comparison_df = recommendations_to_dataframe(
                    comparison_recs,
                    run_id=run_id,
                    comparison_only=True,
                    minimum_coverage_pct=preference_contract.minimum_coverage_pct,
                )
                feature_coverage = summarize_feature_coverage(recommendations, comparison_recs)
                public_contract = as_public_types(
                    profile_contract,
                    [MedicationListItem(**row) for row in st.session_state.get("medication_contract_rows", [])],
                    preference_contract,
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
                    recommendations=pd.concat([result_df, comparison_df], ignore_index=True),
                    run_id=run_id,
                )
                st.session_state["result_df"] = result_df
                st.session_state["comparison_df"] = comparison_df
                st.session_state["audit"] = asdict(audit)
                st.session_state["public_contract"] = public_contract
                st.session_state["recommendations"] = recommendations
                st.session_state["comparison_recommendations"] = comparison_recs
                st.session_state["counselor_note"] = build_counselor_note(
                    profile_contract,
                    preference_contract,
                    result_df,
                    comparison_df,
                )

        result_df = st.session_state.get("result_df")
        comparison_df = st.session_state.get("comparison_df", pd.DataFrame())
        audit = st.session_state.get("audit")
        public_contract = st.session_state.get("public_contract")
        recommendations = st.session_state.get("recommendations", [])
        comparison_recommendations = st.session_state.get("comparison_recommendations", [])
        counselor_note = st.session_state.get("counselor_note")
        if result_df is None or result_df.empty:
            st.info("Complete the first three steps, then run decision support to generate a shortlist.")
            return

        _render_metric_cards(result_df)
        st.markdown("#### Eligible shortlist")
        st.dataframe(result_df.head(10), use_container_width=True, hide_index=True)
        if not comparison_df.empty:
            st.markdown("#### Nearby comparison-only plans")
            st.dataframe(comparison_df.head(5), use_container_width=True, hide_index=True)
        combined_frame = pd.concat([result_df, comparison_df], ignore_index=True)
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

        evidence_gaps = summarize_evidence_gaps(result_df, comparison_df)
        if evidence_gaps:
            st.markdown("#### Trust and evidence gaps")
            for gap in evidence_gaps:
                st.write(f"- {gap}")

        st.markdown("#### Eligible plan details")
        _render_plan_details(recommendations)
        if comparison_recommendations:
            st.markdown("#### Comparison-only plan details")
            _render_plan_details(comparison_recommendations)
        st.download_button(
            "Download recommendation report (CSV)",
            data=serialize_nested_columns(combined_frame).to_csv(index=False),
            file_name="cms_mpd_recommendations.csv",
            mime="text/csv",
        )
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
