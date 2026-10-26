"""Read-only status of a sweep: counts by state, throughput, ETA, time since last progress.

    python -m experiments.run_status --config experiments/configs/expA2_p3.yaml --run RUN_ID

Reads only `results/raw/<run>/trials.jsonl`. It calls no model and needs no key. A voided row
(`harness_error` set) is never counted as done: it is waiting for a retry on resume. The planned
sample is rebuilt from the config exactly as `run_baseline` does, so "pending" is exact.
"""

from __future__ import annotations

import argparse
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from agent.schemas.loaders import REPO_ROOT, load_ground_truth, read_jsonl
from agent.schemas.results import TrialRow
from experiments.run_baseline import latest_rows, load_config, measured_case_ids
from experiments.sampling import select_cases

#: Throughput and ETA come from the newest measured rows only. A resumed run spans days of quota
#: stops and sleep, so a whole-run average would be meaningless.
RECENT_ROWS = 10


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def summarize_status(rows: list[TrialRow], planned: int, now: datetime) -> dict:
    latest = latest_rows(rows)
    measured = [r for r in latest if not r.harness_error]
    voided = [r for r in latest if r.harness_error]
    void_reasons = Counter(r.harness_error.split(":")[0].split()[0] for r in voided)
    stamps = sorted(_parse(r.timestamp_utc) for r in rows)
    last = stamps[-1] if stamps else None
    pending = max(planned - len(measured), 0)

    recent = sorted(_parse(r.timestamp_utc) for r in measured)[-RECENT_ROWS:]
    per_hour = eta_hours = None
    if len(recent) >= 2 and recent[-1] > recent[0]:
        per_hour = (len(recent) - 1) / ((recent[-1] - recent[0]).total_seconds() / 3600)
        eta_hours = pending / per_hour
    return {
        "measured": len(measured),
        "voided": len(voided),
        "void_reasons": dict(void_reasons),
        "pending": pending,
        "planned": planned,
        "per_hour": per_hour,
        "eta_hours": eta_hours,
        "seconds_since_last_progress": (now - last).total_seconds() if last else None,
    }


def _process_running() -> bool:
    out = subprocess.run(
        ["pgrep", "-f", "experiments.run_baseline"], capture_output=True, text=True, check=False
    )
    return bool(out.stdout.strip())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--run", required=True, help="run id under results/raw/")
    args = parser.parse_args()

    config = load_config(args.config)
    ds = config["dataset"]
    prefer = measured_case_ids(ds["prefer_run"]) if ds.get("prefer_run") else set()
    path = REPO_ROOT / "results" / "raw" / args.run / "trials.jsonl"
    rows = read_jsonl(path, TrialRow) if path.exists() else []
    prefer |= {r.case_id for r in rows if not r.harness_error}
    cases = select_cases(
        load_ground_truth(ds["version"]),
        ds.get("cases_per_category"),
        int(ds.get("sample_seed", 7)),
        prefer=prefer,
    )
    planned = len(cases) * int(config["run"]["trials_per_case"])
    ids = {c.case_id for c in cases}
    s = summarize_status([r for r in rows if r.case_id in ids], planned, datetime.now(timezone.utc))

    print(f"run {args.run}")
    print(
        f"measured {s['measured']} | voided {s['voided']} {s['void_reasons']} | "
        f"pending {s['pending']} | total {s['planned']}"
    )
    running = _process_running()
    print(f"process running: {'yes' if running else 'no'} (in-flight cannot be read from rows)")
    if s["per_hour"] is not None:
        print(
            f"throughput {s['per_hour']:.1f} trials/h over last {RECENT_ROWS} rows | "
            f"ETA {s['eta_hours']:.1f} h at that rate"
        )
    else:
        print("throughput: not enough rows yet")
    since = s["seconds_since_last_progress"]
    print(f"last progress: {'never' if since is None else f'{since:.0f} s ago'}")


if __name__ == "__main__":
    main()
