"""Case selection for quota-truncated sweeps (docs/decisions.md, 2026-10-09)."""

from __future__ import annotations

from collections import Counter

from agent.schemas.loaders import load_ground_truth
from experiments.sampling import select_cases

CASES = load_ground_truth("v1")


def test_selection_is_equal_per_category_and_unique():
    picked = select_cases(CASES, per_category=20, seed=7)
    assert len(picked) == 140
    assert len({c.case_id for c in picked}) == 140
    assert set(Counter(c.category for c in picked).values()) == {20}


def test_every_prefix_is_balanced_across_categories():
    picked = select_cases(CASES, per_category=20, seed=7)
    for stop in (7, 28, 70, 140):
        counts = Counter(c.category for c in picked[:stop]).values()
        assert max(counts) - min(counts) <= 1, stop


def test_selection_is_deterministic_and_seed_dependent():
    a = [c.case_id for c in select_cases(CASES, 20, 7)]
    assert a == [c.case_id for c in select_cases(CASES, 20, 7)]
    assert a != [c.case_id for c in select_cases(CASES, 20, 8)]


def test_none_means_all_cases():
    assert len(select_cases(CASES, None, 7)) == len(CASES)


def test_prefer_reuses_done_cases_and_keeps_selection_stable_on_resume():
    fresh = select_cases(CASES, 20, 7)
    done = {c.case_id for c in fresh[:28]}  # one day of work
    resumed = select_cases(CASES, 20, 7, prefer=done)
    assert {c.case_id for c in resumed} == {c.case_id for c in fresh}
    assert done <= {c.case_id for c in resumed[:28]}


def test_prefer_adopts_cases_outside_the_fresh_selection():
    compliant = [c.case_id for c in CASES if c.category.value == "compliant"]
    resumed = select_cases(CASES, 20, 7, prefer=compliant)  # all 25 already measured
    chosen = {c.case_id for c in resumed if c.category.value == "compliant"}
    assert len(chosen) == 20 and chosen <= set(compliant)
