"""Finding matching (spec section 8.4).

This module is the single most consequential piece of the evaluation. Precision, recall, evidence
accuracy and every per-category number depend on how an actual finding is paired with an expected
one, so the rule is pre-registered in the spec and implemented once here. Choosing it after seeing
results would violate spec section 2.

The rule:

1. Deduplicate the agent's findings by rule_id, keeping the first. Repeats are counted as a
   quality signal, never as false positives.
2. Join expected to actual one-to-one on rule_id.
3. Both -> true positive. Actual only -> false positive. Expected only -> false negative.
4. Secondary agreement (finding type, evidence) is computed on true positives only, and the
   denominator is always reported.
5. A true positive with the wrong finding_type is a match with a type error, not a false negative
   plus a false positive. Strict and lenient numbers are both produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent.schemas.models import Finding


@dataclass(frozen=True)
class MatchedPair:
    rule_id: str
    expected: Finding
    actual: Finding

    @property
    def type_matches(self) -> bool:
        return self.expected.finding_type is self.actual.finding_type


@dataclass
class MatchResult:
    matched: list[MatchedPair] = field(default_factory=list)
    false_positives: list[Finding] = field(default_factory=list)
    false_negatives: list[Finding] = field(default_factory=list)
    duplicates: list[str] = field(default_factory=list)

    @property
    def tp(self) -> int:
        return len(self.matched)

    @property
    def fp(self) -> int:
        return len(self.false_positives)

    @property
    def fn(self) -> int:
        return len(self.false_negatives)

    @property
    def tp_strict(self) -> int:
        """True positives where the finding type also agrees."""
        return sum(1 for m in self.matched if m.type_matches)

    @property
    def precision(self) -> float | None:
        """None, not zero, when the agent reported nothing.

        An agent that reports no findings has undefined precision. Recording it as 0.0 would
        understate it; recording it as 1.0 would reward silence. None forces the denominator to be
        visible in the report (spec section 24 rule 3).
        """
        denominator = self.tp + self.fp
        return None if denominator == 0 else self.tp / denominator

    @property
    def recall(self) -> float | None:
        """None when the case expects no findings, which is true of every compliant case."""
        denominator = self.tp + self.fn
        return None if denominator == 0 else self.tp / denominator

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if p is None or r is None or p + r == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def exact(self) -> bool:
        """Every expected finding found, nothing extra, and every type correct."""
        return self.fp == 0 and self.fn == 0 and self.tp == self.tp_strict

    @property
    def exact_lenient(self) -> bool:
        """Same, ignoring finding_type disagreement."""
        return self.fp == 0 and self.fn == 0


def dedupe(findings: list[Finding]) -> tuple[list[Finding], list[str]]:
    """Keep the first finding per rule_id. Return the kept list and the repeated rule_ids."""
    kept: list[Finding] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    for f in findings:
        if f.rule_id in seen:
            duplicates.append(f.rule_id)
            continue
        seen.add(f.rule_id)
        kept.append(f)
    return kept, duplicates


def match(expected: list[Finding], actual: list[Finding]) -> MatchResult:
    """Apply the pre-registered matching rule."""
    kept, duplicates = dedupe(actual)
    by_rule = {f.rule_id: f for f in kept}
    expected_ids = {f.rule_id for f in expected}

    result = MatchResult(duplicates=duplicates)
    for e in expected:
        a = by_rule.get(e.rule_id)
        if a is None:
            result.false_negatives.append(e)
        else:
            result.matched.append(MatchedPair(rule_id=e.rule_id, expected=e, actual=a))
    result.false_positives = [f for f in kept if f.rule_id not in expected_ids]
    return result


def best_match(accepted_sets: list[list[Finding]], actual: list[Finding]) -> MatchResult:
    """Match against the most favourable accepted answer (accept-set cases, spec section 8.3).

    Ranking: an exact match wins outright; otherwise prefer more true positives, then fewer
    mistakes. The agent is given the benefit of any defensible reading, because that is what
    "more than one answer is correct" means.
    """
    results = [match(group, actual) for group in accepted_sets] or [match([], actual)]
    return max(results, key=lambda r: (r.exact, r.tp_strict, r.tp, -(r.fp + r.fn)))
