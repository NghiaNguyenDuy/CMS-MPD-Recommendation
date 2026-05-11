---
title: CMS MPD Recommendation - Journal Manuscript Draft
type: output/manuscript
status: draft
tags:
  - cms-mpd
  - output
  - manuscript
  - journal-draft
  - project-review
created: 2026-04-06
updated: 2026-04-08
related_notes:
  - "[[CMS MPD Recommendation - Research Manuscript Draft]]"
  - "[[CMS MPD Recommendation - Research Flow, Data Logic, and Algorithm]]"
---

# CMS-MPD-Recommendation: A Counselor-Oriented Medicare Part D Decision-Support Study Grounded in Policy-Aware Cost Simulation, Explainable Ranking, and Constrained Hybrid Reranking

> [!note]
> This revised draft reflects direct literature review and repository inspection completed on 2026-04-08.

## Abstract

**Background:** Medicare Part D plan choice remains difficult because beneficiary welfare depends on medication-specific coverage, utilization-management restrictions, pharmacy-channel access, low-income subsidy status, and contract-year policy rules rather than premium alone. Recent policy analyses show that the January 1, 2024 and January 1, 2025 redesign steps improved affordability while increasing the importance of date-aware interpretation, counseling, and explanation [6-9].  
**Objective:** To present `CMS-MPD-Recommendation` clearly as a counselor-oriented Medicare Part D decision-support study and to assess its contribution as an integrated policy-aware recommendation platform rather than as a generic recommender architecture.  
**Materials and Methods:** The manuscript synthesizes published literature and policy reports together with direct inspection of the local repository, including the DuckDB data pipeline, recommendation engine, modeling workflow, and checked-in evaluation artifacts for the `2025-Q3` snapshot. Particular attention is given to related work, data logic and transformation, runtime recommendation workflow, and the constrained role of machine learning in reranking.  
**Results:** The project ingests local CMS SPUF plan, formulary, pricing, pharmacy, geography, and beneficiary-cost files; normalizes them through `bronze`, `silver`, and `gold` layers; and performs beneficiary-specific fill-level cost simulation with deductible, insulin, LIS, pharmacy-channel, and annual out-of-pocket-cap logic. A hybrid reranker then optionally reorders already simulated candidate plans within safety-preserving coverage strata. The current held-out-by-scenario evaluation artifact reports 1,774 plan rows across 32 scenarios, with 22 training scenarios and 10 test scenarios. Against weak-label pseudo-ground truth, `rules_only` achieved top-1 agreement of `0.60`, while the current `tree_reranker` artifact achieved `1.00`; top-10 overlap improved from `0.88` to `0.97`, and top-5 average uncovered drugs remained `0.10`.  
**Conclusions:** The study's main contribution is not a novel general-purpose recommendation model. Its defensible contribution is the integration of Medicare policy knowledge, auditable data transformation, fill-level cost simulation, counselor-aligned explanations, and constrained reranking in a single research and decision-support stack. Current evidence supports internal coherence and research readiness, but not yet external validation against beneficiary outcomes or production claims adjudication.

**Keywords:** Medicare Part D; decision support; SHIP counseling; formulary analytics; cost simulation; explainable recommendation; hybrid reranking

## 1. Introduction

Choosing a Medicare Part D plan is a case-specific decision problem, not a standard consumer price-comparison task. A beneficiary's best option depends on whether each medication is covered, how it is tiered, whether prior authorization, step therapy, or quantity limits apply, whether the beneficiary relies on retail or mail fulfillment, and whether low-income subsidy status changes actual out-of-pocket liability. Prior work shows that many beneficiaries do not enroll in the least-cost plan without assistance, while decision-support and counseling interventions can improve switching behavior, usability, and projected savings [1-4].

