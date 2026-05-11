---
title: CMS-MPD-Recommendation manuscript for Computer Methods and Programs in Biomedicine Update
date: 2026-04-15
status: submission-draft
target_journal: Computer Methods and Programs in Biomedicine Update
tags:
  - manuscript
  - cmpb-update
  - computational-methods
  - cms-mpd
aliases:
  - CMPB Update CMS-MPD manuscript
---

# A policy-aware medallion pipeline and constrained reranking method for Medicare Part D plan recommendation

> [!info] Submission preparation note
> Target journal: *Computer Methods and Programs in Biomedicine Update*. This draft is positioned as a computational method and software manuscript. Remove this note before journal upload. Related local notes: [[CMS MPD Journal Alignment and Submission Checklist]], [[CMS-MPD Technical Data Flow And Modeling Method]], [[CMS-MPD Architecture And Lineage]].

## Title page

**Title:** A policy-aware medallion pipeline and constrained reranking method for Medicare Part D plan recommendation

**Running title:** Policy-aware Part D recommendation method

**Authors:** TODO: Author 1; TODO: Author 2; TODO: Author 3

**Affiliations:** TODO

**Corresponding author:** TODO

**Article type:** Original software/methods research

## Highlights

- A DuckDB medallion pipeline standardizes CMS Part D plan data.
- Fill-level simulation estimates beneficiary annual out-of-pocket cost.
- Scenario-held-out evaluation used 33,961 rows from 600 scenarios.
- Tree reranking improved NDCG@5 from 0.830 to 0.953.
- Cost, restriction, and network features drove most ranking gains.

## Abstract

**Background:** Medicare Part D plan recommendation is computationally difficult because plan eligibility, formulary coverage, utilization management, pharmacy access, insulin rules, subsidy status, and annual out-of-pocket cost must be resolved jointly for a specific beneficiary medication regimen.

**Methods:** We developed CMS-MPD-Recommendation, a Python and DuckDB software pipeline that transforms public CMS 2025-Q3 Part D files into bronze, silver, and gold analytical layers. A rules-first recommendation engine resolves medication identity, restricts plans by ZIP eligibility, simulates fill-level annual out-of-pocket cost, and emits audit-ready explanations. We then constructed mixed-source recommendation scenarios and evaluated constrained reranking systems using a held-out-by-scenario split.

**Results:** The full dataset contained 33,961 plan-scenario rows from 600 scenarios, covering 100 ZIP codes, 460 regimen signatures, and 551 unique NDCs. On 180 held-out scenarios, the tree reranker achieved 0.861 top-1 agreement, 0.934 top-5 overlap, and 0.953 NDCG@5, compared with 0.622, 0.698, and 0.830 for rules-only ranking. Ablations showed that cost, utilization-management, and network features explained most performance gains.

**Conclusions:** The method demonstrates how policy-aware data engineering and deterministic cost simulation can be combined with constrained reranking for transparent Medicare Part D plan recommendation. External validation, prospective workflow testing, and adjudicated cost comparison remain future requirements.

## Keywords

Medicare Part D; biomedical software; decision support; data engineering; cost simulation; recommender systems; health informatics

## Glossary

| Term | Definition |
|---|---|
| CMS | Centers for Medicare & Medicaid Services. |
| Part D | Medicare outpatient prescription drug benefit. |
| SPUF | Public-use plan and formulary files used as source inputs in this study. |
| NDC | National Drug Code, normalized to 11 digits in this pipeline. |
| RXCUI | RxNorm concept identifier used for drug identity and search. |
| LIS | Low-income subsidy or Extra Help status that modifies beneficiary liability. |
| UM | Utilization management, including prior authorization, step therapy, and quantity limits. |
| Medallion pipeline | Layered data architecture using bronze raw, silver normalized, and gold serving tables. |
| Reranker | A model that changes the ordering of already simulated plan rows without creating new coverage or cost facts. |

## 1. Introduction

