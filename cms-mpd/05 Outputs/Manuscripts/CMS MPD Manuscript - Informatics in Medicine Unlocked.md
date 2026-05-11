---
title: CMS-MPD-Recommendation manuscript for Informatics in Medicine Unlocked
date: 2026-04-15
status: submission-draft
target_journal: Informatics in Medicine Unlocked
tags:
  - manuscript
  - informatics-in-medicine-unlocked
  - decision-support
  - cms-mpd
aliases:
  - IMU CMS-MPD manuscript
---

# CMS-MPD-Recommendation: A counselor-centered informatics platform for explainable Medicare Part D plan comparison

> [!info] Submission preparation note
> Target journal: *Informatics in Medicine Unlocked*. This draft is aligned to the journal's open access and guide-for-authors pages. Remove this note before journal upload. Related local notes: [[CMS MPD Journal Alignment and Submission Checklist]], [[CMS MPD Recommendation - Research Flow, Data Logic, and Algorithm]], [[CMS-MPD Architecture And Lineage]].

## Title page

**Title:** CMS-MPD-Recommendation: A counselor-centered informatics platform for explainable Medicare Part D plan comparison

**Running title:** Explainable Medicare Part D plan comparison

**Authors:** TODO: Author 1; TODO: Author 2; TODO: Author 3

**Affiliations:** TODO

**Corresponding author:** TODO

**Article type:** Original research / health informatics systems research

## Highlights

- A counselor-first platform explains Medicare Part D plan tradeoffs.
- CMS 2025-Q3 files are transformed into auditable serving tables.
- Fill-level cost simulation ranks plans before optional reranking.
- Tree reranking reached 0.861 top-1 agreement on held-out scenarios.
- Coverage, insulin, pharmacy, and UM risks remain visible to users.

## Abstract

**Background:** Medicare Part D plan selection requires beneficiaries and counselors to compare premiums, formularies, pharmacy access, utilization management, deductibles, insulin rules, and annual out-of-pocket cost. Existing tools often expose plan data but leave users with a cognitively demanding interpretation task.

**Objective:** We developed and evaluated CMS-MPD-Recommendation, a counselor-centered informatics platform for explainable Medicare Part D plan comparison.

**Methods:** Public CMS 2025-Q3 Part D plan, formulary, pricing, pharmacy, geography, beneficiary-cost, exclusion, and indication files were transformed through a DuckDB medallion pipeline into runtime serving tables. A rules-first engine resolved beneficiary ZIP code and medications, simulated fill-level annual out-of-pocket cost, and generated plan explanations for coverage, utilization management, insulin, pharmacy access, deductible exposure, and evidence gaps. A constrained hybrid reranker was trained on 33,961 plan-scenario rows from 600 mixed-source scenarios and evaluated on a held-out-by-scenario split.

**Results:** The tree reranker achieved 0.861 top-1 agreement, 0.934 top-5 overlap, and 0.953 NDCG@5 on 180 held-out scenarios, compared with 0.622, 0.698, and 0.830 for rules-only ranking. The heuristic baseline remained strong, and ablation results showed that cost, utilization-management, and network features explained most gains. Reranking improved ranking agreement but did not eliminate coverage-risk tradeoffs.

**Conclusions:** CMS-MPD-Recommendation demonstrates a transparent, counselor-facing informatics architecture for Medicare Part D plan comparison. The current evidence supports internal coherence and research readiness, but prospective counselor use, beneficiary comprehension, and real-world outcome validation remain necessary.

## Keywords

Medicare Part D; clinical decision support; health informatics; prescription drug plans; explainable recommendation; pharmacy benefits; out-of-pocket cost

## 1. Introduction

Medicare Part D plan choice is a high-stakes health informatics problem. A beneficiary's best plan depends not only on monthly premium, but also on formulary coverage, tier placement, utilization-management requirements, preferred pharmacy access, deductible rules, insulin protections, low-income subsidy status, and expected use of specific drugs over the plan year. The decision is therefore structured by policy, local geography, plan-specific data, and patient-specific medication needs.

The practical difficulty is well documented. Beneficiaries frequently do not select the lowest-cost plan that fits their medication needs, even when lower-cost options are available [1-3]. Counseling and navigation programs can improve plan comparison, but they also reveal that the task is not simply "show a ranking." It requires translation of plan data into advice that a beneficiary can understand and act on [4,5]. Recent Part D policy changes, including the Inflation Reduction Act and 2025 redesign, add further complexity because the same plan and medication mix can produce different beneficiary liability under different contract-year rules [6-9].

