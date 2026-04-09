"""Shared counselor-workflow helpers for the Streamlit app."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import math

import pandas as pd

from .decision_support import (
    MedicationListItem,
    PreferenceWeights,
    ProfileInput,
    recommend_preference_preset,
)
from .recommend import MedicationInput, PlanDrugBreakdown, PlanRecommendation


DEFAULT_MEDICATION_ROWS = [
    {
        "drug_name": "albuterol 0.21 MG/ML Inhalation Solution",
        "rxcui": "",
        "ndc": "",
        "tier_family": "generic",
        "day_supply": 30,
        "quantity_override": None,
        "fills_per_year_override": None,
    },
    {
        "drug_name": "insulin glargine",
        "rxcui": "",
        "ndc": "",
        "tier_family": "brand",
        "day_supply": 30,
        "quantity_override": None,
        "fills_per_year_override": None,
    },
]

PERSONA_OPTIONS = ["Beneficiary", "Caregiver", "Counselor"]
CHRONIC_FLAG_OPTIONS = ["diabetes", "asthma", "copd", "heart_failure", "kidney_disease"]
PRIMARY_GOALS = [
    "Balanced recommendation",
    "Lowest annual cost",
    "Safest medication coverage",
    "Easiest pharmacy access",
    "Conservative compare and verify",
]
SUPPORTED_TIER_FAMILY_OPTIONS = ("generic", "brand", "specialty")
ROLE_MAP = {
    "Beneficiary": "beneficiary",
    "Caregiver": "caregiver",
    "Counselor": "counselor",
}
CHANNEL_LABELS = {
    "pref_retail": "preferred retail",
    "nonpref_retail": "non-preferred retail",
    "pref_mail": "preferred mail",
    "nonpref_mail": "non-preferred mail",
    "unavailable": "unavailable",
}
MONTH_LABELS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FOCUS_MAP = {
    "Balanced recommendation": "balanced",
    "Lowest annual cost": "lowest_total_cost",
    "Safest medication coverage": "coverage_first",
    "Easiest pharmacy access": "pharmacy_access",
    "Conservative compare and verify": "low_friction",
}


@dataclass(frozen=True)
class WhatIfScenario:
    key: str
    label: str
    description: str
    profile: ProfileInput
    preferences: PreferenceWeights


def coerce_zipcode(value: str | None) -> str:
    return "".join(char for char in str(value or "") if char.isdigit())[:5]


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 3959.0
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlng / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def parse_medication_frame(
    frame: pd.DataFrame,
) -> tuple[list[MedicationInput], list[dict], list[str]]:
    medications: list[MedicationInput] = []
    contract_rows: list[dict] = []
    errors: list[str] = []
    for index, row in frame.fillna("").iterrows():
        drug_name = str(row.get("drug_name", "")).strip()
        rxcui = str(row.get("rxcui", "")).strip()
        ndc = str(row.get("ndc", "")).strip()
        tier_family = str(row.get("tier_family", "")).strip().lower() or None
        if not any([drug_name, rxcui, ndc]):
            continue
        try:
            day_supply = int(float(str(row.get("day_supply", "")).strip() or 0))
        except ValueError:
            errors.append(f"Medication row {index + 1}: invalid day_supply.")
            continue
        if day_supply not in {30, 60, 90}:
            errors.append(f"Medication row {index + 1}: day_supply must be 30, 60, or 90.")
            continue
        try:
            quantity_override = (
                float(str(row.get("quantity_override", "")).strip())
                if str(row.get("quantity_override", "")).strip()
                else None
            )
        except ValueError:
            errors.append(f"Medication row {index + 1}: invalid quantity_override.")
            continue
        try:
            fills_override = (
                int(float(str(row.get("fills_per_year_override", "")).strip()))
                if str(row.get("fills_per_year_override", "")).strip()
                else None
            )
        except ValueError:
            errors.append(f"Medication row {index + 1}: invalid fills_per_year_override.")
            continue
        item = MedicationInput(
            drug_name=drug_name or None,
            rxcui=rxcui or None,
            ndc=ndc or None,
            tier_family=tier_family,
            day_supply=day_supply,
            quantity_override=quantity_override,
            fills_per_year_override=fills_override,
        )
        medications.append(item)
        contract_rows.append(
            asdict(
                MedicationListItem(
                    drug_name=drug_name or ndc or rxcui,
                    rxcui=rxcui or None,
                    ndc=ndc or None,
                    tier_family=tier_family,
                    day_supply=day_supply,
                    quantity_override=quantity_override,
                    fills_per_year_override=fills_override,
                )
            )
        )
    if not medications:
        errors.append("Add at least one medication before running decision support.")
    return medications, contract_rows, errors


def _coerce_catalog_option_list(values: object) -> list[object]:
    if values is None:
        return []
    if isinstance(values, list):
        raw_values = values
    elif isinstance(values, tuple):
        raw_values = list(values)
    elif hasattr(values, "tolist") and not isinstance(values, str):
        converted = values.tolist()
        raw_values = converted if isinstance(converted, list) else [converted]
    elif isinstance(values, str):
        raw_values = [part.strip() for part in values.split(",") if part.strip()]
    else:
        try:
            if pd.isna(values):
                return []
        except (TypeError, ValueError):
            pass
        raw_values = [values]
    return [value for value in raw_values if value not in {None, ""}]


def catalog_available_day_supply_options(row: pd.Series | dict) -> list[int]:
    values = row if isinstance(row, dict) else row.to_dict()
    parsed: list[int] = []
    for value in _coerce_catalog_option_list(values.get("available_day_supply_options")):
        try:
            parsed.append(int(float(value)))
        except (TypeError, ValueError):
            continue
    normalized = sorted({value for value in parsed if value in {30, 60, 90}})
    if normalized:
        return normalized
    try:
        fallback = int(values.get("default_day_supply") or 30)
    except (TypeError, ValueError):
        fallback = 30
    return [fallback if fallback in {30, 60, 90} else 30]


def catalog_tier_family_options(row: pd.Series | dict) -> list[str]:
    values = row if isinstance(row, dict) else row.to_dict()
    parsed = [
        str(value).strip().lower()
        for value in _coerce_catalog_option_list(values.get("available_tier_family_options"))
        if str(value).strip().lower() in SUPPORTED_TIER_FAMILY_OPTIONS
    ]
    if not parsed:
        fallback = str(values.get("tier_family") or "brand").strip().lower() or "brand"
        parsed = [fallback if fallback in SUPPORTED_TIER_FAMILY_OPTIONS else "brand"]
    return [option for option in SUPPORTED_TIER_FAMILY_OPTIONS if option in set(parsed)]


def search_drug_catalog(
    catalog: pd.DataFrame,
    query: str,
    *,
    limit: int = 25,
) -> pd.DataFrame:
    if catalog.empty:
        return catalog.copy()

    working = catalog.copy()
    normalized_query = str(query or "").strip().lower()
    if normalized_query:
        tokens = [token for token in normalized_query.split() if token]
        search_text = (
            working["drug_name"].fillna("").str.lower()
            + " "
            + working["drug_synonym"].fillna("").str.lower()
            + " "
            + working["rxcui"].fillna("").astype(str).str.lower()
            + " "
            + working["ndc"].fillna("").astype(str).str.lower()
        )
        mask = pd.Series(True, index=working.index)
        for token in tokens:
            mask &= search_text.str.contains(token, regex=False)
        working = working[mask].copy()
        if working.empty:
            return working

        name_starts = working["drug_name"].fillna("").str.lower().str.startswith(normalized_query)
        synonym_starts = working["drug_synonym"].fillna("").str.lower().str.startswith(normalized_query)
        name_contains = working["drug_name"].fillna("").str.lower().str.contains(normalized_query, regex=False)
        synonym_contains = working["drug_synonym"].fillna("").str.lower().str.contains(normalized_query, regex=False)
        exact_code = (
            (working["rxcui"].fillna("").astype(str).str.lower() == normalized_query)
            | (working["ndc"].fillna("").astype(str).str.lower() == normalized_query)
        )
        working["_match_score"] = (
            exact_code.astype(int) * 100
            + name_starts.astype(int) * 50
            + synonym_starts.astype(int) * 30
            + name_contains.astype(int) * 20
            + synonym_contains.astype(int) * 10
        )
        working = working.sort_values(
            ["_match_score", "plan_coverage", "drug_name", "ndc"],
            ascending=[False, False, True, True],
        )
    else:
        working = working.sort_values(["plan_coverage", "drug_name", "ndc"], ascending=[False, True, True])
    return working.head(max(1, int(limit))).drop(columns="_match_score", errors="ignore").reset_index(drop=True)


def format_drug_catalog_option(row: pd.Series | dict) -> str:
    if isinstance(row, dict):
        values = row
    else:
        values = row.to_dict()
    drug_name = str(values.get("drug_name") or values.get("ndc") or "Unknown drug")
    default_day_supply = int(values.get("default_day_supply") or 30)
    available_day_supplies = "/".join(str(value) for value in catalog_available_day_supply_options(values))
    tier_family_options = ", ".join(catalog_tier_family_options(values))
    insulin_tag = " | insulin" if bool(values.get("is_insulin")) else ""
    coverage = int(values.get("plan_coverage") or 0)
    rxcui = str(values.get("rxcui") or "")
    return (
        f"{drug_name} | {coverage:,} plans | days {available_day_supplies} | tiers {tier_family_options} | "
        f"{default_day_supply}-day default{insulin_tag}"
        + (f" | RXCUI {rxcui}" if rxcui else "")
    )


def build_medication_row_from_catalog(
    row: pd.Series | dict,
    *,
    day_supply: int | None = None,
    tier_family: str | None = None,
) -> dict:
    values = row if isinstance(row, dict) else row.to_dict()
    selected_day_supply = int(day_supply or values.get("default_day_supply") or 30)
    if selected_day_supply not in {30, 60, 90}:
        selected_day_supply = 30 if selected_day_supply < 45 else (60 if selected_day_supply < 75 else 90)
    available_tier_families = catalog_tier_family_options(values)
    requested_tier_family = str(tier_family or values.get("tier_family") or "brand").strip().lower() or "brand"
    if requested_tier_family not in available_tier_families:
        requested_tier_family = available_tier_families[0]
    return {
        "drug_name": str(values.get("drug_name") or values.get("ndc") or "").strip(),
        "rxcui": str(values.get("rxcui") or "").strip(),
        "ndc": str(values.get("ndc") or "").strip(),
        "tier_family": requested_tier_family or None,
        "day_supply": selected_day_supply,
        "quantity_override": None,
        "fills_per_year_override": None,
    }


def append_medication_row(rows: list[dict], new_row: dict) -> list[dict]:
    updated = [dict(row) for row in rows]
    updated.append(dict(new_row))
    return updated


def _stringify_list(values: object) -> str:
    if isinstance(values, list):
        return "; ".join(str(value) for value in values if value)
    if pd.isna(values):
        return ""
    return str(values)


def _channel_label(channel: str) -> str:
    return CHANNEL_LABELS.get(str(channel), str(channel).replace("_", " "))


def summarize_drug_channel_path(breakdown: PlanDrugBreakdown) -> str:
    if not breakdown.fill_traces:
        if breakdown.pricing_status != "priced":
            return f"No priced fills were simulated ({breakdown.pricing_status.replace('_', ' ')})."
        return "No fill-level timeline is available."

    ordered_traces = sorted(
        breakdown.fill_traces,
        key=lambda item: (item.sequence_index, item.day_offset, item.fill_number),
    )
    condensed_channels: list[str] = []
    for trace in ordered_traces:
        channel = str(trace.selected_channel)
        if not condensed_channels or condensed_channels[-1] != channel:
            condensed_channels.append(channel)

    switch_count = max(0, len(condensed_channels) - 1)
    if switch_count == 0:
        return (
            f"Stable {_channel_label(condensed_channels[0])} path across "
            f"{len(ordered_traces)} fill(s)."
        )
    return (
        f"Switches {switch_count} time(s): "
        + " -> ".join(_channel_label(channel) for channel in condensed_channels)
    )


def build_monthly_timeline_frame(recommendation: PlanRecommendation) -> pd.DataFrame:
    monthly_premium = float(recommendation.annual_premium) / 12.0
    month_rows = [
        {
            "Month": MONTH_LABELS[month_index - 1],
            "Month number": month_index,
            "Drug OOP": 0.0,
            "Deductible applied": 0.0,
            "Monthly premium": monthly_premium,
            "Projected monthly total": monthly_premium,
            "Cumulative drug OOP": 0.0,
            "Cumulative total": 0.0,
            "Fill count": 0,
            "Filled drugs": [],
        }
        for month_index in range(1, 13)
    ]

    for breakdown in recommendation.drug_breakdowns:
        for trace in breakdown.fill_traces:
            month_index = max(1, min(12, int(trace.day_offset // 30) + 1))
            row = month_rows[month_index - 1]
            row["Drug OOP"] += float(trace.final_oop)
            row["Deductible applied"] += float(trace.deductible_applied)
            row["Projected monthly total"] += float(trace.final_oop)
            row["Fill count"] += 1
            if breakdown.drug_name not in row["Filled drugs"]:
                row["Filled drugs"].append(str(breakdown.drug_name))

    cumulative_drug_oop = 0.0
    cumulative_total = 0.0
    normalized_rows: list[dict[str, object]] = []
    for row in month_rows:
        cumulative_drug_oop += float(row["Drug OOP"])
        cumulative_total += float(row["Projected monthly total"])
        normalized_rows.append(
            {
                "Month": row["Month"],
                "Month number": int(row["Month number"]),
                "Drug OOP": round(float(row["Drug OOP"]), 2),
                "Deductible applied": round(float(row["Deductible applied"]), 2),
                "Monthly premium": round(float(row["Monthly premium"]), 2),
                "Projected monthly total": round(float(row["Projected monthly total"]), 2),
                "Cumulative drug OOP": round(cumulative_drug_oop, 2),
                "Cumulative total": round(cumulative_total, 2),
                "Fill count": int(row["Fill count"]),
                "Filled drugs": ", ".join(row["Filled drugs"]),
            }
        )
    return pd.DataFrame(normalized_rows)


def build_what_if_scenarios(
    profile: ProfileInput,
    preferences: PreferenceWeights,
    *,
    has_medications: bool,
) -> list[WhatIfScenario]:
    scenarios: list[WhatIfScenario] = []

    pharmacy_variants = [
        (
            "auto",
            "Allow auto channel choice",
            "Let the engine keep choosing the most plan-friendly available channel mix.",
        ),
        (
            "retail",
            "Prefer retail pickup",
            "Assume the beneficiary wants local retail pickup whenever the plan allows it.",
        ),
        (
            "mail",
            "Prefer mail order",
            "Assume the beneficiary is willing to lean on mail order when it helps the plan fit.",
        ),
    ]
    for pharmacy_preference, label, description in pharmacy_variants:
        if profile.pharmacy_preference == pharmacy_preference:
            continue
        scenarios.append(
            WhatIfScenario(
                key=f"pharmacy_{pharmacy_preference}",
                label=label,
                description=description,
                profile=replace(profile, pharmacy_preference=pharmacy_preference),
                preferences=preferences,
            )
        )

    lis_variants = [
        ("partial", "Assume partial LIS", "Model the same regimen with partial LIS cost-sharing support."),
        ("full", "Assume full LIS", "Model the same regimen with full LIS cost-sharing support."),
    ]
    for lis_status, label, description in lis_variants:
        if profile.lis_status == lis_status:
            continue
        scenarios.append(
            WhatIfScenario(
                key=f"lis_{lis_status}",
                label=label,
                description=description,
                profile=replace(profile, lis_status=lis_status),
                preferences=preferences,
            )
        )

    goal_variants = [
        ("Lowest annual cost", "Optimize for lowest annual cost"),
        ("Safest medication coverage", "Optimize for safest medication coverage"),
        ("Easiest pharmacy access", "Optimize for easiest pharmacy access"),
    ]
    for primary_goal, label in goal_variants:
        if preferences.primary_goal == primary_goal:
            continue
        preset = recommend_preference_preset(profile.persona, primary_goal, has_medications)
        scenarios.append(
            WhatIfScenario(
                key=f"goal_{primary_goal.lower().replace(' ', '_')}",
                label=label,
                description=(
                    f"Keep the beneficiary profile the same, but change the shortlist posture to {primary_goal.lower()}."
                ),
                profile=profile,
                preferences=replace(
                    preferences,
                    primary_goal=primary_goal,
                    minimum_coverage_pct=float(preset["minimum_coverage_pct"]),
                ),
            )
        )

    deduped: list[WhatIfScenario] = []
    seen: set[str] = set()
    for scenario in scenarios:
        if scenario.key in seen:
            continue
        deduped.append(scenario)
        seen.add(scenario.key)
    return deduped


def build_what_if_summary_frame(
    baseline_frame: pd.DataFrame,
    scenario_runs: list[tuple[WhatIfScenario, pd.DataFrame]],
) -> pd.DataFrame:
    columns = [
        "Scenario",
        "Assumption change",
        "Top plan",
        "Top plan changed",
        "Estimated annual total cost",
        "Delta vs baseline top plan",
        "Estimated annual OOP",
        "Coverage percent",
        "Priced medications",
        "Channel switches",
        "Recommendation tier",
        "Ranking source",
    ]
    if baseline_frame is None or baseline_frame.empty:
        return pd.DataFrame(columns=columns)

    baseline_top = baseline_frame.iloc[0]
    baseline_plan_key = str(baseline_top.get("PLAN_KEY") or "")
    baseline_total_cost = float(baseline_top.get("estimated_total_annual_cost") or 0.0)
    rows: list[dict[str, object]] = []
    for scenario, frame in scenario_runs:
        if frame is None or frame.empty:
            rows.append(
                {
                    "Scenario": scenario.label,
                    "Assumption change": scenario.description,
                    "Top plan": "No eligible plan returned",
                    "Top plan changed": "n/a",
                    "Estimated annual total cost": None,
                    "Delta vs baseline top plan": None,
                    "Estimated annual OOP": None,
                    "Coverage percent": None,
                    "Priced medications": 0,
                    "Channel switches": 0,
                    "Recommendation tier": "No eligible plan returned",
                    "Ranking source": "",
                }
            )
            continue

        top = frame.iloc[0]
        top_plan_key = str(top.get("PLAN_KEY") or "")
        total_cost = float(top.get("estimated_total_annual_cost") or 0.0)
        rows.append(
            {
                "Scenario": scenario.label,
                "Assumption change": scenario.description,
                "Top plan": str(top.get("PLAN_NAME") or top_plan_key or "Unknown plan"),
                "Top plan changed": "Changed" if top_plan_key != baseline_plan_key else "Stable",
                "Estimated annual total cost": round(total_cost, 2),
                "Delta vs baseline top plan": round(total_cost - baseline_total_cost, 2),
                "Estimated annual OOP": round(float(top.get("estimated_annual_oop") or 0.0), 2),
                "Coverage percent": round(float(top.get("coverage_pct_requested") or 0.0), 2),
                "Priced medications": int(top.get("priced_drug_count") or 0),
                "Channel switches": int(top.get("channel_switch_count") or 0),
                "Recommendation tier": str(top.get("recommendation_tier") or ""),
                "Ranking source": str(top.get("ranking_source") or ""),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def summarize_what_if_findings(summary_frame: pd.DataFrame) -> str:
    if summary_frame is None or summary_frame.empty:
        return "Run one or more what-if scenarios to compare how alternate beneficiary assumptions shift the shortlist."

    changed_count = int((summary_frame["Top plan changed"] == "Changed").sum())
    total_count = int(len(summary_frame))
    numeric_costs = summary_frame["Estimated annual total cost"].dropna()
    if numeric_costs.empty:
        return "The selected what-if scenarios did not return any eligible plans."

    lowest_index = numeric_costs.astype(float).idxmin()
    lowest_row = summary_frame.loc[lowest_index]
    if changed_count == 0:
        return (
            f"The top eligible plan stayed stable across all {total_count} what-if scenario(s). "
            f"The lowest alternate cost still came from {lowest_row['Scenario']} at "
            f"${float(lowest_row['Estimated annual total cost']):,.0f}."
        )
    return (
        f"{changed_count} of {total_count} what-if scenario(s) changed the top eligible plan. "
        f"The lowest alternate cost came from {lowest_row['Scenario']} at "
        f"${float(lowest_row['Estimated annual total cost']):,.0f}."
    )


def build_side_by_side_frame(
    frame: pd.DataFrame,
    selected_plan_keys: list[str] | None = None,
    *,
    max_plans: int = 3,
) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["Metric"])

    selected = frame.drop_duplicates("PLAN_KEY").copy()
    if selected_plan_keys:
        selected = selected[selected["PLAN_KEY"].isin(selected_plan_keys)]
    if selected.empty:
        selected = frame.drop_duplicates("PLAN_KEY").head(max_plans).copy()
    else:
        selected = selected.head(max_plans).copy()

    metrics = [
        ("Recommendation tier", "recommendation_tier"),
        ("Eligibility", "eligibility_status"),
        ("Annual total cost", "estimated_total_annual_cost"),
        ("Annual premium", "annual_premium"),
        ("Annual drug OOP", "annual_drug_oop"),
        ("Coverage percent", "coverage_pct_requested"),
        ("Coverage status", "coverage_status"),
        ("Uncovered drugs", "uncovered_drug_count"),
        ("Priced medications", "priced_drug_count"),
        ("Restriction summary", "restriction_summary"),
        ("Network flag", "network_flag"),
        ("Preferred distance", "nearest_preferred_distance_miles"),
        ("Channel mix", "selected_channel_mix"),
        ("Channel switches", "channel_switch_count"),
        ("Simulation policy", "simulation_policy"),
        ("Confidence", "confidence_band"),
        ("Decision score", "decision_score"),
        ("Rules score", "rules_score"),
        ("Ranking source", "ranking_source"),
        ("Warnings", "warning_flags"),
        ("Evidence gaps", "evidence_gaps"),
    ]

    rows: list[dict[str, str]] = []
    for label, column in metrics:
        metric_row: dict[str, str] = {"Metric": label}
        for _, item in selected.iterrows():
            plan_name = str(item["PLAN_NAME"])
            value = item.get(column)
            if column in {"estimated_total_annual_cost", "annual_premium", "annual_drug_oop"} and value is not None:
                metric_row[plan_name] = f"${float(value):,.2f}"
            elif column == "coverage_pct_requested" and value is not None:
                metric_row[plan_name] = f"{float(value):.1f}%"
            elif column == "decision_score" and value is not None:
                metric_row[plan_name] = f"{float(value):.1f}"
            elif column == "rules_score" and value is not None:
                metric_row[plan_name] = f"{float(value):.2f}"
            elif column in {"uncovered_drug_count", "priced_drug_count", "channel_switch_count"} and value is not None:
                metric_row[plan_name] = f"{int(value)}"
            elif column == "nearest_preferred_distance_miles":
                metric_row[plan_name] = (
                    "n/a" if value is None or pd.isna(value) else f"{float(value):.1f} miles"
                )
            else:
                metric_row[plan_name] = _stringify_list(value)
        rows.append(metric_row)
    return pd.DataFrame(rows)


def summarize_evidence_gaps(*frames: pd.DataFrame) -> list[str]:
    gaps: list[str] = []
    for frame in frames:
        if frame is None or frame.empty or "evidence_gaps" not in frame.columns:
            continue
        for values in frame["evidence_gaps"].tolist():
            if not isinstance(values, list):
                continue
            for gap in values:
                if gap and gap not in gaps:
                    gaps.append(str(gap))
    return gaps


def build_counselor_note(
    profile: ProfileInput,
    preferences: PreferenceWeights,
    eligible_frame: pd.DataFrame,
    comparison_frame: pd.DataFrame | None = None,
) -> str:
    comparison_frame = comparison_frame if comparison_frame is not None else pd.DataFrame()
    if eligible_frame.empty:
        return "No eligible plans were returned for this ZIP and medication list."

    top = eligible_frame.iloc[0]
    note_parts = [
        f"{profile.persona} workflow prioritized {preferences.primary_goal.lower()}.",
        (
            f"Top eligible option is {top['PLAN_NAME']} with about "
            f"${float(top['estimated_total_annual_cost']):,.0f} annual total cost "
            f"and {float(top['coverage_pct_requested']):.0f}% requested-drug coverage."
        ),
    ]

    if len(eligible_frame) > 1:
        next_best = eligible_frame.iloc[1]
        delta = float(next_best["estimated_total_annual_cost"]) - float(top["estimated_total_annual_cost"])
        note_parts.append(
            f"It is about ${delta:,.0f} lower than the next eligible option in this run."
        )

    priced_drug_count = top.get("priced_drug_count")
    if priced_drug_count is not None and not pd.isna(priced_drug_count):
        note_parts.append(
            f"{int(priced_drug_count)} entered medication(s) were fully priceable in the simulated path."
        )

    channel_switch_count = top.get("channel_switch_count")
    if channel_switch_count is not None and not pd.isna(channel_switch_count):
        channel_switch_count = int(channel_switch_count)
        if channel_switch_count > 0:
            note_parts.append(
                f"The projected yearly fill path switches pharmacy channels {channel_switch_count} time(s)."
            )
        else:
            note_parts.append("The projected yearly fill path stays on a stable pharmacy channel pattern.")

    warning_flags = top.get("warning_flags") or []
    if isinstance(warning_flags, list) and warning_flags:
        note_parts.append(f"Key watchouts: {'; '.join(str(item) for item in warning_flags[:3])}.")

    if not comparison_frame.empty:
        note_parts.append(
            f"{len(comparison_frame)} nearby comparison-only plan(s) were also surfaced for context."
        )

    evidence_gaps = summarize_evidence_gaps(eligible_frame.head(3), comparison_frame.head(3))
    if evidence_gaps:
        note_parts.append(f"Evidence gaps to review: {'; '.join(evidence_gaps[:3])}.")

    return " ".join(note_parts)


__all__ = [
    "CHRONIC_FLAG_OPTIONS",
    "DEFAULT_MEDICATION_ROWS",
    "FOCUS_MAP",
    "PERSONA_OPTIONS",
    "PRIMARY_GOALS",
    "ROLE_MAP",
    "append_medication_row",
    "build_medication_row_from_catalog",
    "build_counselor_note",
    "build_monthly_timeline_frame",
    "build_side_by_side_frame",
    "build_what_if_scenarios",
    "build_what_if_summary_frame",
    "catalog_available_day_supply_options",
    "catalog_tier_family_options",
    "coerce_zipcode",
    "format_drug_catalog_option",
    "haversine_miles",
    "parse_medication_frame",
    "search_drug_catalog",
    "summarize_drug_channel_path",
    "summarize_evidence_gaps",
    "summarize_what_if_findings",
    "WhatIfScenario",
]
