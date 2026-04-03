# Enhancement Execution Tracker

## Phase 1: Coverage Gap (Donut Hole) + Catastrophic Phase ✅
- [x] Add CMS 2025 coverage phase constants (`INITIAL_COVERAGE_LIMIT`, `CATASTROPHIC_TROOP_THRESHOLD`, etc.)
- [x] Add `_compute_coverage_gap_cost()` and `_compute_catastrophic_cost()` helpers
- [x] Extend `FillCostResult` with `coverage_gap_oop`, `catastrophic_oop`, `total_drug_spending_before/after`
- [x] Extend `DrugFillTrace` with `total_drug_spending_before/after`, `coverage_gap_exposure`
- [x] Extend `PlanDrugBreakdown` with `coverage_gap_oop`, `catastrophic_oop`
- [x] Modify `_simulate_fill_cost()` to detect 4 coverage phases:
  - Deductible → Initial Coverage → Coverage Gap → Catastrophic
  - Handle straddle fills (cross threshold mid-fill)
- [x] Update plan-level simulation loop to track `total_drug_spending`
- [x] Add coverage gap/catastrophic explanations to `PlanExplanationGroups`
- [x] Update `test_contracts.py` for new PlanDrugBreakdown fields
- [x] Add `test_phase1_coverage_gap.py` with 20 tests covering all transitions
- [x] Verify no regression — **24/24 tests pass**

## Phase 2: Multi-Drug Deductible Sequencing
- [ ] Implement `_optimize_fill_ordering()` with cheapest-first strategy
- [ ] Modify fill event sort to use optimized ordering
- [ ] Add `deductible_sequencing_savings` to output
- [ ] Add tests comparing orderings

## Phase 3: Advanced Drug Resolution (Fuzzy by drug name)
- [ ] Add `_fuzzy_drug_match()` using DuckDB `jaro_winkler_similarity()`
- [ ] Extend resolution cascade with fuzzy steps
- [ ] Add `similarity_score` to `MedicationMatch`
- [ ] Add tests for misspelled drug names

## Phase 4: Temporal Cost Distribution (Monthly Curve)
- [ ] Add `MonthlyCostCurve` dataclass
- [ ] Implement `_compute_monthly_curve()` from fill traces
- [ ] Add to `PlanRecommendation`
- [ ] Add front-loading explanations
- [ ] Add Streamlit chart visualization

## Phase 5: Enhanced ML Reranking & Explainability
- [ ] Extract feature importance from tree model
- [ ] Add scenario-aware cross-validation
- [ ] Add per-plan model explanations

## Phase 6: Recommendation Workflow UX
- [ ] Create `scenario_analysis.py` module
- [ ] Add medication sensitivity analysis
- [ ] Add plan switch impact analysis
- [ ] Add Streamlit what-if UI

## Phase 7: Pipeline: Generic Alternatives (drug-name search)
- [ ] Add `gold.plan_drug_alternatives` table
- [ ] Add alternative suggestions to `PlanDrugBreakdown`
- [ ] Add alternative explanations

## Phase 8: Plan Stability & YoY Signals (prior data)
- [ ] Support prior-quarter snapshot loading
- [ ] Add `gold.plan_stability_signals` table
- [ ] Add stability fields to `PlanRecommendation`
- [ ] Modify `stability_score` to incorporate YoY deltas
