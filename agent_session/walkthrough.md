# Counselor Timeline Walkthrough

## Summary
The recommendation engine already knew the yearly sequence of fills after the cost-realism sprint. This follow-on work turns that trace data into counselor-facing views so users can see not only which plan ranks highest, but when cost pressure happens and whether the pharmacy-channel path is stable.

## New Timeline Helpers
- `build_monthly_timeline_frame(recommendation)` buckets audited fill traces into a 12-month relative plan-year view.
- Each month now shows:
  - drug OOP
  - deductible applied
  - monthly premium
  - projected monthly total
  - cumulative drug OOP
  - cumulative total
  - fill count
  - filled drugs
- `summarize_drug_channel_path(breakdown)` turns raw channel traces into readable medication-level explanations such as a stable preferred-retail path or a switching retail-to-mail path.

## Streamlit Surface
- Plan detail expanders now show two charts:
  - monthly cash-flow bars
  - cumulative OOP / total-cost timeline lines
- The drug-by-drug table now includes a `Channel path` column built from each medication's fill trace sequence.
- The side-by-side comparison table now carries the operational metadata that became important after the cost-realism sprint:
  - priced medications
  - channel switches
  - channel mix
  - simulation policy

## Why This Matters
- Counselors can now distinguish a low annual total from a plan that creates an early deductible spike.
- Channel stability is visible without reading raw fill traces or explanation groups.
- The UI now better reflects the rules engine's actual logic instead of flattening everything into one annual number.

## Remaining Next Steps
- Decide whether monthly timelines should become downloadable structured outputs.
- Consider adding monthly-variance features to model training.
- Add scenario toggles for channel-stability vs lowest-single-fill-cost preferences.
