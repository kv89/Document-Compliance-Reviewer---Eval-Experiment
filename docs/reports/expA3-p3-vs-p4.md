# Experiment A3: prompt `p4` (tool-argument placement) against `p1`, `p2` and `p3`

Pre-registered in `docs/decisions/decisions.md` (2026-10-26). Model `gemini-3.5-flash-lite`, tools `t1`, `max_steps` 20, dataset `v1`, one trial per case, the 140 cases of the Experiment A sample. The only variable is `prompt_version`. `p4` is `p3` plus a tool-arguments section with one worked `lookup_policy` example; the `p3` text is a strict prefix of the `p4` system prompt and is pinned by a hash test.

- Arm A: `p1`, run `baseline_v1-20261002T092914Z`, trial 1.
- Arm B: `p2`, run `expA_p2-20261017T200247Z`.
- Arm C: `p3`, run `expA2_p3-20261025T120453Z`, closed at 136 of 140.
- Arm D: `p4`, run `expA3_p4-20261026T155432Z`, 140 of 140 measured, 0 voids.

> Diagnostic distribution: the dataset is synthetic and chosen to exercise each failure type. These are counts on that set, not prevalence in real documents. One trial per case; categories have 20 cases, so they are reported as counts only.

## Headline

`p4` removed the invalid first tool call (0 of 140 traces, against 136 of 136 for `p3`) and the S6 flags that came with it (0 against 133). Every case now has an answer, and strict status accuracy rose to 108 of 120, the best of the four arms. S3 (invented offsets) got worse.

## Run and voids

Voids are scored as `NO_ANSWER` failures in the headline. `p4` has none, so the headline and the exclusion analysis coincide.

| | `p1` | `p2` | `p3` | `p4` |
|---|---|---|---|---|
| cases in the sample | 140 | 140 | 140 | 140 |
| measured trials | 140 | 133 | 136 | 140 |
| voided (final) | 0 | 7 | 4 | 0 |
| `NO_ANSWER` among measured | 0 | 34 | 3 | 0 |

The run stopped once on `DAILY_QUOTA_EXHAUSTED` (2026-10-26, 18:07Z) and was resumed with `--resume`. Its file holds 148 lines for 140 cases: 8 superseded void rows (4 `EMPTY_RESPONSE`, 4 `DAILY_QUOTA_EXHAUSTED`), each retried and measured on resume.

## Pre-registered hypothesis

| Hypothesis | `p3` | `p4` | Result |
|---|---|---|---|
| First tool call fails in 10% or less of measured traces | 136 of 136 | 0 of 140 | Held |

All 140 `p4` traces open with `{"tool": "lookup_policy", "arguments": {"rule_id": "CLAUSE-P...` as a successful call. The 10% threshold was set by judgement, not derived from data (decision log, 2026-10-26).

## Guardrails

| Guardrail | `p1` | `p2` | `p3` | `p4` |
|---|---|---|---|---|
| `NO_ANSWER` plus voids (of 140) | 0 | 41 | 7 | 0 |
| Strict status accuracy (of 120, voids as failures) | 101 | 74 | 102 | 108 |
| Contradictory cases correct (of 20) | 1 | 2 | 7 | 8 |
| Accept-set, ambiguous (of 20) | 14 | 12 | 17 | 20 |
| S3 cases (measured) | 38 | 19 | 24 | 39 |
| S6 cases | 0 | 0 | 133 | 0 |
| Offsets consistent with the quote | 21/64 | 23/42 | 39/67 | 35/78 |
| False-positive cases | 0 | 0 | 0 | 0 |
| Cases ending at `max_steps` | 0 | 0 | 0 | 0 |
| Model calls (measured) | 1,609 | 1,635 | 1,791 | 1,839 |
| Tokens (measured) | 2,327,635 | 3,080,554 | 3,699,959 | 4,030,874 |
| Tokens per measured trial | 16,626 | 23,162 | 27,206 | 28,792 |

Output validation (valid / repaired / unparseable): `p1` 129 / 11 / 0, `p2` 51 / 48 / 34, `p3` 96 / 37 / 3, `p4` 115 / 25 / 0.

S3 on a like-for-like set, the 94 cases answered by all four arms: `p1` 24, `p2` 18, `p3` 15, `p4` 19. On the 133 cases answered by both `p3` and `p4`: `p3` 24, `p4` 35. By category, the 39 `p4` S3 cases are ambiguous 13, incorrect_value 10, multiple_violations 10, contradictory 6.

Tokens per measured trial are 73% above `p1` and 6% above `p3`, computed as ratios of the per-trial means.

## Paired by case (strict stratum, 120, voids as failures)

| | cases |
|---|---|
| `p4` correct, `p3` wrong (improved) | 7 |
| `p3` correct, `p4` wrong (worsened) | 1 |
| `p4` correct, `p1` wrong (improved) | 7 |
| `p1` correct, `p4` wrong (worsened) | 0 |
| `p4` correct, `p2` wrong (improved) | 35 |
| `p2` correct, `p4` wrong (worsened) | 1 |

Against `p3`: 5 of the 7 improvements are cases `p3` gave no answer for (DOC-0064, 0069, 0072, 0083, 0159); 2 are contradictions (DOC-0121, DOC-0125). The one worsened case is DOC-0101, a contradiction that `p4` answered `COMPLIANT`. Against `p1`, all 7 improvements are contradictory documents (DOC-0105, 0107, 0111, 0117, 0121, 0123, 0125).

## By category (status correct, voids as failures)

Counts only.

| category | cases | `p1` | `p2` | `p3` | `p4` |
|---|---|---|---|---|---|
| compliant | 20 | 20 | 17 | 20 | 20 |
| contradictory | 20 | 1 | 2 | 7 | 8 |
| distractor | 20 | 20 | 14 | 19 | 20 |
| incorrect_value | 20 | 20 | 15 | 17 | 20 |
| missing_clause | 20 | 20 | 16 | 20 | 20 |
| multiple_violations | 20 | 20 | 10 | 19 | 20 |
| ambiguous (accept-set) | 20 | 14 | 12 | 17 | 20 |

## Reading

1. The example works for its purpose. The invalid first call and the S6 flags are gone, so the wasted model call per case that `p3` made is no longer made.
2. Removing that fault coincided with every case getting an answer. Whether the example also fixed the 3 unparseable answers and 4 empty replies of `p3` is not established: one trial per case, and empty replies at temperature 0 are deterministic per prompt, so a changed prompt can move them either way.
3. Contradictions remain the weakest category: 12 of 20 not correct.
4. S3 is now the largest remaining fault. It is level with `p1` in total (39 against 38) and 35 against 24 on the cases both `p3` and `p4` answered. Offsets are consistent for 35 of 78 quotes checked (45%). The cause is unproven; this experiment changed only the tool-arguments section.
5. The cost is 73% more tokens per trial than `p1` for 7 more strict-correct cases, all contradictions.

Suggested next steps, to be pre-registered separately if pursued: an experiment on offset correctness (S3), or the cross-family comparator (Experiment C) with `p4` as the prompt.

## Deviations and infrastructure notes

- 2026-10-26: pre-registration. Voids scored as failures in the headline, as in Experiment A2.
- The run stopped on the daily quota after 30 measured trials and was resumed after the quota reset. No settings changed between the two sessions.
- Model calls took 12 to 80 s each while the API was slow (median 24.9 s on the first 3 trials, against 1.3 s in earlier runs). This changed the wall time, not any recorded row.
