"""Run the agent over a dataset and write trial rows and traces (spec sections 23, 29).

Usage:
    export GOOGLE_API_KEY=...
    python -m experiments.run_baseline --config experiments/configs/baseline_v1.yaml
    python -m experiments.run_baseline --config ... --limit 2   # smoke test, 2 cases

Three behaviours here are measurement decisions:

- **Quota failures are separated from agent failures.** A trial killed by a free-tier rejection is
  written with a non-empty `harness_error` and excluded from aggregates, not scored as a wrong
  answer (spec section 6.3).
- **A trial that produces no answer still produces a row.** Dropping failed runs would inflate
  every other metric by removing exactly the hardest cases from the denominator.
- **Per-case wall clock is reported.** Section 7's runtime gate needs it before the full matrix is
  sized, and it is the whole reason Milestone 1 runs 14 cases rather than 175.
"""

from __future__ import annotations

import argparse
import platform
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from agent.agent import Agent
from agent.llm.client import GeminiClient, HarnessError, QuotaPolicy
from agent.prompts.p1 import PROMPT_VERSION
from agent.schemas.loaders import (
    REPO_ROOT,
    load_document,
    load_ground_truth,
    load_policy,
    write_jsonl,
)
from agent.schemas.results import TrialRow
from agent.schemas.trace import RunConfig
from agent.tools.toolset import TOOL_SET_VERSION
from analysis.scripts.aggregate import summarize
from evaluation.deterministic.evaluate import evaluate_case, no_answer_row, to_row
from experiments.signoff import signoff_status


def load_config(path: Path) -> dict:
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    model = config["model"]
    for forbidden in ("-latest", "-preview"):
        if forbidden in model["name"]:
            raise SystemExit(
                f"Refusing to run: model {model['name']!r} contains {forbidden!r}. Spec section 6.4 "
                "forbids moving aliases and previews in a reported baseline, because the result "
                "could not be reproduced later."
            )
    return config


