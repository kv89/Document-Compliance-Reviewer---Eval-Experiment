# Document Compliance Reviewer — AI Agent Evaluation Experiment

A small, reproducible AI agent that reviews plain-text documents against a compliance policy.

**The agent is not the product. The measurement is.** This repository is a controlled experimental
system for investigating how AI agents should be evaluated: what counts as success, how to evaluate
tool use and trajectories, when deterministic evaluators suffice, when an LLM judge helps, how
reliable that judge is, and how agent evaluation fits into CI/CD. It supplies the empirical evidence
for an eight-part blog series on AI agent evaluation.

---

## 📖 Essential Documentation

The project follows a strict **pre-registration and specification-first** methodology:

| Document | Role |
|---|---|
| [docs/guides/what-we-are-doing.md](docs/guides/what-we-are-doing.md) | **Start Here.** Plain-language, step-by-step explanation of what the project does and why. |
| [docs/specs/implementation-spec-v2.md](docs/specs/implementation-spec-v2.md) | **Authoritative Specification.** Complete schemas, evaluation layers, constraints, baselines, and CI gates. |
| [docs/decisions/decisions.md](docs/decisions/decisions.md) | **Append-Only Decision Log.** Every post-v2 methodology, parameter, and runner change with rationale and affected experiments. |
| [docs/guides/code-review-walkthrough.md](docs/guides/code-review-walkthrough.md) | **Code Walkthrough.** Traces execution flow and function call sequence of a run from entry point to report. |
| [docs/reports/blog-evidence.md](docs/reports/blog-evidence.md) | **Blog Evidence Digest.** Machine-extracted metrics, safety breakdown, and trace pointers for the blog series. |
| [docs/reports/blog-evidence-expA-p2.md](docs/reports/blog-evidence-expA-p2.md) | **Experiment A Digest.** The same digest for prompt `p2`. |
| [docs/reports/expA-p1-vs-p2.md](docs/reports/expA-p1-vs-p2.md) | **Experiment A Report.** Paired `p1` vs `p2` comparison with void counts and the sensitivity analysis. |
| [docs/archive/v1-experiment-design.md](docs/archive/v1-experiment-design.md) | **Historical Archive.** Superseded version 1 experiment design specification. |

---

## 🎯 How the Experiment Works

A run points the agent at contract-like synthetic documents evaluated against policy `POL-001` (5 rules: Payment Terms, Termination, Liability, Payment Cap, and Governing Law). For each document, the agent:

1. Reads the document and policy.
2. Calls JSON-protocol tools (`search_document`, `get_document_section`, `lookup_policy`).
3. Emits a structured verdict: `COMPLIANT`, `NON_COMPLIANT`, or `NEEDS_REVIEW` with exact evidence quotes and offsets.

Every model request, tool call, token count, and step is recorded in an immutable trace. The agent is never graded on self-reported assertions; it is graded on what the trace proves it did.

### The 7 Test Categories

The dataset uses a stratified diagnostic distribution (25 cases per category in `v1`, 175 total; 20 per category sampled in baseline runs, 140 total):

| Category | Tested Failure Mode | Scoring Stratum |
|---|---|---|
| `compliant` | Clean document obeying all rules | Strict (`COMPLIANT`) |
| `missing_clause` | A mandatory clause is absent | Strict (`NON_COMPLIANT`) |
| `incorrect_value` | Clause present but violates constraint (e.g. payment > 30 days) | Strict (`NON_COMPLIANT`) |
| `multiple_violations` | Two or more rules violated simultaneously | Strict (`NON_COMPLIANT`) |
| `contradictory` | Document contradicts itself across sections | Strict (`NON_COMPLIANT`) |
| `ambiguous` | Document genuinely unresolvable against policy | Accept-set (`NEEDS_REVIEW`) |
| `distractor` | Text looks like a violation but is legally irrelevant (false-positive probe) | Strict (`COMPLIANT`) |

### Six Evaluation Layers

Each trial is graded independently across 6 layers:
1. **Layer 1 — Outcome**: Status correctness and exact finding classification.
2. **Layer 2 — Evidence**: Cited section accuracy, verbatim quotation check, and character offset consistency.
3. **Layer 3 — Tool Use**: Tool selection validity, argument schema conformance, and redundant call count.
4. **Layer 4 — Trajectory**: Loop detection, recovery after errors, step efficiency, and task completion.
5. **Layer 5 — Operational Safety**: 8 deterministic invariant checks (S1–S8, including S2 against fabricated quotes and S3 against invented offsets).
6. **Layer 6 — Efficiency**: Latency, request budget, and input/output/hidden reasoning token counts.

