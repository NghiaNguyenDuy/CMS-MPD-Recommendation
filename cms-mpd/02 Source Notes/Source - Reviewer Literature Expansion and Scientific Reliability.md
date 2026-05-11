---
title: Source - Reviewer Literature Expansion and Scientific Reliability
type: source-note
status: reviewed
tags:
  - cms-mpd
  - source/research
  - reviewer-revision
  - evidence-map
imported_on: 2026-04-21
retrieval_method: Bright Data MCP search and scrape
related_topics:
  - "[[Topic - Manuscript Scientific Reliability Evidence Map]]"
  - "[[Topic - Plan Finder and CMS Pricing Files]]"
  - "[[Topic - Drug Pricing and Formulary Dynamics]]"
  - "[[Topic - Part D Benefit Redesign]]"
---

# Summary

This note records the Bright Data MCP literature expansion for the reviewer-focused manuscript. The goal was not to add citations indiscriminately, but to strengthen the manuscript's scientific reliability across five reviewer-sensitive claims:

- Medicare Part D plan choice is empirically difficult and often non-optimal.
- Plan comparison tools work better when they simplify cost information and provide transparent recommendation support.
- CMS public plan-design files are an appropriate public data boundary, but their outputs require accuracy checks, eligibility filtering, and provenance disclosure.
- Exact medication identity through NDC/RXCUI is a methodological safety requirement, not a cosmetic preprocessing step.
- Health recommender systems should be evaluated beyond model metrics, with attention to interpretability, workflow fit, and real-world usability.

## Bright Data Search Scope

Searches targeted peer-reviewed or official sources in these clusters:

- Medicare Part D plan-choice complexity and switching behavior.
- Medicare Plan Finder usability, pricing accuracy, and decision-aid evidence.
- Formulary restrictions, pharmacy networks, and post-IRA plan-design changes.
- RxNorm, NDC, and drug-identity data infrastructure.
- Health recommender system evaluation and explainable clinical decision support.

## Reviewed Sources

| Source | Evidence type | Main manuscript claim supported | Manuscript use |
|---|---|---|---|
| Abaluck and Gruber, 2011, *American Economic Review*, DOI `10.1257/aer.101.4.1180` | Econometric plan-choice study | Beneficiaries can overweight premiums and underweight expected drug out-of-pocket costs | Strengthens related work on choice difficulty |
| Ketcham, Lucarelli, and Powers, 2015, *American Economic Review*, DOI `10.1257/aer.20120651` | Panel-data switching study | Some beneficiaries learn and switch when status-quo costs rise; plan choice is not uniformly inattentive | Adds balance and avoids overstating irrationality |
| McGarry, Maestas, and Grabowski, 2018, *Health Affairs*, DOI `10.1377/hlthaff.2018.0145` | Randomized hypothetical-choice experiment | Simplifying Plan Finder's default financial display helped older adults select lower-cost Part D plans | Supports concise, explanation-centered output |
| Bundorf et al., 2019, *Health Affairs*, DOI `10.1377/hlthaff.2018.05017` | Randomized decision-aid evaluation | Machine-based expert recommendations increased switching and satisfaction in CHOICE | Supports the hybrid decision-support framing |
| PCORI CHOICE report, DOI `10.25302/05.2020.CDR.130603598` | Funded research report | CHOICE included 928 beneficiaries ages 66-85 and compared decision aid, decision aid plus expert advice, and public information | Supports implementation and usability context |
| Bruine de Bruin and Hodson, 2024, *Health Affairs Scholar*, DOI `10.1093/haschl/qxae141` | National survey after 2024 open enrollment | 53% self-reported making no plan comparisons; non-comparison strongly aligned with non-switching | Supports workflow need for active comparison prompts |
| GAO-14-143, 2014 | Official oversight report | CMS uses data checks and quality measures for Plan Finder pricing accuracy and has assessed usability with feedback sources | Supports need for data-quality and external benchmark language |
| CMS formulary, pharmacy network, and pricing file page | Official data documentation | Public files include plan information, geography, formulary NDCs, UM indicators, beneficiary cost, pharmacy network, and quarterly pricing | Supports public replication boundary |
| NLM RxNorm technical documentation | Official terminology documentation | RxNorm normalizes clinical drug concepts and associates normalized NDCs with RXCUIs when correctness can be determined | Supports exact NDC/RXCUI resolution method |
| FDA National Drug Code Directory | Official identifier documentation | NDCs are FDA identifiers for listed drugs and are updated in the NDC Directory, but NDC presence does not imply coverage or reimbursement | Supports medication identity and coverage-boundary language |
| Cai et al., 2025, *JAMA Internal Medicine*, DOI `10.1001/jamainternmed.2025.4003` | Serial cross-sectional plan-design study | IRA-era plan design can shift deductibles, coinsurance, and beneficiary costs even with an out-of-pocket cap | Supports quarter-aware refresh requirement |
| Anderson et al., 2026, *Health Affairs*, DOI `10.1377/hlthaff.2025.00644` | Counterfactual trend study using 2021-2025 public-use files | 2025 IRA changes were associated with lower premiums, higher deductibles, and smaller formularies in some contexts | Supports post-IRA plan-design caution |
| Joyce, Chen, and Blaylock, 2026, *Health Affairs Scholar*, DOI `10.1093/haschl/qxag078` | Public-use file analysis | Differences between MA-PD and PDP financing may contribute to different coverage-option structures after IRA changes | Supports eligibility and plan-type boundary |
| Barbaric et al., 2025, *Digital Health*, DOI `10.1177/20552076241309386` | HRS scoping review | Health recommender systems need evaluation beyond algorithmic performance and should support collaborative decision-making | Supports workflow-oriented evaluation language |
| Ananthakrishnan et al., 2025, *International Journal of Medical Informatics*, DOI `10.1016/j.ijmedinf.2024.105697` | HRS evaluation scoping review | Robust real-world evaluations of HRS impact remain limited; evaluation criteria should be broader than model performance | Supports limitation and future-work framing |
| Xu et al., 2023, systematic review, DOI `10.1155/2023/9919269` | Explainable CDSS systematic review | Interpretability is essential for CDSS adoption; transparent models and explanation interfaces matter for clinicians and patients | Supports explainability rationale |

