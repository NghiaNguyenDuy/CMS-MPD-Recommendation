from __future__ import annotations

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from .config import BENEFIT_DESIGN_MODES, PipelineConfig
from .decision_support import recommendation_bundle_to_public_payload
from .modeling import build_training_dataset, evaluate_hybrid_reranker, train_hybrid_reranker
from .pipeline import health_check, run_pipeline
from .recommend import BeneficiaryInput, MedicationInput, recommend_plan_bundle, recommend_plans
from .scenario_generation import generate_training_scenarios


def _add_config_arguments(
    parser: argparse.ArgumentParser,
    *,
    include_demo_zipcode: bool = False,
) -> None:
    parser.add_argument("--build-profile", default="full", choices=["full", "demo"])
    parser.add_argument("--benefit-design-mode", default="auto", choices=list(BENEFIT_DESIGN_MODES))
    parser.add_argument("--snapshot-quarter", default="2025-Q3")
    parser.add_argument(
        "--data-dir",
        help="Optional output data directory for DuckDB, staged files, models, and training assets",
    )
    parser.add_argument(
        "--source-data-dir",
        help="Optional source data directory that contains CMS archives, RXCUI data, and reference CSVs",
    )
    if include_demo_zipcode:
        parser.add_argument(
            "--demo-zipcode",
            action="append",
            default=[],
            help="ZIP code(s) used to scope the demo build profile",
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CMS MPD Recommendation counselor-first DuckDB pipeline"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Run extract -> bronze -> silver -> gold")
    _add_config_arguments(build, include_demo_zipcode=True)
    build.add_argument("--no-rebuild", action="store_true", help="Reuse an existing DuckDB file")

    health = subparsers.add_parser("health-check", help="Validate the built DuckDB serving assets")
    _add_config_arguments(health)

    dataset = subparsers.add_parser("build-dataset", help="Build training dataset for the hybrid reranker")
    _add_config_arguments(dataset)
    dataset.add_argument(
        "--scenario-bundle",
        action="append",
        default=[],
        help="Optional scenario bundle filter for research dataset generation",
    )
    dataset.add_argument(
        "--scenario-source-strategy",
        default="mixed",
        choices=["mixed", "pde", "benchmark"],
    )
    dataset.add_argument("--target-scenario-count", type=int, default=0)
    dataset.add_argument("--generator-seed", type=int, default=42)
    dataset.add_argument("--refresh-scenarios", action="store_true")
    dataset.add_argument(
        "--max-workers",
        type=int,
        default=0,
        help="Optional worker count for CPU-parallel scenario replay during dataset generation",
    )
    dataset.add_argument(
        "--chunk-size",
        type=int,
        default=10,
        help="Number of scenarios per persisted chunk during dataset generation",
    )
    dataset.add_argument(
        "--stale-chunk-hours",
        type=int,
        default=6,
        help="Age threshold used to clean up old started chunk state before resume",
    )
    dataset.add_argument(
        "--no-resume-chunks",
        action="store_true",
        help="Rebuild dataset chunks from scratch instead of resuming completed chunk files",
    )

    generate = subparsers.add_parser("generate-scenarios", help="Materialize canonical training scenarios")
    _add_config_arguments(generate)
    generate.add_argument(
        "--scenario-source-strategy",
        default="mixed",
        choices=["mixed", "pde", "benchmark"],
    )
    generate.add_argument("--target-scenario-count", type=int, default=0)
    generate.add_argument("--generator-seed", type=int, default=42)
    generate.add_argument("--refresh-scenarios", action="store_true")

    train = subparsers.add_parser("train-model", help="Train the hybrid reranker artifact")
    _add_config_arguments(train)
    train.add_argument("--model-type", default="tree", choices=["tree", "linear"])
    train.add_argument(
        "--feature-subset",
        default="full",
        choices=["cost_only", "cost_plus_restrictions", "cost_plus_restrictions_network", "full"],
    )
    train.add_argument(
        "--teacher-feature-policy",
        default="student_safe",
        choices=["student_safe", "teacher_features"],
    )

    evaluate = subparsers.add_parser("evaluate-model", help="Evaluate the hybrid reranker artifact")
    _add_config_arguments(evaluate)
    evaluate.add_argument(
        "--scenario-bundle",
        action="append",
        default=[],
        help="Optional scenario bundle filter for evaluation",
    )
    evaluate.add_argument(
        "--baseline-only",
        action="store_true",
        help="Evaluate only rules, heuristic, and linear baselines",
    )
    evaluate.add_argument(
        "--teacher-feature-policy",
        default="student_safe",
        choices=["student_safe", "teacher_features"],
    )

    recommend = subparsers.add_parser("recommend", help="Score plans for a beneficiary")
    _add_config_arguments(recommend)
    recommend.add_argument("--zipcode", required=True)
    recommend.add_argument("--age-band", default="65-74")
    recommend.add_argument("--lis-status", default="none", choices=["none", "partial", "full"])
    recommend.add_argument("--pharmacy-preference", default="auto", choices=["auto", "retail", "mail"])
    recommend.add_argument("--top-n", type=int, default=5)
    recommend.add_argument("--ranking-mode", default="rules", choices=["rules", "hybrid"])
    recommend.add_argument(
        "--shortlist-mode",
        default="default",
        choices=["default", "full_coverage_compare"],
    )
    recommend.add_argument(
        "--user-role",
        default="beneficiary",
        choices=["beneficiary", "caregiver", "counselor"],
    )
    recommend.add_argument(
        "--decision-focus",
        default="balanced",
        choices=[
            "balanced",
            "lowest_total_cost",
            "lowest_monthly_premium",
            "coverage_first",
            "pharmacy_access",
            "low_friction",
        ],
    )
    recommend.add_argument(
        "--condition-flag",
        action="append",
        default=[],
        help="Optional beneficiary chronic condition flags",
    )
    medication_input = recommend.add_mutually_exclusive_group(required=True)
    medication_input.add_argument(
        "--medication-json",
        help="JSON array of medication inputs matching MedicationInput fields",
    )
    medication_input.add_argument(
        "--medication-file",
        help="Path to a JSON file containing an array of medication inputs",
    )
    return parser


