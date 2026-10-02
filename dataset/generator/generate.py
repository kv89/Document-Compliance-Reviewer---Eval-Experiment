"""Dataset generator.

Builds synthetic cases by applying controlled mutations to a compliant base document, and derives
the ground truth from the mutation that was applied. Ground truth is therefore agent-independent:
nothing here ever consults an agent, a model or a previous result (spec section 8.5).

Every generated case is checked before it is written (spec section 9.3). A failing check is a
generator bug, never data to be analysed. Design v1 named "discovering after many runs that the
dataset was flawed" as the top project risk but provided no check for it; this module is that
check.

Usage:
    python -m dataset.generator.generate --version v1-m1 --per-category 2 --seed 7
"""

from __future__ import annotations

import argparse
import hashlib
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from agent.schemas.loaders import REPO_ROOT, load_policy, write_jsonl
from agent.schemas.models import (
    AgentOutput,
    CaseCategory,
    ComplianceStatus,
    DatasetManifest,
    Evidence,
    Finding,
    FindingType,
    GroundTruthCase,
    Mutation,
    Policy,
    RequiredInformation,
    ScoringMode,
)
from agent.schemas.invariants import ground_truth_violations
from evaluation.deterministic.rule_check import violated_rule_ids
from agent.tools.splitter import duplicate_section_ids, split_document
from dataset.generator import clauses as cl

GENERATOR_VERSION = "g1"

CATEGORY_ORDER = (
    CaseCategory.COMPLIANT,
    CaseCategory.MISSING_CLAUSE,
    CaseCategory.INCORRECT_VALUE,
    CaseCategory.MULTIPLE_VIOLATIONS,
    CaseCategory.CONTRADICTORY,
    CaseCategory.AMBIGUOUS,
    CaseCategory.DISTRACTOR,
)


@dataclass(frozen=True)
class PendingFinding:
    """An expected finding whose evidence has not yet been located.

    Quotes are resolved to character offsets only after the document is rendered, because the
    offsets depend on the final byte layout of the file.
    """

    rule_id: str
    finding_type: FindingType
    description: str
    quote: str | None = None
    section_id: str | None = None
    alt_sections: tuple[str, ...] = ()


@dataclass
class Blueprint:
    category: CaseCategory
    spec: cl.DocumentSpec
    mutations: list[Mutation] = field(default_factory=list)
    findings: list[PendingFinding] = field(default_factory=list)
    expected_status: ComplianceStatus | None = ComplianceStatus.COMPLIANT
    accepted_statuses: list[ComplianceStatus] = field(default_factory=list)
    scoring_mode: ScoringMode = ScoringMode.STRICT
    accepted_finding_sets: list[list[PendingFinding]] | None = None
    unacceptable_statuses: list[ComplianceStatus] = field(default_factory=list)
    ambiguity_note: str = ""
    notes: str = ""


# ------------------------------------------------------------------------------------------------
# Category builders. One per category of spec section 7.
# ------------------------------------------------------------------------------------------------


def _base(rng: random.Random, payment_days: int, jurisdiction: str) -> cl.DocumentSpec:
    return cl.compliant_spec(
        customer=rng.choice(cl.CUSTOMERS),
        vendor=rng.choice(cl.VENDORS),
        payment_days=payment_days,
        jurisdiction=jurisdiction,
        notice_days=rng.choice((30, 60, 90)),
    )


def _compliant(rng: random.Random, v: int) -> Blueprint:
    days = (30, 45, 15, 45, 30)[v % 5]
    spec = _base(rng, days, cl.APPROVED_JURISDICTIONS[v % 3])
    return Blueprint(
        category=CaseCategory.COMPLIANT,
        spec=spec,
        expected_status=ComplianceStatus.COMPLIANT,
        accepted_statuses=[ComplianceStatus.COMPLIANT],
        notes=f"All five rules satisfied. Payment terms {days} days, at or under the 45-day cap.",
    )


