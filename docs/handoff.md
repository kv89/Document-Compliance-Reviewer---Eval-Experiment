# Handoff: continue this work on another machine

Read this first on a new laptop. It holds what the repository does not make obvious: what is
finished, what must be set up by hand, and what to do next. Written 2026-10-12.

## What this project is

A controlled experiment on how to evaluate an AI agent, not a product. The agent reviews contract
text against a policy (`POL-001`, 5 rules). Results feed an eight-part blog series. The spec is
`docs/implementation-spec-v2.md` (authoritative); post-spec changes are in `docs/decisions.md`.

## State on 2026-10-12

- Milestone 1 is done: schemas, tools, dataset `v1` (175 cases, signed off, hash verified),
  deterministic/evidence/safety evaluators, REF-0 and REF-1, agent loop.
- Baseline sweep is done: run `baseline_v1-20261002T092914Z`, 140 trials (20 per category, seed 7,
  1 trial each), 0 voided, model `gemini-3.5-flash-lite`, prompt `p1`.
- Results: `results/processed/baseline_v1-20261002T092914Z.md`. Raw rows and traces are in `results/raw/` and `results/traces/`.
- Blog numbers: `docs/blog-evidence.md`, generated from the rows by
  `analysis/scripts/evidence_digest.py` (re-run it; do not type numbers by hand).

## Findings so far (all counts, on a synthetic diagnostic set)

- Strict stratum 120 cases: status 101/120, full pass 69/120, evidence accuracy 0.28, 46 safety
  violations. REF-1 (regex, no LLM) beat the agent on the 14-case set (full pass 10/12 vs 6/12).
- Invented offsets: 38 trials violate S3. The agent cites the right section and quotes verbatim,
  then reports `char_start`/`char_end` that do not match, although the tool returned correct ones.
- Contradictory documents: status correct on 1 of 20. The agent says `COMPLIANT`.
- Every one of the 140 traces starts with the same wasted call, `lookup_policy(rule_id="POL-001")`,
  which returns `UNKNOWN_RULE`. About one request in eleven.
- S2 (fabricated quote) and S1: 2 trials each, the same two cases (DOC-0081, DOC-0083).

## Set up on the new machine

| Item | How |
|---|---|
| Python 3.11.9 and `uv` | `.python-version` pins it; `uv sync` builds `.venv` from `uv.lock`. |
| `GOOGLE_API_KEY` | Google AI Studio key, exported in the shell. Never stored in the repo. The daily free quota is per project, not per key. |
| Claude Code context | Nothing from the earlier chat transfers. This file and `decisions.md` are the memory. |

```bash
uv sync
uv run pytest -q                      # expect 193 passed, no key, no network
uv run python -m experiments.run_baseline --config experiments/configs/baseline_v1.yaml \
  --dry-run --resume baseline_v1-20261002T092914Z    # expect: sign-off verified, 0 cases to run
```

## Rules and gotchas worth knowing

- Design before results. Never change a definition because a result looked bad; log changes in
  `docs/decisions.md` and re-run what they affect. Prompt `p1` is pre-registered: improvements go
  in a `p2` arm under Experiment A.
- Pin model names. No `-latest` or `-preview`. Record the model version the API reports.
- Free tier: about 11.5 requests per trial and roughly 29 trials a day. Quota stops are expected.
  Use `--resume <run_id>`; it keeps measured rows and retries voided ones.
- Dataset order is by category. Never run it front to back; `experiments/sampling.py` interleaves.
- The dataset sign-off is bound to the sha256 of `ground_truth.jsonl`. Regenerating the dataset
  invalidates it.
- Rows are append-only; the last row per (case, trial) wins.
- Thinking cannot be switched off on Gemini 3.x (`thinking_level: MINIMAL` is the floor).
- Every post that quotes an aggregate must state the diagnostic-distribution caveat (spec 25).

## Next steps

1. REF-0 and REF-1 on the same 140-case sample. The reference results on file are the 14-case set.
   `experiments/run_references.py` takes only `--dataset` and runs every case in it (175 for `v1`),
   so first add a sample filter that reuses `select_cases(cases, 20, 7, prefer=<measured ids>)`
   from `experiments/sampling.py`, with `prefer` taken from the baseline run's rows. Then run
   `uv run python -m experiments.run_references --dataset v1`. Needs no key and no network.
   Add a test, and a `decisions.md` entry if the report format changes. Then build REF-2
   (single-shot model call, about 140 requests, needs the key).
2. Repeats for consistency: 28-case stratified subset, two more trials (needs a decision-log entry,
   since the spec asks for 3 trials per case).
3. One controlled change: Experiment A, prompt `p2`, aimed at the offset failure and the wasted
   first lookup. Pre-register in `decisions.md` before running.
4. Judge study (spec 18-20) and two human reviewers (or publish the limitation).
5. CI tiers (spec 22): Tier 1 on every commit, Tier 2 smoke on PR, Tier 3 on dispatch.
6. Statistics and findings table (spec 24); optional Gemma comparator (Experiment C).

Blog readiness: posts 2 and 3 can be drafted now, post 1 after step 1, posts 4-5 from real traces
(Experiment E would add a misuse signal), posts 6-8 after steps 3-5.

## Open decisions

- Key or project fingerprint in trace config, so records show which project each day used.
