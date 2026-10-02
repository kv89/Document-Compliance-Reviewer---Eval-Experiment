"""REF-0: majority-class baseline (spec section 15.1).

Always answers NON_COMPLIANT and reports no findings. It requires no model, no tools and no
document.

Its purpose is to establish the floor that any status-accuracy claim must beat. On a dataset where
most cases are non-compliant, a number like "71% status accuracy" can be produced by a program that
reads nothing at all. Design v1 had no such reference, which would have made the agent's headline
number uninterpretable.
"""

from __future__ import annotations

from agent.schemas.models import AgentOutput, ComplianceStatus, GroundTruthCase, Policy

VERSION = "ref0"


def run(document: str, policy: Policy, case: GroundTruthCase) -> AgentOutput:
    del document, policy, case  # deliberately unused: that is the point of this baseline
    return AgentOutput(
        status=ComplianceStatus.NON_COMPLIANT,
        findings=[],
        summary="Majority-class baseline. No document was read.",
    )
