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
│   └── blog-evidence.md              # Machine-extracted metrics & safety digest for blog series
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

### 5. Historical Archive (`archive/`)
Preserved lineage documents and superseded drafts.
* **[v1-experiment-design.md](archive/v1-experiment-design.md)**: Original v1 experiment proposal and conceptual design, preserved for historical reference.
