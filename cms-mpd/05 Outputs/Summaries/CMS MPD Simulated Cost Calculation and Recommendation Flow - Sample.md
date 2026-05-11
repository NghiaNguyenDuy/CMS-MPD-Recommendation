---
title: CMS MPD Simulated Cost Calculation and Recommendation Flow - Sample
created: 2026-04-25
status: manuscript-support
tags:
  - cms-mpd
  - cost-simulation
  - recommendation-flow
  - manuscript
source_code:
  - sandbox/src/cms_mpd/recommend.py
  - sandbox/src/cms_mpd/modeling.py
---

# CMS MPD Simulated Cost Calculation and Recommendation Flow - Sample

This note gives one implementation-grounded sample of the CMS-MPD recommendation flow. The values below were generated from the local `2025-Q3/full` DuckDB artifact and the current `recommend_plans()` implementation.

## 1. Sample request

Beneficiary request:

| Field | Value |
|---|---|
| ZIP code | `10001` |
| Age band | `65-74` |
| LIS status | `none` |
| Pharmacy preference | `auto` |
| Ranking modes tested | `rules`, `hybrid` |
| Top-N request | `5` for ranking comparison; `100` for finding a nonzero cost trace |

Medication inputs used exact NDCs:

| Medication | NDC | RXCUI resolved by local artifact | Match |
|---|---|---:|---|
| Jardiance, empagliflozin 10 mg tablet | `00597015230` | `1545664` | exact NDC |
| Entresto, sacubitril/valsartan 49/51 mg tablet | `00078077720` | `1656351` | exact NDC |
| Gabapentin 300 mg capsule | `45963055650` | `310431` | exact NDC |

The implementation classified this case as `specialty_high_cost` because the regimen includes high negotiated-price drugs.

## 2. Runtime recommendation flow

The implementation runs the request in this sequence:

1. Resolve medications by NDC/RXCUI against the local gold drug catalog.
2. Map ZIP `10001` to the applicable service area and candidate plans.
3. For each eligible plan, price each medication if a usable plan-drug cost basis exists.
4. Expand each medication into annual fill events.
5. Select the lowest-OOP channel per fill, with tie-breaking for channel continuity and pharmacy preference.
6. Apply the 2025 cost design: deductible, initial coverage, LIS adjustment, insulin override when relevant, and annual OOP cap.
7. Sum drug OOP and annual premium into annual total cost.
8. Rank first with deterministic rules.
9. If `ranking_mode="hybrid"`, score already simulated rows with the tree reranker and rerank only inside safety buckets.

No model step creates new coverage, price, network, or eligibility facts. The model only reranks candidate rows after deterministic simulation.

## 3. Rules-mode ranking output

Rules-mode top 3:

| Rank | Plan key | Plan name | Coverage | Priced drugs | Restrictions | Network | Annual premium | Drug OOP | Total cost | Rules score |
|---:|---|---|---|---:|---:|---|---:|---:|---:|---:|
| 1 | `H7849082000` | Cigna True Choice Medicare (PPO) | full | 3 | 1 | adequate | 0.00 | 0.00 | 0.00 | 9965.00 |
| 2 | `H7849128000` | Cigna True Choice Plus Medicare (PPO) | full | 3 | 1 | adequate | 420.00 | 0.00 | 420.00 | 9545.00 |
| 3 | `H5599004000` | Wellcare Fidelis Simple (HMO-POS) | full | 3 | 1 | adequate | 0.00 | 420.00 | 420.00 | 9545.00 |

The rules score is:

$$
R_{s,p}
=
10000\cdot\mathbb{1}\{\mathrm{coverage}=\mathrm{full}\}
- C_{s,p}
-250U_{s,p}
-35H_{s,p}
-20V_{s,p}.
$$

For the first plan:

$$
R
=
10000
-0
-250(0)
-35(1)
-20(0)
=
9965.
$$

For the third plan:

$$
R
=
10000
-420
-250(0)
-35(1)
-20(0)
=
9545.
$$

This shows why the rules engine ranks the zero-total-cost full-coverage plan first. Plans 2 and 3 tie on rules score because both have full coverage, one restriction, adequate network, and total annual cost of `420.00`.

## 4. Hybrid ranking output

Hybrid-mode top 3:

