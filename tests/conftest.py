"""Hand-built fixtures for evaluator tests.

Deliberately hand-built rather than generated. The evaluators must be tested against cases whose
answers are known independently of the generator, otherwise a shared bug in both would be
invisible. This is the Tier 1 CI gate of spec section 22: a broken evaluator silently invalidates
every number downstream, and nothing else catches it.
"""

from __future__ import annotations

import pytest

from agent.schemas.loaders import load_policy
from agent.schemas.models import (
    AgentOutput,
    CaseCategory,
    ComplianceStatus,
    Evidence,
    Finding,
    FindingType,
    GroundTruthCase,
    Policy,
    RequiredInformation,
    ScoringMode,
    Severity,
)
from agent.schemas.trace import (
    EventType,
    RunConfig,
    Trace,
    TraceEvent,
    TraceTotals,
)

DOCUMENT = (
    "# MASTER SERVICES AGREEMENT\n"
    "\n"
    "## 4.1 Payment Terms\n"
    "Customer shall pay all undisputed invoices within 60 days of receipt.\n"
    "\n"
    "## 8. Governing Law\n"
    "This Agreement is governed by the laws of India.\n"
)

PAY_QUOTE = "within 60 days of receipt"
PAY_START = DOCUMENT.index(PAY_QUOTE)
PAY_END = PAY_START + len(PAY_QUOTE)


@pytest.fixture(scope="session")
def policy() -> Policy:
    return load_policy("POL-001")


@pytest.fixture
def document() -> str:
    return DOCUMENT


def pay_evidence(**over) -> Evidence:
    base = dict(
        section_id="4.1", quote=PAY_QUOTE, char_start=PAY_START, char_end=PAY_END
    )
    base.update(over)
    return Evidence(**base)


def finding(
    rule_id: str = "VALUE-PAY-001",
    finding_type: FindingType = FindingType.POLICY_VIOLATION,
    clause: str = "Payment Terms",
    severity: Severity = Severity.MEDIUM,
    evidence: Evidence | None = None,
    description: str = "60 days exceeds the 45-day maximum.",
) -> Finding:
    if evidence is None and finding_type is not FindingType.MISSING_CLAUSE:
        evidence = pay_evidence()
    return Finding(
        rule_id=rule_id,
        finding_type=finding_type,
        clause=clause,
        severity=severity,
        description=description,
        evidence=evidence,
    )


def missing_liability() -> Finding:
    return Finding(
        rule_id="CLAUSE-LIAB-001",
        finding_type=FindingType.MISSING_CLAUSE,
        clause="Liability",
        severity=Severity.HIGH,
        description="No Liability clause.",
    )


@pytest.fixture
def strict_case() -> GroundTruthCase:
    """One expected finding: a payment-value violation with evidence in section 4.1."""
    return GroundTruthCase(
        case_id="DOC-TEST-1",
        dataset_version="test",
        category=CaseCategory.INCORRECT_VALUE,
        policy_id="POL-001",
        policy_version="v1",
        document_path="tests/fixtures/doc.txt",
        scoring_mode=ScoringMode.STRICT,
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        expected_findings=[finding()],
        required_information=[
            RequiredInformation(rule_id="VALUE-PAY-001", must_consult_sections=["4.1"])
        ],
    )


@pytest.fixture
def compliant_case() -> GroundTruthCase:
    return GroundTruthCase(
        case_id="DOC-TEST-2",
        dataset_version="test",
        category=CaseCategory.COMPLIANT,
        policy_id="POL-001",
        policy_version="v1",
        document_path="tests/fixtures/doc.txt",
        expected_status=ComplianceStatus.COMPLIANT,
        accepted_statuses=[ComplianceStatus.COMPLIANT],
        expected_findings=[],
    )


