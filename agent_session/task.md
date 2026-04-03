# Enhancement Execution Tracker

## Status
- The correctness-first benefit-design refresh remains the active default.
- The cost-realism recommendation-flow sprint is complete.
- Counselor-facing outputs now expose monthly cash-flow timing and medication-level channel-path behavior from the same audited fill traces.
- Hybrid reranker training now consumes explicit priceability-share and monthly variance features from the simulated annual ledger.

## Completed Reranker Feature Expansion
- [x] Add `priced_drug_share` to training and inference feature rows.
- [x] Add monthly temporal-cost features derived from fill timing:
  - `monthly_drug_oop_variance`
  - `monthly_total_variance`
- [x] Bump dataset schema version so reranker artifacts reflect the expanded feature contract.
- [x] Feed the new features into full-model training and the richer ablation subsets.
- [x] Add focused regression coverage for priceability share and monthly variance behavior.
- [x] Extend smoke coverage so generated training datasets must include the new features.

## Validation Snapshot
- Focused reranker-feature verification passed on recommendation-flow and pipeline smoke tests.
- Latest focused verification for this sprint: `8 passed`.
- Full-suite verification remains the final gate after every completed phase.

## Remaining Follow-On Opportunities
- [ ] Expand scenario-analysis tooling for beneficiary what-if comparisons.
- [ ] Add counselor-facing scenario toggles for stable channel preference vs lowest projected single-fill OOP.
- [ ] Add downloadable monthly timeline extracts to the public CSV/audit surfaces if operational users need them outside Streamlit.
