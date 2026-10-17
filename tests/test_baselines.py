"""Reference baseline and end-to-end evaluation tests.

These lock in the reference numbers. If a later change makes REF-1 able to solve contradiction
cases, or makes REF-0 score better than the majority-class floor, something has leaked between the
dataset and the evaluator and every downstream number is suspect.
"""

from __future__ import annotations

from collections import Counter

import pytest

from agent.schemas.loaders import load_document, load_ground_truth, load_policy
from agent.schemas.models import CaseCategory, ComplianceStatus
from baselines import ref0_majority, ref1_regex, ref2_single_shot
from evaluation.deterministic.evaluate import evaluate_case
from experiments.run_references import run_deterministic_baseline as run_baseline
from experiments.sampling import select_cases

DATASET = "v1-m1"


@pytest.fixture(scope="module")
def cases():
    return load_ground_truth(DATASET)


@pytest.fixture(scope="module")
def policy():
    return load_policy("POL-001")


def test_ref0_reads_nothing_and_always_says_non_compliant(cases, policy):
    for case in cases:
        output = ref0_majority.run(load_document(case), policy, case)
        assert output.status is ComplianceStatus.NON_COMPLIANT
        assert output.findings == []


def test_ref0_establishes_the_majority_class_floor():
    rows = run_baseline("ref0_majority", DATASET)
    strict = [r for r in rows if r.scoring_mode == "strict"]
    correct = sum(1 for r in strict if r.status_correct)
    # Eight of twelve strict cases are non-compliant. Any agent status-accuracy claim must beat
    # this, and it is reached by a program that never opens the document.
    assert (correct, len(strict)) == (8, 12)
    assert all(r.deterministic_result == "fail" for r in strict)


def test_ref1_solves_the_regex_detectable_categories(cases, policy):
    for case in cases:
        if case.category not in (
            CaseCategory.MISSING_CLAUSE,
            CaseCategory.INCORRECT_VALUE,
            CaseCategory.MULTIPLE_VIOLATIONS,
        ):
            continue
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.passed, f"{case.case_id} should be solvable without a model"


def test_ref1_fails_every_contradiction_case(cases, policy):
    """The documented capability gap. Blog post 1 depends on this being real."""
    contradictions = [c for c in cases if c.category is CaseCategory.CONTRADICTORY]
    assert contradictions
    for case in contradictions:
        document = load_document(case)
        output = ref1_regex.run(document, policy, case)
        assert output.status is ComplianceStatus.COMPLIANT, "the checker sees nothing wrong"
        evaluation = evaluate_case(output, case, policy, document)
        assert not evaluation.passed
        assert evaluation.match.fn == 1, "the contradiction is a missed finding"


def test_ref1_does_not_hallucinate_on_compliant_or_distractor_cases(cases, policy):
    for case in cases:
        if case.category not in (CaseCategory.COMPLIANT, CaseCategory.DISTRACTOR):
            continue
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.match.fp == 0, f"{case.case_id}: false positive on a clean document"
        assert evaluation.passed


def test_ref1_evidence_is_never_fabricated(cases, policy):
    """S2 and S3 over the whole dataset. A deterministic baseline must be perfect here."""
    for case in cases:
        document = load_document(case)
        evaluation = evaluate_case(ref1_regex.run(document, policy, case), case, policy, document)
        assert evaluation.safety.violations.get("S2") == []
        assert evaluation.safety.violations.get("S3") == []


def test_trace_dependent_safety_checks_are_recorded_as_skipped():
    for name in ("ref0_majority", "ref1_regex"):
        rows = run_baseline(name, DATASET)
        assert all(set(r.safety_checks_skipped) == {"S1", "S6", "S8"} for r in rows)


def test_every_row_carries_its_category_and_scoring_mode():
    """Per-category reporting is impossible without these (spec section 23)."""
    rows = run_baseline("ref1_regex", DATASET)
    assert all(r.case_category for r in rows)
    assert {r.scoring_mode for r in rows} == {"strict", "accept_set"}
    assert len({r.case_id for r in rows}) == len(rows)


def test_rows_round_trip_through_jsonl():
    from agent.schemas.results import TrialRow

    rows = run_baseline("ref1_regex", DATASET)
    assert all(TrialRow.model_validate_json(r.model_dump_json()) == r for r in rows)


def test_report_refuses_to_publish_percentages_for_small_categories():
    from analysis.scripts.aggregate import summarize

    text = summarize(run_baseline("ref1_regex", DATASET), "test")
    assert "no, n<20" in text
    assert "below the n=20 reporting floor" in text or "Counts only where" in text


# ---------------------------------------------------------------------------
# Sampling filter tests (docs/decisions.md, 2026-10-12)
# These ensure run_baseline respects the same case-selection logic used by the
# baseline sweep, so the reference results are on an identical 140-case sample.
# ---------------------------------------------------------------------------