def _missing_clause(rng: random.Random, v: int) -> Blueprint:
    target = (
        (cl.SEC_LIABILITY, "CLAUSE-LIAB-001", "Liability"),
        (cl.SEC_TERMINATION, "CLAUSE-TERM-001", "Termination"),
    )[v % 2]
    section_id, rule_id, clause = target
    spec = _base(rng, 30, cl.APPROVED_JURISDICTIONS[v % 3])
    removed = spec.section(section_id)
    assert removed is not None
    return Blueprint(
        category=CaseCategory.MISSING_CLAUSE,
        spec=spec.without(section_id),
        mutations=[
            Mutation(
                mutation_id="M-REMOVE-CLAUSE",
                target_section=section_id,
                from_text=removed.body,
                to_text=None,
                expected_effect=f"{rule_id} violated: {clause} clause absent",
            )
        ],
        findings=[
            PendingFinding(
                rule_id=rule_id,
                finding_type=FindingType.MISSING_CLAUSE,
                description=f"The document contains no {clause} clause.",
            )
        ],
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        notes=f"Section {section_id} ({clause}) removed entirely.",
    )


def _incorrect_value(rng: random.Random, v: int) -> Blueprint:
    days = (60, 90, 75, 120)[v % 4]
    spec = _base(rng, days, cl.APPROVED_JURISDICTIONS[v % 3])
    return Blueprint(
        category=CaseCategory.INCORRECT_VALUE,
        spec=spec,
        mutations=[
            Mutation(
                mutation_id="M-VALUE-PAY",
                target_section=cl.SEC_PAYMENT,
                from_text="within 45 days of receipt",
                to_text=f"within {days} days of receipt",
                expected_effect=f"VALUE-PAY-001 violated: {days} days exceeds the 45-day cap",
            )
        ],
        findings=[
            PendingFinding(
                rule_id="VALUE-PAY-001",
                finding_type=FindingType.POLICY_VIOLATION,
                description=f"Payment terms of {days} days exceed the 45-day maximum.",
                quote=f"within {days} days of receipt",
                section_id=cl.SEC_PAYMENT,
            )
        ],
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        notes="Payment Terms clause is present, so only the value rule is breached.",
    )


def _multiple_violations(rng: random.Random, v: int) -> Blueprint:
    bad_jurisdiction = ("Delaware", "California", "New South Wales")[v % 3]
    if v % 2 == 0:
        days = (75, 60)[v % 2]
        spec = _base(rng, days, bad_jurisdiction)
        mutations = [
            Mutation(
                mutation_id="M-VALUE-PAY",
                target_section=cl.SEC_PAYMENT,
                from_text="within 45 days of receipt",
                to_text=f"within {days} days of receipt",
                expected_effect=f"VALUE-PAY-001 violated: {days} days exceeds the 45-day cap",
            ),
            Mutation(
                mutation_id="M-ENUM-LAW",
                target_section=cl.SEC_GOVERNING_LAW,
                from_text="India",
                to_text=bad_jurisdiction,
                expected_effect=f"ENUM-LAW-001 violated: {bad_jurisdiction} is not approved",
            ),
        ]
        findings = [
            PendingFinding(
                rule_id="VALUE-PAY-001",
                finding_type=FindingType.POLICY_VIOLATION,
                description=f"Payment terms of {days} days exceed the 45-day maximum.",
                quote=f"within {days} days of receipt",
                section_id=cl.SEC_PAYMENT,
            ),
            PendingFinding(
                rule_id="ENUM-LAW-001",
                finding_type=FindingType.POLICY_VIOLATION,
                description=f"{bad_jurisdiction} is not an approved jurisdiction.",
                quote=f"the laws of {bad_jurisdiction}",
                section_id=cl.SEC_GOVERNING_LAW,
            ),
        ]
        notes = "Two independent rule breaches: payment value and jurisdiction."
    else:
        spec = _base(rng, 30, bad_jurisdiction).without(cl.SEC_LIABILITY)
        mutations = [
            Mutation(
                mutation_id="M-REMOVE-CLAUSE",
                target_section=cl.SEC_LIABILITY,
                expected_effect="CLAUSE-LIAB-001 violated: Liability clause absent",
            ),
            Mutation(
                mutation_id="M-ENUM-LAW",
                target_section=cl.SEC_GOVERNING_LAW,
                from_text="India",
                to_text=bad_jurisdiction,
                expected_effect=f"ENUM-LAW-001 violated: {bad_jurisdiction} is not approved",
            ),
        ]
        findings = [
            PendingFinding(
                rule_id="CLAUSE-LIAB-001",
                finding_type=FindingType.MISSING_CLAUSE,
                description="The document contains no Liability clause.",
            ),
            PendingFinding(
                rule_id="ENUM-LAW-001",
                finding_type=FindingType.POLICY_VIOLATION,
                description=f"{bad_jurisdiction} is not an approved jurisdiction.",
                quote=f"the laws of {bad_jurisdiction}",
                section_id=cl.SEC_GOVERNING_LAW,
            ),
        ]
        notes = "A missing clause and a value breach in one document, with different evidence shapes."

    return Blueprint(
        category=CaseCategory.MULTIPLE_VIOLATIONS,
        spec=spec,
        mutations=mutations,
        findings=findings,
        expected_status=ComplianceStatus.NON_COMPLIANT,
        accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
        notes=notes,
    )


