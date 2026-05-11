---
title: CMS MPD Ranking Models, Evaluation Metrics, and Cost Simulation - Technical Explanation
created: 2026-04-25
status: manuscript-support
tags:
  - cms-mpd
  - medicare-part-d
  - ranking
  - weak-labels
  - cost-simulation
  - manuscript
source_code:
  - sandbox/src/cms_mpd/modeling.py
  - sandbox/src/cms_mpd/recommend.py
related_notes:
  - CMS MPD Recommendation - Research Flow, Data Logic, and Algorithm
---

# CMS MPD Ranking Models, Evaluation Metrics, and Cost Simulation - Technical Explanation

This note explains the model choices, training modes, evaluation metrics, cost simulation, and recommendation flow for the CMS-MPD study. It is written as manuscript-support material and is grounded in the current implementation in `modeling.py`, `recommend.py`, and the research-flow knowledgebase note.

## 1. Why the study uses two ranking models

The ranking problem is not a general consumer recommender problem. Each beneficiary scenario produces a set of eligible plan candidates, and each candidate already has simulated evidence from the deterministic recommendation engine: coverage status, total annual cost, drug out-of-pocket cost, restrictions, missing-price flags, channel availability, network signals, insulin signals, and medication-match quality. The learned model is therefore a supervised tabular reranker over simulated plan-scenario rows, not a free-form model that invents eligibility, coverage, or cost facts.

For a scenario $s$ and plan $p$, the training row can be written as

$$
\mathbf{x}_{s,p} =
\left[
\text{cost features},
\text{coverage features},
\text{restriction features},
\text{network features},
\text{match features},
\text{beneficiary context},
\text{scenario context}
\right].
$$

The target is the weak-label score $\tilde{y}_{s,p}$ constructed from the rules replay. The two fitted models both estimate

$$
\hat{y}_{s,p} = f(\mathbf{x}_{s,p}),
$$

but they do it with different bias-variance and explainability tradeoffs.

### 1.1 Linear ridge reranker

The linear model is a ridge-regression reranker over standardized numeric features and one-hot encoded categorical features. If $\phi(\mathbf{x}_{s,p})$ is the encoded feature vector, the model is

$$
\hat{y}_{s,p}^{\mathrm{linear}}
=
\beta_0 + \phi(\mathbf{x}_{s,p})^\top \boldsymbol{\beta}.
$$

The fitted coefficients solve the penalized least-squares objective

$$
\min_{\beta_0,\boldsymbol{\beta}}
\sum_{(s,p)}
\left(
\tilde{y}_{s,p} -
\beta_0 -
\phi(\mathbf{x}_{s,p})^\top \boldsymbol{\beta}
\right)^2
+
\alpha \lVert \boldsymbol{\beta} \rVert_2^2.
$$

The implementation standardizes encoded features before fitting and uses a closed-form ridge solution with no penalty on the intercept. The default regularization is

$$
\alpha = 5.0.
$$

This model is useful because:

- It is stable for sparse one-hot categorical features and correlated numeric cost features.
- It provides a transparent baseline for whether the weak-label target is learnable from the simulated evidence rows.
- It reduces overfitting risk through ridge shrinkage.
- It makes feature-direction reasoning easier for reviewers because the model is additive in encoded features.

The linear model is therefore the conservative statistical baseline: if it performs well, the target is largely captured by monotone or additive relationships among coverage, cost, and restriction features.

### 1.2 Additive shallow tree reranker

The tree model is a lightweight residual tree ensemble. The implementation starts from the mean weak-label score and then fits shallow regression trees to residuals:

$$
F_0(\mathbf{x}) = \bar{y},
$$

$$
r_i^{(m)} = \tilde{y}_i - F_{m-1}(\mathbf{x}_i),
$$

$$
F_m(\mathbf{x}) = F_{m-1}(\mathbf{x}) + \eta h_m(\mathbf{x}),
$$

where $h_m$ is a shallow regression tree and $\eta$ is the learning rate. The deployed tree score is