| Rank | Plan key | Plan name | Coverage | Priced drugs | Network | Total cost | Rules score | Model score | Confidence |
|---:|---|---|---|---:|---|---:|---:|---:|---|
| 1 | `H7849082000` | Cigna True Choice Medicare (PPO) | full | 3 | adequate | 0.00 | 9965.00 | 10853.21 | high |
| 2 | `H3347016000` | Elderplan Flex (HMO-POS) | full | 3 | no_preferred_retail | 0.00 | 9925.00 | 10774.75 | low |
| 3 | `H3347018000` | Elderplan Select (HMO-POS I-SNP) | full | 3 | no_preferred_retail | 0.00 | 9925.00 | 10774.75 | low |

All three plans are in safety bucket 0:

$$
B_{s,p}=0
\quad\text{because}\quad
\mathrm{coverage}=\mathrm{full}
\ \mathrm{and}\
\mathrm{priced\_drug\_count}=3.
$$

The hybrid reranker therefore orders them within the full-coverage/fully-priceable bucket by:

$$
\left(
-\hat{y}_{s,p},
-\mathrm{priced\_drug\_count},
-R_{s,p},
C_{s,p},
U_{s,p},
H_{s,p},
\mathrm{plan\_name}
\right).
$$

The hybrid model promotes other zero-cost full-coverage candidates above some rules-mode candidates because the model score is used inside the same safety bucket. It does not move any partial-coverage or unpriceable plan ahead of full-coverage plans.

## 5. Cost calculation trace: zero-OOP top hybrid plan

Top hybrid plan:

| Field | Value |
|---|---|
| Plan key | `H7849082000` |
| Plan name | Cigna True Choice Medicare (PPO) |
| Annual premium | `0.00` |
| Annual drug OOP | `0.00` |
| Annual total cost | `0.00` |
| Coverage status | full |
| Restriction summary | quantity limits |
| Selected channel mix | `pref_mail:39` |

The engine expanded 3 medications into 39 total fills: 13 fills per medication.

Drug-level simulated totals:

| Drug | Channel | Fill count | Negotiated price total | Final annual OOP | Notes |
|---|---|---:|---:|---:|---|
| Jardiance | preferred mail | 13 | 6685.04 | 0.00 | quantity limit flagged |
| Entresto | preferred mail | 13 | 4063.73 | 0.00 | quantity limit flagged |
| Gabapentin | preferred mail | 13 | 38.37 | 0.00 | quantity limit flagged |

For Jardiance on this plan, the first fill trace was:

| Trace field | Value |
|---|---:|
| Selected channel | `pref_mail` |
| Coverage phase | `initial_coverage_rule` |
| Negotiated price | 514.23 |
| Deductible before | 0.00 |
| Deductible applied | 0.00 |
| Base OOP | 0.00 |
| LIS-adjusted OOP | 0.00 |
| Final OOP | 0.00 |
| OOP before | 0.00 |
| OOP after | 0.00 |
| OOP cap applied | false |

The arithmetic for this fill is:

$$
\mathrm{negotiated}
=
514.23.
$$

Because no deductible remained and the plan's initial-coverage rule produced zero beneficiary liability for this channel:

$$
\mathrm{base\_oop}=0.00.
$$

With LIS status `none`, the LIS adjustment is identity:

$$
\mathrm{lis\_adjusted\_oop}=0.00.
$$

The 2025 OOP cap does not change the value:

$$
\mathrm{final\_oop}
=
\min(0.00, 2000.00 - 0.00)
=
0.00.
$$

The same zero-OOP result occurred across the simulated fills, so:

$$
\mathrm{DrugOOP}_{s,p}
=
0.00 + 0.00 + 0.00
=
0.00.
$$

Annual total cost is:

$$
C_{s,p}
=
\mathrm{annual\ premium}
+
\mathrm{annual\ drug\ OOP}
=
0.00+0.00
=
0.00.
$$

Important interpretation: the `0.00` value is a public-file/local-artifact simulation result for this plan-design record. It is not a guaranteed real pharmacy transaction price.

## 6. Cost calculation trace: nonzero deductible plan

Rules rank 3 provided a useful nonzero drug-OOP trace:

| Field | Value |
|---|---|
| Plan key | `H5599004000` |
| Plan name | Wellcare Fidelis Simple (HMO-POS) |
| Annual premium | `0.00` |
| Annual drug OOP | `420.00` |
| Annual total cost | `420.00` |
| Coverage status | full |
| Rules score | `9545.00` |

The nonzero annual drug OOP came from Jardiance. The first Jardiance fill trace was:

| Trace field | Value |
|---|---:|
| Selected channel | `pref_mail` |
| Coverage phase | `deductible_then_initial_coverage` |
| Negotiated price | 556.07 |
| Deductible before | 420.00 |
| Deductible applied | 420.00 |
| Deductible after | 0.00 |
| Base OOP | 420.00 |
| LIS-adjusted OOP | 420.00 |
| Final OOP | 420.00 |
| OOP before | 0.00 |
| OOP after | 420.00 |
| OOP cap applied | false |

The arithmetic is:

$$
\mathrm{deductible\ exposure}
=
\min(556.07, 420.00)
=
420.00.
$$

The remaining negotiated amount after deductible is:

$$
556.07 - 420.00
=
136.07.
$$

In this plan's simulated cost basis, the initial-coverage OOP for the remainder was `0.00`, so:

$$
\mathrm{base\_oop}
=
420.00 + 0.00
=
420.00.
$$

With LIS status `none`:

$$
\mathrm{lis\_adjusted\_oop}
=
420.00.
$$

The annual OOP cap does not bind:

$$
\mathrm{final\_oop}
=
\min(420.00, 2000.00 - 0.00)
=
420.00.
$$

After this first fill, the deductible is exhausted:

$$
D_{\mathrm{after}}=0.00.
$$

Later Jardiance fills on this plan used `initial_coverage_rule` and had `final_oop=0.00`, so the annual Jardiance OOP stayed:

$$
420.00 + 12(0.00)
=
420.00.
$$

Entresto and gabapentin added no simulated beneficiary OOP in this candidate, so:

$$
\mathrm{DrugOOP}_{s,p}
=
420.00.
$$

Annual total cost is:

$$
C_{s,p}
=
0.00 + 420.00
=
420.00.
$$

## 7. What this sample demonstrates

This one request shows the core implementation behavior:

- Exact NDC inputs avoid manual-review ambiguity.
- ZIP geography constrains the candidate plan universe before ranking.
- The engine simulates fill-level cost, not only plan-level annual summaries.
- Cost is accumulated through deductible, LIS adjustment, and OOP-cap logic.
- Rules ranking is coverage-first and cost-aware.
- Hybrid ranking is a constrained rerank of already simulated rows.
- A zero-cost result should be interpreted as a local artifact estimate, not a guarantee of realized pharmacy price.

## 8. Full recommendation workflow as a mathematical sample

This section restates the same run as a full mathematical workflow. The goal is to show how the implementation moves from a beneficiary request to the final ranked recommendation, not just how one fill is priced.

### 8.1 Beneficiary request vector

The request can be written as:

$$
s =
(z,\ell,q,a,M),
$$

where:

| Symbol | Meaning | Sample value |
|---|---|---|
| $z$ | ZIP code | `10001` |
| $\ell$ | LIS status | `none` |
| $q$ | pharmacy preference | `auto` |
| $a$ | age band | `65-74` |
| $M$ | requested medication set | Jardiance, Entresto, gabapentin |

The requested medication set is:

$$
M=\{m_1,m_2,m_3\},
$$

with exact NDC inputs:

$$
m_1=\texttt{00597015230}, \quad
m_2=\texttt{00078077720}, \quad
m_3=\texttt{45963055650}.
$$

Because all three inputs are exact NDCs, medication resolution returns exact matches:

$$
\rho(m_j)=
(\mathrm{NDC}_j,\mathrm{RXCUI}_j,\mathrm{name}_j,\mathrm{tier\ family}_j,\mathrm{match}=\mathrm{exact}).
$$

For this sample:

| $j$ | Drug | NDC | RXCUI | Tier family |
|---:|---|---|---:|---|
| 1 | empagliflozin 10 mg tablet [Jardiance] | `00597015230` | `1545664` | brand |
| 2 | sacubitril/valsartan 49/51 mg tablet [Entresto] | `00078077720` | `1656351` | brand |
| 3 | gabapentin 300 mg capsule | `45963055650` | `310431` | generic |

### 8.2 Service-area candidate set

The engine first restricts plans by geography:

$$
\mathcal{P}(z)
=
\{p:\;z\in\mathrm{service\_area}(p)\}.
$$

This is important because the model never scores national plans that are not eligible for the ZIP. For ZIP `10001`, the local artifact produced a service-area candidate set that included both the top hybrid plan:

$$
p_A=\texttt{H7849082000}
$$

and the nonzero deductible comparison plan:

$$
p_B=\texttt{H5599004000}.
$$

### 8.3 Plan-drug pricing basis