This study addresses Medicare Part D plan comparison as a medical informatics workflow rather than as a generic recommender-system problem. The goal is not to replace counselors with an opaque model. The goal is to build an auditable decision-support stack that can ingest official plan data, simulate beneficiary-facing cost, preserve coverage and access risks, and explain why a plan appears safe, affordable, or problematic.

CMS-MPD-Recommendation was designed around that premise. It combines a curated knowledge base, a reproducible local data pipeline, a rules-first recommendation engine, a counselor-facing user interface, and an optional constrained reranker. The machine-learning layer never creates plans, imputes hidden coverage, or overrides core safety facts. It only reranks plan rows already simulated by deterministic logic.

The study makes four contributions:

- It describes an end-to-end informatics architecture for Medicare Part D plan comparison using public CMS source files.
- It formalizes a counselor-centered explanation model covering coverage, utilization management, insulin, pharmacy access, deductible exposure, and data gaps.
- It evaluates a constrained reranking strategy on mixed-source Medicare Part D scenarios while preserving auditability.
- It identifies current validation gaps that must be closed before clinical, counseling, or public deployment.

## 2. Background and related work

### 2.1 Medicare Part D plan selection

Medicare Part D plan choice is a recurrent annual decision for many beneficiaries. The available plan set varies by geography, and beneficiary out-of-pocket cost depends on the interaction between the plan benefit design and the person's medication list. Prior work has shown that many beneficiaries remain in plans that are not the lowest-cost option for their medication needs [3]. Online decision aids and patient-centered comparison tools can improve the decision process, but usability studies also show that beneficiaries need understandable summaries, not only access to raw plan attributes [1,2].

### 2.2 Counseling as the real workflow

State Health Insurance Assistance Program-style counseling reframes plan comparison as an interactive process. Counselors elicit medications, pharmacy preferences, subsidy status, and beneficiary priorities, then explain tradeoffs. A recommendation system for this setting should therefore expose the evidence behind each plan, including when a plan is low cost but has uncovered drugs, prior authorization, step therapy, quantity limits, limited preferred pharmacy access, or missing match confidence.

### 2.3 Policy and market context

Recent Part D reforms altered beneficiary liability, especially through insulin affordability provisions and the 2025 redesign [6-9]. At the same time, formulary strategy and utilization restrictions remain active plan-management tools [10-15]. These dynamics mean that a static premium-only or formulary-only ranking is insufficient. The decision-support system must be policy-aware and contract-year-aware.

### 2.4 Health recommender-system mismatch

Health recommender-system reviews emphasize a persistent gap between algorithmic performance metrics and clinical or health-service usefulness [16,17]. For Medicare Part D counseling, the relevant task is not only to maximize agreement with a learned label. A useful system must retain explanations, identify uncertainty, and avoid hiding safety-relevant facts behind a single score.

## 3. Materials and methods

### 3.1 Study design

We conducted a systems-development and internal-evaluation study of CMS-MPD-Recommendation, a local Medicare Part D decision-support platform. The unit of recommendation was an eligible plan for a beneficiary ZIP code and medication regimen. The unit of evaluation was a plan-scenario row generated by replaying recommendation scenarios through the runtime engine.

### 3.2 Data sources

The platform used public CMS 2025-Q3 Part D source files covering plan information, formulary membership, pricing, pharmacy networks, geography, beneficiary cost rules, insulin beneficiary cost rules, excluded drugs, and indication coverage. Additional reference inputs included RXCUI property shards for drug naming, an insulin reference file for insulin identification, ZIP geography, and a PDE-compatible file used for utilization defaults and scenario generation. The local study snapshot was `2025-Q3`; the build profile was `full`.

No identifiable beneficiary record was used as a clinical outcome target. Scenario data were used to exercise medication-regimen, ZIP, plan, and policy combinations and to build weak-label training rows.

### 3.3 Knowledge-base-driven design

The Obsidian knowledge base organized policy notes, imported articles, source summaries, and study concepts. These notes shaped the implementation requirements:

- rankings should prioritize full medication coverage and annual out-of-pocket cost rather than premium alone;
- explanations should be grouped into counselor-relevant categories;
- insulin rules should be handled separately from general cost-sharing rules;
- low-income subsidy status should modify beneficiary liability;
- pharmacy access should be visible, not hidden in a score;
- approximate medication matches and missing data should be surfaced as evidence gaps.

### 3.4 Data engineering architecture

CMS-MPD-Recommendation uses a DuckDB medallion architecture. The bronze layer preserves source files with lineage columns. The silver layer normalizes plan, ZIP, drug, formulary, pharmacy, beneficiary-cost, and insulin-cost entities. The gold layer materializes serving tables for runtime recommendation, Streamlit user-interface views, and model dataset generation.

Key canonical identifiers include `plan_key`, constructed from contract, plan, and segment identifiers; `contract_plan_key`, used where CMS files omit segment grain; five-digit `zip_code`; county code; normalized 11-digit NDC; RXCUI; day supply; tier; and coverage-level codes. This key discipline is central because erroneous joins can change both plan eligibility and cost simulation.

The runtime-serving tables include ZIP-plan service area, plan summaries, formulary summaries, network summaries, drug cost basis, drug input defaults, preferred pharmacy locations, and compact recommendation features.

### 3.5 Recommendation workflow

The runtime engine accepts beneficiary ZIP code, medication list, low-income subsidy status, pharmacy preference, user role, and decision focus. Medication resolution proceeds from exact NDC, to exact RXCUI, to preferred drug name, synonym, and prefix matches. Approximate matches are preserved for review.

The engine first restricts candidate plans to those serving the beneficiary ZIP code. It then resolves medication quantities and annual fill counts, using user input when available and PDE-derived defaults otherwise. For each plan-drug pair, it reads the plan-drug cost basis, coverage status, tier, utilization-management flags, insulin indicator, deductible applicability, pricing basis, and channel information.

Annual out-of-pocket simulation is performed at the fill level. The engine applies contract-year-aware benefit design logic, uses insulin-specific overrides where applicable, applies low-income subsidy adjustments after base cost computation, and aggregates the resulting beneficiary-facing annual cost. The rules engine is the source of truth for cost and explanation logic.

### 3.6 Explanation model

Each plan is returned with structured explanations. Explanation groups include:

- coverage fit, including covered and uncovered medications;
- utilization management, including prior authorization, step therapy, and quantity limits;
- insulin-specific affordability flags;
- preferred retail, nonpreferred retail, and mail pharmacy access;
- deductible exposure and cost-sharing logic;
- total estimated annual out-of-pocket cost;
- match confidence and data-quality gaps.

This design intentionally separates rank from interpretation. A low-cost plan can still be flagged if it has uncovered drugs, restrictive utilization management, limited pharmacy access, or uncertain medication matching.

### 3.7 Hybrid reranking

The study evaluated an optional hybrid reranker. The reranker operates only on rows already produced by the deterministic recommendation engine. It does not generate eligibility, coverage, or cost facts. Training rows include plan-level, regimen-level, cost, coverage, restriction, network, and request-context features under dataset schema `request_features_v4` and feature version `research_v4`.

Weak labels were generated under `weak_label_v2`, using a student-safe feature policy. The evaluated systems were rules-only ranking, heuristic baseline, linear reranker, tree reranker, and ablation variants using progressively richer feature groups.

### 3.8 Scenario generation and evaluation

The full dataset contained 33,961 plan-scenario rows from 600 mixed-source scenarios. Scenario sources included 180 benchmark scenarios, 300 PDE-derived scenarios, and 120 stress scenarios. Six scenario bundles were represented: access-sensitive, insulin-chronic, low-utilizer, maintenance-generic, mixed-restriction, and specialty-high-cost, with 100 scenarios per bundle. The scenario set covered 100 ZIP codes, 460 regimen signatures, and 551 unique NDCs.

Evaluation used a held-out-by-scenario split with random seed 42. The training set contained 420 scenarios and 23,384 rows; the test set contained 180 scenarios and 10,577 rows. Metrics included top-1 agreement, top-5 overlap, top-10 overlap, normalized discounted cumulative gain at 5 and 10, top-k full-coverage rate, average top-k total cost, average uncovered medications, blocker-classification precision, missing-data behavior, and review-trigger rate.

## 4. Results

### 4.1 System capabilities

