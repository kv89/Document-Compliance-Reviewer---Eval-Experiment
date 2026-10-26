"""The status command counts states exactly and never counts a void as done."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from experiments.run_status import summarize_status


def _row(case, minute, error="", trial=1):
    return SimpleNamespace(
        case_id=case,
        trial_id=trial,
        harness_error=error,
        timestamp_utc=f"2026-10-25T10:{minute:02d}:00Z",
    )


NOW = datetime(2026, 10, 25, 10, 30, tzinfo=timezone.utc)


def test_voids_are_not_done_and_a_retry_supersedes_its_void():
    rows = [
        _row("A", 0),
        _row("B", 1, "EMPTY_RESPONSE: no text"),
        _row("C", 2, "PROVIDER_ERROR: timeout"),
        _row("C", 3),  # retry of C wins over its void
    ]
    s = summarize_status(rows, planned=5, now=NOW)
    assert (s["measured"], s["voided"], s["pending"], s["planned"]) == (2, 1, 3, 5)
    assert s["void_reasons"] == {"EMPTY_RESPONSE": 1}


def test_seconds_since_last_progress_uses_the_newest_row():
    s = summarize_status([_row("A", 0), _row("B", 20)], planned=2, now=NOW)
    assert s["seconds_since_last_progress"] == 600


def test_throughput_and_eta_come_from_recent_measured_rows():
    rows = [_row(f"C{i}", i * 6) for i in range(6)]  # 5 intervals of 6 min = 30 min
    s = summarize_status(rows, planned=16, now=NOW)
    assert round(s["per_hour"], 6) == 10.0
    assert round(s["eta_hours"], 6) == 1.0  # 10 pending at 10/h


def test_empty_run_has_no_rate_and_no_progress_time():
    s = summarize_status([], planned=140, now=NOW)
    assert (s["measured"], s["pending"]) == (0, 140)
    assert s["per_hour"] is None and s["seconds_since_last_progress"] is None
