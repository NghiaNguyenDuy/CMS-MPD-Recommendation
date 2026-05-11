---
name: cms-mpd-costing
description: Explain, debug, or extend the CMS-MPD Medicare Part D recommendation engine. Use when working on benefit-design routing, fill-cost simulation, contract-year behavior, recommendation exports, audits, or reranker evaluation in `src/cms_mpd/recommend.py`, `pipeline.py`, `config.py`, `decision_support.py`, or `modeling.py`.
---

# CMS-MPD Costing

Treat the current implementation as the source of truth. Do not rely on the old `medicare_partd` package paths or the old assumption that 2025 data should enter coverage-gap logic by default.

## Quick Start

1. Read [references/implementation-anchors.md](references/implementation-anchors.md) for the current module map and invariants.
2. If the task changes cost math, inspect `_resolve_plan_benefit_design()`, `_simulate_fill_cost_2025()`, `_simulate_fill_cost_2024()`, and `recommend_plans()`.
3. If the task changes exported outputs, inspect `PlanRecommendation`, `PlanDrugBreakdown`, `DrugFillTrace`, `recommendations_to_frame()`, `recommendations_to_comparison_frame()`, and `src/cms_mpd/decision_support.py`.
4. If the task changes research evaluation, inspect `_recommendations_to_feature_rows()` and `evaluate_hybrid_reranker()` and preserve held-out scenario evaluation.
5. Use [references/checklist.md](references/checklist.md) before finalizing changes.

## Core Rules

- Keep `benefit_design_mode=auto` as the default.
- Treat `2025-Q3` data as `2025_redesign` unless a plan's `contract_year` says otherwise.
- Treat `2024_standard` as explicit historical support, not the default runtime path.
- Keep 2025 logic to deductible -> initial coverage -> annual OOP cap -> $0 thereafter.
- Keep 2024 logic split into deductible -> initial coverage -> coverage gap -> catastrophic, with separate total-spend and TrOOP tracking.
- Never use `coverage_gap_flag` as a proxy for uncovered, excluded, or missing-price drugs.
- Preserve `contract_year` and `benefit_design` through serving tables, recommendation objects, dataframe exports, UI payloads, and audits.

## When To Open References

- Open [references/examples.md](references/examples.md) when you need concrete examples of how the engine should behave.
- Open [references/checklist.md](references/checklist.md) when making edits or reviewing a change.
- Open [references/implementation-anchors.md](references/implementation-anchors.md) when mapping code paths or tracing where a rule is implemented.
