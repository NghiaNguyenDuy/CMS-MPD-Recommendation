"""Shared counselor-workflow helpers for the Streamlit app."""

from __future__ import annotations

from dataclasses import asdict
import math

import pandas as pd

from .decision_support import MedicationListItem, PreferenceWeights, ProfileInput
from .recommend import MedicationInput


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
ROLE_MAP = {
    "Beneficiary": "beneficiary",
    "Caregiver": "caregiver",
    "Counselor": "counselor",
}
FOCUS_MAP = {
    "Balanced recommendation": "balanced",
    "Lowest annual cost": "lowest_total_cost",
    "Safest medication coverage": "coverage_first",
    "Easiest pharmacy access": "pharmacy_access",
    "Conservative compare and verify": "low_friction",
}


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
    tier_family = str(values.get("tier_family") or "brand")
    default_day_supply = int(values.get("default_day_supply") or 30)
    insulin_tag = " | insulin" if bool(values.get("is_insulin")) else ""
    coverage = int(values.get("plan_coverage") or 0)
    rxcui = str(values.get("rxcui") or "")
    return (
        f"{drug_name} | {tier_family} | {default_day_supply}-day default | "
        f"{coverage:,} plans{insulin_tag}"
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
    return {
        "drug_name": str(values.get("drug_name") or values.get("ndc") or "").strip(),
        "rxcui": str(values.get("rxcui") or "").strip(),
        "ndc": str(values.get("ndc") or "").strip(),
        "tier_family": str(tier_family or values.get("tier_family") or "brand").strip().lower() or None,
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
        ("Estimated annual OOP", "estimated_annual_oop"),
        ("Coverage percent", "coverage_pct_requested"),
        ("Coverage status", "coverage_status"),
        ("Confidence", "confidence_band"),
        ("Decision score", "decision_score"),
        ("Rules score", "rules_score"),
        ("Ranking source", "ranking_source"),
        ("Network flag", "network_flag"),
        ("Preferred distance", "nearest_preferred_distance_miles"),
        ("Warnings", "warning_flags"),
        ("Evidence gaps", "evidence_gaps"),
    ]

    rows: list[dict[str, str]] = []
    for label, column in metrics:
        metric_row: dict[str, str] = {"Metric": label}
        for _, item in selected.iterrows():
            plan_name = str(item["PLAN_NAME"])
            value = item.get(column)
            if column in {"estimated_total_annual_cost", "estimated_annual_oop"} and value is not None:
                metric_row[plan_name] = f"${float(value):,.2f}"
            elif column == "coverage_pct_requested" and value is not None:
                metric_row[plan_name] = f"{float(value):.1f}%"
            elif column == "decision_score" and value is not None:
                metric_row[plan_name] = f"{float(value):.1f}"
            elif column == "rules_score" and value is not None:
                metric_row[plan_name] = f"{float(value):.2f}"
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
    "build_side_by_side_frame",
    "coerce_zipcode",
    "format_drug_catalog_option",
    "haversine_miles",
    "parse_medication_frame",
    "search_drug_catalog",
    "summarize_evidence_gaps",
]
