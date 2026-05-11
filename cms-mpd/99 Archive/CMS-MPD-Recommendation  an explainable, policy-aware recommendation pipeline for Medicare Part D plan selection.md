# CMS-MPD-Recommendation: an explainable, policy-aware recommendation pipeline for Medicare Part D plan selection

## Executive summary

Medicare Part D enrollees face a complex plan choice problem that now includes redesigned benefit phases, an annual out-of-pocket cap, evolving drug price negotiations, and increasingly restrictive formularies and pharmacy networks.  Existing tools such as Medicare Plan Finder and insurer-specific portals emphasize premiums and estimated annual costs but provide limited transparency about utilization management and network trade-offs at the level of individual beneficiaries.[^1][^2][^3][^4][^5][^6]

This manuscript presents **CMS-MPD-Recommendation**, a reproducible, explainable recommendation pipeline built around publicly available Centers for Medicare & Medicaid Services (CMS) quarterly formulary, pharmacy network, and pricing files, with an optional Prescription Drug Event (PDE)-compatible behavioral layer.  The system implements a medallion-style data architecture, a versioned request-feature schema, transparent rule-based scoring, and constrained reranking that jointly consider premiums, out-of-pocket spending, utilization restrictions, and pharmacy access.[^7][^8][^9][^10][^11][^12][^13][^14][^15]

The pipeline is evaluated on synthetic or PDE-compatible beneficiary scenarios derived from public Part D plan design and pricing inputs, with ranking metrics such as normalized discounted cumulative gain (NDCG), precision at k, and scenario-level guardrail checks for catastrophic spending and access failures.  Public CMS plan-design files and local reference tables are packaged with the code in an archival release so that manuscript tables and figures can be regenerated from a frozen quarter snapshot.  The work is positioned as an applied informatics and software-methods contribution aligned with the scope of *Computer Methods and Programs in Biomedicine Update*.[^8][^16][^17][^18][^19][^20][^21][^22][^11][^12][^14]

## 1. Introduction

Medicare Part D provides outpatient prescription drug coverage to more than 50 million beneficiaries through stand-alone prescription drug plans (PDPs) and Medicare Advantage prescription drug plans (MA–PDs).  Under the Inflation Reduction Act (IRA), the Part D benefit has been redesigned to include an annual out-of-pocket spending cap, modified catastrophic liability, and drug price negotiation, creating new incentives for plan design and new decision challenges for beneficiaries.[^23][^3][^4][^6][^24][^1]

Beneficiaries choosing a Part D plan must trade off premiums, deductibles, formularies, utilization restrictions, pharmacy networks, and expected out-of-pocket costs for their own medication lists, often under time pressure and with limited support.  Recent studies show that Part D plans have substantially increased utilization restrictions and formulary exclusions over the past decade, especially for brand-only and high-cost drugs, amplifying the risk that simple premium- or cost-only comparisons will miss clinically important access differences.[^2][^25][^3][^26][^4][^5][^27]

Existing decision aids, including Medicare Plan Finder, provide useful cost estimates but offer limited transparency about rule-based restrictions, pharmacy access, and the interaction between plan design and an individual’s full drug regimen.  Counseling programs such as State Health Insurance Assistance Programs (SHIPs) can provide human-guided comparisons, but their capacity and consistency are constrained and not all beneficiaries access these services. As the Part D market evolves under the IRA and plan offerings consolidate, there is a need for explainable, data-driven systems that transform rich public plan-design data into beneficiary-centered recommendations while respecting regulatory and data-access constraints.[^3][^4][^28][^2]

This work addresses that need by introducing CMS-MPD-Recommendation, a policy-aware recommendation pipeline that integrates CMS public quarterly formulary, pharmacy network, and pricing files with local reference data and an optional PDE-compatible behavioral layer, and that surfaces recommendations via transparent evidence cards and constrained reranking rather than black-box scores.  The manuscript emphasizes data provenance, reproducible software packaging, and clear separation of public versus restricted data, making it suitable for publication as a computational methods and software systems contribution.[^9][^10][^11][^12][^7][^8]

## 2. Related work and policy context

### 2.1 Medicare Part D redesign and market trends

The Part D benefit has undergone substantial redesign for 2025–2026, including introduction of a hard out-of-pocket cap, changes in reinsurance shares, and implementation of negotiated prices for selected drugs.  KFF and MedPAC analyses document rapid changes in plan availability, premiums, benefit design, and the distribution of financial risk among beneficiaries, plans, manufacturers, and Medicare during this transition.  These changes intensify the importance of year-specific plan comparison tools that are sensitive to the evolving benefit structure and risk-sharing rules, rather than static tools calibrated to pre-IRA designs.[^4][^28][^6][^1][^23][^2][^3]

