# Implementation Anchors

## Primary Modules

- `src/cms_mpd/config.py`
  - owns `benefit_design_mode`
  - valid values: `auto`, `2025_redesign`, `2024_standard`
- `src/cms_mpd/__main__.py`
  - exposes `--benefit-design-mode`
- `src/cms_mpd/pipeline.py`
  - propagates `CONTRACT_YEAR` into silver and gold serving tables
  - records `benefit_design_mode` in the manifest
- `src/cms_mpd/recommend.py`
  - owns benefit-design resolution and fill-cost simulation
  - exports `contract_year` and `benefit_design` in recommendation frames
- `src/cms_mpd/decision_support.py`
  - carries `contract_year` and `benefit_design` into dataframes and audits
- `src/cms_mpd/modeling.py`
  - carries `contract_year` and `benefit_design` into feature rows
  - evaluates rerankers with a held-out scenario split

## Current Source-Of-Truth Constants And Helpers

From `src/cms_mpd/recommend.py`:

- `ANNUAL_OOP_CAP = 2000.00`
- `BENEFIT_DESIGN_2025 = "2025_redesign"`
- `BENEFIT_DESIGN_2024 = "2024_standard"`
- `_resolve_plan_benefit_design()`
- `_simulate_fill_cost_2025()`
- `_simulate_fill_cost_2024()`
- `_simulate_fill_cost()`

## Current Runtime Invariants

- Candidate plans are fetched with `contract_year` from `gold.plan_summary`.
- Each plan resolves to a specific `benefit_design` before fills are simulated.
- 2025-default fills do not emit coverage-gap or catastrophic phases.
- 2024 fills use separate total drug spending and TrOOP accumulators.
- `coverage_gap_flag` means at least one simulated fill entered a `coverage_gap` phase.
- `PlanRecommendation`, `recommendations_to_frame()`, and `recommendations_to_comparison_frame()` expose `contract_year` and `benefit_design`.
- `RecommendationAudit` top-k exports expose `contract_year` and `benefit_design`.

## Evaluation Invariants

From `src/cms_mpd/modeling.py`:

- `_recommendations_to_feature_rows()` includes `contract_year` and `benefit_design`.
- `evaluate_hybrid_reranker()` uses `_split_frame_by_scenario()`.
- Evaluation reports should include:
  - `evaluation_mode = "held_out_by_scenario"`
  - `split_seed`
  - `train_rows` and `test_rows`
  - `train_scenario_count` and `test_scenario_count`
  - disjoint `train_scenarios` and `test_scenarios`
