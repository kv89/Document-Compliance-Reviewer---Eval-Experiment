"""The sweep runner stops on quota, keeps what it measured, and resumes (decisions.md, 2026-10-09).

No key and no network: GeminiClient is replaced by a fake that answers instantly and then hits the
daily quota after a fixed number of requests.
"""

from __future__ import annotations

import json
import sys
from collections import Counter

import pytest
import yaml

import experiments.run_baseline as rb
from agent.llm.client import HarnessError, LLMResponse
from agent.schemas.loaders import read_jsonl
from agent.schemas.results import TrialRow

FINAL = json.dumps({"final_answer": {"status": "COMPLIANT", "findings": [], "summary": "s"}})


def _fake_client(budget: list[int]):
    class Fake:
        model_name = model_version = runtime_version = "fake"

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, system, prompt):
            if budget[0] <= 0:
                raise HarnessError("DAILY_QUOTA_EXHAUSTED", "429 per-day limit")
            budget[0] -= 1
            return LLMResponse(text=FINAL, input_tokens=1, output_tokens=1, model_version="fake")

    return Fake


@pytest.fixture
def sweep(tmp_path, monkeypatch):
    base = yaml.safe_load(open("experiments/configs/baseline_v1.yaml", encoding="utf-8"))
    base["dataset"].update(version="v1-m1", cases_per_category=1)
    base["model"]["name"] = "gemini-3.5-flash-lite"
    config = tmp_path / "cfg.yaml"
    config.write_text(yaml.safe_dump(base), encoding="utf-8")
    monkeypatch.setattr(rb, "REPO_ROOT", tmp_path)
    budget = [0]
    monkeypatch.setattr(rb, "GeminiClient", _fake_client(budget))

    def run(requests: int, *extra: str) -> None:
        budget[0] = requests
        monkeypatch.setattr(
            sys, "argv", ["run_baseline", "--config", str(config), "--no-preflight", *extra]
        )
        rb.main()

    return run, tmp_path


def _rows(root, run_id):
    return read_jsonl(root / "results" / "raw" / run_id / "trials.jsonl", TrialRow)


def test_quota_stop_keeps_balanced_rows_and_resume_finishes_without_repeats(sweep):
    run, root = sweep
    run(3)  # 3 good trials, then the daily quota
    run_id = next((root / "results" / "raw").iterdir()).name
    first = _rows(root, run_id)
    good = [r for r in first if not r.harness_error]
    assert len(good) == 3 and len(first) == 4  # 3 measured + 1 void, all written before exit
    assert "DAILY_QUOTA_EXHAUSTED" in first[-1].harness_error
    assert len({r.case_category for r in good}) == 3  # interleaved, not the first category thrice

    run(100, "--resume", run_id)
    final = _rows(root, run_id)
    latest = {(r.case_id, r.trial_id): r for r in final}
    assert len(latest) == 7  # one per category
    assert not any(r.harness_error for r in latest.values())
    assert Counter(r.case_id for r in final if not r.harness_error).most_common(1)[0][1] == 1
    report = (root / "results" / "processed" / f"{run_id}.md").read_text(encoding="utf-8")
    assert "Incomplete run" not in report


def test_resume_refuses_a_run_from_a_different_experiment(sweep, monkeypatch):
    run, root = sweep
    run(2)
    run_id = next((root / "results" / "raw").iterdir()).name
    path = root / "results" / "raw" / run_id / "trials.jsonl"
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    lines[0]["model_name"] = "some-other-model"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    with pytest.raises(SystemExit, match="Refusing to resume"):
        run(100, "--resume", run_id)


def test_repeat_subset_runs_extra_trials_for_subset_and_measures_consistency(tmp_path, monkeypatch):
    """Repeat subset runs extra trials only for selected cases (spec §17, docs/decisions.md 2026-10-15)."""
    base = yaml.safe_load(open("experiments/configs/baseline_v1.yaml", encoding="utf-8"))
    # 2 cases per category = 14 cases total for v1-m1
    base["dataset"].update(version="v1-m1", cases_per_category=2)
    base["model"]["name"] = "gemini-3.5-flash-lite"
    config = tmp_path / "cfg.yaml"
    config.write_text(yaml.safe_dump(base), encoding="utf-8")
    monkeypatch.setattr(rb, "REPO_ROOT", tmp_path)
    budget = [100]
    monkeypatch.setattr(rb, "GeminiClient", _fake_client(budget))

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_baseline",
            "--config",
            str(config),
            "--no-preflight",
            "--repeat-per-category",
            "1",
            "--repeat-trials",
            "3",
        ],
    )
    rb.main()

    run_id = next((tmp_path / "results" / "raw").iterdir()).name
    rows = _rows(tmp_path, run_id)
    assert not any(r.harness_error for r in rows)

    # 1 per category (7 cases) x 3 trials = 21 rows
    # 1 per category (7 cases) x 1 trial = 7 rows
    # Total = 28 rows
    assert len(rows) == 28
    by_case = Counter(r.case_id for r in rows)
    counts = Counter(by_case.values())
    assert counts[3] == 7  # 7 cases had 3 trials
    assert counts[1] == 7  # 7 cases had 1 trial

    report = (tmp_path / "results" / "processed" / f"{run_id}.md").read_text(encoding="utf-8")
    assert "Incomplete run" not in report
    assert "Repeatability subset" in report
    # Headline is trial 1 of every case, not 28 pooled trials (decisions.md, 2026-10-17).
    assert "- executions: 14 over 14 cases" in report
    assert "- trial consistency: 7/7 cases where all trials agreed on status" in report
    assert "## Trial consistency (spec section 17)" in report
    assert "| 3 | 2/7 |" in report  # fake always says COMPLIANT: right on compliant, distractor
    assert "trial consistency: 7/7 cases where all trials agreed on status" in report