For each candidate plan $p$ and medication $m_j$, the engine tries to retrieve a plan-drug cost basis:

$$
B_{p,j}
=
(\mathrm{tier},\mathrm{days\ supply},\mathrm{unit\ cost},\mathrm{fees},\mathrm{cost\ sharing},\mathrm{deductible\ flag},\mathrm{UM\ flags}).
$$

A drug is fully priceable for a plan when:

$$
B_{p,j}\neq\varnothing
\quad\text{and}\quad
\exists c\in\mathcal{C}_{p,j}
\text{ such that fill cost can be simulated}.
$$

For the top hybrid plan, all three drugs were covered and priceable:

$$
\mathrm{priced\_drug\_count}_{p_A}=3=|M|.
$$

The plan therefore entered the safest hybrid bucket:

$$
\beta(p_A)=0.
$$

### 8.4 Annual fill-event expansion

For each medication, the implementation expands expected annual use into scheduled fills:

$$
\mathcal{E}_{j}
=
\{e_{j,1},e_{j,2},\ldots,e_{j,n_j}\}.
$$

For 30-day maintenance-style fills in this sample, the local artifact produced:

$$
n_1=n_2=n_3=13.
$$

The day offset for fill $k$ is approximately:

$$
d_{j,k}
=
\operatorname{round}
\left(
(k-1)\frac{365}{n_j}
\right).
$$

Thus the total fill-event set is:

$$
\mathcal{E}
=
\mathcal{E}_1\cup\mathcal{E}_2\cup\mathcal{E}_3,
\qquad
|\mathcal{E}|=39.
$$

Events are sorted deterministically by day offset, deductible applicability, negotiated-price proxy, medication ID, and fill number. This is why the first simulated fill for the nonzero comparison plan is Jardiance: it had deductible applicability and a higher negotiated-price proxy than the other drugs.

### 8.5 Channel choice per fill

For each plan-drug-fill event, the engine evaluates available channels:

$$
\mathcal{C}_{p,j,k}
\subseteq
\{
\mathrm{preferred\ retail},
\mathrm{nonpreferred\ retail},
\mathrm{preferred\ mail},
\mathrm{nonpreferred\ mail}
\}.
$$

For a channel $c$, the negotiated-price proxy is:

$$
N_{p,j,k,c}
=
\max(
\mathrm{unit\_cost}_{p,j}\cdot Q_j + F_{p,j,c},
\mathrm{floor}_{p,j,c}
),
$$

where $Q_j$ is quantity and $F_{p,j,c}$ is the dispensing fee or channel fee component.

The selected channel is the channel with the lowest simulated fill OOP, subject to deterministic tie-breaking:

$$
c^\star_{p,j,k}
=
\operatorname{argmin}_{c\in\mathcal{C}_{p,j,k}}
OOP_{p,j,k,c}.
$$

In the top hybrid plan, all 39 fills selected preferred mail:

$$
\mathrm{channel\ mix}_{p_A}=\texttt{pref\_mail:39}.
$$

This generates a watchout because the beneficiary preference was `auto`, but the cheapest simulated path depended on mail order for all three medications.

### 8.6 Fill-level 2025 cost function

For a fill event $e=(p,j,k,c^\star)$, the 2025 simulation computes:

$$
O_{p,j,k}
=
f_{2025}
(
N_{p,j,k,c^\star},
D_{p,k-1},
A_{p,k-1},
\ell,
B_{p,j}
),
$$

where:

| Symbol | Meaning |
|---|---|
| $N_{p,j,k,c^\star}$ | negotiated-price proxy for selected channel |
| $D_{p,k-1}$ | remaining deductible before the fill |
| $A_{p,k-1}$ | accumulated annual OOP before the fill |
| $\ell$ | LIS status |
| $B_{p,j}$ | plan-drug basis and cost-sharing rule |

The base OOP before LIS is:

$$
BOP_{p,j,k}
=
\mathrm{deductible\ exposure}_{p,j,k}
+
\mathrm{initial\ coverage\ OOP}_{p,j,k}.
$$

The LIS-adjusted OOP is:

$$
LOP_{p,j,k}
=
A_{\ell}(BOP_{p,j,k}).
$$

For LIS status `none`, the adjustment is identity:

$$
A_{\ell=\mathrm{none}}(x)=x.
$$

The 2025 OOP cap is applied as:

