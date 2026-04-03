# Reranker Feature Expansion Walkthrough

## Summary
The hybrid reranker already consumed rules-engine outputs, but it still lacked two important signals introduced by recent sprints:
- how much of the entered regimen was actually priceable
- how uneven cost pressure was across the year

This phase closes that gap by pushing both priceability share and monthly cost-variance features into the training and inference feature frames.

## New Features
- `priced_drug_share`
  - beneficiary-facing meaning: how much of the requested medication list produced usable simulated pricing
  - modeling value: separates partial-but-usable plans from weak fallback plans more clearly than counts alone
- `monthly_drug_oop_variance`
  - measures how uneven drug cost-sharing is across the simulated year
- `monthly_total_variance`
  - measures how uneven combined premium-plus-drug cost pressure is across the simulated year

## How They Are Derived
- `priced_drug_share` is computed from `priced_drug_count / requested_drug_count`.
- Monthly variance features are derived from the same fill traces used by the counselor timeline view:
  - fills are bucketed into 12 relative plan-year months
  - monthly drug OOP totals are aggregated
  - monthly total cost adds the monthly premium to those buckets
  - variance is computed across the 12-month vectors

## Why This Matters
- The reranker can now distinguish a plan that looks acceptable annually but produces a spiky early-year burden.
- Priceability is represented as a normalized share rather than only a raw count, which improves comparability across medication-list sizes.
- The research dataset and production inference frame now stay better aligned with what counselors actually see in the UI.

## Remaining Next Steps
- Build beneficiary what-if scenario tooling.
- Add UI toggles for stable-channel preference vs lowest projected single-fill OOP.
- Decide whether monthly timeline rows should become downloadable public outputs.
