---
title: Study - Part D Plan Comparison Checklist
type: study-note
status: active
updated: 2026-04-08
tags:
  - cms-mpd
  - study
  - checklist
  - plan-comparison
related_topics:
  - "[[Topic - Plan Finder and CMS Pricing Files]]"
  - "[[Topic - Part D Benefit Redesign]]"
  - "[[Topic - Extra Help Low-Income Subsidy]]"
---

# Purpose

Use this note when comparing Part D plans for a real or simulated beneficiary. The current counselor workflow is coverage gated: first determine whether any local ZIP-eligible plan fully covers the exact entered regimen, then compare tradeoffs within the surviving set.

> [!info]
> Use [[Study - CY2025 Scored Plan Decision Worksheet]] after the hard coverage gate is complete and you need a documented weighted comparison among the surviving plans.

## Inputs To Gather

- ZIP code and state
- Current coverage type: PDP, MA-PD, Original Medicare, Medigap
- Preferred pharmacy or pharmacy network constraints
- Full medication list with exact product identifiers when available: `drug_name`, `RXCUI`, `NDC`
- Whether insulin, specialty drugs, or protected-class drugs are involved
- LIS / Extra Help status or possible eligibility
- Whether the case is initial enrollment, annual enrollment, move, loss of coverage, or another special event

## Rapid Screen

- [ ] Are the medication inputs exact enough to lock the regimen to the intended products?
- [ ] Does any local ZIP-eligible plan cover and price every essential medication exactly as entered?
- [ ] If no, which entered drug is `never_local_coverable` and which is only `not_jointly_coverable`?
- [ ] Are any key drugs subject to prior authorization, step therapy, or quantity limits?
- [ ] Is the pharmacy in network and cost-advantaged?
- [ ] Is the plan using low premium marketing to hide higher total drug cost?
- [ ] Does LIS or another assistance program change the decision?
- [ ] Does the case depend on pre-2025 or post-2025 Part D rules?

## Coverage-Gated Shortlist Logic

1. Start with local ZIP-eligible plans only.
2. Keep exact NDC and RXCUI inputs authoritative for the main shortlist whenever they are available.
3. If one or more local plans fully cover and price all entered drugs, shortlist only those plans first.
4. Compare surviving full-coverage plans by annual total cost, annual drug out-of-pocket cost, restriction burden, network and preferred-distance fit, channel switches, and then overall fit.
5. If no local full-coverage plan exists, leave the primary shortlist empty and document the best local fallback plans separately.
6. Keep nearby out-of-area plans in a separate comparison-only section. Do not mix them into the local primary shortlist.
7. Use alternative-product search only after a counselor explicitly chooses an alternate product. Do not auto-substitute medications.

## Top Plan Comparison Table

| Plan | Eligibility | Annual total cost | Annual premium | Annual drug OOP | Coverage % | Uncovered drugs | Restriction summary | Network / preferred distance | Channel mix / switches | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Plan A |  |  |  |  |  |  |  |  |  |  |
| Plan B |  |  |  |  |  |  |  |  |  |  |
| Plan C |  |  |  |  |  |  |  |  |  |  |

## Decision Rules

- Prioritize exact-regimen full coverage and realistic annual total fit before premium-only comparisons.
- Do not let a weighted comparison rescue a plan that fails exact-regimen coverage when a local full-coverage option exists.
- If no local full-coverage plan exists, document the blocker class before discussing fallback plans.
- Check whether the lowest-premium plan creates higher total drug cost through tiering, channel dependence, or restrictions.
- Treat insulin, specialty drugs, and frequently used brand drugs as high-risk items that need closer review.
- If LIS is possible, review subsidy interaction before concluding that the Medicare Prescription Payment Plan is the best answer.
- Flag any recommendation that relies on an older source using pre-2025 coverage gap logic.

## Recommendation Snapshot

- Best local full-coverage option:
- Best local fallback option if needed:
- Blocked exact drug(s):
- Main reason for recommendation:
- Main tradeoff or warning:

## Escalate To Weighted Scoring

- Beneficiary type:
  `low utilizer`, `insulin user`, or `high-cost specialty user`
- Use [[Study - CY2025 Scored Plan Decision Worksheet]] to rank the surviving plans after hard eliminations.
- Do not score plans that fail the exact-regimen gate when at least one local full-coverage plan exists.

## Analytics Capture

- Which topic notes were used?
- Which source notes were most relevant?
- Did the case end in local full coverage, local fallback only, or comparison-only review?
- Which blocker class mattered most?
  - `never_local_coverable`
  - `not_jointly_coverable`
  - no blocker
- What pattern does this case illustrate?
  - Cost confusion
  - Formulary restriction
  - LIS / subsidy issue
  - Insulin affordability
  - Plan Finder usability issue
  - Other:
- Which note in the vault should be updated after this comparison?