The platform produced ZIP-eligible plan rankings, annual cost estimates, plan-drug coverage traces, utilization-management flags, insulin-specific cost logic, preferred-pharmacy access summaries, side-by-side plan comparisons, and counselor-ready explanation groups. The same runtime logic supported command-line evaluation and the Streamlit decision-support workflow.

### 4.2 Overall ranking results

Table 1 summarizes held-out-by-scenario evaluation results on 180 test scenarios.

**Table 1. Held-out ranking performance.**

| System | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | NDCG@10 | Top-5 avg cost | Top-5 avg uncovered | Blocker precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules only | 0.622 | 0.698 | 0.786 | 0.830 | 0.828 | 198.10 | 0.414 | 0.950 |
| Heuristic baseline | 0.811 | 0.899 | 0.953 | 0.924 | 0.920 | 81.79 | 0.463 | 0.989 |
| Linear reranker | 0.628 | 0.879 | 0.919 | 0.899 | 0.890 | 83.06 | 0.459 | 0.994 |
| Tree reranker | 0.861 | 0.934 | 0.962 | 0.953 | 0.947 | 83.07 | 0.459 | 0.994 |

Compared with rules-only ranking, the tree reranker improved top-1 agreement by 0.239 absolute points, top-5 overlap by 0.237, and NDCG@5 by 0.123. The tree reranker also substantially reduced average top-5 cost relative to rules-only ranking. Compared with the heuristic baseline, the tree reranker improved top-1 agreement, top-5 overlap, top-10 overlap, and NDCG, while average top-5 total cost was similar.

### 4.3 Ablation results

The ablation analysis showed that cost, restriction, and network information accounted for most of the ranking gains. The cost-only ablation achieved 0.806 top-1 agreement and 0.926 NDCG@5. Adding restriction features increased top-1 agreement to 0.833 and NDCG@5 to 0.937. Adding network features produced 0.872 top-1 agreement and 0.960 NDCG@5. The full ablation reached 0.867 top-1 agreement and 0.957 NDCG@5.

These results are useful for informatics interpretation. The model did not require a black-box feature universe to perform well. Most observed improvement came from features that are understandable in counseling: cost, coverage restrictions, and pharmacy-network access.

### 4.4 Scenario-bundle results

The tree reranker performed differently across scenario types (Table 2).

**Table 2. Tree-reranker performance by scenario bundle.**

| Scenario bundle | Top-1 agreement | Top-5 overlap | NDCG@5 | Top-5 full coverage | Top-5 avg cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Access-sensitive | 1.000 | 0.979 | 1.000 | 0.771 | 112.81 | 0.307 |
| Insulin-chronic | 0.886 | 0.954 | 0.950 | 0.909 | 40.04 | 0.091 |
| Low-utilizer | 0.844 | 0.938 | 0.956 | 0.656 | 85.75 | 0.375 |
| Maintenance-generic | 0.762 | 0.895 | 0.894 | 0.790 | 90.64 | 0.248 |
| Mixed-restriction | 0.875 | 0.950 | 0.980 | 0.475 | 101.25 | 0.775 |
| Specialty-high-cost | 0.781 | 0.881 | 0.923 | 0.394 | 78.27 | 0.900 |

The access-sensitive and insulin-chronic bundles showed strong ranking agreement and NDCG. Specialty-high-cost and maintenance-generic scenarios were more difficult. Mixed-restriction and specialty-high-cost scenarios also had higher average uncovered-medication counts, indicating that rank quality should not be interpreted without coverage-risk explanations.

### 4.5 Safety and review behavior

The evaluation artifacts indicated improved top-5 and top-10 agreement, but the uncovered-not-worse acceptance guardrail was not fully satisfied. This matters because a system can improve ranking agreement while still exposing users to tradeoffs involving uncovered medications. The study therefore treats reranking as an assistive ordering layer, not as autonomous plan selection. Counselor-facing review triggers and blocker explanations remain required.

## 5. Discussion

CMS-MPD-Recommendation demonstrates how a domain-specific health informatics platform can make Medicare Part D plan comparison more transparent. The main contribution is the integration of policy-aware data engineering, fill-level cost simulation, and counselor-oriented explanation into a single workflow. The optional reranker improved several internal ranking metrics, but the study's practical value depends on the system's ability to show why a plan is recommended and where it may be unsafe.