def test_prefer_run_pins_the_sample_to_another_runs_cases(tmp_path, monkeypatch):
    """An experiment arm runs on exactly the baseline's cases (decisions.md, 2026-10-18)."""
    monkeypatch.setattr(rb, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(rb, "GeminiClient", _fake_client([100]))

    def sweep(name: str, **dataset) -> str:
        base = yaml.safe_load(open("experiments/configs/baseline_v1.yaml", encoding="utf-8"))
        base["experiment_id"] = name
        base["dataset"].update(version="v1-m1", cases_per_category=1, **dataset)
        config = tmp_path / f"{name}.yaml"
        config.write_text(yaml.safe_dump(base), encoding="utf-8")
        monkeypatch.setattr(sys, "argv", ["run_baseline", "--config", str(config), "--no-preflight"])
        rb.main()
        return next(p.name for p in (tmp_path / "results" / "raw").iterdir() if p.name.startswith(name))

    reference = sweep("reference", sample_seed=8)  # seed 8 picks different cases than seed 7
    pinned = sweep("pinned", sample_seed=7, prefer_run=reference)
    unpinned = sweep("unpinned", sample_seed=7)

    def ids(run_id):
        return {r.case_id for r in _rows(tmp_path, run_id)}

    assert ids(pinned) == ids(reference)
    assert ids(unpinned) != ids(reference)


def test_unknown_prompt_version_stops_before_any_request(sweep, tmp_path):
    run, root = sweep
    config = root / "cfg.yaml"
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["prompt_version"] = "p9"
    config.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(SystemExit, match="Unknown prompt_version 'p9'"):
        run(100)
    assert not (root / "results").exists()


# ---------------------------------------------------------------------------
# REF-2 runner (experiments/run_references.py, docs/decisions/decisions.md 2026-10-17)
# ---------------------------------------------------------------------------

import experiments.run_references as rr  # noqa: E402


def _scripted_ref2_client(script: list[str]):
    """Answers from `script`: "quota" raises the daily-quota error, anything else is returned."""

    class Fake:
        model_name = runtime_version = "fake"

        def __init__(self, *args, **kwargs):
            pass

        def generate(self, system, prompt):
            item = script.pop(0) if script else "quota"
            if item == "quota":
                raise HarnessError("DAILY_QUOTA_EXHAUSTED", "429 per-day limit")
            return LLMResponse(text=item, input_tokens=3, output_tokens=2, model_version="fake-v1")

    return Fake


@pytest.fixture
def ref2(tmp_path, monkeypatch):
    monkeypatch.setattr(rr, "REPO_ROOT", tmp_path)
    script: list[str] = []
    monkeypatch.setattr(rr, "GeminiClient", _scripted_ref2_client(script))

    def run(answers: list[str], *extra: str) -> None:
        script[:] = answers
        monkeypatch.setattr(
            sys,
            "argv",
            ["run_references", "--dataset", "v1-m1", "--cases-per-category", "1",
             "--include-ref2", *extra],
        )
        rr.main()

    return run, tmp_path


def _ref2_run_id(root):
    return next(p.name for p in (root / "results" / "raw").iterdir() if p.name.startswith("ref2"))


def test_ref2_voids_quota_failures_scores_unparseable_and_resumes(ref2):
    run, root = ref2
    answer = json.dumps({"status": "COMPLIANT", "findings": [], "summary": "s"})
    run([answer, "not json at all"])  # 2 answers, then the daily quota
    run_id = _ref2_run_id(root)
    first = _rows(root, run_id)
    assert len(first) == 3  # stopped at the first quota error instead of voiding all 7 cases
    good, unparseable, void = first
    assert good.actual_status == "COMPLIANT" and good.model_version == "fake-v1"
    assert good.num_llm_calls == 1 and good.num_tool_calls == 0
    assert unparseable.actual_status == "NO_ANSWER" and not unparseable.harness_error
    assert unparseable.output_validation == "unparseable"  # the model's failure, counted
    assert "DAILY_QUOTA_EXHAUSTED" in void.harness_error  # infrastructure, excluded
    trace = json.loads((root / unparseable.trace_path).read_text())
    assert trace["final_response_raw"] == "not json at all"
    report = (root / "results" / "processed" / "references-v1-m1-s7-n1.md").read_text()
    assert "Incomplete run" in report and "1 of 3 cases are voided" in report

    run([answer] * 10, "--ref2-resume", run_id)
    latest = {r.case_id: r for r in _rows(root, run_id)}
    assert len(latest) == 7 and not any(r.harness_error for r in latest.values())
    assert latest[unparseable.case_id].output_validation == "unparseable"  # measured, not retried
    report = (root / "results" / "processed" / "references-v1-m1-s7-n1.md").read_text()
    assert "Incomplete run" not in report and "- executions: 7 over 7 cases" in report


def test_reference_dry_run_writes_nothing(ref2):
    run, root = ref2
    run([], "--dry-run")
    assert not (root / "results").exists()