def _contradictory(rng: random.Random, v: int) -> Blueprint:
    if v % 2 == 0:
        spec = _base(rng, 30, cl.APPROVED_JURISDICTIONS[v % 3])
        contradiction = (
            "Notwithstanding clause 4.1, Customer shall settle all invoices "
            "within 60 days of the invoice date."
        )
        spec = spec.appending(
            cl.SectionSpec(cl.SEC_PAYMENT_SCHEDULE, "Payment Schedule", contradiction)
        )
        blueprint = Blueprint(
            category=CaseCategory.CONTRADICTORY,
            spec=spec,
            mutations=[
                Mutation(
                    mutation_id="M-CONTRADICT-PAY",
                    target_section=cl.SEC_PAYMENT_SCHEDULE,
                    to_text=contradiction,
                    expected_effect=(
                        "VALUE-PAY-001 contradicted: section 4.1 states 30 days, "
                        "section 12.3 states 60 days"
                    ),
                )
            ],
            findings=[
                PendingFinding(
                    rule_id="VALUE-PAY-001",
                    finding_type=FindingType.CONTRADICTION,
                    description=(
                        "Section 4.1 requires payment within 30 days while section 12.3 "
                        "requires 60 days. The two cannot both hold."
                    ),
                    quote="within 60 days of the invoice date",
                    section_id=cl.SEC_PAYMENT_SCHEDULE,
                    alt_sections=(cl.SEC_PAYMENT, cl.SEC_PAYMENT_SCHEDULE),
                )
            ],
            expected_status=ComplianceStatus.NON_COMPLIANT,
            accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
            notes=(
                "The 60-day branch also breaches the 45-day cap, so an agent may reasonably report "
                "POLICY_VIOLATION instead of CONTRADICTION. Spec section 8.4 step 5 counts that as "
                "a match with a type error, and both strict and lenient numbers are published."
            ),
        )
    else:
        jurisdiction = cl.APPROVED_JURISDICTIONS[v % 3]
        other = next(j for j in cl.APPROVED_JURISDICTIONS if j != jurisdiction)
        spec = _base(rng, 30, jurisdiction)
        notices = spec.section(cl.SEC_NOTICES)
        assert notices is not None
        new_body = (
            notices.body
            + f" For the avoidance of doubt, this Agreement is governed by the laws of {other}."
        )
        spec = spec.replacing(cl.SEC_NOTICES, new_body)
        blueprint = Blueprint(
            category=CaseCategory.CONTRADICTORY,
            spec=spec,
            mutations=[
                Mutation(
                    mutation_id="M-CONTRADICT-LAW",
                    target_section=cl.SEC_NOTICES,
                    from_text=notices.body,
                    to_text=new_body,
                    expected_effect=(
                        f"ENUM-LAW-001 contradicted: section 8 states {jurisdiction}, "
                        f"section 9 states {other}"
                    ),
                )
            ],
            findings=[
                PendingFinding(
                    rule_id="ENUM-LAW-001",
                    finding_type=FindingType.CONTRADICTION,
                    description=(
                        f"Section 8 names {jurisdiction} as the governing law while section 9 "
                        f"names {other}."
                    ),
                    quote=f"this Agreement is governed by the laws of {other}",
                    section_id=cl.SEC_NOTICES,
                    alt_sections=(cl.SEC_GOVERNING_LAW, cl.SEC_NOTICES),
                )
            ],
            expected_status=ComplianceStatus.NON_COMPLIANT,
            accepted_statuses=[ComplianceStatus.NON_COMPLIANT],
            notes=(
                "Both jurisdictions are individually approved, so this is a pure contradiction "
                "with no underlying value breach."
            ),
        )
    return blueprint