This task became more sensitive after the staged redesign of Part D. Policy analyses and program summaries document that the catastrophic 5 percent beneficiary coinsurance ended on January 1, 2024, the redesigned $2,000 annual out-of-pocket cap took effect on January 1, 2025, and negotiated prices for the first selected Part D drugs took effect on January 1, 2026 [6-9]. These changes improved affordability, but they also made year-specific interpretation more important because older evidence, older beneficiary materials, and older pricing intuitions no longer map cleanly to the post-redesign environment.

The present project, `CMS-MPD-Recommendation`, addresses this environment as a counselor-oriented decision-support platform. The system is not intended to replace formal claims adjudication or to claim state-of-the-art status in generic recommendation research. Instead, it combines a DuckDB medallion pipeline, beneficiary-specific fill-level simulation, explanation-first plan comparison, and an optional constrained reranking layer. Its problem framing is motivated by published evidence on plan-selection inefficiency, counseling-oriented assistance, readability barriers, pricing distortions, insurer incentives, and redesign-era program change [1-15].

This manuscript therefore positions the study as a health decision-support and policy analytics contribution. The core question is not whether the project introduces a novel universal recommender. The question is whether it correctly frames the Part D task, preserves auditability from CMS source files to recommendation outputs, supports counselor-style explanation, and provides a credible research path for improving plan ranking without weakening coverage safeguards.

## 2. Related Work

### 2.1 Medicare plan choice and decision-support evidence

The literature most directly matched to this study concerns beneficiary plan choice and decision support. Administrative-data and decision-aid studies consistently show that Medicare beneficiaries often do not enroll in the most cost-effective Part D plan, with avoidable overspending that can remain substantial even after beneficiaries gain experience in the market [1-3]. The CHOICE program and its usability evaluation are especially relevant because they show that user-centered decision tools can improve plan switching and satisfaction while also making the choice environment easier to navigate [1,2]. This body of work matters because it frames the problem as a recurring failure of unaided plan selection rather than as a theoretical optimization exercise.

That same evidence also clarifies what a useful plan-comparison tool must do. Narrowing choices alone is insufficient if beneficiaries cannot interpret annual cost exposure, drug restrictions, or plan-detail pages [1-3]. The literature therefore supports a design in which recommendation quality depends on cost simulation, clear tradeoff presentation, and explanation categories that match how people actually review plans.

### 2.2 Counseling, navigation, and communication infrastructure

The second relevant body of work concerns counseling and communication. Community-based and SHIP-linked assistance models show that one-to-one Medicare counseling can produce meaningful projected savings, strong participant satisfaction, and a workflow centered on prescription entry, plan comparison, and explanation rather than pure score output [4]. This is not a peripheral observation. It implies that a practical Part D system should be counselor-compatible and explanation-first, not just score-driven.

The communication literature reaches the same conclusion from another angle. Readability analysis of Medicare beneficiary materials shows that official communications can be technically accurate yet still exceed the reading level of many beneficiaries, especially in Part D sections involving formularies, enrollment, appeals, and low-income assistance [5]. Together, these findings suggest that explanation is not an optional user-interface layer. It is part of the task definition. A system that produces rankings without interpretable coverage, access, and cost logic would be poorly matched to the communication burden documented in the literature.

### 2.3 Policy redesign, market change, and sponsor operations

The third strand of related work concerns the redesign-era policy environment. Part D after January 1, 2025 cannot be analyzed with the same assumptions used for older four-phase benefit discussions. Policy briefs and program reports show that full-subsidy treatment expanded beginning January 1, 2024 for broader low-income groups, the annual out-of-pocket cap changed the structure of beneficiary liability in 2025, and payment smoothing changed the timing of payments even when it did not change the total owed [6-9].

Market snapshots and oversight reports broaden this picture. Recent analyses show that enrollment keeps growing while stand-alone PDP menus shrink, sponsor concentration remains high, and benchmark-plan pressure continues to matter for LIS beneficiaries [7-9]. These materials matter because they anchor the study in the actual operating environment of Part D, not only in beneficiary-facing abstractions.

### 2.4 Formulary strategy, pricing distortions, and insurer incentives

