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

**Article type:** Methodology Article

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

The data boundary for this study is organized around one rule: the public artifact uses public quarterly CMS plan-design files as the reproducible foundation, while local enrichments and the PDE-compatible behavioral layer are supporting inputs rather than unrestricted beneficiary claims. The public CMS inputs include plan information, basic formulary records, beneficiary cost rules, insulin beneficiary cost rules, quarterly drug pricing, geography, excluded drugs, indication coverage, and pharmacy network files [18]. These files define plan eligibility, formulary coverage, cost-sharing rules, pricing inputs, and network evidence for the 2025-Q3 full build.

The public inputs are augmented by study-side reference layers used for medication matching, geography, insulin classification, and scenario construction. RXCUI-derived drug-reference tables support preferred names, synonyms, and NDC/RXCUI linkage [34]. ZIP geography derived with `uszipcode` supports density and distance proxies [35]. The insulin reference layer, informed by the CMS CY 2021 Part D Senior Savings Model NDC list, supports insulin-specific classification [36]. The local `pde.csv` / `bronze.pde_sample` layer is used only as a PDE-compatible event-style source for utilization defaults and scenario templates, with field semantics aligned to ResDAC Part D Event documentation [37]. It is not treated as production beneficiary truth, public claims data, or a full claims-ground-truth dependency.

Table A.1 gives the detailed data-input and provenance summary. In the main text, the important methodological point is that the manuscript reports a recommendation system under incomplete observability. Public CMS quarterly files are reproducible and define the plan-design boundary; full CMS claims and Prescription Drug Event data remain restricted and require separate CMS approval [19,20].

## 4. Methods

### 4.1 Overall research flow

CMS-MPD-Recommendation was designed as an end-to-end pipeline rather than as an isolated ranking model. The study begins with quarter-frozen source provenance, moves through deterministic data engineering and beneficiary-level recommendation logic, and only then introduces canonical scenario generation, replay-based weak-label supervision, constrained reranking, and held-out evaluation. This ordering is central to the manuscript because explanation and safety are created during the rules-first stages, not appended after model scoring.

Operationally, the workflow proceeds in seven steps. First, the study fixes the source-provenance boundary around public CMS files, local reference enrichments, and a PDE-compatible local sample. Second, the extraction and medallion pipeline normalizes those inputs through bronze, silver, and gold layers. Third, the runtime engine resolves a beneficiary request, restricts candidate plans by ZIP code, prices fills, and emits explanation groups. Fourth, canonical mixed-source scenarios are generated from ZIP strata, drug pools, and PDE-compatible, benchmark, or stress templates. Fifth, the same recommendation engine replays those scenarios into plan-level feature rows. Sixth, weak labels, heuristic baselines, and linear and tree rerankers are fitted from the replay dataset. Finally, held-out evaluation and prescription-sample retrieval convert the software outputs into reviewer-facing evidence.

This prose flow keeps the main text readable while preserving auditability. The detailed workflow audit table is provided as Table B.1, and Figure 3 remains the recommended visual representation for submission.

### 4.2 Reproducible artifact and data-engineering foundation

The study was run from the local `CMS-MPD-Recommendation` workspace in `sandbox` using a quarter-frozen 2025-Q3 full build. The implementation uses DuckDB, NumPy, pandas, Streamlit, and pytest as pinned runtime dependencies, and the current manuscript, dataset metadata, and code constants are synchronized to `request_features_v4`, `research_v4`, `weak_label_v2`, `scenario_generation_v1`, the `student_safe` teacher-feature policy, and generator seed 42. Table B.2 summarizes the reproducible artifact lock, medallion layers, canonical keys, and principal serving tables.

The medallion architecture is methodologically important because it separates raw-source preservation from business normalization and runtime serving. Bronze tables preserve source lineage; silver tables normalize plans, ZIPs, service-area bridges, drug identities, formulary coverage, pharmacy facts, and cost rules; and gold tables materialize the ZIP, plan, drug, network, and recommendation-feature objects used by both the runtime engine and the research workflow. The canonical keys include `plan_key`, `contract_plan_key`, `formulary_id`, `zip_code`, `county_code`, `ndc`, `rxcui`, normalized `days_supply`, `coverage_level`, and `tier_level_value`. These keys are not implementation trivia: they determine whether formularies, geographies, drug costs, and beneficiary cost rules are joined to the correct plan and request.

For internal manuscript preparation, the locked software state is the local workspace snapshot associated with this reviewer revision. Before external submission, this exact state should be archived under a release tag and DOI and cited as the formal software release. Table B.2 and Appendix B.1 retain the detailed artifact and transformation summaries. The main methodological point is that recommendation-time evidence is produced by key-preserving relational transformations from public plan-design data into executable plan, geography, network, and cost objects rather than by opaque feature synthesis alone.

### 4.3 Runtime recommendation workflow

The runtime path follows the same order shown in the overall research flow: beneficiary input, medication resolution, ZIP-eligible candidate plans, fill-level cost simulation, and explanation generation. Because this sequence is deterministic and auditable, the recommendation layer is both a decision-support system and the upstream evidence generator for the later research pipeline.

#### Beneficiary request schema and medication resolution

The runtime request schema includes beneficiary ZIP code, age band, low-income subsidy status, chronic-condition flags, pharmacy preference, user role, decision focus, and a medication list. Each medication can be provided by drug name, RXCUI, or NDC, with optional quantity and annual-fill overrides.

Medication resolution follows a strict order:

1. exact NDC;
2. exact RXCUI;
3. exact preferred name;
4. exact synonym;
5. prefix match on preferred name or synonym.

Approximate matches are retained as explicit evidence gaps rather than silently treated as exact matches. This design follows the logic of medication-terminology infrastructure: RxNorm provides normalized clinical-drug concepts and normalized NDC-to-RXCUI associations where supported, while the FDA NDC Directory identifies listed drug packages but does not itself establish coverage or reimbursement [27,28]. The recommender therefore treats drug identity and plan coverage as two separate checks.

#### Public CMS ingestion and normalization into serving facts

The extraction and build workflow is:

1. locate quarter-frozen CMS source files and local references;
2. extract archive members into `data/staging/<snapshot>/raw`;
3. load bronze tables with lineage columns;
4. normalize plan, geography, drug, pharmacy, and cost-rule entities into silver tables;
5. materialize gold serving tables for runtime recommendation and model dataset generation.

The gold serving layer is the operational contract of the software. In particular, `gold.plan_drug_cost_basis` joins plan-drug coverage, tier, UM flags, exclusions, indication limits, pricing basis, deductible applicability, standard beneficiary-cost rules, and insulin overrides into a runtime-ready plan-drug-day-supply table.

#### Recommendation and cost-simulation method

