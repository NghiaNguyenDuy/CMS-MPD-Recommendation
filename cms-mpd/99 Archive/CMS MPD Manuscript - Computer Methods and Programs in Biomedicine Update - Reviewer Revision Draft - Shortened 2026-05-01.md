---
title: CMS-MPD-Recommendation reviewer-focused manuscript for Computer Methods and Programs in Biomedicine Update
date: 2026-05-01
status: shortened-submission-draft
target_journal: Computer Methods and Programs in Biomedicine Update
tags:
  - manuscript
  - cmpb-update
  - reviewer-focused
  - cms-mpd
  - shortened
aliases:
  - CMPB Update reviewer revision draft shortened
---

# CMS-MPD-Recommendation: A reproducible, explainable, policy-aware pipeline for Medicare Part D plan recommendation

> [!info] Shortened revision note
> This version condenses the 2026-04 reviewer revision while preserving the research contribution, data provenance boundary, mathematical workflow, evaluation design, primary results, guardrail interpretation, and submission statements.

## Title page

**Title:** CMS-MPD-Recommendation: A reproducible, explainable, policy-aware pipeline for Medicare Part D plan recommendation

**Running title:** Explainable Medicare Part D recommendation pipeline

**Authors:** Author A; Author B; Author C

**Affiliations:** TODO

**Corresponding author:** TODO

**Article type:** Original software and methods article

## Highlights

- Quarter-frozen public CMS Part D files drive the reproducible plan-design pipeline.
- Public plan-design data are separated from local enrichments and PDE-compatible samples.
- Fill-level cost simulation and explanations are produced before constrained reranking.
- A 2025-Q3 artifact with 33,961 plan-scenario rows supported held-out evaluation.
- The tree reranker improved ranking agreement while leaving coverage guardrails visible.

## Abstract

Selecting a Medicare Part D prescription drug plan is a high-dimensional decision problem involving premiums, formularies, utilization restrictions, pharmacy networks, geographic eligibility, subsidy status, and benefit-year rules that changed under the Inflation Reduction Act. We present CMS-MPD-Recommendation, a reproducible and explainable software pipeline that integrates public CMS quarterly formulary, pricing, pharmacy network, geography, and beneficiary-cost files with local drug, geography, insulin, and PDE-compatible scenario enrichments. A DuckDB medallion architecture normalizes these inputs into serving tables, after which a rules-first engine resolves medications, constructs ZIP-eligible candidate plans, simulates fill-level annual beneficiary out-of-pocket cost, and emits structured explanations. Optional learned rerankers reorder only already simulated candidate rows within coverage-preserving buckets. The current 2025-Q3 full artifact contains 33,961 plan-scenario rows from 600 mixed-source scenarios covering 100 ZIP codes, 460 regimen signatures, and 551 unique NDCs. On 180 held-out scenarios, the tree reranker achieved 0.861 top-1 agreement, 0.934 top-5 overlap, and 0.953 NDCG@5, compared with 0.622, 0.698, and 0.830 for rules-only ranking. The artifact explicitly distinguishes public plan-design inputs from restricted Prescription Drug Event data, which remain a future extension. CMS-MPD-Recommendation contributes a policy-aware and explainable decision-support framework for Medicare Part D recommendation under incomplete observability.

## Keywords

Medicare Part D; biomedical software; decision support; explainable recommendation; data engineering; out-of-pocket cost simulation; health informatics

## 1. Introduction

Choosing a Medicare Part D prescription drug plan is difficult because the appropriate plan depends on more than premium. A beneficiary's annual experience is shaped by plan eligibility, formulary coverage, tier placement, utilization management, preferred pharmacy access, deductible structure, insulin handling, subsidy status, and benefit-year cost-sharing rules. A system that collapses these dependencies into a single visible cost estimate can hide access or coverage risks that matter to beneficiaries and counselors.

This problem became more dynamic after the Inflation Reduction Act redesigned the Part D benefit, especially beginning in 2025 [6-9]. At the same time, utilization restrictions, formulary management, preferred pharmacy network design, and high-cost or negotiated drugs remain active sources of plan variation [10-15,29-31]. A useful recommender in this domain therefore must be quarter-aware and policy-aware. It must also state which evidence comes from public plan-design files and which evidence cannot be inferred without restricted beneficiary-level data.

CMS-MPD-Recommendation was built as decision-support software rather than as an autonomous plan selector. The project combines a local DuckDB medallion pipeline, a rules-first recommendation engine, a mixed-source scenario-generation workflow, and optional constrained reranking. Its contribution is a concrete reproducible pipeline that ingests quarter-frozen public CMS plan-design data, simulates fill-level beneficiary out-of-pocket cost, preserves explanation traces, and evaluates constrained reranking on scenario-held-out data while keeping deterministic plan facts visible.

The manuscript is written as a software and methods paper. It does not claim to solve Medicare Part D choice in a general sense, and it does not claim that public files reveal full beneficiary behavior. Instead, it demonstrates how public CMS plan-design data, local reference enrichments, and a restricted-compatible scenario layer can support transparent recommendation research under incomplete observability.

## 2. Related work and policy context

Medicare Part D plan choice has long been recognized as difficult for beneficiaries. Prior work showed that many beneficiaries do not choose the lowest-cost plan that fits their medication needs [1-3]. Econometric studies found that beneficiaries may overweight premiums relative to expected out-of-pocket cost, while later evidence showed that some beneficiaries learn and switch when status-quo costs rise [21,22]. More recent survey evidence suggests that many beneficiaries do not actively compare plans during open enrollment [25]. Decision aids and counseling interventions can improve navigation, but the evidence also shows that usable comparison requires explanation rather than raw attribute display alone [1,2,4,5].

