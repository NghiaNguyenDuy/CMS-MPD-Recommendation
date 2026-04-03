# Enhancement Execution Tracker

## Status
- The correctness-first benefit-design refresh remains the active default.
- The cost-realism recommendation-flow sprint is complete.
- Counselor-facing outputs now expose monthly cash-flow timing and medication-level channel-path behavior from the same audited fill traces.

## Completed Counselor Timeline Sprint
- [x] Add reusable monthly cash-flow timeline helpers derived from plan fill traces.
- [x] Surface deductible exposure and cumulative OOP timing in counselor-facing plan details.
- [x] Surface medication-level channel-path summaries, including channel switches, directly in the detailed drug view.
- [x] Expand side-by-side comparison to include priced-med count, channel switches, channel mix, and simulation policy.
- [x] Update counselor notes so they mention priceability and annual channel stability when available.
- [x] Add contract coverage for monthly timeline aggregation and channel-path summaries.

## Validation Snapshot
- Targeted counselor-output verification passed on contracts and smoke paths.
- Latest focused verification for this sprint: `7 passed`.
- The full suite remained green after the previous recommendation-flow sprint and should stay the final verification step for any further work.

## Remaining Follow-On Opportunities
- [ ] Explore whether reranker training should use explicit `priced_drug_share` or monthly variance features.
- [ ] Expand scenario-analysis tooling for beneficiary what-if comparisons.
- [ ] Add counselor-facing scenario toggles for stable channel preference vs lowest projected single-fill OOP.
- [ ] Add downloadable monthly timeline extracts to the public CSV/audit surfaces if operational users need them outside Streamlit.