For a request scenario `s`, the engine first limits candidate plans to plans serving the beneficiary ZIP code. It then resolves medication defaults and, for each candidate plan and medication, retrieves plan-drug cost basis, coverage status, restriction flags, pricing inputs, and channel availability.

Annual beneficiary out-of-pocket cost is simulated at fill level. The engine:

- normalizes day supply to 30, 60, or 90 days;
- applies contract-year-aware benefit design selection;
- supports automatic use of `2025_redesign` for current data and explicit `2024_standard` historical modeling when needed;
- applies insulin-specific overrides where present;
- applies low-income subsidy adjustments after base liability is computed;
- aggregates fill-level results into annual premium, annual drug out-of-pocket cost, and annual total cost.

The runtime engine therefore produces beneficiary-facing economic outputs rather than only relative model scores.

For a concrete trace, consider a one-drug request for lisinopril 40 mg using exact NDC `43547035611`, 30-day supply, and quantity 30 in ZIP `90001`. The resolver maps the NDC to the local drug-reference record and then restricts plans to the ZIP-specific service area. For the top hybrid plan in the current artifact, the engine retrieves the plan-drug-day-supply row from `gold.plan_drug_cost_basis`, selects the feasible preferred-mail channel, schedules 13 fills across the benefit year, and simulates each fill under the `2025_redesign` branch. In the retrieved trace, the annual negotiated-price proxy across the scheduled fills was 6.63, deductible applied was 0.00, LIS-adjusted beneficiary liability was 0.00, final beneficiary drug OOP was 0.00, and no OOP cap was triggered. The reported annual total cost was therefore annual premium plus final simulated beneficiary drug OOP, or 0.00 in that top-plan trace. This example illustrates the interpretation of the sample results: negotiated-price evidence and beneficiary liability are stored separately, and the displayed beneficiary cost is a simulated public-file estimate rather than a guaranteed pharmacy transaction price.

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

#### Explainability outputs

Each recommendation includes structured explanation groups for:

- coverage fit and uncovered drugs;
- utilization management, including prior authorization, step therapy, and quantity limits;
- insulin-specific affordability risks;
- deductible exposure;
- preferred retail, nonpreferred retail, and mail-order access;
- estimated annual out-of-pocket cost;
- medication-match confidence and other data-quality gaps.

Operationally, each explanation group is derived from the same evidence fields used for ranking rather than from a separate narrative model.

| Explanation group | Source evidence | Output interpretation |
|---|---|---|
| Coverage fit | Covered, uncovered, excluded, and missing-price drug counts | Whether the plan can support the requested regimen |
| Utilization management | Prior authorization, step therapy, quantity limit, and restriction counts | Friction that may delay or block access even when covered |
| Insulin handling | Insulin flag, insulin cost-rule rows, and nonpreferred-channel dependence | Whether insulin-specific affordability logic or channel risk applies |
| Deductible and benefit phase | Deductible applicability, fill trace phase, deductible before/after | How the fill path moves through the benefit design |
| Pharmacy access | Preferred retail count, mail availability, network flag, nearest preferred distance | Whether the plan is practical for the beneficiary's channel preference |
| Cost estimate | Annual premium, drug OOP, total cost, negotiated-price proxy, OOP cap flag | How the displayed annual estimate was assembled |
| Medication identity | Match source, confidence, exact/approximate flags, review-required flag | Whether ranking is safe to proceed without manual drug review |
| Missing-data signals | Unknown network flag, channel unavailable, missing price, unsafe reasons | Evidence gaps that should temper confidence in the output |

The explanation layer is generated alongside the recommendation rather than appended later. This enables reviewer inspection of why a plan ranked highly and whether that ranking is safe to trust. The runtime workflow therefore does two jobs at once: it generates beneficiary-facing recommendation outputs and produces the plan-level evidence rows that are later replayed for weak-label supervision and constrained reranking research.

### 4.4 Scoring, feature design, and constrained reranking

Once runtime recommendation rows exist, the study adds a second methodological layer: explicit scoring for research supervision, replay-dataset feature construction, and constrained reranking at inference. The key design choice is that machine learning is permitted to reorder already simulated plans, but not to replace the deterministic evidence model.

#### Scoring, constraints, and reranking

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

#### Feature schema and model feature groups

The reranking dataset combines both human-interpretable scoring signals and richer plan-scenario descriptors. Numeric features include current rules rank and score, fit sub-scores, annual premium, annual drug out-of-pocket cost, annual total cost, covered and uncovered drug counts and shares, restriction counts, deductible and initial-coverage exposure, negotiated-price totals, insulin flags, medication-match counts, network counts, formulary rates, geography proxies, and missing-data indicators. Categorical features include coverage status, network flag, LIS status, age band, pharmacy preference, ZIP density category, scenario bundle, scenario profile, and fallback group.

For reviewer readability, these can be grouped as follows.

**Table 1. Feature groups used in modeling and ablation.**

| Feature group | Example variables | Why included |
|---|---|---|
| Rules-engine summary | `current_rules_rank`, `current_rules_score`, `fit_score`, `coverage_score`, `access_score` | Preserve deterministic ranking context for dataset analysis and teacher-feature ablations |
| Cost and liability | `annual_premium`, `annual_drug_oop`, `annual_total_cost`, `deductible_exposure_total`, `lis_adjusted_oop_total`, `negotiated_price_total` | Reflect beneficiary-facing economic burden |
| Coverage and exclusions | `coverage_status`, `covered_drug_share`, `uncovered_drug_count`, `excluded_drug_count`, `missing_price_drug_count` | Preserve medication-safety and coverage completeness |
| Restriction burden | `restriction_count`, `pa_rate`, `st_rate`, `ql_rate`, `channel_unavailable_count` | Capture clinically and operationally relevant friction |
| Network and access | `network_flag`, `network_risk_score`, `preferred_retail_count`, `preferred_mail_count`, `nearest_preferred_distance_bucket` | Represent pharmacy usability and access risk |
| Medication identity and evidence quality | `approximate_match_count`, `exact_match_count`, `match_review_required_flag`, `unknown_network_data_flag`, `unsafe_reason_count` | Prevent false confidence when evidence is weak |
| Beneficiary and scenario context | `lis_status`, `age_band`, `pharmacy_preference`, `scenario_bundle`, `scenario_profile`, `beneficiary_chronic_condition_count` | Preserve context and subgroup sensitivity |

The current study trains two reranker families on this feature frame. Both are deliberately modest tabular models because the research question is not whether a high-capacity model can infer beneficiary utility from hidden behavior. The question is whether an auditable model can improve the ordering of already simulated plan rows while preserving coverage and priceability constraints. This makes linear ridge regression and a shallow residual tree ensemble appropriate: the former gives a stable additive baseline, and the latter captures low-order interactions among coverage, cost, restrictions, LIS status, network risk, and scenario type without creating an opaque recommender [38-40].