Implementation studies reinforce this point. Simplifying Plan Finder's financial display improved older adults' ability to select lower-cost Part D plans without reducing average plan quality or pharmacy network size [23]. The CHOICE trial found that personalized expert-like recommendations increased plan switching and decision satisfaction [24]. GAO oversight of Plan Finder emphasized pricing-data checks, sponsor corrections, and usability feedback loops, supporting the view that recommendation tools should expose provenance and data-quality assumptions rather than hiding them [26].

The empirical policy literature also supports multi-objective comparison. Utilization restrictions have increased across Part D plans [10]. Brand-versus-generic out-of-pocket signals can be misleading from the beneficiary perspective [11,12]. Preferred branded products, insulin, and high-cost therapies can create situations in which list price, formulary status, and beneficiary liability do not move together cleanly [13-15]. Health recommender-system reviews and explainable clinical decision-support reviews similarly argue that usefulness depends on workflow fit, interpretable outputs, and evaluation beyond ranking accuracy [16,17,32,33].

CMS-MPD-Recommendation responds to these findings by treating coverage, restrictions, pharmacy access, benefit-year rules, data provenance, and missing-evidence signals as first-order objects. Machine learning is used only after deterministic cost and coverage evidence has been generated. This design positions the system as counselor-oriented Medicare Part D decision support, not as a generic recommender benchmark.

## 3. Materials and data sources

### 3.1 Data provenance and study boundary

The central data-provenance rule is that the public artifact is based on public quarterly CMS plan-design data, not unrestricted beneficiary claims. The system combines public CMS formulary, pricing, pharmacy network, geography, cost-rule, exclusion, and indication files [18]; local reference enrichments for drug identity, ZIP geography, and insulin classification [34-36]; and a local PDE-compatible sample aligned to ResDAC Part D Event documentation [37]. Full CMS Part D claims and Prescription Drug Event data remain restricted and are not part of the public replication boundary [19,20].

**Table 1. Data inputs and provenance.**

| Input family | Example local table/file | Main use | Public/restricted status |
|---|---|---|---|
| CMS plan-design public files | `bronze.plan_information`, `bronze.basic_formulary`, `bronze.pricing`, `bronze.pharmacy_network` | Eligibility, coverage, pricing basis, pharmacy-network features | Public |
| CMS cost-rule public files | `bronze.beneficiary_cost`, `bronze.insulin_beneficiary_cost` | Beneficiary cost simulation | Public |
| CMS geography, exclusion, and indication files | `bronze.geographic_locator`, `bronze.excluded_drugs`, `bronze.indication_coverage` | Service-area resolution and coverage explanation | Public |
| RXCUI and ZIP enrichments | `bronze.rxcui_properties`, `bronze.us_zipcode_geo` | Drug identity, synonym resolution, density and distance proxies | Local enrichment |
| Insulin reference mapping | `bronze.insulin_reference` | Insulin classification and insulin-specific handling | Local enrichment |
| PDE-compatible local sample | `bronze.pde_sample`, `pde.csv` | Defaults and mixed-source scenario generation | Local sample / restricted-compatible |

This separation matters for interpretation. Public CMS files make the plan-design pipeline reproducible. Local enrichments improve matching, geography, insulin handling, and scenario construction. The PDE-compatible layer gives the research workflow a beneficiary-drug-event shape, but it is not treated as claims-ground truth.

### 3.2 Reproducible artifact

The current manuscript uses a quarter-frozen 2025-Q3 full build. The locked experiment identifiers are `snapshot_quarter = 2025-Q3`, `build_profile = full`, `dataset_schema_version = request_features_v4`, `feature_version = research_v4`, `weak_label_version = weak_label_v2`, `generation_version = scenario_generation_v1`, `teacher_feature_policy = student_safe`, and `generator_seed = 42`. Pinned runtime dependencies include DuckDB 1.5.1, NumPy 2.3.4, pandas 2.3.3, Streamlit 1.55.0, and pytest 9.0.2. Before external submission, this local state should be archived as a release tag and DOI.

## 4. Methods

### 4.1 Overall workflow and data-engineering foundation

CMS-MPD-Recommendation was designed as an end-to-end pipeline. The study begins with quarter-frozen source provenance, moves through medallion data engineering and beneficiary-level recommendation logic, and only then introduces canonical scenario generation, replay-based weak-label supervision, constrained reranking, and held-out evaluation. This order is central because explanation and safety are created during the rules-first stages, not appended after model scoring.

The DuckDB medallion architecture separates raw preservation, business normalization, and runtime serving. Bronze tables preserve raw source inputs with lineage fields such as source file, snapshot quarter, and load timestamp. Silver tables normalize entities and canonical keys, including plan, ZIP code, drug reference, plan service area, plan-drug coverage, pharmacy network, beneficiary cost rules, and insulin cost rules. Gold tables materialize runtime-serving facts such as `gold.plan_service_area`, `gold.plan_drug_cost_basis`, `gold.plan_channel_summary`, `gold.plan_network_summary`, `gold.plan_summary`, `gold.drug_input_defaults`, and `gold.recommendation_features`.

Canonical keys prevent ambiguous joins across public CMS files. The main keys are `plan_key = CONTRACT_ID + PLAN_ID + SEGMENT_ID`, `contract_plan_key`, `formulary_id`, normalized 5-digit ZIP code, CMS county code, normalized 11-digit NDC, normalized RXCUI, normalized day supply, coverage level, and tier level. These contracts are methodological choices: errors in these keys can assign the wrong geography, formulary, or cost rule to a plan.

Let the raw input family be $\mathcal{R}=\{R_1,\dots,R_n\}$. The medallion pipeline can be represented as:

$$
\mathcal{R}
\xrightarrow{\mathcal{B}}
\mathcal{B}(\mathcal{R})
\xrightarrow{\mathcal{S}}
\mathcal{S}(\mathcal{B}(\mathcal{R}))
\xrightarrow{\mathcal{G}}
\mathcal{G}(\mathcal{S}(\mathcal{B}(\mathcal{R}))).
$$

Here, $\mathcal{B}$ preserves lineage, $\mathcal{S}$ normalizes onto canonical keys, and $\mathcal{G}$ materializes serving-layer tables. At runtime, plan-drug cost evidence is produced by joining normalized coverage, tier, utilization-management, exclusion, indication, pricing, standard cost-rule, and insulin override fields. Service-area eligibility is represented as $A(z,p)=1$ when ZIP code $z$ is served by plan $p$ through the ZIP-county and plan-county bridge. Thus, recommendation-time evidence is produced by deterministic relational transformations rather than opaque feature synthesis alone.

### 4.2 Runtime recommendation and cost simulation

For a beneficiary request scenario

$$
s=(z,M,\ell,h,r,f),
$$

$z$ is ZIP code, $M$ is the medication set, $\ell$ is low-income subsidy status, $h$ is pharmacy preference, $r$ is user role, and $f$ is decision focus. The eligible plan set is:

$$
P(z)=\{p:A(z,p)=1\}.
$$

Each medication can be supplied by NDC, RXCUI, preferred name, synonym, or prefix match. The resolver follows that order and retains approximate matches as evidence gaps rather than silently treating them as exact matches. This separation of drug identity from plan coverage follows the role of RxNorm and the FDA NDC Directory: identity resolution does not itself establish coverage or reimbursement [27,28].

For each plan and medication, the engine retrieves coverage status, restriction flags, pricing inputs, channel availability, deductible applicability, and insulin-specific overrides. Annual beneficiary out-of-pocket cost is simulated at fill level. The engine normalizes day supply to 30, 60, or 90 days, schedules annual fills, applies contract-year-aware benefit logic, uses the 2025 redesign branch for current data, supports a 2024 standard branch for historical modeling, applies insulin overrides where present, applies LIS adjustments after base liability is computed, and aggregates annual premium, annual drug out-of-pocket cost, and annual total cost.

If medication $m$ has $n_m$ annual fills, its fill-event set is:

$$
E_m=\left\{\left(k,\operatorname{round}\left((k-1)\frac{365}{n_m}\right)\right):k=1,\dots,n_m\right\}.
$$

For plan $p$, drug $m$, fill $k$, and feasible channel $c$, the allowed-cost proxy is:

$$
g_{pmkc}=\max(u_{pms}q_{mk}+f_{pc\tau s},\phi_{pc}),
$$

where $u_{pms}$ is unit cost, $q_{mk}$ is fill quantity, $f_{pc\tau s}$ is a channel-specific fee term by channel, tier family, and day supply, and $\phi_{pc}$ is any channel floor price. A policy-year-aware rule operator $\chi_y$ converts allowed cost into base beneficiary liability, after which the annual cap is applied:

$$
o_{pmkc,y}=\min(c^{base}_{pmkc,y},cap_y-O_{k-1}),
\qquad cap_{2025}=2000.
$$

The annual plan-level total used in ranking is:

$$
T_p(s)=Premium_p+\sum_{m\in M}\sum_{k\in E_m}\min_{c\in C_{pmk}}o_{pmkc,y},
$$

where $C_{pmk}$ is the feasible channel set. The rules engine then ranks plans with a coverage-preserving lexicographic key:

$$
K_p=(b_p,-q_p,-F_p,T_p,U_p,H_p,N_p),
$$

where $b_p$ is coverage bucket, $q_p$ is priced-drug count, $F_p$ is fit score, $U_p$ is uncovered-drug burden, $H_p$ is restriction burden, and $N_p$ is network-risk burden. This key formalizes the implementation choice that coverage completeness and priceability are first-order ordering decisions rather than soft penalties.

Every recommendation includes structured explanations derived from the same fields used for ranking. Explanation groups include coverage fit, utilization management, insulin handling, deductible and benefit phase, pharmacy access, cost estimate, medication-match confidence, and missing-data signals. In the local trace for an exact lisinopril NDC request in ZIP `90001`, for example, the engine selected a feasible preferred-mail channel, scheduled 13 fills, simulated the 2025 benefit branch, and separately stored negotiated-price evidence, deductible exposure, final beneficiary OOP, and cap-trigger status. The reported beneficiary cost is therefore a simulated public-file estimate, not a guaranteed pharmacy transaction price.

### 4.3 Feature design, weak labels, and constrained reranking

The machine-learning layer is deliberately downstream of deterministic evidence generation. Runtime recommendation rows are replayed into plan-scenario feature rows; weak labels encode the study's explicit preference structure; optional learned models rerank only rows already produced by the rules engine. The model cannot invent eligibility, coverage, cost, pharmacy-network, or geography facts.

**Table 2. Feature groups used in modeling and ablation.**

