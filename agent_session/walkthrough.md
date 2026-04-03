# Cost-Realistic Recommendation Flow Walkthrough

## Summary
The recommendation engine now uses a more realistic annual ledger instead of relying on simple chronological fill ordering and per-fill greedy channel picks. The goal is not to mimic every operational detail of Part D claims, but to produce rankings that are stable, auditable, and easier for counselors to trust.

## Annual Simulation Flow
1. Each covered medication is expanded into `ScheduledFillEvent` records with:
   - medication id
   - fill number
   - day offset
   - deductible applicability
   - negotiated-price proxy
   - feasible channels
2. Events are sorted deterministically by:
   - day offset
   - deductible applicability
   - negotiated-price proxy descending
   - medication id
   - fill number
3. The engine simulates each event against the active benefit design (`2025_redesign` or `2024_standard`) and records a `DrugFillTrace` with a global `sequence_index`.

## Channel Selection Flow
- Every feasible channel is still priced for the fill.
- The chosen channel now follows a stable policy:
  - lowest projected OOP first
  - keep the previous medication channel when within the `$1.00` tolerance
  - prefer preferred-network channels
  - then honor retail-vs-mail preference
- Medication-level channel switches are counted and surfaced as `channel_switch_count` in recommendation outputs.

## Recommendation Ranking Flow
- Plans are no longer sorted only by full-vs-partial coverage and fit score.
- The rules engine now buckets plans into:
  - fully covered and fully priceable
  - eligible but needs verification
  - fallback only
- `priced_drug_count` helps separate plans that produced real pricing evidence from plans that only remain as weak comparisons.
- Hybrid reranking, when enabled, preserves those bucket boundaries and reranks only within them.

## Audit Surface
- `DrugFillTrace.sequence_index` makes deductible and OOP transitions auditable.
- `PlanRecommendation` now exposes:
  - `priced_drug_count`
  - `channel_switch_count`
  - `simulation_policy`
  - `contract_year`
  - `benefit_design`
- Dataframe exports and run-audit payloads now carry the same fields so counselor-facing analysis can trace how a recommendation was formed.

## Validation Snapshot
- Focused tests cover deterministic sequencing, deductible-first ordering on same-day fills, near-tie channel continuity, and bucket-aware ranking.
- Smoke coverage confirms recommendation output is stable even when medication input order is reversed.