$$
\hat{y}_{s,p}^{\mathrm{tree}}
=
F_M(\mathbf{x}_{s,p}).
$$

The default tree parameters are:

| Parameter | Current default | Rationale |
|---|---:|---|
| Learning rate $\eta$ | `0.12` | Moderates each residual update so no single tree dominates the ranking. |
| Number of trees $M$ | `40` | Enough capacity for interactions without turning the model into a large opaque ensemble. |
| Maximum depth | `3` | Captures low-order interactions such as coverage-by-cost, LIS-by-cost, or restriction-by-network. |
| Minimum leaf size | `5` | Prevents highly specific plan-scenario fragments from driving splits. |

This model is useful because many Part D ranking effects are conditional rather than purely additive. For example:

- A low annual cost is less meaningful when a requested drug is uncovered.
- A restriction burden has different implications for generic maintenance drugs than for specialty or insulin scenarios.
- Network risk matters more in access-sensitive scenarios than in mail-order-friendly scenarios.
- LIS status changes how simulated out-of-pocket exposure should affect plan preference.

The tree reranker is therefore the practical non-linear model: it can learn interactions, but its shallow depth and small ensemble size keep the model compatible with reviewer-facing explanation and constrained deployment.

### 1.3 Why not a larger black-box model

A larger neural or high-capacity ranker would be poorly matched to the study's evidence structure. The study does not have prospective enrollment choices, adherence outcomes, health outcomes, or observed beneficiary utility labels. Instead, it has replayed plan-scenario rows and an auditable weak-label target. In that setting, the correct methodological priority is not raw predictive capacity; it is traceable ranking behavior under safety constraints. Ridge regression and shallow residual trees are appropriate because they are:

- tabular-data models;
- reproducible with a small artifact footprint;
- inspectable enough for manuscript review;
- compatible with held-out-by-scenario evaluation;
- constrained to rerank already simulated candidate rows.

## 2. `student_safe` versus `teacher_features`

The training dataset includes both direct rules-engine summary columns and lower-level simulated evidence columns. The key distinction is whether the learned model is allowed to use direct teacher outputs as inputs.

The implementation names the two modes:

- `student_safe`
- `teacher_features`

The phrase `teacher_style` is best interpreted as the code's `teacher_features` policy.

### 2.1 Teacher-style columns

The code defines the direct teacher-style numeric columns as:

| Column | Meaning |
|---|---|
| `current_rules_rank` | Rank assigned by the deterministic rules-first engine. |
| `current_rules_score` | Rules score computed from coverage, annual cost, uncovered drugs, restrictions, and network priority. |
| `fit_score` | Composite fit score exposed by the recommendation engine. |
| `cost_score` | Cost component of the fit summary. |
| `premium_score` | Premium component of the fit summary. |
| `coverage_score` | Coverage component of the fit summary. |
| `access_score` | Access/network component of the fit summary. |
| `stability_score` | Stability component of the fit summary. |

These columns are valuable for audit and analysis, but they are also close to the deterministic teacher that produces the initial ranking. If the model uses them, it can partially learn to copy the teacher.

### 2.2 `student_safe` mode

In `student_safe` mode, the dataset still records teacher columns for analysis, but the feature matrix excludes them:

$$
X_{\mathrm{student}}
=
X_{\mathrm{full}} \setminus T,
$$

where $T$ is the set of teacher-style columns listed above.

The trained model still sees simulated evidence, such as annual premium, annual drug OOP, annual total cost, covered/priced drug shares, uncovered drugs, restriction counts, deductible exposure, LIS-adjusted OOP, negotiated price totals, insulin risk, match quality, network risk, and scenario context. It does not directly see the current rules rank or rules score.

This is the default policy:

$$
\texttt{DEFAULT\_TEACHER\_FEATURE\_POLICY} = \texttt{student\_safe}.
$$

For manuscript purposes, `student_safe` is the cleaner default because it tests whether the model can learn ranking preferences from explainable simulated features rather than simply memorizing the deterministic ranker.