def _build_config(args: argparse.Namespace) -> PipelineConfig:
    default_config = PipelineConfig()
    build_profile = getattr(args, "build_profile", default_config.build_profile)
    demo_zipcodes = tuple(getattr(args, "demo_zipcode", []) or default_config.demo_zipcodes)
    return PipelineConfig(
        build_profile=build_profile,
        benefit_design_mode=getattr(args, "benefit_design_mode", default_config.benefit_design_mode),
        demo_zipcodes=demo_zipcodes,
        snapshot_quarter=getattr(args, "snapshot_quarter", default_config.snapshot_quarter),
        data_dir=Path(args.data_dir) if getattr(args, "data_dir", None) else None,
        source_data_dir=Path(args.source_data_dir) if getattr(args, "source_data_dir", None) else None,
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args()
    config = _build_config(args)

    if args.command == "build":
        db_path = run_pipeline(config=config, rebuild=not args.no_rebuild)
        print(db_path)
        return

    if args.command == "health-check":
        print(json.dumps(health_check(config=config), indent=2))
        return

    if args.command == "generate-scenarios":
        print(
            json.dumps(
                generate_training_scenarios(
                    config=config,
                    scenario_source_strategy=args.scenario_source_strategy,
                    target_scenario_count=(args.target_scenario_count or None),
                    generator_seed=args.generator_seed,
                    refresh=args.refresh_scenarios,
                ),
                indent=2,
            )
        )
        return

    if args.command == "build-dataset":
        print(
            build_training_dataset(
                config=config,
                scenario_bundles=args.scenario_bundle or None,
                scenario_source_strategy=args.scenario_source_strategy,
                target_scenario_count=(args.target_scenario_count or None),
                generator_seed=args.generator_seed,
                refresh_scenarios=args.refresh_scenarios,
                max_workers=(args.max_workers or None),
                chunk_size=args.chunk_size,
                resume_chunks=not args.no_resume_chunks,
                stale_chunk_hours=args.stale_chunk_hours,
            )
        )
        return

    if args.command == "train-model":
        print(
            train_hybrid_reranker(
                config=config,
                model_type=args.model_type,
                feature_subset=args.feature_subset,
                teacher_feature_policy=args.teacher_feature_policy,
            )
        )
        return

    if args.command == "evaluate-model":
        print(
            json.dumps(
                evaluate_hybrid_reranker(
                    config=config,
                    scenario_bundles=args.scenario_bundle or None,
                    baseline_only=args.baseline_only,
                    teacher_feature_policy=args.teacher_feature_policy,
                ),
                indent=2,
            )
        )
        return

    if args.medication_file:
        medications_payload = json.loads(Path(args.medication_file).read_text(encoding="utf-8"))
    else:
        medications_payload = json.loads(args.medication_json)
    medications = [MedicationInput(**payload) for payload in medications_payload]
    beneficiary = BeneficiaryInput(
        zipcode=args.zipcode,
        age_band=args.age_band,
        lis_status=args.lis_status,
        chronic_condition_flags=args.condition_flag or None,
        pharmacy_preference=args.pharmacy_preference,
        top_n=args.top_n,
        user_role=args.user_role,
        decision_focus=args.decision_focus,
    )
    if args.shortlist_mode == "full_coverage_compare":
        bundle = recommend_plan_bundle(
            beneficiary,
            medications,
            config=config,
            ranking_mode=args.ranking_mode,
        )
        print(
            json.dumps(
                recommendation_bundle_to_public_payload(
                    bundle,
                    minimum_coverage_pct=100.0,
                ),
                indent=2,
            )
        )
        return

    recommendations = recommend_plans(
        beneficiary,
        medications,
        config=config,
        ranking_mode=args.ranking_mode,
    )
    print(json.dumps([asdict(item) for item in recommendations], indent=2))


if __name__ == "__main__":
    main()