---

## 📊 Current State & Baseline Findings

Milestone 1 baseline sweep is complete on dataset `v1` (run `baseline_v1-20261002T092914Z`, model `gemini-3.5-flash-lite`, prompt `p1`, 140 cases, 0 voided, 0 `NO_ANSWER`).

### Comparison Across Baselines (140-Case Sample)

REF-2 is run `ref2_single_shot-20261017T150310Z` (same model and settings as the agent, one call per case, no tools; 140 measured, 0 voided). Full tables: [results/processed/references-v1-s7-n20.md](results/processed/references-v1-s7-n20.md).

| Metric | REF-0 (Majority Class) | REF-1 (Deterministic Regex) | REF-2 (Single Shot, no tools) | Agent v1 (`p1`, Flash-Lite) |
|---|---|---|---|---|
| **Status accuracy** (120 strict cases) | 80/120 (67%) | 100/120 (83%) | **109/120 (91%)** | 101/120 (84%) |
| **Full case pass** (all checks) | 0/120 (0%) | **100/120 (83%)** | 43/120 (36%) | 69/120 (58%) |
| **False positives** (findings) | 0 | **0** | 26 | **0** |
| **Finding recall** | 0.00 | 0.75 | **0.90** | 0.76 |
| **Evidence accuracy** | undefined | **1.00** | 0.00 (quotes verbatim, offsets all wrong) | 0.28 |
| **Safety violations** | **0** | **0** | 96 (mostly S3 offsets) | 46 (38 are S3 invented offsets) |
| **Contradictory docs resolved** | 20/20 (guessed) | 0/20 (missed) | **20/20** | 1/20 (answers COMPLIANT) |
| **Model calls / tokens** (140 cases) | 0 | 0 | 140 / 152k | 1,609 / 2.33M |

> [!IMPORTANT]
> **Key Insight for Post 1:** REF-1 (a simple regex checker with no LLM) outperforms the LLM agent on full case pass (100 vs 69) and safety (0 vs 46 violations). The LLM agent quotes verbatim from the correct section, but frequently hallucinates character offsets (Safety Check S3).
>
> **REF-2 vs the agent:** one model call with the whole document gets the status right more often (109 vs 101) and catches every contradiction (20/20 vs 1/20) at about 1/15 of the tokens. The agent's tools buy precision (0 vs 26 false positives) and better evidence: without tools, REF-2 cannot report correct offsets. REF-2 also often wrote section IDs as `"4.1 Payment Terms"` instead of `"4.1"`; its pre-registered prompt did not specify the format, so the score stands. One trial per case on a synthetic, balanced set: an 8-case gap is suggestive, not established.

### Experiment A: prompt `p2` vs `p1` (133 of 140 cases measured)

Run `expA_p2-20261017T200247Z`, pre-registered 2026-10-18. Only the prompt changed. 7 cases returned empty replies on every attempt and are voided (excluded from the headline, scored as failures in the sensitivity analysis). Full report: [docs/reports/expA-p1-vs-p2.md](docs/reports/expA-p1-vs-p2.md).

| Metric | `p1` | `p2` |
|---|---|---|
| Wasted first lookup `lookup_policy("POL-001")` | 145 of 145 traces | **0 of 133** |
| Status accuracy (114 strict cases, voids excluded) | **95/114** | 74/114 |
| Unparseable answers (`NO_ANSWER`) | 0 | 34 |
| S3 invented offsets | 38 cases | 19 cases (20 of 83 vs 10 of 83 where `p2` answered) |
| Contradictory docs correct | 0/19 | 2/19 |
| False positives | 0 | 0 |
| Tokens | 2.19M | 3.08M |

> [!IMPORTANT]
> **Reading:** the `p2` instructions fix the tool-contract fault and halve invented offsets, but the prompt makes the output format unreliable. All 23 cases that got worse are cases where `p2` gave no parseable answer. Where it answered, its status was right slightly more often than `p1` on the same cases (74 vs 72 of 83). The next experiment should target output reliability.

