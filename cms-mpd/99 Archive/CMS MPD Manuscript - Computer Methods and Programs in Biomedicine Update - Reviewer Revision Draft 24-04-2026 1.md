---
title: CMS-MPD-Recommendation reviewer-focused manuscript for Computer Methods and Programs in Biomedicine Update
date: 2026-04-17
status: submission-draft
target_journal: Computer Methods and Programs in Biomedicine Update
tags:
  - manuscript
  - cmpb-update
  - reviewer-focused
  - cms-mpd
aliases:
  - CMPB Update reviewer revision draft
---

# CMS-MPD-Recommendation: A reproducible, explainable, policy-aware pipeline for Medicare Part D plan recommendation

> [!info] Submission preparation note
> This draft is the reviewer-focused rewrite aligned to [[CMS MPD Manuscript - Computer Methods and Programs in Biomedicine Update - Revision]]. It keeps the current local evidence base but makes the data-provenance boundary, reproducibility lock, comparator logic, and limitations more explicit for reviewers and general readers.

## Title page

**Title:** CMS-MPD-Recommendation: A reproducible, explainable, policy-aware pipeline for Medicare Part D plan recommendation

**Running title:** Explainable Medicare Part D recommendation pipeline

**Authors:** Author A; Author B; Author C

**Affiliations:** TODO

**Corresponding author:** TODO

**Article type:** Original software and methods article

## Highlights

- Quarter-frozen CMS Part D public files drive the public pipeline.
- Public and PDE-compatible data layers are separated explicitly.
- Deterministic cost simulation precedes constrained reranking.
- 33,961 rows from 600 scenarios supported held-out evaluation.
- Explanations preserve coverage, access, and restriction trade-offs.

## Abstract

Selecting a Medicare Part D prescription drug plan is a high-dimensional decision problem involving premiums, formularies, utilization restrictions, pharmacy networks, and out-of-pocket spending rules that changed under the Inflation Reduction Act. We present CMS-MPD-Recommendation, a reproducible and explainable software pipeline that integrates public CMS quarterly formulary, pharmacy network, pricing, geography, and beneficiary-cost files with local reference enrichments and a PDE-compatible behavioral layer. A DuckDB medallion architecture normalizes plan, drug, pharmacy, and beneficiary-request data into runtime serving tables. A rules-first engine simulates fill-level annual out-of-pocket cost and emits explanation traces; constrained rerankers then reorder only already simulated plan rows. The current 2025-Q3 full artifact contains 33,961 plan-scenario rows from 600 mixed-source scenarios covering 100 ZIP codes, 460 regimen signatures, and 551 unique NDCs. On 180 held-out scenarios, the tree reranker achieved 0.861 top-1 agreement, 0.934 top-5 overlap, and 0.953 NDCG@5, compared with 0.622, 0.698, and 0.830 for rules-only ranking. The public artifact explicitly separates public CMS plan-design inputs from restricted Prescription Drug Event data, which are treated as a future extension rather than a public dependency. CMS-MPD-Recommendation contributes a policy-aware and explainable software framework for Medicare Part D recommendation under incomplete observability.

## Keywords

Medicare Part D; biomedical software; decision support; explainable recommendation; data engineering; out-of-pocket cost simulation; health informatics

## 1. Introduction

Choosing a Medicare Part D prescription drug plan is a difficult computational and communication task. The plan that is most appropriate for a beneficiary depends on more than premium. It also depends on plan eligibility in the beneficiary's geography, formulary coverage for the beneficiary's medications, utilization-management restrictions, preferred pharmacy access, deductible structure, insulin protections, low-income subsidy status, and the way those factors interact over a full coverage year. A system that does not resolve these dependencies explicitly risks recommending plans that appear attractive on one dimension while imposing hidden access or cost trade-offs on another.

This problem has become more important in the post-Inflation Reduction Act environment. The redesign of the Part D benefit changed beneficiary liability and sponsor incentives, especially beginning in 2025 [6-9]. At the same time, utilization restrictions, preferred pharmacy network design, and plan responses to high-cost or negotiated drugs remain active components of plan behavior [10-15]. Recent post-IRA studies also show that plan design can shift through deductibles, coinsurance, premium changes, formulary size, and coverage-option structure [29-31]. A useful recommendation system in this domain therefore cannot be quarter-agnostic or policy-agnostic. It must be explicit about what data were available, what policy assumptions were applied, and what cannot be inferred from public files alone.

CMS-MPD-Recommendation was built to address that requirement. The project combines a local DuckDB medallion pipeline, a rules-first recommendation engine, a mixed-source scenario-generation workflow, and an optional constrained reranking layer. The system is designed for decision support rather than autonomous plan selection. It emphasizes explainability, reproducibility, and explicit separation between public CMS plan-design files and any behavioral data layer that resembles Prescription Drug Event records.

This manuscript is written as a software and methods paper. Its contribution is not a claim to solve Medicare Part D choice in a general sense. Its contribution is a concrete, reproducible pipeline that:

- ingests quarter-frozen public CMS plan-design data into auditable tables;
- performs fill-level beneficiary out-of-pocket simulation using transparent rules;
- surfaces explanation traces and guardrails with every recommendation;
- evaluates constrained reranking on scenario-held-out data while preserving deterministic plan facts.

The manuscript also states the system's boundaries clearly. The public artifact depends on public CMS files and local reference enrichments. Full CMS Prescription Drug Event data remain restricted and are treated here as a future extension rather than a public requirement [18-20].

## 2. Related work and policy context

Medicare Part D plan choice has long been recognized as difficult for beneficiaries. Prior work showed that many beneficiaries do not choose the lowest-cost plan that fits their medication needs [1-3]. Econometric work similarly found that beneficiaries may overweight premiums relative to expected out-of-pocket cost, while later panel evidence showed that some beneficiaries do learn and switch plans when status-quo costs rise [21,22]. Recent survey evidence after open enrollment also suggests that many beneficiaries do not actively compare plans at all [25]. Patient-centered decision aids and counseling interventions can improve navigation, but those studies also show that usable plan comparison requires understandable explanation rather than raw attribute display alone [1,2,4,5].

Experimental and implementation evidence further supports the need for concise, explanation-centered recommendation outputs. Simplifying Plan Finder's default financial display improved older adults' ability to choose lower-cost Part D plans without reducing average plan quality or pharmacy network size [23]. The CHOICE decision-aid trial showed that personalized expert-like recommendations increased plan switching and satisfaction with the decision process among Medicare Part D enrollees [24]. GAO's Plan Finder oversight report also shows that official comparison tools depend on pricing-data checks, sponsor correction processes, and usability feedback loops, reinforcing that recommendation software should expose data-quality and provenance assumptions rather than hiding them [26].

