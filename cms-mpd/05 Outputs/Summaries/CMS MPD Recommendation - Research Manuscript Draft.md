---
title: CMS MPD Recommendation - Research Manuscript Draft
type: output/manuscript
status: draft
tags:
  - cms-mpd
  - output
  - manuscript
  - research-draft
  - project-review
created: 2026-04-06
updated: 2026-04-08
related_notes:
  - "[[CMS MPD Recommendation - Journal Manuscript Draft]]"
  - "[[CMS MPD Recommendation - Research Flow, Data Logic, and Algorithm]]"
  - "[[Source Index]]"
  - "[[Topic Map - Medicare Plan Knowledge]]"
  - "[[Source - Plan Selection and Decision Support Evidence]]"
  - "[[Source - SHIP Counseling and Beneficiary Navigation]]"
  - "[[Source - Part D Reform and IRA Timeline]]"
  - "[[Source - Extra Help and LIS Operations]]"
  - "[[Source - Insulin Affordability in Part D]]"
  - "[[Source - Drug Pricing and Formulary Distortions]]"
  - "[[Source - Part D Operations, Enrollment, and Bidding Guidance]]"
  - "[[Source - Part D Market Snapshots and Enrollment Trends]]"
  - "[[Source - MedPAC Part D Status Reports and Oversight]]"
  - "[[Source - Part D Insurer Incentives and Market Design]]"
  - "[[Source - Medicare Communication and Beneficiary Readability]]"
---

# CMS-MPD-Recommendation: A Counselor-First Medicare Part D Decision-Support Platform With Policy-Grounded Data Logic and Constrained Hybrid Reranking

> [!note]
> This revision reflects the updated `cms-mpd` vault and the current repository state reviewed on 2026-04-08.

## Abstract

Medicare Part D plan choice is difficult because the best plan depends on medication-specific coverage, pharmacy access, low-income subsidy status, utilization-management burden, and contract-year benefit rules rather than premium alone. The updated `cms-mpd` knowledge base shows that beneficiaries often fail to choose the least-cost plan without assistance, that SHIP counseling remains central to real-world navigation, and that post-IRA redesign changed both beneficiary liability and sponsor incentives. In response to that problem, `CMS-MPD-Recommendation` implements a counselor-first decision-support platform built on a DuckDB medallion pipeline. The system ingests local CMS SPUF `2025-Q3` files and reference data, transforms them into runtime-serving tables, simulates fill-level annual cost plan by plan, groups explanations into counseling-relevant categories, and optionally reranks already simulated plans using weak-label supervision. The current held-out-by-scenario evaluation artifact reports 1,774 rows across 32 scenarios, with `rules_only` top-1 agreement of `0.60` and `tree_reranker` top-1 agreement of `1.00` against the internal weak-label target while maintaining top-5 average uncovered drugs at `0.10`. These findings support internal coherence and a credible research workflow, but they do not yet constitute beneficiary-outcome validation.

## 1. Study Framing

This project should not be described as a generic recommender paper with Medicare data attached afterward. The task in this repository is much narrower and more practical:

1. a beneficiary has a known medication list, ZIP code, LIS status, and pharmacy preference;
2. candidate plans differ on coverage, tiering, utilization management, channel access, deductible exposure, insulin treatment, and contract-year rules;
3. the system must rank plans in a way that a beneficiary, caregiver, or counselor can inspect and explain.

The updated evidence base in `cms-mpd` makes that framing defensible. [[Source - Plan Selection and Decision Support Evidence]] documents persistent plan-choice inefficiency and measurable gains from guided decision support. [[Source - SHIP Counseling and Beneficiary Navigation]] shows that local, neutral counseling infrastructure remains central to plan comparison. [[Source - Medicare Communication and Beneficiary Readability]] adds that explanation burden is a direct barrier, not a side issue. Taken together, these notes argue that the problem is not only prediction. It is translation of policy and pricing detail into a beneficiary-specific decision.

