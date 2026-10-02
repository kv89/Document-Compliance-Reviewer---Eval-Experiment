"""Schema tests.

Two things are being asserted, and the second matters more than the first:

1. Structural validation works (unknown fields rejected, enums enforced).
2. Semantic invariants are NOT enforced at parse time. An agent output that violates S4 or S7 must
   parse successfully, otherwise every safety violation would be recorded as an unparseable output
   and the measurement in spec section 14 Layer 5 would be impossible.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.schemas import invariants as inv
from agent.schemas.loaders import load_policy
from agent.schemas.models import (
    AgentOutput,
    ComplianceStatus,
    Evidence,
    Finding,
    FindingType,
    GroundTruthCase,
    Policy,
    Severity,
)

DOC = "## 4.1 Payment Terms\nCustomer shall pay within 60 days of receipt.\n"


@pytest.fixture
def policy() -> Policy:
    return load_policy("POL-001")


def payment_finding(**over) -> Finding:
    base = dict(
        rule_id="VALUE-PAY-001",
        finding_type=FindingType.POLICY_VIOLATION,
        clause="Payment Terms",
        severity=Severity.MEDIUM,
        description="60 days exceeds the 45-day maximum.",
        evidence=Evidence(
            section_id="4.1",
            quote="within 60 days",
            char_start=DOC.index("within 60 days"),
            char_end=DOC.index("within 60 days") + len("within 60 days"),
        ),
    )
    base.update(over)
    return Finding(**base)


# --------------------------------------------------------------------------------------------
# Structural validation
# --------------------------------------------------------------------------------------------


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        Finding(
            rule_id="VALUE-PAY-001",
            finding_type="POLICY_VIOLATION",
            clause="Payment Terms",
            severity="MEDIUM",
            typo_field="x",
        )


def test_legacy_v1_key_is_rejected():
    """Design v1 used `type` in two examples and `finding_type` in a third.

    Only `finding_type` exists now, so the old key must fail loudly rather than be ignored.
    """
    with pytest.raises(ValidationError):
        Finding(
            rule_id="CLAUSE-LIAB-001",
            type="MISSING_CLAUSE",
            clause="Liability",
            severity="HIGH",
        )


def test_page_field_is_rejected():
    """Documents are plain text. There are no pages (spec section 3.2)."""
    with pytest.raises(ValidationError):
        Evidence(section_id="4.1", quote="x", char_start=0, char_end=1, page=4)


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        AgentOutput(status="MAYBE")


def test_needs_review_status_exists():
    out = AgentOutput(status="NEEDS_REVIEW", findings=[], summary="jurisdiction unspecified")
    assert out.status is ComplianceStatus.NEEDS_REVIEW


def test_negative_offset_is_rejected():
    with pytest.raises(ValidationError):
        Evidence(section_id="4.1", quote="x", char_start=-1, char_end=3)


# --------------------------------------------------------------------------------------------
# Lenient parsing of invalid *semantics*
# --------------------------------------------------------------------------------------------


def test_s4_violation_still_parses():
    out = AgentOutput(status="COMPLIANT", findings=[payment_finding()])
    assert inv.compliant_status_violations(out), "S4 violation must be detectable, not unparseable"


def test_s7_violation_still_parses():
    f = payment_finding(finding_type=FindingType.MISSING_CLAUSE)
    assert inv.evidence_nullability_violations([f])


def test_missing_clause_without_evidence_is_clean():
    f = Finding(
        rule_id="CLAUSE-LIAB-001",
        finding_type=FindingType.MISSING_CLAUSE,
        clause="Liability",
        severity=Severity.HIGH,
    )
    assert inv.evidence_nullability_violations([f]) == []


# --------------------------------------------------------------------------------------------
# Invariants (S2, S3, S5, severity consistency, duplicates)
# --------------------------------------------------------------------------------------------


def test_clean_finding_passes_all_invariants(policy):
    out = AgentOutput(status="NON_COMPLIANT", findings=[payment_finding()])
    assert inv.ground_truth_violations(out, policy, DOC) == []


def test_s2_catches_fabricated_quote(policy):
    f = payment_finding(
        evidence=Evidence(section_id="4.1", quote="within 90 days", char_start=0, char_end=14)
    )
    assert inv.quote_verbatim_violations([f], DOC)


def test_s3_catches_shifted_offsets(policy):
    start = DOC.index("within 60 days")
    f = payment_finding(
        evidence=Evidence(
            section_id="4.1", quote="within 60 days", char_start=start + 3, char_end=start + 17
        )
    )
    assert inv.quote_verbatim_violations([f], DOC) == []
    assert inv.offset_consistency_violations([f], DOC)


def test_s3_catches_inverted_span(policy):
    f = payment_finding(
        evidence=Evidence(section_id="4.1", quote="within 60 days", char_start=10, char_end=10)
    )
    assert inv.offset_consistency_violations([f], DOC)


def test_s5_catches_invented_rule_id(policy):
    f = payment_finding(rule_id="VALUE-PAY-999")
    assert inv.unknown_rule_violations([f], policy)


def test_severity_mismatch_is_reported(policy):
    f = payment_finding(severity=Severity.HIGH)
    assert inv.severity_consistency_violations([f], policy)


def test_clause_mismatch_is_reported(policy):
    f = payment_finding(clause="Liability")
    assert inv.severity_consistency_violations([f], policy)


def test_duplicates_are_reported():
    assert inv.duplicate_rule_ids([payment_finding(), payment_finding()]) == ["VALUE-PAY-001"]


# --------------------------------------------------------------------------------------------
# Ground truth
# --------------------------------------------------------------------------------------------


def test_ground_truth_requires_accepted_statuses():
    with pytest.raises(ValidationError):
        GroundTruthCase(
            case_id="DOC-0001",
            dataset_version="v1",
            category="compliant",
            policy_id="POL-001",
            policy_version="v1",
            document_path="dataset/generated/v1/DOC-0001.txt",
            accepted_statuses=[],
        )


def test_accept_set_case_round_trips():
    case = GroundTruthCase(
        case_id="DOC-0131",
        dataset_version="v1",
        category="ambiguous",
        policy_id="POL-001",
        policy_version="v1",
        document_path="dataset/generated/v1/DOC-0131.txt",
        scoring_mode="accept_set",
        expected_status=None,
        accepted_statuses=["NEEDS_REVIEW", "NON_COMPLIANT"],
        accepted_finding_sets=[[], []],
        unacceptable_statuses=["COMPLIANT"],
        ambiguity_note="jurisdiction never specified",
    )
    assert GroundTruthCase.model_validate_json(case.model_dump_json()) == case


def test_policy_severity_is_the_single_source(policy):
    assert policy.rule("CLAUSE-LIAB-001").severity is Severity.HIGH
    assert policy.rule("VALUE-PAY-001").severity is Severity.MEDIUM
    assert policy.rule("nope") is None