Let $\phi(x_{s,p})$ denote the encoded feature vector for scenario $s$ and plan $p$. Numeric variables are zero-filled when absent and standardized for the linear model; categorical variables are one-hot encoded. The linear reranker estimates:

$$
\hat{W}_{s,p}^{linear}
=
\beta_0+\phi(x_{s,p})^\top\beta,
$$

with ridge objective:

$$
\min_{\beta_0,\beta}
\sum_{(s,p)}
\left(
W_{s,p}-\beta_0-\phi(x_{s,p})^\top\beta
\right)^2
+
\alpha\lVert\beta\rVert_2^2,
\qquad
\alpha=5.0.
$$

The intercept is not penalized. This model is used as a transparent baseline because ridge coefficient shrinkage is well suited to sparse one-hot variables and correlated cost features [38].

The tree reranker is implemented as a small additive residual ensemble, following the same broad stagewise residual-fitting logic used by gradient boosting methods [39]. Starting from the mean weak-label target, each shallow tree is fit to the current residual:

$$
F_0(x)=\bar{W},
\qquad
r_i^{(m)}=W_i-F_{m-1}(x_i),
\qquad
F_m(x)=F_{m-1}(x)+\eta h_m(x).
$$

The deployed tree score is $\hat{W}_{s,p}^{tree}=F_M(x_{s,p})$. The default settings are `learning_rate = 0.12`, `n_estimators = 40`, `max_depth = 3`, and `min_samples_leaf = 5`. These values intentionally restrict model capacity: depth 3 permits interactions such as coverage-by-cost or restriction-by-network, while the minimum leaf size prevents isolated plan-scenario fragments from dominating a split.

The default trained artifact uses the `student_safe` policy. Under that policy, the dataset still records teacher-style rules summary fields such as `current_rules_rank`, `current_rules_score`, `fit_score`, `cost_score`, `premium_score`, `coverage_score`, `access_score`, and `stability_score` for audit and ablation analysis, but those numeric teacher features are excluded from the default student feature matrix used in training. Reviewers should therefore distinguish between columns present in the replay dataset and the smaller default feature subset actually exposed to the trained student artifact.

Formally, if $T$ is the set of teacher-style columns, the default student matrix is:

$$
X_{student}=X_{full}\setminus T.
$$

The alternative `teacher_features` policy keeps $X_{full}$ and is useful for diagnostic or upper-bound ablations, but it is not the default reviewer-facing policy because it allows the model to learn directly from the deterministic teacher's rank and score outputs. Missingness is not hidden in either policy: variables such as missing price, unknown network data, channel unavailability, and match-review flags are retained as explicit features because incomplete observability is part of the decision-support problem.

#### Dataset generation and weak-label construction

The training dataset is generated by replaying canonical scenarios through the same recommendation engine used at runtime. Each row is a plan under a specific scenario. In this flow, weak labels are the bridge between deterministic recommendation replay and supervised reranker training. They are not treated as a clinical gold standard. Instead, they encode the study's recommendation preference structure by rewarding safer and more useful plan rows according to coverage, cost, restrictions, network risk, and evidence quality. This use of explicit programmatic supervision follows the broader weak-supervision motivation of creating auditable training labels when hand-curated or outcome-ground-truth labels are unavailable [42].

Weak labels serve three roles in the pipeline. First, they convert plan-scenario replay rows into an ordered supervision target. Second, they make the study's preference structure explicit and auditable because every reward and penalty term is visible. Third, they enable held-out-by-scenario evaluation when real enrollment, switching, or outcome labels are unavailable.

This design makes the evaluation honest about what it measures. Agreement with the weak label indicates alignment with the study's stated decision logic, not proof of downstream beneficiary outcomes.

The weak-label construction is deliberately conservative. Coverage and priceability terms dominate because a lower-cost plan is not useful if a requested drug is uncovered, excluded, unpriceable, or available only through an unusable channel. Restriction, network, insulin, mail-order, and approximate-match penalties then refine the ordering among otherwise plausible plans. This makes the label useful for internal ranking research while preserving a clear boundary: it evaluates whether the model follows the study's encoded decision logic, not whether beneficiaries would actually enroll, adhere, save money, or report higher satisfaction after using the tool.

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

with no cross-bucket promotion. In practical terms, a weak-coverage or unpriceable plan cannot leap ahead of a fully covered and fully priceable plan solely because of model score. This is the central mathematical expression of the system's safety constraint and the main reason weak-label alignment should be interpreted as internal ranking validity rather than external clinical validity. This reranking layer depends on canonical scenario replay and weak-label supervision, which is why the next subsection focuses on scenario generation and evaluation design rather than on model fitting alone.

### 4.5 Scenario generation and evaluation design

The research workflow no longer depends on ad hoc synthetic cases. Instead, it materializes canonical mixed-source scenarios first, then replays them through the same rules-first recommendation path used at runtime. This design keeps the modeling task tied to realistic beneficiary-like inputs and makes held-out evaluation more defensible. The approach is consistent with synthetic patient-data evaluation work that treats generated cases as useful for software testing, model development, and method evaluation when real patient-level data are limited or restricted [43].

#### Scenario generation

The current full artifact uses mixed-source canonical scenarios. The generation flow is intentionally structured so that model training begins from beneficiary-like requests rather than from disconnected plan rows. The pipeline:

1. draws a stratified sample of service-area ZIP codes so the scenario set spans the geographic density mix present in `gold.plan_service_area`;
2. builds drug pools from the gold catalog, including generic, brand, insulin, specialty, restricted, and lower-cost pools;
3. assembles local PDE-compatible regimen pools when event-style templates are available;
4. generates benchmark and stress regimens from the catalog pools when a local PDE-compatible template is unavailable or when harder edge cases are needed;
5. assigns mixed-source scenarios across the canonical bundles and source kinds (`pde`, `benchmark`, `stress`);
6. validates each generated scenario against its intended bundle/profile before accepting it into the canonical set;
7. materializes a scenario manifest that records bundle counts, source mix, regimen-signature counts, unique NDC and RXCUI counts, and validation rates.

In implementation terms, each evaluation scenario is a tuple:

$$
s_i=
(z_i,\;b_i,\;M_i,\;q_i,\;\ell_i,\;g_i,\;u_i),
$$