---

## ⚡ Guiding Rules & Principles

1. **Design before results (spec §2):** Never change an evaluation definition or prompt to fix a bad score. Every modification must be logged in [`docs/decisions/decisions.md`](docs/decisions/decisions.md).
2. **Immutable results & append-only records:** Trial rows in `results/raw/` are append-only; the last row per `(case_id, trial_id)` wins.
3. **Model pinning (spec §6.4):** No `-latest` or `-preview` aliases. The exact version reported by the provider is recorded per trial.
4. **Reproducibility & thinking tokens:** Gemini 3.x enforces a minimum thinking floor (`thinking_level: MINIMAL`). Reasoning tokens are charged, never returned in text, and logged explicitly in traces.
5. **Signed-off dataset integrity:** Dataset sign-off binds the SHA-256 of `ground_truth.jsonl`. Regenerating the dataset invalidates the sign-off.

---

## 🛠️ Developer Quickstart & Setup

### Environment Setup

Pinned to Python 3.11 via `.python-version` and managed with `uv`:

```bash
uv sync
uv run pytest -q    # runs all unit tests with mock clients (200 passed, no API key required)
```

### Running Experiments

Set your Google AI Studio API key in the shell:

```bash
export GOOGLE_API_KEY=...
```

#### 1. Validate configuration and sign-off without calling the model:
```bash
uv run python -m experiments.run_baseline \
  --config experiments/configs/baseline_v1.yaml \
  --resume baseline_v1-20261002T092914Z \
  --dry-run
```

#### 2. Run the deterministic reference baselines (REF-0 and REF-1):
```bash
uv run python -m experiments.run_references \
  --dataset v1 \
  --cases-per-category 20 \
  --sample-seed 7 \
  --prefer-run baseline_v1-20261002T092914Z
```

#### 3. Run repeatability trials (28-case stratified subset, 3 trials each):
```bash
uv run python -m experiments.run_baseline \
  --config experiments/configs/baseline_v1.yaml \
  --resume baseline_v1-20261002T092914Z \
  --repeat-per-category 4 \
  --repeat-trials 3
```

---

## 🗺️ Project Roadmap & Next Steps

- [x] **Step 1:** Run REF-0 and REF-1 on the 140-case sample to establish like-for-like baselines.
- [x] **Step 2:** Repeatability trials — 28-case stratified subset, trials 2 & 3: status agreed on 27/28 cases.
- [x] **Step 3:** Milestone 1 formal one-page report (spec §29): [docs/reports/milestone-1-report.md](docs/reports/milestone-1-report.md).
- [x] **Step 4:** REF-2 single-shot baseline on the 140-case sample (pre-registered in decisions.md, 2026-10-17): run `ref2_single_shot-20261017T150310Z`.
- [x] **Step 5:** Experiment A — Prompt `p2`: run `expA_p2-20261017T200247Z`, 133 of 140 measured. Wasted lookup gone, S3 halved, but 34 unparseable answers and net status accuracy fell (95/114 to 74/114). Report: [docs/reports/expA-p1-vs-p2.md](docs/reports/expA-p1-vs-p2.md). A follow-up on output reliability is a separate experiment to pre-register.
- [ ] **Step 6:** Experiment C — Cross-family comparator (`gemma-4-31b-it`).
- [ ] **Step 7:** Judge study (LLM judge vs deterministic evaluator vs human audit; spec §18–20), with two human reviewers or the limitation published.
- [ ] **Step 8:** Automated CI evaluation tiers (spec §22).
- [ ] **Step 9:** Statistics and findings table (spec §24).

---

## 📁 Repository Layout

```
agent/          Agent loop, prompt templates (p1), JSON tools (t1), schemas
analysis/       Scripts for evidence digest and clustered bootstrap aggregation
baselines/      Reference baselines: REF-0 (majority class), REF-1 (regex rules), REF-2 (single shot)
dataset/        Synthetic case generator, policies (POL-001), ground truth
docs/           Authoritative spec, decision log, walkthrough, and archives
evaluation/     Deterministic, evidence, safety (S1-S8), trajectory evaluators
experiments/    Runner scripts (run_baseline, run_references), sampling, configs
results/        Committed raw trials.jsonl, execution traces, and processed reports
tests/          Complete test suite verifying evaluators, schemas, and runners
```
