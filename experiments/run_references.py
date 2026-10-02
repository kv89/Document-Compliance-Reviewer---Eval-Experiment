"""Run the no-LLM reference baselines over a dataset (spec section 15.1).

This runs before the agent exists, on purpose. It proves the measurement apparatus works on cases
whose answers are already known, which is the specific risk spec section 29 exists to retire: a
flawed dataset or evaluator discovered after hundreds of model runs.

Usage:
    python -m experiments.run_references --dataset v1-m1
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from agent.schemas.loaders import (
    REPO_ROOT,
    load_document,
    load_ground_truth,
    load_policy,
    write_jsonl,
)
from agent.schemas.results import TrialRow
from analysis.scripts.aggregate import summarize
from baselines import ref0_majority, ref1_regex
from evaluation.deterministic.evaluate import evaluate_case, to_row
from experiments.signoff import signoff_status

BASELINES = {
    "ref0_majority": (ref0_majority, "Majority class, always NON_COMPLIANT, reads nothing"),
    "ref1_regex": (ref1_regex, "Deterministic rule check, no LLM"),
}


def run_baseline(name: str, dataset_version: str) -> list[TrialRow]:
    module, _ = BASELINES[name]
    cases = load_ground_truth(dataset_version)
    policy = load_policy(cases[0].policy_id)
    run_id = f"{name}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    rows: list[TrialRow] = []
    for case in cases:
        document = load_document(case)
        output = module.run(document, policy, case)
        evaluation = evaluate_case(output, case, policy, document, trace=None)
        rows.append(
            to_row(
                evaluation,
                experiment_id=name,
                run_id=run_id,
                agent_version=module.VERSION,
                trial_id=1,
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    args = parser.parse_args()

    ready, reason = signoff_status(args.dataset)
    report: list[str] = [f"# Reference baselines — dataset `{args.dataset}`", ""]
    if ready:
        report += [f"> Dataset sign-off verified: {reason}.", ""]
    else:
        report += [
            f"> **Not a reportable result.** {reason}. This run verifies the experimental "
            "machinery only. Spec sections 9.3 and 28.",
            "",
        ]
    print(f"dataset sign-off: {'verified' if ready else 'MISSING'} — {reason}")
    report += [
        "Both baselines are deterministic and use no model. They exist to give the agent's "
        "numbers something to be measured against (spec section 15.1).",
        "",
    ]

    for name, (_, description) in BASELINES.items():
        rows = run_baseline(name, args.dataset)
        out_dir = REPO_ROOT / "results" / "raw" / name
        written = write_jsonl(out_dir / "trials.jsonl", rows)
        report.append(summarize(rows, f"{name} — {description}"))
        print(f"{name}: {written} rows -> {out_dir / 'trials.jsonl'}")

    processed = REPO_ROOT / "results" / "processed" / f"references-{args.dataset}.md"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("\n".join(report), encoding="utf-8")
    print(f"report -> {processed}")


if __name__ == "__main__":
    main()
