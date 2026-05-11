---
title: CMS MPD Journal Alignment and Submission Checklist
date: 2026-04-15
status: draft
tags:
  - manuscript
  - journal-targeting
  - cms-mpd
---

# CMS MPD Journal Alignment and Submission Checklist

> [!note] Purpose
> This note keeps the submission strategy separate from the manuscript body. Remove these operational notes before uploading the paper itself.

## Manuscript package

| File | Use |
|---|---|
| [[CMS MPD Manuscript - Informatics in Medicine Unlocked]] | Submit here if the primary story is counselor-centered medical informatics and explainable decision support. |
| [[CMS MPD Manuscript - Computer Methods and Programs in Biomedicine Update]] | Submit here if the primary story is computational method, software architecture, and reranking evaluation. |
| [[CMS MPD Manuscript - Computer Methods and Programs in Biomedicine Update - Reviewer Revision Draft]] | Use this version if you want the CMPB Update manuscript rewritten around reviewer-facing provenance, reproducibility, and limitation clarity. |
| [[CMS MPD Journal Alignment and Submission Checklist]] | Use before export to verify metadata, declarations, highlights, references, and data-sharing decisions. |

## Target journals

| Journal | Best-fit angle for this study | Open access status | APC shown on ScienceDirect | Source |
|---|---|---|---|---|
| Informatics in Medicine Unlocked | Counselor-centered medical informatics decision support for Medicare Part D plan comparison. | Peer-reviewed open access journal. | USD 2300 excluding taxes. | [ScienceDirect open access options](https://www.sciencedirect.com/journal/informatics-in-medicine-unlocked/publish/open-access-options) |
| Computer Methods and Programs in Biomedicine Update | Policy-aware data engineering, cost simulation, and constrained reranking method. | Peer-reviewed gold open access journal. | USD 1500 excluding taxes. | [ScienceDirect open access options](https://www.sciencedirect.com/journal/computer-methods-and-programs-in-biomedicine-update/publish/open-access-options) |

## Shared Elsevier preparation requirements

Both journal guide pages support an initial "Your Paper Your Way" submission, but the manuscript package should still be prepared with the following items:

| Item                      | Requirement to satisfy                                                  | Local action                                                                          |
| ------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Editable manuscript       | Submit an editable source file, such as Word or LaTeX.                  | Export the selected markdown draft to DOCX before submission.                         |
| Abstract                  | Concise abstract of no more than 250 words.                             | Keep each draft abstract under 250 words.                                             |
| Keywords                  | 1 to 7 keywords.                                                        | Each draft includes 7 or fewer keywords.                                              |
| Highlights                | 3 to 5 bullet points, each no more than 85 characters including spaces. | Export highlights as a separate editable file if requested during upload.             |
| Figures                   | Submit figure files separately and cite them in the manuscript.         | Prepare pipeline, runtime workflow, and evaluation figures outside the manuscript.    |
| Research data statement   | State whether research data are available, deposited, or restricted.    | Use the included data availability text, then revise based on final sharing decision. |
| Declaration of interests  | Required.                                                               | Keep "none declared" only if accurate.                                                |
| Funding statement         | Required if applicable.                                                 | Replace TODO funding text before submission.                                          |
| CRediT author statement   | Required.                                                               | Replace placeholder author names and roles before submission.                         |
| Generative AI declaration | Required when AI tools were used in writing or research.                | Keep the included AI-assisted writing statement, then revise for accuracy.            |

Sources: [IMU guide for authors](https://www.sciencedirect.com/journal/informatics-in-medicine-unlocked/publish/guide-for-authors), [CMPB Update guide for authors](https://www.sciencedirect.com/journal/computer-methods-and-programs-in-biomedicine-update/publish/guide-for-authors).

## Current evidence base to use

The manuscripts should use the full 2025-Q3 evaluation artifact, not the older small-draft evidence.

| Artifact | Current value |
|---|---|
| Snapshot quarter | 2025-Q3 |
| Build profile | full |
| Dataset schema | request_features_v4 |
| Feature version | research_v4 |
| Weak-label version | weak_label_v2 |
| Dataset rows | 33,961 |
| Scenarios | 600 |
| Train/test split | held out by scenario, 420 train scenarios and 180 test scenarios |
| Scenario source strategy | mixed |
| Scenario source mix | 180 benchmark, 300 PDE-derived, 120 stress |
| Scenario bundles | access-sensitive, insulin-chronic, low-utilizer, maintenance-generic, mixed-restriction, specialty-high-cost |
| Unique NDC count | 551 |
| ZIP count | 100 |
| Random seed | 42 |

## Journal-specific positioning

### Informatics in Medicine Unlocked

Lead with the health informatics problem: Medicare Part D plan comparison is cognitively difficult, policy-sensitive, and counseling-intensive. The contribution is a transparent, counselor-first decision-support stack that integrates public CMS plan data, fill-level out-of-pocket simulation, coverage and utilization-management explanations, and constrained reranking.

Use the IMU draft when the paper should emphasize:

- beneficiary and counselor workflow
- explainable rankings
- health communication and actionability
- medical informatics system design
- safe use of machine learning as an ordering layer, not as the source of truth

### Computer Methods and Programs in Biomedicine Update

Lead with the computational method: a reproducible DuckDB medallion pipeline, canonical data contracts, policy-aware cost simulation, scenario generation, and scenario-held-out reranking evaluation for Medicare Part D recommendation.

Use the CMPB Update draft when the paper should emphasize:

- data engineering and lineage
- algorithmic formalization
- cost simulation rules
- constrained hybrid reranking
- ablation evaluation and reproducibility

## Before submission

- Replace all `TODO` author metadata.
- Decide whether the submission will include code repository access, a frozen Zenodo archive, or "available on reasonable request".
- Confirm whether any local PDE-derived files have sharing restrictions.
- Export the selected manuscript to DOCX and create separate editable files for highlights, title page, declarations, and figures if the submission portal asks for them.
- Verify all references in Zotero or another citation manager before final upload.
