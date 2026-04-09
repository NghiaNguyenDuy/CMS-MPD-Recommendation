---
title: Study - URL Package Processing Tracker
type: study-note
status: active
tags:
  - cms-mpd
  - study
  - tracker
  - urls
  - intake
processed_on: 2026-04-07
source_note: "[[01 Inbox/References/URLs package]]"
related_topics:
  - "[[Topic - Plan Finder and CMS Pricing Files]]"
  - "[[Topic - Part D Benefit Redesign]]"
  - "[[Topic - Part D Enrollment and Premium Trends]]"
  - "[[Topic - Drug Pricing and Formulary Dynamics]]"
  - "[[Topic - Insulin Affordability in Part D]]"
---

# Purpose

Track the current processing state of the URLs collected in [[01 Inbox/References/URLs package]] and connect those links to the existing `cms-mpd` knowledge base.

## Current Snapshot

- The source note contains 140 URL lines and 127 unique URLs.
- The automated scan baseline from 2026-04-07 found 87 unique URLs that were directly reachable and 37 unique URLs that returned `403` from the scripted environment.
- A second processing batch on 2026-04-07 imported 32 additional raw notes and moved 32 exact URLs into reviewed source notes.
- A third processing batch on 2026-04-07 imported 6 additional raw notes and moved 6 exact URLs into reviewed source notes focused on GAO, OIG, and ASPE oversight material.
- A fourth processing batch on 2026-04-07 imported 5 additional raw notes and moved the full MedPAC section into reviewed source notes.
- A fifth processing batch on 2026-04-07 imported 4 additional raw notes and moved 4 exact NBER URLs into reviewed source notes on plan choice and insurer incentives.
- A sixth processing batch on 2026-04-07 imported 3 additional open-access PMC URLs and folded them into the pricing and formulary coverage notes.
- A seventh processing batch on 2026-04-07 imported 3 dual-eligible access URLs and opened a dedicated note on protections for Medicare-Medicaid enrollees.
- An eighth processing batch on 2026-04-07 imported 2 biosimilar oversight URLs and opened a dedicated note on biosimilar coverage and savings pressure.
- A ninth processing batch on 2026-04-07 imported 3 GLP-1 URLs and opened a dedicated note on use growth, BALANCE-model coverage, and spending pressure.
- The current exact-URL status is 61 reviewed, 29 still reachable but not yet reviewed, and 37 blocked by `403`.
- Three of the reviewed URLs were already in the vault before this batch:
  - [Changes to Medicare Part D in 2024 and 2025 Under the Inflation Reduction Act and How Enrollees Will Benefit](https://www.kff.org/medicare/changes-to-medicare-part-d-in-2024-and-2025-under-the-inflation-reduction-act-and-how-enrollees-will-benefit/) -> [[Source - Part D Reform and IRA Timeline]]
  - [Medicare Part D Plans Greatly Increased Utilization Restrictions On Prescription Drugs, 2011-20](https://www.healthaffairs.org/doi/10.1377/hlthaff.2023.00999) -> [[Source - Drug Pricing and Formulary Distortions]]
  - [Sending The Wrong Price Signal Why Do Some Brand-Name Drugs Cost Medicare Beneficiaries Less Than Generics](https://www.healthaffairs.org/doi/10.1377/hlthaff.2018.05476) -> [[Source - Drug Pricing and Formulary Distortions]]
- Thirteen URL lines in the raw note are duplicates of earlier links and should not be double-counted when planning intake.
- Detailed scan artifacts for reruns are stored in `agent_session/url_status_scan.jsonl` and `agent_session/url_tracker_preview.md`.

## Status Legend

- `Reviewed`: exact URL already flows into a reviewed source note.
- `Reachable`: URL resolved during the scan and is ready for import or synthesis.
- `Blocked 403`: URL rejected the scripted request from this environment; use a PDF mirror, PMC or PubMed alternative, or manual browser review if needed.

## Section Status

- Section counts are deduplicated within each section, but they do not add up to the global total because some URLs appear in more than one section of the source note.

| Section | Unique URLs | Reviewed | Reachable | Blocked 403 | Knowledge-base use |
| --- | ---: | ---: | ---: | ---: | --- |
| CMS / OFFICIAL PROGRAM GUIDANCE | 15 | 15 | 0 | 0 | Now reviewed through [[Source - Part D Operations, Enrollment, and Bidding Guidance]] and supporting topic notes. |
| CMS / DATA, PUF, SPUF, PLAN FINDER RELATED | 7 | 7 | 0 | 0 | Now reviewed through [[Source - Part D Operations, Enrollment, and Bidding Guidance]] and [[Topic - Plan Finder and CMS Pricing Files]]. |
| KFF / EXPLAINERS / MARKET SNAPSHOTS | 8 | 6 | 2 | 0 | Enrollment and premium evidence now feeds [[Source - Part D Market Snapshots and Enrollment Trends]]; the remaining two KFF index pages stay as discovery links. |
| MEDPAC | 5 | 5 | 0 | 0 | MedPAC annual oversight now feeds [[Source - MedPAC Part D Status Reports and Oversight]]. |
| GAO / OIG / ASPE / CBO | 15 | 6 | 3 | 6 | Affordability and implementation oversight now feed [[Source - Part D Oversight and Affordability Monitoring]]; three discovery pages remain in the queue. |
| RESEARCH / JOURNAL ARTICLES / WORKING PAPERS | 21 | 2 | 5 | 14 | The reachable administrative-choice and strategic-formulary NBER papers now feed reviewed notes; blocked DOI and abstract pages still need fallback access. |
| CMS / HPMS / IMPLEMENTATION HISTORY | 6 | 0 | 6 | 0 | Extend operational-history coverage around HPMS memos, application history, and model materials. |
| NBER / ECONOMICS / PLAN DESIGN / INCENTIVES | 7 | 3 | 4 | 0 | Early NBER market-design work now feeds [[Source - Part D Insurer Incentives and Market Design]]; the remaining papers stay in the economics queue. |
| JAMA / JAMA NETWORK | 3 | 0 | 0 | 3 | Blocked JAMA pages also recur in later topic sections, so they remain a fallback-access queue. |
| HEALTH AFFAIRS | 5 | 2 | 0 | 3 | One pricing theme is already reviewed; additional DOI pages need alternate access before intake. |
| OLDER / CLASSIC POLICY CONTEXT | 3 | 0 | 0 | 3 | This section repeats older NEJM links already listed elsewhere in the package. |
| USEFUL DISCOVERY / INDEX PAGES | 3 | 0 | 3 | 0 | Discovery-only pages; lower synthesis priority than direct evidence pages. |
| FORMULARY COVERAGE / RESTRICTIONS / COST SHARING | 6 | 3 | 0 | 3 | Open-access formulary and cost-sharing studies now feed [[Source - Drug Pricing and Formulary Distortions]] and [[Topic - Drug Pricing and Formulary Dynamics]]. |
| PREFERRED PHARMACY NETWORKS / ACCESS / PHARMACY CLOSURES | 5 | 0 | 3 | 2 | Candidate new access and network note. |
| BIOSIMILARS / HUMIRA / BIOLOGIC SPENDING | 4 | 2 | 0 | 2 | OIG biosimilar oversight now feeds [[Source - Biosimilar Coverage and Part D Spending]] and [[Topic - Biosimilar Coverage and Savings Pressure]]. |
| INSULIN / BENEFICIARY OUT-OF-POCKET COSTS | 5 | 2 | 0 | 3 | Newer KFF insulin pages are now reviewed in [[Source - Insulin Affordability in Part D]]; PubMed and JAMA links still need fallback access. |
| GLP-1 / SEMAGLUTIDE / OBESITY COVERAGE / FISCAL IMPACT | 7 | 3 | 0 | 4 | GLP-1 evidence now feeds [[Source - GLP-1 Coverage Use and Fiscal Pressure]] and [[Topic - GLP-1 Coverage and Spending Pressure]]. |
| DUAL-ELIGIBLE ACCESS / ENROLLEE PROTECTION | 3 | 3 | 0 | 0 | Dual-eligible access evidence now feeds [[Source - Dual-Eligible Access to Drugs Under Part D]] and [[Topic - Dual-Eligible Drug Access and Protections]]. |
| BENEFICIARY COSTS / REBATES / GENERICS / PRICING INCENTIVES | 6 | 0 | 3 | 3 | Extend pricing and generic-use coverage, especially beneficiary signal distortion and incentives. |
| PART D REDESIGN / OOP CAP / NEGOTIATION-ERA COVERAGE | 6 | 3 | 1 | 2 | Negotiation and redesign evidence now feeds [[Source - Part D Reform and IRA Timeline]]; one PMC page plus blocked Health Affairs and JAMA items remain. |

## Blocked Domains To Recheck

- `jamanetwork.com` blocked multiple JAMA, JAMA Internal Medicine, JAMA Health Forum, and JAMA Network Open pages.
- `healthaffairs.org` DOI pages were blocked except for the already imported raw notes.
- `pubmed.ncbi.nlm.nih.gov` article pages were blocked in the scripted scan even when related PMC paths may exist.
- `gao.gov`, `cbo.gov`, and `nejm.org` rejected the scripted request path used in this session.

## Priority Next Pass

- Start with the remaining pharmacy-network and NBER papers because the official CMS, Data CMS, core KFF market batches, the first GAO/OIG/ASPE affordability batch, the MedPAC batch, the initial NBER incentive batch, the open-access PMC formulary batch, the dual-eligible access batch, the biosimilar oversight batch, and the GLP-1 batch are now processed.
- Use the next pass to open new source-note coverage areas that the vault still lacks: pharmacy networks, biosimilars, GLP-1, dual-eligible protection, and broader oversight or affordability analysis.
- Treat blocked DOI and abstract pages as a separate intake lane that requires PDF, PMC, or manual-browser fallbacks before summary writing.

## Related Notes

- [[01 Inbox/References/URLs package]]
- [[Source - Part D Operations, Enrollment, and Bidding Guidance]]
- [[Source - Part D Reform and IRA Timeline]]
- [[Source - Part D Market Snapshots and Enrollment Trends]]
- [[Source - Part D Oversight and Affordability Monitoring]]
- [[Source - MedPAC Part D Status Reports and Oversight]]
- [[Source - Part D Insurer Incentives and Market Design]]
- [[Source - Dual-Eligible Access to Drugs Under Part D]]
- [[Source - Biosimilar Coverage and Part D Spending]]
- [[Source - GLP-1 Coverage Use and Fiscal Pressure]]
- [[Source - Drug Pricing and Formulary Distortions]]
- [[Source - Insulin Affordability in Part D]]
- [[Topic - Plan Finder and CMS Pricing Files]]
- [[Topic - Part D Benefit Redesign]]
- [[Topic - Part D Enrollment and Premium Trends]]
- [[Topic - Drug Pricing and Formulary Dynamics]]