Prescription drug plan recommendation is a biomedical software problem with unusually strong policy and data-lineage constraints. For Medicare Part D, the recommendation target is not a single product or medication. It is a geographically eligible insurance plan whose value depends on the beneficiary's medication list, pharmacy preference, subsidy status, and expected filling behavior. The computational system must combine plan attributes, formularies, drug prices, cost-sharing rules, pharmacy networks, coverage restrictions, exclusions, indication-specific rules, insulin protections, and benefit-year policy changes.

Conventional recommender-system framing is incomplete for this task. A model that returns a top plan without explaining coverage, restrictions, pharmacy access, and cost assumptions is not adequate for counseling or biomedical decision support. Conversely, a purely rules-based ranking can be transparent but may underperform when many correlated plan attributes compete. The challenge is to combine deterministic simulation and interpretable data contracts with a constrained learning layer that can improve ordering without hiding safety-relevant facts.

CMS-MPD-Recommendation addresses this challenge with a local, reproducible, policy-aware software stack. The method has four major components:

- a DuckDB medallion pipeline that converts public CMS and reference files into auditable serving tables;
- a rules-first recommendation engine that resolves medications and simulates fill-level annual out-of-pocket cost;
- a scenario-generation and weak-labeling workflow for research evaluation;
- constrained reranking models evaluated on scenario-held-out splits with ablation analysis.

This manuscript describes the computational method, implementation logic, evaluation design, and current internal results.

## 2. System requirements and scope

The system was designed to support Medicare Part D plan comparison for a beneficiary-level request. A valid request includes ZIP code, medication list, low-income subsidy status, pharmacy preference, user role, and decision focus. Each medication may be specified by name, RXCUI, or NDC, with optional quantity, days supply, and annual fill count.

The method has the following requirements:

- restrict candidate plans to those eligible for the beneficiary ZIP code;
- normalize plan, drug, geography, and cost-rule keys before runtime recommendation;
- simulate beneficiary-facing annual out-of-pocket cost at fill level;
- handle insulin-specific rules separately from general cost-sharing rules;
- surface formulary coverage, prior authorization, step therapy, quantity limits, exclusions, indication restrictions, pharmacy access, deductible exposure, and evidence gaps;
- allow reranking only after deterministic simulation has produced auditable plan rows;
- evaluate ranking behavior under scenario-held-out splits rather than row-random leakage.

The method is not an adjudication engine and does not claim to replace official Medicare plan-selection tools. It is a research and decision-support method for transparent plan comparison.

## 3. Data sources and canonical data contracts

### 3.1 Source families

The 2025-Q3 full build used CMS source families for plan information, basic formulary, beneficiary cost, insulin beneficiary cost, pricing, geographic locator, excluded drugs, indication coverage, and pharmacy networks. Reference sources included RXCUI property shards, an insulin reference file, ZIP geography, and a PDE-compatible file used for utilization defaults and scenario generation.

### 3.2 Canonical keys

Correct joins are the central technical risk. The method defines canonical keys before runtime recommendation:

| Key | Construction | Purpose |
|---|---|---|
| `plan_key` | Contract ID + plan ID + segment ID, with missing segment mapped to `000`. | Plan grain across plan, pricing, formulary, pharmacy, and serving tables. |
| `contract_plan_key` | Contract ID + plan ID. | Joins files that omit segment grain. |
| `formulary_id` | CMS formulary identifier. | Connects plans to formulary membership. |
| `zip_code` | Five-digit normalized ZIP code. | Beneficiary geography and pharmacy geography. |
| `county_code` | CMS county geography code. | Service-area expansion. |
| `ndc` | Eleven-digit normalized National Drug Code. | Plan-drug-cost grain. |
| `rxcui` | Normalized RxNorm concept identifier. | Medication identity and search. |
| `days_supply` | Normalized to 30, 60, or 90. | Pricing and cost-rule matching. |
| `coverage_level` | CMS cost-rule coverage level. | Separates deductible and initial-coverage schedules. |
| `tier_level_value` | Integer formulary tier. | Cost-rule lookup and feature construction. |

