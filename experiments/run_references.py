"""Run the reference baselines over a dataset (spec section 15.1).

This runs before the agent exists, on purpose. It proves the measurement apparatus works on cases
whose answers are already known, which is the specific risk spec section 29 exists to retire: a
flawed dataset or evaluator discovered after hundreds of model runs.

Baselines:
- REF-0: Majority class (always NON_COMPLIANT, reads nothing)
- REF-1: Deterministic regex/keyword checker (no LLM)
- REF-2: Single-shot LLM (full document in prompt, no tools)

Usage:
    # Deterministic baselines (REF-0, REF-1):
    python -m experiments.run_references --dataset v1 \\
        --cases-per-category 20 --sample-seed 7 \\
        --prefer-run baseline_v1-20261002T092914Z

    # Including REF-2 (single-shot LLM baseline, requires GOOGLE_API_KEY):
    python -m experiments.run_references --dataset v1 \\
        --cases-per-category 20 --sample-seed 7 \\
        --prefer-run baseline_v1-20261002T092914Z \\
        --include-ref2
"""

from __future__ import annotations

import argparse
import platform
from datetime import datetime, timezone
from pathlib import Path

from agent.llm.client import GeminiClient, HarnessError, QuotaPolicy
from agent.schemas.loaders import (
    REPO_ROOT,
    append_jsonl,
    load_document,
    load_ground_truth,
    load_policy,
    read_jsonl,
    write_jsonl,
)
from agent.schemas.results import TrialRow
from agent.schemas.trace import (
    EventType,
    OutputValidation,
    RunConfig,
    TerminatedReason,
    Trace,
    TraceEvent,
    TraceTotals,
)
from analysis.scripts.aggregate import summarize
from baselines import ref0_majority, ref1_regex, ref2_single_shot
from evaluation.deterministic.evaluate import evaluate_case, no_answer_row, to_row
from experiments.run_baseline import latest_rows, load_config
from experiments.sampling import select_cases
from experiments.signoff import signoff_status

DETERMINISTIC_BASELINES = {
    "ref0_majority": (ref0_majority, "Majority class, always NON_COMPLIANT, reads nothing"),
    "ref1_regex": (ref1_regex, "Deterministic rule check, no LLM"),
}

REF2_EXPERIMENT_ID = "ref2_single_shot"
#: REF-2 borrows the agent baseline's model settings so that the comparison varies one thing.
DEFAULT_REF2_CONFIG = Path("experiments/configs/baseline_v1.yaml")


def _load_measured_ids(run_id: str) -> set[str]:
    """Return the set of case IDs that have a non-voided row in the given run."""
    path = REPO_ROOT / "results" / "raw" / run_id / "trials.jsonl"
    if not path.exists():
        raise SystemExit(
            f"Cannot load prefer-run {run_id!r}: {path} does not exist.\n"
            "Check the run ID or omit --prefer-run to use the full dataset order."
        )
    rows = read_jsonl(path, TrialRow)
    return {r.case_id for r in rows if not r.harness_error}


def run_deterministic_baseline(
    name: str,
    dataset_version: str,
    cases_per_category: int | None = None,
    sample_seed: int = 7,
    prefer: set[str] | None = None,
) -> list[TrialRow]:
    module, _ = DETERMINISTIC_BASELINES[name]
    all_cases = load_ground_truth(dataset_version)
    cases = select_cases(
        all_cases,
        per_category=cases_per_category,
        seed=sample_seed,
        prefer=prefer or (),
    )
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


def ref2_run_config(config: dict, dataset_version: str, policy_version: str) -> RunConfig:
    """REF-2 uses the agent baseline's model settings, so the only difference is the loop and tools."""
    model = config["model"]
    return RunConfig(
        provider=model.get("provider", ""),
        model_name=model["name"],
        model_tag=model.get("tag", model["name"]),
        temperature=float(model.get("temperature", 0.0)),
        top_p=float(model.get("top_p", 1.0)),
        top_k=model.get("top_k"),
        seed=model.get("seed"),
        max_output_tokens=model.get("max_output_tokens"),
        thinking_level=model.get("thinking_level", ""),
        max_steps=1,
        python_version=platform.python_version(),
        hardware_id=f"{platform.machine()} {platform.system()} {platform.release()}",
        prompt_version=ref2_single_shot.VERSION,
        tool_set_version="none",
        agent_version=ref2_single_shot.VERSION,
        dataset_version=dataset_version,
        policy_version=policy_version,
    )


