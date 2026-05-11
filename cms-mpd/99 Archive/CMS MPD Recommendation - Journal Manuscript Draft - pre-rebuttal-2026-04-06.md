---
title: CMS MPD Recommendation - Journal Manuscript Draft
type: output/manuscript
status: draft
tags:
  - cms-mpd
  - output
  - manuscript
  - journal-draft
  - project-review
created: 2026-04-06
related_notes:
  - "[[CMS MPD Recommendation - Research Manuscript Draft]]"
  - "[[Source Index]]"
  - "[[Topic Map - Medicare Plan Knowledge]]"
---

# CMS-MPD-Recommendation: An Explainable Counselor-Oriented Medicare Part D Decision-Support System Using Rules-First Cost Simulation and Hybrid Reranking

## Abstract

**Background:** Medicare Part D plan selection remains difficult because beneficiary welfare depends on medication-specific coverage, utilization-management restrictions, pharmacy-channel access, low-income subsidy status, and policy-year benefit rules rather than premium alone [1-6].  
**Objective:** To evaluate `CMS-MPD-Recommendation` as a counselor-oriented Medicare Part D decision-support and research platform grounded in curated policy knowledge and implemented as an end-to-end local analytical system.  
**Materials and Methods:** This manuscript synthesizes the reviewed knowledge base in the `cms-mpd` Obsidian vault with a local codebase review of the `CMS-MPD-Recommendation` project, including architecture documentation, runtime logic, model-building workflow, and refreshed evaluation artifacts regenerated on April 6, 2026 [7-11].  
**Results:** The system ingests local CMS SPUF 2025-Q3 files and reference data, builds a DuckDB medallion serving layer, simulates plan-specific fill-level out-of-pocket costs, surfaces counselor-readable explanations, and optionally reranks candidate plans using a hybrid model trained on synthetic and PDE-compatible scenarios. The regenerated evaluation dataset contains 1,774 plan rows across 32 scenarios, with a held-out-by-scenario split of 22 training scenarios and 10 test scenarios [10,11]. In the refreshed report, the tree reranker improved top-1 agreement from 0.60 under rules-only ranking to 1.00, improved top-10 overlap from 0.88 to 0.97, and did not worsen average uncovered drugs in the top 5, which remained 0.10 [11].  
**Conclusions:** `CMS-MPD-Recommendation` is a strong research and product foundation for counselor-facing Medicare Part D decision support. Its principal strength is the integration of policy-aware cost simulation, explanation-first ranking, and research instrumentation. However, current validation remains internal and weak-label based, so observed gains should be interpreted as evidence of internal coherence rather than external beneficiary-outcome validity.

**Keywords:** Medicare Part D; clinical decision support; SHIP counseling; formulary analytics; cost simulation; hybrid reranking; explainable recommendation

## 1. Introduction

Medicare Part D plan selection is a beneficiary-specific decision problem rather than a conventional consumer price-comparison task. The practical question is not merely which plan has the lowest premium, but which plan best fits a beneficiary's actual medication list, pharmacy usage, subsidy status, and tolerance for access friction. The reviewed knowledge base in this vault shows that beneficiaries frequently struggle to identify cost-effective plans, often misinterpret plan details, and benefit materially from guided decision support and neutral counseling infrastructure [1,2].

This problem has become more policy sensitive in the period from January 1, 2024 through January 1, 2026. The prepared notes document that the catastrophic 5 percent beneficiary coinsurance ended in 2024, that the 2025 redesign introduced a $2,000 annual out-of-pocket cap, and that subsequent indexed increases changed the cost environment again for 2026 [3]. The same note set also shows that insulin affordability, Extra Help eligibility, and formulary or pricing distortions remain critical determinants of real beneficiary burden even under the redesigned framework [3-6].

The present project, `CMS-MPD-Recommendation`, attempts to address this environment by combining a rules-first recommendation engine with a counselor-facing interface and a research workflow for hybrid reranking [7-9]. The aim of this manuscript is not to present a prospective clinical trial or claims-validated production system. Rather, it is to present a rigorous project review and manuscript-style synthesis of a local Medicare Part D decision-support platform informed by a curated policy and evidence vault.

## 2. Background

Three strands of prior evidence motivate the project design.

First, beneficiary choice quality is often poor under unaided plan selection. The reviewed source synthesis on plan selection and decision support indicates that beneficiaries frequently fail to enroll in the most cost-effective plans and that alternative decision-support interfaces can improve plan choice quality and user satisfaction [1].