Recent policy and market changes make the computational problem more dynamic. CMS redesign guidance and implementation materials document major changes in beneficiary liability, including the changed structure of the 2025 Part D benefit and ongoing affordability reforms [6-9]. These changes matter because a recommender that assumes a static pre-redesign benefit will misestimate beneficiary liability for current plan years.

The empirical policy literature also supports a multi-objective plan-comparison approach. Utilization restrictions increased substantially across Part D plans over the last decade [10]. Brand-versus-generic out-of-pocket signals can be misleading from the beneficiary perspective [11,12]. Preferred branded products, insulin, and other protected or high-cost therapies create plan-comparison contexts in which list price, formulary status, and beneficiary out-of-pocket cost do not move together cleanly [13-15].

For biomedical software, the key methodological lesson is that ranking accuracy alone is not enough. Reviews of health recommender systems emphasize that real-world usefulness depends on fit between the algorithm and the decision context [16,17]. More recent health recommender and explainable clinical decision-support reviews argue for broader evaluation, stakeholder workflow fit, and interpretable outputs rather than algorithmic performance alone [32,33]. In Medicare Part D, that means preserving access and coverage explanations, surfacing evidence gaps, and treating machine learning as an assistive layer rather than the source of truth.

## 3. Materials and data sources

### 3.1 Provenance model and study boundary

The single most important data-provenance rule in this study is that the public artifact is based on public-quarterly CMS plan-design data, not on unrestricted beneficiary claims. The system combines three layers of input:

1. **Public CMS quarterly plan-design files**, which describe plan structure, formularies, pricing, pharmacy networks, geography, exclusions, and beneficiary cost rules [18].
2. **Local reference enrichments**, including RXCUI property pulls from the NLM RxNav/RxNorm API, ZIP geography attributes derived with the `uszipcode` Python library, and insulin reference mappings informed by the CMS CY 2021 Part D Senior Savings Model NDC list [34-36].
3. **A PDE-compatible behavioral layer**, implemented locally as `pde.csv` and `bronze.pde_sample`, whose field semantics are aligned to the ResDAC Part D Event data documentation and used for utilization defaults and mixed-source scenario generation rather than as public claims-ground-truth [37].

Full CMS Part D claims and Prescription Drug Event data are restricted, require CMS approval, and are not part of the public replication boundary for this manuscript [19,20]. Table 1 summarizes these source families, their working grains, and the public-versus-local provenance boundary used throughout the study. The public manuscript therefore reports a recommendation system under incomplete observability rather than a claims-ground-truth optimizer.

### 3.2 Public CMS source families

The 2025-Q3 full build ingests the following public CMS source families:

- plan information;
- basic formulary;
- beneficiary cost;
- insulin beneficiary cost;
- quarterly drug pricing;
- geographic locator;
- excluded drugs;
- indication coverage;
- pharmacy network files.

These files correspond to the public CMS Part D formulary, pharmacy network, and pricing release used for plan transparency and plan-comparison tooling [18].

### 3.3 Local reference enrichments

The system also uses study-side reference enrichments that are sourced separately from the public CMS plan-design release:

- `bronze.rxcui_properties` and related drug-reference tables, materialized from local pulls against the NLM RxNav/RxNorm API, for medication naming, synonym resolution, and RXCUI-linked properties [34];
- `us_zipcode_geo.csv` and `bronze.us_zipcode_geo`, derived with the `uszipcode` library, for ZIP latitude, longitude, county, and density attributes [35];
- `insulin_ref.csv` and `bronze.insulin_reference`, informed by the CMS CY 2021 Part D Senior Savings Model NDC list, for insulin identification and insulin-specific handling [36].

These references are not substitutes for CMS plan data. They are local enrichment layers used to improve medication matching, service-area resolution, pharmacy access summaries, and subgroup-sensitive explanation.

### 3.4 PDE-compatible behavioral layer

The local file `pde.csv` is used as a PDE-compatible local sample, not as a claim that the public artifact contains full CMS Prescription Drug Event data. Its field semantics and event-style structure were aligned to the ResDAC Medicare Part D Event data documentation so that the local sample preserves a beneficiary-drug-event shape suitable for defaults and scenario templating [37]. In the current public study state, this layer is used to estimate medication quantity defaults, fills-per-year defaults, and PDE-like scenario templates. It is not treated as production beneficiary truth, and it is not necessary to understand the public plan-design pipeline itself.

This distinction is critical for reviewers. Public CMS quarterly plan files are open and reproducible [18]. Full Part D claims and PDE data are restricted [19,20]. The current manuscript explicitly respects that boundary.

### 3.5 Data inputs and provenance summary

**Table 1. Data inputs and provenance.**

| Input family | Example local table/file | Main grain | Primary use | Public/restricted status |
|---|---|---|---|---|
| CMS plan-design public files | `bronze.plan_information`, `bronze.basic_formulary`, `bronze.pricing`, `bronze.pharmacy_network` | plan, formulary, plan-drug, plan-pharmacy | eligibility, coverage, cost basis, network features | Public |
| CMS cost-rule public files | `bronze.beneficiary_cost`, `bronze.insulin_beneficiary_cost` | plan-tier-channel-day supply | beneficiary cost simulation | Public |
| CMS geography public files | `bronze.geographic_locator` | ZIP/region/county bridge | service-area and geography resolution | Public |
| CMS exclusions and indication files | `bronze.excluded_drugs`, `bronze.indication_coverage` | drug or plan-drug | coverage and explanation logic | Public |
| RXCUI API-derived drug reference enrichment | `bronze.rxcui_properties`, `silver.dim_drug_reference` | NDC/RXCUI | drug identity, synonym resolution, and property lookup | Local enrichment |
| ZIP geography enrichment (`uszipcode`-derived) | `bronze.us_zipcode_geo` | ZIP code | density and distance proxy | Local enrichment |
| Insulin reference mapping (CMS Senior Savings Model-informed) | `bronze.insulin_reference` | NDC/RXCUI | insulin-specific classification | Local enrichment |
| PDE-compatible local sample aligned to PDE documentation | `bronze.pde_sample`, `pde.csv` | beneficiary-drug event compatible | defaults and scenario generation | Local sample / restricted-compatible |

