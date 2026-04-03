# Implementation Plan: Cost-Realistic Recommendation Flow

## Goal
Make the rules engine more counselor-trustworthy by stabilizing annual sequencing, reducing noisy channel oscillation, and separating fully priceable recommendations from weak fallbacks before ranking.

## Implemented Changes
| Step | Outcome | Main Files |
|------|---------|------------|
| 1 | Added `ScheduledFillEvent` and deterministic annual sequencing helpers | `recommend.py` |
| 2 | Added global `sequence_index` to `DrugFillTrace` for annual auditability | `recommend.py` |
| 3 | Replaced pure greedy channel choice with near-tie continuity and preference-aware selection | `recommend.py` |
| 4 | Added `channel_switch_count` and incorporated it into fit scoring and watchouts | `recommend.py` |
| 5 | Added internal recommendation buckets plus `priced_drug_count`-aware rules sorting | `recommend.py` |
| 6 | Exposed `priced_drug_count`, `channel_switch_count`, and `simulation_policy` in recommendation frames and audits | `recommend.py`, `decision_support.py` |
| 7 | Passed the stronger rules output into hybrid feature generation and bucket-preserving reranking | `modeling.py` |
| 8 | Added focused regression tests for sequencing, channel continuity, bucket order, and smoke-path invariance | `tests/test_recommendation_flow_realism.py`, `tests/test_contracts.py`, `tests/test_pipeline_smoke.py` |

## Active Defaults
- Benefit-design behavior stays as previously corrected:
  - `benefit_design_mode=auto`
  - `2025_redesign` for `contract_year >= 2025`
  - `2024_standard` only for explicit historical support
- Channel continuity near-tie tolerance is fixed at `$1.00`.
- Hybrid reranking remains optional and downstream of the rules engine.

## Ranking Flow Now
1. Resolve plan-year benefit design and build medication-level fill events.
2. Sort events with deterministic annual sequencing rather than medication input order.
3. Simulate each fill across feasible channels and choose a stable channel winner.
4. Aggregate fill traces into medication breakdowns with explicit priceability and switch metadata.
5. Bucket plans into fully priceable, needs verification, and fallback-only groups before final rules sorting.
6. Optionally rerank within those buckets using the hybrid model.
