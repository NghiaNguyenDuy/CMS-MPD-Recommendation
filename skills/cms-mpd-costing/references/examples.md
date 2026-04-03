# Examples

## Example: Explain why a 2025 plan should not enter the coverage gap

Look at:

- `src/cms_mpd/recommend.py`
- `_resolve_plan_benefit_design()`
- `_simulate_fill_cost_2025()`

Expected conclusion:

- a 2025 plan in `auto` mode resolves to `2025_redesign`
- that path applies deductible and initial coverage logic, then the annual OOP cap
- `coverage_gap_oop` and `catastrophic_oop` stay `0.0`

## Example: Fix a threshold-straddle bug

Look at:

- `_simulate_fill_cost_2024()`
- `tests/test_phase1_coverage_gap.py`

Expected shape of fix:

- split the fill at the threshold
- price each segment once
- assert final total OOP, not only the gap component

## Example: Trace audit visibility for benefit design

Look at:

- `src/cms_mpd/recommend.py`
- `src/cms_mpd/decision_support.py`
- `tests/test_contracts.py`

Expected conclusion:

- `contract_year` and `benefit_design` should appear in dataframe exports and audit top-k outputs

## Example: Review a research claim about reranker performance

Look at:

- `src/cms_mpd/modeling.py`
- `tests/test_pipeline_smoke.py`

Expected conclusion:

- reranker metrics should come from held-out scenarios only
- train and test scenario sets must be disjoint
