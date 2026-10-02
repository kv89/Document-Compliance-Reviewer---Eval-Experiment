"""Reference baseline and end-to-end evaluation tests.

These lock in the reference numbers. If a later change makes REF-1 able to solve contradiction
cases, or makes REF-0 score better than the majority-class floor, something has leaked between the
dataset and the evaluator and every downstream number is suspect.
"""

from __future__ import annotations

import pytest

from agent.schemas.loaders import load_document, load_ground_truth, load_policy
from agent.schemas.models import CaseCategory, ComplianceStatus
from baselines import ref0_majority, ref1_regex
from evaluation.deterministic.evaluate import evaluate_case
from experiments.run_references import run_baseline

DATASET = "v1-m1"


@pytest.fixture(scope="module")
def cases():
    return load_ground_truth(DATASET)


@pytest.fixture(scope="module")
def policy():
    return load_policy("POL-001")


def test_ref0_reads_nothing_and_always_says_non_compliant(cases, policy):
    for case in cases:
        output = ref0_majority.run(load_document(case), policy, case)
        assert output.status is ComplianceStatus.NON_COMPLIANT
        assert output.findings == []


def test_ref0_establishes_the_majority_class_floor():
    rows = run_baseline("ref0_majority", DATASET)
    strict = [r for r in rows if r.scoring_mode == "strict"]
    correct = sum(1 for r in strict if r.status_correct)
    # Eight of twelve strict cases are non-compliant. Any agent status-accuracy claim must beat
    # this, and it is reached by a program that never opens the document.
    assert (correct, len(strict)) == (8, 12)
    assert all(r.deterministic_result == "fail" for r in strict)


def test_ref1_solves_the_regex_detectable_categories(cases, policy):
    for case in cases:
        if case.category not in (
            CaseCategory.MISSING_CLAUSE,
            CaseCategory.INCORRECT_VALUE,
            CaseCategory.MULTIPLE_VIOLATIONS,
        ):
            continue
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.passed, f"{case.case_id} should be solvable without a model"


def test_ref1_fails_every_contradiction_case(cases, policy):
    """The documented capability gap. Blog post 1 depends on this being real."""
    contradictions = [c for c in cases if c.category is CaseCategory.CONTRADICTORY]
    assert contradictions
    for case in contradictions:
        document = load_document(case)
        output = ref1_regex.run(document, policy, case)
        assert output.status is ComplianceStatus.COMPLIANT, "the checker sees nothing wrong"
        evaluation = evaluate_case(output, case, policy, document)
        assert not evaluation.passed
        assert evaluation.match.fn == 1, "the contradiction is a missed finding"


def test_ref1_does_not_hallucinate_on_compliant_or_distractor_cases(cases, policy):
    for case in cases:
        if case.category not in (CaseCategory.COMPLIANT, CaseCategory.DISTRACTOR):
            continue
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.match.fp == 0, f"{case.case_id}: false positive on a clean document"
        assert evaluation.passed


def test_ref1_evidence_is_never_fabricated(cases, policy):
    """S2 and S3 over the whole dataset. A deterministic baseline must be perfect here."""
    for case in cases:
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.safety.violations.get("S2") == []
        assert evaluation.safety.violations.get("S3") == []


def test_trace_dependent_safety_checks_are_recorded_as_skipped():
    for name in ("ref0_majority", "ref1_regex"):
        rows = run_baseline(name, DATASET)
        assert all(set(r.safety_checks_skipped) == {"S1", "S6", "S8"} for r in rows)


def test_every_row_carries_its_category_and_scoring_mode():
    """Per-category reporting is impossible without these (spec section 23)."""
    rows = run_baseline("ref1_regex", DATASET)
    assert all(r.case_category for r in rows)
    assert {r.scoring_mode for r in rows} == {"strict", "accept_set"}
    assert len({r.case_id for r in rows}) == len(rows)


def test_rows_round_trip_through_jsonl():
    from agent.schemas.results import TrialRow

    rows = run_baseline("ref1_regex", DATASET)
    assert all(TrialRow.model_validate_json(r.model_dump_json()) == r for r in rows)


def test_report_refuses_to_publish_percentages_for_small_categories():
    from analysis.scripts.aggregate import summarize

    text = summarize(run_baseline("ref1_regex", DATASET), "test")
    assert "no, n<20" in text
    assert "below the n=20 reporting floor" in text or "Counts only where" in text
