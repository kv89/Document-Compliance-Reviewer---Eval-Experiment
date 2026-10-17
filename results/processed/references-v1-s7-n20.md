# Reference baselines — dataset `v1` — 20 cases/category (seed 7)

> Dataset sign-off verified: signed off by Vishal Kalaskar (mail.vishaldk@gmail.com).

> **Sampled run.** 20 cases per category (seed 7, case order aligned to run `baseline_v1-20261002T092914Z`). This matches the agent baseline sample so that like-for-like comparison is possible (docs/decisions/decisions.md, 2026-10-12).

REF-0 and REF-1 are deterministic and use no model. REF-2, when present, is one model call per case with no tools. They exist to give the agent's numbers something to be measured against (spec section 15.1).

## ref0_majority — Majority class, always NON_COMPLIANT, reads nothing

- executions: 140 over 140 cases
- strict stratum: 120 cases
- accept-set stratum: 20 cases, reported separately
- safety violations: **0** (a count, never a rate)
- safety checks skipped for want of a trace: S1, S6, S8 — skipped, not passed
- trial consistency: not measurable, one trial per case

### Strict stratum

| metric | value | denominator |
|---|---|---|
| status accuracy | 80/120 | strict executions |
| findings exact (strict types) | 40/120 | strict executions |
| findings exact (ignoring type) | 40/120 | strict executions |
| full case pass | 0/120 | strict executions |
| finding precision | undefined | 0 cases where it is defined |
| finding recall | 0.00 [0.00, 0.00] (n=80) | 80 cases where it is defined |
| evidence accuracy | undefined | 0 cases where it is defined |
| true positives / false positives / false negatives | 0 / 0 / 100 | findings |
| fabricated evidence (S2) | 0 | count |

### Per category

| category | cases | status correct | full pass | reportable as a percentage |
|---|---|---|---|---|
| ambiguous | 20 | 20/20 | 0/20 | yes |
| compliant | 20 | 0/20 | 0/20 | yes |
| contradictory | 20 | 20/20 | 0/20 | yes |
| distractor | 20 | 0/20 | 0/20 | yes |
| incorrect_value | 20 | 20/20 | 0/20 | yes |
| missing_clause | 20 | 20/20 | 0/20 | yes |
| multiple_violations | 20 | 20/20 | 0/20 | yes |

Counts only where a category has fewer than 20 cases. Percentages at that sample size would not survive their own confidence interval.

### Accept-set stratum (ambiguous cases)

- status within the accepted set: 20/20
- matched one accepted answer exactly: 0/20
- excluded from the strict aggregates above by design (spec section 8.3)

### Efficiency

- tool calls: 0 total
- model calls: 0 total
- tokens: 0 total
- latency: not meaningful for a baseline that performs no inference

## ref1_regex — Deterministic rule check, no LLM

- executions: 140 over 140 cases
- strict stratum: 120 cases
- accept-set stratum: 20 cases, reported separately
- safety violations: **0** (a count, never a rate)
- safety checks skipped for want of a trace: S1, S6, S8 — skipped, not passed
- trial consistency: not measurable, one trial per case

### Strict stratum

| metric | value | denominator |
|---|---|---|
| status accuracy | 100/120 | strict executions |
| findings exact (strict types) | 100/120 | strict executions |
| findings exact (ignoring type) | 100/120 | strict executions |
| full case pass | 100/120 | strict executions |
| finding precision | 1.00 [1.00, 1.00] (n=60) | 60 cases where it is defined |
| finding recall | 0.75 [0.65, 0.84] (n=80) | 80 cases where it is defined |
| evidence accuracy | 1.00 [1.00, 1.00] (n=40) | 40 cases where it is defined |
| true positives / false positives / false negatives | 80 / 0 / 20 | findings |
| fabricated evidence (S2) | 0 | count |

### Per category

| category | cases | status correct | full pass | reportable as a percentage |
|---|---|---|---|---|
| ambiguous | 20 | 11/20 | 11/20 | yes |
| compliant | 20 | 20/20 | 20/20 | yes |
| contradictory | 20 | 0/20 | 0/20 | yes |
| distractor | 20 | 20/20 | 20/20 | yes |
| incorrect_value | 20 | 20/20 | 20/20 | yes |
| missing_clause | 20 | 20/20 | 20/20 | yes |
| multiple_violations | 20 | 20/20 | 20/20 | yes |

Counts only where a category has fewer than 20 cases. Percentages at that sample size would not survive their own confidence interval.

### Accept-set stratum (ambiguous cases)

- status within the accepted set: 11/20
- matched one accepted answer exactly: 11/20
- excluded from the strict aggregates above by design (spec section 8.3)

### Efficiency

- tool calls: 0 total
- model calls: 0 total
- tokens: 0 total
- latency: not meaningful for a baseline that performs no inference

Run `ref2_single_shot-20261017T150310Z`. Model `gemini-3.5-flash-lite`, reported version `gemini-3.5-flash-lite`, temperature 0.0, seed 7, thinking level `MINIMAL`, prompt `ref2`, no tools.

## ref2_single_shot — Single LLM call, full document in prompt, no tools

- executions: 140 over 140 cases
- strict stratum: 120 cases
- accept-set stratum: 20 cases, reported separately
- safety violations: **96** (a count, never a rate)
- safety checks skipped for want of a trace: S1, S6, S8 — skipped, not passed
- trial consistency: not measurable, one trial per case

### Strict stratum

| metric | value | denominator |
|---|---|---|
| status accuracy | 109/120 | strict executions |
| findings exact (strict types) | 62/120 | strict executions |
| findings exact (ignoring type) | 78/120 | strict executions |
| full case pass | 43/120 | strict executions |
| finding precision | 0.80 [0.72, 0.86] (n=91) | 91 cases where it is defined |
| finding recall | 0.90 [0.86, 0.94] (n=80) | 80 cases where it is defined |
| evidence accuracy | 0.00 [0.00, 0.00] (n=54) | 54 cases where it is defined |
| true positives / false positives / false negatives | 84 / 26 / 16 | findings |
| fabricated evidence (S2) | 0 | count |

### Per category

| category | cases | status correct | full pass | reportable as a percentage |
|---|---|---|---|---|
| ambiguous | 20 | 14/20 | 0/20 | yes |
| compliant | 20 | 16/20 | 16/20 | yes |
| contradictory | 20 | 20/20 | 0/20 | yes |
| distractor | 20 | 13/20 | 13/20 | yes |
| incorrect_value | 20 | 20/20 | 0/20 | yes |
| missing_clause | 20 | 20/20 | 14/20 | yes |
| multiple_violations | 20 | 20/20 | 0/20 | yes |

Counts only where a category has fewer than 20 cases. Percentages at that sample size would not survive their own confidence interval.

### Accept-set stratum (ambiguous cases)

- status within the accepted set: 14/20
- matched one accepted answer exactly: 0/20
- excluded from the strict aggregates above by design (spec section 8.3)

### Efficiency

- tool calls: 0 total
- model calls: 140 total
- tokens: 152349 total
- latency: median 1418 ms, p95 2241 ms
