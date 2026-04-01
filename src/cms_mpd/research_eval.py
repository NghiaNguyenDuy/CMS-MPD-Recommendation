"""Research-mode helpers built on the hybrid training dataset and evaluation report."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .config import PipelineConfig
from .modeling import build_training_dataset, evaluate_hybrid_reranker


def ensure_research_artifacts(
    config: PipelineConfig | None = None,
    *,
    scenario_bundles: list[str] | None = None,
    baseline_only: bool = False,
) -> tuple[pd.DataFrame, dict]:
    active_config = config or PipelineConfig()
    dataset_path = active_config.training_dataset_path
    if not dataset_path.exists():
        build_training_dataset(active_config, scenario_bundles=scenario_bundles)
    frame = pd.read_csv(dataset_path)
    if scenario_bundles:
        frame = frame[frame["scenario_bundle"].isin(scenario_bundles)].copy()
    report = evaluate_hybrid_reranker(
        config=active_config,
        dataset_path=dataset_path,
        scenario_bundles=scenario_bundles,
        baseline_only=baseline_only,
    )
    return frame, report


def systems_summary_frame(report: dict) -> pd.DataFrame:
    rows: list[dict] = []
    for system_name, metrics in (report.get("systems") or {}).items():
        row = {"system": system_name}
        row.update(metrics)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("system").reset_index(drop=True) if rows else pd.DataFrame()


def scenario_bundle_frames(report: dict) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for bundle_name, bundle_metrics in (report.get("scenario_bundle_metrics") or {}).items():
        rows: list[dict] = []
        for system_name, metrics in bundle_metrics.items():
            row = {"system": system_name}
            row.update(metrics)
            rows.append(row)
        frames[bundle_name] = pd.DataFrame(rows).sort_values("system").reset_index(drop=True) if rows else pd.DataFrame()
    return frames


def dataset_diagnostics_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=["metric", "value"])
    metrics = [
        ("Rows", int(len(frame))),
        ("Scenarios", int(frame["scenario_id"].nunique())),
        ("Bundles", int(frame["scenario_bundle"].nunique())),
        ("Plans", int(frame["plan_key"].nunique())),
        ("Average annual total cost", round(float(frame["annual_total_cost"].mean()), 2)),
        ("Average covered share", round(float(frame["covered_drug_share"].mean() * 100.0), 2)),
        ("Average uncovered count", round(float(frame["uncovered_drug_count"].mean()), 2)),
        ("Average restriction count", round(float(frame["restriction_count"].mean()), 2)),
        ("Average network risk score", round(float(frame["network_risk_score"].mean()), 2)),
    ]
    return pd.DataFrame(metrics, columns=["metric", "value"])


def subgroup_frames(frame: pd.DataFrame) -> dict[str, pd.DataFrame]:
    if frame.empty:
        return {}

    def summarize(column: str) -> pd.DataFrame:
        summary = (
            frame.groupby(column, dropna=False)
            .agg(
                scenarios=("scenario_id", "nunique"),
                plans=("plan_key", "nunique"),
                avg_total_cost=("annual_total_cost", "mean"),
                avg_covered_share=("covered_drug_share", "mean"),
                avg_uncovered=("uncovered_drug_count", "mean"),
                avg_network_risk=("network_risk_score", "mean"),
            )
            .reset_index()
        )
        return summary.sort_values("scenarios", ascending=False).reset_index(drop=True)

    available: dict[str, str] = {
        "scenario_bundle": "Scenario bundle",
        "lis_status": "LIS status",
        "age_band": "Age band",
        "pharmacy_preference": "Pharmacy preference",
        "zip_density_category": "ZIP density",
        "coverage_status": "Coverage status",
    }
    return {
        label: summarize(column)
        for column, label in available.items()
        if column in frame.columns
    }


def load_report_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