where $z_i$ is ZIP code, $b_i$ is the intended scenario bundle, $M_i$ is the medication set, $q_i$ is pharmacy preference, $\ell_i$ is LIS status, $g_i$ is the regimen signature, and $u_i$ is the source kind (`pde`, `benchmark`, or `stress`). ZIPs are sampled from service-area ZIPs using density-stratified sampling from `gold.plan_service_area` joined to `silver.dim_zipcode`; the full profile targets 100 ZIPs. This stratification is used to preserve geographic-density representation rather than drawing only from the most frequent ZIP contexts [44]. Drug pools are built from `gold.plan_drug_cost_basis` grouped by NDC with RXCUI, drug name, tier family, day supply, insulin and utilization-management flags, coverable-plan count, and median unit cost. When local PDE-compatible regimen templates are available, they are grouped into event-style medication bundles; otherwise the generator falls back to benchmark catalog pools. Stress scenarios deliberately include harder patterns such as low coverability, ambiguous names, access sensitivity, restriction burden, and high-cost therapy. The manifest therefore makes scenario generation inspectable rather than a hidden data augmentation step.

Six scenario bundles are represented:

- access-sensitive
- insulin-chronic
- low-utilizer
- maintenance-generic
- mixed-restriction
- specialty-high-cost

The bundles were chosen to make clinically and operationally different recommendation stresses visible.

| Scenario bundle | Real-world stress represented | Typical medication pattern | Main risk exposed | Why included |
|---|---|---|---|---|
| Access-sensitive | Pharmacy usability and channel fit | Brand or generic drugs where retail/mail access matters | Preferred retail gaps or mail dependence | Tests whether ranking preserves access explanations |
| Insulin-chronic | Diabetes and insulin affordability | Insulin plus chronic companion drugs | Insulin rules, channel dependence, UM flags | Tests policy-sensitive affordability handling |
| Low-utilizer | Simple one-drug or low-drug use | One low-cost generic or sparse regimen | Overfitting to complex regimens | Confirms the model handles low-friction cases cleanly |
| Maintenance-generic | Common chronic generic management | Multiple 90-day generic fills | Premium versus low drug OOP trade-offs | Represents frequent counseling cases |
| Mixed-restriction | Multi-drug chronic regimen with restrictions | Brands, generics, PA/ST/QL drugs | Friction hidden behind coverage status | Tests restriction-aware ranking |
| Specialty-high-cost | Biologics, anticoagulants, and rare high-cost therapies | Specialty or high negotiated-price drugs | Sparse coverage, restrictions, OOP-cap exposure | Tests edge cases where explanations are essential |

Each bundle contains 100 scenarios. The overall source mix is 180 benchmark scenarios, 300 local PDE-compatible scenarios, and 120 stress scenarios. The canonical generator version is `scenario_generation_v1`. For evaluation, the scenario is the unit of splitting because replaying one scenario creates many plan rows that share the same beneficiary ZIP, regimen, LIS status, and pharmacy preference. A row-random split would therefore leak scenario context from training into testing. The held-out-by-scenario split instead asks whether the learned reranker generalizes to new beneficiary-like requests.

This design benefits the reranker in several ways. It broadens training coverage beyond only common medication combinations, preserves representation across clinically and operationally important bundles, adds harder stress cases so the reranker sees edge conditions, and keeps the training data close to runtime behavior because the same recommendation engine is replayed to build feature rows. In effect, scenario generation produces beneficiary-like inputs, and replay through the rules engine turns those inputs into the same evidence rows used at recommendation time. The learned model is therefore a reranker over realistic simulated plan comparisons rather than over disconnected synthetic labels.

#### Experimental design and comparators

Evaluation is performed with a held-out-by-scenario split rather than row-random splitting. The training set contains 420 scenarios and 23,384 plan-scenario rows. The test set contains 180 scenarios and 10,577 rows. This design reduces leakage from repeated plan rows associated with the same beneficiary request. The implementation also produces held-out-by-ZIP and held-out-by-regimen-signature reports to probe geographic and medication-regimen novelty, but the primary manuscript results use held-out-by-scenario evaluation because it is the closest analogue to future unseen counseling cases.

The evaluated systems are:

- rules-only ranking;
- heuristic baseline;
- linear reranker;
- tree reranker;
- ablation systems using cost-only, cost-plus-restrictions, cost-plus-restrictions-plus-network, and full feature sets.

The heuristic baseline is reported explicitly as an operational comparator. A fully frozen external Medicare Plan Finder comparator for the exact same quarter and medication cases was not yet packaged into this public artifact. Rather than imply comparability that does not yet exist, the manuscript reports transparent internal comparators that can be reproduced from the same frozen quarter and code state.

#### Primary metrics and guardrails

Primary metrics were chosen to separate ranking agreement from operational safety and follow standard learning-to-rank evaluation practice [40,41]. Let $\mathcal{S}_{test}$ be the held-out scenario set, $\mathcal{P}_s$ the candidate plans for scenario $s$, $\pi_s^m$ the ordering produced by method $m$, and $\pi_s^\star$ the weak-label reference ordering:

$$
\pi_s^\star
=
\operatorname{sort}_{p\in\mathcal{P}_s}
(-W_{s,p},T_{s,p}),
$$

where $W_{s,p}$ is the weak-label score and $T_{s,p}$ is annual total cost. Top-1 agreement is:

$$
\operatorname{Top1}(m)
=
\frac{1}{|\mathcal{S}_{test}|}
\sum_{s\in\mathcal{S}_{test}}
\mathbf{1}\{\pi_s^m(1)=\pi_s^\star(1)\}.
$$

Top-$k$ overlap measures shortlist agreement:

$$
\operatorname{Overlap}_k(m)
=
\frac{1}{|\mathcal{S}_{test}|}
\sum_{s\in\mathcal{S}_{test}}
\frac{
|\operatorname{Top}_k(\pi_s^m)\cap\operatorname{Top}_k(\pi_s^\star)|
}{
\min(k,|\mathcal{P}_s|)
}.
$$

For graded ranking quality, the weak-label rank is converted to relevance:

$$
rel_{s,p}
=
\max(0,\;6-\operatorname{rank}_s^\star(p)).
$$

Thus the reference top five plans receive relevance values 5 through 1. Discounted cumulative gain is:

$$
\operatorname{DCG}@k(s,m)
=
\sum_{i=1}^k
\frac{2^{rel_{s,\pi_s^m(i)}}-1}{\log_2(i+1)},
\qquad
\operatorname{NDCG}@k(s,m)
=
\frac{\operatorname{DCG}@k(s,m)}{\operatorname{IDCG}@k(s)}.
$$

Safety and usability metrics are computed on the same top-$k$ lists. The top-$k$ full-coverage rate is:

$$
\operatorname{FullCoverageRate}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
\mathbf{1}\{\operatorname{coverage}_{s,\pi_s^m(i)}=\mathrm{full}\},
\qquad
k_s=\min(k,|\mathcal{P}_s|).
$$

