"""Case selection and ordering for a sweep that may be cut short by a daily quota.

The dataset on disk is ordered by category, so running it front to back and stopping at the quota
yields only the first categories (the 2026-10-02 run reached 25 compliant and 4 missing_clause).
This module fixes the order, not the data: it picks a seeded, equal-sized sample per category and
interleaves the categories, so every stopping point is a balanced partial sample.

Pure functions of (cases, per_category, seed, prefer). Nothing here reads results or the model.
"""

from __future__ import annotations

import random
from typing import Collection, Sequence

from agent.schemas.models import GroundTruthCase


def select_cases(
    cases: Sequence[GroundTruthCase],
    per_category: int | None,
    seed: int,
    prefer: Collection[str] = (),
) -> list[GroundTruthCase]:
    """Return up to `per_category` cases from each category, interleaved by category.

    Within a category the order is a seeded shuffle of the whole category, so the choice does not
    depend on how many cases happen to have run. `prefer` moves already-measured case ids to the
    front of their category, keeping their shuffled order, so a resumed sweep reuses them instead
    of paying for them again. Because `prefer` only reorders a prefix that the same shuffle
    produced, the selection is the same on every resume.
    """
    by_category: dict[str, list[GroundTruthCase]] = {}
    for case in cases:
        by_category.setdefault(case.category.value, []).append(case)

    preferred = set(prefer)
    ordered: list[list[GroundTruthCase]] = []
    for category, members in by_category.items():
        shuffled = list(members)
        random.Random(f"{seed}:{category}").shuffle(shuffled)
        shuffled = [c for c in shuffled if c.case_id in preferred] + [
            c for c in shuffled if c.case_id not in preferred
        ]
        ordered.append(shuffled if per_category is None else shuffled[:per_category])

    interleaved: list[GroundTruthCase] = []
    for rank in range(max((len(group) for group in ordered), default=0)):
        for group in ordered:
            if rank < len(group):
                interleaved.append(group[rank])
    return interleaved