Second, SHIP counseling functions as a critical operational bridge between policy complexity and practical enrollment advice. The prepared knowledge in the vault frames SHIP as neutral, local, and workflow oriented, with counselors routinely translating prescriptions, pharmacy preferences, LIS questions, and misinformation into actual plan decisions [2]. This implies that a useful Part D tool should support dialogue, explanation, and case review, not only score optimization.

Third, formulary and affordability signals in Part D are often counterintuitive. The reviewed notes on insulin affordability, pricing distortions, and formulary dynamics show that out-of-pocket exposure can vary substantially even when drugs are nominally covered, that generic drugs do not always produce lower beneficiary costs, and that policy reforms have changed but not eliminated plan-level heterogeneity [3-6]. These conditions favor explicit plan-level simulation over coarse or premium-dominant heuristics.

## 3. Objective

The objective of this manuscript is to assess whether `CMS-MPD-Recommendation` constitutes a coherent counselor-oriented and research-usable Part D recommendation platform. Specifically, the review examines:

1. whether the system architecture supports transparent movement from local CMS source files to beneficiary-facing recommendation outputs;
2. whether the recommendation logic is appropriately grounded in policy-aware, medication-level cost and coverage simulation;
3. whether the hybrid reranking workflow improves internal ranking quality without degrading coverage safety signals; and
4. whether the current evidence justifies describing the project as a research foundation rather than a completed validated recommendation product.

## 4. Materials and Methods

### 4.1 Knowledge Base

The manuscript is grounded in the reviewed knowledge stored in the `cms-mpd` Obsidian vault. The principal evidence notes used for this synthesis are the source notes on plan selection and decision support, SHIP counseling and navigation, Part D reform and IRA timeline, Extra Help operations, insulin affordability, and drug-pricing or formulary distortions [1-6]. These notes distill the vault's imported PDFs, web captures, and policy summaries into stable topic knowledge.

### 4.2 Project Materials

The project review covered the main repository documentation, architecture description, technical data-flow description, local training metadata, and regenerated evaluation artifacts [7-11]. The review also included direct inspection of the runtime recommendation module, modeling workflow, research helper module, CLI entry point, and Streamlit application, along with a focused local test run covering extraction, pipeline behavior, benefit-phase logic, recommendation realism, and decision-support export contracts.

### 4.3 System Architecture

The system is implemented as a DuckDB medallion architecture with `bronze`, `silver`, `gold`, and `synthetic` schemas [7-9]. Raw CMS SPUF plan, formulary, pricing, pharmacy-network, geography, exclusion, and beneficiary-cost files are ingested into `bronze.*`. These are normalized into reusable business entities in `silver.*`, including plan dimensions, ZIP geography, service areas, drug reference entities, plan-drug coverage facts, pharmacy facts, and cost-rule tables. Runtime-serving tables are then materialized in `gold.*`, including plan service areas, formulary summaries, network summaries, plan-drug cost basis, and recommendation feature views [8,9].

This architecture is appropriate for the problem because it separates ingestion, normalization, and serving concerns while keeping lineage visible. It also enables the same serving model to support recommendation, UI comparison, synthetic scenario generation, and research evaluation.

### 4.4 Recommendation Method

At inference time, the recommendation engine accepts beneficiary ZIP code, age band, LIS status, chronic-condition flags, pharmacy preference, user role, decision focus, and a medication list. Medication identity can be resolved by NDC, RXCUI, preferred name, synonym, or prefix match [9]. Candidate plans are restricted to the beneficiary service area, then joined to the plan summary, network summary, and plan-drug cost basis tables.

The engine performs fill-level simulation rather than plan-level approximation. For each drug and feasible channel, it estimates negotiated price, applies floor price and dispensing-fee logic, handles deductible exposure, respects insulin-specific overrides, applies LIS adjustments, and enforces the annual out-of-pocket cap when relevant [7,9]. The reviewed regression tests confirm explicit support for both `2025_redesign` and `2024_standard` benefit modes, which is important because the curated knowledge base contains both historical and current policy evidence.

### 4.5 Explanation and Ranking Logic

The rules engine groups human-readable explanation content into coverage issues, utilization-management issues, insulin considerations, pharmacy-access issues, deductible issues, and cost-logic issues [9]. This structure aligns closely with SHIP-style counseling workflows described in the vault notes [2].

