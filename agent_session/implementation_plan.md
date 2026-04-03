# Implementation Plan: Reranker Feature Expansion

## Goal
Strengthen hybrid reranker inputs by feeding it the rules-engine signals that were newly introduced in the cost-realism and counselor-timeline sprints: how much of the regimen was actually priceable, and how uneven the beneficiary's monthly cost pressure looks across the simulated year.

## Implemented Changes
| Step | Outcome | Main Files |
|------|---------|------------|
| 1 | Added `priced_drug_share` to feature rows so the model sees explicit priceability instead of only raw counts | `modeling.py` |
| 2 | Added `monthly_drug_oop_variance` and `monthly_total_variance` from fill-trace timing | `modeling.py` |
| 3 | Updated the full-model numeric feature contract and richer ablation subsets | `modeling.py` |
| 4 | Bumped the dataset schema version to track the expanded reranker feature set | `modeling.py` |
| 5 | Added focused regression coverage plus smoke assertions for the new dataset columns | `tests/test_recommendation_flow_realism.py`, `tests/test_pipeline_smoke.py` |

## Current Modeling Surface
- Training and inference feature rows now include:
  - `priced_drug_share`
  - `monthly_drug_oop_variance`
  - `monthly_total_variance`
- The tree and linear reranker artifacts now train on dataset schema `request_features_v4`.
- Held-out evaluation remains scenario-based and unchanged in method; it now just sees stronger temporal and priceability features.

## Next Technical Candidates
- Build what-if scenario tooling on top of the now-richer annual simulation outputs.
- Add counselor-facing toggles for stable channel preference vs lowest-single-fill OOP.
- Decide whether monthly timeline rows should be exportable through CSV and audit payloads.