### 2.3 `teacher_features` mode

In `teacher_features` mode, the model keeps the teacher-style columns:

$$
X_{\mathrm{teacher}}
=
X_{\mathrm{full}}.
$$

This can be useful for ablation, diagnostics, and upper-bound experiments. It answers a different question: how much performance is possible when the model can use both lower-level evidence and direct outputs of the deterministic teacher?

However, `teacher_features` is less conservative for reviewer-facing claims. If a model trained with teacher features improves agreement with the weak-label ranking, some of that gain may come from copying or smoothing the teacher's own summary scores. It should therefore be interpreted as a teacher-assisted reranker, not as a fully independent student model.

### 2.4 Recommended interpretation in the manuscript

The manuscript should state:

- The replay dataset contains rules-engine summary columns for auditability.
- The default trained artifact uses `student_safe`, which excludes direct teacher-style numeric columns from the feature matrix.
- The model is not replacing the rules engine; it learns from lower-level simulated evidence and reranks only within safety buckets.
- `teacher_features` is best reserved for sensitivity analysis or diagnostic comparison.

## 3. Weak-label target and supervised ranking interpretation

The study lacks observed beneficiary plan selections or prospective clinical outcomes. Weak labels bridge that gap by converting deterministic replay rows into an explicit supervised target.

For each scenario-plan row $(s,p)$, the weak label is:

$$
\begin{aligned}
\tilde{y}_{s,p}
=&
1000 \cdot \mathbb{1}\{\mathrm{coverage}_{s,p}=\mathrm{full}\}
+ R_{s,p}
- C_{s,p}
\\
&-250U_{s,p}
-125E_{s,p}
-110M_{s,p}
-90A_{s,p}
\\
&-25H_{s,p}
-20Q_{s,p}
-18D_{s,p}
-15I_{s,p}
\\
&-12N_{s,p}
-20G_{s,p}.
\end{aligned}
$$

Where:

| Symbol | Implementation field | Interpretation |
|---|---|---|
| $R_{s,p}$ | `current_rules_score` | Deterministic rules score from the serving engine. |
| $C_{s,p}$ | `annual_total_cost` | Annual premium plus simulated drug OOP. |
| $U_{s,p}$ | `uncovered_drug_count` | Requested drugs not covered/priced. |
| $E_{s,p}$ | `excluded_drug_count` | Formulary exclusions. |
| $M_{s,p}$ | `missing_price_drug_count` | Covered drugs without usable price basis. |
| $A_{s,p}$ | `channel_unavailable_count` | Drugs not priceable under selected channel preference. |
| $H_{s,p}$ | `restriction_count` | Prior authorization, step therapy, or quantity-limit burden. |
| $Q_{s,p}$ | `approximate_match_count` | Medication matches below exact/preferred confidence. |
| $D_{s,p}$ | `mail_order_dependency_flag` | Reliance on mail-order availability. |
| $I_{s,p}$ | `insulin_risk_flag` | Insulin-specific plan-design risk. |
| $N_{s,p}$ | `insulin_nonpreferred_dependency_count` | Insulin dependent on non-preferred channels. |
| $G_{s,p}$ | `network_risk_score` | Network/access risk mapped from network status. |

The target intentionally makes coverage dominate cost. This reflects the study's decision-support boundary: a lower-cost plan is not clinically or operationally preferable if it fails to cover or price the beneficiary's requested drugs.

Weak labels serve three roles:

- They convert each plan-scenario candidate set into an ordered supervision target.
- They make the study's preference structure explicit and auditable.
- They enable held-out evaluation when external enrollment or outcome labels are unavailable.

Agreement with weak labels should be interpreted as internal ranking validity relative to the study's explicit decision logic. It is not evidence of causal improvement in clinical outcomes, adherence, enrollment satisfaction, or realized pharmacy spending.

## 4. Evaluation metrics in mathematical form

Let $\mathcal{S}_{\mathrm{test}}$ be a held-out scenario set. For each scenario $s$, let $\mathcal{P}_s$ be the candidate plans. The weak-label reference ranking is

