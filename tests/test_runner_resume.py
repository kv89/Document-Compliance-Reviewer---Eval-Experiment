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