Another relevant literature addresses why plan design can look inconsistent or confusing from the beneficiary side. Recent studies show that list price, generic status, negotiated cost, and beneficiary out-of-pocket cost do not map neatly to one another [10-13]. The same literature documents growth in utilization-management restrictions, persistent formulary distortions, and situations in which brand drugs can create lower beneficiary cost than generics. This evidence strongly supports fill-level plan simulation rather than premium-first or generic-first heuristics.

Program-design research adds an explanation for this behavior. Studies of Part D formulary strategy and welfare design show that formularies and pricing strategies reflect not only clinical coverage choices but also the interaction of risk adjustment, subsidy design, integration incentives, and selection incentives [9,14]. Recent insulin formulary research further shows how changing policy can alter tiering and management behavior without eliminating plan heterogeneity [15]. Together, these sources support a study design that treats plan behavior as policy-shaped and sponsor-incentive-sensitive rather than as simple retail pricing.

### 2.5 Health recommender systems and the task mismatch problem

Broader health recommender research is relevant for positioning, but it is not the direct comparator. Existing scoping reviews of health recommender systems show a heterogeneous field in which knowledge-based and hybrid methods remain common when safety, interpretability, and controllability matter more than raw predictive lift [16,17]. The present study fits that pattern. It does not recommend medications from electronic health records or optimize repeated consumer interactions. It ranks insurance plans for a known medication regimen under policy, geography, subsidy, and access constraints.

This task difference matters. Many modern recommender systems assume dense interaction data, repeated exposure, and objectives such as relevance, engagement, or conversion. Medicare Part D choice is low frequency, high stakes, and explanation dependent. For that reason, the study uses broader recommender literature only for conceptual placement. Its task-matched comparators are rules-based ranking, heuristic ranking, and constrained reranking within a policy-aware cost-simulation stack.

## 3. Objective and Study Contributions

The objective of this manuscript is to present `CMS-MPD-Recommendation` clearly as an integrated Medicare Part D decision-support study and to assess what the project contributes relative to the published Part D literature and the current codebase.

This study makes six contributions that are defensible within that scope.

1. It frames the recommendation problem at the correct decision level: plan ranking for a beneficiary with a known medication regimen, not medication prediction and not premium-only sorting.
2. It integrates current Part D policy knowledge into contract-year-aware runtime logic, including deductible handling, insulin-specific protections, LIS effects, and the post-2025 annual out-of-pocket-cap structure.
3. It preserves explicit data lineage from raw CMS source files to normalized business entities and runtime-serving tables through a DuckDB `bronze -> silver -> gold` pipeline.
4. It treats explanation as a core analytic output by surfacing coverage, utilization-management, pharmacy-access, deductible, insulin, and cost-logic issues in counselor-readable groups.
5. It adds a constrained hybrid reranking workflow in which machine learning refines the order of already simulated plan candidates without overriding the authoritative rules-based coverage and cost logic.
6. It creates a single research environment in which literature-grounded problem framing, runtime recommendation, synthetic or PDE-compatible scenario generation, model fitting, and evaluation all use the same serving layer.

The main novelty claim is therefore system-level and task-level rather than algorithmic. The contribution is the integration of established technical elements into a Medicare-specific, counselor-usable, policy-aware decision-support stack.

## 4. Materials and Methods

### 4.1 Literature and repository review

This manuscript is grounded in two linked evidence sources. The first is the domain literature and policy-report base on Part D plan choice, decision support, counseling-oriented assistance, readability, redesign-era policy change, plan-market trends, pricing distortions, and sponsor incentives [1-15].

The second source is the local `CMS-MPD-Recommendation` repository, including the project `README`, `docs/architecture-lineage.md`, `docs/technical-data-flow-modeling.md`, `docs/study-research-flow-data-logic-algorithm.md`, runtime modules under `src/cms_mpd/`, and the checked-in training and evaluation artifacts under `data/training/2025-Q3/full/`.

