# CMS-MPD-Recommendation

Counselor-first Medicare Part D recommendation and research platform built on a DuckDB medallion pipeline.

`CMS-MPD-Recommendation` studies how public CMS Part D plan-design data can be transformed into explainable, beneficiary-centered plan recommendations under incomplete observability. The project is not a generic recommender demo. It is a policy-aware software study that connects data engineering, deterministic benefit simulation, counselor-facing explanation, and constrained reranking evaluation.

This project combines:

- the DuckDB extraction, build, rules engine, hybrid reranker, CLI, and smoke-test foundation from `Medicare-PartD-Recommendation`
- the counselor workflow, trust and evidence framing, canonical mixed-source scenario generation, and research views from `CMS-Medicare-PartD-Recommendation`

The result is a new standalone project named `CMS-MPD-Recommendation` with package name `cms_mpd`.

Detailed technical reference:

- [Architecture And Lineage](docs/architecture-lineage.md)
- [Project Description](docs/project-description.md)
- [Study Research Flow, Data Logic, And Algorithm](docs/study-research-flow-data-logic-algorithm.md)
- [Technical Data Flow And Modeling Method](docs/technical-data-flow-modeling.md)
- [Sample Recommendation Result PDFs](docs/samples_recommendation/)
- [UI Simulation Screenshots](docs/UI_simulation/)

## Research Purpose

Medicare Part D plan selection is a high-dimensional decision problem. A beneficiary's best plan depends on geography, formulary coverage, utilization-management restrictions, pharmacy channel availability, deductible rules, insulin protections, low-income subsidy status, and the annual out-of-pocket structure introduced by the redesigned Part D benefit. A premium-only or generic recommender can therefore surface plans that look inexpensive while hiding coverage or access problems.

This repository frames the problem as decision-support research:

1. Build a reproducible public-data pipeline from quarter-frozen CMS Part D files.
2. Convert plan, formulary, drug, geography, pharmacy, and cost-rule data into auditable serving tables.
3. Simulate annual beneficiary liability at the fill and channel level before any learned model is used.
4. Generate explanation groups that a counselor can inspect, challenge, and export.
5. Evaluate whether constrained reranking improves the ordering of already simulated plan rows without hiding coverage, access, or missing-data risks.

The current study should be interpreted as research-ready decision support, not as an autonomous enrollment advisor. Public CMS plan-design files and restricted Prescription Drug Event data are not interchangeable; the local PDE-compatible layer is used for defaults and scenario construction, not as production beneficiary claims truth.

## Current Research Snapshot

The current full research artifact is aligned to the local `2025-Q3` CMS Part D snapshot.

| Area | Current artifact |
|---|---|
| Snapshot | `2025-Q3` full build |
| Benefit design | `auto`, resolving 2025-Q3 to `2025_redesign` |
| Training scenarios | 600 canonical mixed-source scenarios |
| Scenario source mix | 180 benchmark, 300 PDE-compatible, 120 stress |
| Scenario bundles | access-sensitive, insulin-chronic, low-utilizer, maintenance-generic, mixed-restriction, specialty-high-cost |
| Feature rows | 33,961 plan-scenario rows |
| Primary split | held out by scenario, with 420 train scenarios and 180 test scenarios |
| Best evaluated reranker | constrained tree reranker using student-safe features |
| Main ranking result | tree reranker top-1 agreement 0.861, top-5 overlap 0.934, NDCG@5 0.953 |
| Key caution | ranking agreement improved, but top-5 uncovered-drug burden still requires counselor-visible safety review |

The main methodological conclusion is deliberately restrained: constrained reranking can improve alignment with the study's weak-label preference structure, but ranking metrics must be interpreted alongside uncovered-medication burden, utilization restrictions, pharmacy-network status, missing-data indicators, and sample-level traces.

## What It Does

- ingests local CMS SPUF 2025 Q3 source files into `bronze.*`
- normalizes reusable entities into `silver.*`
- materializes `gold.*` serving assets for the recommendation engine, model dataset builder, and Streamlit app
- materializes canonical mixed-source training scenarios into `synthetic.*`
- estimates annual premium, annual drug OOP, and annual total cost for plan comparison
- ranks top 5 or top 10 plans with rules-first logic and an optional hybrid reranker
- defaults to the 2025 redesigned Part D benefit for `2025-Q3` data and supports explicit `2024_standard` historical modeling when needed
- explains uncovered drugs, insulin risks, pharmacy access limits, PA/ST/QL restrictions, deductible exposure, and comparison-only status in human-readable language
- stores reviewer-facing recommendation samples and UI workflow simulations under `docs/`

