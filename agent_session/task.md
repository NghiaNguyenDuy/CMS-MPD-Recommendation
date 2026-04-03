# Enhancement Execution Tracker

## Status
- The original Phase 1 coverage-gap-first implementation is superseded.
- Default snapshot behavior is now `2025_redesign` for `2025-Q3` data.
- Historical gap and catastrophic modeling is preserved only as explicit `2024_standard` support.

## Correctness-First Stabilization Sprint
- [x] Add `benefit_design_mode` to runtime config, environment handling, and CLI.
- [x] Propagate `CONTRACT_YEAR` from formulary data into gold serving tables.
- [x] Refactor fill-cost simulation into explicit `2025_redesign` and `2024_standard` paths.
- [x] Keep 2025 logic on deductible -> initial coverage -> annual OOP cap -> $0 thereafter.
- [x] Keep 2024 logic on deductible -> initial coverage -> coverage gap -> catastrophic with separate TrOOP handling.
- [x] Fix straddle-fill math so threshold crossings are segmented instead of double-charged.
- [x] Correct `coverage_gap_flag` to mean actual entry into the coverage gap.
- [x] Add `contract_year` and `benefit_design` to recommendation outputs, dataframe exports, and audit payloads.
- [x] Change reranker evaluation to a held-out scenario split.
- [x] Refresh tests for 2025-default, 2024-explicit, and held-out evaluation behavior.

## Deferred Roadmap
- [ ] Multi-drug deductible sequencing optimization.
- [ ] Advanced fuzzy drug resolution improvements.
- [ ] Temporal cost distribution and monthly curve views.
- [ ] Expanded explainability and scenario-analysis workflows.
