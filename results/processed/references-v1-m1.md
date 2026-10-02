# Reference baselines — dataset `v1-m1`

> Dataset sign-off verified: signed off by Vishal Kalaskar (vishal.kalaskar@searce.com).

Both baselines are deterministic and use no model. They exist to give the agent's numbers something to be measured against (spec section 15.1).

## ref0_majority — Majority class, always NON_COMPLIANT, reads nothing

- executions: 14 over 14 cases
- strict stratum: 12 cases
- accept-set stratum: 2 cases, reported separately
- safety violations: **0** (a count, never a rate)
- safety checks skipped for want of a trace: S1, S6, S8 — skipped, not passed
- trial consistency: not measurable, one trial per case

### Strict stratum

| metric | value | denominator |
|---|---|---|
| status accuracy | 8/12 | strict executions |
| findings exact (strict types) | 4/12 | strict executions |
| findings exact (ignoring type) | 4/12 | strict executions |
| full case pass | 0/12 | strict executions |
| finding precision | undefined | 0 cases where it is defined |
| finding recall | 0.00 [0.00, 0.00] (n=8) | 8 cases where it is defined |
| evidence accuracy | undefined | 0 cases where it is defined |
| true positives / false positives / false negatives | 0 / 0 / 10 | findings |
| fabricated evidence (S2) | 0 | count |

### Per category

| category | cases | status correct | full pass | reportable as a percentage |
|---|---|---|---|---|
| ambiguous | 2 | 2/2 | 0/2 | no, n<20 |
| compliant | 2 | 0/2 | 0/2 | no, n<20 |
| contradictory | 2 | 2/2 | 0/2 | no, n<20 |
| distractor | 2 | 0/2 | 0/2 | no, n<20 |
| incorrect_value | 2 | 2/2 | 0/2 | no, n<20 |
| missing_clause | 2 | 2/2 | 0/2 | no, n<20 |
| multiple_violations | 2 | 2/2 | 0/2 | no, n<20 |

Counts only where a category has fewer than 20 cases. Percentages at that sample size would not survive their own confidence interval.

### Accept-set stratum (ambiguous cases)

- status within the accepted set: 2/2
- matched one accepted answer exactly: 0/2
- excluded from the strict aggregates above by design (spec section 8.3)

### Efficiency

- tool calls: 0 total
- model calls: 0 total
- tokens: 0 total
- latency: not meaningful for a baseline that performs no inference

## ref1_regex — Deterministic rule check, no LLM

- executions: 14 over 14 cases
- strict stratum: 12 cases
- accept-set stratum: 2 cases, reported separately
- safety violations: **0** (a count, never a rate)
- safety checks skipped for want of a trace: S1, S6, S8 — skipped, not passed
- trial consistency: not measurable, one trial per case

### Strict stratum

| metric | value | denominator |
|---|---|---|
| status accuracy | 10/12 | strict executions |
| findings exact (strict types) | 10/12 | strict executions |
| findings exact (ignoring type) | 10/12 | strict executions |
| full case pass | 10/12 | strict executions |
| finding precision | 1.00 [1.00, 1.00] (n=6) | 6 cases where it is defined |
| finding recall | 0.75 [0.38, 1.00] (n=8) | 8 cases where it is defined |
| evidence accuracy | 1.00 [1.00, 1.00] (n=4) | 4 cases where it is defined |
| true positives / false positives / false negatives | 8 / 0 / 2 | findings |
| fabricated evidence (S2) | 0 | count |

### Per category

| category | cases | status correct | full pass | reportable as a percentage |
|---|---|---|---|---|
| ambiguous | 2 | 1/2 | 1/2 | no, n<20 |
| compliant | 2 | 2/2 | 2/2 | no, n<20 |
| contradictory | 2 | 0/2 | 0/2 | no, n<20 |
| distractor | 2 | 2/2 | 2/2 | no, n<20 |
| incorrect_value | 2 | 2/2 | 2/2 | no, n<20 |
| missing_clause | 2 | 2/2 | 2/2 | no, n<20 |
| multiple_violations | 2 | 2/2 | 2/2 | no, n<20 |

Counts only where a category has fewer than 20 cases. Percentages at that sample size would not survive their own confidence interval.

### Accept-set stratum (ambiguous cases)

- status within the accepted set: 1/2
- matched one accepted answer exactly: 1/2
- excluded from the strict aggregates above by design (spec section 8.3)

### Efficiency

- tool calls: 0 total
- model calls: 0 total
- tokens: 0 total
- latency: not meaningful for a baseline that performs no inference
