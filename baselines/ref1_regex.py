"""REF-1: deterministic rule checker as a baseline (spec section 15.1).

No LLM. It answers the question "how much of this task is not actually AI work?" An agent that does
not clearly beat REF-1 has not earned its inference cost.

It shares its implementation with the generator's self-validation checker, so there is exactly one
definition of what a shallow rule check can see (evaluation/deterministic/rule_check.py). Its blind
spots - contradictions spread across sections, qualitative values - are documented and asserted in
tests, because those are precisely the capabilities the agent is meant to add.
"""

from __future__ import annotations

from agent.schemas.models import (
    AgentOutput,
    ComplianceStatus,
    Evidence,
    Finding,
    GroundTruthCase,
    Policy,
)
from evaluation.deterministic.rule_check import check_document

VERSION = "ref1"


def run(document: str, policy: Policy, case: GroundTruthCase) -> AgentOutput:
    del case  # the baseline never sees ground truth
    violations = check_document(document, policy)

    findings: list[Finding] = []
    for v in violations:
        rule = policy.rule(v.rule_id)
        assert rule is not None  # the checker only ever emits rules from this policy
        evidence = None
        if v.quote is not None and v.char_start is not None and v.char_end is not None:
            evidence = Evidence(
                section_id=v.section_id or "",
                quote=v.quote,
                char_start=v.char_start,
                char_end=v.char_end,
            )
        findings.append(
            Finding(
                rule_id=rule.rule_id,
                finding_type=v.finding_type,
                clause=rule.clause,
                severity=rule.severity,
                description=v.detail,
                evidence=evidence,
            )
        )

    status = ComplianceStatus.COMPLIANT if not findings else ComplianceStatus.NON_COMPLIANT
    return AgentOutput(
        status=status,
        findings=findings,
        summary=f"Deterministic rule check found {len(findings)} violation(s).",
    )
