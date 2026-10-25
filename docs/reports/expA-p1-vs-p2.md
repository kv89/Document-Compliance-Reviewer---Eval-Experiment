# Experiment A: prompt `p1` vs `p2`

Pre-registered in `docs/decisions/decisions.md` (2026-10-18). Model `gemini-3.5-flash-lite`, tools `t1`, `max_steps` 20, dataset `v1`, one trial per case. The only variable is `prompt_version`.

- Arm A: `p1`, run `baseline_v1-20261002T092914Z`, trial 1.
- Arm B: `p2`, run `expA_p2-20261017T200247Z`, the 140 cases of arm A's sample.

> Diagnostic distribution: the dataset is synthetic and chosen to exercise each failure type. These are counts on that set, not prevalence in real documents. Categories have fewer than 20 cases, so they are reported as counts only.

## Headline

`p2` fixed the tool-contract fault and reduced invented offsets, but it made the output format unreliable, and net status accuracy fell from 95/114 to 74/114.

All 23 cases that got worse are cases where `p2` gave no parseable answer. Where `p2` did answer (83 strict cases), its status was correct on 74, against 72 for `p1` on the same cases.

## Run and voids

| | `p1` | `p2` |
|---|---|---|
| cases in the sample | 140 | 140 |
| measured trials | 140 | 133 |
| voided (final) | 0 | 7 |

The 7 `p2` voids are `EMPTY_RESPONSE`: the model returned no text at the same step on every attempt (2 to 8 attempts each, at temperature 0). Cases: DOC-0014, DOC-0035, DOC-0049, DOC-0113, DOC-0143, DOC-0162, DOC-0170. Finish reason `MALFORMED_FUNCTION_CALL` for 4, `STOP` for 3. The run was closed at 133 measured before this comparison was run (decision log, 2026-10-21).

The pre-registered analysis below excludes these 7 cases from both arms (133 cases, strict stratum 114). The sensitivity analysis scores them as `NO_ANSWER` failures.

## Pre-registered hypotheses

| Hypothesis | `p1` | `p2` | Result |
|---|---|---|---|
| Wasted first call `lookup_policy("POL-001")` falls to about 0 | 145 of 145 traces | 0 of 133 | Held |
| Correct evidence offsets become the majority | 20 of 63 quotes | 23 of 42 quotes | Held, on fewer quotes (see below) |
| S3 violations fall | 38 cases | 19 cases | Held, confounded (see below) |
| Contradictory cases with correct status rise | 0 of 19 | 2 of 19 | Not meaningful: 2 cases |

S3 and the offset check need a parsed answer. The 34 `NO_ANSWER` cases of `p2` have S1 to S8 skipped, not passed. The fair comparison is on cases where `p2` answered: S3 on 20 of 83 for `p1` and 10 of 83 for `p2`.

## Guardrails

| Guardrail | `p1` | `p2` |
|---|---|---|
| False positives | 0 | 0 |
| Strict status accuracy | 95/114 | 74/114 |
| Unparseable answers (`NO_ANSWER`) | 0 | 34 |
| Cases ending at `max_steps` | 0 | 0 |
| Model calls | 1,521 | 1,635 |
| Tokens | 2,193,720 | 3,080,554 (+40%) |

`p2` output validation (133 cases): 51 valid, 48 repaired, 34 unparseable. `p1` (145 cases): 133 valid, 12 repaired, 0 unparseable.

The accept-set stratum (ambiguous, 19 cases, reported separately): status within the accepted set 14 for `p1`, 12 for `p2`.

## Paired by case (strict stratum, 114)

| | cases |
|---|---|
| `p2` correct, `p1` wrong (improved) | 2 |
| `p1` correct, `p2` wrong (worsened) | 23 |
| of the worsened, `p2` gave no parseable answer | 23 |

## By category (status correct, `p1` / `p2`)

Counts only.

| category | cases | `p1` | `p2` | `p2` no answer |
|---|---|---|---|---|
| compliant | 19 | 19 | 17 | 2 |
| contradictory | 19 | 0 | 2 | 8 |
| distractor | 18 | 18 | 14 | 4 |
| incorrect_value | 20 | 20 | 15 | 5 |
| missing_clause | 18 | 18 | 16 | 2 |
| multiple_violations | 20 | 20 | 10 | 10 |

The "no answer" column includes the accept-set cases, so it sums to 34 with 3 ambiguous cases.

## Sensitivity: the 7 voids scored as `NO_ANSWER` failures

140 cases, strict stratum 120.

| | `p1` | `p2` |
|---|---|---|
| strict status accuracy | 101/120 | 74/120 |
| `NO_ANSWER` | 0 | 41 |
| improved / worsened (paired) | | 2 / 29 |
| tokens | 2,327,635 | 3,162,258 |

The conclusion does not change.

## Reading

1. The prompt content works. The wasted lookup is gone, `p2` agents search the whole document before declaring a rule satisfied, and invented offsets fall by about half among answered cases.
2. The prompt also destabilises the output format. The 34 unparseable answers are the model's own text: fake "Result of …" tool output, Python-style dicts instead of JSON, prose, or junk tokens. The 7 voids are empty replies. Both are measured results of `p2`, not harness faults.
3. Contradictions remain a weakness: 2 of 19 correct, and 8 more got no answer.
4. The cost is 40% more tokens for a worse net result.

Suggested next experiment, to be pre-registered separately: keep the `p2` instructions and target output reliability.

## Deviations and infrastructure notes

Decision-log entries made during the run, none changing a recorded row:

- 2026-10-18: parser-fault stop rule excludes model output; void counts reported per arm; sensitivity analysis added.
- 2026-10-21: sensitivity analysis covers every repeated `EMPTY_RESPONSE`, whatever the finish reason; run closed at 133.
- 2026-10-20 and 2026-10-21: 120 s request timeout; empty responses retried once.
- The sweep was repeatedly stalled by the laptop sleeping, which produced timeout and disconnect voids. These were retried and are not scored.