### 4.2 Data sources and analytical scope

The implementation combines four practical data families and one evidence layer.

| Family | Main contents | Role in the study |
| --- | --- | --- |
| CMS SPUF files | plan information, formulary, pricing, pharmacy network, geographic locator, exclusions, indication coverage, beneficiary-cost rules | authoritative plan, drug, geography, and rule inputs |
| Reference CSVs | `insulin_ref.csv`, `us_zipcode_geo.csv`, `pde.csv` | insulin identification, ZIP geography, and utilization defaults or scenario support |
| RXCUI property shards | preferred names, synonyms, term types | medication-name resolution and user input matching |
| Project artifacts | DuckDB tables, dataset metadata, evaluation JSON | runtime serving, modeling, and evaluation evidence |
| Published literature and policy reports | articles and reports cited in this manuscript | policy framing, related work, and interpretation |

The current checked-in implementation is centered on the `2025-Q3` snapshot. That matters methodologically because the runtime cost logic is built around the 2025 redesign branch by default, while historical `2024_standard` logic remains available for explicit backward-looking comparison.

### 4.3 Data logic and transformation

The project uses a medallion architecture with `bronze`, `silver`, `gold`, and `synthetic` schemas. The transformation logic is important because the study depends on stable business keys and auditable lineage rather than on opaque feature generation.

The main canonical keys are:

- `plan_key`, constructed from `CONTRACT_ID + PLAN_ID + SEGMENT_ID`
- `contract_plan_key`, used where CMS files omit segment grain
- `formulary_id`, linking plans to formulary rows
- `zip_code` and `county_code`, linking beneficiaries and pharmacies to service areas
- `ndc` and `rxcui`, linking medication identity, naming, and price rows
- `days_supply`, normalized to `30`, `60`, or `90`

The transformation stages are:

| Layer | Main logic | Main outputs |
| --- | --- | --- |
| `bronze` | permissive ingestion of CMS and reference files with lineage metadata | raw tables close to source format |
| `silver` | normalization of plans, ZIP geography, service-area bridges, drug reference, utilization defaults, plan-drug coverage, pharmacy facts, and cost rules | reusable business entities |
| `gold` | serving-layer materialization for eligibility, network summary, formulary summary, plan-drug cost basis, plan summary, drug defaults, and modeling features | runtime and modeling tables |
| `synthetic` | scenario-support tables for synthetic or PDE-compatible beneficiaries and prescriptions | training and evaluation inputs |

Several silver and gold transformations are central to the study. `silver.dim_plan` creates the canonical plan grain. `silver.dim_zipcode` standardizes ZIP-to-county geography and density context. `silver.bridge_plan_service_area` resolves the mismatch between county-based MA service areas and PDP region-based service areas. `silver.fact_plan_drug_coverage` joins formulary membership, pricing, utilization-management flags, exclusion signals, indication restrictions, and insulin identity at the plan-drug-day-supply level. `gold.plan_drug_cost_basis` then assembles those elements into the runtime-ready table used by the recommendation engine.

This design separates raw truth, deterministic derivation, and approximation. Raw truth comes from CMS source files, RXCUI properties, and reference tables. Deterministic derivation includes plan keys, ZIP-to-county mapping, service-area expansion, formulary summary metrics, and network flags. Approximation enters later through PDE-based quantity defaults, ZIP-centroid distance, negotiated-price proxies, and weak-label targets. That distinction is necessary for an honest manuscript because the system is auditable, but it is not claims-adjudication-exact.

### 4.4 Mathematical formalization of flow and rules

The transformation from source data to ranked plans can be expressed as a composition:

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

where $\mathcal{R}$ is the raw CMS and reference input family, $\mathcal{B}$ is bronze ingestion, $\mathcal{S}$ is silver normalization, $\mathcal{G}$ is gold serving-layer materialization, and $\Pi_b$ is the ranked plan set for beneficiary $b$.

At the table level, the core plan-drug fact is:

$$
\text{SilverCoverage}
=
\gamma_{plan\_key,ndc,s}
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
\Big),
$$

and the runtime cost basis is:

$$
\text{GoldCostBasis}
=
\text{SilverCoverage}
\overset{\text{left}}{\bowtie}
\text{BenefitRules}
\overset{\text{left}}{\bowtie}
\text{InsulinRules}.
$$

These expressions make the study's main design claim more concrete: policy rules become executable data objects after being joined to plan, drug, tier, day-supply, and channel keys.

### 4.5 Runtime recommendation workflow

At inference time, the engine accepts a beneficiary ZIP code, age band, LIS status, chronic-condition flags, pharmacy preference, user role, decision focus, and medication list. Medication identity can be resolved by exact NDC, exact RXCUI, exact preferred name, exact synonym, or prefix match on a name field. Approximate matches are preserved and surfaced later as evidence gaps rather than silently treated as exact matches.

The runtime workflow follows six steps.

1. **Candidate-plan selection:** plans are restricted to the beneficiary ZIP by querying `gold.plan_service_area` and joining `gold.plan_summary` and `gold.plan_network_summary`.
2. **Medication normalization:** each drug is normalized to a supported day-supply value, assigned a tier family if needed, and supplemented with default quantity and fills-per-year values from `gold.drug_input_defaults`.
3. **Plan-drug retrieval:** for each candidate plan and medication, the engine loads the relevant row from `gold.plan_drug_cost_basis` together with channel summary and preferred-pharmacy location data.
4. **Fill-level simulation:** the engine expands annual fills, simulates each feasible channel, applies deductible rules, standard cost-sharing or insulin overrides, LIS adjustments, and the annual cap, then selects the cheapest feasible channel subject to continuity rules that reduce unrealistic switching.
5. **Explanation generation:** coverage gaps, missing prices, utilization-management flags, deductible exposure, insulin dependence, pharmacy-access limits, and annual cap behavior are grouped into counselor-readable explanation categories.
6. **Rules-first ranking:** fully covered and fully priceable plans are prioritized; within that structure, fit score, annual total cost, uncovered-drug burden, restriction count, and network status guide ordering.

This workflow matters because it shows that recommendation truth is generated by policy-aware simulation first. Machine learning is not allowed to replace that first-stage logic.

### 4.6 Mathematical view of runtime scoring

For medication $d$ with $n_d$ annual fills, the engine constructs fill events:

$$
E_d = \left\{ \left(k, \operatorname{round}\left((k-1)\frac{365}{n_d}\right) \right) : k = 1, \dots, n_d \right\}.
$$

For plan $p$, fill $k$, and feasible channel $c$, the negotiated-price proxy is:

$$
g_{pdkc} = \max(u_{pds}q_{dk} + f_{pc\tau s}, \phi_{pc}),
$$

where $u_{pds}$ is unit cost, $q_{dk}$ is fill quantity, $f_{pc\tau s}$ is channel-specific dispensing fee, and $\phi_{pc}$ is the channel floor price.

The 2025 branch applies deductible, benefit-rule, LIS, and annual-cap updates in sequence:

$$
\delta_{pdkc} = \min(g_{pdkc}, D_{k-1}),
$$

$$
L(c,\ell,\tau)=
\begin{cases}
\min(c,4.90), & \ell=\text{full},\ \tau=\text{generic} \\
\min(c,12.15), & \ell=\text{full},\ \tau=\text{brand} \\
\min(0.75c,12.00), & \ell=\text{partial},\ \tau=\text{generic} \\
\min(0.75c,35.00), & \ell=\text{partial},\ \tau=\text{brand} \\
c, & \ell=\text{none},
\end{cases}
$$

$$
o_{pdkc}^{2025} =
\begin{cases}
0, & O_{k-1} \geq 2000 \\
\min(L(c^{base}_{pdkc},\ell,\tau), 2000 - O_{k-1}), & O_{k-1} < 2000.
\end{cases}
$$

