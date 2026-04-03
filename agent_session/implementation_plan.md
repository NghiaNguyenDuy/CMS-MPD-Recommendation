# Implementation Plan: Correctness-First Benefit Design Refresh

## Supersession Note
The earlier Phase 1 plan that treated coverage gap and catastrophic logic as the default for 2025 data is no longer current. This project now treats the 2025 Part D redesign as the primary path and keeps pre-2025 gap logic as explicit historical support.

## Completed Plan
| Step | Outcome | Main Files |
|------|---------|------------|
| 1 | Added `benefit_design_mode` config and CLI wiring (`auto`, `2025_redesign`, `2024_standard`) | `config.py`, `__main__.py` |
| 2 | Propagated `contract_year` into gold serving assets and manifest output | `pipeline.py` |
| 3 | Refactored recommendation simulation into explicit 2025 and 2024 benefit-design paths | `recommend.py` |
| 4 | Fixed segmented threshold math and corrected coverage-gap reporting semantics | `recommend.py`, `tests/test_phase1_coverage_gap.py` |
| 5 | Added `contract_year` and `benefit_design` to exports and audit contracts | `recommend.py`, `decision_support.py`, `tests/test_contracts.py` |
| 6 | Hardened reranker evaluation with scenario-level held-out testing | `modeling.py`, `tests/test_pipeline_smoke.py` |
| 7 | Updated project notes and docs to reflect the corrected default behavior | `README.md`, `docs/*`, `agent_session/*` |

## Current Default Rules
- `benefit_design_mode=auto` uses each plan's `contract_year` when available.
- `contract_year >= 2025` resolves to `2025_redesign`.
- `contract_year <= 2024` resolves to `2024_standard`.
- `2025_redesign` removes coverage-gap and catastrophic phases from the default simulation path.
- `2024_standard` keeps historical gap logic with separate total-spend and TrOOP accumulators.