## 2. Knowledge-Base Grounding and Related Work

The updated vault supports five related-work claims that matter for this study.

### 2.1 Plan-choice inefficiency is well established

The plan-selection evidence note shows that many beneficiaries do not enroll in their lowest expected cost plan and often leave money on the table even when public comparison tools exist. The CHOICE decision-aid work in that note is especially relevant because it connects user-centered interface design with plan choices that align more closely with expert reasoning.

### 2.2 SHIP-style workflows are part of the problem definition

The SHIP note shows that counseling is not an afterthought. Counselors routinely convert medication lists, LIS questions, enrollment timing, and pharmacy preferences into actual plan decisions. A useful Part D system therefore has to expose reasoning in a form that can support counseling dialogue.

### 2.3 The redesign era changed the meaning of affordability

The reform and LIS notes show that the current Part D environment is shaped by specific dates: January 1, 2024 for broader full-subsidy treatment and elimination of catastrophic 5 percent cost sharing, January 1, 2025 for the redesigned annual out-of-pocket cap, and January 1, 2026 for the first negotiated prices. This means contract-year awareness is not optional for a modern Part D recommendation system.

### 2.4 Pricing and formulary behavior are incentive shaped

The pricing-distortion, insurer-incentive, market-snapshot, and MedPAC notes show why premium-only or generic-only reasoning is unreliable. Out-of-pocket costs can diverge from intuitive expectations because of tier placement, coinsurance, exclusions, rebates, reinsurance design, benchmark pressure, and sponsor incentives. This supports plan-specific cost simulation and explanation-first outputs.

### 2.5 Broader health recommender literature is useful, but not task matched

Health recommender reviews remain useful for positioning because they show why knowledge-based and hybrid designs continue to matter in high-stakes settings. Even so, the present task differs from EHR-based medication recommendation and consumer interaction recommendation. `CMS-MPD-Recommendation` assumes the medication regimen is already known and asks which insurance plan best supports that regimen under policy and access constraints.

## 3. What This Study Contributes

The study contributes a policy-aware and counselor-usable system design rather than a new generic algorithm.

1. It operationalizes the Part D recommendation problem at the plan-comparison level for known regimens.
2. It connects the updated policy knowledge base to runtime logic for deductible handling, insulin rules, LIS adjustments, and 2025 redesign behavior.
3. It uses a medallion data model to preserve lineage from raw CMS files to recommendation outputs.
4. It treats grouped explanation output as part of the algorithm, not merely a reporting layer.
5. It restricts machine learning to reranking within coverage-preserving buckets after rules-first simulation.
6. It links recommendation, scenario generation, model training, evaluation, and research summaries to the same serving layer.

## 4. System Architecture and Data Logic

### 4.1 Source families

The repository uses five source families:

| Source family | Contents | Role |
| --- | --- | --- |
| CMS SPUF files | plan information, formulary, pricing, pharmacy network, geographic locator, exclusions, indication coverage, beneficiary-cost rules | raw authoritative Part D structure |
| RXCUI property shards | preferred names, synonyms, term types | medication identity and name resolution |
| `insulin_ref.csv` | insulin mappings | insulin-specific logic |
| `us_zipcode_geo.csv` and `pde.csv` | ZIP geography and utilization defaults | geography, quantity defaults, and scenario support |
| `cms-mpd` vault | reviewed evidence and topic synthesis | study framing and interpretation |

### 4.2 Canonical keys and transformation logic

The main business keys are `plan_key`, `contract_plan_key`, `formulary_id`, `zip_code`, `county_code`, `ndc`, `rxcui`, and normalized `days_supply`. These keys are what let the system move from sponsor files to beneficiary-level recommendation logic without collapsing plan, geography, and medication grains together incorrectly.

The medallion flow is:

- `bronze`: preserve CMS and reference sources with lineage fields
- `silver`: normalize plans, ZIP geography, service areas, drug reference, utilization defaults, plan-drug coverage, pharmacy facts, and cost rules
- `gold`: materialize serving tables for eligibility, network summary, formulary summary, plan-drug cost basis, drug defaults, plan summary, and recommendation features
- `synthetic`: store synthetic or PDE-compatible beneficiaries and prescriptions for model scenarios

Several transformations are methodologically central. `silver.bridge_plan_service_area` resolves county-based MA and region-based PDP service areas into a common bridge. `silver.fact_plan_drug_coverage` is the main plan x drug x day-supply fact table. `gold.plan_drug_cost_basis` then joins price, tier, utilization-management flags, deductible applicability, standard cost rules, and insulin overrides into the runtime table the engine actually uses.

### 4.3 Deterministic logic versus approximations

The project is strongest when three categories are kept separate.

- Raw truth: CMS SPUF files, RXCUI shards, insulin reference, ZIP reference.
- Deterministic derivation: plan keys, ZIP-to-county mapping, service-area expansion, formulary summary metrics, network flags, plan-drug cost basis.
- Approximation: PDE-derived quantity defaults, ZIP-centroid pharmacy distance, negotiated-price proxies, weak-label targets, synthetic beneficiary generation.

That separation is important because the study makes strong internal-coherence claims, not claims that every simulated dollar equals real adjudicated beneficiary cost.

### 4.4 Mathematical formalization of the data flow

The transformation path from raw sources to ranked plan outputs can be summarized as:

$$
\mathcal{R}
\xrightarrow{\mathcal{B}}
\mathcal{B}(\mathcal{R})
\xrightarrow{\mathcal{S}}
\mathcal{S}(\mathcal{B}(\mathcal{R}))
\xrightarrow{\mathcal{G}}
\mathcal{G}(\mathcal{S}(\mathcal{B}(\mathcal{R})))
\xrightarrow{\mathcal{Q}_b}
\Pi_b,
$$

where $\mathcal{R}$ is the family of raw CMS and reference inputs, $\mathcal{B}$ is bronze ingestion, $\mathcal{S}$ is silver normalization, $\mathcal{G}$ is gold serving-layer materialization, and $\Pi_b$ is the ranked plan set returned for beneficiary $b$.

At the table level, the central plan-drug transformation is:

$$
\text{GoldCostBasis}
=
\Big(
\text{DimPlan}
\bowtie_{formulary\_id}
\text{Formulary}
\bowtie_{plan\_key,ndc,s}
\text{Pricing}
\overset{\text{left}}{\bowtie}
\text{Exclusions}
\overset{\text{left}}{\bowtie}
\text{IndicationCoverage}
\overset{\text{left}}{\bowtie}
\text{DrugReference}
\Big)
\overset{\text{left}}{\bowtie}
\text{BenefitRules}
\overset{\text{left}}{\bowtie}
\text{InsulinRules},
$$

with normalized day supply $s \in \{30,60,90\}$. This equation makes the implementation claim explicit: plan rules become executable data only after being aligned to stable plan, drug, tier, channel, and day-supply keys.

## 5. Recommendation Workflow

The runtime recommendation engine is beneficiary specific. It takes ZIP code, age band, LIS status, chronic-condition flags, pharmacy preference, user role, decision focus, and a medication list. Medication identity can be resolved by exact NDC, exact RXCUI, exact preferred name, exact synonym, or prefix match.

The workflow is:

1. select eligible plans from `gold.plan_service_area` for the beneficiary ZIP;
2. normalize medications to supported day-supply values and fill in defaults from `gold.drug_input_defaults`;
3. load plan-drug rows from `gold.plan_drug_cost_basis` and channel summaries from `gold.plan_channel_summary`;
4. expand annual fills and simulate each feasible retail or mail channel;
5. apply deductible handling, standard cost-sharing or insulin overrides, LIS adjustments, and the annual OOP cap according to the resolved benefit design;
6. accumulate explanation items for uncovered drugs, missing prices, PA/ST/QL flags, deductible exposure, insulin dependence, pharmacy-access limits, and cap behavior;
7. assign rules-first rankings and fit scores that differ slightly by role and decision focus.