| Feature group | Example variables | Why included |
|---|---|---|
| Rules-engine summary | `current_rules_rank`, `current_rules_score`, `fit_score`, `coverage_score`, `access_score` | Audit deterministic ranking context and teacher-feature ablations |
| Cost and liability | `annual_premium`, `annual_drug_oop`, `annual_total_cost`, `deductible_exposure_total`, `negotiated_price_total` | Reflect beneficiary-facing economic burden |
| Coverage and exclusions | `coverage_status`, `covered_drug_share`, `uncovered_drug_count`, `excluded_drug_count`, `missing_price_drug_count` | Preserve coverage completeness and priceability |
| Restriction burden | `restriction_count`, `pa_rate`, `st_rate`, `ql_rate`, `channel_unavailable_count` | Represent access friction |
| Network and access | `network_flag`, `network_risk_score`, `preferred_retail_count`, `preferred_mail_count`, `nearest_preferred_distance_bucket` | Represent pharmacy usability and network risk |
| Evidence quality | `approximate_match_count`, `exact_match_count`, `match_review_required_flag`, `unknown_network_data_flag`, `unsafe_reason_count` | Prevent false confidence when evidence is weak |
| Beneficiary and scenario context | `lis_status`, `age_band`, `pharmacy_preference`, `scenario_bundle`, `scenario_profile` | Preserve subgroup and workflow context |

Two modest tabular reranker families are trained: ridge regression and a shallow residual tree ensemble. Ridge regression provides a stable additive baseline for correlated sparse features [38]. The tree ensemble follows stagewise residual fitting and captures low-order interactions among cost, coverage, restrictions, LIS status, network risk, and scenario type while limiting capacity through shallow depth and minimum leaf size [39]. The default trained artifact uses the `student_safe` policy, which excludes numeric teacher-style fields such as current rules rank, rules score, fit score, and sub-scores from the default student feature matrix. Those columns remain in the dataset for audit and ablation but are not exposed to the reviewer-facing student artifact.

Weak labels are not clinical gold standards. They are transparent programmatic supervision targets that encode the study's decision logic when external outcome labels are unavailable [42]. The current weak-label target can be summarized as:

$$
W_p =
1000\mathbf{1}\{\text{coverage}_p=full\}
+R_p-T_p-250U_p-125E_p-110M_p-90C_p-25H_p-20A_p-18Mail_p-15Ins_p-12InsNP_p-20Net_p.
$$

Here $R_p$ is rules score; $T_p$ is annual total cost; $U_p$, $E_p$, $M_p$, and $C_p$ are uncovered, excluded, missing-price, and channel-unavailable burdens; $H_p$ is restriction burden; $A_p$ is approximate-match burden; and the remaining terms represent mail-order, insulin, insulin-nonpreferred, and network-risk burdens. Coverage and priceability dominate ordinary cost differences because a lower-cost plan is not useful if a requested drug is uncovered, excluded, unpriceable, or available only through an unusable channel.

At inference, constrained hybrid reranking estimates a model score $\hat{W}_p$ but orders only within coverage-priceability buckets:

$$
\pi^{hybrid}(p)=(\beta(p),-\hat{W}_p),
$$

where $\beta(p)$ maps the plan to a safety-preserving bucket. A weak-coverage or unpriceable plan cannot leap ahead of a fully covered and fully priceable plan solely because of model score. This is the mathematical expression of the system's safety constraint and the reason ranking agreement should be interpreted as internal ranking validity, not external clinical validity.

### 4.4 Scenario generation and evaluation design

The research workflow materializes canonical scenarios first, then replays them through the same rules-first recommendation path used at runtime. This keeps modeling tied to beneficiary-like inputs and is consistent with synthetic patient-data work that uses generated cases for software testing and method evaluation when real patient-level data are restricted [43].

Each scenario can be represented as:

$$
s_i=(z_i,b_i,M_i,q_i,\ell_i,g_i,u_i),
$$

where $z_i$ is ZIP code, $b_i$ is scenario bundle, $M_i$ is medication set, $q_i$ is pharmacy preference, $\ell_i$ is LIS status, $g_i$ is regimen signature, and $u_i$ is source kind. ZIPs are sampled from service-area ZIPs using density-stratified sampling to preserve geographic-density representation [44]. Drug pools are built from the gold catalog and include generic, brand, insulin, specialty, restricted, and lower-cost pools. Local PDE-compatible templates are used when available; benchmark and stress regimens are generated when local templates are unavailable or when harder edge cases are needed.

The current full artifact contains six scenario bundles: access-sensitive, insulin-chronic, low-utilizer, maintenance-generic, mixed-restriction, and specialty-high-cost. Each bundle contains 100 scenarios. The source mix is 180 benchmark scenarios, 300 local PDE-compatible scenarios, and 120 stress scenarios. Evaluation uses a held-out-by-scenario split because replaying one scenario creates many plan rows that share the same ZIP, regimen, LIS status, and pharmacy preference. A row-random split would leak scenario context. The training set contains 420 scenarios and 23,384 plan-scenario rows; the test set contains 180 scenarios and 10,577 rows.

The evaluated systems are rules-only ranking, a heuristic baseline, the linear reranker, the tree reranker, and ablation systems using cost-only, cost-plus-restrictions, cost-plus-restrictions-plus-network, and full feature sets. A frozen external Medicare Plan Finder comparator for the exact same quarter and cases was not yet packaged into the public artifact, so the manuscript reports transparent internal comparators reproducible from the same code and data state.

Primary metrics separate ranking agreement from operational safety [40,41]. Let $\mathcal{S}_{test}$ be held-out scenarios, $\pi_s^m$ the ordering from method $m$, and $\pi_s^\star$ the weak-label reference ordering. Top-1 agreement is the fraction of scenarios for which the method and reference select the same first plan. Top-$k$ overlap is:

$$
\operatorname{Overlap}_k(m)=
\frac{1}{|\mathcal{S}_{test}|}
\sum_{s\in\mathcal{S}_{test}}
\frac{|\operatorname{Top}_k(\pi_s^m)\cap\operatorname{Top}_k(\pi_s^\star)|}{\min(k,|\mathcal{P}_s|)}.
$$