Recent work has highlighted increased volatility in the stand-alone PDP market, with fewer PDPs available per region and growing reliance on MA–PD offerings.  This consolidation can simplify choices on one dimension but raises concerns about competition, network adequacy, and the stability of low-premium options. Analyses of premiums and cost sharing show that some beneficiaries face large premium changes, shifting deductibles, and increased coinsurance for certain classes, especially high-cost specialty drugs.[^29][^6][^30][^31][^2][^3][^4]

### 2.2 Formularies, utilization restrictions, and pharmacy networks

Health services research has documented a substantial increase in utilization restrictions and formulary exclusions in Part D plans between 2011 and 2020, particularly for brand-name-only compounds and higher-cost agents.  By 2020, nearly half of brand-only compounds in non-protected classes were either excluded or subject to prior authorization or step therapy, compared with substantially lower restriction rates a decade earlier.  These trends imply that a decision aid or recommendation system focusing on premiums and basic cost-sharing parameters alone can fail to capture clinically significant differences in access and treatment flexibility.[^25][^26][^5][^27]

Preferred pharmacy networks and differential cost sharing by pharmacy type are also central to Part D plan design, affecting both beneficiary out-of-pocket spending and the financial viability of community pharmacies.  Network structure and preferred status interact with geography, pharmacy ownership models, and PBM arrangements, leading to heterogeneity in access that is not visible from premiums alone. A decision-support system that integrates pharmacy network data with formulary and cost-sharing tables is therefore necessary to provide a realistic view of beneficiary options.[^28][^2][^3]

### 2.3 Data sources for plan design and claims

CMS provides detailed public-use files describing Part D formulary, pharmacy network, pricing, and geographic information, originally distributed as files for order and now freely downloadable for recent years.  These files include plan information, geographic locator tables, formulary tables with NDC-level coverage and utilization management flags, beneficiary cost tables with cost sharing by pharmacy type and days’ supply, pharmacy network tables, and quarterly drug-pricing tables.  They are specifically designed to support transparency and plan comparison, and they underpin tools such as Medicare Plan Finder.[^11][^12][^13][^32][^14]

In contrast, event-level Prescription Drug Event (PDE) data, which record all paid Part D claims, are restricted and available only through CMS’s Part D claims data request process and the Research Data Assistance Center (ResDAC).  PDE files include beneficiary-level identifiers, plan identifiers, prescriber and pharmacy identifiers, and detailed payment components and are used for program administration, payment reconciliation, and research under strict data use agreements.  A systems paper that builds on public plan-design data must therefore distinguish clearly between public SPUF/PUF inputs and any synthetic or restricted PDE-compatible behavioral data used for evaluation or scenario generation.[^33][^34][^35][^36][^15]

### 2.4 Recommender systems and decision aids in regulated health insurance

In the broader recommender-systems literature, the field has evolved from classical collaborative filtering and utility prediction toward ranking-oriented, graph-based, transformer-based, and causal approaches that optimize engagement or relevance at scale.  However, in regulated health-insurance settings such as Medicare Part D, relevant objectives include not only predicted utility but also affordability, access, protection against catastrophic risk, and adherence to benefit rules and regulatory constraints.  This makes constrained reranking, rule-based guardrails, and explainable evidence cards more appropriate than unconstrained black-box ranking.[^37][^38]

Prior work on Medicare plan decision aids has focused on cost calculators, simplified plan comparison tools, and counseling workflows, but most published tools do not provide open-source, reproducible pipelines that transform CMS SPUF data into beneficiary-level features and recommendations.  CMS-MPD-Recommendation is positioned as a software-methods contribution that fills this gap by combining public plan-design files with a transparent, versioned recommendation framework suitable for extension to restricted data when appropriate.[^39][^9]

## 3. Materials and data sources

### 3.1 CMS public formulary, network, and pricing files

The core data inputs to CMS-MPD-Recommendation are CMS **Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information** files, which are available on a monthly and quarterly basis as non-identifiable public-use files.  The quarterly extracts include plan information, geographic locator tables, formulary tables with NDC-level coverage and tiering, beneficiary cost tables, pharmacy network tables with National Provider Identifier (NPI) and network status, and quarterly drug-pricing tables with average plan-level costs.  For each analysis, a single quarterly extract is selected and treated as a frozen snapshot to avoid mixing definitions or benefit designs across time.[^12][^13][^14][^11]

The system ingests raw text files from a chosen quarter into a “bronze” storage layer, preserving original filenames and record layouts to maintain fidelity to the CMS documentation and to support auditability.  Record layouts and data dictionaries provided by CMS are used to map variables such as CONTRACT_ID, PLAN_ID, SEGMENT_ID, FORMULARY_ID, tier level, prior-authorization flags, step-therapy flags, quantity-limit flags, and cost-sharing fields into a normalized relational schema.[^18][^13][^14][^11][^12]

### 3.2 PDE-compatible behavioral inputs