def _ambiguous(rng: random.Random, v: int) -> Blueprint:
    """Accept-set cases.

    These have no single correct answer by construction. They carry a set of defensible answers and
    are reported as their own stratum, never pooled into single-truth aggregates
    (spec section 8.3).
    """
    if v % 2 == 0:
        vague = (
            "This Agreement is governed by the laws of the Vendor's principal place of business, "
            "and the parties submit to the exclusive jurisdiction of its courts."
        )
        spec = _base(rng, 30, cl.APPROVED_JURISDICTIONS[v % 3]).replacing(
            cl.SEC_GOVERNING_LAW, vague
        )
        quote = "the laws of the Vendor's principal place of business"
        rule_id, section_id = "ENUM-LAW-001", cl.SEC_GOVERNING_LAW
        note = (
            "The governing law is defined by reference to a place that the document never states, "
            "so the jurisdiction cannot be checked against the approved list."
        )
        desc_amb = "The governing law is unresolvable from the document."
        desc_vio = "The governing law is not stated as an approved jurisdiction."
    else:
        vague = (
            "Customer shall pay all undisputed invoices promptly following receipt and in any "
            "event within a reasonable period. Invoices are issued monthly in arrears."
        )
        spec = _base(rng, 30, cl.APPROVED_JURISDICTIONS[v % 3]).replacing(cl.SEC_PAYMENT, vague)
        quote = "within a reasonable period"
        rule_id, section_id = "VALUE-PAY-001", cl.SEC_PAYMENT
        note = (
            "The payment period is qualitative, so it cannot be compared against the 45-day cap "
            "either way."
        )
        desc_amb = "The payment period is not quantified, so the 45-day cap cannot be evaluated."
        desc_vio = "The payment period is not demonstrably within the 45-day cap."

    as_ambiguous = PendingFinding(
        rule_id=rule_id,
        finding_type=FindingType.AMBIGUOUS,
        description=desc_amb,
        quote=quote,
        section_id=section_id,
    )
    as_violation = PendingFinding(
        rule_id=rule_id,
        finding_type=FindingType.POLICY_VIOLATION,
        description=desc_vio,
        quote=quote,
        section_id=section_id,
    )
    return Blueprint(
        category=CaseCategory.AMBIGUOUS,
        spec=spec,
        mutations=[
            Mutation(
                mutation_id="M-AMBIGUOUS",
                target_section=section_id,
                to_text=vague,
                expected_effect=f"{rule_id} cannot be decided from the document",
            )
        ],
        findings=[as_ambiguous],
        expected_status=None,
        accepted_statuses=[ComplianceStatus.NEEDS_REVIEW, ComplianceStatus.NON_COMPLIANT],
        scoring_mode=ScoringMode.ACCEPT_SET,
        accepted_finding_sets=[[as_ambiguous], [as_violation]],
        unacceptable_statuses=[ComplianceStatus.COMPLIANT],
        ambiguity_note=note,
        notes="Excluded from the primary aggregates and reported as its own stratum.",
    )


