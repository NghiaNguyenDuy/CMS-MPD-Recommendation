---
title: CMS MPD Time-Based Prescription Cost Case Studies
type: output
status: complete
tags:
  - cms-mpd
  - output
  - case-study
  - part-d
  - cost-simulation
  - counseling
created: 2026-04-08
related_notes:
  - "[[Study - Part D Plan Comparison Checklist]]"
  - "[[Study - CY2025 Scored Plan Decision Worksheet]]"
  - "[[CMS MPD CY2025 Enrollment Workflow and Case Comparison]]"
  - "[[CMS MPD Specific Prescription Case Illustrations]]"
  - "[[CMS MPD Counselor Narrative Case Studies]]"
  - "[[Topic - Part D Benefit Redesign]]"
  - "[[Topic - Insulin Affordability in Part D]]"
  - "[[Topic - Extra Help Low-Income Subsidy]]"
  - "[[Topic - Drug Pricing and Formulary Dynamics]]"
---

# Summary

This note converts vault themes into counseling-style case studies that are explicitly time based. The cases assume fill-level simulation across the year rather than a single annual multiplication.

> [!info]
> These are illustrative counseling cases derived from the vault and implementation notes. Month estimates are scenario-based and can shift with exact quantity, days supply, pharmacy channel, LIS status, and formulary design.

## Formal Case Study Table