The exported rules score is:

$$
R_p =
10000\,\mathbf{1}\{\text{coverage}_p=\text{full}\}
- T_p
- 250U_p
- 35H_p
- 20N_p,
$$

where $T_p$ is annual total cost, $U_p$ uncovered-drug count, $H_p$ restriction count, and $N_p$ network penalty.

The fit score is a weighted composite:

$$
F_p = w_c S_p^{cost} + w_m S_p^{premium} + w_v S_p^{coverage} + w_a S_p^{access} + w_s S_p^{stability},
$$

followed by a coverage guardrail that floors fully covered plans and caps non-full-coverage plans below 60. In implementation, baseline ranking is lexicographic over coverage bucket, priced-drug count, fit score, annual total cost, uncovered-drug count, restriction count, and network status.

### 4.7 Research workflow and constrained hybrid reranking

The research path reuses the runtime engine rather than bypassing it. `scripts/generate_beneficiary_profiles.py` can generate synthetic beneficiaries or PDE-compatible regimens. `modeling.py` then replays recommendation scenarios into a plan-level feature dataset. The current code declares dataset schema `request_features_v4` and weak-label version `weak_label_v2`. Feature families include current rules outputs, cost and access burden, request-specific match quality, network status, plan-level summary metrics, and beneficiary context.

Because observed beneficiary-choice labels are not present in the local environment, the workflow uses a weak-label target that strongly rewards full coverage and penalizes uncovered drugs, exclusions, missing prices, access problems, restriction burden, approximate matches, insulin risk, mail-order dependency, and higher annual total cost. Linear and tree rerankers are then trained on those weak labels.

Importantly, hybrid inference is constrained. The learned model reranks only within coverage-based strata rather than across the full candidate list. Fully covered and fully priceable plans remain separated from weaker coverage buckets. This is a deliberate safety design: learning can refine order within clinically safer comparison sets, but it cannot erase the primary role of coverage completeness and rules-based simulation.

The weak-label target used for reranker fitting is:

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
- 20Net_p,
$$

and hybrid inference reranks only within coverage-preserving buckets rather than across the full candidate set.

### 4.8 Evaluation design

The checked-in evaluation artifact uses a held-out-by-scenario split rather than a random row split. That design is materially stronger because rows from the same beneficiary scenario do not leak across training and test sets. The current report compares `rules_only`, a heuristic baseline, a linear reranker, and a tree reranker using top-1 agreement, top-5 and top-10 overlap, NDCG, full-coverage rates, average total cost, and average uncovered-drug burden.

The evaluation remains internal. It tests whether reranking better reproduces the weak-label ordering while preserving coverage safety signals. It does not yet test whether the system improves real beneficiary outcomes, enrollment decisions, or expert-adjudicated case quality.

## 5. Results

### 5.1 System capabilities

Repository inspection shows that `CMS-MPD-Recommendation` is an integrated analytical system rather than a disconnected prototype. The same serving layer supports command-line recommendation, Streamlit decision support, synthetic-scenario generation, model training, evaluation, and research summaries. Recommendation outputs carry plan cost, coverage status, channel mix, network summaries, grouped explanations, contract year, benefit design, and feature-version metadata. This shared-runtime design is a significant strength because it reduces drift between product logic and research logic.

### 5.2 Current evaluation artifact

The current evaluation JSON under `data/training/2025-Q3/full/` reports:

- dataset schema version `request_features_v4`
- weak-label version `weak_label_v2`
- `1774` plan rows
- `32` scenarios
- `1255` training rows and `519` test rows
- `22` training scenarios and `10` test scenarios

System-level mean results in that artifact are:

| System | Top-1 agreement | Top-10 overlap | NDCG@5 | Top-5 avg uncovered |
| --- | --- | --- | --- | --- |
| `rules_only` | `0.60` | `0.88` | `0.893` | `0.10` |
| `heuristic_baseline` | `0.70` | `0.91` | `0.912` | `0.10` |
| `linear_reranker` | `0.80` | `0.88` | `0.924` | `0.10` |
| `tree_reranker` | `1.00` | `0.97` | `1.000` | `0.10` |