def _ref2_trace(
    case,
    run_id: str,
    run_config: RunConfig,
    metadata: dict,
    validation: OutputValidation,
    error: str = "",
) -> Trace:
    """One-call trace. It keeps the raw response, the only record of what the model said."""
    events: list[TraceEvent] = []
    if metadata:
        events.append(
            TraceEvent(
                seq=1,
                type=EventType.LLM_CALL,
                latency_ms=metadata.get("latency_ms", 0),
                input_tokens=metadata.get("input_tokens", 0),
                output_tokens=metadata.get("output_tokens", 0),
                thinking_tokens=metadata.get("thinking_tokens", 0),
                stop_reason=metadata.get("stop_reason", ""),
            )
        )
    tokens = {k: metadata.get(k, 0) for k in ("input_tokens", "output_tokens", "thinking_tokens")}
    return Trace(
        experiment_id=REF2_EXPERIMENT_ID,
        case_id=case.case_id,
        trial_id=1,
        run_id=run_id,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        config=run_config.model_copy(deep=True),
        events=events,
        errors=[error] if error else [],
        final_response_raw=metadata.get("raw_text", ""),
        output_validation=validation,
        totals=TraceTotals(
            latency_ms=metadata.get("latency_ms", 0),
            num_llm_calls=len(events),
            total_tokens=sum(tokens.values()),
            **tokens,
        ),
        terminated_reason=TerminatedReason.ERROR if error else TerminatedReason.FINAL_ANSWER,
    )


def run_ref2_baseline(
    cases: list,
    policy,
    client,
    run_config: RunConfig,
    run_id: str,
    done: set[str] = frozenset(),
) -> tuple[list[TrialRow], str]:
    """Run REF-2 over the cases not yet measured. Returns (new rows, reason it stopped early or "").

    Mirrors the agent runner's measurement rules (experiments/run_baseline.py): a provider failure
    is written as a void row with `harness_error` and excluded from scoring, never charged to the
    model as a wrong answer; an unparseable answer is the model's failure and counts against it;
    rows are appended per call so a quota stop loses nothing.
    """
    rows_path = REPO_ROOT / "results" / "raw" / run_id / "trials.jsonl"
    trace_dir = REPO_ROOT / "results" / "traces" / run_id
    trace_dir.mkdir(parents=True, exist_ok=True)

    todo = [c for c in cases if c.case_id not in done]
    rows: list[TrialRow] = []
    stopped_early = ""
    for idx, case in enumerate(todo, 1):
        document = load_document(case)
        harness_error = ""
        output = None
        metadata: dict = {}
        try:
            output, metadata = ref2_single_shot.run(document, policy, case, client=client)
        except HarnessError as exc:
            harness_error = f"{exc.code}: {exc.message}"

        if metadata.get("model_version"):
            run_config.model_version = metadata["model_version"]
        run_config.runtime_version = getattr(client, "runtime_version", "")

        if harness_error:
            validation = OutputValidation.NOT_PRODUCED
        elif output is None:
            validation = OutputValidation.UNPARSEABLE
        else:
            validation = OutputValidation.VALID
        trace = _ref2_trace(case, run_id, run_config, metadata, validation, harness_error)
        trace_path = trace_dir / f"{case.case_id}-t1.json"
        trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        relative = str(trace_path.relative_to(REPO_ROOT))

        common = dict(
            experiment_id=REF2_EXPERIMENT_ID,
            run_id=run_id,
            agent_version=ref2_single_shot.VERSION,
            trial_id=1,
            trace_path=relative,
        )
        if output is None:
            row = no_answer_row(case, trace, harness_error=harness_error, **common)
        else:
            # No trace for the safety checks: S1, S6 and S8 judge tool use, and REF-2 has no tools,
            # so they are recorded as skipped, as for REF-0 and REF-1.
            evaluation = evaluate_case(output, case, policy, document, trace=None)
            row = to_row(evaluation, trace=trace, **common)

        rows.append(row)
        append_jsonl(rows_path, [row])
        print(
            f"  [{idx}/{len(todo)}] {case.case_id}: {row.actual_status} "
            f"({row.deterministic_result}{', void: ' + harness_error if harness_error else ''})"
        )

        if "MODEL_UNAVAILABLE" in harness_error:
            stopped_early = "the configured model stopped being callable mid-run"
        elif "DAILY_QUOTA_EXHAUSTED" in harness_error:
            stopped_early = (
                f"the daily free-tier quota was exhausted after {idx} of {len(todo)} planned calls"
            )
        if stopped_early:
            print(f"  stopping: {stopped_early}")
            break

    return rows, stopped_early


