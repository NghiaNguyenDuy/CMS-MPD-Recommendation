# CMS-MPD Technical Data Flow And Modeling Method

## Overview

This document explains how `CMS-MPD-Recommendation` moves from local CMS source files to DuckDB serving tables, beneficiary-level recommendation outputs, synthetic or PDE-compatible training scenarios, hybrid reranking, and evaluation reports.

The project has four connected layers:

1. medallion data engineering in DuckDB
2. rules-first recommendation and explanation logic
3. synthetic scenario generation and ML dataset construction
4. ranking evaluation and research reporting

## 1. End-To-End Technical Flow

The operational sequence is:

1. `PipelineConfig` resolves input and output paths, build profile, snapshot quarter, DuckDB file path, model directory, and training directory.
2. `extract.py` expands CMS archives and locates reference files and RXCUI shards.
3. `pipeline.py` builds `bronze.*`, `silver.*`, and `gold.*` in order, and ensures the `synthetic` schema exists.
4. `recommend.py` reads serving data from `gold.*` plus selected lookup tables in `silver.*` and simulates plan-level annual cost for a beneficiary and medication list.
5. `scripts/generate_beneficiary_profiles.py` writes `synthetic.syn_beneficiary` and `synthetic.syn_beneficiary_prescriptions`.
6. `modeling.py` replays recommendation scenarios, builds feature rows, trains rerankers, and evaluates ranking systems.
7. `research_eval.py` converts the evaluation outputs into summary frames used by research mode.
8. `streamlit_app.py` wraps the same runtime logic in a counselor-first UI and can add nearby comparison-only plans by rerunning the core engine on nearby ZIP codes.

## 2. Configuration And Extraction

`PipelineConfig` is the canonical contract for both build and runtime. It controls:

- `build_profile`: `full` or `demo`
- `snapshot_quarter`
- `data_dir`
- `source_data_dir`
- derived paths such as `db_path`, `cms_root`, `reference_dir`, `rxcui_dir`, `model_dir`, and `training_dir`

`extract_sources()` returns a `SourcePaths` object containing:

- CMS archive outputs such as plan information, formulary, pricing, geography, exclusions, indication coverage, and beneficiary cost rules
- split pharmacy network files
- reference CSVs for insulin, ZIP geography, and PDE sample
- RXCUI property shards

Important extraction behavior:

- each CMS archive is expected to contain one member file
- extracted files are reused when already present
- RXCUI files are discovered by glob
- extraction writes to `data/staging/<snapshot>/raw`

## 3. Bronze Layer

The bronze layer preserves raw CMS and reference inputs with minimal transformation. Each bronze table carries lineage metadata:

- `source_file`
- `snapshot_quarter`
- `load_ts`

Bronze tables include:

- `bronze.plan_information`
- `bronze.basic_formulary`
- `bronze.beneficiary_cost`
- `bronze.insulin_beneficiary_cost`
- `bronze.pricing`
- `bronze.geographic_locator`
- `bronze.excluded_drugs`
- `bronze.indication_coverage`
- `bronze.pharmacy_network`
- `bronze.rxcui_properties`
- `bronze.insulin_reference`
- `bronze.us_zipcode_geo`
- `bronze.pde_sample`

Most bronze loads use permissive string ingestion to avoid schema breakage from CMS formatting variation. `bronze.pharmacy_network` is especially fault tolerant because split CMS files can contain malformed rows. Its loader uses relaxed parsing with null padding and ignored bad rows so the full build is not blocked by one corrupt line.

## 4. Silver Transformation Logic

The silver layer converts raw files into normalized business entities.

### 4.1 `silver.dim_plan`

Purpose:

- create a canonical plan dimension keyed by `plan_key`

Main logic:

- normalize `CONTRACT_ID`, `PLAN_ID`, `SEGMENT_ID`
- build `plan_key` and `contract_plan_key`
- keep a single representative row per plan with `row_number()`
- preserve `formulary_id`, monthly premium, deductible, MA or PDP region code, suppression flag, and plan type
- derive `service_area_type` as county-based or PDP-region-based

### 4.2 `silver.dim_zipcode`

Purpose:

