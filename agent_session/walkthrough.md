# Correctness-First Benefit Design Walkthrough

## Summary
The old walkthrough was directionally useful but no longer represented the intended runtime behavior. `2025-Q3` data now runs through the 2025 Part D redesign by default, while historical coverage-gap behavior is available only through explicit `2024_standard` handling.

## Active Benefit Designs
- `2025_redesign`: deductible -> initial coverage -> annual OOP cap -> $0 thereafter.
- `2024_standard`: deductible -> initial coverage -> coverage gap -> catastrophic, with catastrophic beneficiary liability modeled as $0.
- `auto`: choose between those paths using `contract_year`, falling back to the snapshot year when the source year is missing.

## Engine Changes
- `PipelineConfig` and CLI now expose `benefit_design_mode`.
- `CONTRACT_YEAR` is carried from formulary input into the gold serving layer and recommendation outputs.
- `_simulate_fill_cost()` dispatches into explicit 2025 and 2024 paths instead of mixing phase logic in one flow.
- 2024 threshold crossings now split fills into segments so straddle fills are not double-charged.
- `coverage_gap_flag` now means the simulation actually entered the coverage gap.
- Recommendation exports and audits now include both `contract_year` and `benefit_design`.
- Hybrid reranker evaluation now trains on scenario-level train splits and reports metrics on held-out scenarios only.

## Validation Snapshot
- Focused regression suite covers 2025-default behavior, explicit 2024 transitions, export contracts, and held-out evaluation metadata.
- The full project should continue to use rules-first cost simulation as the source of truth, with ML limited to reranking simulated plan rows.

## Follow-On Work
- Deductible sequencing and what-if scenario UX can continue from this corrected baseline.
- Any future historical modeling should remain opt-in and auditable through `benefit_design` output fields.