NDCG@k uses weak-label rank as graded relevance. Safety metrics include top-k full-coverage rate, average top-k total cost, average top-k uncovered-drug burden, blocker precision when no full-coverage plan exists, review-trigger rates, and missing-data behavior. Guardrails were defined prospectively: top-5 and top-10 ranking should improve, and uncovered-medication burden should not worsen.

### 4.5 Multi-case retrieval protocol

To make the workflow concrete, eight prescription samples were run through the current local recommendation engine. These cases probe maintenance generics, insulin and GLP-1 therapy, specialty plus anticoagulant therapy, a low-utilizer generic case, access-sensitive respiratory use, mixed-restriction cardiometabolic therapy, LIS sensitivity, and a high-cost specialty stress case. All used exact NDC inputs to avoid unintended manual-review blockage. Each case recorded candidate counts, full and partial coverage, unknown-network counts, rules and hybrid top plans, cost traces, restriction burden, network status, model score, and model confidence. The cases are functional probes of software workflow behavior, not patient-specific clinical or enrollment recommendations.

## 5. Results

### 5.1 Artifact characteristics and main ranking results

The current 2025-Q3 full artifact contains 33,961 plan-scenario rows from 600 scenarios, 100 ZIP codes, 460 regimen signatures, 551 unique NDCs, 88 completed dataset chunks, and balanced representation across six scenario bundles. These counts come from the local metadata artifact rather than from proposed future work.

**Table 3. Main held-out-by-scenario ranking results.**

| System | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | NDCG@10 | Top-5 full coverage | Top-5 avg total cost | Top-5 avg uncovered | Blocker precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules only | 0.622 | 0.698 | 0.786 | 0.830 | 0.828 | 0.660 | 198.10 | 0.414 | 0.950 |
| Heuristic baseline | 0.811 | 0.899 | 0.953 | 0.924 | 0.920 | 0.660 | 81.79 | 0.463 | 0.989 |
| Linear reranker | 0.628 | 0.879 | 0.919 | 0.899 | 0.890 | 0.660 | 83.06 | 0.459 | 0.994 |
| Tree reranker | 0.861 | 0.934 | 0.962 | 0.953 | 0.947 | 0.660 | 83.07 | 0.459 | 0.994 |

The tree reranker improved top-1 agreement by 0.239 absolute points, top-5 overlap by 0.237 absolute points, and NDCG@5 by 0.123 absolute points relative to rules-only ranking. It also improved over the heuristic baseline on top-1 agreement, top-5 overlap, top-10 overlap, and NDCG while maintaining similar average top-5 total cost. The heuristic baseline remains important because it is not a weak comparator; it shows that practical ranking already benefits from simple coverage and cost logic, and that the tree reranker adds value over that stronger operational baseline.

### 5.2 Ablation and scenario-bundle results

**Table 4. Ablation results.**

| Feature subset | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | Top-5 avg total cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Cost only | 0.806 | 0.882 | 0.935 | 0.926 | 80.75 | 0.469 |
| Cost plus restrictions | 0.833 | 0.903 | 0.954 | 0.937 | 82.57 | 0.460 |
| Cost plus restrictions plus network | 0.872 | 0.950 | 0.973 | 0.960 | 82.99 | 0.459 |
| Full feature set | 0.867 | 0.940 | 0.971 | 0.957 | 82.94 | 0.459 |

Cost, restriction, and network information accounted for most of the learnable signal. The cost-plus-restrictions-plus-network subset slightly outperformed the nominal full feature set on some metrics, suggesting that model complexity should be justified conservatively. This result is favorable for interpretability because a compact and explainable feature subset captures most of the gain.

**Table 5. Tree-reranker performance by scenario bundle.**

| Scenario bundle | Top-1 agreement | Top-5 overlap | NDCG@5 | Top-5 full coverage | Top-5 avg total cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Access-sensitive | 1.000 | 0.979 | 1.000 | 0.771 | 112.81 | 0.307 |
| Insulin-chronic | 0.886 | 0.954 | 0.950 | 0.909 | 40.04 | 0.091 |
| Low-utilizer | 0.844 | 0.938 | 0.956 | 0.656 | 85.75 | 0.375 |
| Maintenance-generic | 0.762 | 0.895 | 0.894 | 0.790 | 90.64 | 0.248 |
| Mixed-restriction | 0.875 | 0.950 | 0.980 | 0.475 | 101.25 | 0.775 |
| Specialty-high-cost | 0.781 | 0.881 | 0.923 | 0.394 | 78.27 | 0.900 |

Performance was strongest in access-sensitive and insulin-chronic scenarios. It was weaker in specialty-high-cost and maintenance-generic scenarios, where coverage complexity, sparse feasible sets, or restriction burden make ranking more brittle. These subgroup differences support the manuscript's emphasis on explanation fields rather than opaque scores alone.

### 5.3 Guardrails and sample-case retrieval

The evaluation artifact showed that top-5 and top-10 agreement improved, but the uncovered-not-worse guardrail was not fully satisfied. The tree reranker improved top-5 overlap from 0.698 to 0.934 and NDCG@5 from 0.830 to 0.953, but average top-5 uncovered-drug burden increased from 0.414 to 0.459. The aggregate increase is small, but an uncovered medication is not cosmetic in this domain. It can change whether a recommendation is usable. The risk concentrates in specialty-high-cost and mixed-restriction scenarios, where coverage is sparse, utilization management is common, and favorable cost estimates can coexist with access barriers.