Table 1 therefore separates public CMS plan-design files from study-side reference enrichments and the PDE-compatible local sample so reviewers can see which inputs are directly reproducible from public CMS releases and which are local aids used to support matching, scenario construction, and explanation.

## 4. Methods

### 4.1 Reproducible software artifact and release lock

The study was run from the `CMS-MPD-Recommendation` workspace in `sandbox`, with a quarter-frozen 2025-Q3 full build and pinned runtime dependencies listed in `requirements.txt`: DuckDB 1.5.1, NumPy 2.3.4, pandas 2.3.3, Streamlit 1.55.0, and pytest 9.0.2. The locked experiment identifiers for the current artifact are:

- `snapshot_quarter = 2025-Q3`
- `build_profile = full`
- `dataset_schema_version = request_features_v4`
- `feature_version = research_v4`
- `weak_label_version = weak_label_v2`
- `generation_version = scenario_generation_v1`
- `teacher_feature_policy = student_safe`
- `generator_seed = 42`

For internal manuscript preparation, the locked software state is the local workspace snapshot associated with this 2026-04-17 reviewer revision. Before external submission, this exact state should be archived under a release tag and DOI and cited as the formal software release. The important methodological point is that the manuscript, dataset metadata, and code constants are synchronized to the same schema and weak-label versions.

### 4.2 Medallion data engineering architecture

CMS-MPD-Recommendation uses a bronze-silver-gold medallion pipeline implemented in DuckDB.

**Bronze** preserves raw source inputs with lineage fields (`source_file`, `snapshot_quarter`, `load_ts`). The bronze layer is intentionally permissive because public CMS flat files can vary in formatting. Pharmacy-network ingestion is fault tolerant so malformed split-file rows do not abort the build.

**Silver** normalizes business entities and canonical keys. It includes:

- `silver.dim_plan`
- `silver.dim_zipcode`
- `silver.bridge_plan_service_area`
- `silver.dim_drug_reference`
- `silver.drug_utilization_defaults`
- `silver.fact_plan_drug_coverage`
- `silver.fact_plan_pharmacy`
- `silver.plan_beneficiary_cost_rules`
- `silver.plan_insulin_cost_rules`

**Gold** materializes runtime-serving tables used directly by recommendation and modeling:

- `gold.plan_service_area`
- `gold.plan_channel_summary`
- `gold.plan_preferred_pharmacy_locations`
- `gold.plan_formulary_summary`
- `gold.plan_network_summary`
- `gold.plan_drug_cost_basis`
- `gold.plan_summary`
- `gold.drug_input_defaults`
- `gold.recommendation_features`

This architecture matters methodologically because it separates raw source preservation from business normalization and runtime serving. Reviewers can therefore ask not only "what was the final metric?" but also "what exact transformed facts supported that metric?"

### 4.3 Canonical keys and data contracts

The study uses canonical keys to avoid ambiguous joins across public CMS file families:

- `plan_key = CONTRACT_ID + PLAN_ID + SEGMENT_ID`, with blank segment mapped to `000`;
- `contract_plan_key = CONTRACT_ID + PLAN_ID` for segment-less joins;
- `formulary_id` for plan-formulary linkage;
- normalized 5-digit `zip_code`;
- CMS `county_code`;
- normalized 11-digit `ndc`;
- normalized `rxcui`;
- normalized `days_supply` in {30, 60, 90};
- beneficiary-cost `coverage_level`;
- integer `tier_level_value`.

These data contracts are not implementation trivia. They are core methodological choices. If they are wrong, the system can assign the wrong formularies, the wrong geography, or the wrong beneficiary cost logic to a plan.

#### Mathematical view of transformation logic

Let the raw input family be:

$$
\mathcal{R} = \{R_1, R_2, \dots, R_n\},
$$

where each $R_i$ is a public CMS or local reference source table. The medallion pipeline can be written as a composition of deterministic transformation operators:

$$
\mathcal{R}
\xrightarrow{\mathcal{B}}
\mathcal{B}(\mathcal{R})
\xrightarrow{\mathcal{S}}
\mathcal{S}(\mathcal{B}(\mathcal{R}))
\xrightarrow{\mathcal{G}}
\mathcal{G}(\mathcal{S}(\mathcal{B}(\mathcal{R}))).
$$

Here, $\mathcal{B}$ denotes bronze ingestion with lineage preservation, $\mathcal{S}$ denotes silver normalization onto canonical keys, and $\mathcal{G}$ denotes gold serving-layer materialization. At a table level, the core plan-drug fact can be expressed as:

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

where $s$ denotes normalized day supply and $\gamma$ denotes projection and aggregation to the plan x drug x day-supply grain. The runtime cost basis is then:

$$
\text{GoldCostBasis}
=
\text{SilverCoverage}
\overset{\text{left}}{\bowtie}
\text{BenefitRules}
\overset{\text{left}}{\bowtie}
\text{InsulinRules}.
$$

Service-area eligibility is also represented as a deterministic relation. Let $A(z,p)=1$ when ZIP code $z$ is served by plan $p$. Then:

$$
A(z,p)=1
\iff
\exists c \; : \; (z,c)\in \text{ZipCountyBridge}
\wedge
(p,c)\in \text{PlanCountyBridge}.
$$

These expressions are useful because they make the manuscript's main systems claim explicit: recommendation-time evidence is not produced by opaque feature synthesis alone. It is produced by a sequence of key-preserving relational transformations from public plan-design data into executable plan, geography, network, and cost objects.

### 4.4 Beneficiary request schema

The runtime request schema includes beneficiary ZIP code, age band, low-income subsidy status, chronic-condition flags, pharmacy preference, user role, decision focus, and a medication list. Each medication can be provided by drug name, RXCUI, or NDC, with optional quantity and annual-fill overrides.

Medication resolution follows a strict order:

1. exact NDC;
2. exact RXCUI;
3. exact preferred name;
4. exact synonym;
5. prefix match on preferred name or synonym.

Approximate matches are retained as explicit evidence gaps rather than silently treated as exact matches. This design follows the logic of medication-terminology infrastructure: RxNorm provides normalized clinical-drug concepts and normalized NDC-to-RXCUI associations where supported, while the FDA NDC Directory identifies listed drug packages but does not itself establish coverage or reimbursement [27,28]. The recommender therefore treats drug identity and plan coverage as two separate checks.

### 4.5 Public CMS ingestion and normalization

The extraction and build workflow is:

1. locate quarter-frozen CMS source files and local references;
2. extract archive members into `data/staging/<snapshot>/raw`;
3. load bronze tables with lineage columns;
4. normalize plan, geography, drug, pharmacy, and cost-rule entities into silver tables;
5. materialize gold serving tables for runtime recommendation and model dataset generation.

The gold serving layer is the operational contract of the software. In particular, `gold.plan_drug_cost_basis` joins plan-drug coverage, tier, UM flags, exclusions, indication limits, pricing basis, deductible applicability, standard beneficiary-cost rules, and insulin overrides into a runtime-ready plan-drug-day-supply table.

### 4.6 Recommendation and cost-simulation method

For a request scenario `s`, the engine first limits candidate plans to plans serving the beneficiary ZIP code. It then resolves medication defaults and, for each candidate plan and medication, retrieves plan-drug cost basis, coverage status, restriction flags, pricing inputs, and channel availability.

Annual beneficiary out-of-pocket cost is simulated at fill level. The engine:

- normalizes day supply to 30, 60, or 90 days;
- applies contract-year-aware benefit design selection;
- supports automatic use of `2025_redesign` for current data and explicit `2024_standard` historical modeling when needed;
- applies insulin-specific overrides where present;
- applies low-income subsidy adjustments after base liability is computed;
- aggregates fill-level results into annual premium, annual drug out-of-pocket cost, and annual total cost.

The runtime engine therefore produces beneficiary-facing economic outputs rather than only relative model scores.

#### Mathematical view of the recommendation workflow

Let a beneficiary request scenario be:

$$
s = (z, M, \ell, h, r, f),
$$

where $z$ is ZIP code, $M$ is the medication set, $\ell$ is low-income subsidy status, $h$ is pharmacy preference, $r$ is user role, and $f$ is decision focus. The eligible plan set is:

$$
P(z)=\{p : A(z,p)=1\}.
$$

For each medication $m \in M$, the resolver applies an ordered matching function $\rho(m)$ across NDC, RXCUI, preferred name, synonym, and prefix matches. The resolved medication record contains normalized day supply, quantity, and annual fill count. If $n_m$ annual fills are assigned to medication $m$, the fill-event set is:

$$
E_m=\left\{\left(k,\operatorname{round}\left((k-1)\frac{365}{n_m}\right)\right) : k=1,\dots,n_m\right\}.
$$

For plan $p$, drug $m$, fill $k$, and feasible channel $c$, the allowed-cost proxy is:

$$
g_{pmkc}=\max(u_{pms}q_{mk} + f_{pc\tau s}, \phi_{pc}),
$$

where $u_{pms}$ is unit cost for plan $p$, medication $m$, and normalized day supply $s$; $q_{mk}$ is fill quantity; $f_{pc\tau s}$ is a channel-specific fee term by channel $c$, tier family $\tau$, and day supply $s$; and $\phi_{pc}$ is any channel floor price.

The base beneficiary liability for a fill is then computed through a policy-year-aware rule operator:

$$
c^{base}_{pmkc,y}=\chi_y(g_{pmkc}, \tau, d, \iota, \ell, c),
$$

where $y$ is contract year, $d$ is deductible applicability, and $\iota$ is an insulin override indicator. The annual out-of-pocket contribution for the fill is:

$$
o_{pmkc,y}=\min\left(c^{base}_{pmkc,y}, \; cap_y - O_{k-1}\right),
$$

with $cap_{2025}=2000$ under the 2025 redesign branch and $O_{k-1}$ denoting accumulated beneficiary out-of-pocket cost before fill $k$. The annual plan-level total used in ranking is:

$$
T_p(s)=Premium_p+\sum_{m \in M}\sum_{k \in E_m}\min_{c \in C_{pmk}} o_{pmkc,y},
$$

where $C_{pmk}$ is the feasible channel set for plan $p$, medication $m$, and fill $k$.

To preserve coverage safety, the rules engine does not rank solely by a scalar score. It constructs a lexicographic key:

$$
K_p =
\left(
b_p,
-q_p,
-F_p,
T_p,
U_p,
H_p,
N_p
\right),
$$

where $b_p$ is the coverage bucket, $q_p$ is the priced-drug count, $F_p$ is the fit score, $U_p$ is uncovered-drug burden, $H_p$ is restriction burden, and $N_p$ is network-risk burden. Plans are ordered lexicographically by $K_p$, which formalizes the implementation choice that coverage completeness and priceability are first-order ordering decisions rather than soft penalties.

### 4.7 Scoring, constraints, and reranking

The recommendation process is deliberately layered.

First, the rules engine computes deterministic evidence and a rules-first rank. The rules layer prioritizes:

- complete medication coverage;
- lower annual total cost;
- lower restriction burden;
- better pharmacy fit;
- insulin safety;
- fewer evidence gaps.

Second, for research supervision, replayed plan-scenario rows are assigned a weak-label target that makes the study's preference structure explicit. That target is derived from the already simulated coverage, cost, restriction, network, and evidence-quality fields rather than from an external enrollment or outcome label.

Third, optional learned reranking uses only those already simulated candidate rows as input. The model cannot invent eligibility, coverage, cost, or geography facts. It can only reorder rows that were already produced by the deterministic engine.

At inference, hybrid reranking is constrained to three safety-preserving buckets: plans with full coverage and full priceability, plans with at least one priced medication but incomplete priceability, and fallback or unpriceable plans. Within each bucket, ordering is determined first by predicted model score, then by priced-drug count, then by rules score, then by annual total cost, then by uncovered-drug burden, and finally by restriction burden. This constraint is important for regulated decision support because it means the learned layer changes presentation order, not the underlying plan evidence.

### 4.8 Explainability outputs

Each recommendation includes structured explanation groups for:

- coverage fit and uncovered drugs;
- utilization management, including prior authorization, step therapy, and quantity limits;
- insulin-specific affordability risks;
- deductible exposure;
- preferred retail, nonpreferred retail, and mail-order access;
- estimated annual out-of-pocket cost;
- medication-match confidence and other data-quality gaps.

The explanation layer is generated alongside the recommendation rather than appended later. This enables reviewer inspection of why a plan ranked highly and whether that ranking is safe to trust.

### 4.9 Feature schema and model feature groups

The reranking dataset combines both human-interpretable scoring signals and richer plan-scenario descriptors. Numeric features include current rules rank and score, fit sub-scores, annual premium, annual drug out-of-pocket cost, annual total cost, covered and uncovered drug counts and shares, restriction counts, deductible and initial-coverage exposure, negotiated-price totals, insulin flags, medication-match counts, network counts, formulary rates, geography proxies, and missing-data indicators. Categorical features include coverage status, network flag, LIS status, age band, pharmacy preference, ZIP density category, scenario bundle, scenario profile, and fallback group.