Average top-$k$ total cost and uncovered-drug burden are:

$$
\operatorname{AvgCost}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
T_{s,\pi_s^m(i)},
\qquad
\operatorname{AvgUncovered}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
U_{s,\pi_s^m(i)}.
$$

When no full-coverage plan exists in the reference set, blocker-classification precision checks whether the method's top plan belongs to the same fallback group as the reference top plan:

$$
\operatorname{BlockerPrecision}(s,m)
=
\mathbf{1}\{
fallback_{s,\pi_s^m(1)}
=
fallback_{s,\pi_s^\star(1)}
\}.
$$

The review-trigger rate summarizes manual-review or uncertain-match signals in the top five, and missing-data behavior records plans dropped because of incomplete evidence and scenarios containing unknown network data. These metrics are reported alongside ranking agreement because, in this domain, a better NDCG score is not sufficient if the top list increases uncovered-medication burden or hides evidence gaps.

Guardrails were defined prospectively:

- top-5 ranking should improve;
- top-10 ranking should improve;
- uncovered-medication burden should not worsen.

The last guardrail is especially important because improved ranking agreement is not clinically or operationally meaningful if it increases exposure to uncovered drugs. These aggregate evaluation procedures are complemented by concrete prescription-case retrieval, which makes the phase-by-phase flow visible to reviewers in terms of actual recommendation outputs rather than only summary metrics.

### 4.6 Multi-case retrieval protocol

To make the overall research flow concrete for readers, we ran eight prescription samples through the current local recommendation engine. These cases were designed as functional probes of the pipeline shown in Section 4.1 rather than as clinical recommendations. They vary scenario profile, drug count, ZIP, pharmacy preference, LIS status, drug cost intensity, restriction burden, and network sensitivity. All cases used age band `65-74`, user role `counselor`, automatic 2025 benefit-design selection, and both rules-only and hybrid ranking.

The cases were selected to stress different parts of the workflow:

| Case | Intended workflow stress test | Request context | Medication inputs |
|---|---|---|---|
| Case 1: maintenance generics | Low-cost chronic generics and 90-day fills | ZIP `90001`, LIS `none`, pharmacy `auto` | atorvastatin NDC `60505257908`; amlodipine NDC `82009002710`; tamsulosin NDC `68382013201` |
| Case 2: insulin plus GLP-1 | Exact NDC resolution, insulin handling, high-cost brand therapy, UM flags | ZIP `90001`, LIS `none`, pharmacy `auto` | Toujeo NDC `00024586903`; Ozempic NDC `00169418113` |
| Case 3: specialty plus anticoagulant | Specialty drug handling, high-cost biologic, brand anticoagulant, network trade-offs | ZIP `90001`, LIS `none`, pharmacy `auto` | Humira NDC `00074012402`; Eliquis NDC `00003089421` |
| Case 4: low-utilizer generic | Single-drug low-utilizer behavior | ZIP `90001`, LIS `none`, pharmacy `auto` | lisinopril NDC `43547035611` |
| Case 5: access-sensitive respiratory/retail | Retail preference and respiratory-medication access | ZIP `93543`, LIS `none`, pharmacy `retail` | albuterol NDC `76204020025`; omeprazole NDC `55111015810` |
| Case 6: mixed-restriction cardiometabolic | Brand/generic cardiometabolic regimen with restrictions | ZIP `90001`, LIS `none`, pharmacy `auto` | Jardiance NDC `00597015230`; Entresto NDC `00078077720`; gabapentin NDC `45963055650` |
| Case 7: LIS sensitivity cardiometabolic | Same regimen as Case 6 with full LIS | ZIP `90001`, LIS `full`, pharmacy `auto` | Jardiance NDC `00597015230`; Entresto NDC `00078077720`; gabapentin NDC `45963055650` |
| Case 8: high-cost specialty stress | Sparse coverage and very high negotiated-price specialty therapy | ZIP `90001`, LIS `none`, pharmacy `auto` | Rivfloza/nedosiran NDC `00169530610` |

For each case, the workflow was:

1. resolve all medications using exact NDC;
2. construct the ZIP-specific candidate plan set from `gold.plan_service_area`;
3. compute rules-first recommendations and hybrid recommendations;
4. record candidate counts, full-coverage counts, partial-coverage counts, unknown-network counts, top-ranked plan, annual premium, annual drug OOP, annual total cost, coverage status, network flag, restriction count, uncovered-drug count, priced-drug count, model score, and model confidence;
5. extract fill-trace fields for the top hybrid plan, including selected channel, negotiated-price proxy, deductible applied, LIS-adjusted OOP, final OOP, OOP-cap flag, and benefit-design branch.

The higher-risk cases used NDCs intentionally. During pilot execution, text-only high-impact drug inputs could trigger the system's manual-review guardrail because typed drug strings may have multiple possible matches and uneven local coverage. That behavior is part of the intended safety design: ambiguous high-impact drug matching should stop ranking until an exact drug identity is supplied.

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

**Table 2. Main held-out-by-scenario ranking results.**

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

**Table 3. Ablation results.**

| Feature subset | Top-1 agreement | Top-5 overlap | Top-10 overlap | NDCG@5 | Top-5 avg total cost | Top-5 avg uncovered |
|---|---:|---:|---:|---:|---:|---:|
| Cost only | 0.806 | 0.882 | 0.935 | 0.926 | 80.75 | 0.469 |
| Cost plus restrictions | 0.833 | 0.903 | 0.954 | 0.937 | 82.57 | 0.460 |
| Cost plus restrictions plus network | 0.872 | 0.950 | 0.973 | 0.960 | 82.99 | 0.459 |
| Full feature set | 0.867 | 0.940 | 0.971 | 0.957 | 82.94 | 0.459 |

The ablation analysis shows that cost, restriction, and network information account for most of the learnable signal. This is a favorable result for reviewer interpretability because it means the model's performance is not dependent on a large opaque feature space. A relatively compact and explainable subset already captures most of the gain.

The fact that the cost-plus-restrictions-plus-network subset slightly outperformed the nominal full feature set on some metrics is also informative. It suggests that model complexity should be justified conservatively in this domain.

### 5.5 Scenario-bundle results

**Table 4. Tree-reranker performance by scenario bundle.**

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

The evaluation artifact indicated that top-5 and top-10 agreement improved, but the uncovered-not-worse guardrail was not fully satisfied. This is a critical reviewer-facing result. The tree reranker improved top-5 overlap from 0.698 to 0.934 and NDCG@5 from 0.830 to 0.953, but average top-5 uncovered-drug burden increased from 0.414 to 0.459. The magnitude is small in aggregate, but it matters because an uncovered medication is not a cosmetic error in this domain. It can change whether the recommendation is usable.