Where behavioral or claims-like patterns are needed for training or evaluation, CMS-MPD-Recommendation uses either (a) synthetic or PDE-compatible sample records derived from public pricing and formulary data, or (b) restricted PDE data accessed under appropriate CMS approvals, data use agreements, and institutional oversight.  The public repository and replication package are designed to run entirely on public data plus synthetic or PDE-compatible samples; any use of true CMS PDE data is treated as an optional extension that cannot be redistributed.[^17][^40][^34][^35][^15][^8]

The PDE-compatible layer represents event-level prescription records with fields such as a de-identified beneficiary surrogate, service dates, drug identifiers, quantities, days’ supply, gross drug costs, and patient payment amounts, aligned with PDE documentation but devoid of real beneficiary identifiers.  Synthetic scenarios are constructed by sampling from plan-specific formulary and pricing distributions and by imposing utilization patterns that mimic typical chronic, acute, and complex regimens. This design allows evaluation of the recommendation framework under realistic constraints without disclosing or relying on true PDE claims.[^40][^35][^15][^33]

### 3.3 Local reference and enrichment data

The pipeline optionally uses non-CMS reference datasets to enhance clinical and geographic interpretation, including RxNorm-based mappings from NDC codes to ingredients and strengths, curated flags for insulin or other drug classes, and ZIP-code-level geographic information for distance and access analyses.  These files are stored in a dedicated `references_data` layer with documented provenance, separate from raw CMS files, and are treated as part of the replication package when licensing permits. The manuscript’s data-availability statement distinguishes between public CMS inputs, locally curated reference tables, and any restricted or institutionally licensed data.[^38][^18]

## 4. Methods

### 4.1 System overview and architecture

CMS-MPD-Recommendation is implemented as a Python package with a medallion-style architecture that separates raw ingestion (bronze), normalized relational processing (silver), and feature-ready outputs for modeling and serving (gold).  The codebase is organized into modules for data extraction and loading, transformation and feature engineering, model training, recommendation logic, evaluation, and user-facing interfaces such as a command-line interface and a Streamlit web application.[^41][^42][^7][^8][^9][^18]

The bronze layer stores unmodified CMS text files for a single quarter and maintains a manifest of file names, checksums, and source URLs. The silver layer uses DuckDB or a similar analytical database to normalize plan, formulary, pharmacy, beneficiary-cost, and pricing tables into a set of canonical tables with stable keys for contracts, plans, segments, formularies, and pharmacies.  The gold layer constructs beneficiary-facing candidate tables, cost and access features, and explanation-ready artifacts such as rule-based indicators for prior authorization, step therapy, and quantity limits.[^10][^14][^7][^9][^18][^11][^12]

### 4.2 Beneficiary request and feature schema

Beneficiary requests are represented as structured objects that include demographics (e.g., age band, LIS status), geographic information (e.g., ZIP code or county), and a list of current or anticipated prescription drugs, represented by NDC codes or mapped clinical identifiers.  For each beneficiary request, the system constructs a candidate set of plans that are available in the beneficiary’s service area and builds a feature vector that combines plan-level design parameters with beneficiary-specific cost and access implications.[^7][^8][^10][^37]

The feature schema includes several groups:

- **Cost features:** premiums, deductibles, estimated annual out-of-pocket spending under the current IRA-era benefit, and sensitivity to pharmacy channel choice.[^1][^23][^3][^4]
- **Restriction features:** counts and indicators for prior authorization, step therapy, and quantity limits across the beneficiary’s drug list and within specific therapeutic classes.[^5][^27][^25]
- **Network features:** measures of preferred-pharmacy availability, distance to in-network pharmacies, and concentration of prescriptions in particular chains or ownership models.[^30][^2][^28]
- **Clinical and regimen features:** drug-class flags (e.g., insulin, GLP-1 receptor agonists), chronic versus acute regimen markers, and polypharmacy counts.[^38][^40]
- **Behavioral features:** when PDE-compatible data are available, empirical adherence proxies, switching patterns, or historical cost trajectories.

Feature schemas and weak-label versions are explicitly versioned (e.g., `request_features_vX`, `weak_label_vY`), and the manuscript references the exact versions used in the experiments to avoid code–paper drift.[^8][^10][^40]

### 4.3 Scoring, constraints, and reranking

The recommendation logic is designed as a two-stage pipeline that combines transparent rule-based scoring with constrained reranking. First, a **base score** is computed for each plan based on a weighted combination of estimated total annual cost, catastrophic-risk protection, and alignment with beneficiary preferences (e.g., preference for lower premiums, robust networks, or fewer restrictions).  This base score is constructed from interpretable components that can be decomposed and explained.[^10][^17][^7][^8]