$$
\pi_s^\star =
\operatorname{sort}_{p \in \mathcal{P}_s}
\left(
-\tilde{y}_{s,p},
C_{s,p}
\right),
$$

meaning descending weak-label score with annual total cost as the tie-breaker.

For a ranking method $m$, let $\pi_s^{(m)}$ be the plan ordering produced by that method. The implementation evaluates `rules_only`, `heuristic_baseline`, `linear_reranker`, `tree_reranker`, and tree feature-ablation variants.

### 4.1 Held-out splits

The evaluation uses group-level splits, not random row-level splits. For a split key $g$, such as scenario ID, ZIP code, or regimen signature:

$$
\mathcal{G}
=
\mathcal{G}_{\mathrm{train}}
\cup
\mathcal{G}_{\mathrm{test}},
\qquad
\mathcal{G}_{\mathrm{train}}
\cap
\mathcal{G}_{\mathrm{test}}
=
\varnothing.
$$

Rows are assigned by group membership:

$$
(s,p) \in \mathcal{D}_{\mathrm{test}}
\iff
g(s,p) \in \mathcal{G}_{\mathrm{test}}.
$$

The current defaults are:

$$
\mathrm{test\_fraction}=0.3,
\qquad
\mathrm{seed}=42.
$$

The primary interpretation uses held-out-by-scenario evaluation. Held-out-by-ZIP and held-out-by-regimen-signature reports test geographic and medication-regimen novelty.

### 4.2 Top-1 agreement

Top-1 agreement checks whether the method selects the same top plan as the weak-label reference:

$$
\mathrm{Top1}(s,m)
=
\mathbb{1}
\left[
\pi_s^{(m)}(1) = \pi_s^\star(1)
\right].
$$

The reported value is the scenario average:

$$
\mathrm{Top1}(m)
=
\frac{1}{|\mathcal{S}_{\mathrm{test}}|}
\sum_{s \in \mathcal{S}_{\mathrm{test}}}
\mathrm{Top1}(s,m).
$$

This is a strict metric. It gives no partial credit for placing the reference-best plan second or third.

### 4.3 Top-k overlap

Top-k overlap measures how much the method's shortlist matches the weak-label reference shortlist:

$$
\mathrm{Overlap}_k(s,m)
=
\frac{
\left|
\mathrm{Top}_k(\pi_s^{(m)})
\cap
\mathrm{Top}_k(\pi_s^\star)
\right|
}{
\min(k, |\mathcal{P}_s|)
}.
$$

The reported value averages over held-out scenarios:

$$
\mathrm{Overlap}_k(m)
=
\frac{1}{|\mathcal{S}_{\mathrm{test}}|}
\sum_s
\mathrm{Overlap}_k(s,m).
$$

This metric is important for plan counseling because a reviewer or counselor often cares about whether the top shortlist contains the same plausible plans, not only whether the first plan is identical.

### 4.4 Relevance and NDCG

The code converts the weak-label rank into a graded relevance score. If $\operatorname{rank}_s^\star(p)$ is the reference rank of plan $p$ in scenario $s$, then:

$$
\mathrm{rel}_{s,p}
=
\max
\left(
0,
6 - \operatorname{rank}_s^\star(p)
\right).
$$

Thus the top five reference plans receive relevance values $5,4,3,2,1$, and lower-ranked plans receive $0$.

For method $m$, discounted cumulative gain is:

$$
\mathrm{DCG}@k(s,m)
=
\sum_{i=1}^{k}
\frac{
2^{\mathrm{rel}_{s,\pi_s^{(m)}(i)}} - 1
}{
\log_2(i+1)
}.
$$

The ideal DCG is computed from the best possible ordering under the same relevance values:

$$
\mathrm{IDCG}@k(s)
=
\max_{\pi}
\mathrm{DCG}@k(s,\pi).
$$

Normalized discounted cumulative gain is:

$$
\mathrm{NDCG}@k(s,m)
=
\frac{\mathrm{DCG}@k(s,m)}{\mathrm{IDCG}@k(s)}.
$$

The reported $\mathrm{NDCG}@k$ is the mean across scenarios. NDCG gives higher credit for placing the best weak-label plans near the top, while still rewarding useful ordering beyond rank 1.

### 4.5 Full-coverage rate

For top-$k$ recommendations, the full-coverage rate is:

$$
\mathrm{FullCoverageRate}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
\mathbb{1}
\left[
\mathrm{coverage}_{s,\pi_s^{(m)}(i)}=\mathrm{full}
\right],
$$

where $k_s=\min(k,|\mathcal{P}_s|)$. This metric verifies that ranking improvements do not come from moving partially covered or unpriceable plans into the shortlist.

### 4.6 Top-k average total cost

The top-$k$ average total cost is:

$$
\mathrm{AvgCost}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
C_{s,\pi_s^{(m)}(i)}.
$$

where

$$
C_{s,p}
=
\mathrm{annual\_premium}_{p}
+
\mathrm{annual\_drug\_oop}_{s,p}.
$$

This metric is not optimized alone. It is interpreted after coverage and safety metrics because a low-cost but uncovered plan is not a good recommendation.

### 4.7 Top-k average uncovered burden

The uncovered-drug burden is:

$$
\mathrm{AvgUncovered}_k(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
U_{s,\pi_s^{(m)}(i)}.
$$

This is a guardrail metric. If a learned reranker improves top-k agreement but increases uncovered-drug burden, the result supports constrained decision support rather than autonomous model-driven plan selection.

### 4.8 Blocker precision and review-trigger metrics

For scenarios where no plan has full coverage in the weak-label reference set, the implementation compares whether the top predicted plan belongs to the same fallback group as the reference top plan:

$$
\mathrm{BlockerPrecision}(s,m)
=
\mathbb{1}
\left[
\mathrm{fallback}_{s,\pi_s^{(m)}(1)}
=
\mathrm{fallback}_{s,\pi_s^\star(1)}
\right].
$$

The match-review trigger rate is the average manual-review flag rate in the top five:

$$
\mathrm{ReviewRate}_5(s,m)
=
\frac{1}{k_s}
\sum_{i=1}^{k_s}
\mathbb{1}
\left[
\mathrm{manual\_review}_{s,\pi_s^{(m)}(i)}=1
\right].
$$

The unknown-network indicator is scenario-level:

$$
\mathrm{UnknownNetwork}(s,m)
=
\mathbb{1}
\left[
\exists p \in \pi_s^{(m)}
:
\mathrm{unknown\_network}_{s,p}=1
\right].
$$

These metrics measure whether the ranking flow preserves operational caution when evidence is incomplete.

## 5. Mathematical cost simulation flow

The cost engine simulates plan-drug cost using public plan-design artifacts and local derived serving tables. It does not guarantee actual pharmacy transaction prices. It creates a consistent public-file/local-artifact estimate for comparing plans under the same beneficiary scenario.

### 5.1 Beneficiary input and eligible plans

Let a beneficiary request be:

$$
b =
\left(
z,
\mathcal{M},
\ell,
a,
q
\right),
$$

where $z$ is ZIP code, $\mathcal{M}$ is the requested medication set, $\ell$ is LIS status, $a$ is age context, and $q$ is pharmacy preference.

ZIP-to-county and plan service-area tables define the eligible candidate set:

$$
\mathcal{P}(z)
=
\left\{
p:
\mathrm{county}(z) \in \mathrm{service\_area}(p)
\right\}.
$$

The recommendation engine starts from $\mathcal{P}(z)$, not from all plans nationally.

### 5.2 Medication resolution

Each requested medication $m \in \mathcal{M}$ is resolved to plan-drug evidence where possible:

$$
\rho(m,p)
\rightarrow
\left(
\mathrm{NDC},
\mathrm{RXCUI},
\mathrm{tier},
\mathrm{quantity},
\mathrm{days\_supply},
\mathrm{cost\_basis},
\mathrm{restriction\_flags}
\right).
$$

Exact NDC or RXCUI-backed matches are preferred. Approximate matches and manual-review cases are flagged and penalized in weak-label construction.

### 5.3 Fill-event expansion

For each medication $m$, the engine expands annual utilization into scheduled fills:

$$
\mathcal{E}_m =
\left\{
e_{m,j}: j=1,\dots,n_m
\right\},
$$

where $n_m$ is `fills_per_year`. The scheduled day offset is approximately:

$$
d_{m,j}
=
\operatorname{round}
\left(
(j-1)\frac{365}{n_m}
\right).
$$

Events are ordered by:

1. day offset;
2. deductible-applicable drugs before non-deductible drugs;
3. higher negotiated-price proxy first;
4. medication ID;
5. fill number.

This ordering gives the simulation a deterministic path for deductible and annual OOP accumulation.

### 5.4 Channel selection

For each fill event $e$, the available channel set is:

$$
\mathcal{C}_{p,m,e}
\subseteq
\{
\mathrm{preferred\ retail},
\mathrm{standard\ retail},
\mathrm{preferred\ mail},
\mathrm{standard\ mail},
\mathrm{nonpreferred\ retail},
\mathrm{nonpreferred\ mail}
\}.
$$

For each channel $c$, the negotiated price proxy is:

$$
N_{p,m,e,c}
=
\max
\left(
\mathrm{unit\_cost}_{p,m} \cdot \mathrm{quantity}_{m}
+ \mathrm{dispensing\_fee}_{p,m,c},
\mathrm{channel\_floor}_{p,m,c}
\right).
$$

The engine simulates OOP for each available channel and chooses the channel with the lowest OOP. Near ties preserve the previous channel when available, then apply preferred-channel and pharmacy-preference tie-breakers. Formally, the chosen channel is approximately:

$$
c^\star
=
\operatorname{argmin}_{c \in \mathcal{C}_{p,m,e}}
\mathrm{OOP}_{p,m,e,c},
$$

with deterministic tie-breaking for continuity and preference.

### 5.5 2025 benefit-design cost calculation

For 2025, the simulation uses deductible, initial coverage, insulin handling, LIS adjustment, and the annual out-of-pocket cap. For fill event $e$ under chosen channel $c^\star$, let:

$$
N_e = N_{p,m,e,c^\star}
$$

be the negotiated price proxy. The base pre-LIS OOP is computed by the plan's cost-sharing rule:

$$
B_e
=
f_{\mathrm{initial}}
\left(
N_e,
\mathrm{deductible\_remaining}_{e-1},
\mathrm{tier}_{p,m},
\mathrm{channel}_{c^\star},
\mathrm{insulin}_{m}
\right).
$$

For deductible-applicable non-insulin fills, this can include:

$$
B_e
=
\min(N_e, D_{e-1})
+
\mathrm{costshare}_{\mathrm{initial}}
\left(
\max(0, N_e-\min(N_e,D_{e-1}))
\right),
$$

where $D_{e-1}$ is remaining deductible before the fill. For insulin, the implementation first checks insulin-specific copay fields and uses an insulin override when available.

LIS adjustment is then applied:

$$
L_e =
A_{\mathrm{LIS}}(B_e, \mathrm{tier}, \ell).
$$

For full LIS:

$$
A_{\mathrm{LIS}}(B_e, \mathrm{tier}, \mathrm{full})
=
\min(B_e, \mathrm{LISCap}_{\mathrm{tier}}).
$$

For partial LIS:

$$
A_{\mathrm{LIS}}(B_e, \mathrm{tier}, \mathrm{partial})
=
\min(\gamma B_e, \mathrm{PartialLISCap}_{\mathrm{tier}}),
$$

where $\gamma$ is the partial-LIS discount factor. For no LIS:

$$
A_{\mathrm{LIS}}(B_e, \mathrm{tier}, \mathrm{none})
=
B_e.
$$

The final beneficiary OOP for the fill is capped by remaining annual OOP capacity:

$$
O_e =
\begin{cases}
0, & O_{e-1}^{\mathrm{cum}} \ge K, \\
\min(L_e, K - O_{e-1}^{\mathrm{cum}}), & O_{e-1}^{\mathrm{cum}} < K,
\end{cases}
$$

where $K$ is the annual OOP cap. The cumulative OOP update is:

$$
O_e^{\mathrm{cum}}
=
O_{e-1}^{\mathrm{cum}} + O_e.
$$

The cumulative negotiated spending update is:

$$
S_e^{\mathrm{cum}}
=
S_{e-1}^{\mathrm{cum}} + N_e.
$$

The implementation records each fill's negotiated price, deductible exposure, initial-coverage OOP, LIS-adjusted OOP, final OOP, OOP-before/OOP-after, OOP-cap flag, and benefit-design label.

### 5.6 2024 benefit-design branch

The code also retains a 2024 benefit-design branch. In that branch, the simulation can split a fill into initial-coverage and coverage-gap segments, track TrOOP, and enter catastrophic coverage:

$$
N_e
=
N_e^{\mathrm{initial}}
+
N_e^{\mathrm{gap/catastrophic}}.
$$

The 2024 branch is useful for year-over-year methodology, but the current 2025 manuscript interpretation should emphasize the 2025 path because it includes the IRA-era annual OOP cap behavior.

### 5.7 Annual plan cost

For plan $p$ and scenario $s$, annual drug OOP is:

$$
\mathrm{DrugOOP}_{s,p}
=
\sum_{m \in \mathcal{M}}
\sum_{e \in \mathcal{E}_m}
O_{s,p,m,e}.
$$

Annual premium is:

$$
\mathrm{Premium}_{p}
=
12 \cdot \mathrm{monthly\_premium}_{p}.
$$

Annual total cost is:

$$
C_{s,p}
=
\mathrm{Premium}_{p}
+
\mathrm{DrugOOP}_{s,p}.
$$

This $C_{s,p}$ is used in rules scoring, weak-label construction, evaluation metrics, and the hybrid reranking tie-breaks.

## 6. Recommendation and model ranking flow

The deployed recommendation flow is rules-first, then optionally hybrid-reranked within safety buckets.

### 6.1 Deterministic rules score

For a candidate plan $p$ in scenario $s$, the rules score is:

$$
R_{s,p}
=
10000 \cdot \mathbb{1}
\{\mathrm{coverage}_{s,p}=\mathrm{full}\}
- C_{s,p}
- 250U_{s,p}
- 35H_{s,p}
- 20V_{s,p},
$$

where:

- $C_{s,p}$ is annual total cost;
- $U_{s,p}$ is uncovered-drug count;
- $H_{s,p}$ is restriction count;
- $V_{s,p}$ is the network-priority penalty.

The large full-coverage bonus makes the deterministic ranker coverage-first. This prevents a low-premium plan with missing medication coverage from being treated as superior to a plan that actually prices all requested drugs.

### 6.2 Rules-first safety buckets

Before detailed ordering, plans are assigned to safety buckets:

$$
B_{s,p}
=
\begin{cases}
0, & \mathrm{coverage}_{s,p}=\mathrm{full}\ \mathrm{and}\ \mathrm{priced}_{s,p}=|\mathcal{M}|,\\
1, & \mathrm{priced}_{s,p}>0,\\
2, & \mathrm{otherwise}.
\end{cases}
$$

Bucket 0 is full coverage and fully priceable. Bucket 1 is partially priceable. Bucket 2 is fallback or unpriceable. Rules ranking sorts by bucket first, then by priced-drug count and scenario-specific tie-breaks. For example, specialty scenarios prioritize restriction burden, channel switching, network priority, distance, total cost, and fit score; insulin scenarios emphasize drug OOP and insulin channel dependency; maintenance scenarios emphasize total cost and premium.

### 6.3 Training replay rows

Scenario generation creates beneficiary-like inputs. Each scenario is replayed through the same recommendation engine used at runtime. This yields feature rows:

$$
\mathcal{D}
=
\{
(\mathbf{x}_{s,p}, \tilde{y}_{s,p}, \mathrm{rel}_{s,p})
:
s \in \mathcal{S},\ p \in \mathcal{P}(z_s)
\}.
$$

This design keeps training close to runtime behavior. The model does not learn from disconnected synthetic labels; it learns from the same kind of plan comparison rows the application serves.

### 6.4 Hybrid reranking

At inference, the hybrid model computes:

$$
\hat{y}_{s,p}
=
f(\mathbf{x}_{s,p})
$$

for each already simulated recommendation row. It does not create new coverage, eligibility, network, or cost facts.

The hybrid ordering is constrained:

$$
\pi_{\mathrm{hybrid}}(s)
=
\bigcup_{b \in \{0,1,2\}}
\operatorname{sort}_{p:B_{s,p}=b}
\left(
-\hat{y}_{s,p},
-P_{s,p},
-R_{s,p},
C_{s,p},
U_{s,p},
H_{s,p},
\mathrm{name}_p
\right),
$$

where:

- $B_{s,p}$ is the safety bucket;
- $\hat{y}_{s,p}$ is the model score;
- $P_{s,p}$ is priced-drug count;
- $R_{s,p}$ is rules score;
- $C_{s,p}$ is annual total cost;
- $U_{s,p}$ is uncovered-drug count;
- $H_{s,p}$ is restriction count.

This means the model can change the order within bucket 0, within bucket 1, and within bucket 2, but it cannot move a partially priceable plan ahead of a fully covered and fully priceable plan. The model is therefore a constrained reranker rather than an autonomous recommender.

### 6.5 Confidence bucket

After reranking, the implementation assigns a confidence bucket based on the model-score margin from the top score:

$$
\Delta_{s,p}
=
\hat{y}_{s,p^\star} - \hat{y}_{s,p}.
$$

The current thresholds are:

| Margin from top score | Confidence bucket |
|---:|---|
| $\Delta \le 5$ | `high` |
| $5 < \Delta \le 25$ | `medium` |
| $\Delta > 25$ | `low` |

This is a ranking-confidence signal, not a probability of clinical benefit or realized savings.

## 7. How to describe the model contribution in the manuscript

A concise reviewer-facing description would be:

> The study evaluates a rules-first Medicare Part D recommendation engine with an optional constrained hybrid reranker. Candidate plans are first restricted by service area and simulated using public plan-design evidence, medication-level cost basis, pharmacy-channel availability, LIS status, deductible logic, insulin rules, and the 2025 OOP cap. The deterministic engine produces coverage-first rankings and auditable explanations. Scenario replay converts these runtime comparisons into plan-scenario feature rows. Weak labels transform the study's preference structure into an ordered supervision target. A ridge reranker and a shallow residual tree ensemble are trained to predict the weak-label score from encoded simulated evidence. The default `student_safe` policy excludes direct teacher-style rank and score columns from the model feature matrix. At inference, the learned score reranks only within three safety buckets, so the model cannot override coverage or priceability constraints.

The important methodological claim is not that the model discovers true beneficiary utility. The defensible claim is narrower:

$$
\text{The learned reranker improves alignment with an explicit, auditable ranking policy}
$$

subject to:

$$
\text{public-file cost simulation}
+ 
\text{scenario replay}
+
\text{weak-label supervision}
+
\text{safety-bucket constraints}.
$$

## 8. Practical manuscript caveats

The manuscript should keep four boundaries explicit:

- Cost estimates are simulated from public-file/local-artifact plan design, not guaranteed pharmacy transaction prices.
- Weak-label agreement is internal validity against the study's decision logic, not external clinical or enrollment validity.
- `student_safe` is the default reviewer-facing policy because it avoids direct teacher-output leakage.
- The hybrid model reranks only already simulated candidate rows and cannot create coverage, eligibility, network, or price evidence.