Initial ranking is deterministic and coverage aware. Rules scoring rewards full coverage and penalizes uncovered drugs, restrictions, network risk, and higher total cost. A separate fit score incorporates role- and preference-sensitive weighting, allowing the system to present results differently for beneficiaries, caregivers, and counselors [7,9]. Machine learning is therefore not the primary source of recommendation truth; it is an optional reranking layer applied after plan simulation.

### 4.6 Hybrid Reranking and Evaluation

The modeling workflow generates scenario-level training rows by replaying recommendation scenarios, not by fitting directly on beneficiary enrollment outcomes [9-11]. Scenario sources include synthetic and PDE-compatible profiles, and the resulting dataset records weak-label scores, heuristic scores, cost and access features, coverage burden, and plan-level recommendation features [10].

The refreshed evaluation report generated on April 6, 2026 uses dataset schema version `request_features_v4`, weak-label version `weak_label_v2`, and a held-out-by-scenario train-test split with seed `42` and test fraction `0.3` [11]. Under this design, the model is evaluated on scenarios not used for fitting, which is methodologically stronger than in-sample scoring, but the target remains pseudo-ground truth derived from internal weak-label logic.

## 5. Results

### 5.1 System Capabilities

The reviewed codebase demonstrates that the platform supports:

1. ingestion of local CMS SPUF 2025-Q3 data and reference files into a structured serving model;
2. medication-level recommendation through CLI and Streamlit interfaces;
3. fill-level cost simulation with deductible, insulin, channel, LIS, and cap logic;
4. counselor-oriented explanatory outputs and exportable audit records; and
5. synthetic-scenario generation, hybrid reranker training, and held-out evaluation [7-11].

Taken together, these features indicate that the project is not a loose prototype but an integrated analytical application with a shared runtime and research core.

### 5.2 Evaluation Metrics

The refreshed evaluation artifact contains 1,774 plan rows across 32 scenarios, split into 1,255 training rows from 22 scenarios and 519 test rows from 10 scenarios [10,11]. Within this held-out-by-scenario framework:

- `rules_only` achieved top-1 agreement of 0.60, top-10 overlap of 0.88, NDCG@5 of 0.893, and top-5 average total cost of 61.352 [11].
- `heuristic_baseline` improved top-1 agreement to 0.70 and reduced top-5 average total cost to 56.792 [11].
- `linear_reranker` achieved top-1 agreement of 0.80 and NDCG@5 of 0.924 [11].
- `tree_reranker` achieved top-1 agreement of 1.00, top-5 overlap of 1.00, top-10 overlap of 0.97, and NDCG@5 and NDCG@10 of 1.00 [11].

Top-5 full-coverage rate remained 0.90 across all reported systems, and top-5 average uncovered drugs remained 0.10 for the reranker outputs [11]. The refreshed acceptance checks recorded `top5_improved = true`, `top10_improved = true`, and `uncovered_not_worse = true` [11].

### 5.3 Verification Findings

A focused local verification pass during this manuscript preparation passed 26 of 27 selected tests. Passing tests covered pipeline smoke behavior, recommendation realism, benefit-phase regression logic, and decision-support export contracts. The single failure occurred in extraction setup because the sandbox's default `data/rxcui_info` directory did not contain the expected local RXCUI files, making the failure environment dependent rather than a direct logic contradiction. This finding supports the conclusion that the project is internally coherent but still sensitive to local source-layout assumptions.

## 6. Discussion

The central finding of this review is that `CMS-MPD-Recommendation` is strongest when interpreted as an explainable counselor-support system with research instrumentation. The project is well aligned with the evidence base summarized in the vault. The literature and policy notes emphasize that beneficiaries require guided interpretation, that SHIP-style workflows depend on medication-specific and pharmacy-specific analysis, and that post-IRA Part D policy demands explicit date-aware modeling [1-4]. The reviewed architecture and runtime logic satisfy those demands more directly than a premium-led or generic recommendation approach would.

The system also shows disciplined separation between rules and learning. Cost, coverage, insulin, subsidy, and explanation logic remain under explicit rules control, while machine learning is limited to reranking simulated candidate plans [7-9]. This is a sound design decision in a high-stakes benefit-selection context because it constrains the role of learned behavior and preserves auditable reasoning.