def _distractor(rng: random.Random, v: int) -> Blueprint:
    """Compliant documents carrying irrelevant content.

    The failure mode under test is the false positive: does added noise make the agent invent a
    violation?
    """
    spec = _base(rng, (30, 45)[v % 2], cl.APPROVED_JURISDICTIONS[v % 3])
    extra = cl.DISTRACTOR_SECTIONS[: 2 + (v % 2)]
    for section in extra:
        spec = spec.appending(section)
    return Blueprint(
        category=CaseCategory.DISTRACTOR,
        spec=spec,
        mutations=[
            Mutation(
                mutation_id="M-DISTRACTOR",
                target_section=s.section_id,
                to_text=s.body,
                expected_effect="No rule affected. Irrelevant content only.",
            )
            for s in extra
        ],
        expected_status=ComplianceStatus.COMPLIANT,
        accepted_statuses=[ComplianceStatus.COMPLIANT],
        notes=(
            f"Compliant document plus {len(extra)} irrelevant sections, including a 30-day "
            "expense deadline that must not be mistaken for payment terms."
        ),
    )


BUILDERS = {
    CaseCategory.COMPLIANT: _compliant,
    CaseCategory.MISSING_CLAUSE: _missing_clause,
    CaseCategory.INCORRECT_VALUE: _incorrect_value,
    CaseCategory.MULTIPLE_VIOLATIONS: _multiple_violations,
    CaseCategory.CONTRADICTORY: _contradictory,
    CaseCategory.AMBIGUOUS: _ambiguous,
    CaseCategory.DISTRACTOR: _distractor,
}


# ------------------------------------------------------------------------------------------------
# Finalisation: render, locate evidence, build ground truth
# ------------------------------------------------------------------------------------------------


class GeneratorError(RuntimeError):
    """A generated case failed its own invariants. Always a generator bug, never data."""


def _locate(quote: str, text: str, case_id: str) -> tuple[int, int]:
    """Resolve a quote to character offsets, insisting the quote is unique.

    A quote that occurs twice has no single correct offset, which would make the S3 offset check
    ambiguous and the evidence metric unfalsifiable.
    """
    count = text.count(quote)
    if count == 0:
        raise GeneratorError(f"{case_id}: expected quote absent from document: {quote!r}")
    if count > 1:
        raise GeneratorError(f"{case_id}: expected quote occurs {count} times, must be unique: {quote!r}")
    start = text.index(quote)
    return start, start + len(quote)


def _resolve(pending: PendingFinding, text: str, policy: Policy, case_id: str) -> Finding:
    rule = policy.rule(pending.rule_id)
    if rule is None:
        raise GeneratorError(f"{case_id}: unknown rule_id {pending.rule_id!r}")

    evidence = None
    if pending.finding_type is not FindingType.MISSING_CLAUSE:
        if pending.quote is None or pending.section_id is None:
            raise GeneratorError(
                f"{case_id}: {pending.finding_type.value} needs a quote and a section_id"
            )
        start, end = _locate(pending.quote, text, case_id)
        evidence = Evidence(
            section_id=pending.section_id, quote=pending.quote, char_start=start, char_end=end
        )

    # Severity and clause come from the policy, never from the blueprint. This is what makes
    # severity a derived field rather than a judgement (spec section 3.1).
    return Finding(
        rule_id=rule.rule_id,
        finding_type=pending.finding_type,
        clause=rule.clause,
        severity=rule.severity,
        description=pending.description,
        evidence=evidence,
    )


def _required_information(findings: list[PendingFinding]) -> list[RequiredInformation]:
    """What must have been consulted before each conclusion is drawn.

    Order-agnostic by construction: we record which sections carry the needed information, never
    the order in which they must be visited (spec section 13).

    A contradiction requires both halves of the contradiction, so both sections are listed. A
    missing clause has no section to read, so the requirement reduces to consulting the policy
    rule, and the discovery obligation is enforced separately by S8.
    """
    out: list[RequiredInformation] = []
    for f in findings:
        if f.alt_sections:
            sections = list(f.alt_sections)
        elif f.section_id:
            sections = [f.section_id]
        else:
            sections = []
        out.append(RequiredInformation(rule_id=f.rule_id, must_consult_sections=sections))
    return out


