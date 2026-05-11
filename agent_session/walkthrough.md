# Beneficiary What-If Scenario Walkthrough

## Summary
The recommendation flow already supported a strong baseline run, side-by-side plan comparison, and counselor-facing timeline review. This phase adds a lightweight scenario-analysis layer on top of that baseline so counselors can ask, "What changes if this beneficiary prefers mail order, qualifies for LIS, or needs a stricter coverage-first shortlist?" without rebuilding the case from scratch.

## What Was Added
- Reusable scenario presets generated from the current beneficiary profile and shortlist posture.
- A results-tab action that reruns the same medication list under selected alternate assumptions.
- A summary table that compares each scenario back to the baseline shortlist.
- Per-scenario shortlist previews, side-by-side plan comparisons, and top-plan detail drilldowns.

## Scenario Coverage
- Pharmacy preference scenarios compare `auto`, `retail`, and `mail` assumptions.
- LIS scenarios model `partial` and `full` subsidy support when they differ from the current input.
- Goal scenarios re-run the shortlist under alternate postures such as lowest total cost or safest medication coverage.

## Why This Matters
- Counselors can test realistic beneficiary questions without re-entering the regimen.
- The comparison stays grounded in the same audited rules engine and output contracts already used by the main flow.
- Plan movement becomes easier to explain because the summary shows whether the top plan stayed stable or changed under each alternate assumption.

## Remaining Next Steps
- Add UI controls for choosing stable-channel policy versus lowest projected single-fill OOP.
- Decide whether monthly timeline rows should be exportable outside the Streamlit view.