Eight sample cases retrieved recommendations from the 2025-Q3 local database. All cases had 126 ZIP-eligible service-area candidates, but regimen composition changed the effective feasible set. Routine maintenance, low-utilizer, respiratory, and cardiometabolic cases retained 110 fully covered candidates; insulin/GLP-1 and specialty/anticoagulant cases retained 101 and 99; the high-cost specialty stress case retained only 6 fully covered candidates. Thus, candidate availability is driven first by geography and then by drug-level coverage completeness.

**Table 6. Candidate-set and top-recommendation summary for eight samples.**

| Case | Profile | Full coverage | Partial coverage | Rules top plan | Hybrid top plan | Main top-plan watchout |
|---|---|---:|---:|---|---|---|
| Case 1 | maintenance generic | 110 | 16 | Blue Shield 65 Plus (HMO) | Blue Shield 65 Plus (HMO) | No top-plan watchout |
| Case 2 | insulin plus GLP-1 | 101 | 25 | Anthem I Carelon Chronic Care (HMO-POS C-SNP) | Aetna Medicare Preferred Plus (HMO-POS) | Mail-order dependence and 2 UM restrictions |
| Case 3 | specialty plus anticoagulant | 99 | 27 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) | Mail-order dependence and 2 UM restrictions |
| Case 4 | low-utilizer generic | 110 | 16 | Aetna Medicare Core (PPO) | Aetna Medicare Core (PPO) | Mail-order dependence |
| Case 5 | access-sensitive respiratory/retail | 110 | 16 | Blue Shield 65 Plus (HMO) | Blue Shield 65 Plus (HMO) | 1 UM restriction |
| Case 6 | mixed-restriction cardiometabolic | 110 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) | Mail-order dependence and 1 UM restriction |
| Case 7 | LIS sensitivity cardiometabolic | 110 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) | Mail-order dependence and 1 UM restriction |
| Case 8 | high-cost specialty stress | 6 | 120 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | No preferred-retail network and mail-order dependence |

All eight top hybrid rows were fully covered and had 0.00 simulated beneficiary total cost in the local artifact, but the rows were not operationally equivalent. Cases 1, 4, and 5 were stable because the rules winner remained the hybrid winner. Cases 2, 3, 6, and 7 showed substantive constrained reranking: the hybrid-selected plans came from lower rules ranks, but remained within the same safety bucket and preserved restriction, channel, and network explanations. Case 8 was stable for a different reason: the full-coverage set was very small, leaving limited safe room to reorder.

The cost traces further show why explanation fields are necessary. Case 8 had a final simulated beneficiary drug OOP of 0.00 for the top plan, but the negotiated-price proxy exceeded 856,000 across scheduled fills and the selected plan lacked preferred-retail network status. The correct interpretation is not simply "low cost." It is "full coverage in a sparse market with large underlying price exposure and channel limitations." This distinction is the practical reason the system reports negotiated-price evidence, final OOP, coverage scarcity, restrictions, and network status together.

## 6. Discussion

The main claim of this manuscript is that Medicare Part D recommendation can be implemented as a transparent software pipeline rather than as a black-box ranking problem. The architecture supports this claim by preserving a path from public source files to bronze, silver, and gold tables; from serving facts to beneficiary-level cost simulation and explanations; from scenario replay to weak-label supervision; and from constrained reranking to held-out evaluation. The machine-learning layer is downstream of deterministic plan evidence and cannot replace that evidence.

The policy-aware contribution is the treatment of benefit-year rules, formulary status, restrictions, insulin logic, LIS status, pharmacy networks, and incomplete observability as core modeling objects. This matters because a high-cost therapy can show large negotiated-price exposure while simulated beneficiary OOP is zero in the selected plan; a plan can fully cover the regimen but depend on mail order; and a specialty drug can be fully covered by only a small subset of local candidate plans. These are not edge details in Medicare Part D. They are the practical substance of plan comparison.

The results support a restrained view of machine learning in regulated recommendation. The tree reranker improved internal ranking quality, but the strongest ablation subset used highly interpretable cost, restriction, and network features. This suggests that the model adds value without requiring a large opaque feature space. The finding is consistent with health recommender and clinical decision-support literature that treats interpretability, workflow fit, and real-world evaluation as central requirements [16,17,32,33].

The guardrail result is mixed and therefore useful. Top-k ranking agreement improved substantially, but uncovered-medication burden increased slightly. The appropriate interpretation is not that reranking should be discarded, but that ranking metrics must be reported with coverage, restriction, network, and missing-data endpoints. In Medicare Part D, a better ordering is only useful if users can inspect why that ordering was produced and whether it hides access risk.

The sample cases make the same point operationally. Exact NDC inputs allowed the workflow to proceed through medication resolution, candidate construction, fill-level simulation, explanation generation, rules ranking, and constrained hybrid reranking without unintended manual-review blockage. In the insulin, specialty, and mixed-restriction cases, the reranker changed trade-off ordering while preserving explanation fields. In the high-cost specialty case, the system showed a low simulated beneficiary OOP result and a strong access warning at the same time. These are exactly the cases in which explanation should remain coupled to ranking.

The provenance clarification is also central. Public CMS quarterly plan files and restricted PDE data are not interchangeable [18-20]. The current public artifact demonstrates a plan-design and decision-support pipeline under incomplete observability. It does not claim to be a claims-based simulator of beneficiary behavior, and it should not be interpreted as a production enrollment advisor until additional eligibility filters, external benchmarking, restricted-data validation, and counselor usability testing are completed.

## 7. Limitations

This study has several limitations. The evaluation is internal and scenario-based. Weak-label agreement measures alignment with the study's explicit preference structure, not clinical outcome validity, causal savings, adherence improvement, or beneficiary satisfaction. Public CMS files do not expose all economically relevant signals, including rebates, net prices, PBM incentives, and actual pharmacy-adjudication behavior. The PDE-compatible layer is a local sample aligned to PDE documentation and used for defaults and scenario generation; it is not unrestricted CMS PDE access.