## 4. Medallion data engineering method

### 4.1 Bronze layer

The bronze layer preserves raw CMS and reference inputs with minimal transformation. Each bronze table carries `source_file`, `snapshot_quarter`, and `load_ts` fields. Most bronze ingestion uses permissive string loading to reduce breakage from format variation. Pharmacy network ingestion is intentionally fault tolerant because CMS split files can contain malformed rows; the loader pads missing values and ignores bad rows so one malformed line does not block the full build.

### 4.2 Silver layer

The silver layer converts raw inputs into normalized business entities:

- `silver.dim_plan` creates the canonical plan dimension and service-area type;
- `silver.dim_zipcode` normalizes ZIP, county, state, latitude, longitude, population, and density;
- `silver.bridge_plan_service_area` expands plan eligibility to counties and ZIPs;
- `silver.dim_drug_reference` merges formulary, insulin, and RXCUI naming information;
- `silver.drug_utilization_defaults` estimates quantity and annual fill defaults;
- `silver.fact_plan_drug_coverage` joins formulary, pricing, UM, exclusions, indication restrictions, and insulin flags;
- `silver.fact_plan_pharmacy` normalizes retail and mail pharmacy network facts;
- `silver.plan_beneficiary_cost_rules` and `silver.plan_insulin_cost_rules` normalize cost-sharing rules.

### 4.3 Gold layer

The gold layer is the runtime serving model. It includes eligible ZIP-plan rows, plan summaries, pharmacy-channel summaries, preferred-pharmacy locations, formulary summaries, network summaries, plan-drug cost basis, drug input defaults, and compact recommendation features.

The key table is `gold.plan_drug_cost_basis`, which combines plan-drug-day-supply coverage with price, tier, UM flags, deductible applicability, standard cost-sharing rules, and insulin overrides. This table allows the recommendation engine to avoid repeatedly joining large raw CMS inputs during runtime.

## 5. Recommendation algorithm

### 5.1 Problem formulation

Let a request scenario be:

$$
s = (z, M, l, h, r, f)
$$

where `z` is beneficiary ZIP code, `M` is the medication set, `l` is low-income subsidy status, `h` is pharmacy preference, `r` is user role, and `f` is decision focus. Let `P_z` be the set of plans serving ZIP `z`. The runtime engine computes a plan evidence vector:

$$
x_{p,s} = g(p, s, D)
$$

where `D` is the gold serving layer and `g` is the deterministic simulation function. The initial ranking score is a transparent function of coverage, cost, restrictions, pharmacy access, insulin logic, deductible exposure, and evidence gaps:

$$
score_{p,s}^{rules} = R(x_{p,s})
$$

The optional reranker estimates:

$$
score_{p,s}^{model} = F(x_{p,s})
$$

but it is constrained to reorder only the existing rows `p in P_z`; it cannot change coverage, cost, or eligibility facts.

### 5.2 Medication resolution

Medication resolution uses the following sequence:

1. exact NDC;
2. exact RXCUI;
3. exact preferred name;
4. exact synonym;
5. prefix match on preferred name or synonym.

Approximate matches are retained as evidence gaps. This prevents a plan from appearing definitive when medication identity is uncertain.

### 5.3 Fill-level cost simulation

For each candidate plan and medication, the runtime engine retrieves plan-drug cost basis, normalized days supply, quantity, annual fill count, tier, coverage status, UM flags, insulin flag, deductible applicability, channel prices, and applicable cost-sharing rules.

For each fill, the simulation computes a base allowed amount and beneficiary liability according to channel, tier, deductible status, benefit-design mode, insulin override, and low-income subsidy adjustment. Annual plan cost is aggregated across fills and medications:

$$
OOP_{p,s} = \sum_{m \in M} \sum_{t=1}^{fills(m)} liability(p, m, t, l, h)
$$

The engine also emits per-drug and per-fill trace information so a recommendation can be audited.