The results also clarify what kind of machine learning is appropriate for this setting. A generic recommender that directly predicts the "best" plan would be difficult to audit and could hide high-consequence facts. In this platform, deterministic simulation creates the evidence base first. Reranking can then adjust the presentation order, but the user still sees coverage, cost, insulin, utilization-management, pharmacy, and evidence-gap details.

For an informatics audience, the key lesson is that explanation is not a cosmetic feature. In Medicare Part D, explanation is part of the intervention. Beneficiaries and counselors need to know whether a plan is lower cost because it truly covers the regimen, because it shifts risk through restrictions, because it assumes a particular pharmacy channel, or because data are incomplete.

The ablation results support this design choice. Cost, restriction, and network features explained much of the gain. These are not abstract latent features; they are interpretable plan-comparison concepts. This creates a path for counselor-facing model governance: if a reranker changes plan order, the system can show which transparent factors contributed to that change.

## 6. Limitations

This study is an internal systems-development and evaluation study. It does not measure beneficiary plan switching, medication adherence, out-of-pocket spending after enrollment, complaint rates, or health outcomes. It also does not compare recommendations against production claims adjudication or all possible pharmacy-specific negotiated-price combinations.

The cost simulation depends on public CMS files, local transformations, normalized identifiers, and assumptions about quantities, fills per year, pharmacy channel, and benefit design. PDE-compatible inputs were used for utilization defaults and scenario generation, not as direct evidence of patient outcomes. ZIP-centroid pharmacy access is an approximation and may not represent individual transportation constraints.

The weak-label target is not a clinical gold standard. It encodes a study-specific preference structure, and the held-out-by-scenario evaluation tests internal generalization rather than external validity. The uncovered-not-worse guardrail indicates that reranking still requires human-readable safety review.

Finally, the current platform has not yet been evaluated with counselors or beneficiaries. Usability, comprehension, trust calibration, and workflow burden should be tested before deployment.

## 7. Future work

Future work should include prospective counselor usability testing, beneficiary comprehension studies, external validation against official plan-finder outputs or adjudicated cost examples, robustness testing across future CMS quarters, and sensitivity analyses for drug quantities, pharmacy channel choices, LIS status, and policy-year assumptions.

The platform should also be prepared for reproducible release by freezing source-data versions, publishing data dictionaries, separating shareable derived artifacts from restricted local inputs, and documenting all transformations from raw CMS files to recommendation outputs.

## 8. Conclusions

CMS-MPD-Recommendation provides a practical, explainable informatics architecture for Medicare Part D plan comparison. In the current 2025-Q3 internal evaluation, a constrained tree reranker improved ranking agreement and NDCG over rules-only ranking while preserving counselor-visible explanations. The system is best viewed as research-ready decision support: promising for counselor-assisted plan comparison, but requiring prospective workflow, usability, and outcome validation before real-world deployment.

## Declarations

### Ethics approval and consent to participate

This study used public CMS plan data and internally generated or PDE-compatible research scenarios. No direct intervention with human participants was performed for this manuscript draft. TODO: Confirm whether institutional review board review is exempt, not required, or required before submission.

### Consent for publication

Not applicable. The manuscript does not report identifiable individual-level clinical information.

### Availability of data and materials

Public CMS Part D source files are available from CMS. Derived tables, scenario manifests, and evaluation artifacts can be made available subject to source-data licensing, local data-use restrictions, and removal of any non-shareable inputs. TODO: Add repository or archive URL if code and artifacts will be deposited.

### Competing interests

TODO: The authors declare no competing interests, if accurate.

### Funding

TODO: State funding source or "This research received no specific grant from any funding agency in the public, commercial, or not-for-profit sectors."

### Authors' contributions

TODO: Add CRediT author contribution statement. Suggested roles include conceptualization, data curation, formal analysis, methodology, software, validation, visualization, writing - original draft, and writing - review and editing.

### Acknowledgements

TODO: Add acknowledgements if applicable.

### Declaration of generative AI and AI-assisted technologies

During preparation of this manuscript draft, OpenAI Codex/ChatGPT was used to help organize study notes, align the draft with journal instructions, and edit manuscript language. The authors reviewed and are responsible for all content, interpretations, results, and conclusions. No generative AI or AI-assisted tool was used to create or alter study figures in this draft.

## Suggested figures and tables

**Figure 1.** Counselor-centered CMS-MPD workflow from intake to plan explanation.