## Analytical Synthesis

### 1. Plan-choice difficulty is well supported, but should be stated with nuance.

Abaluck and Gruber provide strong evidence that beneficiaries can make choices inconsistent with full-information optimization. Ketcham et al. provide an important balancing result: some beneficiaries switch and respond to higher status-quo costs over time. The manuscript should therefore avoid a simplistic "beneficiaries are irrational" claim. A stronger scientific framing is that Part D choice is a complex, high-dimensional decision environment where many beneficiaries need decision support, while some learning and switching behavior exists.

### 2. Decision support should simplify and explain.

McGarry et al. and Bundorf et al. support the manuscript's design choice to prioritize total-cost estimates, visible recommendation logic, and expert-like guidance. The relevant point for CMS-MPD is not that a model should replace Plan Finder, but that a structured layer can reduce information burden and help users act on plan comparisons.

### 3. Public-file reproducibility is defensible, but not complete market truth.

CMS and GAO sources support use of public plan-design files while also supporting caution. CMS files contain the operational ingredients needed for formularies, cost sharing, networks, and pricing. GAO's Plan Finder oversight report shows that even official comparison outputs depend on data checks, sponsor correction, and usability feedback. This strengthens the manuscript's incomplete-observability boundary.

### 4. Exact medication identity is part of safety.

RxNorm and FDA NDC documentation justify the manuscript's exact NDC/RXCUI logic. NDC identifies listed drug packages, and RxNorm maps drug names and normalized NDCs to clinical-drug concepts. At the same time, FDA explicitly warns that NDC presence does not itself establish coverage or reimbursement. That distinction aligns closely with the manuscript's workflow: resolve drug identity first, then separately evaluate coverage.

### 5. Post-IRA plan behavior makes quarter-aware refresh mandatory.

Cai et al., Anderson et al., and Joyce et al. show that IRA-era redesign can shift plan premiums, deductibles, coinsurance, formularies, and coverage-option structure. This supports a manuscript claim that the system must be year-specific and quarter-specific, not a one-time static recommender.

### 6. HRS and CDSS literature support the rules-first plus constrained-reranking design.

The health recommender and explainable CDSS literature gives a general biomedical informatics rationale for this study. Recommender evaluation should include usability, implementation, and real-world fit. CDSS interpretability literature supports transparent rules, decision trees, feature importance, and explanation interfaces. This fits the manuscript's claim that the reranker should reorder already simulated facts rather than replace deterministic plan logic.

## Recommended Manuscript Strengthening

- Add a related-work paragraph that separates plan-choice inefficiency from learning/switching evidence.
- Add Plan Finder simplification and CHOICE expert-recommendation evidence to justify recommendation cards and concise explanation fields.
- Add NLM RxNorm and FDA NDC references to the medication-resolution subsection.
- Add post-IRA plan-design studies to the quarter-aware limitation.
- Add HRS/CDSS evaluation reviews to the discussion around explainability and evaluation beyond ranking metrics.

## Related Notes

- [[Topic - Manuscript Scientific Reliability Evidence Map]]
- [[Topic - Plan Finder and CMS Pricing Files]]
- [[Topic - Drug Pricing and Formulary Dynamics]]
- [[Topic - Part D Benefit Redesign]]
- [[Source - Plan Selection and Decision Support Evidence]]
- [[Source - Drug Pricing and Formulary Distortions]]
