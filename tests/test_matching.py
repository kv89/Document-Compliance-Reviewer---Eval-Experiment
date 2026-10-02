"""Matching rule tests (spec section 8.4).

Every outcome metric in the experiment is a function of this rule, so each clause of it is tested
explicitly, including the deliberate choice to return None rather than 0.0 for an undefined
precision or recall.
"""

from __future__ import annotations

from agent.schemas.models import FindingType
from evaluation.deterministic.matching import best_match, dedupe, match
from tests.conftest import finding, missing_liability


def test_perfect_match():
    result = match([finding()], [finding()])
    assert (result.tp, result.fp, result.fn) == (1, 0, 0)
    assert result.precision == 1.0 and result.recall == 1.0 and result.exact


def test_missed_finding_is_a_false_negative():
    result = match([finding()], [])
    assert (result.tp, result.fp, result.fn) == (0, 0, 1)
    assert result.recall == 0.0
    assert result.precision is None, "precision is undefined when nothing was reported"


def test_invented_finding_is_a_false_positive():
    result = match([], [finding()])
    assert (result.tp, result.fp, result.fn) == (0, 1, 0)
    assert result.precision == 0.0
    assert result.recall is None, "recall is undefined when nothing was expected"


def test_compliant_case_answered_correctly_has_no_defined_rates():
    result = match([], [])
    assert result.precision is None and result.recall is None and result.f1 is None
    assert result.exact, "finding nothing when nothing is expected is an exact match"


def test_duplicates_are_deduped_not_counted_as_false_positives():
    result = match([finding()], [finding(), finding(), finding()])
    assert (result.tp, result.fp, result.fn) == (1, 0, 0)
    assert result.duplicates == ["VALUE-PAY-001", "VALUE-PAY-001"]
    assert result.precision == 1.0


def test_dedupe_keeps_the_first_occurrence():
    first = finding(description="first")
    kept, dupes = dedupe([first, finding(description="second")])
    assert [f.description for f in kept] == ["first"]
    assert dupes == ["VALUE-PAY-001"]


def test_wrong_type_is_a_match_with_a_type_error():
    """Spec section 8.4 step 5. Not a false negative plus a false positive."""
    result = match([finding(finding_type=FindingType.CONTRADICTION)], [finding()])
    assert (result.tp, result.fp, result.fn) == (1, 0, 0)
    assert result.tp_strict == 0
    assert not result.exact, "strict scoring counts the type error"
    assert result.exact_lenient, "lenient scoring ignores it"


def test_partial_credit_on_a_multiple_violation_case():
    expected = [finding(), missing_liability()]
    result = match(expected, [finding()])
    assert (result.tp, result.fp, result.fn) == (1, 0, 1)
    assert result.precision == 1.0 and result.recall == 0.5
    assert result.f1 == 2 / 3


def test_mixed_hit_and_invention():
    expected = [finding()]
    actual = [finding(), missing_liability()]
    result = match(expected, actual)
    assert (result.tp, result.fp, result.fn) == (1, 1, 0)
    assert result.precision == 0.5


def test_matching_ignores_order():
    expected = [finding(), missing_liability()]
    result = match(expected, [missing_liability(), finding()])
    assert result.exact


def test_best_match_prefers_the_defensible_reading():
    """Accept-set case: the agent chose POLICY_VIOLATION, the first accepted set says AMBIGUOUS."""
    sets = [
        [finding(finding_type=FindingType.AMBIGUOUS)],
        [finding(finding_type=FindingType.POLICY_VIOLATION)],
    ]
    result = best_match(sets, [finding(finding_type=FindingType.POLICY_VIOLATION)])
    assert result.exact, "the second accepted answer matches exactly"


def test_best_match_still_fails_an_indefensible_answer():
    sets = [[finding(finding_type=FindingType.AMBIGUOUS)]]
    result = best_match(sets, [missing_liability()])
    assert not result.exact
    assert (result.tp, result.fp, result.fn) == (0, 1, 1)


def test_best_match_with_no_accepted_sets_is_not_a_crash():
    result = best_match([], [finding()])
    assert (result.tp, result.fp) == (0, 1)