_V1_CASES = load_ground_truth("v1")
_BASELINE_SAMPLE = select_cases(_V1_CASES, per_category=20, seed=7)
_BASELINE_IDS = {c.case_id for c in _BASELINE_SAMPLE}


def test_sampled_run_baseline_produces_exactly_cases_per_category_rows():
    """run_baseline with cases_per_category=20, seed=7 yields exactly 140 rows (20 × 7)."""
    rows = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=7)
    assert len(rows) == 140
    category_counts = Counter(r.case_category for r in rows)
    assert set(category_counts.values()) == {20}, (
        f"Expected 20 rows per category, got: {dict(category_counts)}"
    )


def test_sampled_run_baseline_case_ids_match_baseline_sweep_sample():
    """The 140 case IDs selected by run_baseline must equal the baseline sweep's sample."""
    rows = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=7)
    result_ids = {r.case_id for r in rows}
    assert result_ids == _BASELINE_IDS, (
        f"Mismatch: {len(result_ids - _BASELINE_IDS)} extra, "
        f"{len(_BASELINE_IDS - result_ids)} missing"
    )


def test_sampled_run_baseline_is_deterministic():
    """Same args must produce the same set of case IDs on every call."""
    rows_a = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=7)
    rows_b = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=7)
    assert [r.case_id for r in rows_a] == [r.case_id for r in rows_b]


def test_sampled_run_baseline_seed_changes_selection():
    """A different seed must change which cases are selected."""
    rows_7 = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=7)
    rows_8 = run_baseline("ref1_regex", "v1", cases_per_category=20, sample_seed=8)
    ids_7 = {r.case_id for r in rows_7}
    ids_8 = {r.case_id for r in rows_8}
    assert ids_7 != ids_8, "Different seeds must produce different samples"


def test_prefer_moves_measured_ids_into_sampled_selection():
    """When prefer contains IDs from an earlier run, they must appear in the selected sample."""
    # Simulate a 'prefer' set: pick 10 cases not necessarily in the default seed-7 sample.
    all_ids = {c.case_id for c in _V1_CASES}
    prefer_ids = set(list(all_ids)[:10])  # arbitrary 10
    rows = run_baseline(
        "ref1_regex", "v1", cases_per_category=20, sample_seed=7, prefer=prefer_ids
    )
    selected_ids = {r.case_id for r in rows}
    # Every preferred ID that exists in the dataset must be included (up to per_category cap).
    # Because per_category=20 and there are 25 cases per category, all 10 preferred IDs fit.
    assert prefer_ids <= selected_ids, (
        f"Preferred IDs not in selection: {prefer_ids - selected_ids}"
    )


def test_unsampled_run_baseline_runs_all_v1_cases():
    """With no cases_per_category, run_baseline covers all 175 v1 cases."""
    rows = run_baseline("ref1_regex", "v1")
    assert len(rows) == len(_V1_CASES)
    assert {r.case_id for r in rows} == {c.case_id for c in _V1_CASES}


# ---------------------------------------------------------------------------
# REF-2 single-shot LLM baseline tests (spec §15.1, docs/decisions/decisions.md 2026-10-17)
# ---------------------------------------------------------------------------


class _MockLLMResponse:
    def __init__(self, text: str, input_tokens: int = 100, output_tokens: int = 50):
        self.text = text
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.thinking_tokens = 0
        self.model_version = "mock-v1"


class _MockLLMClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.last_system = ""
        self.last_prompt = ""

    def generate(self, system: str, prompt: str):
        self.last_system = system
        self.last_prompt = prompt
        return _MockLLMResponse(self.response_text)


def test_ref2_prompt_construction(cases, policy):
    case = cases[0]
    document = load_document(case)
    prompt = ref2_single_shot.build_prompt(policy, document)
    assert policy.policy_id in prompt
    assert "Rules:" in prompt
    assert document in prompt


def test_ref2_successful_structured_output(cases, policy):
    case = cases[0]
    document = load_document(case)
    mock_json = """{
      "status": "COMPLIANT",
      "findings": [],
      "summary": "Document complies with all rules."
    }"""
    client = _MockLLMClient(mock_json)
    output, meta = ref2_single_shot.run(document, policy, case, client=client)
    assert output is not None
    assert output.status == ComplianceStatus.COMPLIANT
    assert output.findings == []
    assert meta["input_tokens"] == 100


def test_ref2_handles_unparseable_output(cases, policy):
    case = cases[0]
    document = load_document(case)
    client = _MockLLMClient("I am not returning JSON.")
    output, meta = ref2_single_shot.run(document, policy, case, client=client)
    assert output is None
    assert meta["output_tokens"] == 50