Pharmacy access is approximated using network flags and ZIP-based geography rather than full beneficiary travel behavior. The public artifact does not yet include a frozen external comparator such as Medicare Plan Finder exports for matched sentinel cases. Post-IRA plan design is still evolving, so the software should be evaluated as a quarter-frozen artifact and refreshed for each benefit year before operational use [29-31]. Finally, this manuscript does not yet report prospective counselor or beneficiary usability evaluation, which is substantive because explanation is central to the system's intended use.

The sample retrievals also expose a deployment boundary. Some top retrieved plans are MA-PD or HMO/HMO-POS products, including SNP-like plan names. Production deployment should add explicit beneficiary eligibility filters for MA-PD, D-SNP, C-SNP, and related enrollment constraints before presenting outputs as actionable enrollment advice. In this manuscript, those cases are workflow probes, not beneficiary-specific recommendations.

## 8. Conclusion

CMS-MPD-Recommendation is a reproducible, explainable, policy-aware software pipeline for Medicare Part D plan recommendation. Its public artifact is built from quarter-frozen CMS plan-design files, local reference enrichments, and a PDE-compatible behavioral layer that is explicitly distinguished from restricted claims data. The system combines medallion data engineering, fill-level out-of-pocket simulation, structured explanation outputs, and constrained reranking. In the current 2025-Q3 full evaluation, the tree reranker improved ranking agreement and NDCG over rules-only ranking while preserving a reviewer-visible evidence model and surfacing unresolved coverage guardrails. The software is therefore best understood as research-ready decision support under incomplete observability, not as an autonomous claims-ground-truth optimizer.

## Data availability

Public Medicare Part D formulary, pharmacy network, pricing, geography, and related plan files used in this study are available from the CMS quarterly public-use release [18]. Restricted Prescription Drug Event data are not part of the public replication boundary and require separate CMS approval under a Data Use Agreement [19,20]. The current public manuscript state is designed so that the main plan-design pipeline can be understood and reproduced from public inputs, local schema definitions, and derived artifacts.

## Code availability

The software described in this manuscript is implemented in the local `CMS-MPD-Recommendation` workspace associated with this reviewer revision. Before journal submission, this exact code state should be archived as a versioned public release with a DOI, dependency lockfile, and one-command regeneration script for manuscript tables and figures. Until that archive exists, this manuscript should be treated as a submission-preparation draft rather than the final archival record.

## Ethics statement

This study used publicly available administrative plan-design data and non-identifiable synthetic or PDE-compatible sample records for software evaluation. No intervention involving human participants was conducted, and no identifiable beneficiary-level data are reported in this manuscript draft. Institutional review board approval was therefore not required for the work described here. If restricted CMS beneficiary-level data are used in future work, those analyses should be conducted under the applicable Data Use Agreement and oversight requirements.

## Funding

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

## Declaration of competing interests

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## CRediT authorship contribution statement

Author A: Conceptualization, Methodology, Software, Formal analysis, Writing - original draft.  
Author B: Data curation, Validation, Visualization, Writing - review and editing.  
Author C: Supervision, Methodology, Writing - review and editing.

Replace placeholder names and roles before submission if the actual contribution map differs.

## Declaration of generative AI and AI-assisted technologies

During preparation of this manuscript draft, OpenAI Codex/ChatGPT was used to help organize manuscript revisions, align the text with journal expectations, and edit language for clarity. The authors reviewed and take responsibility for all content, interpretations, results, and conclusions. No generative AI tool was used to generate study results or alter figure evidence.

## Acknowledgements

The authors acknowledge the public CMS documentation and data ecosystem that makes quarter-specific Medicare Part D plan-design analysis possible, and the counseling-oriented problem framing that shaped the system's emphasis on explanation and guardrails.

## Suggested figure and table package for submission

**Figure 1.** Medicare Part D data lifecycle and CMS-MPD medallion pipeline.  
Caption: Public CMS quarterly plan-design files are ingested into bronze storage, normalized into silver relational tables, transformed into gold recommendation features, and consumed by transparent scoring and constrained reranking layers. The PDE-compatible layer is a behavioral extension, not a public-data substitute.

**Figure 2.** Beneficiary request to recommendation workflow.  
Caption: Beneficiary inputs, medication normalization, ZIP eligibility, fill-level cost simulation, explanation-card construction, and final top-k ranking.

**Figure 3.** Overall research flow, scenario generation, and evaluation design.  
Caption: Provenance inputs, medallion serving-layer construction, rules-first recommendation and explanation generation, mixed-source canonical scenario generation, replay dataset construction, weak-label supervision, constrained reranking, held-out evaluation, and reviewer-facing retrieval outputs.

**Figure 4.** Explainability card example.  
Caption: Illustrative output showing annual premium, deductible, annual drug out-of-pocket cost, utilization restrictions, preferred pharmacy access, insulin flags, and key trade-offs.