### 5.4 Ranking and explanations

Rules-first ranking prioritizes complete medication coverage, lower estimated annual out-of-pocket cost, lower restriction burden, pharmacy fit, insulin safety, and lower evidence-gap burden. The output includes plan-level scores, annual cost estimates, covered and uncovered drug counts, restriction summaries, network flags, deductible signals, insulin flags, and explanation groups.

The explanation layer is part of the algorithmic output. It is not added after ranking. This matters because a plan with a favorable numerical score may still require human review if it has an uncovered drug, restrictive prior authorization, no preferred retail access, or uncertain medication matching.

## 6. Reranking and weak-label construction

### 6.1 Dataset generation

The model dataset is generated by replaying canonical scenarios through the same recommendation engine used at runtime. Each row represents a plan under a scenario. The current dataset uses schema `request_features_v4`, feature version `research_v4`, weak-label version `weak_label_v2`, and student-safe feature policy.

The full dataset contains 33,961 rows from 600 scenarios. Scenario source strategy is mixed: 180 benchmark scenarios, 300 PDE-derived scenarios, and 120 stress scenarios. Six scenario bundles are balanced at 100 scenarios each: access-sensitive, insulin-chronic, low-utilizer, maintenance-generic, mixed-restriction, and specialty-high-cost.

### 6.2 Weak labels

Weak labels encode the study's recommendation preference structure rather than an external clinical gold standard. They reward safer and more useful plan rows by combining cost, coverage, restriction, network, insulin, and evidence-gap information. This label design allows supervised evaluation while preserving the limitation that agreement with the label is not equivalent to beneficiary outcome validity.

### 6.3 Reranking systems

The evaluated systems include:

- rules-only ranking;
- heuristic baseline;
- linear reranker;
- tree reranker;
- cost-only ablation;
- cost plus restrictions ablation;
- cost plus restrictions plus network ablation;
- full ablation.

The tree reranker is the primary learned model because it can capture nonlinear interactions among interpretable features while still being restricted to deterministic input rows.

## 7. Experimental design

Evaluation used held-out-by-scenario splitting with random seed 42. The training set contained 420 scenarios and 23,384 plan-scenario rows. The test set contained 180 scenarios and 10,577 rows. Splitting by scenario rather than row reduces leakage from the same beneficiary-regimen request appearing in both training and test rows.

Metrics included:

- top-1 agreement with the weak-label ranking;
- top-5 and top-10 overlap;
- NDCG@5 and NDCG@10;
- top-k full-coverage rate;
- average top-k total cost;
- average uncovered medication count;
- blocker-classification precision;
- review-trigger rate;
- missing-data behavior.

Acceptance flags tracked whether top-5 and top-10 agreement improved and whether uncovered medications were not worse.

## 8. Results

### 8.1 Dataset characteristics

The 2025-Q3 full evaluation artifact contained 33,961 rows, 600 scenarios, 100 ZIP codes, 460 regimen signatures, and 551 unique NDCs. All 88 dataset chunks were completed. The build used generator seed 42 and the mixed-source scenario strategy.

### 8.2 Overall ranking performance

**Table 1. Held-out-by-scenario ranking performance.**

| System | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | NDCG@10 | Top-5 avg cost | Top-5 avg uncovered | Blocker precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules only | 0.622 | 0.698 | 0.786 | 0.830 | 0.828 | 198.10 | 0.414 | 0.950 |
| Heuristic baseline | 0.811 | 0.899 | 0.953 | 0.924 | 0.920 | 81.79 | 0.463 | 0.989 |
| Linear reranker | 0.628 | 0.879 | 0.919 | 0.899 | 0.890 | 83.06 | 0.459 | 0.994 |
| Tree reranker | 0.861 | 0.934 | 0.962 | 0.953 | 0.947 | 83.07 | 0.459 | 0.994 |