The bundle results show where this risk concentrates. Specialty-high-cost scenarios had the highest top-5 uncovered burden under the tree reranker (0.900), followed by mixed-restriction scenarios (0.775). These are also the bundles where coverage is sparse, utilization management is common, and apparently favorable cost estimates can coexist with access barriers. By contrast, insulin-chronic scenarios had lower top-5 uncovered burden (0.091), suggesting that the current feature and weak-label design is more stable when insulin identity and cost-rule signals are explicit.

This pattern explains why the manuscript treats ranking agreement and guardrails as separate endpoints. Agreement with the weak-label ranking shows that the model learned the study's internal decision logic. The uncovered-medication guardrail shows whether that ordering remains acceptable for decision support. The system should therefore be interpreted as a decision-support tool with visible guardrails, not as an autonomous optimization engine.

Additional operational signals strengthen this interpretation:

- blocker-classification precision remained high;
- unknown-network conditions can still occur in practice;
- match-review-required flags remain important when medication identity is approximate.

These outputs are not peripheral. They are part of the system's safety posture.

### 5.7 Prescription-sample retrieval and ranking-trace results

Eight prescription samples were replayed against the current 2025-Q3 local database to probe behaviors that aggregate metrics can hide. The cases cover low-friction maintenance use, a low-utilizer generic, an access-sensitive retail request, insulin/GLP-1 therapy, specialty/anticoagulant therapy, cardiometabolic regimens with and without full LIS, and a sparse-coverage high-cost specialty stress case. All cases used exact NDC inputs, so the manual-review drug-matching gate did not block the retrieval pass. Detailed candidate counts, top hybrid rows, and fill-level trace summaries are provided in Tables C.1-C.3.

The sample results support three concise findings. First, candidate availability was governed by geography and medication coverage separately: the California examples all began from 126 service-area candidates, but full-coverage counts ranged from 110 in broad-choice cases to only 6 in the high-cost specialty stress case. Second, zero simulated beneficiary OOP did not imply an uncomplicated recommendation. Several top hybrid rows retained mail-order dependence, utilization-management restrictions, no preferred-retail network status, or large negotiated-price exposure. Third, constrained reranking changed ordering primarily where multiple plans occupied the same full-coverage and fully priceable safety bucket. In Cases 2, 3, 6, and 7, the hybrid winner came from lower rules ranks while preserving coverage and explanation fields; in low-friction cases and the sparse-coverage stress case, the rules and hybrid winners were stable.

These retrieval probes therefore function as a compact audit of the research flow rather than as clinical recommendations. They show that coverage, priceability, channel selection, restrictions, network status, cost traces, and model rank remain visible together. They also expose deployment boundaries: some top plans were MA-PD or HMO/HMO-POS products, including SNP-like names, so production use would require explicit beneficiary eligibility filters before outputs could be treated as enrollment advice.

## 6. Discussion

This manuscript's main claim is that Medicare Part D recommendation can be implemented as a transparent software pipeline rather than as a black-box ranking problem. The software-method contribution is the explicit ordering of responsibilities: the public CMS quarter defines the plan-design snapshot; the medallion pipeline turns that snapshot into auditable serving tables; the rules engine simulates beneficiary-facing cost, coverage, and access evidence; scenario replay converts those same outputs into a modeling dataset; and the reranker changes ordering only after deterministic plan facts exist. This sequence preserves an explanation trail from source data to final recommendation.

The policy-aware contribution is that benefit-year rules, formulary coverage, utilization management, insulin handling, LIS status, pharmacy networks, and incomplete observability are treated as first-order modeling objects. The sample retrieval probes show why this matters. A selected plan can have zero simulated beneficiary OOP while retaining mail-order dependence, restrictions, no preferred-retail access, or very large negotiated-price exposure. Those are not incidental edge cases in Part D; they are often the practical substance of plan comparison.

The results support a restrained view of machine learning in this setting. The tree reranker improved internal ranking agreement and NDCG over rules-only ranking, and the strongest ablation signal came from interpretable cost, restriction, and network features. At the same time, the uncovered-not-worse guardrail was not satisfied. This mixed finding is central to the paper. It suggests that constrained reranking can improve alignment with the study's weak-label preference structure, but ranking metrics must be reported alongside coverage burden, restriction burden, network status, missing-data indicators, and sample-level traces.

The provenance boundary is also part of the contribution. Public CMS quarterly plan files and restricted PDE data are not interchangeable [18-20]. The current artifact demonstrates a plan-design and decision-support pipeline under incomplete observability; it does not claim to be a full claims-based simulator of beneficiary behavior. Because Part D benefit design changed materially in 2025 and plan behavior continues to evolve [6-9], the software should be interpreted as a quarter-frozen research artifact rather than a permanent enrollment advisor.

Deployment readiness remains a separate question. The current artifact is strong enough to support software-method evaluation, scenario-held-out reranking analysis, and reviewer-facing retrieval probes. It is not yet a production enrollment advisor because external Plan Finder benchmarking, MA-PD/SNP eligibility filters, restricted-data validation, runtime benchmarking, uncertainty intervals, and prospective counselor usability testing remain future work.

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

## Suggested figure and table package for submission

**Figure 1.** Medicare Part D data lifecycle and CMS-MPD medallion pipeline.  
Caption: Public CMS quarterly plan-design files are ingested into bronze storage, normalized into silver relational tables, transformed into gold recommendation features, and consumed by transparent scoring and constrained reranking layers. The PDE-compatible layer is a behavioral extension, not a public-data substitute.

**Figure 2.** Beneficiary request to recommendation workflow.  
Caption: Beneficiary inputs, medication normalization, ZIP eligibility, fill-level cost simulation, explanation-card construction, and final top-k ranking.

**Figure 3.** Overall research flow, scenario generation, and evaluation design.  
Caption: Provenance inputs, medallion serving-layer construction, rules-first recommendation and explanation generation, mixed-source canonical scenario generation, replay dataset construction, weak-label supervision, constrained reranking, held-out evaluation, and reviewer-facing retrieval outputs.

**Figure 4.** Explainability card example.  
Caption: Illustrative output showing annual premium, deductible, annual drug out-of-pocket cost, utilization restrictions, preferred pharmacy access, insulin flags, and key trade-offs.

**Table 1.** Feature groups used in modeling and ablation.  
**Table 2.** Main held-out-by-scenario ranking results.  
**Table 3.** Ablation results.  
**Table 4.** Tree-reranker performance by scenario bundle.  
**Table A.1.** Data inputs and provenance.  
**Table B.1.** Overall workflow audit.  
**Table B.2.** Artifact lock, medallion layers, and data contracts.  
**Tables C.1-C.3.** Prescription-sample candidate, recommendation, and trace outputs.

