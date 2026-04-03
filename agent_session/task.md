# Enhancement Execution Tracker

## Status
- The correctness-first benefit-design refresh is complete and remains the active default.
- The cost-realism recommendation-flow sprint is now implemented in the rules engine and supporting exports.
- Recommendations continue to be rules-first, with hybrid reranking constrained to the stronger rules output.

## Completed Cost-Realism Sprint
- [x] Extract annual fill scheduling into explicit `ScheduledFillEvent` helpers.
- [x] Replace simple day-only ordering with deterministic sequencing:
  - day offset ascending
  - deductible-applicable fills before deductible-exempt fills on the same day
  - higher negotiated-price proxy first within the same deductible bucket
  - medication id and fill number as stable tiebreakers
- [x] Record `sequence_index` on every `DrugFillTrace` so annual transitions are auditable.
- [x] Replace pure greedy per-fill channel choice with a stable policy:
  - lowest projected fill OOP first
  - keep the previous medication channel when within the `$1.00` near-tie tolerance
  - then prefer preferred-network channels
  - then respect beneficiary retail-vs-mail preference
- [x] Count medication-level channel switches and carry them into plan scoring, watchouts, and exports.
- [x] Add explicit recommendation buckets in the rules ranking flow:
  - fully covered and fully priceable
  - eligible but needs verification
  - fallback only
- [x] Track `priced_drug_count` and use it in recommendation ordering.
- [x] Add `priced_drug_count`, `channel_switch_count`, and `simulation_policy` to recommendation exports and audits.
- [x] Align hybrid reranking with the new internal buckets and stronger rules output.
- [x] Add focused regression coverage for sequencing, channel stability, ranking buckets, and order invariance.

## Validation Snapshot
- Focused regression coverage now includes deterministic fill sequencing, near-tie channel continuity, rules-ranking bucket order, export contracts, and smoke-path integration.
- Latest targeted verification: `10 passed` across contract, smoke, and recommendation-flow realism tests.

## Follow-On Opportunities
- [ ] Add richer monthly cash-flow views and deductible/OOP timelines to counselor outputs.
- [ ] Surface medication-level channel-switch explanations directly in UI comparison views.
- [ ] Explore whether reranker training should use explicit `priced_drug_share` or monthly variance features.
- [ ] Expand scenario-analysis tooling for beneficiary what-if comparisons.
