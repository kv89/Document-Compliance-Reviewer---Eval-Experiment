"""Dataset sign-off gate tests (spec sections 9.3, 28).

A sign-off is a claim that a human read specific bytes. Two failure modes matter more than the
happy path: an empty table being read as approval, and a real sign-off surviving a regeneration of
the data it approved. The second is the dangerous one, because it looks like approval of something
nobody reviewed.
"""

from __future__ import annotations

import hashlib

import pytest

from agent.schemas.loaders import REPO_ROOT
from dataset.generator.validation_report import build_report, existing_signoff
from experiments.signoff import signoff_status

DATASET = "v1-m1"
BASE = REPO_ROOT / "dataset" / "generated" / DATASET


def test_current_dataset_is_signed_off_and_verified():
    ready, reason = signoff_status(DATASET)
    assert ready, reason
    assert "signed off by" in reason


def test_recorded_hash_matches_the_file_on_disk():
    text = (BASE / "validation.md").read_text(encoding="utf-8")
    actual = hashlib.sha256((BASE / "ground_truth.jsonl").read_bytes()).hexdigest()
    assert actual in text


def test_signoff_survives_report_regeneration():
    """Regenerating the report must not silently revoke a human review."""
    regenerated = build_report(DATASET)
    assert "Vishal Kalaskar" in regenerated
    assert regenerated.count("Until this table is filled in") == 0


def test_signoff_block_is_carried_forward_exactly_once():
    block = existing_signoff(DATASET)
    assert block is not None
    assert block.count("| reviewer |") == 1


def test_empty_table_is_not_a_signoff(tmp_path, monkeypatch):
    _fake_dataset(tmp_path, monkeypatch, reviewer="", result="accepted / rejected", sha="")
    ready, reason = signoff_status("fake")
    assert not ready and "empty" in reason


def test_rejected_review_is_not_a_signoff(tmp_path, monkeypatch):
    _fake_dataset(tmp_path, monkeypatch, reviewer="A Reviewer", result="rejected", sha="x")
    ready, reason = signoff_status("fake")
    assert not ready and "not 'accepted'" in reason


def test_signoff_without_a_hash_cannot_be_verified(tmp_path, monkeypatch):
    _fake_dataset(tmp_path, monkeypatch, reviewer="A Reviewer", result="accepted", sha="")
    ready, reason = signoff_status("fake")
    assert not ready and "cannot be verified" in reason


def test_stale_signoff_is_rejected(tmp_path, monkeypatch):
    """The reviewer approved different bytes. The gate must refuse, not shrug."""
    _fake_dataset(
        tmp_path, monkeypatch, reviewer="A Reviewer", result="accepted", sha="0" * 64
    )
    ready, reason = signoff_status("fake")
    assert not ready and "stale" in reason


def test_missing_validation_file_is_not_a_signoff(tmp_path, monkeypatch):
    monkeypatch.setattr("experiments.signoff.REPO_ROOT", tmp_path)
    ready, reason = signoff_status("fake")
    assert not ready and "never been reviewed" in reason


def _fake_dataset(tmp_path, monkeypatch, *, reviewer: str, result: str, sha: str) -> None:
    base = tmp_path / "dataset" / "generated" / "fake"
    base.mkdir(parents=True)
    (base / "ground_truth.jsonl").write_text("{}\n", encoding="utf-8")
    (base / "validation.md").write_text(
        "## Sign-off\n\n"
        "| field | value |\n|---|---|\n"
        f"| reviewer | {reviewer} |\n"
        f"| result | {result} |\n"
        f"| reviewed ground_truth.jsonl sha256 | {sha} |\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("experiments.signoff.REPO_ROOT", tmp_path)
