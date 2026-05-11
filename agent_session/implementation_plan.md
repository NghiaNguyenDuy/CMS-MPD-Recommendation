# Implementation Plan: Beneficiary What-If Scenario Tooling

## Goal
Extend the Decision Support flow so counselors can keep the same medication list, baseline recommendation run, and audited rules engine, then quickly compare how alternate beneficiary assumptions or shortlist postures change the top plans.

## Implemented Changes
| Step | Outcome | Main Files |
|------|---------|------------|
| 1 | Added reusable scenario presets for pharmacy preference, LIS status, and alternate shortlist goals | `src/cms_mpd/app_support.py` |
| 2 | Added a scenario-runner path that reuses the same recommendation engine and dataframe export surface | `streamlit_app.py` |
| 3 | Added a scenario summary frame with baseline deltas for annual cost, coverage, priceability, and channel switching | `src/cms_mpd/app_support.py` |
| 4 | Added results-tab rendering for scenario summary, shortlist previews, side-by-side comparisons, and top-plan details | `streamlit_app.py` |
| 5 | Added regression coverage for scenario generation and summary interpretation | `tests/test_contracts.py` |

## Current Scenario Surface
- Decision Support results now include a `Beneficiary what-if scenarios` section after the baseline shortlist.
- Scenario presets currently cover:
  - alternate pharmacy preferences: `auto`, `retail`, `mail`
  - alternate LIS assumptions: `partial`, `full`
  - alternate shortlist goals: lowest annual cost, safest medication coverage, easiest pharmacy access
- Each scenario run reuses the same medication list and recommendation engine, then shows:
  - top-plan change versus baseline
  - annual total-cost delta versus baseline
  - coverage percent, priced-med count, and channel-switch count
  - a scenario-specific shortlist preview and top-plan details

## Next Technical Candidates
- Add explicit counselor toggles for stable channel preference versus lowest projected single-fill OOP.
- Decide whether monthly timeline rows should become downloadable CSV or audit outputs.
