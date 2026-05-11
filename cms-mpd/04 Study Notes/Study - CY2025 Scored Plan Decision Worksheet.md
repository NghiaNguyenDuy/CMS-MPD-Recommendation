---
title: Study - CY2025 Scored Plan Decision Worksheet
type: study-note
status: active
updated: 2026-04-08
tags:
  - cms-mpd
  - study
  - worksheet
  - cy2025
  - plan-comparison
  - decision-support
related_topics:
  - "[[Topic - Part D Benefit Redesign]]"
  - "[[Topic - Plan Finder and CMS Pricing Files]]"
  - "[[Topic - Insulin Affordability in Part D]]"
---

# Purpose

Use this note to rank candidate plans for `CY2025` after the coverage gate has already been applied. If at least one local full-coverage plan exists, score only those plans. If no local full-coverage plan exists, document blockers first and then score only the fallback set you intentionally keep for tradeoff review.

> [!warning]
> Do not use weighted scoring to rescue a clinically unsafe or exact-regimen-incompatible plan. If a plan fails a red-line field such as exact formulary access or realistic specialty access, eliminate it before scoring.

## Pre-Scoring Gate

- Exact regimen locked to the entered `drug_name`, `RXCUI`, and `NDC` whenever available
- Candidate set is local full-coverage plans if any exist
- If no local full-coverage plan exists, blocker review is completed first: `never_local_coverable` versus `not_jointly_coverable`
- Nearby out-of-area plans remain comparison-only and are not mixed into the primary shortlist
- Alternative-product searches require explicit human approval and a fresh rerun

## Tradeoff Fields To Capture For Every Plan

- annual total cost
- annual premium
- annual drug out-of-pocket cost
- requested-drug coverage percent
- uncovered drug count
- restriction summary
- network flag and nearest preferred distance
- channel mix and channel switch count

## Scoring Rules

- Score each field from `1` to `5`.
- Multiply `Score x Weight` to get the weighted points.
- Higher total is better.
- Keep short notes next to every score so the result is auditable later.

### Score Meaning

| Score | Meaning |
| --- | --- |
| `1` | unacceptable or clearly weak fit |
| `2` | risky or high-friction fit |
| `3` | workable but not strong |
| `4` | strong fit |
| `5` | best fit among the compared plans |

## Case 1: Low Utilizer Worksheet

### Red-Line Fields

- Every essential routine drug covered and priced as entered
- Preferred pharmacy is in network and cost-advantaged

### Weighted Fields

| Field | Weight | What to evaluate |
| --- | --- | --- |
| Total annual cost | `5` | annual premium + simulated annual drug out-of-pocket cost |
| Preferred pharmacy fit | `4` | whether the actual pharmacy is preferred, standard, or practically distant |
| Routine formulary completeness | `4` | whether all maintenance drugs are covered and priceable cleanly |
| Early-year affordability | `3` | whether deductible and first-quarter fills create avoidable cash stress |
| Administrative simplicity | `2` | stable channel pattern, fewer switches, fewer avoidable hassles |
| Future flexibility | `1` | whether the plan is still reasonable if one low-cost brand or new drug gets added mid-year |

### Scoring Table

| Field | Weight | Plan A Score | Plan A Points | Plan B Score | Plan B Points | Plan C Score | Plan C Points | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Total annual cost | `5` |  |  |  |  |  |  |  |
| Preferred pharmacy fit | `4` |  |  |  |  |  |  |  |
| Routine formulary completeness | `4` |  |  |  |  |  |  |  |
| Early-year affordability | `3` |  |  |  |  |  |  |  |
| Administrative simplicity | `2` |  |  |  |  |  |  |  |
| Future flexibility | `1` |  |  |  |  |  |  |  |
| **Total** |  |  |  |  |  |  |  |  |

## Case 2: Insulin User Worksheet

### Red-Line Fields

- Exact insulin product covered and priced as entered
- Pharmacy or supply arrangement works in real life
- If no local exact full-coverage plan exists, blocker class documented before fallback scoring begins

### Weighted Fields

| Field | Weight | What to evaluate |
| --- | --- | --- |
| Exact insulin coverage and access | `5` | formulary placement, supply rules, and whether the exact insulin workflow is stable |
| Total annual cost for full regimen | `5` | insulin plus all non-insulin medications across the full year |
| Monthly cash-flow burden | `5` | how painful the high-cost months are even if annual total is acceptable |
| Rest-of-regimen formulary fit | `4` | whether companion diabetes, cardiovascular, or other chronic drugs are covered well |
| Pharmacy and supply fit | `4` | preferred pharmacy pricing, 90-day access, mail order, and refill practicality |
| Utilization-management burden | `3` | prior auth, quantity limits, and refill friction on the total regimen |

### Scoring Table

| Field | Weight | Plan A Score | Plan A Points | Plan B Score | Plan B Points | Plan C Score | Plan C Points | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Exact insulin coverage and access | `5` |  |  |  |  |  |  |  |
| Total annual cost for full regimen | `5` |  |  |  |  |  |  |  |
| Monthly cash-flow burden | `5` |  |  |  |  |  |  |  |
| Rest-of-regimen formulary fit | `4` |  |  |  |  |  |  |  |
| Pharmacy and supply fit | `4` |  |  |  |  |  |  |  |
| Utilization-management burden | `3` |  |  |  |  |  |  |  |
| **Total** |  |  |  |  |  |  |  |  |

## Case 3: High-Cost Specialty User Worksheet

### Red-Line Fields

- Exact specialty drug covered and priced as entered
- Realistic specialty-pharmacy access
- No clinically dangerous access delay

### Weighted Fields

| Field | Weight | What to evaluate |
| --- | --- | --- |
| Exact specialty-drug access | `5` | whether the exact drug is covered and not practically blocked |
| Time-to-fill and continuity risk | `5` | likelihood of therapy interruption, transition-fill trouble, or slow approval path |
| Utilization-management burden | `5` | prior auth, step therapy, reauthorization frequency, and appeals risk |
| Specialty pharmacy and dispensing fit | `4` | whether the required pharmacy or shipping model is workable for the beneficiary |
| Total annual cost among safe plans | `4` | annual cost only after unsafe plans are eliminated |
| Rest-of-regimen support | `3` | whether the plan also handles supportive or chronic companion drugs well |
| Administrative burden | `3` | burden on beneficiary, caregiver, prescriber, and office staff |

### Scoring Table

| Field | Weight | Plan A Score | Plan A Points | Plan B Score | Plan B Points | Plan C Score | Plan C Points | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Exact specialty-drug access | `5` |  |  |  |  |  |  |  |
| Time-to-fill and continuity risk | `5` |  |  |  |  |  |  |  |
| Utilization-management burden | `5` |  |  |  |  |  |  |  |
| Specialty pharmacy and dispensing fit | `4` |  |  |  |  |  |  |  |
| Total annual cost among safe plans | `4` |  |  |  |  |  |  |  |
| Rest-of-regimen support | `3` |  |  |  |  |  |  |  |
| Administrative burden | `3` |  |  |  |  |  |  |  |
| **Total** |  |  |  |  |  |  |  |  |

## Recommendation Snapshot

- Beneficiary type:
- Candidate set type: `local full coverage`, `local fallback`, or `comparison-only review`
- Plans compared:
- Eliminated plans and why:
- Blocked exact drugs:
- Highest-scoring surviving plan:
- Main reason:
- Main caution:

## Related Notes

- [[Study - Part D Plan Comparison Checklist]]
- [[CMS MPD CY2025 Enrollment Workflow and Case Comparison]]
- [[Topic - Part D Benefit Redesign]]
