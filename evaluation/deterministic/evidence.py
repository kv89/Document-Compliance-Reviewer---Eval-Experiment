"""Evidence evaluation, Layer 2 (spec section 14).

Computed on true positives only: evidence quality is meaningless for a finding that should not
have been reported, or for one that was missed. Every rate therefore carries the true-positive
count as its denominator.

There are no page checks. Documents are plain text, and evidence is a section identifier plus a
verbatim quote plus character offsets (spec sections 3.2, 11.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.schemas.models import GroundTruthCase
from evaluation.deterministic.matching import MatchedPair, MatchResult


@dataclass(frozen=True)
class EvidenceScore:
    checked: int           # denominator: matched pairs whose expected finding cites evidence
    present: int           # agent supplied evidence where it was required
    quote_verbatim: int    # S2: the quote really occurs in the document
    offsets_consistent: int  # S3: document[start:end] equals the quote
    section_correct: int   # cited section is the expected one, or an accepted alternative
    span_overlap: float    # mean character-level intersection over union
    fully_correct: int     # all of the above for one finding

    def rate(self, numerator: int) -> float | None:
        return None if self.checked == 0 else numerator / self.checked

    @property
    def accuracy(self) -> float | None:
        return self.rate(self.fully_correct)


def _iou(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
    overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
    union = max(a_end, b_end) - min(a_start, b_start)
    return 0.0 if union <= 0 else overlap / union


def score_pair(pair: MatchedPair, case: GroundTruthCase, document: str) -> dict[str, float]:
    """Score one matched pair. Returns zeros rather than raising on malformed evidence."""
    expected, actual = pair.expected, pair.actual
    if expected.evidence is None:
        return {}

    if actual.evidence is None:
        return {
            "present": 0.0,
            "quote_verbatim": 0.0,
            "offsets_consistent": 0.0,
            "section_correct": 0.0,
            "span_overlap": 0.0,
            "fully_correct": 0.0,
        }

    ev, exp_ev = actual.evidence, expected.evidence
    verbatim = ev.quote in document
    consistent = ev.char_end > ev.char_start and document[ev.char_start : ev.char_end] == ev.quote

    acceptable = {exp_ev.section_id, *case.evidence_section_alternatives.get(pair.rule_id, [])}
    section_ok = ev.section_id in acceptable

    overlap = _iou(ev.char_start, ev.char_end, exp_ev.char_start, exp_ev.char_end)

    return {
        "present": 1.0,
        "quote_verbatim": float(verbatim),
        "offsets_consistent": float(consistent),
        "section_correct": float(section_ok),
        "span_overlap": overlap,
        "fully_correct": float(verbatim and consistent and section_ok),
    }


def score(result: MatchResult, case: GroundTruthCase, document: str) -> EvidenceScore:
    rows = [
        scored
        for pair in result.matched
        if (scored := score_pair(pair, case, document))
    ]
    if not rows:
        return EvidenceScore(0, 0, 0, 0, 0, 0.0, 0)
    total = lambda key: int(sum(r[key] for r in rows))  # noqa: E731 - local shorthand
    return EvidenceScore(
        checked=len(rows),
        present=total("present"),
        quote_verbatim=total("quote_verbatim"),
        offsets_consistent=total("offsets_consistent"),
        section_correct=total("section_correct"),
        span_overlap=sum(r["span_overlap"] for r in rows) / len(rows),
        fully_correct=total("fully_correct"),
    )
