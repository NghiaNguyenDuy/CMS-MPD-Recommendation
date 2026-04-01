# CMS-MPD Project Description

## Overview

`CMS-MPD-Recommendation` is a counselor-first Medicare Part D recommendation platform built on a DuckDB medallion pipeline. It combines CMS plan, formulary, pricing, pharmacy-network, ZIP geography, and reference data into a reusable gold-layer serving model that powers plan comparison, cost simulation, Streamlit interaction, and research evaluation.

The project is designed to help users move from raw CMS files to practical decision support. Instead of only exposing plan data, it turns those inputs into beneficiary-centered recommendations with estimated annual out-of-pocket cost, annual premium, annual total cost, and plain-language explanations for important tradeoffs.

## Problem It Solves

Medicare Part D plan selection is difficult because the best plan depends on more than premium. A beneficiary or counselor often needs to understand:

- whether a plan covers the beneficiary's actual medications
- how cost sharing changes across tiers, deductible rules, and insulin protections
- whether the plan depends on preferred retail, non-preferred retail, or mail-order channels
- whether prior authorization, step therapy, or quantity limits may create friction
- whether a cheaper plan is still a worse fit once coverage and pharmacy access are considered

This project addresses that problem by combining a rules-first cost engine with a hybrid reranking workflow, then presenting the results in a way that is useful for beneficiaries, caregivers, counselors, navigators, and researchers.

## Intended Users

- beneficiaries comparing Part D plan options
- caregivers helping someone evaluate medication coverage and pharmacy access
- counselors and navigators supporting enrollment or annual review conversations
- researchers studying ranking behavior, subgroup performance, and plan recommendation logic

## What The System Does

The platform:

- ingests CMS SPUF quarterly plan, formulary, pharmacy, pricing, geography, exclusion, and cost-rule data
- normalizes those sources into medallion layers using DuckDB
- creates a gold serving layer for plan eligibility, formulary metrics, network access, and plan-drug cost simulation
- supports medication lookup by drug name, RXCUI, or NDC
- estimates annual out-of-pocket cost using deductible rules, channel-specific fees, insulin overrides, LIS adjustments, and the annual OOP cap
- ranks plans with deterministic rules-first logic and an optional hybrid machine-learning reranker
- returns top plan options with human-readable explanations about uncovered drugs, insulin risk, utilization management, deductible exposure, and pharmacy network limitations
- supports synthetic or PDE-derived beneficiary scenarios for modeling and research evaluation

## End-To-End Workflow

The project follows a full pipeline from source data to user-facing recommendation:

1. Raw CMS archives and reference files are extracted and loaded into `bronze.*`.
2. Reusable business entities such as plans, ZIPs, service areas, drug reference data, and cost rules are normalized into `silver.*`.
3. Runtime-ready serving tables are materialized in `gold.*`.
4. The recommendation engine resolves a beneficiary profile and medication list against eligible plans in the selected ZIP code.
5. The rules engine simulates per-fill and annual cost for each plan.
6. Plans are ranked and returned with explanation groups and access signals.
7. Training and research workflows build synthetic scenarios and evaluate hybrid reranking methods from the same serving layer.

## Product Experience

The Streamlit application is designed around a counselor workflow:

- profile intake for ZIP, LIS, age band, persona, conditions, and decision focus
- medication search and selection from the system drug catalog
- preference setting for cost, coverage, access, and comparison posture
- ranked results with side-by-side comparison, counselor notes, exports, and evidence-gap signals

This makes the system useful both as a decision-support tool and as a transparent discussion aid during beneficiary consultations.

## Technical Approach

The platform is intentionally opinionated:

- DuckDB is the core analytical engine
- medallion architecture separates ingestion, normalization, and serving concerns
- the rules engine remains the source of truth for cost and explanation behavior
- machine learning is used only to rerank already simulated candidate plans
- synthetic and PDE-compatible beneficiary data support reproducible training and evaluation
- the same serving layer is shared by CLI, Streamlit, and research workflows

## Key Outputs

For each recommendation request, the system can produce:

- estimated annual drug OOP
- annual premium
- estimated annual total cost
- plan ranking and fit score
- coverage status for requested medications
- restriction summary for PA, step therapy, and quantity limits
- network and pharmacy access summary
- insulin-specific warnings and deductible exposure notes
- exportable audit records for counselor review and downstream reporting

## Why This Project Matters

`CMS-MPD-Recommendation` is not only a data pipeline and not only a recommendation app. It is an end-to-end decision-support platform that turns complex CMS source data into structured, explainable, and research-friendly Medicare Part D recommendations.

Its value is in connecting three layers that are often separate:

- operational data engineering through a maintainable medallion architecture
- trustworthy recommendation logic through explicit cost and coverage simulation
- practical usability through a counselor-first interface and exportable recommendation outputs

## Current Scope

The current version is focused on:

- local CMS Q3 2025 source snapshots
- ZIP-centroid-based pharmacy distance estimation
- rules-first recommendation with optional hybrid reranking
- top plan comparison for beneficiaries and counselor workflows
- research evaluation using synthetic and PDE-derived scenarios

It is best understood as a strong technical and product foundation for a more advanced Medicare Part D recommendation platform.