- create a ZIP-level geography lookup for service-area mapping and distance estimation

Main logic:

- normalize ZIP code to five digits
- standardize county text and state abbreviation
- join ZIP geography to CMS county geography through normalized county and state names
- preserve lat/lng, population, density, county code
- derive `density_category` as `urban`, `suburban`, or `rural`

### 4.3 `silver.bridge_plan_service_area`

Purpose:

- map every plan to the counties it serves

Main logic:

- MA-style plans are taken directly from county rows in the plan information source
- PDP-style plans are expanded from `pdp_region_code` to all counties in the CMS geographic locator

### 4.4 `silver.build_plan_scope`

Purpose:

- restrict demo builds to ZIP-relevant plans while allowing full builds to include all plans

Main logic:

- in `demo` mode, find plans serving the configured demo ZIP codes
- in `full` mode, include all plans in `silver.dim_plan`

### 4.5 `silver.dim_drug_reference`

Purpose:

- create the canonical drug identity table used by the UI and recommendation engine

Main logic:

- union formulary NDC or RXCUI mappings with insulin reference mappings
- rank RXCUI property rows to choose the best preferred name
- favor unsuppressed English names and useful term types
- attach synonym, TTY, and `is_insulin`

### 4.6 `silver.drug_utilization_defaults`

Purpose:

- estimate quantity and annual fill defaults for medication input

Main logic:

- normalize PDE day supply into `30`, `60`, or `90`
- estimate `tier_family` from formulary tier or PDE generic-brand indicator
- calculate median quantity as `default_quantity`
- calculate annualized fill count as `default_fills_per_year`
- create both NDC-specific and fallback defaults

### 4.7 `silver.fact_plan_drug_coverage`

Purpose:

- create the normalized plan-drug fact table that combines formulary, price, and restriction behavior

Grain:

- `plan_key x ndc x days_supply`

Main logic:

- join plans to formulary rows through `formulary_id`
- join pricing rows by `plan_key`, NDC, and day supply
- derive `tier_level_value` and `tier_family`
- preserve `has_prior_auth`, `has_step_therapy`, `has_quantity_limit`
- preserve quantity limit amount and days
- flag exclusions and indication restrictions
- attach insulin flag from drug reference

### 4.8 `silver.fact_plan_pharmacy`

Purpose:

- normalize the pharmacy network into a plan-pharmacy fact used for channel and distance logic

Main logic:

- normalize plan key and pharmacy ZIP
- expose booleans for preferred retail, preferred mail, retail availability, mail availability, and in-area status
- carry dispensing fees and floor price
- join pharmacy ZIP geolocation and density from `silver.dim_zipcode`
- filter incomplete pharmacy rows

### 4.9 `silver.plan_beneficiary_cost_rules`

Purpose:

- normalize standard CMS beneficiary cost-sharing rules

Main logic:

- map CMS days-supply codes into 30, 60, 90
- expose deductible applicability
- preserve fixed-copay or coinsurance parameters for preferred retail, nonpreferred retail, preferred mail, and nonpreferred mail

### 4.10 `silver.plan_insulin_cost_rules`

Purpose:

- normalize insulin-specific channel copays

Main logic:

- map CMS days-supply codes into 30, 60, 90
- expose insulin override copays by channel and tier where available

## 5. Gold Serving Layer

The gold layer is the serving model for inference, UI workflows, and model dataset generation.

### 5.1 `gold.plan_service_area`

Purpose:

- derive eligible plans for each ZIP code

Built from:

- `silver.dim_zipcode`
- `silver.bridge_plan_service_area`
- `silver.dim_plan`

### 5.2 `gold.plan_channel_summary`

Purpose:

- summarize pharmacy access and fee behavior at the plan level

Built from:

- `silver.fact_plan_pharmacy`

Main outputs:

- counts of in-area pharmacies
- preferred and nonpreferred retail counts
- preferred and nonpreferred mail counts
- minimum floor prices and dispensing fees by channel and day supply
- availability booleans such as `has_pref_retail` and `has_pref_mail`

### 5.3 `gold.plan_preferred_pharmacy_locations`

Purpose:

- provide lat/lng points for preferred in-area retail pharmacies so nearest-distance estimates can be computed

