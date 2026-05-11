---
title: Topic - Manuscript Scientific Reliability Evidence Map
type: topic-note
status: active
tags:
  - cms-mpd
  - topic
  - manuscript
  - evidence-map
  - reviewer-revision
reviewed_on: 2026-04-21
related_sources:
  - "[[Source - Reviewer Literature Expansion and Scientific Reliability]]"
  - "[[Source - Plan Selection and Decision Support Evidence]]"
  - "[[Source - Drug Pricing and Formulary Distortions]]"
  - "[[Source - Part D Reform and IRA Timeline]]"
---

# Definition

This evidence map links the reviewer-focused manuscript's major scientific claims to external literature and official data sources. It is intended to help future revisions answer reviewer questions quickly.

## Claim-to-Evidence Map

| Manuscript claim | Best supporting evidence | How to use it |
|---|---|---|
| Part D plan selection is hard and often inefficient | Abaluck and Gruber; Zhou and Zhang; Heiss et al.; Bruine de Bruin and Hodson | Use to justify decision support, not to imply all beneficiaries behave the same way |
| Beneficiaries can learn or switch when incentives are clear | Ketcham, Lucarelli, and Powers | Use as a balancing source so the manuscript sounds scientifically careful |
| Simpler comparison displays can improve plan choices | McGarry, Maestas, and Grabowski; PCORI CHOICE; Bundorf et al. | Use to justify concise recommendation cards, top-plan explanations, and counselor-facing outputs |
| Public CMS files support reproducible plan-design simulation | CMS formulary, pharmacy network, pricing, and geography files | Use to defend the public replication boundary |
| Public files are not the same as full adjudicated market truth | CMS PDE guidance; GAO Plan Finder accuracy report; Part D claims restrictions | Use to justify incomplete-observability language and external benchmark limitations |
| Exact drug identity matters before cost simulation | NLM RxNorm documentation; FDA NDC Directory | Use in medication resolution and guardrail sections |
| Utilization management is central, not secondary | Joyce et al. 2024; plan-design and formulary studies | Use to justify restrictions, prior authorization, step therapy, and exclusions as first-class features |
| Post-IRA plan design is dynamic | Cai et al. 2025; Anderson et al. 2026; Joyce et al. 2026; CMS redesign guidance | Use to justify quarter-frozen artifacts and annual refresh |
| Health recommender systems need broader evaluation than ranking accuracy | Cai et al. 2022; Barbaric et al. 2025; Ananthakrishnan et al. 2025 | Use to justify scenario tests, explanation checks, usability future work |
| Explainable decision support is methodologically important | Xu et al. 2023; health CDSS interpretability literature | Use to defend rules-first simulation and constrained reranking |

## Reviewer-Ready Framing

The strongest framing is:

> CMS-MPD-Recommendation is not a generic black-box recommender. It is a reproducible public-data pipeline that resolves drug identity, constructs eligible plan-service-area candidates, simulates beneficiary-facing costs and access facts, and only then applies constrained reranking. This order aligns with Part D choice evidence, official CMS data structure, RxNorm/NDC terminology practice, and health recommender-system evaluation literature.

## Practical Use in Manuscript Work

- Use this note before responding to reviewers who ask why the system is not a pure machine-learning recommender.
- Use this note before adding future data sources so public, restricted, and local enrichment layers stay separated.
- Use this note when designing validation tables: include not only top-k ranking metrics, but also coverage, restriction, network, medication-match, and explanation-fidelity checks.

## Related Notes

- [[Source - Reviewer Literature Expansion and Scientific Reliability]]
- [[Topic - Plan Finder and CMS Pricing Files]]
- [[Topic - Drug Pricing and Formulary Dynamics]]
- [[Topic - Part D Benefit Redesign]]
- [[CMS MPD Manuscript - Computer Methods and Programs in Biomedicine Update - Reviewer Revision Draft]]