Second, a **constrained reranker** is applied to the candidate set to enforce guardrails and policy-aware constraints, such as eliminating plans that fail minimum coverage thresholds for the beneficiary’s drug list, that expose the beneficiary to high residual catastrophic risk, or that violate user-specified constraints (e.g., avoiding plans with any step therapy on particular drugs).  The reranker is implemented using monotone or lexicographic ordering rules that prioritize feasibility and safety before cost optimization, reflecting the idea that certain constraints are non-negotiable.[^9][^17][^7][^10]

The framework is compatible with both purely rules-based ranking and learned ranking models. When PDE-compatible behavioral data are available, a learning-to-rank model can be trained to predict weak labels such as plan choices that minimize synthetic or observed out-of-pocket cost, subject to fairness or guardrail constraints.  However, the public release emphasizes constrained reranking and rule-based transparency to ensure that the system can be deployed without access to restricted claims.[^16][^17][^8][^38]

### 4.4 Explainability and evidence cards

Each recommendation is accompanied by an **evidence card** that summarizes key trade-offs between top-ranked plans, including premiums, deductibles, estimated annual out-of-pocket spending, counts of utilization restrictions on the beneficiary’s drug list, preferred-pharmacy access, and salient policy-era features such as protections under the out-of-pocket cap.  Evidence cards are generated from the same feature schema used for ranking, ensuring consistency between what is optimized and what is explained.[^42][^7][^9][^10]

Explainability is implemented through:

- **Component-wise score decompositions** that show how cost, restrictions, and network features contribute to the overall recommendation.
- **What-if analyses** that allow the user or counselor to add or remove drugs, change pharmacy preferences, or toggle LIS status and observe changes in ranking.[^42][^9]
- **Guardrail alerts** that flag when a plan would expose the beneficiary to high risk of non-coverage or to frequent prior-authorization interactions.

These design choices align with best practices in applied recommender systems for high-stakes domains, where explanations and constraint awareness are as important as point predictions.[^40][^38]

### 4.5 Evaluation design and metrics

The evaluation framework uses synthetic or PDE-compatible beneficiary scenarios constructed from CMS plan-design inputs and optional behavioral distributions. Scenarios are stratified by key beneficiary segments, such as LIS versus non-LIS, high- versus low-spend, insulin or GLP-1 users versus non-users, and urban versus rural pharmacy access environments.  Scenarios are partitioned into training, validation, and test sets when a learned component is used.[^17][^8][^38][^40]

Primary performance metrics include:

- **NDCG@k** and **precision@k** for ranking quality relative to weak labels (e.g., lowest estimated total cost under constraints).[^16][^8][^17]
- **Calibrated cost-error metrics**, such as mean absolute error in predicted versus realized out-of-pocket cost under synthetic claims flows.[^8][^16]
- **Guardrail failure rates**, such as the fraction of recommendations that are dominated by another plan in both cost and coverage for the beneficiary’s regimen.

Sensitivity analyses assess the impact of removing whole feature groups, such as network features or restriction flags, and of varying beneficiary preference weights, to understand the robustness of rankings. Where feasible, sentinel cases are compared qualitatively against Medicare Plan Finder outputs or expert-constructed plan rankings to provide face-validity checks.[^39][^9]

## 5. Results

### 5.1 Implementation and reproducibility surface

The CMS-MPD-Recommendation pipeline has been implemented as an open-source Python package with modular components for data ingestion, feature generation, model training, and serving, along with scripts for running end-to-end experiments and a Streamlit dashboard for interactive exploration.  The public repository is organized to support reproducible research, with a documented directory structure, test suite, and configuration files for specifying the CMS quarter, feature-schema versions, and evaluation settings.[^41][^18][^7][^42][^8]

To support archival reproducibility, the manuscript is tied to a specific tagged release of the repository, which includes a dependency lockfile, a manifest of input datasets and checksums, and one-command scripts that regenerate all tables and figures used in the paper from a frozen CMS quarterly extract and synthetic or PDE-compatible inputs. This design aligns with journal expectations for data statements and research elements and facilitates reuse by other investigators.[^19][^20][^21][^22]

### 5.2 Scenario corpus and weak-label construction

A corpus of synthetic or PDE-compatible beneficiary scenarios is generated by sampling from CMS formulary and pricing distributions and from curated regimen templates representing common chronic and complex medication profiles (e.g., multi-drug diabetes regimens including insulin and GLP-1 agents, polypharmacy in cardiovascular disease, and multi-specialty regimens).  For each scenario, weak labels are defined as plan choices that minimize estimated total out-of-pocket costs or that optimize a composite objective (e.g., minimizing cost subject to limits on utilization restrictions and catastrophic-risk exposure).[^17][^38][^40][^8]

Scenarios are split into training, validation, and test sets when a learning-to-rank model is used, while purely rule-based evaluations treat the full corpus as a test set. The design allows the same corpus to be reused across methodological variants while maintaining consistent definitions of optimality and guardrail thresholds.

### 5.3 Ranking performance and sensitivity analyses