### 5.4 `gold.plan_formulary_summary`

Purpose:

- calculate high-level formulary and restriction metrics per plan

Main outputs:

- `covered_drug_count`
- `insulin_drug_count`
- `formulary_breadth_pct`
- `generic_tier_pct`
- `specialty_tier_pct`
- `pa_rate`
- `st_rate`
- `ql_rate`
- `excluded_rate`
- `insulin_coverage_pct`
- `restrictiveness_class`

`restrictiveness_class` is derived from the combined PA, ST, and QL rates:

- `2` for highly restrictive plans
- `1` for moderately restrictive plans
- `0` for lower-restriction plans

### 5.5 `gold.plan_network_summary`

Purpose:

- compress channel counts into a simple network risk label

Network logic:

- `no_preferred_retail` when preferred retail count is `0`
- `limited_preferred_retail` when preferred retail count is less than `10`
- `adequate` otherwise

### 5.6 `gold.plan_drug_cost_basis`

Purpose:

- materialize the runtime-ready cost simulation table

Built from:

- `silver.fact_plan_drug_coverage`
- `silver.dim_drug_reference`
- `silver.plan_beneficiary_cost_rules`
- `silver.plan_insulin_cost_rules`

Main outputs:

- readable drug identity
- plan, NDC, RXCUI, day supply, tier, tier family
- observed `unit_cost`
- exclusion and insulin flags
- PA/ST/QL flags and quantity-limit values
- deductible applicability
- pre-deductible rule parameters by channel
- initial-coverage rule parameters by channel
- insulin override copays by channel

### 5.7 `gold.plan_summary`

Purpose:

- create a compact plan-level serving dimension

Main outputs:

- annual premium
- deductible
- service-area size through `served_counties`
- formulary breadth and restriction metrics

### 5.8 `gold.drug_input_defaults`

Purpose:

- expose medication defaults in the gold layer for runtime use

### 5.9 `gold.recommendation_features`

Purpose:

- provide plan-level feature inputs for model dataset construction and reranking

It combines:

- premium and deductible
- plan type and service area type
- service-area size
- formulary breadth and restriction rates
- network counts and `network_flag`

### 5.10 UI Views

The gold layer also exposes:

- `gold.ui_plan_drug_serving`
- `gold.ui_plan_comparison_base`

These are lightweight serving views for app and export workflows.

## 6. Synthetic And PDE-Compatible Scenario Flow

The project supports synthetic and PDE-derived beneficiary scenarios written into:

- `synthetic.syn_beneficiary`
- `synthetic.syn_beneficiary_prescriptions`

Synthetic generation without PDE:

- creates beneficiaries with risk segment, insulin-user flag, target drug count, and target annual fills
- assigns geography by sampling ZIP codes proportional to population
- samples drugs from a formulary pool weighted by plan coverage frequency
- forces insulin users to include at least one insulin when possible
- assigns day supply, quantity per fill, and annual cost using observed median `unit_cost` when available

PDE-derived generation:

- reads PDE events
- aggregates them to beneficiary x NDC summaries
- matches NDCs to the formulary drug pool
- derives readable drug names from RXCUI reference data
- aggregates regimen totals per beneficiary
- assigns ZIP geography using the ZIP pool

## 7. Runtime Recommendation Method

The main runtime function is `recommend_plans()`.

### 7.1 Input Normalization

Medication inputs are resolved in this order:

- exact NDC
- exact RXCUI
- exact preferred name
- exact synonym
- prefix name or synonym match

Then the engine:

- normalizes day supply to `30`, `60`, or `90`
- infers `tier_family` from observed plan-drug data when not provided
- fills missing quantity and fills-per-year from `gold.drug_input_defaults`

### 7.2 Candidate Plan Selection

The engine selects eligible plans from `gold.plan_service_area` for the beneficiary ZIP and joins:

- `gold.plan_summary`
- `gold.plan_network_summary`

This is the core service-area boundary for recommendation.

### 7.3 Runtime Fetches

For all candidate plans and requested drugs, the engine loads:

- `gold.plan_drug_cost_basis`
- `gold.plan_channel_summary`
- `gold.plan_preferred_pharmacy_locations`
- ZIP centroid coordinates from `silver.dim_zipcode`

