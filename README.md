# CMS-MPD-Recommendation

Counselor-first Medicare Part D recommendation platform built on a DuckDB medallion pipeline.

This project combines:

- the DuckDB extraction, build, rules engine, hybrid reranker, CLI, and smoke-test foundation from `Medicare-PartD-Recommendation`
- the counselor workflow, trust and evidence framing, synthetic PDE-compatible beneficiary generation, and research views from `CMS-Medicare-PartD-Recommendation`

The result is a new standalone project named `CMS-MPD-Recommendation` with package name `cms_mpd`.

Detailed technical reference:

- [Architecture And Lineage](docs/architecture-lineage.md)
- [Project Description](docs/project-description.md)
- [Technical Data Flow And Modeling Method](docs/technical-data-flow-modeling.md)

## What It Does

- ingests local CMS SPUF 2025 Q3 source files into `bronze.*`
- normalizes reusable entities into `silver.*`
- materializes `gold.*` serving assets for the recommendation engine, model dataset builder, and Streamlit app
- generates PDE-compatible synthetic beneficiaries into `synthetic.*`
- estimates annual premium, annual drug OOP, and annual total cost for plan comparison
- ranks top 5 or top 10 plans with rules-first logic and an optional hybrid reranker
- defaults to the 2025 redesigned Part D benefit for `2025-Q3` data and supports explicit `2024_standard` historical modeling when needed
- explains uncovered drugs, insulin risks, pharmacy access limits, PA/ST/QL restrictions, deductible exposure, and comparison-only status in human-readable language

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

## Synthetic Beneficiary Generation

Generate synthetic beneficiaries and prescriptions into the DuckDB `synthetic` schema:

```powershell
.venv\Scripts\python.exe scripts\generate_beneficiary_profiles.py --num-beneficiaries 250
```

Use PDE-derived scenarios:

```powershell
.venv\Scripts\python.exe scripts\generate_beneficiary_profiles.py --from-pde
```

## Hybrid Dataset and Model Workflow

Build the training dataset:

```powershell
.venv\Scripts\python.exe -m cms_mpd build-dataset
```

Train the tree reranker:

```powershell
.venv\Scripts\python.exe -m cms_mpd train-model --model-type tree --feature-subset full
```

Evaluate rules, heuristic baseline, and rerankers:

```powershell
.venv\Scripts\python.exe -m cms_mpd evaluate-model
```

Evaluation uses a held-out scenario split so the reported reranker metrics are measured on scenarios that were not used for fitting.

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
