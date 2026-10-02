"""Tests for the shared deterministic rule checker (REF-1 and generator validation).

The blind spots are tested as deliberately as the detections. If a later change made the checker
able to see contradictions, REF-1 would stop being the honest "how much of this is not AI work"
reference, and the generator's contradiction invariant would silently stop asserting anything.
"""

from __future__ import annotations

import pytest

from agent.schemas.loaders import load_policy
from agent.schemas.models import FindingType, Policy
from dataset.generator import clauses as cl
from evaluation.deterministic.rule_check import check_document, violated_rule_ids


@pytest.fixture
def policy() -> Policy:
    return load_policy("POL-001")


def doc(payment_days: int = 30, jurisdiction: str = "India") -> str:
    return cl.render(
        cl.compliant_spec("Northwind Industries", "Blue Harbour Systems", payment_days,
                          jurisdiction, 30)
    )


def test_compliant_document_is_clean(policy):
    assert check_document(doc(), policy) == []


def test_boundary_value_is_compliant(policy):
    """45 days is the limit and must pass. An off-by-one here would mislabel the dataset."""
    assert violated_rule_ids(doc(payment_days=45), policy) == set()


def test_one_day_over_the_limit_is_a_violation(policy):
    assert violated_rule_ids(doc(payment_days=46), policy) == {"VALUE-PAY-001"}


def test_violation_offsets_point_at_the_document(policy):
    text = doc(payment_days=60)
    violation = check_document(text, policy)[0]
    assert text[violation.char_start : violation.char_end] == violation.quote


def test_unapproved_jurisdiction_is_detected(policy):
    assert violated_rule_ids(doc(jurisdiction="Delaware"), policy) == {"ENUM-LAW-001"}


def test_every_approved_jurisdiction_passes(policy):
    for jurisdiction in cl.APPROVED_JURISDICTIONS:
        assert violated_rule_ids(doc(jurisdiction=jurisdiction), policy) == set()


def test_removed_clause_is_detected_as_missing(policy):
    spec = cl.compliant_spec("A", "B", 30, "India", 30).without(cl.SEC_LIABILITY)
    violations = check_document(cl.render(spec), policy)
    assert [(v.rule_id, v.finding_type) for v in violations] == [
        ("CLAUSE-LIAB-001", FindingType.MISSING_CLAUSE)
    ]


def test_missing_clause_violation_cites_no_evidence(policy):
    spec = cl.compliant_spec("A", "B", 30, "India", 30).without(cl.SEC_LIABILITY)
    assert check_document(cl.render(spec), policy)[0].quote is None


def test_blind_to_cross_section_contradiction(policy):
    """Documented limitation.

    Section 4.1 says 30 days, section 12.3 says 60 days. The checker only looks inside the section
    whose title matches the clause, so it sees nothing. This is the capability gap the agent is
    supposed to fill, and blog post 1 depends on the gap being real.
    """
    spec = cl.compliant_spec("A", "B", 30, "India", 30).appending(
        cl.SectionSpec(
            cl.SEC_PAYMENT_SCHEDULE,
            "Payment Schedule",
            "Notwithstanding clause 4.1, Customer shall settle all invoices within 60 days "
            "of the invoice date.",
        )
    )
    assert violated_rule_ids(cl.render(spec), policy) == set()


def test_blind_to_qualitative_payment_period(policy):
    """"within a reasonable period" has no number to compare, so no violation is reported."""
    spec = cl.compliant_spec("A", "B", 30, "India", 30).replacing(
        cl.SEC_PAYMENT,
        "Customer shall pay all undisputed invoices promptly following receipt and in any event "
        "within a reasonable period.",
    )
    assert violated_rule_ids(cl.render(spec), policy) == set()


def test_distractor_deadline_is_not_mistaken_for_payment_terms(policy):
    """The expenses section carries "within 30 days", outside the Payment Terms clause."""
    spec = cl.compliant_spec("A", "B", 30, "India", 30)
    for section in cl.DISTRACTOR_SECTIONS:
        spec = spec.appending(section)
    assert violated_rule_ids(cl.render(spec), policy) == set()
