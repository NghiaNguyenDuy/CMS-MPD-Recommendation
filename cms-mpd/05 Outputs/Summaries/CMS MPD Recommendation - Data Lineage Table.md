---
title: CMS MPD Recommendation - Data Lineage Table
type: output/methods-table
status: draft
tags:
  - cms-mpd
  - output
  - methods
  - data-lineage
created: 2026-04-10
updated: 2026-04-10
aliases:
  - CMS MPD Data Lineage
related_notes:
  - "[[CMS MPD Recommendation - Research Flow, Data Logic, and Algorithm]]"
  - "[[CMS MPD Recommendation - Research Manuscript Draft]]"
  - "[[CMS MPD Recommendation - Journal Manuscript Draft]]"
  - "[[CMS MPD Source Processing Summary - 2026-04-07]]"
---

# CMS MPD Recommendation - Data Lineage Table

> [!note]
> This note condenses the project into a manuscript-style lineage table using the flow `Source -> Transformation -> Table -> Consumer -> Output`.

## One-Page Lineage Table

| Source                                                                                                                                                | Transformation                                                                                                                    | Table                                                                                                                                                                           | Consumer                                                                                                    | Output                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| CMS quarterly plan and geography files: `plan_information`, `geographic_locator`                                                                      | Canonicalize plan identifiers, contract year, premiums, deductibles, plan type, county and region mapping                         | `silver.dim_plan`, `silver.bridge_plan_service_area`, `silver.dim_zipcode`                                                                                                      | `gold.plan_summary`, `gold.plan_service_area` builders                                                      | Canonical plan identity and ZIP-level eligibility base                                       |
| CMS formulary file plus RXCUI shards and insulin reference                                                                                            | Normalize `ndc`, `rxcui`, preferred drug names, synonyms, and insulin flags                                                       | `silver.dim_drug_reference`                                                                                                                                                     | medication resolution in `recommend.py`, coverage basis builder                                             | Searchable medication identity layer for exact and reviewed matching                         |
| CMS beneficiary cost file and insulin beneficiary cost file                                                                                           | Normalize standard and insulin-specific cost-sharing rules by tier and day supply                                                 | `silver.plan_beneficiary_cost_rules`, `silver.plan_insulin_cost_rules`                                                                                                          | `gold.plan_drug_cost_basis` builder                                                                         | Executable cost-sharing rules for runtime fill simulation                                    |
| CMS pricing, formulary, excluded drug, and indication coverage files                                                                                  | Join coverage status, unit cost, utilization management, exclusions, and indication constraints at plan x drug x day-supply grain | `silver.fact_plan_drug_coverage`                                                                                                                                                | `gold.plan_drug_cost_basis`, `gold.plan_formulary_summary` builders                                         | Runtime-ready coverage and restriction facts                                                 |
| CMS pharmacy network files plus ZIP geography                                                                                                         | Normalize retail vs mail channels, preferred vs nonpreferred access, dispensing fees, floor prices, and pharmacy locations        | `silver.fact_plan_pharmacy`                                                                                                                                                     | `gold.plan_channel_summary`, `gold.plan_preferred_pharmacy_locations`, `gold.plan_network_summary` builders | Access, distance, and network-confidence layer                                               |
| ZIP-service mapping from normalized plan and geography tables                                                                                         | Expand service-area rules to ZIP-level eligible plan membership                                                                   | `gold.plan_service_area`                                                                                                                                                        | candidate-plan query in `recommend.py`                                                                      | Local ZIP-eligible plan set for each beneficiary                                             |
| Normalized drug defaults from PDE-based utilization patterns                                                                                          | Derive default quantity and annual fills when user input is incomplete                                                            | `silver.drug_utilization_defaults`, `gold.drug_input_defaults`                                                                                                                  | medication normalization in `recommend.py`                                                                  | Default regimen quantities for fill-event construction                                       |
| Gold serving tables: `plan_service_area`, `plan_drug_cost_basis`, `plan_channel_summary`, `plan_network_summary`, `plan_preferred_pharmacy_locations` | Resolve medication identity, simulate annual fills, apply deductible/LIS/insulin/OOP-cap logic, then rank plans                   | In-memory `PlanRecommendation` and `RecommendationBundle` objects                                                                                                               | CLI, Streamlit, counselor workflow, decision-support serializers                                            | Full-coverage shortlist, fallback shortlist, blockers, explanations, and tradeoff comparison |
| Recommendation outputs plus `gold.recommendation_features`                                                                                            | Convert ranked plans into scenario-level feature rows with weak labels and relevance targets                                      | `data/training/2025-Q3/full/hybrid_reranker_dataset.csv`                                                                                                                        | `train_hybrid_reranker`, `evaluate_hybrid_reranker`                                                         | Synced reranker dataset: `request_features_v4`, `research_v4`, `16116` rows, `300` scenarios |
| Training dataset with weak labels                                                                                                                     | Fit constrained linear and tree rerankers, then evaluate on held-out scenarios                                                    | `data/models/2025-Q3/full/hybrid_reranker_linear.json`, `data/models/2025-Q3/full/hybrid_reranker_tree.json`, `data/training/2025-Q3/full/hybrid_reranker_evaluation_tree.json` | hybrid inference path and research evaluation                                                               | Synchronized reranker artifacts and evaluation reports                                       |

## Reading Guide

- Raw operational truth enters from CMS quarterly files, reference CSVs, and RXCUI shards.
- Deterministic transformation happens in `bronze -> silver -> gold`.
- Counselor-facing outputs are produced from gold tables through fill-level simulation, not from a direct model score.
- Modeling artifacts are downstream research products built from recommendation outputs, not upstream source data.

## Current Synchronized State

> [!success]
> As of 2026-04-10, the local knowledge base reflects the rebuilt artifact state:
> - `data/cms_mpd.duckdb` rebuilt from staged `2025-Q3` raw files
> - training dataset rebuilt to `request_features_v4` / `research_v4`
> - linear and tree reranker artifacts retrained
> - evaluation report refreshed against the rebuilt dataset