## Intended Users

- beneficiaries
- caregivers
- counselors and navigators
- researchers evaluating plan ranking behavior

## Project Layout

```text
CMS-MPD-Recommendation/
|-- data/
|   |-- staging/
|   |-- models/
|   |-- training/
|   `-- cms_mpd.duckdb
|-- scripts/
|   |-- generate_beneficiary_profiles.py
|   |-- recommend_plans.py
|   `-- run_pipeline.py
|-- src/cms_mpd/
|   |-- app_support.py
|   |-- config.py
|   |-- decision_support.py
|   |-- extract.py
|   |-- modeling.py
|   |-- pipeline.py
|   |-- recommend.py
|   |-- research_eval.py
|   `-- __main__.py
|-- docs/
|   |-- samples_recommendation/
|   |-- UI_simulation/
|   |-- architecture-lineage.md
|   |-- project-description.md
|   |-- study-research-flow-data-logic-algorithm.md
|   `-- technical-data-flow-modeling.md
|-- tests/
|-- requirements.txt
`-- streamlit_app.py
```

## Data Architecture

### Bronze

Raw ingested inputs with lineage metadata:

- CMS plan information, formulary, pricing, pharmacy network, geographic locator, excluded drug, and indication coverage files
- RXCUI property files
- insulin reference
- ZIP geography
- sample PDE file

### Silver

Normalized business entities:

- `silver.dim_plan`
- `silver.dim_zipcode`
- `silver.bridge_plan_service_area`
- `silver.dim_drug_reference`
- `silver.drug_utilization_defaults`
- `silver.fact_plan_drug_coverage`
- `silver.fact_plan_pharmacy`
- `silver.plan_beneficiary_cost_rules`
- `silver.plan_insulin_cost_rules`

### Gold

Runtime serving layer used by the model and app:

- `gold.plan_service_area`
- `gold.plan_formulary_summary`
- `gold.plan_channel_summary`
- `gold.plan_network_summary`
- `gold.plan_preferred_pharmacy_locations`
- `gold.plan_drug_cost_basis`
- `gold.plan_summary`
- `gold.drug_input_defaults`
- `gold.recommendation_features`
- `gold.ui_plan_drug_serving`
- `gold.ui_plan_comparison_base`

### Synthetic

Synthetic research and training support:

- `synthetic.syn_beneficiary`
- `synthetic.syn_beneficiary_prescriptions`
- `synthetic.training_scenarios`
- `synthetic.training_scenario_medications`
- `synthetic.training_scenario_manifest`

## Input Contracts

### `PipelineConfig`

Canonical runtime and build config:

- `data_dir`
- `source_data_dir`
- `snapshot_quarter`
- `build_profile` as `full` or `demo`

The project writes outputs into its own `data/` directory while still being able to read raw CMS files from sibling project folders.

### `BeneficiaryInput`

- `zipcode`
- `age_band`
- `lis_status`
- `chronic_condition_flags`
- `pharmacy_preference`
- `user_role`
- `decision_focus`
- `top_n`

### `MedicationInput`

- one of `drug_name`, `rxcui`, or `ndc`
- `tier_family`
- `day_supply`
- optional `quantity_override`
- optional `fills_per_year_override`

### `PlanRecommendation`

The recommendation contract includes:

- annual premium
- estimated annual OOP
- annual total cost
- coverage status
- selected channel mix
- network and access summary
- nearest preferred pharmacy distance
- grouped explanations
- `rules_score`
- `model_score`
- `ranking_source`
- `feature_version`

### `RecommendationAudit`

Stable export contract for the Streamlit workflow:

- run id
- generation timestamp
- model version
- data snapshot
- input summary
- feature coverage summary
- top-k outputs, including `contract_year` and `benefit_design` for each exported recommendation

## Source Data

Expected source folders:

- `Medicare-PartD-Recommendation/data/Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information/2025-Q3/`
- `Medicare-PartD-Recommendation/data/rxcui_info/`
- `Medicare-PartD-Recommendation/data/references_data/insulin_ref.csv`
- `Medicare-PartD-Recommendation/data/references_data/us_zipcode_geo.csv`
- `Medicare-PartD-Recommendation/data/references_data/pde.csv`

By default `PipelineConfig` checks, in order:

1. `CMS-MPD-Recommendation/data`
2. sibling `Medicare-PartD-Recommendation/data`
3. sibling `CMS-Medicare-PartD-Recommendation/data`

You can override both output and source roots with environment variables or CLI flags.

## Environment Variables

- `CMS_MPD_BUILD_PROFILE`
- `CMS_MPD_DEMO_ZIPCODES`
- `CMS_MPD_DATA_DIR`
- `CMS_MPD_SOURCE_DATA_DIR`
- `CMS_MPD_BENEFIT_DESIGN_MODE` (`auto`, `2025_redesign`, or `2024_standard`)

Example:

```powershell
$env:CMS_MPD_BUILD_PROFILE = "demo"
$env:CMS_MPD_DEMO_ZIPCODES = "43004,43005"
```

## Setup

```powershell
.venv\Scripts\Activate.ps1
.venv\Scripts\pip.exe install -r requirements.txt
$env:PYTHONPATH = "src"
```

## Build the Database

Full build:

```powershell
.venv\Scripts\python.exe -m cms_mpd build
```

Demo build:

```powershell
.venv\Scripts\python.exe -m cms_mpd build --build-profile demo --demo-zipcode 43004
```

Explicit source/output roots:

```powershell
.venv\Scripts\python.exe -m cms_mpd build `
  --data-dir ".\\data" `
  --source-data-dir "..\\Medicare-PartD-Recommendation\\data"
