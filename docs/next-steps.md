# Next steps after the baseline sweep

Replaces the earlier list, whose steps 1-5 and 7 are done. Scope and order of the sweep are
recorded in `docs/decisions.md`, 2026-10-09.

## Where the run stands (2026-10-12)

The 140-case sample is complete and verified: run `baseline_v1-20261002T092914Z`, 20 cases in each of
7 categories, 0 voided trials, 0 `NO_ANSWER`, no "Incomplete run" banner. Strict stratum: status
accuracy 101/120, full case pass 69/120, evidence accuracy 0.28, 46 safety violations (38 are S3,
invented char offsets). Report: `results/processed/baseline_v1-20261002T092914Z.md`.

No daily resume is needed any more. If a re-run is ever required, use
`--resume baseline_v1-20261002T092914Z` (it reports 0 cases to run) or a new run id.

## After the sweep

1. Done: report checked (140 executions, 20 per category, no banner).
2. Read the report with the known caveat in mind: the agent quotes evidence verbatim but invents
   `char_start`/`char_end` (safety check S3, evidence accuracy), and tends to answer `COMPLIANT`
   on contradictory documents. Do not "fix" `p1` to improve the number; a better prompt is a `p2`
   arm under Experiment A.
3. Re-run the reference baselines on the same sample if the results schema changed since they were
   last generated (`experiments.run_references`), so the comparison table is like for like.
4. Repeats for trial consistency: re-run a stratified 7 x 4 = 28 case subset twice more
   (about one extra day of quota). This needs a small change to the runner; decide before starting.
5. Write the one-page Milestone 1 report required by spec section 29.
6. Experiment C comparator (`gemma-4-31b-it`): first check that it accepts the JSON tool protocol
   (spec section 6.4). Its quota is a separate bucket, so it can run on the same days.
7. Collect the blog evidence set: `docs/decisions.md` (narrative), `docs/implementation-spec-v2.md`
   (method), `results/processed/*.md` and `results/raw/*/trials.jsonl` (numbers).

## Open housekeeping

- Records do not show which key or project each day used. If wanted, add a non-secret key
  fingerprint to the trace config (schema change, needs a decision-log entry).