## 8. Cost Simulation Logic

The cost engine is fill-level and rules-first.

### 8.1 Coverage States

For each plan-drug pair, the engine classifies the row as:

- `uncovered`
- `excluded`
- `missing_price`
- `covered`

Only covered drugs generate simulated fills.

### 8.2 Fill Expansion

For each covered drug:

- annual fills are expanded using resolved `fills_per_year`
- fills are spread across the year using `365 / fills_per_year`
- deductible and annual OOP accumulation are tracked across all fills

### 8.3 Channel Evaluation

For each fill, the engine tries:

- `pref_retail`
- `nonpref_retail`
- `pref_mail`
- `nonpref_mail`

Subject to:

- plan channel availability
- beneficiary pharmacy preference

The engine simulates every feasible channel and selects the cheapest OOP result for that fill.

### 8.4 Negotiated Price

Negotiated price is approximated as:

- `unit_cost * quantity + dispensing_fee`

Then floor price is applied:

- `negotiated = max(raw_price, floor_price)`

### 8.5 Standard Cost Rule Logic

The rule handler supports:

- fixed copay
- coinsurance percentage

It also respects rule minimums and maximums and never charges more than the negotiated price.

### 8.6 Deductible Logic

When deductible applies:

- the negotiated amount first consumes remaining deductible
- any remaining negotiated amount can then move into initial-coverage-style cost sharing

When deductible does not apply or is exhausted:

- the engine uses the appropriate standard rule directly

### 8.7 Insulin Logic

If the drug is insulin:

- insulin-specific override copays are used when available
- otherwise the engine falls back to standard initial-coverage-style rules

### 8.8 LIS And OOP Cap

After base OOP is computed:

- `full` LIS applies fixed caps by generic vs brand
- `partial` LIS discounts cost and then caps it
- annual accumulated OOP is stopped at the project’s annual OOP cap

### 8.9 Fill Trace

Each winning simulated fill stores:

- fill number
- day offset
- selected channel
- coverage phase
- negotiated price
- deductible before and after
- base OOP
- LIS-adjusted OOP
- final OOP
- OOP-cap flag

The plan aggregate then rolls up:

- annual drug OOP
- annual premium
- annual total cost
- uncovered drug count
- restriction count
- selected channel mix
- nearest preferred retail distance
- network and access summary

## 9. Explanation And Ranking Logic

The engine groups human-readable explanations into:

- coverage issues
- utilization-management issues
- insulin considerations
- pharmacy-access issues
- deductible issues
- cost-logic issues

Examples include:

- uncovered or excluded drugs
- prior authorization
- step therapy
- quantity limits
- deductible exposure
- LIS relief
- annual OOP-cap activation
- limited preferred retail access
- mail-order dependency

### 9.1 Rules Score

Each plan receives a deterministic `rules_score` that:

- strongly rewards full coverage
- penalizes annual total cost
- penalizes uncovered drugs
- penalizes restriction count
- penalizes worse `network_flag`

### 9.2 Fit Score

A second score, `fit_score`, is computed from:

- cost score
- premium score
- coverage score
- access score
- stability score

Weights are determined by:

- decision focus such as balanced, lowest total cost, coverage first, pharmacy access, or low friction
- user role such as beneficiary, caregiver, or counselor

The design intentionally prevents cheap but partial-coverage plans from dominating the ranking.

## 10. ML Dataset Construction

The ML dataset is generated by replaying recommendation scenarios, not by training directly on raw claims.

Scenario sources:

- `synthetic.*` when present
- otherwise default scenario bundles created from gold serving data

Each scenario:

1. calls `recommend_plans()` in rules mode
2. converts every recommended plan into one feature row
3. enriches those rows with plan-level data from `gold.recommendation_features`

Feature families include:

- current rules rank and score
- fit score and component scores
- annual premium, drug OOP, total cost
- coverage shares and uncovered counts
- restriction counts
- deductible, LIS-adjusted, and negotiated-price totals
- mail-order dependency
- insulin risk
- medication-match quality counts
- network flag and network risk score
- ZIP density and beneficiary context
- plan-level formulary and network metrics

