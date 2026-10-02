"""Evidence evaluation tests (Layer 2).

The S2 fabrication check is the sharpest deterministic signal in the whole experiment, so it is
tested on the exact failure shapes a model produces: a plausible quote that is not in the document,
a real quote with the wrong offsets, and a real quote attributed to the wrong section.
"""

from __future__ import annotations

from evaluation.deterministic import evidence as ev
from evaluation.deterministic.matching import match
from tests.conftest import PAY_END, PAY_QUOTE, PAY_START, finding, missing_liability, pay_evidence


def score_one(actual_finding, case, document):
    return ev.score(match([finding()], [actual_finding]), case, document)


def test_correct_evidence_scores_full_marks(strict_case, document):
    score = score_one(finding(), strict_case, document)
    assert score.checked == 1 and score.accuracy == 1.0
    assert score.span_overlap == 1.0


def test_fabricated_quote_fails(strict_case, document):
    fake = finding(evidence=pay_evidence(quote="within 90 days of receipt"))
    score = score_one(fake, strict_case, document)
    assert score.quote_verbatim == 0 and score.accuracy == 0.0


def test_real_quote_with_shifted_offsets_fails_only_the_offset_check(strict_case, document):
    shifted = finding(
        evidence=pay_evidence(char_start=PAY_START + 4, char_end=PAY_END + 4)
    )
    score = score_one(shifted, strict_case, document)
    assert score.quote_verbatim == 1
    assert score.offsets_consistent == 0
    assert score.accuracy == 0.0
    assert 0 < score.span_overlap < 1


def test_wrong_section_attribution_fails(strict_case, document):
    wrong = finding(evidence=pay_evidence(section_id="8"))
    score = score_one(wrong, strict_case, document)
    assert score.quote_verbatim == 1 and score.offsets_consistent == 1
    assert score.section_correct == 0 and score.accuracy == 0.0


def test_alternative_section_is_accepted_for_a_contradiction(contradiction_case, document):
    """Citing either half of a contradiction is defensible (spec section 8.2)."""
    from agent.schemas.models import FindingType

    expected = finding(finding_type=FindingType.CONTRADICTION)
    actual = finding(finding_type=FindingType.CONTRADICTION, evidence=pay_evidence(section_id="12.3"))
    score = ev.score(match([expected], [actual]), contradiction_case, document)
    assert score.section_correct == 1 and score.accuracy == 1.0


def test_missing_evidence_where_required_scores_zero(strict_case, document):
    from agent.schemas.models import Finding, FindingType, Severity

    no_evidence = Finding(
        rule_id="VALUE-PAY-001",
        finding_type=FindingType.POLICY_VIOLATION,
        clause="Payment Terms",
        severity=Severity.MEDIUM,
        description="no citation given",
    )
    score = score_one(no_evidence, strict_case, document)
    assert score.present == 0 and score.accuracy == 0.0


def test_missing_clause_findings_are_not_evidence_checked(document):
    """A missing clause has nothing to cite, so it must not be counted in the denominator."""
    from agent.schemas.models import CaseCategory, ComplianceStatus, GroundTruthCase

    case = GroundTruthCase(
        case_id="DOC-TEST-5",
        dataset_version="test",
        category=CaseCategory.MISSING_CLAUSE,
        policy_id="POL-001",
        policy_version="v1",
        document_path="tests/fixtures/doc.txt",
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        expected_findings=[missing_liability()],
    )
    score = ev.score(match([missing_liability()], [missing_liability()]), case, document)
    assert score.checked == 0
    assert score.accuracy is None, "no evidence to check means no rate, not a perfect rate"


def test_partial_span_overlap_is_measured(strict_case, document):
    """The agent quoted a shorter true substring. Verbatim and consistent, overlap below 1."""
    short = "within 60 days"
    actual = finding(
        evidence=pay_evidence(
            quote=short, char_start=document.index(short), char_end=document.index(short) + len(short)
        )
    )
    score = score_one(actual, strict_case, document)
    assert score.quote_verbatim == 1 and score.offsets_consistent == 1
    assert 0.5 < score.span_overlap < 1.0
    assert score.accuracy == 1.0, "a true, correctly located substring of the span is acceptable"