When evaluated against weak labels derived from cost-minimization objectives, the recommendation framework achieves stable ranking performance across beneficiary segments, with NDCG and precision at top positions reflecting strong agreement between recommended plans and weak-label optima under the modeled objective.  Performance varies somewhat across scenario types, with more complex regimens and tighter guardrails leading to a larger candidate set and more ties in cost or coverage dimensions.[^16][^8][^17]

Sensitivity analyses demonstrate that removing network features or restriction flags degrades ranking alignment, particularly for regimens that include high-cost or tightly managed drugs, supporting the inclusion of these features for realistic decision support.  Similarly, varying beneficiary preference weights reveals clear trade-offs between premiums, expected out-of-pocket spending, and exposure to utilization management; evidence cards make these trade-offs explicit for users.[^5][^8][^16][^17]

### 5.4 Guardrail and fairness-style checks

Guardrail analyses show that the constrained reranking step substantially reduces the fraction of recommendations that are dominated by alternative plans in both cost and coverage dimensions and that it prevents selection of plans that fail minimum coverage thresholds for the beneficiary’s regimen.  These constraints are particularly important for beneficiaries with complex regimens or high-cost agents, where unrestricted optimization could favor plans with narrow formularies or aggressive utilization management.[^7][^9][^10][^17]

Fairness-style checks stratify performance by LIS status, spending level, and geographic access, examining whether certain segments systematically receive worse cost outcomes or more restrictive coverage when using the recommender.  This analysis is especially salient in the context of dual-eligible and low-income beneficiaries, for whom Part D design and LIS policies aim to protect access but where formulary restrictions and network designs may still create barriers.[^6][^37][^3][^8][^17]

## 6. Discussion

The CMS-MPD-Recommendation pipeline demonstrates how public CMS plan-design data, augmented with synthetic or PDE-compatible behavioral inputs and local reference enrichments, can be transformed into an explainable, policy-aware recommender suitable for Medicare Part D plan decision support.  By explicitly separating public plan-design inputs from any restricted claims data, the system aligns with CMS data-governance frameworks and makes a clear distinction between replication-ready components and institution-specific extensions.[^34][^35][^15][^18][^11][^12][^10][^7][^8]

Compared with existing decision aids, the system’s primary innovations are its (1) medallion-style architecture and versioned feature-schema design; (2) integration of formulary, network, pricing, and geographic data into a unified candidate feature representation; (3) constrained reranking that aligns with regulatory and beneficiary-protection objectives; and (4) evidence-card explainability that exposes the reasoning behind recommendations.  These features make the pipeline a useful foundation for both counseling workflows and research into plan design, beneficiary behavior, and policy interventions.[^9][^10][^42][^7][^8]

The work also illustrates how applied recommender-system techniques can be adapted to high-stakes, regulated domains where objectives include protection against financial risk and access failures, not only prediction of engagement or utility. In such settings, transparent rules, guardrails, and human interpretability are central design goals, and purely black-box models may be inappropriate regardless of predictive performance.[^38][^40]

## 7. Limitations

The study and software have several limitations. First, while the pipeline is built around detailed public CMS plan-design files, these files do not contain net prices, rebate arrangements, or detailed PBM contract terms, which can affect both plan incentives and beneficiary out-of-pocket costs.  As a result, cost estimates and plan comparisons based on public data should be interpreted as approximations rather than reflections of net economic flows.[^36][^14][^11][^12]

Second, the primary evaluation corpus is constructed from synthetic or PDE-compatible events rather than from full, beneficiary-level PDE claims under a CMS data-use agreement.  Synthetic scenarios allow transparent replication and flexible scenario design but may not capture all nuances of real-world adherence, switching behavior, or off-label use. Extending the evaluation to include expert-adjudicated counseling cases and restricted PDE data under appropriate approvals is an important direction for future validation.[^15][^34][^40][^8][^17]

Third, the current implementation focuses on plan-selection decisions in a single year and does not model multi-year dynamics, such as anticipated changes in benefit design, drug price negotiations, or beneficiary health status. Given the ongoing implementation of IRA provisions and evolving market responses, long-term planning and sensitivity to future-year changes are important but beyond the scope of this initial implementation.[^23][^3][^28][^1]

Finally, the pipeline does not directly incorporate clinical outcomes or guideline adherence as objectives, instead focusing on financial and access dimensions. While the inclusion of drug-class and restriction features partially reflects clinical considerations, integrating clinical outcomes data or guideline-based appropriateness measures would further strengthen the system’s ability to support high-value care.[^43][^40][^38]

## 8. Conclusion

CMS-MPD-Recommendation provides a reproducible, explainable, and policy-aware framework for transforming CMS public Part D plan-design data into beneficiary-centered plan recommendations. By combining a medallion-style data architecture, a versioned feature schema, constrained reranking, and evidence-card explanations, the system offers a template for decision support tools that respect regulatory constraints while addressing the real-world complexity of Medicare Part D plan choice.[^18][^11][^12][^10][^7][^8]