**Figure 2.** Medallion architecture from CMS source files to bronze, silver, gold, runtime, and evaluation layers.

**Figure 3.** Reranking evaluation design with scenario-held-out split.

**Table 1.** Held-out ranking performance.

**Table 2.** Tree-reranker performance by scenario bundle.

**Supplementary Table S1.** Data-source and table-lineage dictionary.

**Supplementary Table S2.** Feature groups used in reranker and ablation systems.

## References

1. Bundorf MK, Stults CD, Klimke R, Meehan A, Chan AS, Polyakova M, Tai-Seale M. *Using an Online Decision Aid to Help Medicare Beneficiaries Choose a Prescription Drug Plan*. Washington, DC: Patient-Centered Outcomes Research Institute; 2020.
2. Stults CD, Fattahi S, Meehan A, et al. Comparative usability study of a newly created patient-centered tool and Medicare.gov Plan Finder to help Medicare beneficiaries choose prescription drug plans. *Journal of Patient Experience*. 2019;6(1):81-86.
3. Zhou C, Zhang Y. The vast majority of Medicare Part D beneficiaries still do not choose the cheapest plans that meet their medication needs. *Health Affairs*. 2012;31(10):2259-2265.
4. Hohmann LA, Hastings TJ, McFarland SJ, Hollingsworth JC, Westrick SC. Implementation of a Medicare plan selection assistance program through a community partnership. *American Journal of Pharmaceutical Education*. 2018;82(9):6452. doi:10.5688/ajpe6452
5. Aruru M, Salmon JW. Assessment of Medicare Part D communications to beneficiaries. *American Health & Drug Benefits*. 2010;3(5):310-317.
6. Centers for Medicare & Medicaid Services. *The Inflation Reduction Act Lowers Health Care Costs for Millions of Americans*. Fact sheet. October 5, 2022.
7. Centers for Medicare & Medicaid Services. *Final CY 2025 Part D Redesign Program Instructions Fact Sheet*. April 1, 2024.
8. Centers for Medicare & Medicaid Services. *Medicare Advantage and Medicare Prescription Drug Programs to Remain Stable as CMS Implements Improvements to the Programs in 2025*. Press release. September 27, 2024.
9. Centers for Medicare & Medicaid Services. *Medicare Drug Price Negotiation Program: Negotiated Prices for Initial Price Applicability Year 2026*. Fact sheet. August 15, 2024.
10. Joyce G, Blaylock B, Chen J, Van Nuys K. Medicare Part D plans greatly increased utilization restrictions on prescription drugs, 2011-20. *Health Affairs*. 2024;43(3):391-397. doi:10.1377/hlthaff.2023.00999
11. Dusetzina SB, Jazowski S, Cole A, Nguyen J. Sending the wrong price signal: why do some brand-name drugs cost Medicare beneficiaries less than generics? *Health Affairs*. 2019;38(7):1188-1194. doi:10.1377/hlthaff.2018.05476
12. Dusetzina SB, Cubanski J, Nshuti L, True S, Hoadley J, Roberts D, Neuman T. Medicare Part D plans rarely cover brand-name drugs when generics are available. *Health Affairs*. 2020;39(8):1326-1333. doi:10.1377/hlthaff.2019.01694
13. Trish E, Blaylock B, Van Nuys K. Cost sharing for preferred branded drugs in Medicare Part D. *JAMA*. 2025;333(13):1170-1172. doi:10.1001/jama.2024.28092
14. Lavetti K, Simon K. Strategic formulary design in Medicare Part D plans. *American Economic Journal: Economic Policy*. 2018;10(3):154-192. doi:10.1257/pol.20160248
15. Buttorff C, James HO, Sorbero ME, Reid RO. Medicare Part D insulin coverage: formulary strategies amid policy headwinds. *Health Affairs Scholar*. 2025;3(4):qxaf042. doi:10.1093/haschl/qxaf042
16. Cai Y, Yu F, Kumar M, Gladney R, Mostafa J. Health recommender systems development, usage, and evaluation from 2010 to 2022: a scoping review. *International Journal of Environmental Research and Public Health*. 2022;19(22):15115.
17. Ananthakrishnan A, Milne-Ives M, Cong C, Meinert E. The evaluation of health recommender systems: a scoping review. *International Journal of Medical Informatics*. 2025;195:105697.
