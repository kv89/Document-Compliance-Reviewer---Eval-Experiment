# Experiment A2: prompt `p3` (output reliability) against `p1` and `p2`

Pre-registered in `docs/decisions/decisions.md` (2026-10-25). Model `gemini-3.5-flash-lite`, tools `t1`, `max_steps` 20, dataset `v1`, one trial per case, the 140 cases of the Experiment A sample. The only variable is `prompt_version`. `p3` is `p2` plus an output-format section; the `p2` text is a strict prefix of the `p3` system prompt.

- Arm A: `p1`, run `baseline_v1-20261002T092914Z`, trial 1.
- Arm B: `p2`, run `expA_p2-20261017T200247Z`.
- Arm C: `p3`, run `expA2_p3-20261025T120453Z`, closed at 136 of 140 (decision log, 2026-10-26).

> Diagnostic distribution: the dataset is synthetic and chosen to exercise each failure type. These are counts on that set, not prevalence in real documents. One trial per case; categories have 20 cases, so they are reported as counts only.

## Headline

`p3` fixed the output-format fault: unparseable answers and voids fell from 41 to 7 of 140, and strict status accuracy recovered from 74/120 (`p2`) to 102/120, level with `p1` (101/120). It kept the `p2` content gains on contradictions (7 of 20 correct, against 1 and 2). It brought back a wasted first tool call, with a different cause, and cost more tokens.

## Run and voids

All voids are scored as `NO_ANSWER` failures in the headline, as pre-registered. Void counts per arm:

| | `p1` | `p2` | `p3` |
|---|---|---|---|
| cases in the sample | 140 | 140 | 140 |
| measured trials | 140 | 133 | 136 |
| voided (final) | 0 | 7 | 4 |
| `NO_ANSWER` among measured | 0 | 34 | 3 |

The 4 `p3` voids are `EMPTY_RESPONSE`: DOC-0159 (4 attempts), DOC-0064 (4), DOC-0083 (3), all finish reason `STOP`, and DOC-0140 (2), finish reason `MALFORMED_FUNCTION_CALL`. DOC-0159 returned empty after the same 10 model calls and 18,198 tokens on every attempt.

## Pre-registered hypothesis

| Hypothesis | `p2` | `p3` | Result |
|---|---|---|---|
| `NO_ANSWER` plus voids fall to 10 or fewer of 140 | 41 | 7 (3 + 4) | Held |

The threshold of 10 was set by judgement, not derived from data (decision log, 2026-10-25).

## Guardrails

| Guardrail | `p1` | `p2` | `p3` |
|---|---|---|---|
| Strict status accuracy (120, voids as failures) | 101 | 74 | 102 |
| Strict correct among answered | 101/120 | 74/83 | 102/115 |
| False-positive cases | 0 | 0 | 0 |
| S3 cases (measured) | 38 | 19 | 24 |
| Cases ending at `max_steps` | 0 | 0 | 0 |
| Model calls (measured) | 1,609 | 1,635 | 1,791 |
| Tokens (measured) | 2,327,635 | 3,080,554 | 3,699,959 |
| Tokens per measured trial | 16,626 | 23,162 | 27,206 |

Output validation (valid / repaired / unparseable): `p1` 129 / 11 / 0, `p2` 51 / 48 / 34, `p3` 96 / 37 / 3.

S3 on a like-for-like set, the 94 cases answered by both `p2` and `p3`: `p1` 24, `p2` 18, `p3` 15. The unmatched totals above (19 and 24) differ because `p3` answered more cases.

Accept-set stratum (ambiguous, 20 cases, voids as failures): status within the accepted set 14 for `p1`, 12 for `p2`, 17 for `p3`.

## Paired by case (strict stratum, 120, voids as failures)

| | cases |
|---|---|
| `p3` correct, `p2` wrong (improved) | 33 |
| `p2` correct, `p3` wrong (worsened) | 5 |
| `p3` correct, `p1` wrong (improved) | 6 |
| `p1` correct, `p3` wrong (worsened) | 5 |

Against `p1`, all 6 improved cases are contradictory documents (DOC-0101, 0105, 0107, 0111, 0117, 0123). All 5 worsened cases are cases where `p3` gave no answer: 3 voids (DOC-0064, DOC-0083, DOC-0159) and 2 `NO_ANSWER` (DOC-0069, DOC-0072). A 6 against 5 split is not evidence of a difference.

## By category (status correct, voids as failures)

Counts only.

| category | cases | `p1` | `p2` | `p3` | `p3` no answer or void |
|---|---|---|---|---|---|
| compliant | 20 | 20 | 17 | 20 | 0 |
| contradictory | 20 | 1 | 2 | 7 | 0 |
| distractor | 20 | 20 | 14 | 19 | 1 |
| incorrect_value | 20 | 20 | 15 | 17 | 3 |
| missing_clause | 20 | 20 | 16 | 20 | 0 |
| multiple_violations | 20 | 20 | 10 | 19 | 1 |
| ambiguous (accept-set) | 20 | 14 | 12 | 17 | 2 |

Part of the contradictory gain over `p2` is recovery: `p2` had 9 of those 20 with no answer.

## A regression `p3` introduced

All 136 measured `p3` traces open with a failed tool call: `lookup_policy` with empty arguments, returning `INVALID_ARGUMENTS`. The model writes `{"tool": "lookup_policy", "rule_id": "CLAUSE-..."}` with `rule_id` outside `arguments`. `p2` had 0 such traces (the `p1` wasted lookup used the policy id as a rule id, a different fault). Safety check S6 (no malformed tool arguments) flags 133 `p3` cases; `p2` had none. The agent recovers on the next call and every affected trace still reaches an answer.

The cause has not been established. The only change from `p2` is the output-format section, so the section is the suspect, but no experiment has tested that.

## Reading

1. The output-format section works for its purpose. Unparseable answers fell from 34 to 3 and voids from 7 to 4, and the `p2` instruction gains are kept.
2. Net accuracy is back to `p1`'s level, with more contradictions caught (7 of 20) and no false positives. The cost is about 64% more tokens per measured trial than `p1`.
3. The wasted first call is back in a new form, and S6 now flags nearly every case. This is the next fault to isolate.
4. Contradictions are still mostly missed (13 of 20 not correct).

Suggested next experiment, to be pre-registered separately: keep `p3` and target the `rule_id`-outside-`arguments` fault.

## Deviations and infrastructure notes

- 2026-10-25: pre-registration. Unlike Experiment A, voids are scored as failures in the headline.
- 2026-10-26: run closed at 136 measured.
- The progress line now carries a UTC time, and `experiments/run_status.py` was added before the run. Neither changes a recorded row.