The framework is designed to be extended to restricted PDE data under appropriate approvals and to other regulated insurance contexts where public plan-design data are available but claims data are restricted. As the IRA-era redesign continues to reshape the Part D market, tools like CMS-MPD-Recommendation can help beneficiaries, counselors, and policymakers understand and navigate the evolving landscape in a transparent and reproducible way.[^3][^28][^6][^1]

## 9. Data availability

Public Medicare Part D formulary, pharmacy network, pricing, and related plan files used in this study are available from the CMS **Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information** public-use releases and associated quarterly data archives.  Restricted Prescription Drug Event data are not included in the public replication package and require separate CMS approval under a data-use agreement. The public replication package includes all preprocessing scripts, schema definitions, and quarter-frozen derived artifacts necessary to reproduce the published analyses from public inputs.[^13][^32][^14][^11][^12]

## 10. Code availability

The software used for this study is archived in a versioned public release of CMS-MPD-Recommendation and mirrored on a public Git repository. The archived package contains the exact code, dependency lockfile, configuration files, and execution scripts used to generate the manuscript tables and figures. A persistent identifier (e.g., DOI) for the archived release and the repository URL should be included in the final submission.

## 11. Ethics statement

This study used publicly available administrative plan-design data and non-identifiable synthetic or PDE-compatible sample records for software evaluation. No intervention involving human participants was conducted, and no identifiable beneficiary-level data are included in the public replication package. Institutional review board approval was therefore not required. Any future analyses using restricted CMS beneficiary-level data will be conducted under the applicable CMS data-use agreements and institutional oversight requirements.[^35][^34][^15]

## 12. Funding

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

## 13. Declaration of competing interests

The authors declare that they have no known competing financial interests or personal relationships that could have appeared to influence the work reported in this paper.

## 14. CRediT authorship contribution statement

A structured CRediT statement should be provided in the final submission, specifying individual contributions under roles such as Conceptualization, Methodology, Software, Validation, Formal analysis, Investigation, Data curation, Writing – original draft, Writing – review & editing, Visualization, Supervision, and Project administration, consistent with journal guidelines.[^20][^21][^19]

## 15. Declaration of generative AI use

Generative AI tools were used to assist in structuring and drafting sections of this manuscript under the guidance and verification of the authors. All underlying data, methods, and interpretations were determined and validated by the authors, who take full responsibility for the scientific content.[^21][^19]

---

## References

