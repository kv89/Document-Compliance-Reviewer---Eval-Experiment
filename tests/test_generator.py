"""Generator tests.

Two properties matter most: the dataset is byte-reproducible from a seed, and a case that violates
its own invariants is never written to disk.
"""

from __future__ import annotations

import pytest

from agent.schemas.loaders import load_policy
from agent.schemas.models import (
    CaseCategory,
    ComplianceStatus,
    FindingType,
    ScoringMode,
)
from agent.tools.splitter import split_document
from dataset.generator import clauses as cl
from dataset.generator.generate import (
    GeneratorError,
    PendingFinding,
    build_dataset,
    validate_case,
)

POLICY = load_policy("POL-001")


@pytest.fixture(scope="module")
def cases():
    return build_dataset("v1-test", per_category=2, seed=7, policy=POLICY)


def test_all_seven_categories_are_built(cases):
    assert {c.category for c, _ in cases} == set(CaseCategory)
    assert len(cases) == 14


def test_generation_is_deterministic_for_a_seed():
    first = build_dataset("v1-test", 2, 7, POLICY)
    second = build_dataset("v1-test", 2, 7, POLICY)
    assert [t for _, t in first] == [t for _, t in second]
    assert [c.model_dump_json() for c, _ in first] == [c.model_dump_json() for c, _ in second]


def test_different_seed_changes_the_documents():
    a = build_dataset("v1-test", 2, 7, POLICY)
    b = build_dataset("v1-test", 2, 99, POLICY)
    assert [t for _, t in a] != [t for _, t in b]


def test_every_case_passes_its_own_validation(cases):
    for case, text in cases:
        assert validate_case(case, text, POLICY) == []


def test_every_expected_quote_is_unique_in_its_document(cases):
    for case, text in cases:
        for finding in case.expected_findings:
            if finding.evidence is not None:
                assert text.count(finding.evidence.quote) == 1


def test_every_expected_offset_resolves_to_its_quote(cases):
    for case, text in cases:
        for finding in case.expected_findings:
            ev = finding.evidence
            if ev is not None:
                assert text[ev.char_start : ev.char_end] == ev.quote


def test_missing_clause_cases_have_no_evidence(cases):
    for case, _ in cases:
        for finding in case.expected_findings:
            if finding.finding_type is FindingType.MISSING_CLAUSE:
                assert finding.evidence is None


def test_removed_clause_is_really_absent(cases):
    for case, text in cases:
        if case.category is not CaseCategory.MISSING_CLAUSE:
            continue
        titles = {s.title for s in split_document(text).sections}
        assert case.expected_findings[0].clause not in titles


def test_severity_always_comes_from_the_policy(cases):
    for case, _ in cases:
        for finding in case.expected_findings:
            assert finding.severity is POLICY.rule(finding.rule_id).severity
            assert finding.clause == POLICY.rule(finding.rule_id).clause


def test_ambiguous_cases_are_accept_set_and_reject_compliant(cases):
    ambiguous = [c for c, _ in cases if c.category is CaseCategory.AMBIGUOUS]
    assert ambiguous
    for case in ambiguous:
        assert case.scoring_mode is ScoringMode.ACCEPT_SET
        assert case.expected_status is None
        assert ComplianceStatus.COMPLIANT not in case.accepted_statuses
        assert ComplianceStatus.COMPLIANT in case.unacceptable_statuses
        assert len(case.accepted_finding_sets) == 2


def test_only_ambiguous_cases_are_accept_set(cases):
    for case, _ in cases:
        expected = case.category is CaseCategory.AMBIGUOUS
        assert (case.scoring_mode is ScoringMode.ACCEPT_SET) is expected


def test_contradiction_declares_both_sections_as_required_and_acceptable(cases):
    for case, _ in cases:
        if case.category is not CaseCategory.CONTRADICTORY:
            continue
        rule_id = case.expected_findings[0].rule_id
        assert len(case.evidence_section_alternatives[rule_id]) == 2
        required = {r.rule_id: r.must_consult_sections for r in case.required_information}
        assert len(required[rule_id]) == 2


def test_multiple_violation_cases_carry_more_than_one_finding(cases):
    multi = [c for c, _ in cases if c.category is CaseCategory.MULTIPLE_VIOLATIONS]
    assert all(len(c.expected_findings) >= 2 for c in multi)


def test_compliant_and_distractor_cases_expect_no_findings(cases):
    for case, _ in cases:
        if case.category in (CaseCategory.COMPLIANT, CaseCategory.DISTRACTOR):
            assert case.expected_status is ComplianceStatus.COMPLIANT
            assert case.expected_findings == []


def test_case_ids_are_sequential_and_unique(cases):
    ids = [c.case_id for c, _ in cases]
    assert ids == sorted(ids) and len(set(ids)) == len(ids)


def test_mutation_is_recorded_for_every_mutated_case(cases):
    for case, _ in cases:
        if case.category is CaseCategory.COMPLIANT:
            assert case.mutations == []
        else:
            assert case.mutations, f"{case.case_id} records no mutation"


# --------------------------------------------------------------------------------------------
# The validator must reject bad cases. A validator that passes everything protects nothing.
# --------------------------------------------------------------------------------------------


def test_validator_rejects_a_quote_absent_from_the_document():
    from dataset.generator.generate import _locate

    with pytest.raises(GeneratorError, match="absent"):
        _locate("not in here", "some document text", "DOC-TEST")


def test_validator_rejects_a_non_unique_quote():
    from dataset.generator.generate import _locate

    with pytest.raises(GeneratorError, match="unique"):
        _locate("abc", "abc and again abc", "DOC-TEST")


def test_validator_rejects_a_silently_failed_mutation(cases):
    """Simulate a removal mutation that did not remove anything.

    The ground truth claims the Liability clause is missing while the document still contains it.
    This is the exact failure mode section 9.3 of the spec exists to catch.
    """
    case = next(c for c, _ in cases if c.category is CaseCategory.MISSING_CLAUSE)
    intact = cl.render(cl.compliant_spec("A", "B", 30, "India", 30))
    problems = validate_case(case, intact, POLICY)
    assert any("not detected" in p for p in problems)


def test_validator_rejects_an_unintended_violation_in_a_compliant_case(cases):
    case = next(c for c, _ in cases if c.category is CaseCategory.COMPLIANT)
    breached = cl.render(cl.compliant_spec("A", "B", 90, "Delaware", 30))
    problems = validate_case(case, breached, POLICY)
    assert any("unintended violations" in p for p in problems)


def test_build_dataset_raises_rather_than_writing_a_bad_case(monkeypatch):
    """A broken builder must abort the whole run. Nothing is written until all cases pass."""
    import dataset.generator.generate as gen

    def broken(rng, v):
        blueprint = gen._compliant(rng, v)
        blueprint.findings = [
            PendingFinding(
                rule_id="VALUE-PAY-001",
                finding_type=FindingType.POLICY_VIOLATION,
                description="fabricated",
                quote="text that is not in the document",
                section_id="4.1",
            )
        ]
        return blueprint

    monkeypatch.setitem(gen.BUILDERS, CaseCategory.COMPLIANT, broken)
    with pytest.raises(GeneratorError):
        gen.build_dataset("v1-test", 1, 7, POLICY)