```

Build outputs:

- database: `data/cms_mpd.duckdb` or `data/cms_mpd_demo.duckdb`
- manifest: `data/staging/2025-Q3/manifest.json`
- staged raw extracts: `data/staging/2025-Q3/raw/`

## Recommendation CLI

```powershell
.venv\Scripts\python.exe -m cms_mpd recommend `
  --benefit-design-mode auto `
  --zipcode 43004 `
  --age-band 65-74 `
  --lis-status none `
  --pharmacy-preference auto `
  --user-role counselor `
  --decision-focus coverage_first `
  --ranking-mode rules `
  --top-n 5 `
  --condition-flag diabetes `
  --medication-json "[{\"drug_name\":\"insulin glargine\",\"tier_family\":\"brand\",\"day_supply\":30}]"
```

PowerShell-friendly alternative:

```powershell
.venv\Scripts\python.exe -m cms_mpd recommend `
  --zipcode 43004 `
  --medication-file ".\\medications.json"
```

## Scenario Generation

Legacy beneficiary generation remains available for raw-support tables:

```powershell
.venv\Scripts\python.exe scripts\generate_beneficiary_profiles.py --num-beneficiaries 250
```

Use PDE-derived scenarios:

```powershell
.venv\Scripts\python.exe scripts\generate_beneficiary_profiles.py --from-pde
```

Canonical training scenarios are now first-class:

```powershell
.venv\Scripts\python.exe -m cms_mpd generate-scenarios `
  --scenario-source-strategy mixed `
  --target-scenario-count 600 `
  --generator-seed 42 `
  --refresh-scenarios
```

## Hybrid Dataset and Model Workflow

Build the training dataset from canonical scenarios:

```powershell
.venv\Scripts\python.exe -m cms_mpd build-dataset `
  --scenario-source-strategy mixed `
  --target-scenario-count 600 `
  --generator-seed 42 `
  --max-workers 4 `
  --chunk-size 10 `
  --stale-chunk-hours 6
```

The dataset build is now ZIP-grouped, chunked, and resumable. Intermediate chunk files are written under `data/training/<snapshot>/<profile>/hybrid_reranker_dataset.chunks/`, so if a long run is interrupted you can resume with the same command instead of losing completed work. Use `--no-resume-chunks` only when you intentionally want to rebuild the chunk set from scratch. Stale `started` chunks are cleaned up after the configured `--stale-chunk-hours` threshold.

Train the tree reranker with the default student-safe feature policy:

```powershell
.venv\Scripts\python.exe -m cms_mpd train-model `
  --model-type tree `
  --feature-subset full `
  --teacher-feature-policy student_safe
```

Evaluate rules, heuristic baseline, and rerankers across scenario, ZIP, and regimen-held-out splits:

```powershell
.venv\Scripts\python.exe -m cms_mpd evaluate-model `
  --teacher-feature-policy student_safe
```

Evaluation reports all three split modes:

- held-out by scenario
- held-out by beneficiary ZIP
- held-out by regimen signature

Generated assets live under:

- `data/models/<snapshot>/<profile>/`
- `data/training/<snapshot>/<profile>/`

## Streamlit Workflow

Run:

```powershell
.venv\Scripts\streamlit.exe run streamlit_app.py
```

The app supports two modes:

- `Decision Support`
- `Research / Evaluation`

### Decision Support

Four-step counselor workflow:

1. profile
2. medications
3. preferences
4. results

Results include:

- eligible shortlist
- nearby comparison-only plans
- side-by-side plan comparison
- counselor note
- visible trust and evidence gaps
- CSV export
- JSON audit export

### Research / Evaluation

Research mode surfaces:

- system-level summary across rules, heuristic baseline, linear reranker, and tree reranker
- scenario-bundle slices
- subgroup summaries
- downloadable dataset and evaluation report

## Stored Result Artifacts

The repository includes a small reviewer-facing result package under `docs/`. These artifacts are intended to make the research workflow inspectable without requiring a full local rebuild.

### Sample Recommendation PDFs

The `docs/samples_recommendation/` folder stores eight generated recommendation examples. These are concrete retrieval probes rather than aggregate metrics; each one shows how the system handles a different beneficiary-like medication and access profile.

| Case | Stored result | What it demonstrates |
|---|---|---|
| Case 1 | [maintenance generic](docs/samples_recommendation/case_1_maintenance_generic.pdf) | Low-friction maintenance medications and stable full-coverage ranking. |
| Case 2 | [insulin chronic](docs/samples_recommendation/case_2_insulin_chronic.pdf) | Insulin and GLP-1 style therapy with insulin-specific cost and restriction signals. |
| Case 3 | [specialty high cost](docs/samples_recommendation/case_3_specialty_high_cost.pdf) | High-cost specialty and anticoagulant therapy, where coverage and network tradeoffs become more visible. |
| Case 4 | [low utilizer](docs/samples_recommendation/case_4_low_utilizer.pdf) | Single-drug low-utilization use case with simple recommendation behavior. |
| Case 5 | [access sensitive](docs/samples_recommendation/case_5_access_sensitive.pdf) | Retail-access-sensitive request where pharmacy channel and preferred network evidence matter. |
| Case 6 | [mixed restriction](docs/samples_recommendation/case_6_mixed_restriction.pdf) | Multi-drug cardiometabolic regimen with utilization-management burden. |
| Case 7 | [mixed restriction with LIS](docs/samples_recommendation/case_7_mixed_restriction_lis.pdf) | Same style of restriction-heavy regimen under full low-income subsidy assumptions. |
| Case 8 | [specialty high-cost stress](docs/samples_recommendation/case_8_specialty_high_cost_stress.pdf) | Sparse-coverage specialty stress case used to expose recommendation and evidence-gap behavior. |

Together, the PDFs complement the aggregate evaluation. They show the visible plan rows, coverage status, cost estimates, restrictions, network notes, and counselor-facing watchouts that explain why a recommendation is useful or risky.

### UI Simulation Screenshots

The `docs/UI_simulation/` folder stores a four-step Streamlit walkthrough of the counselor workflow.

| Step | Screenshot | Workflow stage |
|---|---|---|
| 1 | [input profile](docs/UI_simulation/1-input-profile.jpeg) | Beneficiary ZIP, LIS status, age band, role, conditions, and decision focus. |
| 2 | [input medications](docs/UI_simulation/2-input-medications.jpeg) | Medication search, selection, and request construction. |
| 3 | [select preferences](docs/UI_simulation/3-select-preferences.jpeg) | Ranking posture, pharmacy preference, and comparison settings. |
| 4 | [run system](docs/UI_simulation/4-run-system.jpeg) | Recommendation execution, top-plan output, comparison, and export path. |

These screenshots document the current product surface for the research artifact. They are useful when reviewing the manuscript, explaining the system to collaborators, or checking that the implementation still matches the counselor-first workflow described in the docs.

## Testing

Run the project tests with:

```powershell
.venv\Scripts\pytest.exe -q
```

Coverage includes:

- extraction smoke tests
- build and recommendation smoke tests
- gold-layer contract checks
- synthetic and hybrid dataset checks
- audit/export helper tests
- app workflow helper tests

## Current Modeling Assumptions

- CMS source snapshot is local SPUF `2025-Q3`
- `benefit_design_mode=auto` resolves `2025-Q3` plans to `2025_redesign`; `2024_standard` is available only for historical or what-if use
- distance is ZIP-centroid based
- PDE data is used for defaults and research scenarios, not production beneficiary truth
- rules remain the source of truth for OOP, deductible, LIS, insulin cap handling, uncovered drugs, and channel choice
- the hybrid reranker only reorders the eligible candidate set
- evaluation reports are based on a scenario-level held-out split rather than in-sample scoring
- nearby out-of-area plans may be shown for comparison but are never returned as eligible recommendations