For reviewer readability, these can be grouped as follows.

**Table 2. Feature groups used in modeling and ablation.**

| Feature group | Example variables | Why included |
|---|---|---|
| Rules-engine summary | `current_rules_rank`, `current_rules_score`, `fit_score`, `coverage_score`, `access_score` | Preserve deterministic ranking context for dataset analysis and teacher-feature ablations |
| Cost and liability | `annual_premium`, `annual_drug_oop`, `annual_total_cost`, `deductible_exposure_total`, `lis_adjusted_oop_total`, `negotiated_price_total` | Reflect beneficiary-facing economic burden |
| Coverage and exclusions | `coverage_status`, `covered_drug_share`, `uncovered_drug_count`, `excluded_drug_count`, `missing_price_drug_count` | Preserve medication-safety and coverage completeness |
| Restriction burden | `restriction_count`, `pa_rate`, `st_rate`, `ql_rate`, `channel_unavailable_count` | Capture clinically and operationally relevant friction |
| Network and access | `network_flag`, `network_risk_score`, `preferred_retail_count`, `preferred_mail_count`, `nearest_preferred_distance_bucket` | Represent pharmacy usability and access risk |
| Medication identity and evidence quality | `approximate_match_count`, `exact_match_count`, `match_review_required_flag`, `unknown_network_data_flag`, `unsafe_reason_count` | Prevent false confidence when evidence is weak |
| Beneficiary and scenario context | `lis_status`, `age_band`, `pharmacy_preference`, `scenario_bundle`, `scenario_profile`, `beneficiary_chronic_condition_count` | Preserve context and subgroup sensitivity |

The current study trains two reranker families on this feature frame. The linear reranker is ridge regression implemented on standardized numeric features plus one-hot encoded categorical features, with default regularization `alpha = 5.0`. The tree reranker is a lightweight additive shallow regression-tree ensemble trained on residuals, with default settings `learning_rate = 0.12`, `n_estimators = 40`, `max_depth = 3`, and `min_samples_leaf = 5`.

The default trained artifact uses the `student_safe` policy. Under that policy, the dataset still records teacher-style rules summary fields such as `current_rules_rank`, `current_rules_score`, `fit_score`, `cost_score`, `premium_score`, `coverage_score`, `access_score`, and `stability_score` for audit and ablation analysis, but those numeric teacher features are excluded from the default student feature matrix used in training. Reviewers should therefore distinguish between columns present in the replay dataset and the smaller default feature subset actually exposed to the trained student artifact.

### 4.10 Dataset generation and weak-label construction

The training dataset is generated by replaying canonical scenarios through the same recommendation engine used at runtime. Each row is a plan under a specific scenario. In this flow, weak labels are the bridge between deterministic recommendation replay and supervised reranker training. They are not treated as a clinical gold standard. Instead, they encode the study's recommendation preference structure by rewarding safer and more useful plan rows according to coverage, cost, restrictions, network risk, and evidence quality.

Weak labels serve three roles in the pipeline. First, they convert plan-scenario replay rows into an ordered supervision target. Second, they make the study's preference structure explicit and auditable because every reward and penalty term is visible. Third, they enable held-out-by-scenario evaluation when real enrollment, switching, or outcome labels are unavailable.

This design makes the evaluation honest about what it measures. Agreement with the weak label indicates alignment with the study's stated decision logic, not proof of downstream beneficiary outcomes.

#### Mathematical view of weak-label and reranking logic

The weak-label target used for reranking is intentionally domain-shaped rather than neutral. For plan $p$, the current implementation can be summarized as:

$$
W_p =
1000 \cdot \mathbf{1}\{\text{coverage\_status}_p = full\}
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

where:

- $R_p$ is the current rules score;
- $T_p$ is annual total cost;
- $U_p$ is uncovered-drug count;
- $E_p$ is excluded-drug count;
- $M_p$ is missing-price burden;
- $C_p$ is channel-unavailable burden;
- $H_p$ is restriction count;
- $A_p$ is approximate-match burden;
- $Mail_p$ is mail-order dependency burden;
- $Ins_p$ is insulin-risk burden;
- $InsNP_p$ is insulin dependence on non-preferred channels;
- $Net_p$ is network-risk burden.

The coefficient structure is intentionally shaped so that coverage failures dominate ordinary cost differences. The full-coverage bonus rewards plans that keep the medication set intact. The uncovered, excluded, and missing-price penalties discourage recommendations that look inexpensive only because part of the regimen is not reliably priceable. The channel-unavailable and restriction penalties represent operational friction. The approximate-match penalty reduces confidence in rows built from weak medication identity. The mail-order, insulin-risk, insulin-nonpreferred, and network-risk penalties preserve clinically and operationally important access burdens that would be easy to hide inside a single cost score.

The simpler heuristic comparator is:

$$
H_p =
500 \cdot \mathbf{1}\{\text{coverage\_status}_p = full\}
 + R_p
 - T_p
 - 200U_p
 - 30H_p
 - 10Net_p.
$$

The constrained reranker then estimates a model score $\hat{W}_p$, but only within safety-preserving buckets. If $\beta(p)$ maps each plan to a coverage-priceability bucket, hybrid ordering is:

$$
\pi^{hybrid}(p) = \left(\beta(p), -\hat{W}_p\right),
$$

with no cross-bucket promotion. In practical terms, a weak-coverage or unpriceable plan cannot leap ahead of a fully covered and fully priceable plan solely because of model score. This is the central mathematical expression of the system's safety constraint and the main reason weak-label alignment should be interpreted as internal ranking validity rather than external clinical validity.

### 4.11 Scenario generation

The current full artifact uses mixed-source canonical scenarios. The generation flow is intentionally structured so that model training begins from beneficiary-like requests rather than from disconnected plan rows. The pipeline:

1. draws a stratified sample of service-area ZIP codes so the scenario set spans the geographic density mix present in `gold.plan_service_area`;
2. builds drug pools from the gold catalog, including generic, brand, insulin, specialty, restricted, and lower-cost pools;
3. assembles PDE-derived or PDE-compatible regimen pools when local event-style templates are available;
4. generates benchmark and stress regimens from the catalog pools when a PDE-derived template is unavailable or when harder edge cases are needed;
5. assigns mixed-source scenarios across the canonical bundles and source kinds (`pde`, `benchmark`, `stress`);
6. validates each generated scenario against its intended bundle/profile before accepting it into the canonical set;
7. materializes a scenario manifest that records bundle counts, source mix, regimen-signature counts, unique NDC and RXCUI counts, and validation rates.