$$
O_{p,j,k}
=
\begin{cases}
0, & A_{p,k-1}\ge 2000,\\
\min(LOP_{p,j,k},2000-A_{p,k-1}), & A_{p,k-1}<2000.
\end{cases}
$$

The accumulated OOP is updated after each fill:

$$
A_{p,k}
=
A_{p,k-1}+O_{p,j,k}.
$$

### 8.7 Worked fill: zero-OOP top hybrid plan

For top plan `H7849082000`, the first Jardiance fill had:

$$
N_{p_A,1,1}=514.23,
\quad
D_{before}=0.00,
\quad
A_{before}=0.00.
$$

The plan's cost-sharing rule produced:

$$
BOP_{p_A,1,1}=0.00.
$$

Because LIS status is `none`:

$$
LOP_{p_A,1,1}=0.00.
$$

The OOP cap does not bind:

$$
O_{p_A,1,1}
=
\min(0.00,2000.00-0.00)
=
0.00.
$$

The same pattern applied across all fills for the top plan, so:

$$
\mathrm{DrugOOP}_{s,p_A}
=
\sum_{j=1}^{3}\sum_{k=1}^{13}O_{p_A,j,k}
=
0.00.
$$

With annual premium:

$$
\mathrm{Premium}_{p_A}=0.00,
$$

annual total cost is:

$$
T_{s,p_A}
=
\mathrm{Premium}_{p_A}
+
\mathrm{DrugOOP}_{s,p_A}
=
0.00.
$$

### 8.8 Worked fill: nonzero deductible comparison plan

For plan `H5599004000`, the first Jardiance fill had:

$$
N_{p_B,1,1}=556.07,
\quad
D_{before}=420.00,
\quad
A_{before}=0.00.
$$

The deductible exposure was:

$$
\mathrm{deductible\ exposure}
=
\min(556.07,420.00)
=
420.00.
$$

The post-deductible negotiated remainder was:

$$
556.07-420.00=136.07.
$$

The initial-coverage OOP on the remainder was:

$$
\mathrm{initial\ coverage\ OOP}=0.00.
$$

Therefore:

$$
BOP_{p_B,1,1}
=
420.00+0.00
=
420.00.
$$

With LIS status `none`:

$$
LOP_{p_B,1,1}=420.00.
$$

The OOP cap does not bind:

$$
O_{p_B,1,1}
=
\min(420.00,2000.00-0.00)
=
420.00.
$$

After this fill:

$$
D_{after}=0.00,
\qquad
A_{after}=420.00.
$$

Later Jardiance fills had no remaining deductible and simulated final OOP of `0.00`, so:

$$
\mathrm{JardianceOOP}_{s,p_B}
=
420.00+12(0.00)
=
420.00.
$$

Entresto and gabapentin added no simulated OOP for this candidate:

$$
\mathrm{EntrestoOOP}_{s,p_B}=0.00,
\qquad
\mathrm{GabapentinOOP}_{s,p_B}=0.00.
$$

Thus:

$$
\mathrm{DrugOOP}_{s,p_B}
=
420.00.
$$

With annual premium:

$$
\mathrm{Premium}_{p_B}=0.00,
$$

annual total cost is:

$$
T_{s,p_B}=0.00+420.00=420.00.
$$

### 8.9 Coverage and priceability classification

For each plan, the coverage status is derived from the drug-level breakdowns. Let:

$$
K_{s,p}
=
\sum_{j=1}^{|M|}
\mathbf{1}\{\mathrm{drug}\ j\ \mathrm{is\ covered\ and\ priced}\}.
$$

The plan is full coverage when:

$$
K_{s,p}=|M|.
$$

For both `H7849082000` and `H5599004000`:

$$
K_{s,p}=3=|M|,
\qquad
\mathrm{coverage\_status}_{s,p}=\mathrm{full}.
$$

Both plans also had one utilization-management burden:

$$
H_{s,p}=1
\quad
\text{from quantity limits}.
$$

### 8.10 Rules score

The deterministic rules score is:

$$
R_{s,p}
=
10000\cdot\mathbf{1}\{\mathrm{coverage}_{s,p}=\mathrm{full}\}
-T_{s,p}
-250U_{s,p}
-35H_{s,p}
-20V_{s,p},
$$

where:

| Symbol | Meaning |
|---|---|
| $T_{s,p}$ | annual total cost |
| $U_{s,p}$ | uncovered-drug count |
| $H_{s,p}$ | restriction count |
| $V_{s,p}$ | network-priority penalty |

For top plan `H7849082000`:

$$
R_{s,p_A}
=
10000-0-250(0)-35(1)-20(0)
=
9965.
$$

For comparison plan `H5599004000`:

$$
R_{s,p_B}
=
10000-420-250(0)-35(1)-20(0)
=
9545.
$$

This explains the deterministic ranking difference: both plans are full coverage with one restriction and adequate network, but `H7849082000` has lower simulated total cost.

### 8.11 Scenario-specific rules ordering

The case was classified as:

$$
\mathrm{scenario\_profile}=\mathrm{specialty\_high\_cost}.
$$

For specialty-high-cost scenarios, the rules ordering uses the safety bucket first, then scenario-specific tie-breaks emphasizing restriction burden, channel switching, network priority, distance, total cost, and fit score.

The rules ordering can be summarized as:

$$
\pi^{rules}_{s}
=
\operatorname{sort}_{p\in\mathcal{P}(z)}
\left(
\beta(p),
-K_{s,p},
\mathrm{scenario\_sort}_{specialty}(p),
U_{s,p}
\right).
$$

Since both worked plans are full coverage and fully priceable:

$$
\beta(p_A)=\beta(p_B)=0.
$$

Total cost then helps separate them:

$$
T_{s,p_A}=0.00
<
T_{s,p_B}=420.00.
$$

### 8.12 Hybrid reranking

The hybrid model is applied only after the rules engine has produced candidate recommendation rows. The model receives a feature vector:

$$
x_{s,p}
=
[
T_{s,p},
\mathrm{DrugOOP}_{s,p},
\mathrm{Premium}_{p},
K_{s,p},
U_{s,p},
H_{s,p},
\mathrm{network}_{s,p},
\mathrm{match}_{s,p},
\mathrm{scenario}_{s},
\ldots
].
$$

The trained tree reranker estimates:

$$
\hat{W}_{s,p}=F_M(x_{s,p}).
$$

For the top hybrid plan:

$$
\hat{W}_{s,p_A}=10853.21.
$$

The constrained hybrid ordering is:

$$
\pi^{hybrid}_{s}
=
\bigcup_{b\in\{0,1,2\}}
\operatorname{sort}_{p:\beta(p)=b}
\left(
-\hat{W}_{s,p},
-K_{s,p},
-R_{s,p},
T_{s,p},
U_{s,p},
H_{s,p},
\mathrm{name}_p
\right).
$$

The bucket function is:

$$
\beta(p)=
\begin{cases}
0, & \mathrm{full\ coverage\ and\ all\ drugs\ priceable},\\
1, & \mathrm{at\ least\ one\ drug\ priceable},\\
2, & \mathrm{fallback\ or\ unpriceable}.
\end{cases}
$$

Because `H7849082000` is in bucket 0, it can be compared against other fully covered, fully priceable plans by model score. But a partially priceable or fallback plan cannot move above it solely because of model score.

### 8.13 Final output and explanation layer

The final top hybrid recommendation for this sample was:

| Output field | Value |
|---|---|
| Plan key | `H7849082000` |
| Plan name | Cigna True Choice Medicare (PPO) |
| Ranking source | `hybrid_reranker` |
| Coverage status | full |
| Priced drugs | 3 of 3 |
| Annual premium | 0.00 |
| Annual drug OOP | 0.00 |
| Annual total cost | 0.00 |
| Rules score | 9965.00 |
| Model score | 10853.21 |
| Model confidence bucket | high |
| Scenario profile | specialty_high_cost |
| Channel mix | `pref_mail:39` |
| Restriction summary | quantity limits |

The explanation layer is generated from the same evidence:

| Evidence | Explanation effect |
|---|---|
| All drugs covered and priced | Plan can appear in the full-coverage bucket |
| Quantity limits on all three drugs | Utilization-management watchout |
| Preferred mail selected for all 39 fills | Mail-order dependency watchout |
| Annual total cost 0.00 | Low-cost strength, subject to artifact caveat |
| Exact NDC matches | No medication-identity manual review needed |

The final interpretation is therefore:

$$
\text{Recommendation}
=
\text{service-area eligible}
+
\text{exact medication resolution}
+
\text{full coverage}
+
\text{fill-level cost simulation}
+
\text{rules-first safety ranking}
+
\text{within-bucket model reranking}
+
\text{explanation flags}.
$$

This is the core implementation claim: machine learning does not replace the plan-design and cost-simulation logic. It only reranks already simulated, explanation-bearing rows inside safety-preserving buckets.
