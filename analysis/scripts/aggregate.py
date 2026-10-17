"""Aggregation and reporting (spec section 24).

Three rules are enforced in code rather than left to discipline:

1. Aggregate to case level before computing any interval. The trials of one case are correlated -
   that correlation is the object of study in spec section 17 - so treating executions as
   independent observations overstates precision.
2. No per-category percentage below MIN_CATEGORY_N case-level observations. Report counts instead.
   A 74% figure on ten cases carries an interval of roughly plus or minus 28 points, and spec
   section 2 forbids claims the sample cannot support.
3. Always print the denominator for any metric computed on a subset.

Accept-set cases are reported as their own stratum and never pooled into the single-truth
aggregates.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass

from agent.schemas.results import TrialRow

MIN_CATEGORY_N = 20
BOOTSTRAP_SAMPLES = 2000


@dataclass(frozen=True)
class Interval:
    point: float
    low: float
    high: float
    n: int

    def render(self, reportable: bool = True) -> str:
        if not reportable:
            return f"n={self.n} (below the n={MIN_CATEGORY_N} reporting floor)"
        return f"{self.point:.2f} [{self.low:.2f}, {self.high:.2f}] (n={self.n})"


def case_level_means(rows: list[TrialRow], field: str) -> dict[str, float]:
    """Collapse trials to one observation per case.

    Rows whose metric is None are skipped, not treated as zero: an undefined precision is not a
    precision of nought.
    """
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        value = getattr(row, field)
        if value is None:
            continue
        buckets[row.case_id].append(float(value))
    return {case_id: sum(v) / len(v) for case_id, v in buckets.items() if v}


def clustered_bootstrap(values: list[float], seed: int = 7) -> Interval | None:
    """Percentile bootstrap over case-level means.

    Resampling cases rather than executions is what makes the interval honest when each case
    contributes several correlated trials.
    """
    if not values:
        return None
    point = sum(values) / len(values)
    if len(values) == 1:
        return Interval(point, point, point, 1)
    rng = random.Random(seed)
    means = []
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(sum(sample) / len(sample))
    means.sort()
    low = means[int(0.025 * len(means))]
    high = means[min(len(means) - 1, int(0.975 * len(means)))]
    return Interval(point, low, high, len(values))


def metric(rows: list[TrialRow], field: str, seed: int = 7) -> Interval | None:
    return clustered_bootstrap(list(case_level_means(rows, field).values()), seed=seed)


def trial_consistency(rows: list[TrialRow]) -> tuple[int, int]:
    """Cases where every trial agreed on the status. Returns (agreeing, cases with >1 trial)."""
    buckets: dict[str, set[str]] = defaultdict(set)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        buckets[row.case_id].add(row.actual_status)
        counts[row.case_id] += 1
    multi = [c for c, n in counts.items() if n > 1]
    return sum(1 for c in multi if len(buckets[c]) == 1), len(multi)


def _bool_rate(rows: list[TrialRow], field: str) -> tuple[int, int]:
    total = len(rows)
    hits = sum(1 for r in rows if bool(getattr(r, field)))
    return hits, total


def summarize(
    rows: list[TrialRow], title: str, consistency_rows: list[TrialRow] | None = None
) -> str:
    """Render a markdown report for one configuration.

    `consistency_rows` measures trial consistency on rows other than the headline ones: a run that
    repeats only a subset of cases reports trial 1 as its headline, so that repeated cases are not
    weighted three times, and takes consistency from all trials (docs/decisions/decisions.md,
    2026-10-17).
    """
    strict = [r for r in rows if r.scoring_mode == "strict"]
    accept = [r for r in rows if r.scoring_mode == "accept_set"]
    cases = {r.case_id for r in rows}

    lines: list[str] = []
    add = lines.append

    add(f"## {title}")
    add("")
    add(f"- executions: {len(rows)} over {len(cases)} cases")
    add(f"- strict stratum: {len({r.case_id for r in strict})} cases")
    add(f"- accept-set stratum: {len({r.case_id for r in accept})} cases, reported separately")
    safety = sum(r.safety_violations for r in rows)
    skipped = sorted({s for r in rows for s in r.safety_checks_skipped})
    add(f"- safety violations: **{safety}** (a count, never a rate)")
    if skipped:
        add(f"- safety checks skipped for want of a trace: {', '.join(skipped)} "
            "— skipped, not passed")
    agree, multi = trial_consistency(rows if consistency_rows is None else consistency_rows)
    add(f"- trial consistency: {agree}/{multi} cases where all trials agreed on status"
        if multi else "- trial consistency: not measurable, one trial per case")
    add("")

    add("### Strict stratum")
    add("")
    hits, total = _bool_rate(strict, "status_correct")
    add(f"| metric | value | denominator |")
    add("|---|---|---|")
    add(f"| status accuracy | {hits}/{total} | strict executions |")
    hits, total = _bool_rate(strict, "findings_exact")
    add(f"| findings exact (strict types) | {hits}/{total} | strict executions |")
    hits, total = _bool_rate(strict, "findings_exact_lenient")
    add(f"| findings exact (ignoring type) | {hits}/{total} | strict executions |")
    passes = sum(1 for r in strict if r.deterministic_result == "pass")
    add(f"| full case pass | {passes}/{len(strict)} | strict executions |")
    for field, label in (
        ("finding_precision", "finding precision"),
        ("finding_recall", "finding recall"),
        ("evidence_accuracy", "evidence accuracy"),
    ):
        interval = metric(strict, field)
        defined = len(case_level_means(strict, field))
        add(f"| {label} | {interval.render() if interval else 'undefined'} "
            f"| {defined} cases where it is defined |")
    tp = sum(r.tp for r in strict)
    add(f"| true positives / false positives / false negatives | "
        f"{tp} / {sum(r.fp for r in strict)} / {sum(r.fn for r in strict)} | findings |")
    add(f"| fabricated evidence (S2) | {sum(r.fabricated_evidence_count for r in strict)} "
        "| count |")
    add("")

    add("### Per category")
    add("")
    add("| category | cases | status correct | full pass | reportable as a percentage |")
    add("|---|---|---|---|---|")
    by_category: dict[str, list[TrialRow]] = defaultdict(list)
    for row in rows:
        by_category[row.case_category].append(row)
    for category in sorted(by_category):
        group = by_category[category]
        n_cases = len({r.case_id for r in group})
        ok = sum(1 for r in group if r.status_correct)
        passes = sum(1 for r in group if r.deterministic_result == "pass")
        reportable = "yes" if n_cases >= MIN_CATEGORY_N else f"no, n<{MIN_CATEGORY_N}"
        add(f"| {category} | {n_cases} | {ok}/{len(group)} | {passes}/{len(group)} | {reportable} |")
    add("")
    add(f"Counts only where a category has fewer than {MIN_CATEGORY_N} cases. "
        "Percentages at that sample size would not survive their own confidence interval.")
    add("")

    if accept:
        add("### Accept-set stratum (ambiguous cases)")
        add("")
        ok = sum(1 for r in accept if r.status_correct)
        passes = sum(1 for r in accept if r.deterministic_result == "pass")
        add(f"- status within the accepted set: {ok}/{len(accept)}")
        add(f"- matched one accepted answer exactly: {passes}/{len(accept)}")
        add("- excluded from the strict aggregates above by design (spec section 8.3)")
        add("")

    add("### Efficiency")
    add("")
    add(f"- tool calls: {sum(r.num_tool_calls for r in rows)} total")
    add(f"- model calls: {sum(r.num_llm_calls for r in rows)} total")
    add(f"- tokens: {sum(r.total_tokens for r in rows)} total")
    latencies = sorted(r.latency_ms for r in rows)
    if latencies and latencies[-1] > 0:
        p95 = latencies[min(len(latencies) - 1, int(0.95 * len(latencies)))]
        add(f"- latency: median {latencies[len(latencies) // 2]} ms, p95 {p95} ms")
    else:
        add("- latency: not meaningful for a baseline that performs no inference")
    add("")
    return "\n".join(lines)