def build_run_config(config: dict, dataset_version: str, policy_version: str) -> RunConfig:
    model = config["model"]
    return RunConfig(
        provider=model["provider"],
        model_name=model["name"],
        model_tag=model.get("tag", model["name"]),
        temperature=model.get("temperature", 0.0),
        top_p=model.get("top_p", 1.0),
        top_k=model.get("top_k"),
        seed=model.get("seed"),
        max_output_tokens=model.get("max_output_tokens"),
        thinking_level=model.get("thinking_level", ""),
        max_steps=config["agent"]["max_steps"],
        python_version=platform.python_version(),
        hardware_id=f"{platform.machine()} {platform.system()} {platform.release()}",
        prompt_version=config.get("prompt_version", PROMPT_VERSION),
        tool_set_version=config.get("tool_set_version", TOOL_SET_VERSION),
        agent_version=config.get("agent_version", Agent.version),
        dataset_version=dataset_version,
        policy_version=policy_version,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--limit", type=int, default=None, help="run only the first N cases")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate config, dataset and sign-off without calling the model",
    )
    parser.add_argument(
        "--no-preflight",
        action="store_true",
        help="skip the single request that checks the model is callable",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    experiment_id = config["experiment_id"]
    dataset_version = config["dataset"]["version"]

    cases = load_ground_truth(dataset_version)
    policy = load_policy(cases[0].policy_id)
    if args.limit:
        cases = cases[: args.limit]

    ready, reason = signoff_status(dataset_version)
    print(f"dataset sign-off: {'verified' if ready else 'MISSING'} — {reason}")

    run_config = build_run_config(config, dataset_version, policy.policy_version)
    print(
        f"{experiment_id}: {len(cases)} cases x {config['run']['trials_per_case']} trial(s) "
        f"on {run_config.model_name}"
    )
    if args.dry_run:
        print("dry run: config, dataset and sign-off check complete. No model was called.")
        return

    quota = config.get("quota", {})
    client = GeminiClient(
        run_config.model_name,
        temperature=run_config.temperature,
        top_p=run_config.top_p,
        top_k=run_config.top_k,
        seed=run_config.seed,
        max_output_tokens=run_config.max_output_tokens,
        thinking_level=run_config.thinking_level or None,
        quota=QuotaPolicy(
            max_retries=quota.get("max_retries", 5),
            initial_backoff_seconds=quota.get("initial_backoff_seconds", 2.0),
            backoff_multiplier=quota.get("backoff_multiplier", 2.0),
            max_backoff_seconds=quota.get("max_backoff_seconds", 60.0),
        ),
    )
    run_config.runtime_version = client.runtime_version

    if not args.no_preflight:
        # One request, to establish that the configured model is callable by this key. A model can
        # be listed by the API and still be closed to new keys, and finding that out trial by trial
        # costs one void row per case. The request also captures the provider-reported model
        # version before any trial runs.
        try:
            probe = client.generate("Reply with the single word: ok", "ok")
        except HarnessError as exc:
            if exc.code == "MODEL_UNAVAILABLE":
                raise SystemExit(
                    f"Model {run_config.model_name!r} is not callable by this key:\n  {exc.message}\n"
                    "Nothing was run. Update `model.name` in the config, then try again."
                ) from exc
            raise SystemExit(f"Preflight failed: {exc}") from exc
        run_config.model_version = probe.model_version or run_config.model_version
        print(
            f"preflight ok: model reports version "
            f"{run_config.model_version or 'nothing'}"
        )

    run_id = f"{experiment_id}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    trace_dir = REPO_ROOT / "results" / "traces" / run_id
    trace_dir.mkdir(parents=True, exist_ok=True)

    rows: list[TrialRow] = []
    wall_clock: list[float] = []
    attempted = 0
    stopped_early = ""
    for case in cases:
        if stopped_early:
            break
        document = load_document(case)
        for trial_id in range(1, int(config["run"]["trials_per_case"]) + 1):
            agent = Agent(client, max_steps=run_config.max_steps)
            started = time.monotonic()
            try:
                result = agent.run(
                    document,
                    policy,
                    config=run_config.model_copy(deep=True),
                    experiment_id=experiment_id,
                    case_id=case.case_id,
                    trial_id=trial_id,
                    run_id=run_id,
                )
            except HarnessError as exc:
                # Raised before a trace existed, so there is nothing to evaluate or store.
                print(f"  {case.case_id} trial {trial_id}: harness failure — {exc}")
                raise
            elapsed = time.monotonic() - started
            wall_clock.append(elapsed)

            trace_path = trace_dir / f"{case.case_id}-t{trial_id}.json"
            trace_path.write_text(
                result.trace.model_dump_json(indent=2), encoding="utf-8"
            )
            relative = str(trace_path.relative_to(REPO_ROOT))

            if result.output is None:
                row = no_answer_row(
                    case,
                    result.trace,
                    experiment_id=experiment_id,
                    run_id=run_id,
                    agent_version=run_config.agent_version,
                    trial_id=trial_id,
                    trace_path=relative,
                    harness_error=result.harness_error,
                )
            else:
                evaluation = evaluate_case(
                    result.output, case, policy, document, trace=result.trace
                )
                row = to_row(
                    evaluation,
                    experiment_id=experiment_id,
                    run_id=run_id,
                    agent_version=run_config.agent_version,
                    trial_id=trial_id,
                    # Without the trace, every tool, trajectory and token metric silently records
                    # zero. The first live run did exactly that.
                    trace=result.trace,
                    trace_path=relative,
                )
            rows.append(row)
            attempted += 1
            print(
                f"  {case.case_id} trial {trial_id}: {row.actual_status} "
                f"({row.deterministic_result}, {elapsed:.1f}s, {row.total_tokens} tokens, "
                f"{row.num_llm_calls} llm calls)"
            )

            if "MODEL_UNAVAILABLE" in row.harness_error:
                stopped_early = "the configured model stopped being callable mid-run"
                print(f"  stopping: {stopped_early}")
                break

            if "DAILY_QUOTA_EXHAUSTED" in row.harness_error:
                # The daily budget is spent. Continuing would collect one identical rejection per
                # remaining case, which costs time and tells us nothing. Stop, keep what was
                # measured, and say so in the report.
                stopped_early = (
                    f"the daily free-tier quota was exhausted after {attempted} of "
                    f"{len(cases) * int(config['run']['trials_per_case'])} planned trials"
                )
                print(f"  stopping: {stopped_early}")
                break

    out_dir = REPO_ROOT / "results" / "raw" / run_id
    written = write_jsonl(out_dir / "trials.jsonl", rows)
    print(f"{written} rows -> {out_dir / 'trials.jsonl'}")

    voided = [r for r in rows if r.harness_error]
    scored = [r for r in rows if not r.harness_error]
    llm_calls = [r.num_llm_calls for r in rows if r.num_llm_calls]

    report = [f"# {experiment_id} — dataset `{dataset_version}`", ""]
    if ready:
        report += [f"> Dataset sign-off verified: {reason}.", ""]
    else:
        report += [
            f"> **Not a reportable result.** {reason}. Spec sections 9.3 and 28.",
            "",
        ]
    report += [
        f"Model `{run_config.model_name}`, reported version "
        f"`{run_config.model_version or 'not reported'}`, temperature {run_config.temperature}, "
        f"seed {run_config.seed}, thinking level "
        f"`{run_config.thinking_level or 'provider default'}`, "
        f"prompt `{run_config.prompt_version}`, tools `{run_config.tool_set_version}`.",
        "",
    ]
    if stopped_early:
        report += [
            f"> **Incomplete run.** This run stopped because {stopped_early}. The cases that were "
            "never attempted are absent from the data rather than recorded as failures, so the "
            "numbers below describe only the trials that ran and must not be read as dataset-wide "
            "results.",
            "",
        ]
    if voided:
        report += [
            f"{len(voided)} of {len(rows)} trials were voided by infrastructure failures and are "
            "excluded from every metric below (spec section 6.3). They are not agent errors.",
            "",
        ]
    report.append(summarize(scored, f"{experiment_id} — {run_config.model_name}"))

    if wall_clock:
        total = sum(wall_clock)
        mean = total / len(wall_clock)
        report += [
            "",
            "## Runtime (spec section 7 gate)",
            "",
            f"- trials: {len(wall_clock)}",
            f"- mean per trial: {mean:.1f} s",
            f"- slowest trial: {max(wall_clock):.1f} s",
            f"- total: {total / 60:.1f} min",
            "",
            f"Projected for 175 cases x 3 trials: {mean * 175 * 3 / 3600:.1f} h per configuration "
            "of model latency alone.",
        ]
        if llm_calls:
            per_trial = sum(llm_calls) / len(llm_calls)
            report += [
                "",
                "### Request budget",
                "",
                f"- mean model requests per trial: {per_trial:.1f}",
                f"- hidden reasoning tokens: {sum(r.thinking_tokens for r in rows)} "
                f"({sum(r.thinking_tokens for r in rows) / max(sum(r.total_tokens for r in rows), 1):.0%} "
                "of all tokens), charged but never returned",
                f"- most in one trial: {max(llm_calls)}",
                f"- requests for 175 cases x 3 trials: {per_trial * 175 * 3:.0f}",
                "",
                "This is the binding constraint on a free tier, not wall clock. A per-day request "
                "cap divided by requests per trial gives the real daily throughput, and the full "
                "matrix must be sized against that number (spec section 7).",
        ]
        print(f"mean {mean:.1f}s per trial, total {total / 60:.1f} min")

    processed = REPO_ROOT / "results" / "processed" / f"{run_id}.md"
    processed.parent.mkdir(parents=True, exist_ok=True)
    processed.write_text("\n".join(report), encoding="utf-8")
    print(f"report -> {processed}")


if __name__ == "__main__":
    sys.exit(main())