def ref2_report(rows: list[TrialRow], run_config: RunConfig, run_id: str, stopped_early: str,
                planned: int) -> str:
    """Summary of the whole REF-2 run so far: the latest row per case, voided rows excluded."""
    voided = [r for r in rows if r.harness_error]
    scored = [r for r in rows if not r.harness_error]
    if len(scored) < planned and not stopped_early:
        stopped_early = f"only {len(scored)} of {planned} planned cases have a measured row"
    lines = [
        f"Run `{run_id}`. Model `{run_config.model_name}`, reported version "
        f"`{run_config.model_version or 'not reported'}`, temperature {run_config.temperature}, "
        f"seed {run_config.seed}, thinking level `{run_config.thinking_level or 'provider default'}`, "
        f"prompt `{run_config.prompt_version}`, no tools.",
        "",
    ]
    if stopped_early:
        lines += [
            f"> **Incomplete run.** REF-2 stopped because {stopped_early}. Resume it with "
            f"`--include-ref2 --ref2-resume {run_id}`. The numbers below cover only the cases "
            "that ran.",
            "",
        ]
    if voided:
        lines += [
            f"{len(voided)} of {len(rows)} cases are voided by infrastructure failures and "
            "excluded from every number below (spec section 6.3).",
            "",
        ]
    lines.append(
        summarize(scored, f"{REF2_EXPERIMENT_ID} — Single LLM call, full document in prompt, no tools")
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument(
        "--cases-per-category",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Run only N cases per category (same seeded sample as the baseline sweep). "
            "Omit to run the full dataset."
        ),
    )
    parser.add_argument(
        "--sample-seed",
        type=int,
        default=7,
        metavar="SEED",
        help="Random seed for the per-category case selection (default: 7, matching baseline_v1).",
    )
    parser.add_argument(
        "--prefer-run",
        default=None,
        metavar="RUN_ID",
        help=(
            "A baseline sweep run ID (e.g. baseline_v1-20261002T092914Z). "
            "The case IDs that were measured in that run are moved to the front of the "
            "per-category shuffle, so the reference sample matches the agent sample exactly. "
            "Only meaningful when --cases-per-category is also set."
        ),
    )
    parser.add_argument(
        "--include-ref2",
        action="store_true",
        help="Also execute REF-2 (single-shot LLM baseline). Requires GOOGLE_API_KEY.",
    )
    parser.add_argument(
        "--ref2-resume",
        default=None,
        metavar="RUN_ID",
        help="Continue a REF-2 run after a quota stop: measured cases are kept, void ones retried.",
    )
    parser.add_argument(
        "--ref2-config",
        type=Path,
        default=DEFAULT_REF2_CONFIG,
        help="Config whose model and quota settings REF-2 uses (default: the agent baseline's).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the dataset, sample and REF-2 config, call no model and write no files.",
    )
    args = parser.parse_args()
    if args.ref2_resume and not args.include_ref2:
        parser.error("--ref2-resume needs --include-ref2")

    prefer: set[str] | None = None
    if args.prefer_run:
        prefer = _load_measured_ids(args.prefer_run)
        print(
            f"prefer-run {args.prefer_run!r}: {len(prefer)} measured case IDs loaded"
        )

    ready, reason = signoff_status(args.dataset)
    print(f"dataset sign-off: {'verified' if ready else 'MISSING'} — {reason}")
    cases = select_cases(
        load_ground_truth(args.dataset),
        per_category=args.cases_per_category,
        seed=args.sample_seed,
        prefer=prefer or (),
    )
    policy = load_policy(cases[0].policy_id)
    case_ids = {c.case_id for c in cases}

    ref2_config: RunConfig | None = None
    ref2_prior: list[TrialRow] = []
    ref2_run_id = ""
    if args.include_ref2:
        config = load_config(args.ref2_config)
        ref2_config = ref2_run_config(config, args.dataset, policy.policy_version)
        if args.ref2_resume:
            prior_path = REPO_ROOT / "results" / "raw" / args.ref2_resume / "trials.jsonl"
            if not prior_path.exists():
                raise SystemExit(f"Cannot resume {args.ref2_resume!r}: {prior_path} does not exist.")
            ref2_prior = latest_rows(read_jsonl(prior_path, TrialRow))
            mismatched = {
                r.model_name for r in ref2_prior if r.model_name != ref2_config.model_name
            } | {r.agent_version for r in ref2_prior if r.agent_version != ref2_single_shot.VERSION}
            if mismatched:
                raise SystemExit(
                    f"Refusing to resume {args.ref2_resume!r}: its rows were produced with "
                    f"{sorted(mismatched)}, not model {ref2_config.model_name!r} and prompt "
                    f"{ref2_single_shot.VERSION!r}."
                )
            ref2_config.model_version = next(
                (r.model_version for r in reversed(ref2_prior) if r.model_version), ""
            )
        ref2_run_id = args.ref2_resume or (
            f"{REF2_EXPERIMENT_ID}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        )

    ref2_done = {r.case_id for r in ref2_prior if not r.harness_error}
    print(f"sample: {len(cases)} cases")
    if args.include_ref2:
        print(
            f"ref2: {len(case_ids - ref2_done)} of {len(cases)} cases to run on "
            f"{ref2_config.model_name}, run {ref2_run_id}"
        )
    if args.dry_run:
        print("dry run: nothing was written and no model was called.")
        return

    sample_desc = (
        f"{args.cases_per_category} cases/category (seed {args.sample_seed})"
        if args.cases_per_category
        else "all cases"
    )
    report: list[str] = [
        f"# Reference baselines — dataset `{args.dataset}` — {sample_desc}",
        "",
    ]
    if ready:
        report += [f"> Dataset sign-off verified: {reason}.", ""]
    else:
        report += [
            f"> **Not a reportable result.** {reason}. This run verifies the experimental "
            "machinery only. Spec sections 9.3 and 28.",
            "",
        ]
    if args.cases_per_category:
        prefer_note = (
            f", case order aligned to run `{args.prefer_run}`" if args.prefer_run else ""
        )
        report += [
            f"> **Sampled run.** {args.cases_per_category} cases per category "
            f"(seed {args.sample_seed}{prefer_note}). "
            "This matches the agent baseline sample so that like-for-like comparison is possible "
            "(docs/decisions/decisions.md, 2026-10-12).",
            "",
        ]
    report += [
        "REF-0 and REF-1 are deterministic and use no model. REF-2, when present, is one model "
        "call per case with no tools. They exist to give the agent's numbers something to be "
        "measured against (spec section 15.1).",
        "",
    ]

    for name, (_, description) in DETERMINISTIC_BASELINES.items():
        rows = run_deterministic_baseline(
            name,
            args.dataset,
            cases_per_category=args.cases_per_category,
            sample_seed=args.sample_seed,
            prefer=prefer,
        )
        out_dir = REPO_ROOT / "results" / "raw" / name
        written = write_jsonl(out_dir / "trials.jsonl", rows)
        report.append(summarize(rows, f"{name} — {description}"))
        print(f"{name}: {written} rows -> {out_dir / 'trials.jsonl'}")

    if args.include_ref2:
        print(f"\nREF-2: single-shot LLM baseline, run {ref2_run_id}")
        quota = config.get("quota", {})
        client = GeminiClient(
            ref2_config.model_name,
            temperature=ref2_config.temperature,
            top_p=ref2_config.top_p,
            top_k=ref2_config.top_k,
            seed=ref2_config.seed,
            max_output_tokens=ref2_config.max_output_tokens,
            thinking_level=ref2_config.thinking_level or None,
            quota=QuotaPolicy(
                max_retries=quota.get("max_retries", 5),
                initial_backoff_seconds=quota.get("initial_backoff_seconds", 2.0),
                backoff_multiplier=quota.get("backoff_multiplier", 2.0),
                max_backoff_seconds=quota.get("max_backoff_seconds", 60.0),
            ),
        )
        new_rows, stopped_early = run_ref2_baseline(
            cases, policy, client, ref2_config, ref2_run_id, done=ref2_done
        )
        rows = [r for r in latest_rows(ref2_prior + new_rows) if r.case_id in case_ids]
        report.append(ref2_report(rows, ref2_config, ref2_run_id, stopped_early, len(cases)))

    dataset_tag = args.dataset
    if args.cases_per_category:
        dataset_tag += f"-s{args.sample_seed}-n{args.cases_per_category}"
    processed = REPO_ROOT / "results" / "processed" / f"references-{dataset_tag}.md"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("\n".join(report), encoding="utf-8")
    print(f"\nreport -> {processed}")


if __name__ == "__main__":
    main()