| Case | Patient profile                                                        | Drug mix                                                                             | Policy year          | Deductible phase                                                    | Cap-hit month                                                                 | Monthly timeline                                                                                                                                                | Cost calculation logic                                                                                                                                                        | Final annual result                                                                                                                       | Recommended counseling action                                                                                                |
| ---- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | -------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1    | Low utilizer, non-LIS, stable maintenance therapy                      | 2 to 3 low-cost generics with 30-day retail fills                                    | `CY2025`             | Mostly concentrated in `Jan-Feb`; modest deductible exposure        | Not expected                                                                  | `Jan-Feb`: deductible and first copays. `Mar-Dec`: stable low monthly cost.                                                                                     | Apply deductible only where required, then simulate recurring fills at the actual pharmacy. Premium plus routine copays dominate; cap logic is usually irrelevant.            | Low annual cost; the best plan is usually the cleanest low-total-cost plan, not necessarily the lowest premium alone.                     | Compare total annual cost across safe plans, confirm the pharmacy is preferred, and avoid overemphasizing the annual cap.    |
| 2    | Insulin user with several chronic drugs, non-LIS                       | Covered insulin plus antihypertensive, statin, and one brand diabetes companion drug | `CY2025`             | Insulin protected; other drugs may still drive early deductible use | Usually not expected, but possible late year if the companion brand is costly | `Every month`: insulin cost is relatively stable. `Quarterly or high-cost months`: companion drugs create spikes.                                               | Price insulin under insulin-specific protections, then simulate the rest of the regimen fill by fill. Track both total annual cost and monthly cash-flow burden.              | Whole-regimen cost can differ materially across plans even when insulin looks similarly covered.                                          | Check the exact insulin product and supply arrangement, then score plans on both annual total and monthly burden.            |
| 3    | High-cost specialty or oncology user, non-LIS                          | One specialty drug plus supportive generics                                          | `CY2025`             | Deductible consumed almost immediately                              | `Jan` or `Feb` in many severe-cost cases                                      | `Jan-Feb`: very high first fills rapidly increase OOP. After the cap is hit, covered Part D cost sharing falls to `$0` for the rest of the year.                | Order fills chronologically because early specialty fills determine when the annual OOP cap is reached. Safety and access checks come before price ranking.                   | Annual liability compresses toward the `CY2025` `$2,000` cap, but access risk and utilization management become the main differentiators. | Eliminate unsafe plans first, then choose the lowest total-cost safe plan with realistic specialty-pharmacy access.          |
| 4    | High-cost user under older rules                                       | One very expensive brand drug with ongoing monthly fills                             | `CY2024`             | Consumed immediately                                                | Catastrophic may be reached in `Jan` or `Feb`, depending on drug price        | `Jan-Feb`: old phase logic still matters. After catastrophic entry, beneficiary cost sharing for covered drugs is `$0` in this repository's 2024 approximation. | Simulate deductible, initial coverage, and threshold crossing under `2024_standard`; do not reuse `CY2025` cap logic.                                                         | Costs are still much harsher than `CY2025`, and timing of catastrophic entry drives much of the annual result.                            | Flag the case as pre-2025 logic, compare with care, and do not mix older coverage-gap assumptions into `CY2025+` counseling. |
| 5    | Beneficiary potentially eligible for Extra Help / LIS                  | Mixed generic and brand chronic regimen                                              | `CY2025`             | Often reduced or effectively neutralized by LIS treatment           | Usually not the main decision driver                                          | `Jan-Dec`: each fill is recalculated under LIS rules, producing lower and steadier cost exposure.                                                               | Compute base plan liability, then apply LIS per fill. Also evaluate whether a premium remains if the beneficiary chooses a plan above the benchmark.                          | Real annual liability can fall sharply; a case that looks unaffordable without LIS can become manageable with LIS.                        | Screen LIS before making a final recommendation and before suggesting the Medicare Prescription Payment Plan.                |
| 6    | Specialty product with a generic alternative, non-LIS                  | One high-price brand/generic pair with a modest price spread                         | `CY2024`             | Similar early deductible exposure for both options                  | Brand may reach catastrophic earlier than generic                             | `Midyear`: the brand can move faster through older phase thresholds while the generic remains exposed longer.                                                   | Under older rules, manufacturer-discount dynamics can make brand OOP lower than generic OOP; generic is not automatically cheaper to the beneficiary.                         | Counterintuitive annual result: the brand-name drug can produce lower beneficiary OOP than the generic alternative.                       | Compare the exact product pair in the same plan and pharmacy, and warn against assuming `generic = lower OOP`.               |
| 7    | Beneficiary with manageable annual total but unaffordable early months | Mixed chronic regimen with front-loaded deductible and one higher-cost brand         | `CY2025` or `CY2026` | Early-year deductible remains the cash-flow pressure point          | Unchanged by smoothing; often `not expected`                                  | `Jan-Apr`: costs feel front-loaded. `Later months`: payment smoothing can spread liability more evenly.                                                         | The Medicare Prescription Payment Plan changes timing of payment, not total annual liability. The annual result stays roughly the same unless LIS or plan choice changes too. | Same or nearly same annual total, but a much smoother month-to-month burden.                                                              | Use payment smoothing only after confirming LIS status and after ruling out a better-fitting plan.                           |
| 8    | Returning enrollee with the same drugs next year                       | Same regimen as prior year, often mixed chronic therapy                              | `CY2026`             | Deductible resets on `January 1, 2026`                              | Often later than `CY2025` because the threshold rises to `$2,100`             | `Jan`: new plan year resets accumulation. `All year`: prior-year plan assumptions may no longer hold because premiums, tiers, and thresholds change.            | Recompute from scratch using `CY2026` parameters, including the `$615` deductible and `$2,100` OOP threshold.                                                                 | Last year's best plan can stop being the best plan.                                                                                       | Re-shop every plan year and do not carry forward a prior recommendation without recalculation.                               |

## Use In Counseling

- Start with [[Study - Part D Plan Comparison Checklist]] and collect the exact drug list, pharmacy, and subsidy status.
- Use [[Study - CY2025 Scored Plan Decision Worksheet]] after eliminating clinically unsafe plans.
- Treat [[Topic - Part D Benefit Redesign]] as the year-rule anchor so `CY2024` and `CY2025+` logic do not get mixed.
- Treat [[Topic - Insulin Affordability in Part D]], [[Topic - Extra Help Low-Income Subsidy]], and [[Topic - Drug Pricing and Formulary Dynamics]] as special-case modifiers, not minor details.

## Related Notes

- [[CMS MPD CY2025 Enrollment Workflow and Case Comparison]]
- [[CMS MPD Specific Prescription Case Illustrations]]
- [[CMS MPD Counselor Narrative Case Studies]]
- [[Study - Part D Plan Comparison Checklist]]
- [[Study - CY2025 Scored Plan Decision Worksheet]]
- [[Topic - Part D Benefit Redesign]]
- [[Topic - Plan Finder and CMS Pricing Files]]
- [[Topic - Insulin Affordability in Part D]]
- [[Topic - Extra Help Low-Income Subsidy]]
- [[Topic - Drug Pricing and Formulary Dynamics]]
