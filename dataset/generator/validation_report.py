"""Emit the human spot-check report for a generated dataset (spec section 9.3).

The automated invariant checks already ran inside the generator and nothing was written unless
they passed. This report exists for the part a machine cannot do: confirming that the ground truth
a human reads agrees with the document a human reads.

Usage:
    python -m dataset.generator.validation_report --version v1-m1
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from agent.schemas.loaders import REPO_ROOT, load_policy, read_jsonl
from agent.schemas.models import DatasetManifest, GroundTruthCase, ScoringMode
from agent.tools.splitter import split_document
from evaluation.deterministic.rule_check import violated_rule_ids


def _context(text: str, start: int, end: int, radius: int = 70) -> str:
    left = text[max(0, start - radius) : start].replace("\n", " ")
    hit = text[start:end]
    right = text[end : end + radius].replace("\n", " ")
    return f"...{left}[[{hit}]]{right}..."


def build_report(version: str) -> str:
    out_dir = REPO_ROOT / "dataset" / "generated" / version
    cases = read_jsonl(out_dir / "ground_truth.jsonl", GroundTruthCase)
    manifest = DatasetManifest.model_validate_json((out_dir / "manifest.json").read_text())
    policy = load_policy(manifest.policy_id)

    lines: list[str] = []
    add = lines.append

    add(f"# Dataset validation — {version}")
    add("")
    add("Spec section 9.3. Two gates: automated invariant checks on 100% of cases, and a human")
    add("spot-check. The dataset is not ready for agent runs until both are signed off.")
    add("")
    add("## Provenance")
    add("")
    add(f"- dataset_version: `{manifest.dataset_version}`")
    add(f"- generator_version: `{manifest.generator_version}`")
    add(f"- generator_seed: `{manifest.generator_seed}`")
    add(f"- policy: `{manifest.policy_id}` `{manifest.policy_version}`")
    add(f"- created_utc: `{manifest.created_utc}`")
    add(f"- cases: {manifest.case_count} — {json.dumps(manifest.counts_by_category)}")
    add("")
    add("Regenerate byte-identically with:")
    add("")
    add("```")
    add(f"python -m dataset.generator.generate --version {version} "
        f"--per-category {manifest.case_count // len(manifest.counts_by_category)} "
        f"--seed {manifest.generator_seed}")
    add("```")
    add("")

    add("## Automated gate (passed — the generator refuses to write otherwise)")
    add("")
    add("Checked for every case:")
    add("")
    add("- no duplicate section identifiers;")
    add("- every expected evidence quote appears exactly once in the document (S2), and its")
    add("  character offsets resolve to that quote (S3);")
    add("- every cited section exists, and the quote lies inside it;")
    add("- severity and clause equal the policy rule's values;")
    add("- `MISSING_CLAUSE` findings carry no evidence, all other types carry evidence (S7);")
    add("- status and findings agree (S4), and accept-set cases never accept `COMPLIANT`;")
    add("- every expected finding has a `required_information` entry;")
    add("- the mutation actually took effect, judged by the independent reference checker.")
    add("")

    add("## Independent reference check")
    add("")
    add("Each document re-checked by `evaluation/deterministic/rule_check.py`, which never sees the")
    add("ground truth. `-` means it found nothing.")
    add("")
    add("| case | category | reference checker sees | expected rules |")
    add("|---|---|---|---|")
    for case in cases:
        detected = sorted(violated_rule_ids(_read(case), policy)) or ["-"]
        expected = sorted({f.rule_id for f in case.expected_findings}) or ["-"]
        add(f"| {case.case_id} | {case.category.value} | {', '.join(detected)} "
            f"| {', '.join(expected)} |")
    add("")
    add("Contradiction cases are expected to show `-`: the checker only looks inside the section")
    add("whose title matches the clause, so a contradiction spread across two sections is invisible")
    add("to it. That blind spot is the capability the agent is meant to add, and it is asserted in")
    add("`tests/test_rule_check.py` so it cannot disappear unnoticed.")
    add("")

    add("## Human spot-check")
    add("")
    add("For each case: read the quoted context, then confirm the verdict column is right. Mark the")
    add("checkbox or write what is wrong.")
    add("")

    for case in cases:
        text = _read(case)
        doc = split_document(text)
        add(f"### {case.case_id} — {case.category.value}")
        add("")
        add(f"- document: `{case.document_path}`")
        add(f"- scoring mode: `{case.scoring_mode.value}`")
        if case.scoring_mode is ScoringMode.STRICT:
            add(f"- **expected status: `{case.expected_status.value}`**")
        else:
            add("- **expected status: any of "
                f"`{', '.join(s.value for s in case.accepted_statuses)}`**")
            add(f"- unacceptable: `{', '.join(s.value for s in case.unacceptable_statuses)}`")
            add(f"- ambiguity: {case.ambiguity_note}")
        add(f"- sections present: {', '.join(doc.section_ids)}")
        if case.notes:
            add(f"- note: {case.notes}")
        add("")

        groups = case.accepted_finding_sets or [case.expected_findings]
        if not any(groups):
            add("Expected findings: **none**. Confirm the document really does satisfy all five")
            add("rules, and that nothing in it should be read as a violation.")
            add("")
        for gi, group in enumerate(groups):
            if case.scoring_mode is ScoringMode.ACCEPT_SET:
                add(f"Accepted answer {gi + 1} of {len(groups)}:")
                add("")
            for f in group:
                add(f"- `{f.rule_id}` **{f.finding_type.value}** "
                    f"({f.clause}, severity {f.severity.value})")
                add(f"  - claim: {f.description}")
                if f.evidence is None:
                    add("  - evidence: none, correct for a missing clause")
                else:
                    add(f"  - cites section {f.evidence.section_id}, "
                        f"chars {f.evidence.char_start}-{f.evidence.char_end}")
                    add(f"  - context: `{_context(text, f.evidence.char_start, f.evidence.char_end)}`")
                alt = case.evidence_section_alternatives.get(f.rule_id)
                if alt:
                    add(f"  - citing any of sections {', '.join(alt)} is accepted")
            add("")
        for m in case.mutations:
            add(f"- mutation `{m.mutation_id}` on section {m.target_section}: {m.expected_effect}")
        if case.mutations:
            add("")
        add(f"- [ ] {case.case_id} verdict is correct")
        add("")

    add("## Sign-off")
    add("")
    existing = existing_signoff(version)
    if existing:
        add(SIGNED_OFF_NOTE)
        add("")
        # Preserve a sign-off that has already been given. Regenerating the report must never
        # silently revoke a human review, and must never silently keep one either: the hash below
        # ties the sign-off to the exact bytes that were reviewed.
        add(existing)
    else:
        add("| field | value |")
        add("|---|---|")
        add("| reviewer | |")
        add("| date | |")
        add("| cases reviewed | / " + str(len(cases)) + " |")
        add("| result | accepted / rejected |")
        add("| reviewed ground_truth.jsonl sha256 | |")
        add("| notes | |")
        add("")
        add("Until this table is filled in, the dataset is not ready and no agent run against it")
        add("may be reported as a result (spec sections 9.3, 28).")
        add("")
    return "\n".join(lines)


SIGNED_OFF_NOTE = (
    "This dataset is signed off. The sha256 below ties the sign-off to the exact "
    "`ground_truth.jsonl` bytes that were reviewed; regenerating the dataset invalidates it and "
    "`experiments/run_references.py` will refuse to treat the run as reportable."
)

#: The unsigned template's trailing warning, removed before a signed block is carried forward.
_BOILERPLATE = re.compile(
    r"\n*Until this table is filled in.*?\(spec sections 9\.3, 28\)\.\n*", re.DOTALL
)

#: Everything from the sign-off heading to the end of the file.
_SIGNOFF = re.compile(r"^## Sign-off\s*$(?P<body>.*)\Z", re.MULTILINE | re.DOTALL)


def existing_signoff(version: str) -> str | None:
    """Return a previously written sign-off block, if the reviewer field has been filled in.

    An unfilled template is not a sign-off, so it is discarded and regenerated.
    """
    path = REPO_ROOT / "dataset" / "generated" / version / "validation.md"
    if not path.exists():
        return None
    match = _SIGNOFF.search(path.read_text(encoding="utf-8"))
    if match is None:
        return None
    body = _BOILERPLATE.sub("", match.group("body")).strip("\n")
    reviewer = re.search(r"\|\s*reviewer\s*\|(?P<value>[^|]*)\|", body)
    if reviewer is None or not reviewer.group("value").strip():
        return None
    return body


def _read(case: GroundTruthCase) -> str:
    path = REPO_ROOT / case.document_path
    with path.open(encoding="utf-8", newline="") as fh:
        return fh.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    out = REPO_ROOT / "dataset" / "generated" / args.version / "validation.md"
    out.write_text(build_report(args.version).rstrip("\n") + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