The tree reranker improved ranking agreement and NDCG relative to rules-only ranking. It also improved top-1 agreement, top-5 overlap, top-10 overlap, and NDCG relative to the heuristic baseline, while retaining similar average top-5 cost. The linear reranker improved overlap and NDCG relative to rules-only ranking but underperformed the heuristic baseline in top-1 agreement.

### 8.3 Ablation performance

**Table 2. Ablation results.**

| System | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | Top-5 avg cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Cost only | 0.806 | 0.882 | 0.935 | 0.926 | 80.75 | 0.469 |
| Cost plus restrictions | 0.833 | 0.903 | 0.954 | 0.937 | 82.57 | 0.460 |
| Cost plus restrictions plus network | 0.872 | 0.950 | 0.973 | 0.960 | 82.99 | 0.459 |
| Full feature set | 0.867 | 0.940 | 0.971 | 0.957 | 82.94 | 0.459 |

The cost plus restrictions plus network ablation performed slightly better than the full feature set on several ranking metrics. This result suggests that core interpretable features explain most of the learnable signal. It also warns against assuming that adding more features necessarily improves decision-support behavior.

### 8.4 Scenario-bundle performance

**Table 3. Tree-reranker results by scenario bundle.**

| Scenario bundle | Top-1 agreement | Top-5 overlap | NDCG@5 | Top-5 full coverage | Top-5 avg cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Access-sensitive | 1.000 | 0.979 | 1.000 | 0.771 | 112.81 | 0.307 |
| Insulin-chronic | 0.886 | 0.954 | 0.950 | 0.909 | 40.04 | 0.091 |
| Low-utilizer | 0.844 | 0.938 | 0.956 | 0.656 | 85.75 | 0.375 |
| Maintenance-generic | 0.762 | 0.895 | 0.894 | 0.790 | 90.64 | 0.248 |
| Mixed-restriction | 0.875 | 0.950 | 0.980 | 0.475 | 101.25 | 0.775 |
| Specialty-high-cost | 0.781 | 0.881 | 0.923 | 0.394 | 78.27 | 0.900 |

Performance was strongest for access-sensitive scenarios and weakest for specialty-high-cost scenarios. High uncovered-medication counts in mixed-restriction and specialty-high-cost scenarios show that ranking metrics must be interpreted together with coverage-risk metrics.

### 8.5 Acceptance guardrails

The evaluation artifact marked top-5 and top-10 improvement as true, but uncovered-not-worse as false. The practical implication is that reranking improved ordering metrics but did not fully satisfy the coverage-risk guardrail. Therefore, the model should remain an assistive reranker with visible blockers rather than an autonomous plan-selection mechanism.

## 9. Software architecture and reproducibility

The software is implemented as a local Python package with DuckDB as the analytical store. The major modules are:

- configuration and source discovery;
- extraction of CMS and reference files;
- pipeline construction for bronze, silver, gold, and synthetic schemas;
- recommendation and decision-support logic;
- drug input resolution;
- scenario generation;
- dataset build, model training, and evaluation;
- Streamlit user interface support.

The reproducibility boundary is defined by the source snapshot quarter, build profile, generator seed, dataset schema version, feature version, weak-label version, and scenario manifest. For the current artifact, these are `2025-Q3`, `full`, seed `42`, `request_features_v4`, `research_v4`, `weak_label_v2`, and mixed-source scenarios.

To reproduce the analysis, a user should:

1. obtain the same CMS source snapshot and reference files;
2. run the extraction and medallion pipeline build;
3. materialize canonical training scenarios;
4. build the reranker dataset;
5. run held-out-by-scenario evaluation;
6. compare the generated metadata and evaluation JSON against the reported artifact.

TODO: Add final repository URL, release tag, archived artifact DOI, and exact command sequence before submission.

## 10. Discussion

This study shows that Medicare Part D plan recommendation can be structured as a policy-aware computational pipeline rather than a monolithic prediction task. The core design decision is to separate deterministic evidence generation from learned ordering. The medallion pipeline normalizes official source data into auditable tables. The rules engine simulates annual out-of-pocket cost and creates explanations. The reranker then works only on the simulated rows.