At the same time, the evaluation results must be interpreted conservatively. The near-perfect tree reranker performance almost certainly reflects strong fit to the internally generated feature space and weak-label structure rather than definitive evidence of superiority in real beneficiary counseling or enrollment outcomes. The results therefore support claims about internal consistency and modeling potential, but not yet claims about external effectiveness.

## 7. Limitations

This review identified six principal limitations.

1. The study does not introduce a novel generic recommendation architecture; its contribution is domain-specific integration and explainable decision-support design.
2. The evaluation target used for model training and evaluation is weak-label based rather than based on observed beneficiary choice, adherence, or health outcomes [10,11].
3. Scenario generation is synthetic or PDE compatible, not derived from expert-adjudicated counseling cases or real beneficiary switching records [9-11].
4. Distance and pharmacy-access burden are approximated from ZIP centroids rather than travel-time or pharmacy-level utilization data [7,9].
5. The cost engine is an analytical approximation of plan behavior, not a production claims-adjudication engine [7,9].
6. The current manuscript relies on prepared internal knowledge notes rather than a fully externalized formal bibliography, although those notes themselves synthesize multiple imported policy and research sources [1-6].
7. Reproducibility still depends on disciplined local data management. During this review, the evaluation artifact had to be regenerated on April 6, 2026 to align the stored report with the current code path and schema version [11].

## 8. Conclusion

`CMS-MPD-Recommendation` represents a credible and technically disciplined foundation for counselor-oriented Medicare Part D decision support. The project integrates curated policy knowledge, explainable cost simulation, beneficiary-specific ranking, and research evaluation within a single local architecture. Its main contribution is not the presence of a reranker in isolation. Rather, its contribution is the combination of rules-first affordability logic, workflow-sensitive explanation, and research-ready instrumentation.

The present evidence supports describing the project as a strong research and product foundation. It does not yet support describing it as externally validated or outcome proven. Future work should prioritize comparison against expert-adjudicated counseling cases, direct benchmarking against live Plan Finder outputs, and validation against beneficiary-relevant outcomes.

## References

1. `Source - Plan Selection and Decision Support Evidence`. Reviewed source note in the `cms-mpd` vault synthesizing evidence on Medicare Part D plan selection, usability, counseling support, and Plan Finder limitations. [[Source - Plan Selection and Decision Support Evidence]]
2. `Source - SHIP Counseling and Beneficiary Navigation`. Reviewed source note in the `cms-mpd` vault summarizing SHIP counseling operations, barriers, and navigation workflows. [[Source - SHIP Counseling and Beneficiary Navigation]]
3. `Source - Part D Reform and IRA Timeline`. Reviewed source note in the `cms-mpd` vault summarizing staged Part D redesign from 2023 through 2026. [[Source - Part D Reform and IRA Timeline]]
4. `Source - Extra Help and LIS Operations`. Reviewed source note in the `cms-mpd` vault summarizing SSA and CMS operational handling of the Part D Low-Income Subsidy. [[Source - Extra Help and LIS Operations]]
5. `Source - Insulin Affordability in Part D`. Reviewed source note in the `cms-mpd` vault summarizing insulin affordability, coverage, and policy changes in Part D. [[Source - Insulin Affordability in Part D]]
6. `Source - Drug Pricing and Formulary Distortions`. Reviewed source note in the `cms-mpd` vault summarizing beneficiary price-signal distortions, formulary variation, and related pricing issues. [[Source - Drug Pricing and Formulary Distortions]]
7. `CMS-MPD-Recommendation README`. Local repository overview of project scope, architecture, user workflows, and modeling assumptions. [README](../../../README.md)
8. `CMS-MPD Architecture And Lineage`. Local project architecture and lineage document. [architecture-lineage.md](../../../docs/architecture-lineage.md)
9. `CMS-MPD Technical Data Flow And Modeling Method`. Local project methods document covering runtime logic, synthetic scenarios, reranking, and evaluation. [technical-data-flow-modeling.md](../../../docs/technical-data-flow-modeling.md)
10. `hybrid_reranker_dataset.metadata.json`. Local metadata artifact for the 2025-Q3 full-profile reranker dataset. [hybrid_reranker_dataset.metadata.json](../../../data/training/2025-Q3/full/hybrid_reranker_dataset.metadata.json)
11. `hybrid_reranker_evaluation_tree.json`. Local held-out evaluation report regenerated on April 6, 2026 during manuscript preparation. [hybrid_reranker_evaluation_tree.json](../../../data/training/2025-Q3/full/hybrid_reranker_evaluation_tree.json)