def finalize(
    blueprint: Blueprint, case_id: str, policy: Policy, dataset_version: str, doc_rel_path: str
) -> tuple[GroundTruthCase, str]:
    text = cl.render(blueprint.spec)

    findings = [_resolve(p, text, policy, case_id) for p in blueprint.findings]
    accepted_sets = None
    if blueprint.accepted_finding_sets is not None:
        accepted_sets = [
            [_resolve(p, text, policy, case_id) for p in group]
            for group in blueprint.accepted_finding_sets
        ]

    alternatives = {
        p.rule_id: list(p.alt_sections) for p in blueprint.findings if p.alt_sections
    }

    case = GroundTruthCase(
        case_id=case_id,
        dataset_version=dataset_version,
        category=blueprint.category,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        document_path=doc_rel_path,
        scoring_mode=blueprint.scoring_mode,
        expected_status=blueprint.expected_status,
        accepted_statuses=blueprint.accepted_statuses,
        expected_findings=findings,
        accepted_finding_sets=accepted_sets,
        unacceptable_statuses=blueprint.unacceptable_statuses,
        evidence_section_alternatives=alternatives,
        required_information=_required_information(blueprint.findings),
        mutations=blueprint.mutations,
        ambiguity_note=blueprint.ambiguity_note,
        notes=blueprint.notes,
    )
    return case, text


# ------------------------------------------------------------------------------------------------
# Validation (spec section 9.3). Runs over 100% of cases before anything is written.
# ------------------------------------------------------------------------------------------------

#: Categories whose mutation the shallow reference checker must be able to see. If it cannot, the
#: mutation silently failed.
_REGEX_DETECTABLE = {
    CaseCategory.MISSING_CLAUSE,
    CaseCategory.INCORRECT_VALUE,
    CaseCategory.MULTIPLE_VIOLATIONS,
}

#: Categories that must look clean to the reference checker. For compliant and distractor cases
#: that proves no accidental violation was introduced. For contradiction cases it documents the
#: checker's blind spot, which is exactly the capability the agent is meant to add.
_MUST_LOOK_CLEAN = {
    CaseCategory.COMPLIANT,
    CaseCategory.DISTRACTOR,
    CaseCategory.CONTRADICTORY,
}


def validate_case(case: GroundTruthCase, text: str, policy: Policy) -> list[str]:
    """Return every problem found with one generated case. Empty list means the case is sound."""
    problems: list[str] = []
    doc = split_document(text)

    dupes = duplicate_section_ids(doc)
    if dupes:
        problems.append(f"duplicate section ids {dupes}")

    # Structural invariants, against the same predicates the safety evaluator uses.
    groups = case.accepted_finding_sets or [case.expected_findings]
    for i, group in enumerate(groups):
        status = case.expected_status or case.accepted_statuses[0]
        if group and status is ComplianceStatus.COMPLIANT:
            status = ComplianceStatus.NON_COMPLIANT
        output = AgentOutput(status=status, findings=group)
        problems += [f"finding set {i}: {m}" for m in ground_truth_violations(output, policy, text)]

    # Cited sections must exist, and the quote must sit inside the section it claims.
    for group in groups:
        for f in group:
            if f.evidence is None:
                continue
            section = doc.section(f.evidence.section_id)
            if section is None:
                problems.append(f"{f.rule_id}: cited section {f.evidence.section_id!r} not in document")
            elif not section.contains(f.evidence.char_start, f.evidence.char_end):
                problems.append(
                    f"{f.rule_id}: quote lies outside section {f.evidence.section_id}"
                )

    # Mutation effect actually occurred, judged by an independent checker.
    detected = violated_rule_ids(text, policy)
    if case.category in _REGEX_DETECTABLE:
        expected_ids = {f.rule_id for f in case.expected_findings}
        missed = expected_ids - detected
        if missed:
            problems.append(
                f"mutation appears not to have taken effect: {sorted(missed)} not detected "
                "by the reference checker"
            )
    if case.category in _MUST_LOOK_CLEAN and detected:
        problems.append(
            f"reference checker found unintended violations {sorted(detected)} "
            f"in a {case.category.value} case"
        )

    # Status and findings must agree with each other.
    if case.scoring_mode is ScoringMode.STRICT:
        if case.expected_status is None:
            problems.append("strict case has no expected_status")
        if case.expected_status is ComplianceStatus.COMPLIANT and case.expected_findings:
            problems.append("compliant case carries expected findings")
        if case.expected_status is ComplianceStatus.NON_COMPLIANT and not case.expected_findings:
            problems.append("non-compliant case carries no expected findings")
    else:
        if case.expected_status is not None:
            problems.append("accept_set case must leave expected_status null")
        if not case.accepted_finding_sets:
            problems.append("accept_set case has no accepted_finding_sets")
        if ComplianceStatus.COMPLIANT in case.accepted_statuses:
            problems.append("COMPLIANT must not be acceptable for an ambiguous case")

    # Every expected finding needs its required information declared, or Layer 3 has nothing to
    # check against.
    declared = {r.rule_id for r in case.required_information}
    for f in case.expected_findings:
        if f.rule_id not in declared:
            problems.append(f"{f.rule_id}: no required_information entry")

    return problems