The same report records `top5_improved = true`, `top10_improved = true`, and `uncovered_not_worse = true`. These results show strong internal fit to the study's weak-label objective and suggest that constrained reranking can improve internal ranking agreement without increasing uncovered-drug burden in the top recommendations.

### 5.3 Interpretation of current findings

The reported gains should be interpreted carefully. They indicate that the reranker can learn the internally defined feature space and pseudo-ground truth effectively. They do not establish real-world superiority over other recommendation systems, Medicare Plan Finder, or expert human counseling. What the results support is narrower and still useful: the project's rules-based candidate generation, feature engineering, and constrained reranking appear internally coherent and stable enough to support further evaluation.

## 6. Discussion

The direct literature base makes the study's positioning clearer than earlier drafts. The closest related work is not generic recommender research. It is the combined literature on plan-selection inefficiency, decision-aid design, SHIP counseling, readability barriers, reform-era affordability, formulary strategy, and insurer incentives in Part D. Once those strands are read together, the rationale for the system's design becomes more defensible.

First, the evidence base strongly favors explanation-first recommendation. Beneficiaries and counselors need to know not only which plan ranks higher, but why. The project's explanation groups therefore align well with the plan-selection, SHIP, and communication literature. Second, the evidence base supports fill-level cost logic over premium-led heuristics. Insulin protections, LIS effects, and pricing distortions make annual beneficiary burden path dependent and medication specific. Third, the policy and insurer-incentive literature supports contract-year-aware modeling. Part D after January 1, 2025 is not simply the old program with lower costs; it is a changed liability structure with operational implications for plans and beneficiaries.

The project is also appropriately conservative in how it uses machine learning. Rules remain the source of truth for cost, coverage, and explanation. Learning enters only as a reranking step after simulation and only within coverage-preserving strata. In a high-stakes benefit-selection setting, that separation is a feature, not a weakness.

The main claim boundary is therefore straightforward. This study shows how to build and evaluate a counselor-oriented, policy-aware Part D recommendation stack. It does not yet show that the stack improves real beneficiary outcomes or that it outperforms all alternative plan-comparison workflows in practice.

## 7. Limitations

This manuscript should state the current limits directly.

1. The contribution is integrative and domain specific, not a novel generic recommendation architecture.
2. The reranking target is weak-label based rather than based on observed beneficiary enrollment, adherence, financial outcomes, or expert-adjudicated counseling truth.
3. The checked-in evaluation artifact is scenario based and internal; it should not be interpreted as external validation.
4. The cost engine is an analytical approximation built from CMS rule schedules, observed pricing inputs, and channel heuristics rather than a production claims-adjudication engine.
5. Pharmacy burden is estimated from ZIP-centroid distance rather than route-time or pharmacy-choice histories.
6. Utilization defaults rely partly on PDE-derived aggregates and therefore cannot capture every beneficiary-specific quantity or adherence pattern.
7. The checked-in dataset metadata file still reports older schema markers than the current evaluation JSON, so strict reproducibility requires artifact regeneration from the present code path.

## 8. Conclusion

`CMS-MPD-Recommendation` is best understood as a counselor-oriented Medicare Part D decision-support study grounded in policy knowledge, explicit data transformation, fill-level simulation, and constrained reranking. The literature reviewed here supports that framing by showing why plan selection is simultaneously a policy problem, a communication problem, an incentive problem, and a workflow problem.

The project's defensible contribution is not algorithmic novelty in isolation. It is the disciplined integration of Medicare source data, beneficiary-specific cost logic, counselor-readable explanations, and research instrumentation in one auditable stack. The current evidence is strong enough to support a journal manuscript framed around system design, task alignment, and internal evaluation. The next threshold for a stronger publication claim is external validation against expert-reviewed cases, matched Plan Finder comparisons, or beneficiary-level outcome data.

