# Document Compliance Reviewer — AI Agent Evaluation Experiment

A small, reproducible AI agent that reviews plain-text documents against a compliance
policy.

**The agent is not the product. The measurement is.** This repository is a controlled experimental
system for investigating how AI agents should be evaluated: what counts as success, how to evaluate
tool use and trajectories, when deterministic evaluators suffice, when an LLM judge helps, how
reliable that judge is, and how agent evaluation fits into CI/CD. It supplies the evidence for an
eight-part blog series on AI agent evaluation.

## Read first

| Document | Role |
|---|---|
| [docs/implementation-spec-v2.md](docs/implementation-spec-v2.md) | **Authoritative.** Build from this. |
| [docs/experiment-design.md](docs/experiment-design.md) | Original design (v1). Historical intent only. |
| [docs/decisions.md](docs/decisions.md) | Append-only log of post-v2 changes. |

Where v1 and v2 disagree, v2 wins. Appendix A of the spec maps every correction.

## Two rules that govern all work here

1. **Design before results** (spec §2). Schemas, metric denominators, matching rules, gate
   thresholds and reporting limits are fixed in the spec *before* data is generated. Never change a
   definition because a result looked bad. If a definition is genuinely wrong, fix it, log it in
   `docs/decisions.md`, and re-run the affected configurations from scratch.
2. **Every quantitative claim is traceable** to `experiment_id` + `dataset_version` +
   `agent_version`. No invented numbers, no hypothetical results presented as experimental ones.

## Layout

```
agent/        the visible Python agent loop, prompts, tools, schemas
baselines/    non-agent reference baselines (majority class, regex, single-shot)
dataset/      generator, policies, generated cases + ground truth
evaluation/   deterministic / safety / trajectory / deepeval / judges
experiments/  one config file per experiment
results/      raw traces and trial rows (append-only), processed tables
analysis/     notebooks and scripts
tests/        unit tests, incl. evaluator tests against hand-built fixtures
```

## Setup

```bash
uv sync
uv run pytest
```

`uv sync` installs the project in editable mode, so every command below runs from the repository
root with no `PYTHONPATH` prefix. `requirements.txt` is kept in step with `pyproject.toml` for
anyone without uv (`pip install -e .` then `pip install pytest`).

Inference uses the Google AI Studio free tier (spec §6.3). Set the API key in the environment; it
is never stored in the repository or in a result row:

```bash
export GOOGLE_API_KEY=...
```

A model is required only from step 8 of Milestone 1 onward (the agent loop). Steps 0–7 — schemas,
tools, dataset generation, dataset validation, deterministic evaluators, and the two no-LLM
reference baselines — need no key and no network. That ordering is deliberate: the evaluators are
proven against cases whose answers are already known, before the agent exists.

## Status

Milestone 1, steps 0-7 complete. No LLM involved yet.

| Step | State |
|---|---|
| 0 scaffold | done |
| 1 schemas and invariants | done |
| 2 policy `POL-001`, 5 rules | done |
| 3 section splitter and 4 tools | done |
| 4 generator, dataset `v1-m1`, 14 cases | done |
| 5 dataset validation | done: automated gate passed, signed off 2026-10-01, hash verified |
| 6 deterministic, evidence and safety evaluators | done |
| 7 REF-0 and REF-1 reference baselines | done |
| 8 agent loop | built and unit tested against a scripted client; not yet run against the live model |

Reference results on `v1-m1`: `results/processed/references-v1-m1.md`. The sign-off is bound to the
sha256 of `ground_truth.jsonl`, so regenerating the dataset invalidates it and the runner stops
treating the output as reportable.

Next action: run step 8 against the live model and record per-case wall clock for the §7 runtime
gate.

```bash
export GOOGLE_API_KEY=...
uv run python -m experiments.run_baseline --config experiments/configs/baseline_v1.yaml --dry-run
uv run python -m experiments.run_baseline --config experiments/configs/baseline_v1.yaml --limit 2
uv run python -m experiments.run_baseline --config experiments/configs/baseline_v1.yaml
```

The loop itself is tested with `ScriptedClient`, so the whole suite runs with no key and no network.
That is deliberate: a malformed reply, an unauthorized tool call, a step-limit overrun and a quota
rejection are not reproducible on demand against a real model, so testing them against one would
mean not testing them at all.

See spec §29 for the milestone sequence.

Provider note: the experiment originally specified local inference via Ollama. It moved to a hosted
free tier before any LLM trial was run; `docs/decisions.md` records the change and spec §6.3 states
what it costs, most importantly that a hosted model alias can be re-pointed at new weights, so every
trial records the `model_version` the API reports back.
