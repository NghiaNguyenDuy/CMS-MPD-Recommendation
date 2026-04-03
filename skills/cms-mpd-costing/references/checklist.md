# Review Checklist

Use this checklist when editing or reviewing the recommendation engine.

## Benefit Design

- Verify `benefit_design_mode` behavior in `auto`, `2025_redesign`, and `2024_standard`.
- Verify `contract_year` is available where the runtime uses it.
- Verify 2025 plans do not emit coverage-gap or catastrophic phases by default.
- Verify 2024 plans use TrOOP for catastrophic entry rather than total drug spending.

## Outputs

- Verify `coverage_gap_flag` reflects actual phase entry.
- Verify `contract_year` and `benefit_design` stay visible in recommendation exports, comparison exports, UI payloads, and audits.
- Verify fill traces carry enough data to audit threshold behavior.

## Evaluation

- Verify held-out evaluation still splits by `scenario_id`.
- Verify train and test scenarios are disjoint.
- Verify evaluation metadata is still present in the report.

## Tests To Run

- `./.venv/Scripts/pytest.exe -q tests/test_phase1_coverage_gap.py`
- `./.venv/Scripts/pytest.exe -q tests/test_contracts.py`
- `./.venv/Scripts/pytest.exe -q tests/test_pipeline_smoke.py`
- `./.venv/Scripts/pytest.exe -q`
