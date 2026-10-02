"""Canonical data models for the Document Compliance Reviewer experiment.

Every component imports its types from this module: the generator, the agent, the tools, the
baselines and the evaluators. A single definition is what makes the three incompatible finding
schemas of design v1 impossible to reintroduce (spec section 8.1).

Deliberate design decision — these models are *structurally* strict and *semantically* lenient.

Field names, types and enum members are enforced at parse time. Cross-field invariants such as
"a COMPLIANT status implies no findings" (S4) or "evidence is null if and only if the finding type
is MISSING_CLAUSE" (S7) are NOT enforced here, because those are exactly the agent behaviours the
safety evaluator must be able to observe and count. If the parser rejected them, every safety
violation would be recorded as an unparseable output and the measurement would be destroyed
(spec sections 11.2, 14 Layer 5).

Ground truth is held to a higher standard: the generator must never emit a case that violates an
invariant. Use `agent.schemas.invariants` for that check, which the generator runs over 100% of
cases (spec section 9.3).
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0"


class _Model(BaseModel):
    """Base model that rejects unknown fields.

    A typo in a field name is a silent data-loss bug in a measurement system, so unknown keys are
    an error rather than being dropped.
    """

    model_config = ConfigDict(extra="forbid", frozen=False)


# --------------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------------


class RuleType(str, Enum):
    CLAUSE_REQUIRED = "CLAUSE_REQUIRED"
    VALUE_CONSTRAINT = "VALUE_CONSTRAINT"
    ENUM_CONSTRAINT = "ENUM_CONSTRAINT"


class Severity(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FindingType(str, Enum):
    MISSING_CLAUSE = "MISSING_CLAUSE"
    POLICY_VIOLATION = "POLICY_VIOLATION"
    CONTRADICTION = "CONTRADICTION"
    AMBIGUOUS = "AMBIGUOUS"


class ComplianceStatus(str, Enum):
    """Three values, not two.

    NEEDS_REVIEW exists so that deliberately ambiguous cases are answerable. Design v1 scored
    ambiguous cases against a two-value enum, which made them unanswerable by construction
    (spec section 8.3).
    """

    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class ScoringMode(str, Enum):
    STRICT = "strict"
    ACCEPT_SET = "accept_set"


class CaseCategory(str, Enum):
    COMPLIANT = "compliant"
    MISSING_CLAUSE = "missing_clause"
    INCORRECT_VALUE = "incorrect_value"
    MULTIPLE_VIOLATIONS = "multiple_violations"
    CONTRADICTORY = "contradictory"
    AMBIGUOUS = "ambiguous"
    DISTRACTOR = "distractor"


# --------------------------------------------------------------------------------------------
# Policy (spec section 3.1)
# --------------------------------------------------------------------------------------------


class PolicyRule(_Model):
    """One compliance requirement.

    Severity is an attribute of the rule, not a judgement the agent makes. This is why
    severity_accuracy was removed as an agent metric and kept only as a consistency check
    (spec sections 3.1, 15.3).
    """

    rule_id: str = Field(min_length=1)
    rule_type: RuleType
    clause: str = Field(min_length=1)
    severity: Severity
    statement: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)


class Policy(_Model):
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    rules: list[PolicyRule] = Field(min_length=1)

    def rule(self, rule_id: str) -> PolicyRule | None:
        for r in self.rules:
            if r.rule_id == rule_id:
                return r
        return None

    @property
    def rule_ids(self) -> set[str]:
        return {r.rule_id for r in self.rules}


# --------------------------------------------------------------------------------------------
# Findings and agent output (spec sections 8.1, 11)
# --------------------------------------------------------------------------------------------


class Evidence(_Model):
    """A located, quotable span of the document.

    There is no page field. Documents are plain text (spec sections 3.2, 11.1). Evidence is
    verifiable by two deterministic checks: the quote occurs verbatim in the document (S2), and
    document[char_start:char_end] equals the quote (S3).
    """

    section_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)


class Finding(_Model):
    rule_id: str = Field(min_length=1)
    finding_type: FindingType
    clause: str = Field(min_length=1)
    severity: Severity
    description: str = ""
    evidence: Evidence | None = None


class AgentOutput(_Model):
    """What the agent, and each reference baseline, must produce.

    Parsed leniently on purpose. See the module docstring.
    """

    status: ComplianceStatus
    findings: list[Finding] = Field(default_factory=list)
    summary: str = ""


# --------------------------------------------------------------------------------------------
# Ground truth (spec section 8.2)
# --------------------------------------------------------------------------------------------


class RequiredInformation(_Model):
    """What must have been consulted before a conclusion on `rule_id` is drawn.

    Order-agnostic by design. This is the operationalisation of spec section 13: we never require a
    fixed tool-call sequence, only that the needed information was obtained before the claim was
    made.
    """

    rule_id: str = Field(min_length=1)
    must_consult_sections: list[str] = Field(default_factory=list)


class Mutation(_Model):
    mutation_id: str = Field(min_length=1)
    target_section: str | None = None
    from_text: str | None = None
    to_text: str | None = None
    expected_effect: str = Field(min_length=1)


class GroundTruthCase(_Model):
    """One test case with its known-correct answer.

    Agent-independent: produced by the generator from the mutation it applied, never from any agent
    output (spec section 8.5).

    Two scoring modes. `strict` cases have one correct answer in `expected_status` and
    `expected_findings`. `accept_set` cases (the ambiguous category) have a set of defensible
    answers in `accepted_statuses` and `accepted_finding_sets`, and are reported as their own
    stratum rather than pooled into single-truth aggregates (spec section 8.3).
    """

    case_id: str = Field(min_length=1)
    dataset_version: str = Field(min_length=1)
    category: CaseCategory
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    document_path: str = Field(min_length=1)
    scoring_mode: ScoringMode = ScoringMode.STRICT

    expected_status: ComplianceStatus | None = None
    accepted_statuses: list[ComplianceStatus] = Field(min_length=1)
    expected_findings: list[Finding] = Field(default_factory=list)
    accepted_finding_sets: list[list[Finding]] | None = None
    unacceptable_statuses: list[ComplianceStatus] = Field(default_factory=list)

    #: rule_id -> section identifiers that are also acceptable evidence for that finding.
    #: Needed by contradiction cases, where the contradiction is spread across two sections and
    #: citing either one is defensible. Ground-truth only: it never appears in agent output, so the
    #: agent contract is unchanged (see docs/decisions.md, 2026-10-01).
    evidence_section_alternatives: dict[str, list[str]] = Field(default_factory=dict)

    required_information: list[RequiredInformation] = Field(default_factory=list)
    prohibited_actions: list[str] = Field(default_factory=list)
    mutations: list[Mutation] = Field(default_factory=list)
    ambiguity_note: str = ""
    notes: str = ""


class DatasetManifest(_Model):
    """Makes the dataset byte-reproducible (spec sections 9.2, 26)."""

    dataset_version: str = Field(min_length=1)
    generator_seed: int
    generator_version: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    created_utc: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    counts_by_category: dict[str, int]
    checksums: dict[str, str]
    schema_version: str = SCHEMA_VERSION