## References

1. Bundorf MK, Stults CD, Klimke R, Meehan A, Chan AS, Polyakova M, Tai-Seale M. *Using an Online Decision Aid to Help Medicare Beneficiaries Choose a Prescription Drug Plan*. Washington, DC: Patient-Centered Outcomes Research Institute; 2020.
2. Stults CD, Fattahi S, Meehan A, et al. Comparative usability study of a newly created patient-centered tool and Medicare.gov Plan Finder to help Medicare beneficiaries choose prescription drug plans. *Journal of Patient Experience*. 2019;6(1):81-86.
3. Zhou C, Zhang Y. The vast majority of Medicare Part D beneficiaries still don't choose the cheapest plans that meet their medication needs. *Health Affairs (Millwood)*. 2012;31(10):2259-2265.
4. Hohmann LA, Hastings TJ, McFarland SJ, Hollingsworth JC, Westrick SC. Implementation of a Medicare plan selection assistance program through a community partnership. *American Journal of Pharmaceutical Education*. 2018;82(9):6452. doi:10.5688/ajpe6452
5. Aruru M, Salmon JW. Assessment of Medicare Part D communications to beneficiaries. *American Health & Drug Benefits*. 2010;3(5):310-317.
6. Cubanski J, Neuman T. Changes to Medicare Part D in 2024 and 2025 under the Inflation Reduction Act and how enrollees will benefit. KFF. April 20, 2023.
7. Cubanski J. A current snapshot of the Medicare Part D prescription drug benefit. KFF. October 7, 2025.
8. Cubanski J, Ochieng N, Neuman T. Analyzing changes in Medicare Part D enrollment for 2026. KFF. March 3, 2026.
9. Medicare Payment Advisory Commission. *March 2026 Report to the Congress: Medicare Payment Policy*. Washington, DC: MedPAC; 2026.
10. Joyce G, Blaylock B, Chen J, Van Nuys K. Medicare Part D plans greatly increased utilization restrictions on prescription drugs, 2011-20. *Health Affairs (Millwood)*. 2024;43(3):391-397. doi:10.1377/hlthaff.2023.00999
11. Dusetzina SB, Jazowski S, Cole A, Nguyen J. Sending the wrong price signal: why do some brand-name drugs cost Medicare beneficiaries less than generics? *Health Affairs (Millwood)*. 2019;38(7):1188-1194. doi:10.1377/hlthaff.2018.05476
12. Dusetzina SB, Cubanski J, Nshuti L, True S, Hoadley J, Roberts D, Neuman T. Medicare Part D plans rarely cover brand-name drugs when generics are available. *Health Affairs (Millwood)*. 2020;39(8):1326-1333. doi:10.1377/hlthaff.2019.01694
13. Trish E, Blaylock B, Van Nuys K. Cost sharing for preferred branded drugs in Medicare Part D. *JAMA*. 2025;333(13):1170-1172. doi:10.1001/jama.2024.28092
14. Lavetti K, Simon K. Strategic formulary design in Medicare Part D plans. *American Economic Journal: Economic Policy*. 2018;10(3):154-192. doi:10.1257/pol.20160248
15. Buttorff C, James HO, Sorbero ME, Reid RO. Medicare Part D insulin coverage: formulary strategies amid policy headwinds. *Health Affairs Scholar*. 2025;3(4):qxaf042. doi:10.1093/haschl/qxaf042
16. Cai Y, Yu F, Kumar M, Gladney R, Mostafa J. Health recommender systems development, usage, and evaluation from 2010 to 2022: a scoping review. *International Journal of Environmental Research and Public Health*. 2022;19(22):15115.
17. Ananthakrishnan A, Milne-Ives M, Cong C, Meinert E. The evaluation of health recommender systems: a scoping review. *International Journal of Medical Informatics*. 2025;195:105697.