@pytest.fixture
def accept_set_case() -> GroundTruthCase:
    """Either AMBIGUOUS or POLICY_VIOLATION on the same rule is defensible."""
    return GroundTruthCase(
        case_id="DOC-TEST-3",
        dataset_version="test",
        category=CaseCategory.AMBIGUOUS,
        policy_id="POL-001",
        policy_version="v1",
        document_path="tests/fixtures/doc.txt",
        scoring_mode=ScoringMode.ACCEPT_SET,
        expected_status=None,
        accepted_statuses=[ComplianceStatus.NEEDS_REVIEW, ComplianceStatus.NON_COMPLIANT],
        expected_findings=[finding(finding_type=FindingType.AMBIGUOUS)],
        accepted_finding_sets=[
            [finding(finding_type=FindingType.AMBIGUOUS)],
            [finding(finding_type=FindingType.POLICY_VIOLATION)],
        ],
        unacceptable_statuses=[ComplianceStatus.COMPLIANT],
        required_information=[
            RequiredInformation(rule_id="VALUE-PAY-001", must_consult_sections=["4.1"])
        ],
    )


@pytest.fixture
def contradiction_case() -> GroundTruthCase:
    """Evidence in section 4.1 or section 12.3 is accepted."""
    return GroundTruthCase(
        case_id="DOC-TEST-4",
        dataset_version="test",
        category=CaseCategory.CONTRADICTORY,
        policy_id="POL-001",
        policy_version="v1",
        document_path="tests/fixtures/doc.txt",
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        expected_findings=[finding(finding_type=FindingType.CONTRADICTION)],
        evidence_section_alternatives={"VALUE-PAY-001": ["4.1", "12.3"]},
        required_information=[
            RequiredInformation(rule_id="VALUE-PAY-001", must_consult_sections=["4.1", "12.3"])
        ],
    )


def make_trace(
    events: list[TraceEvent] | None = None,
    *,
    case_id: str = "DOC-TEST-1",
    final: AgentOutput | None = None,
    retries: int = 0,
) -> Trace:
    return Trace(
        experiment_id="test",
        case_id=case_id,
        trial_id=1,
        run_id="run-test",
        timestamp_utc="2026-10-01T00:00:00Z",
        config=RunConfig(prompt_version="p1", tool_set_version="t1", agent_version="v1"),
        events=events or [],
        retries=retries,
        final_decision=final.model_dump(mode="json") if final else None,
        totals=TraceTotals(),
    )


def tool_call(seq: int, tool: str, **arguments) -> TraceEvent:
    return TraceEvent(seq=seq, type=EventType.TOOL_CALL, tool=tool, arguments=arguments)


def tool_result(
    seq: int, tool: str, sections: list[str] | None = None, rules: list[str] | None = None
) -> TraceEvent:
    return TraceEvent(
        seq=seq,
        type=EventType.TOOL_RESULT,
        tool=tool,
        ok=True,
        sections_returned=sections or [],
        rules_returned=rules or [],
    )


def tool_error(seq: int, tool: str, error: str, **arguments) -> TraceEvent:
    return TraceEvent(
        seq=seq, type=EventType.TOOL_ERROR, tool=tool, error=error, arguments=arguments, ok=False
    )


def llm_call(seq: int) -> TraceEvent:
    return TraceEvent(seq=seq, type=EventType.LLM_CALL)


def full_trace(case_id: str = "DOC-TEST-1", sections: list[str] | None = None) -> Trace:
    """A clean trace: policy retrieved, sections listed, section read, answer given."""
    sections = sections or ["4.1"]
    events = [
        llm_call(1),
        tool_call(2, "lookup_policy", rule_id="VALUE-PAY-001"),
        tool_result(3, "lookup_policy", rules=["VALUE-PAY-001"]),
        tool_call(4, "list_document_sections"),
        tool_result(5, "list_document_sections"),
    ]
    seq = 6
    for section_id in sections:
        events.append(tool_call(seq, "get_document_section", section_id=section_id))
        events.append(tool_result(seq + 1, "get_document_section", sections=[section_id]))
        seq += 2
    events.append(llm_call(seq))
    return make_trace(events, case_id=case_id)
