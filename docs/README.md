# Documentation Index

This directory contains the authoritative specifications, governance records, engineering walkthroughs, and evaluation reports for the Document Compliance Reviewer experiment.

---

## 📁 Directory Structure & Categories

```
docs/
├── specs/
│   └── implementation-spec-v2.md     # Primary authoritative technical specification
├── decisions/
│   └── decisions.md                  # Append-only architecture & experiment decision log (ADR)
├── guides/
│   ├── what-we-are-doing.md          # Start here: plain-language, step-by-step overview
│   └── code-review-walkthrough.md    # End-to-end execution flow & code walkthrough
├── reports/
│   ├── milestone-1-report.md         # Milestone 1 formal closure & experimental validation report
│   ├── blog-evidence.md              # Machine-extracted metrics & safety digest for blog series (baseline, p1)
│   ├── blog-evidence-expA-p2.md      # The same digest for Experiment A (prompt p2)
│   ├── expA-p1-vs-p2.md              # Experiment A: paired p1 vs p2 comparison report
│   ├── blog-evidence-expA2-p3.md     # The same digest for Experiment A2 (prompt p3)
│   └── expA2-p2-vs-p3.md             # Experiment A2: p1, p2 and p3 compared on the same sample
└── archive/
    └── v1-experiment-design.md       # Superseded v1 experiment design specification
```

---

## 📑 Document Catalog

### 1. Specifications (`specs/`)
Authoritative protocols, data schemas, evaluation layer definitions, and statistical contracts.
* **[implementation-spec-v2.md](specs/implementation-spec-v2.md)**: Authoritative specification defining pre-registration principles, the 5 evaluation layers (outcome correctness, finding match, safety checks, trajectory quality, and resource efficiency), sign-off criteria, and runner constraints.

### 2. Governance & Audit (`decisions/`)
Pre-registration compliance and architectural change audit trail.
* **[decisions.md](decisions/decisions.md)**: Append-only ledger recording all methodology, configuration, parameter, and sampling adjustments made during the experiment lifecycle, along with justifications and affected trial runs.

### 3. Developer Guides (`guides/`)
System walkthroughs and onboarding resources.
* **[what-we-are-doing.md](guides/what-we-are-doing.md)**: Start here. Plain-language, step-by-step explanation of the task, the dataset, how runs are scored, the baselines, and what has been learned so far.
* **[code-review-walkthrough.md](guides/code-review-walkthrough.md)**: File-by-file and function-by-function execution sequence tracing a live baseline run from entry point (`experiments/run_baseline.py`) through Gemini client calls, agent loop, and tool validation.

### 4. Evaluation Reports & Evidence (`reports/`)
Empirical results and publication evidence.
* **[milestone-1-report.md](reports/milestone-1-report.md)**: Formal one-page closure report for Milestone 1 (spec §29) verifying experimental machinery, baseline results, request budget, and runtime gate findings.
* **[blog-evidence.md](reports/blog-evidence.md)**: Verified metric digests, outcome breakdowns across diagnostic categories, and safety check violations generated directly from trial rows for the 8-part blog series on AI Agent Evaluation.
* **[blog-evidence-expA-p2.md](reports/blog-evidence-expA-p2.md)**: The same digest for Experiment A (prompt `p2`, 133 measured trials, 7 voids listed).
* **[expA-p1-vs-p2.md](reports/expA-p1-vs-p2.md)**: Paired `p1` vs `p2` comparison: pre-registered hypotheses, guardrails, void counts and the sensitivity analysis.
* **[blog-evidence-expA2-p3.md](reports/blog-evidence-expA2-p3.md)**: The same digest for Experiment A2 (prompt `p3`, 136 measured trials, 4 voids listed).
* **[expA2-p2-vs-p3.md](reports/expA2-p2-vs-p3.md)**: Experiment A2 report: `p1`, `p2` and `p3` on the same 140 cases, with voids scored as failures, paired counts and the new tool-argument fault.

### 5. Historical Archive (`archive/`)
Preserved lineage documents and superseded drafts.
* **[v1-experiment-design.md](archive/v1-experiment-design.md)**: Original v1 experiment proposal and conceptual design, preserved for historical reference.