Six scenario bundles are represented:

- access-sensitive
- insulin-chronic
- low-utilizer
- maintenance-generic
- mixed-restriction
- specialty-high-cost

Each bundle contains 100 scenarios. The overall source mix is 180 benchmark scenarios, 300 PDE-derived or PDE-compatible scenarios, and 120 stress scenarios. The canonical generator version is `scenario_generation_v1`.

This design benefits the reranker in several ways. It broadens training coverage beyond only common medication combinations, preserves representation across clinically and operationally important bundles, adds harder stress cases so the reranker sees edge conditions, and keeps the training data close to runtime behavior because the same recommendation engine is replayed to build feature rows. In effect, scenario generation produces beneficiary-like inputs, and replay through the rules engine turns those inputs into the same evidence rows used at recommendation time. The learned model is therefore a reranker over realistic simulated plan comparisons rather than over disconnected synthetic labels.

### 4.12 Experimental design and comparators

Evaluation is performed with a held-out-by-scenario split rather than row-random splitting. The training set contains 420 scenarios and 23,384 plan-scenario rows. The test set contains 180 scenarios and 10,577 rows. This design reduces leakage from repeated plan rows associated with the same beneficiary request.

The evaluated systems are:

- rules-only ranking;
- heuristic baseline;
- linear reranker;
- tree reranker;
- ablation systems using cost-only, cost-plus-restrictions, cost-plus-restrictions-plus-network, and full feature sets.

The heuristic baseline is reported explicitly as an operational comparator. A fully frozen external Medicare Plan Finder comparator for the exact same quarter and medication cases was not yet packaged into this public artifact. Rather than imply comparability that does not yet exist, the manuscript reports transparent internal comparators that can be reproduced from the same frozen quarter and code state.

### 4.13 Primary metrics and guardrails

Primary metrics include top-1 agreement, top-5 overlap, top-10 overlap, NDCG@5, NDCG@10, top-k full-coverage rate, average top-k total cost, average uncovered medications, blocker-classification precision, review-trigger rate, and missing-data behavior.

Guardrails were defined prospectively:

- top-5 ranking should improve;
- top-10 ranking should improve;
- uncovered-medication burden should not worsen.

The last guardrail is especially important because improved ranking agreement is not clinically or operationally meaningful if it increases exposure to uncovered drugs.

### 4.14 Three-case recommendation retrieval protocol

To make the research flow concrete for readers, we also ran three prescription samples through the current local recommendation engine. These cases were designed as functional probes of the pipeline rather than as clinical recommendations. Each case used ZIP code `90001`, age band `65-74`, LIS status `none`, pharmacy preference `auto`, user role `counselor`, top-5 output, automatic 2025 benefit-design selection, and both rules-only and hybrid ranking.

The cases were selected to stress different parts of the workflow:

| Case | Intended workflow stress test | Medication inputs |
|---|---|---|
| Case 1: maintenance generics | Exact-name resolution, low-cost chronic generics, 90-day fills | atorvastatin 20 mg tablet; amlodipine 5 mg tablet; tamsulosin 0.4 mg capsule |
| Case 2: insulin plus GLP-1 | Exact NDC resolution, insulin handling, high-cost brand therapy, UM flags | Toujeo NDC `00024586903`; Ozempic NDC `00169413013` |
| Case 3: specialty plus anticoagulant | Specialty drug handling, high-cost biologic, brand anticoagulant, network trade-offs | Humira NDC `00074012402`; Eliquis NDC `00003089421` |

For each case, the workflow was:

1. resolve all medications using exact name or exact NDC;
2. construct the ZIP-specific candidate plan set from `gold.plan_service_area`;
3. compute rules-first recommendations and hybrid recommendations;
4. record candidate counts, full-coverage counts, partial-coverage counts, unknown-network counts, top-ranked plan, annual cost estimate, coverage status, network flag, restriction count, uncovered-drug count, and counselor-facing watchouts.

The higher-risk cases used NDCs intentionally. During pilot execution, the text-only insulin input triggered the system's manual-review guardrail because the typed drug string had multiple possible matches and low local coverage for the top candidate. That behavior is part of the intended safety design: ambiguous high-impact drug matching should stop ranking until an exact drug identity is supplied.

## 5. Results

### 5.1 Artifact characteristics

The current 2025-Q3 full artifact contains:

- 33,961 plan-scenario rows;
- 600 scenarios;
- 100 ZIP codes;
- 460 regimen signatures;
- 551 unique NDCs;
- 88 completed dataset chunks;
- balanced representation across six scenario bundles.

These counts reflect the actual local metadata artifact rather than a proposal for future evaluation.

### 5.2 Main ranking results

**Table 3. Main held-out-by-scenario ranking results.**

| System | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | NDCG@10 | Top-5 full coverage | Top-5 avg total cost | Top-5 avg uncovered | Blocker precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rules only | 0.622 | 0.698 | 0.786 | 0.830 | 0.828 | 0.660 | 198.10 | 0.414 | 0.950 |
| Heuristic baseline | 0.811 | 0.899 | 0.953 | 0.924 | 0.920 | 0.660 | 81.79 | 0.463 | 0.989 |
| Linear reranker | 0.628 | 0.879 | 0.919 | 0.899 | 0.890 | 0.660 | 83.06 | 0.459 | 0.994 |
| Tree reranker | 0.861 | 0.934 | 0.962 | 0.953 | 0.947 | 0.660 | 83.07 | 0.459 | 0.994 |

The tree reranker improved top-1 agreement by 0.239 absolute points relative to rules-only ranking, improved top-5 overlap by 0.237 absolute points, and improved NDCG@5 by 0.123 absolute points. Relative to the heuristic baseline, the tree reranker improved top-1 agreement, top-5 overlap, top-10 overlap, and NDCG while maintaining similar average top-5 total cost.

### 5.3 Comparator interpretation

The results support two distinct claims.

First, the rules engine alone already creates a meaningful decision-support baseline because it is grounded in deterministic plan facts and explicit explanations. Second, constrained reranking can improve ordering quality over that baseline without replacing the underlying evidence model.