## Appendices

### Appendix A. Data provenance

**Table A.1. Data inputs and provenance.**

| Input family                                                  | Example local table/file                                                                         | Main grain                                | Primary use                                            | Public/restricted status             |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------- | ------------------------------------------------------ | ------------------------------------ |
| CMS plan-design public files                                  | `bronze.plan_information`, `bronze.basic_formulary`, `bronze.pricing`, `bronze.pharmacy_network` | plan, formulary, plan-drug, plan-pharmacy | eligibility, coverage, cost basis, network features    | Public                               |
| CMS cost-rule public files                                    | `bronze.beneficiary_cost`, `bronze.insulin_beneficiary_cost`                                     | plan-tier-channel-day supply              | beneficiary cost simulation                            | Public                               |
| CMS geography public files                                    | `bronze.geographic_locator`                                                                      | ZIP/region/county bridge                  | service-area and geography resolution                  | Public                               |
| CMS exclusions and indication files                           | `bronze.excluded_drugs`, `bronze.indication_coverage`                                            | drug or plan-drug                         | coverage and explanation logic                         | Public                               |
| RXCUI API-derived drug reference enrichment                   | `bronze.rxcui_properties`, `silver.dim_drug_reference`                                           | NDC/RXCUI                                 | drug identity, synonym resolution, and property lookup | Local enrichment                     |
| ZIP geography enrichment (`uszipcode`-derived)                | `bronze.us_zipcode_geo`                                                                          | ZIP code                                  | density and distance proxy                             | Local enrichment                     |
| Insulin reference mapping (CMS Senior Savings Model-informed) | `bronze.insulin_reference`                                                                       | NDC/RXCUI                                 | insulin-specific classification                        | Local enrichment                     |
| PDE-compatible local sample aligned to PDE documentation      | `bronze.pde_sample`, `pde.csv`                                                                   | beneficiary-drug event compatible         | defaults and scenario generation                       | Local sample / restricted-compatible |

### Appendix B. Workflow and artifact audit

**Table B.1. Overall workflow audit.**

| Research-flow phase      | Input                                                      | Output artifact                             | Quality check                                       | Manuscript evidence               |
| ------------------------ | ---------------------------------------------------------- | ------------------------------------------- | --------------------------------------------------- | --------------------------------- |
| Source provenance        | Public CMS files, local enrichments, PDE-compatible sample | Source-family inventory                     | Public versus local boundary stated                 | Section 3 and Table A.1           |
| Medallion transformation | Raw source tables                                          | Bronze, silver, and gold DuckDB tables      | Canonical keys and serving grains preserved         | Section 4.2 and Table B.2         |
| Runtime recommendation   | Beneficiary profile and medications                        | Ranked plan rows with fill traces           | ZIP eligibility, drug resolution, and priced fills  | Section 4.3                       |
| Scenario generation      | Gold drug catalog and ZIP service area                     | Canonical scenario tables and manifest      | Bundle, source mix, ZIP, NDC, and validation counts | Section 4.5                       |
| Scenario replay          | Canonical scenarios                                        | Plan-scenario feature rows                  | Same rules engine replayed for each scenario        | Section 4.4                       |
| Weak-label training      | Feature rows and weak labels                               | Linear and tree reranker artifacts          | `student_safe` feature policy and held-out split    | Sections 4.4 and 5.2              |
| Reviewer-facing outputs  | Evaluation report and sample retrievals                    | Results tables, guardrails, and case traces | Ranking metrics plus concrete recommendation traces | Sections 5.2-5.7                  |

**Table B.2. Reproducible artifact lock, medallion layers, and data contracts.**

| Component | Summary | Reviewer-facing reason |
|---|---|---|
| Runtime workspace | `CMS-MPD-Recommendation` under `sandbox`; 2025-Q3 full build | Ties manuscript claims to a specific local software state |
| Runtime dependencies | DuckDB 1.5.1, NumPy 2.3.4, pandas 2.3.3, Streamlit 1.55.0, pytest 9.0.2 | Supports reproducibility and environment reconstruction |
| Experiment identifiers | `snapshot_quarter=2025-Q3`; `build_profile=full`; `dataset_schema_version=request_features_v4`; `feature_version=research_v4`; `weak_label_version=weak_label_v2`; `generation_version=scenario_generation_v1`; `teacher_feature_policy=student_safe`; `generator_seed=42` | Keeps manuscript, metadata, and code constants synchronized |
| Bronze layer | Preserves raw source inputs with `source_file`, `snapshot_quarter`, and `load_ts`; permissive loading handles source variation | Maintains source lineage and reduces brittle ingestion failure |
| Silver layer | Normalizes plans, ZIPs, service areas, drug reference, utilization defaults, plan-drug coverage, pharmacy facts, beneficiary cost rules, and insulin cost rules | Creates business entities and canonical join keys |
| Gold layer | Materializes service area, channel summaries, preferred pharmacy locations, formulary summaries, network summaries, plan-drug cost basis, plan summary, drug defaults, and recommendation features | Provides runtime serving facts for recommendations and modeling |
| Canonical keys | `plan_key`, `contract_plan_key`, `formulary_id`, `zip_code`, `county_code`, `ndc`, `rxcui`, `days_supply`, `coverage_level`, `tier_level_value` | Prevents plan, geography, drug, and benefit-rule joins from drifting |

#### Appendix B.1. Transformation equations

Let the raw input family be:

$$
\mathcal{R} = \{R_1, R_2, \dots, R_n\}, \tag{B.1}
$$

where each $R_i$ is a public CMS or local reference source table. The medallion pipeline can be written as a composition of deterministic transformation operators:

$$
\mathcal{R}
\xrightarrow{\mathcal{B}}
\mathcal{B}(\mathcal{R})
\xrightarrow{\mathcal{S}}
\mathcal{S}(\mathcal{B}(\mathcal{R}))
\xrightarrow{\mathcal{G}}
\mathcal{G}(\mathcal{S}(\mathcal{B}(\mathcal{R}))). \tag{B.2}
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
\Big), \tag{B.3}
$$

where $s$ denotes normalized day supply and $\gamma$ denotes projection and aggregation to the plan x drug x day-supply grain. The runtime cost basis is then:

$$
\text{GoldCostBasis}
=
\text{SilverCoverage}
\overset{\text{left}}{\bowtie}
\text{BenefitRules}
\overset{\text{left}}{\bowtie}
\text{InsulinRules}. \tag{B.4}
$$

Service-area eligibility is represented as a deterministic relation. Let $A(z,p)=1$ when ZIP code $z$ is served by plan $p$. Then:

$$
A(z,p)=1
\iff
\exists c \; : \; (z,c)\in \text{ZipCountyBridge}
\wedge
(p,c)\in \text{PlanCountyBridge}. \tag{B.5}
$$

### Appendix C. Prescription-sample retrieval details

**Table C.1. Candidate-set summaries for eight prescription samples.**

| Case | Scenario profile | ZIP | LIS | Pharmacy | Requested drugs | Service-area candidates | Ranked candidates | Full coverage | Partial coverage | Unknown-network plans | Rules top plan | Hybrid top plan |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| Case 1: maintenance generics | maintenance_generic | 90001 | none | auto | 3 | 126 | 126 | 110 | 16 | 16 | Blue Shield 65 Plus (HMO) | Blue Shield 65 Plus (HMO) |
| Case 2: insulin plus GLP-1 | insulin_chronic | 90001 | none | auto | 2 | 126 | 126 | 101 | 25 | 16 | Anthem I Carelon Chronic Care (HMO-POS C-SNP) | Aetna Medicare Preferred Plus (HMO-POS) |
| Case 3: specialty plus anticoagulant | specialty_high_cost | 90001 | none | auto | 2 | 126 | 126 | 99 | 27 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) |
| Case 4: low-utilizer generic | low_utilizer | 90001 | none | auto | 1 | 126 | 126 | 110 | 16 | 16 | Aetna Medicare Core (PPO) | Aetna Medicare Core (PPO) |
| Case 5: access-sensitive respiratory/retail | access_sensitive | 93543 | none | retail | 2 | 126 | 126 | 110 | 16 | 16 | Blue Shield 65 Plus (HMO) | Blue Shield 65 Plus (HMO) |
| Case 6: mixed-restriction cardiometabolic | mixed_restriction | 90001 | none | auto | 3 | 126 | 126 | 110 | 16 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) |
| Case 7: LIS sensitivity cardiometabolic | mixed_restriction_lis | 90001 | full | auto | 3 | 126 | 126 | 110 | 16 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Aetna Medicare Preferred Plus (HMO-POS) |
| Case 8: high-cost specialty stress | specialty_high_cost_stress | 90001 | none | auto | 1 | 126 | 126 | 6 | 120 | 16 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) |

**Table C.2. Top hybrid recommendation by sample case.**

| Case   | Top hybrid plan                                         | Premium | Drug OOP | Total cost | Coverage | Network             | Restrictions | Uncovered | Main watchout                                         |
| ------ | ------------------------------------------------------- | ------: | -------: | ---------: | -------- | ------------------- | -----------: | --------: | ----------------------------------------------------- |
| Case 1 | Blue Shield 65 Plus (HMO)                               |    0.00 |     0.00 |       0.00 | full     | adequate            |            0 |         0 | No top-plan watchout                                  |
| Case 2 | Aetna Medicare Preferred Plus (HMO-POS)                 |    0.00 |     0.00 |       0.00 | full     | adequate            |            2 |         0 | Mail-order dependence and 2 UM restrictions           |
| Case 3 | Aetna Medicare Preferred Plus (HMO-POS)                 |    0.00 |     0.00 |       0.00 | full     | adequate            |            2 |         0 | Mail-order dependence and 2 UM restrictions           |
| Case 4 | Aetna Medicare Core (PPO)                               |    0.00 |     0.00 |       0.00 | full     | adequate            |            0 |         0 | Mail-order dependence                                 |
| Case 5 | Blue Shield 65 Plus (HMO)                               |    0.00 |     0.00 |       0.00 | full     | adequate            |            1 |         0 | 1 UM restriction                                      |
| Case 6 | Aetna Medicare Preferred Plus (HMO-POS)                 |    0.00 |     0.00 |       0.00 | full     | adequate            |            1 |         0 | Mail-order dependence and 1 UM restriction            |
| Case 7 | Aetna Medicare Preferred Plus (HMO-POS)                 |    0.00 |     0.00 |       0.00 | full     | adequate            |            1 |         0 | Mail-order dependence and 1 UM restriction            |
| Case 8 | Kaiser Permanente Senior Advantage LA, Orange Co. (HMO) |    0.00 |     0.00 |       0.00 | full     | no_preferred_retail |            0 |         0 | No preferred-retail network and mail-order dependence |

**Table C.3. Cost-simulation and model-ranking trace for sample cases.**

| Case | Top-hybrid fill simulation | Negotiated-price proxy | Final drug OOP | Ranking effect | Model score/confidence |
|---|---|---:|---:|---|---|
| Case 1 | 5 fills per 90-day generic through preferred retail; no deductible or OOP-cap trigger | 233.20 | 0.00 | Rules top remained hybrid rank 1; hybrid top was rules rank 1 | 10891.22 high |
| Case 2 | 13 fills each for Toujeo and Ozempic through preferred mail; no deductible or OOP-cap trigger | 16415.75 | 0.00 | Rules top moved to hybrid rank 3; hybrid top was rules rank 13 | 10825.09 high |
| Case 3 | 13 fills each for Humira and Eliquis through preferred mail; no deductible or OOP-cap trigger | 96497.83 | 0.00 | Rules top moved to hybrid rank 24; hybrid top was rules rank 16 | 10825.09 high |
| Case 4 | 13 lisinopril fills through preferred mail; no deductible or OOP-cap trigger | 6.63 | 0.00 | Rules top remained hybrid rank 1; hybrid top was rules rank 1 | 10894.22 high |
| Case 5 | 13 fills each for albuterol and omeprazole through preferred retail; no deductible or OOP-cap trigger | 174.20 | 0.00 | Rules top remained hybrid rank 1; hybrid top was rules rank 1 | 10853.21 high |
| Case 6 | 13 fills each for Jardiance, Entresto, and gabapentin through preferred mail; no deductible or OOP-cap trigger | 17637.75 | 0.00 | Rules top moved to hybrid rank 28; hybrid top was rules rank 20 | 10853.21 high |
| Case 7 | Same fill path as Case 6 under full LIS; LIS-adjusted final OOP remained 0.00 in the top trace | 17637.75 | 0.00 | Rules top moved to hybrid rank 40; hybrid top was rules rank 20 | 10853.21 high |
| Case 8 | 13 Rivfloza fills through nonpreferred mail; sparse full-coverage set; no deductible or OOP-cap trigger in top trace | 856671.53 | 0.00 | Rules top remained hybrid rank 1; hybrid top was rules rank 1 | 10817.51 high |

## Acknowledgements

The authors acknowledge the public CMS documentation and data ecosystem that makes quarter-specific Medicare Part D plan-design analysis possible, and the counseling-oriented problem framing that shaped the system's emphasis on explanation and guardrails.

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