**Table 1.** Data inputs and provenance.  
**Table 2.** Feature groups used in modeling and ablation.  
**Table 3.** Main held-out-by-scenario ranking results.  
**Table 4.** Ablation results.  
**Table 5.** Tree-reranker performance by scenario bundle.  
**Table 6.** Candidate-set and top-recommendation summary for eight samples.

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
18. Centers for Medicare & Medicaid Services. Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information Files. Available at: https://www.cms.gov/Research-Statistics-Data-and-Systems/Files-for-Order/NonIdentifiableDataFiles/PrescriptionDrugPlanFormularyPharmacyNetworkandPricingInformationFiles. Accessed April 17, 2026.
19. Centers for Medicare & Medicaid Services. Part D Claims Data. Available at: https://www.cms.gov/medicare/coverage/prescription-drug-coverage/part-d-claims-data. Accessed April 17, 2026.
20. Centers for Medicare & Medicaid Services. Prescription Drug Event Data Guidance. Available at: https://www.cms.gov/DrugCoverageClaimsData/. Accessed April 17, 2026.
21. Abaluck J, Gruber J. Choice inconsistencies among the elderly: evidence from plan choice in the Medicare Part D program. *American Economic Review*. 2011;101(4):1180-1210. doi:10.1257/aer.101.4.1180
22. Ketcham JD, Lucarelli C, Powers CA. Paying attention or paying too much in Medicare Part D. *American Economic Review*. 2015;105(1):204-233. doi:10.1257/aer.20120651
23. McGarry BE, Maestas N, Grabowski DC. Simplifying the Medicare Plan Finder tool could help older adults choose lower-cost Part D plans. *Health Affairs*. 2018;37(8):1290-1297. doi:10.1377/hlthaff.2018.0145
24. Bundorf MK, Polyakova M, Stults C, Meehan A, Klimke R, Pun T, Chan AS, Tai-Seale M. Machine-based expert recommendations and insurance choices among Medicare Part D enrollees. *Health Affairs*. 2019;38(3):482-490. doi:10.1377/hlthaff.2018.05017
25. Bruine de Bruin W, Hodson N. Medicare Part D beneficiaries' self-reported barriers to switching plans and making plan comparisons at all. *Health Affairs Scholar*. 2024;2(11):qxae141. doi:10.1093/haschl/qxae141
26. U.S. Government Accountability Office. *Medicare Part D: CMS Has Implemented Processes to Oversee Plan Finder Pricing Accuracy and Improve Website Usability*. GAO-14-143. January 10, 2014.
27. National Library of Medicine. *RxNorm Technical Documentation*. Available at: https://www.nlm.nih.gov/research/umls/rxnorm/docs/techdoc.html. Accessed April 21, 2026.
28. U.S. Food and Drug Administration. *National Drug Code Directory*. Available at: https://www.fda.gov/drugs/drug-approvals-and-databases/national-drug-code-directory. Accessed April 21, 2026.
29. Cai CL, Bhaskar A, Kesselheim AS, Rome BN. Changes in Medicare Part D plan designs after the Inflation Reduction Act. *JAMA Internal Medicine*. 2025;185(10):1266-1273. doi:10.1001/jamainternmed.2025.4003
30. Anderson DM, McEnany M, Petry SE, Anderson KE. Inflation Reduction Act changes to Part D plan design: lower premiums, higher deductibles, and some smaller formularies. *Health Affairs*. 2026;45(4):441-447. doi:10.1377/hlthaff.2025.00644
31. Joyce G, Chen B, Blaylock B. The changing Part D landscape. *Health Affairs Scholar*. 2026;4(4):qxag078. doi:10.1093/haschl/qxag078
32. Barbaric A, Christofferson K, Benseler SM, Lalloo C, Mariakakis A, Pham Q, Swart JF, Yeung RSM, Cafazzo JA. Health recommender systems to facilitate collaborative decision-making in chronic disease management: a scoping review. *Digital Health*. 2025;11. doi:10.1177/20552076241309386
33. Xu Q, Xie W, Liao B, et al. Interpretability of clinical decision support systems based on artificial intelligence from technological and medical perspective: a systematic review. *Computational and Mathematical Methods in Medicine*. 2023;2023:9919269. doi:10.1155/2023/9919269
34. National Library of Medicine. *RxNorm API*. Available at: https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html. Accessed April 24, 2026.
35. uszipcode project. *uszipcode 1.0.1 documentation*. Available at: https://uszipcode.readthedocs.io/. Accessed April 24, 2026.
36. Centers for Medicare & Medicaid Services. *Calendar Year (CY) 2021 Part D Senior Savings Model Drug National Drug Code (NDC) List*. Version August 17, 2020. Available at: https://www.cms.gov/priorities/innovation/files/x/partd-seniordav-ndclist.pdf. Accessed April 24, 2026.
37. Research Data Assistance Center. *Data Documentation: Part D Event*. Available at: https://resdac.org/cms-data/files/pde/data-documentation. Accessed April 24, 2026.
38. Hoerl AE, Kennard RW. Ridge regression: biased estimation for nonorthogonal problems. *Technometrics*. 1970;12(1):55-67. doi:10.1080/00401706.1970.10488634
39. Friedman JH. Greedy function approximation: a gradient boosting machine. *The Annals of Statistics*. 2001;29(5):1189-1232. doi:10.1214/aos/1013203451
40. Liu TY. Learning to rank for information retrieval. *Foundations and Trends in Information Retrieval*. 2009;3(3):225-331. doi:10.1561/1500000016
41. Jarvelin K, Kekalainen J. Cumulated gain-based evaluation of IR techniques. *ACM Transactions on Information Systems*. 2002;20(4):422-446. doi:10.1145/582415.582418
42. Ratner A, Bach SH, Ehrenberg H, Fries J, Wu S, Re C. Snorkel: rapid training data creation with weak supervision. *Proceedings of the VLDB Endowment*. 2017;11(3):269-282. doi:10.14778/3157794.3157797
43. Goncalves A, Ray P, Soper B, Stevens J, Coyle L, Sales AP. Generation and evaluation of synthetic patient data. *BMC Medical Research Methodology*. 2020;20:108. doi:10.1186/s12874-020-00977-1
44. Cochran WG. *Sampling Techniques*. 3rd ed. New York: John Wiley & Sons; 1977.