The heuristic baseline is important here because it approximates a simpler operational comparator. It performs strongly, especially relative to rules-only ranking, which suggests that practical plan ranking already benefits from obvious cost and coverage heuristics. The tree reranker's value is therefore not that it beats a weak straw-man baseline. Its value is that it improves upon an already strong heuristic comparator while remaining constrained to deterministic evidence rows.

### 5.4 Ablation and sensitivity results

**Table 4. Ablation results.**

| Feature subset | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | Top-5 avg total cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Cost only | 0.806 | 0.882 | 0.935 | 0.926 | 80.75 | 0.469 |
| Cost plus restrictions | 0.833 | 0.903 | 0.954 | 0.937 | 82.57 | 0.460 |
| Cost plus restrictions plus network | 0.872 | 0.950 | 0.973 | 0.960 | 82.99 | 0.459 |
| Full feature set | 0.867 | 0.940 | 0.971 | 0.957 | 82.94 | 0.459 |

The ablation analysis shows that cost, restriction, and network information account for most of the learnable signal. This is a favorable result for reviewer interpretability because it means the model's performance is not dependent on a large opaque feature space. A relatively compact and explainable subset already captures most of the gain.

The fact that the cost-plus-restrictions-plus-network subset slightly outperformed the nominal full feature set on some metrics is also informative. It suggests that model complexity should be justified conservatively in this domain.

### 5.5 Scenario-bundle results

**Table 5. Tree-reranker performance by scenario bundle.**

| Scenario bundle | Top-1 agreement | Top-5 overlap | NDCG@5 | Top-5 full coverage | Top-5 avg total cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Access-sensitive | 1.000 | 0.979 | 1.000 | 0.771 | 112.81 | 0.307 |
| Insulin-chronic | 0.886 | 0.954 | 0.950 | 0.909 | 40.04 | 0.091 |
| Low-utilizer | 0.844 | 0.938 | 0.956 | 0.656 | 85.75 | 0.375 |
| Maintenance-generic | 0.762 | 0.895 | 0.894 | 0.790 | 90.64 | 0.248 |
| Mixed-restriction | 0.875 | 0.950 | 0.980 | 0.475 | 101.25 | 0.775 |
| Specialty-high-cost | 0.781 | 0.881 | 0.923 | 0.394 | 78.27 | 0.900 |

Performance was strongest in access-sensitive and insulin-chronic scenarios. It was weaker in specialty-high-cost and maintenance-generic scenarios, where coverage complexity, cost intensity, or restriction burden can make ranking more brittle. These subgroup differences reinforce the need to present recommendation outputs with visible explanation rather than as opaque scores.

### 5.6 Guardrails and incomplete observability

The evaluation artifact indicated that top-5 and top-10 agreement improved, but the uncovered-not-worse guardrail was not fully satisfied. This is a critical reviewer-facing result. The model can improve ranking agreement while still exposing users to residual coverage trade-offs. The system should therefore be interpreted as a decision-support tool with guardrails, not as an autonomous optimization engine.

Additional operational signals strengthen this interpretation:

- blocker-classification precision remained high;
- unknown-network conditions can still occur in practice;
- match-review-required flags remain important when medication identity is approximate.

These outputs are not peripheral. They are part of the system's safety posture.

### 5.7 Three prescription-sample retrieval results

The three sample cases retrieved recommendations from the current 2025-Q3 local database. Table 6 summarizes the candidate-set behavior.

**Table 6. Candidate-set summaries for three prescription samples.**

| Case | Requested drugs | Service-area candidates | Ranked candidates | Full coverage | Partial coverage | Unknown-network plans | Scenario profile | Rules top plan | Hybrid top plan |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| Maintenance generics | 3 | 126 | 126 | 110 | 16 | 16 | mixed_restriction | Blue Shield 65 Plus (HMO) | Blue Shield 65 Plus (HMO) |
| Insulin plus GLP-1 | 2 | 126 | 126 | 101 | 25 | 16 | specialty_high_cost | Anthem I Carelon Chronic Care (HMO-POS C-SNP) | Aetna Medicare Preferred Plus (HMO-POS) |
| Specialty plus anticoagulant | 2 | 126 | 126 | 99 | 27 | 16 | specialty_high_cost | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) |

Table 7 reports the top hybrid recommendation for each case.

**Table 7. Top hybrid recommendation by sample case.**

| Case | Top hybrid plan | Premium | Drug OOP | Total cost | Coverage | Network | Restrictions | Uncovered | Main watchout |
|---|---|---:|---:|---:|---|---|---:|---:|---|
| Maintenance generics | Blue Shield 65 Plus (HMO) | 0.00 | 0.00 | 0.00 | full | adequate | 0 | 0 | No top-plan watchout; another top-5 plan depended on mail order |
| Insulin plus GLP-1 | Aetna Medicare Preferred Plus (HMO-POS) | 0.00 | 0.00 | 0.00 | full | adequate | 2 | 0 | Mail-order dependence plus prior authorization and quantity limits |
| Specialty plus anticoagulant | Aetna Medicare Preferred Plus (HMO-POS) | 0.00 | 0.00 | 0.00 | full | adequate | 2 | 0 | Mail-order dependence plus prior authorization and quantity limits |

The maintenance-generic case behaved as expected for a low-friction regimen. All three medications resolved by exact name at 90-day supply. The top rules and hybrid rankings were identical, with full coverage, no restrictions, adequate network status, and zero estimated annual total cost among the top plans. This case mainly confirms that the pipeline can execute the simplest maintenance-medication workflow without invoking match-review or coverage fallback logic.

The insulin plus GLP-1 case exercised more of the system. Both drugs were supplied by exact NDC after the text-only insulin input triggered manual review. The top rules and hybrid plans were both fully covered with adequate network status and zero estimated annual total cost, but both retained two utilization-management restrictions. The hybrid reranker moved Aetna Medicare Preferred Plus above the rules-only top C-SNP plan while preserving the same coverage bucket and exposing prior authorization, quantity-limit, and mail-order watchouts.

The specialty plus anticoagulant case exposed a more informative trade-off. Rules-only ranking selected Kaiser Permanente Senior Advantage LA, Orange Co. with full coverage, zero estimated cost, no restrictions, and `no_preferred_retail` network status. The hybrid ranking selected Aetna Medicare Preferred Plus, also with full coverage and zero estimated cost, but with adequate network status and two restrictions. This illustrates why the ranking output must be read together with explanation fields: a plan can be more favorable on restrictions while weaker on preferred-retail access, or better on network status while carrying utilization-management burdens.

## 6. Discussion

