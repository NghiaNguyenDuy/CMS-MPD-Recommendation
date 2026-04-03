# Enhancement Plan: Core Logic & Recommendation Workflow

## Revised Phase Order (per user feedback)

| Phase | Enhancement | Files Modified |
|-------|-------------|---------------|
| **1** | Coverage Gap (Donut Hole) + Catastrophic Phase | `recommend.py` |
| **2** | Multi-Drug Deductible Sequencing Optimization | `recommend.py` |
| **3** | Advanced Drug Resolution (Fuzzy by drug name) | `recommend.py`, `app_support.py` |
| **4** | Temporal Cost Distribution (Monthly Curve) | `recommend.py`, `streamlit_app.py` |
| **5** | Enhanced ML Reranking & Explainability | `modeling.py`, `recommend.py` |
| **6** | Recommendation Workflow UX (What-If, Sensitivity) | NEW `scenario_analysis.py`, `streamlit_app.py` |
| **7** | Pipeline: Generic Alternatives (drug-name search) | `pipeline.py`, `recommend.py` |
| **8** | Plan Stability & YoY Signals (prior data) | `pipeline.py`, `recommend.py` |

> [!IMPORTANT]
> Each phase is independently testable. Phase 5 (Stability) moved to last per user request since prior data is available but lower priority.

## Phase 1: Coverage Gap + Catastrophic Phase — READY TO IMPLEMENT

See [task.md](file:///C:/Users/Admin/.gemini/antigravity/brain/22908bfa-9516-433d-a6f5-1aab7ac56f9a/task.md) for execution tracking.