# ------------------------------------------------------------------------------------------------
# Build and write
# ------------------------------------------------------------------------------------------------


def build_dataset(
    dataset_version: str, per_category: int, seed: int, policy: Policy
) -> list[tuple[GroundTruthCase, str]]:
    """Build every case in memory and validate it. Nothing is written until all cases pass."""
    rng = random.Random(seed)
    cases: list[tuple[GroundTruthCase, str]] = []
    index = 0
    all_problems: list[str] = []

    for category in CATEGORY_ORDER:
        builder = BUILDERS[category]
        for v in range(per_category):
            index += 1
            case_id = f"DOC-{index:04d}"
            blueprint = builder(rng, v)
            doc_rel = f"dataset/generated/{dataset_version}/{case_id}.txt"
            case, text = finalize(blueprint, case_id, policy, dataset_version, doc_rel)
            problems = validate_case(case, text, policy)
            all_problems += [f"{case_id} [{category.value}]: {p}" for p in problems]
            cases.append((case, text))

    if all_problems:
        raise GeneratorError(
            "dataset validation failed, nothing written:\n  " + "\n  ".join(all_problems)
        )
    return cases


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_dataset(
    dataset_version: str, cases: list[tuple[GroundTruthCase, str]], seed: int, policy: Policy
) -> Path:
    out_dir = REPO_ROOT / "dataset" / "generated" / dataset_version
    out_dir.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    for case, text in cases:
        path = REPO_ROOT / case.document_path
        # newline="" keeps the bytes exactly as rendered. Newline translation would shift every
        # character offset in the ground truth.
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        checksums[f"{case.case_id}.txt"] = _sha256(text.encode("utf-8"))

    gt_path = out_dir / "ground_truth.jsonl"
    write_jsonl(gt_path, [c for c, _ in cases])
    checksums["ground_truth.jsonl"] = _sha256(gt_path.read_bytes())

    counts: dict[str, int] = {}
    for case, _ in cases:
        counts[case.category.value] = counts.get(case.category.value, 0) + 1

    manifest = DatasetManifest(
        dataset_version=dataset_version,
        generator_seed=seed,
        generator_version=GENERATOR_VERSION,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        created_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        case_count=len(cases),
        counts_by_category=counts,
        checksums=checksums,
    )
    (out_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a synthetic compliance dataset.")
    parser.add_argument("--version", required=True, help="dataset version, e.g. v1-m1")
    parser.add_argument("--per-category", type=int, default=2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--policy", default="POL-001")
    args = parser.parse_args()

    policy = load_policy(args.policy)
    cases = build_dataset(args.version, args.per_category, args.seed, policy)
    out_dir = write_dataset(args.version, cases, args.seed, policy)

    print(f"dataset {args.version}: {len(cases)} cases validated and written to {out_dir}")
    for case, _ in cases:
        rules = ",".join(f.rule_id for f in case.expected_findings) or "-"
        print(
            f"  {case.case_id}  {case.category.value:<20} {case.scoring_mode.value:<11} "
            f"{(case.expected_status.value if case.expected_status else 'accept-set'):<14} {rules}"
        )


if __name__ == "__main__":
    main()