This manuscript's main claim is that Medicare Part D recommendation can be implemented as a transparent software pipeline rather than as a black-box ranking problem. That claim is supported by the architecture, the feature design, and the evaluation results.

The most defensible contribution is the explicit separation of roles inside the system. The public CMS quarter determines the plan-design snapshot. The medallion pipeline normalizes that quarter into auditable tables. The rules engine simulates beneficiary-facing cost and access logic. The reranker changes ordering only after those facts exist. This sequence matters because it preserves an explanation trail from raw input to final recommendation.

The results also support a restrained view of machine learning in regulated recommendation. The tree reranker improved internal ranking quality, but the strongest ablation subset was still based on highly interpretable features: cost, restrictions, and network. That is exactly the outcome one would want in a high-stakes domain. It suggests that the model adds value without requiring an opaque, difficult-to-govern feature space. This design is consistent with health recommender-system and clinical decision-support literature that treats interpretability, workflow fit, and real-world evaluation as core requirements rather than optional presentation features [16,17,32,33].

The provenance clarification in this reviewer-oriented revision is equally important. Public CMS quarterly plan files and restricted PDE data are not interchangeable [18-20]. By making the public-versus-restricted boundary explicit, the manuscript avoids overstating what the current artifact can claim. The public software demonstrates a plan-design and decision-support pipeline under incomplete observability. It does not claim to be a full claims-based simulator of beneficiary behavior.

The quarter-aware framing is also methodologically necessary. Part D benefit design changed materially in 2025, and plan incentives continue to evolve [6-9]. A recommendation system that ignores benefit-year logic or quarter-specific public files can produce stale or misleading outputs even if its model metrics appear acceptable.

### 6.1 Methodological interpretation of the sample cases

The three sample cases clarify the research flow in ways that aggregate evaluation metrics do not. First, they show that recommendation retrieval is not a single model call. It is a sequential workflow: drug resolution, candidate plan construction, fill-level cost simulation, explanation generation, rules ranking, and optional constrained reranking. Each step leaves observable traces that can be audited.

Second, the sample cases show why exact drug identity matters. The initial insulin text input triggered manual review before ranking, while exact NDC inputs allowed the insulin, GLP-1, specialty biologic, and anticoagulant cases to proceed. This supports the manuscript's claim that medication matching is part of the safety system rather than a preprocessing detail.

Third, the cases show how rules-only and hybrid ranking can diverge without violating coverage constraints. In the specialty case, rules-only ranking favored a plan with no restrictions but no preferred-retail network status, whereas hybrid ranking favored a plan with adequate network status but two restrictions. That difference is useful for reviewers because it demonstrates that the reranker is operating inside the same full-coverage bucket and changing trade-off ordering rather than erasing core plan facts.

Finally, the sample cases reveal an implementation boundary that should remain visible in the manuscript. The top retrieved plans for ZIP `90001` were county-based MA-PD or HMO/HMO-POS plans, including SNP-like plan names in some rankings. A production deployment should therefore add explicit beneficiary eligibility filters for MA-PD, D-SNP, and C-SNP enrollment constraints before presenting outputs as actionable enrollment advice. In this manuscript, the cases are evidence of software workflow behavior, not beneficiary-specific clinical or enrollment recommendations.

## 7. Limitations

This study has several important limitations that should be stated plainly.

First, the evaluation is internal and scenario-based. Weak-label agreement is an internal validity measure of alignment with the study's explicit preference structure, not a clinical gold standard and not a causal measure of beneficiary outcomes. The current artifact therefore does not prove that beneficiaries would switch to better plans, spend less after enrollment, or experience improved adherence or satisfaction.

Second, public CMS files do not expose all economically relevant signals. Rebates, net prices, some PBM incentive structures, and actual pharmacy-adjudication behavior are only partially or indirectly observable in the public release. The recommender should therefore be interpreted as decision support under incomplete observability rather than as an optimizer against full market truth.

Third, the PDE-compatible layer is not equivalent to unrestricted CMS PDE access. In the current artifact it is a local sample aligned to PDE documentation and used for defaults and scenario generation, not definitive real-world behavior measurement. Any future claims-grounded extension would require restricted CMS data access, formal governance, and updated evaluation.

Fourth, pharmacy access is approximated using network flags and ZIP-based geography rather than full beneficiary travel behavior. Preferred pharmacy distance and channel usability are therefore proxies, not exact access measures.

Fifth, the current public artifact does not yet include a frozen external comparator such as a Medicare Plan Finder export for matched sentinel cases. The heuristic comparator is reproducible and useful, but external face-validity benchmarking remains a next step.

Sixth, post-IRA plan behavior is still evolving. Recent studies report design changes in deductibles, coinsurance, premiums, formularies, and coverage-option structure after the 2025 redesign [29-31]. The software should therefore be evaluated as a quarter-frozen artifact and refreshed for each benefit year before any operational use.

Finally, this manuscript does not yet report prospective usability evaluation with counselors or beneficiaries. Because explanation is central to the system's intended use, that omission is substantive rather than incidental.

## 8. Conclusion

CMS-MPD-Recommendation is a reproducible, explainable, policy-aware software pipeline for Medicare Part D plan recommendation. Its public artifact is built from quarter-frozen CMS plan-design files, local reference enrichments, and a PDE-compatible behavioral layer that is explicitly distinguished from restricted claims data. The system combines medallion data engineering, fill-level out-of-pocket simulation, structured explanation outputs, and constrained reranking. In the current 2025-Q3 full evaluation, the tree reranker improved ranking agreement and NDCG over rules-only ranking while preserving a reviewer-visible evidence model and highlighting unresolved coverage guardrails. The software is therefore best understood as research-ready decision support under incomplete observability, not as an autonomous claims-ground-truth optimizer.

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

**Figure 3.** Scenario generation and evaluation design.  
Caption: Mixed-source scenario construction, held-out-by-scenario splitting, weak-label construction, ablation systems, and primary metrics.

**Figure 4.** Explainability card example.  
Caption: Illustrative output showing annual premium, deductible, annual drug out-of-pocket cost, utilization restrictions, preferred pharmacy access, insulin flags, and key trade-offs.

**Table 1.** Data inputs and provenance.  
**Table 2.** Feature groups used in modeling and ablation.  
**Table 3.** Main held-out-by-scenario ranking results.  
**Table 4.** Ablation results.  
**Table 5.** Tree-reranker performance by scenario bundle.  
**Table 6.** Candidate-set summaries for three prescription samples.  
**Table 7.** Top hybrid recommendation by sample case.

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