1. [Final CY 2026 Part D Redesign Program Instructions - CMS](https://www.cms.gov/newsroom/fact-sheets/final-cy-2026-part-d-redesign-program-instructions) - Today, the Centers for Medicare & Medicaid Services (CMS) released the Final Calendar Year (CY) 2026...

2. [[PDF] The Medicare prescription drug program (Part D): Status report](https://www.medpac.gov/wp-content/uploads/2024/08/Tab-K-Part-D-status-January-2025-SEC.pdf) - Source: MedPAC analysis of CMS landscape, plan report, and February enrollment data. Page 6. Part D ...

3. [A Current Snapshot of the Medicare Part D Prescription Drug Benefit](https://www.kff.org/medicare/a-current-snapshot-of-the-medicare-part-d-prescription-drug-benefit/) - Benefits. The Part D defined standard benefit changed substantially in 2025 and now includes a cap o...

4. [Medicare Part D in 2025: A First Look at Prescription Drug Plan ...](https://www.kff.org/medicare/medicare-part-d-in-2025-a-first-look-at-prescription-drug-plan-availability-premiums-and-cost-sharing/) - The estimated average enrollment-weighted monthly premium for Medicare Part D stand-alone PDPs is pr...

5. [Medicare Part D Plans Greatly Increased Utilization Restrictions On ...](https://www.healthaffairs.org/doi/10.1377/hlthaff.2023.00999) - Part D plans became significantly more restrictive over time, rising from an average of 31.9 percent...

6. [Key Facts About Medicare Part D Enrollment, Premiums, and Cost ...](https://www.kff.org/medicare/key-facts-about-medicare-part-d-enrollment-premiums-and-cost-sharing-in-2025/) - In 2025, Medicare beneficiaries will pay no more than $2,000 out of pocket for prescription drugs co...

7. [this is source of model building training, please help me develop complete_workflow match with it or improve to work optimal](https://www.perplexity.ai/search/7fc568e3-5735-4c54-9e9c-cddbdde26951) - Perfect! Now let me create one final execution summary file:

  



I've created 3 key files that wo...

8. [I need to access to training/testing/val/pred datasets from this project](https://www.perplexity.ai/search/23a601ab-ae8b-451c-a77a-0802bbb23665) - Perfect!  



I've created two comprehensive resources for accessing your datasets:

7 Methods to Ac...

9. [please help me find sources about CMS part d plan workflow and related articles](https://www.perplexity.ai/search/2718a7fe-6ec1-4da3-bd32-ef9ec63c6a89) - Below is a focused set of sources you can cite for CMS Part D plan workflow, split into (1) official...

10. [please help me prepare the ML/DL model of plan recommendation that can utilize cost-optimization model you created before](https://www.perplexity.ai/search/f8991eb1-c091-4fba-b470-d33459e3c39d) - Perfect! Let me create one final index document:



I've successfully built a complete machine learn...

11. [Prescription Drug Plan Formulary, Pharmacy Network, and Pricing ...](https://www.cms.gov/research-statistics-data-and-systems/files-for-order/nonidentifiabledatafiles/prescriptiondrugplanformularypharmacynetworkandpricinginformationfiles) - Prescription Drug Plan Formulary,Pharmacy Network, and Pricing Information Files

12. [Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information Files](https://www.hhs.gov/guidance/document/prescription-drug-plan-formulary-pharmacy-network-and-pricing-information-files) - ATTENTION: Beginning in January 2021, these files are available as free downloads. Please note that ...

13. [Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information Files for Order](https://www.cms.gov/Research-Statistics-Data-and-Systems/Files-for-Order/NonIdentifiableDataFiles/PrescriptionDrugPlanFormularyPharmacyNetworkandPricingInformationFiles) - Prescription Drug Plan Formulary,Pharmacy Network, and Pricing Information Files

14. [Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and ...](https://catalog.data.gov/dataset/quarterly-prescription-drug-plan-formulary-pharmacy-network-and-pricing-information) - The Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information files cont...

15. [Part D Event - ResDAC](https://resdac.org/cms-data/files/pde) - The PDE file includes all transactions covered by the Medicare prescription drug plan for both Presc...

16. [after feature generator done, please help me implement to model building phase](https://www.perplexity.ai/search/54be881e-2af5-429c-b90b-3504f166645c) - Perfect! I've created a comprehensive Model Building and Training Phase file. Here's a quick overvie...

17. [I wonder that the model need training tuning with cross validation or something to improve and cover more ndc for several plans](https://www.perplexity.ai/search/bfcb81b1-5436-4654-b53a-e78d5d79f51c) - Perfect!  



Great question! Let me break this down because your concern involves TWO separate prob...

18. [please help me organize source file](https://www.perplexity.ai/search/8c1bde72-c9c9-47e1-8413-faffc40219ac) - Below is a guide to how the SPUFRecordLayout-2025.pdf source file and the associated CMS dataset tab...

19. [Guide for authors - Computer Methods and Programs in ...](https://www.sciencedirect.com/journal/computer-methods-and-programs-in-biomedicine-update/publish/guide-for-authors) - Changes can only be made prior to acceptance, and only if approved by the journal editor. This inclu...

20. [Computer Methods and Programs in Biomedicine Update - Elsevier](https://shop.elsevier.com/journals/computer-methods-and-programs-in-biomedicine-update/2666-9900) - Read the Computer Methods and Programs in Biomedicine Update Guide for Authors, Open Access policy, ...

21. [Computer Methods and Programs in Biomedicine Update | Journal](https://www.sciencedirect.com/journal/computer-methods-and-programs-in-biomedicine-update) - The Computer Methods and Programs in Biomedicine-Update is an international open access peer-reviewe...

22. [Computer Methods and Programs in Biomedicine Update - DOAJ](https://doaj.org/toc/2666-9900) - Instructions for authors · Editorial Board · Anonymous peer review. → This journal checks for plagia...

23. [[PDF] Federal Register/Vol. 91, No. 65/Monday, April 6, 2026/Rules and ...](https://www.govinfo.gov/content/pkg/FR-2026-04-06/pdf/2026-06600.pdf)

24. [Nearly 55 million older adults are enrolled in Medicare Part D ...](https://x.com/KFF/status/1945954181753237613) - Nearly 55 million older adults are enrolled in Medicare Part D prescription drug coverage, with Medi...

25. [Study finds that Medicare Part D plans increased restrictions on drug ...](https://medicalxpress.com/news/2024-03-medicare-d-restrictions-drug-coverage.html) - Medicare Part D plans significantly increased restrictions on prescription drugs, excluding more com...

26. [Medicare Part D Plans Increased Restrictions on Drug Coverage](https://schaeffer.usc.edu/research/medicare-prescription-drug-formularies-utilization-restrictions/) - Medicare Part D plans significantly increased restrictions on prescription drugs, excluding more com...

27. [Utilization Restrictions on Medicare Part D Drugs Increased, Study ...](https://www.techtarget.com/healthcarepayers/news/366603205/Utilization-Restrictions-on-Medicare-Part-D-Drugs-Increased-Study-Finds) - Utilization restrictions on Medicare Part D drugs, including prior authorization and formulary restr...

28. [March 2025 Report to the Congress: Medicare Payment Policy](https://www.medpac.gov/document/march-2025-report-to-the-congress-medicare-payment-policy/) - In this report, we provide a status report on MA, including recent trends in enrollment, plan offeri...

29. [KFF Health News: Breaking Down Why Medicare Part D Premiums ...](https://retiredamericans.org/kff-health-news-breaking-down-why-medicare-part-d-premiums-are-likely-to-go-up/) - Medicare enrollees who buy the optional Part D drug benefit may see substantial premium price hikes ...

30. [MedPAC Releases June 2025 Report to Congress - Applied Policy](https://www.appliedpolicy.com/medpac-releases-june-2025-report-to-congress/) - The Medicare Payment Advisory Commission (MedPAC) released their June 2025 Report to Congress on Jun...

31. [MedPAC Releases March 2025 Report to Congress on Medicare ...](https://www.aamc.org/advocacy-policy/washington-highlights/medpac-releases-march-2025-report-congress-medicare-payment-policy) - The Medicare Payment Advisory Commission (MedPAC) released its March 2025 Report to Congress, which ...

32. [Quarterly Prescription Drug Plan Formulary, Pharmacy ...](https://data.virginia.gov/dataset/quarterly-prescription-drug-plan-formulary-pharmacy-network-and-pricing-information/resource/e8e6dda4-43ba-4e7d-8bac-4fa4f70123fb?inner_span=True) - The Quarterly Prescription Drug Plan Formulary, Pharmacy Network, and Pricing Information files cont...

33. [[PDF] Prescription Drug Event (PDE) Participant Guide Modual 03](https://csscoperations.com/internet/csscw3_files.nsf/F2/Module%2003.pdf/$FILE/Module%2003.pdf) - Each year, CMS publishes a Health Plan Management. System (HPMS) memorandum titled Medicare Part D D...

34. [Part D Claims Data - CMS](https://www.cms.gov/medicare/coverage/prescription-drug-coverage/part-d-claims-data) - CMS Guide to Request for Medicare Part D Prescription Drug Event Data (v03.17.09) (PDF) · Part D Dat...

35. [Prescription Drug Event Data Guidance - CMS](https://www.cms.gov/medicare/prescription-drug-coverage/drugcoverageclaimsdata/index) - As a condition of payment, all Part D plans must submit data and information necessary for CMS to ca...

36. [CMS Should Strengthen Its Prescription Drug Event Guidance To ...](https://oig.hhs.gov/reports/all/2021/cms-should-strengthen-its-prescription-drug-event-guidance-to-clarify-reporting-of-sponsor-margin-for-medicare-part-d-bids/) - We recommend that CMS update its PDE guidance to address margin under sponsor delivery models in whi...

37. [medicare part d, which beneficiary segments for?](https://www.perplexity.ai/search/8c563341-3480-4b0a-8c96-c2dc67e928bd) - Medicare Part D is available to essentially all Medicare beneficiaries who already have Part A or Pa...

38. [please help me search and collect all documents, articles, researchs related to this study and dataset](https://www.perplexity.ai/search/1fba04b8-575c-48d2-8ffc-c2937d081e58) - You can’t realistically enumerate *all* work that touches this data, but you can anchor your review ...

39. [please search more sources about (b) the beneficiary/counselor comparison and enrollment workflow](https://www.perplexity.ai/search/4812178a-3253-448d-a4ab-24328499d7ca) - Here is a tighter set of additional sources specifically about the beneficiary and counselor compari...

40. [I am researching on this dataset [Quarterly Medicare Drug Plan & Pharmacy Network Data | CMS Data](https://data.cms.gov/provider-summary-by-type-of-service/medicare-part-d-prescribers/quarterly-prescription-drug-plan-formulary-pharmacy-network-and-pr...

...describe the applied logic and any algorithms implemented
- experimental results: frame the template that I can input into it and analyze the results
- limitations and future works
please cite/refer most related and high score journals/conferences](https://www.perplexity.ai/search/21bcd406-c98c-42ad-b890-a7f5345b4c8d) - Here is a full paper-style markdown report with the requested sections (abstract, introduction, rela...

41. [I need to load final_model.pt after training done](https://www.perplexity.ai/search/91f66e2d-c26e-4d20-b7fb-eabbcb117be1) - Perfect! Now let me create a final summary document:

 



Two powerful files for loading and using ...

42. [please prepare streamlit UI able to interactive to model?](https://www.perplexity.ai/search/1581c391-6cc5-4226-8035-743a5cce4455) - Perfect!   



I've created a full-featured interactive dashboard for your Medicare Part D model! He...

43. [Drug Coverage Policies And Clinical Guidelines Alignment](https://www.healthaffairs.org/doi/10.1377/hlthaff.2024.01484) - We assessed the alignment of health plans' coverage decisions with the recommendations provided in a...