This design has two important consequences. First, recommendation truth comes from simulation and coverage logic rather than from a learned model. Second, the output is immediately counselor usable because the engine returns grouped explanations rather than only a scalar score.

In mathematical terms, if medication $d$ has $n_d$ annual fills, then the engine constructs:

$$
E_d = \left\{ \left(k, \operatorname{round}\left((k-1)\frac{365}{n_d}\right) \right) : k = 1, \dots, n_d \right\},
$$

and for plan $p$, fill $k$, and channel $c$, it uses the negotiated-price proxy:

$$
g_{pdkc} = \max(u_{pds}q_{dk} + f_{pc\tau s}, \phi_{pc}).
$$

In the 2025 branch, deductible, LIS, and annual-cap logic then act as sequential state updates:

$$
\delta_{pdkc} = \min(g_{pdkc}, D_{k-1}),
\qquad
o_{pdkc}^{2025} =
\begin{cases}
0, & O_{k-1} \geq 2000 \\
\min(L(c^{base}_{pdkc},\ell,\tau), 2000 - O_{k-1}), & O_{k-1} < 2000,
\end{cases}
$$

where $D_{k-1}$ is remaining deductible, $O_{k-1}$ is accumulated out-of-pocket spending, and $L(\cdot)$ is the LIS adjustment function.

The exported rules score is:

$$
R_p =
10000\,\mathbf{1}\{\text{coverage}_p=\text{full}\}
- T_p
- 250U_p
- 35H_p
- 20N_p,
$$

and the baseline order is lexicographic over coverage bucket, priced-drug count, fit score, annual total cost, uncovered-drug count, restriction count, and network status.

## 6. Research Dataset, Weak Labels, and Hybrid Reranking

The project does not train on observed beneficiary enrollment outcomes. Instead, it replays recommendation scenarios into a feature dataset. Scenario sources can come from synthetic beneficiaries or from PDE-compatible regimen generation.

For each scenario, `modeling.py` runs the rules engine, converts each returned plan into a feature row, augments those rows with `gold.recommendation_features`, and computes internal supervision targets. The current code declares:

- dataset schema version `request_features_v4`
- weak-label version `weak_label_v2`
- feature version `research_v4` in runtime recommendation outputs

The weak-label score strongly rewards full coverage and penalizes higher annual total cost, uncovered drugs, exclusions, missing prices, channel-unavailable drugs, restriction burden, approximate matches, mail-order dependency, insulin risk, and network risk. A simpler heuristic baseline uses a lighter penalty structure. Linear and tree rerankers are trained on those weak labels.

That internal target can be written as:

$$
W_p =
1000\,\mathbf{1}\{\text{coverage}_p=\text{full}\}
+ R_p
- T_p
- 250U_p
- 125E_p
- 110M_p
- 90C_p
- 25H_p
- 20A_p
- 18Mail_p
- 15Ins_p
- 12InsNP_p
- 20Net_p.
$$

The safety design is important. The learned model does not reorder every plan across the entire candidate set. Hybrid inference preserves coverage-oriented strata and reranks only within them. This means a weak-coverage plan cannot outrank a fully covered and fully priceable plan solely because of model score.

## 7. Evaluation and Current Findings

The checked-in evaluation JSON under `data/training/2025-Q3/full/hybrid_reranker_evaluation_tree.json` reports:

- held-out-by-scenario evaluation
- split seed `42`
- test fraction `0.3`
- `1774` dataset rows
- `32` scenarios
- `22` training scenarios and `10` test scenarios

System-level means in that artifact are:

| System | Top-1 | Top-5 overlap | Top-10 overlap | NDCG@5 | Top-5 avg uncovered |
| --- | --- | --- | --- | --- | --- |
| `rules_only` | `0.60` | `0.98` | `0.88` | `0.893` | `0.10` |
| `heuristic_baseline` | `0.70` | `1.00` | `0.91` | `0.912` | `0.10` |
| `linear_reranker` | `0.80` | `0.88` | `0.88` | `0.924` | `0.10` |
| `tree_reranker` | `1.00` | `1.00` | `0.97` | `1.000` | `0.10` |

The same report records `top5_improved = true`, `top10_improved = true`, and `uncovered_not_worse = true`. These are encouraging internal findings. They show that reranking can better reproduce the internal target without worsening uncovered-drug burden in the top five.

At the same time, the artifact state also shows a reproducibility caveat. The current dataset metadata file still reports `request_features_v2` and `research_v2`, while the evaluation JSON already reports `request_features_v4`. The research workflow is coherent, but stored artifacts are partially out of sync and should be rebuilt for strict reproducibility.

## 8. Claim Boundaries and Limitations

The study should keep its claims narrow and defensible.

1. It is not a novel generic recommendation architecture.
2. It is not a validated predictor of actual beneficiary enrollment behavior.
3. It is not a claims-adjudication engine.
4. It uses weak-label supervision rather than expert-adjudicated or outcome-based labels.
5. It relies partly on PDE-derived defaults and synthetic scenario construction.
6. It estimates pharmacy burden from ZIP centroids rather than travel-time or pharmacy-history data.

Those limits do not make the project weak. They define the stage of the work accurately: a strong counselor-support and research platform that still needs external validation.

## 9. Why The Study Still Matters

Even with those limits, the updated knowledge base shows why this project is worth studying. Part D plan choice is still a setting in which beneficiaries can lose money or access quality because the decision environment is too complex. SHIP remains operationally important because official materials and comparison tools do not remove that complexity. Policy redesign improved affordability, but it also made year-specific logic and explanation more important. Pricing and formulary behavior still create misleading surface signals. A system that integrates those realities into a single auditable workflow is useful even before outcome validation is complete.

## 10. Conclusion

`CMS-MPD-Recommendation` is best described as a counselor-first Medicare Part D decision-support platform with a built-in research workflow. Its core strength is not that it uses machine learning. Its core strength is that it joins policy-aware data transformation, beneficiary-specific cost simulation, explanation-first ranking, and constrained reranking in one inspectable architecture.

The current evidence supports manuscript claims about study framing, data logic, workflow coherence, and internal ranking evaluation. Stronger future claims should come from expert-reviewed counseling cases, matched comparisons against Medicare Plan Finder, or beneficiary-level outcome data.

## Internal Reference Base

- [[Source - Plan Selection and Decision Support Evidence]]
- [[Source - SHIP Counseling and Beneficiary Navigation]]
- [[Source - Medicare Communication and Beneficiary Readability]]
- [[Source - Part D Reform and IRA Timeline]]
- [[Source - Extra Help and LIS Operations]]
- [[Source - Insulin Affordability in Part D]]
- [[Source - Drug Pricing and Formulary Distortions]]
- [[Source - Part D Operations, Enrollment, and Bidding Guidance]]
- [[Source - Part D Market Snapshots and Enrollment Trends]]
- [[Source - MedPAC Part D Status Reports and Oversight]]
- [[Source - Part D Insurer Incentives and Market Design]]

## Appendix A. Implementation Anchors

- `src/cms_mpd/config.py`
- `src/cms_mpd/extract.py`
- `src/cms_mpd/pipeline.py`
- `src/cms_mpd/recommend.py`
- `scripts/generate_beneficiary_profiles.py`
- `src/cms_mpd/modeling.py`
- `src/cms_mpd/research_eval.py`
- `streamlit_app.py`