The ablation results are encouraging for transparency. Cost, utilization-management, and pharmacy-network features accounted for most of the observed gains. These features are understandable to counselors and beneficiaries, which makes model behavior easier to inspect. The fact that the full feature set did not dominate the simpler cost-restriction-network ablation also supports a conservative modeling posture: a smaller, interpretable feature set may be preferable unless additional features demonstrate clear benefit without worsening safety metrics.

The uncovered-not-worse guardrail is an important negative finding. In biomedical decision support, improved ranking agreement is insufficient if the system can increase exposure to uncovered drugs. Future versions should treat uncovered-medication risk as a hard constraint, a lexicographic priority, or an explicit multi-objective optimization target rather than only a feature in a learned ranking score.

## 11. Limitations

The current results are internal and scenario-based. Weak-label agreement is not a clinical gold standard, and the scenarios do not establish that beneficiaries would choose better plans, spend less after enrollment, or experience improved medication access. Public CMS files may not fully reproduce real pharmacy-specific adjudication. Pharmacy-distance logic based on ZIP centroids is approximate. Quantity and annual-fill defaults depend on PDE-compatible assumptions and may not match an individual beneficiary.

The system has not yet been prospectively evaluated with counselors or beneficiaries. It also lacks formal runtime benchmarking, external replication across future CMS quarters, and comparison against official plan-finder outputs under controlled medication cases.

## 12. Conclusions

CMS-MPD-Recommendation provides a reproducible computational method for policy-aware Medicare Part D plan recommendation. The method combines medallion data engineering, canonical data contracts, deterministic fill-level cost simulation, counselor-visible explanations, mixed-source scenario generation, and constrained reranking. In the 2025-Q3 internal evaluation, tree reranking improved ranking agreement and NDCG over rules-only ranking, while ablations showed that interpretable cost, restriction, and network features drove most gains. The method is suitable for further research and validation, not yet for autonomous plan selection.

## Declarations

### Ethics approval and consent to participate

This manuscript draft reports a software and internal scenario-evaluation study using public CMS plan data and generated or PDE-compatible research scenarios. No direct human-participant intervention is reported. TODO: Confirm institutional review board status before submission.

### Consent for publication

Not applicable. No identifiable personal health information is presented.

### Availability of data and materials

Public CMS source data are available from CMS. Derived artifacts can be shared subject to source-data terms, data-use restrictions, and removal of non-shareable inputs. TODO: Add repository, release tag, and archive DOI if the code and derived artifacts will be deposited.

### Competing interests

TODO: The authors declare no competing interests, if accurate.

### Funding

TODO: State funding source or "This research received no specific grant from any funding agency in the public, commercial, or not-for-profit sectors."

### Authors' contributions

TODO: Add CRediT statement. Suggested roles include conceptualization, data curation, formal analysis, methodology, software, validation, visualization, writing - original draft, and writing - review and editing.

### Acknowledgements

TODO: Add acknowledgements if applicable.

### Declaration of generative AI and AI-assisted technologies

During preparation of this manuscript draft, OpenAI Codex/ChatGPT was used to help organize study notes, align the draft with journal instructions, and edit manuscript language. The authors reviewed and are responsible for all content, interpretations, results, and conclusions. No generative AI or AI-assisted tool was used to create or alter study figures in this draft.

## Suggested figures and supplementary files

**Figure 1.** End-to-end medallion pipeline from CMS source files to runtime serving tables.

**Figure 2.** Recommendation algorithm showing medication resolution, ZIP eligibility, fill-level cost simulation, explanations, and optional reranking.

**Figure 3.** Scenario generation and held-out-by-scenario evaluation design.

**Supplementary File S1.** Data dictionary for bronze, silver, gold, and synthetic tables.

**Supplementary File S2.** Feature dictionary for reranker and ablation systems.

**Supplementary File S3.** Reproducibility manifest containing snapshot quarter, schema versions, seed, command sequence, and artifact checksums.

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
