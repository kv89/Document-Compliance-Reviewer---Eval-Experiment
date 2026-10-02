"""Deterministic rule checker. No LLM.

Two consumers, one definition:

1. Reference baseline REF-1 (spec section 15.1). It answers "how much of this task is not actually
   AI work?" An agent that does not clearly beat this number has not earned its inference cost.
2. Generator self-validation (spec section 9.3). It independently confirms that a mutation actually
   produced the effect the ground truth claims.

The checker is deliberately shallow: it looks for each rule inside the section whose title matches
the rule's clause. It therefore cannot see a contradiction spread across two sections, and it
cannot resolve a qualitative payment period. Those blind spots are not defects, they are the
measurement: they are what the agent is supposed to be better at, and the generator asserts them
so the limits stay documented rather than assumed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from agent.schemas.models import (
    FindingType,
    Policy,
    PolicyRule,
    RuleType,
)
from agent.tools.splitter import ParsedDocument, Section, split_document

#: "within 60 days" -> 60
_DAYS = re.compile(r"within\s+(\d+)\s+days", re.IGNORECASE)
#: "the laws of Delaware," -> Delaware. Stops at a comma or sentence end.
_JURISDICTION = re.compile(r"laws of\s+(?P<name>[^,.;]+)", re.IGNORECASE)


@dataclass(frozen=True)
class RuleViolation:
    rule_id: str
    finding_type: FindingType
    section_id: str | None
    quote: str | None
    char_start: int | None
    char_end: int | None
    detail: str


def _section_for_clause(doc: ParsedDocument, clause: str) -> Section | None:
    wanted = clause.strip().lower()
    for section in doc.sections:
        if section.title.strip().lower() == wanted:
            return section
    return None


def _check_clause_required(doc: ParsedDocument, rule: PolicyRule) -> list[RuleViolation]:
    if _section_for_clause(doc, rule.clause) is not None:
        return []
    return [
        RuleViolation(
            rule_id=rule.rule_id,
            finding_type=FindingType.MISSING_CLAUSE,
            section_id=None,
            quote=None,
            char_start=None,
            char_end=None,
            detail=f"No section titled {rule.clause!r}",
        )
    ]


def _check_value_constraint(doc: ParsedDocument, rule: PolicyRule) -> list[RuleViolation]:
    section = _section_for_clause(doc, rule.clause)
    if section is None:
        return []  # absence is CLAUSE_REQUIRED's business, not this rule's
    limit = int(rule.params["value"])
    out: list[RuleViolation] = []
    for match in _DAYS.finditer(section.body):
        days = int(match.group(1))
        if days > limit:
            start = section.char_start + match.start()
            out.append(
                RuleViolation(
                    rule_id=rule.rule_id,
                    finding_type=FindingType.POLICY_VIOLATION,
                    section_id=section.section_id,
                    quote=match.group(0),
                    char_start=start,
                    char_end=start + len(match.group(0)),
                    detail=f"{days} days exceeds the {limit}-day maximum",
                )
            )
    return out


def _check_enum_constraint(doc: ParsedDocument, rule: PolicyRule) -> list[RuleViolation]:
    section = _section_for_clause(doc, rule.clause)
    if section is None:
        return []
    allowed = {a.strip().lower() for a in rule.params["allowed"]}
    match = _JURISDICTION.search(section.body)
    if match is None:
        return []
    name = match.group("name").strip()
    if name.lower() in allowed:
        return []
    start = section.char_start + match.start("name")
    return [
        RuleViolation(
            rule_id=rule.rule_id,
            finding_type=FindingType.POLICY_VIOLATION,
            section_id=section.section_id,
            quote=name,
            char_start=start,
            char_end=start + len(name),
            detail=f"{name!r} is not in the approved list",
        )
    ]


_CHECKS = {
    RuleType.CLAUSE_REQUIRED: _check_clause_required,
    RuleType.VALUE_CONSTRAINT: _check_value_constraint,
    RuleType.ENUM_CONSTRAINT: _check_enum_constraint,
}


def check_document(document: str, policy: Policy) -> list[RuleViolation]:
    """Return every violation this checker can see, in policy rule order."""
    doc = split_document(document)
    out: list[RuleViolation] = []
    for rule in policy.rules:
        out.extend(_CHECKS[rule.rule_type](doc, rule))
    return out


def violated_rule_ids(document: str, policy: Policy) -> set[str]:
    return {v.rule_id for v in check_document(document, policy)}
