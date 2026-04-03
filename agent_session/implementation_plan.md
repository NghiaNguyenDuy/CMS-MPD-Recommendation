# Implementation Plan: Counselor Timeline And Channel Visibility

## Goal
Turn the audited fill-trace data from the cost-realism sprint into counselor-facing outputs that explain when costs happen across the year and how stable each medication's pharmacy-channel path is.

## Implemented Changes
| Step | Outcome | Main Files |
|------|---------|------------|
| 1 | Added reusable monthly timeline aggregation from `DrugFillTrace` rows | `app_support.py` |
| 2 | Added medication-level channel-path summaries that explain stable vs switching fill patterns | `app_support.py` |
| 3 | Expanded side-by-side comparison metrics to include priceability and channel behavior | `app_support.py` |
| 4 | Updated counselor notes to reference priceability and channel stability | `app_support.py` |
| 5 | Added monthly cash-flow charts and detailed timeline tables in Streamlit plan details | `streamlit_app.py` |
| 6 | Added contract tests covering monthly aggregation and channel-path explanations | `tests/test_contracts.py` |

## Current Counselor Surface
- Side-by-side comparison now includes:
  - priced medications
  - channel switches
  - channel mix
  - simulation policy
- Detailed plan expanders now include:
  - monthly projected cash-flow chart
  - cumulative OOP timeline chart
  - monthly timeline table
  - per-drug channel-path summaries

## Next Technical Candidates
- Feed `priced_drug_share` and monthly cost-variance features into reranker training artifacts.
- Decide whether monthly timeline rows should be exported into CSV and audit payloads.
- Build what-if scenario controls on top of the now-visible annual timeline model.