## 11. Weak Labels, Models, And Hybrid Reranking

### 11.1 Weak Label Supervision

The system does not have observed beneficiary-choice targets. Instead it builds:

- `weak_label_score`
- `heuristic_score`

`weak_label_score` rewards:

- full coverage
- better rules score

and penalizes:

- annual total cost
- uncovered, excluded, missing-price, and channel-unavailable drugs
- restrictions
- approximate medication matches
- mail dependency
- insulin risk
- network risk

### 11.2 Feature Encoding

Model inputs are split into:

- numeric columns
- categorical columns

Encoding behavior:

- numeric columns are zero-filled and cast to float
- categorical columns are one-hot encoded
- inference frames are aligned to artifact feature names

Supported feature subsets:

- `cost_only`
- `cost_plus_restrictions`
- `cost_plus_restrictions_network`
- `full`

### 11.3 Linear Reranker

The linear model is ridge regression implemented directly with NumPy:

- standardize encoded features
- solve ridge regression with pseudoinverse
- persist means, scales, weights, intercept, and metadata

This acts as the transparent baseline ML reranker.

### 11.4 Tree Reranker

The tree model is a lightweight custom regression-tree ensemble:

- initialize from mean target value
- fit shallow regression trees to residuals
- add predictions with a learning rate

This behaves similarly to a small gradient-boosted regression ensemble and captures non-linear interactions among cost, coverage, access, and restriction signals.

### 11.5 Hybrid Inference

At inference:

1. the rules engine produces candidate recommendations
2. if an artifact exists, the system builds an inference feature frame
3. the artifact predicts `model_score`
4. plans are reranked within coverage strata

Important guardrails:

- full-coverage and partial-coverage plans are grouped separately
- rules score remains an important tie-breaker
- missing artifact means automatic fallback to rules-only ranking

## 12. Evaluation Method

The evaluation pipeline compares:

- `rules_only`
- `heuristic_baseline`
- `linear_reranker`
- `tree_reranker`

and, when requested, ablation tree models for:

- `cost_only`
- `cost_plus_restrictions`
- `cost_plus_restrictions_network`
- `full`

### 12.1 Ranking Truth Construction

Within each scenario:

- plans are ordered by `weak_label_score`
- that ordering becomes pseudo-ground-truth
- top positions are converted into graded relevance for NDCG-style metrics

### 12.2 Metrics

For each system and scenario, the evaluator computes:

- `top1_agreement`
- `top5_overlap`
- `top10_overlap`
- `ndcg_5`
- `ndcg_10`
- `top5_full_coverage_rate`
- `top10_full_coverage_rate`
- `top5_avg_total_cost`
- `top10_avg_total_cost`
- `top5_avg_uncovered`

### 12.3 Aggregation And Acceptance

Metrics are summarized:

- overall across all scenarios
- by scenario bundle

The report also records simple acceptance checks:

- whether top-5 overlap improved versus rules-only
- whether top-10 overlap improved versus rules-only
- whether uncovered drugs in the top-5 did not get worse

### 12.4 Research Reporting

`research_eval.py` converts evaluation outputs into:

- system summary frames
- scenario-bundle frames
- dataset diagnostics
- subgroup summaries by LIS, age, pharmacy preference, ZIP density, scenario bundle, and coverage status

## 13. Current Assumptions And Limits

Important constraints in the current version:

- snapshot assumptions are centered on CMS Q3 2025 local files
- distance is ZIP-centroid based, not route-time based
- nearby comparison-only plans are assembled in Streamlit, not the core engine
- ML supervision is weak-label based rather than outcome based
- evaluation is scenario replay, not prospective real-world validation
- the cost engine is an approximation built from CMS rule schedules and observed prices, not a claims adjudication system

## Summary

`CMS-MPD-Recommendation` is structured so that the same gold serving layer supports:

- counselor-facing recommendation workflows
- fill-level cost simulation
- synthetic and PDE-compatible scenario generation
- hybrid reranking
- evaluation and research reporting

The system is rules-first by design. Machine learning refines ranking order, but the authoritative logic for cost, coverage, access, and explanation remains in the DuckDB-backed recommendation engine.
