"""Agent loop tests (spec sections 5, 11, 12).

Every test here drives the loop with `ScriptedClient`. That is deliberate, not a convenience: the
behaviours that matter most — a malformed reply, an unauthorized tool name, a refusal to ever stop,
a quota rejection — are not reproducible on demand against a real model, so testing them against
one would mean not testing them at all.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from agent.agent import Agent, extract_json
from agent.llm.client import HarnessError, LLMResponse, QuotaPolicy, ScriptedClient
from agent.prompts import p1, p2
from agent.prompts.p1 import SYSTEM_PROMPT
from agent.schemas.models import ComplianceStatus, FindingType, Severity
from agent.schemas.trace import (
    EventType,
    OutputValidation,
    RunConfig,
    TerminatedReason,
)
from evaluation.deterministic.evaluate import NO_ANSWER_STATUS, no_answer_row


def _config(**over) -> RunConfig:
    base = dict(
        provider="scripted",
        model_name="scripted",
        temperature=0.0,
        seed=7,
        max_steps=6,
        prompt_version="p1",
        tool_set_version="t1",
        agent_version="v1",
        dataset_version="test",
        policy_version="v1",
    )
    base.update(over)
    return RunConfig(**base)


def _run(responses: list[str], document: str, policy, **over):
    client = ScriptedClient(responses=list(responses))
    agent = Agent(client, max_steps=over.pop("max_steps", 6))
    result = agent.run(
        document,
        policy,
        config=_config(**over),
        experiment_id="test",
        case_id="DOC-TEST-1",
    )
    return result, client


def _final(status: str, findings: list[dict] | None = None) -> str:
    return json.dumps(
        {"final_answer": {"status": status, "findings": findings or [], "summary": "s"}}
    )


# ---------------------------------------------------------------- output extraction
@pytest.mark.parametrize(
    "text",
    [
        '{"tool": "list_document_sections"}',
        '```json\n{"tool": "list_document_sections"}\n```',
        '```\n{"tool": "list_document_sections"}\n```',
        'Here is my call: {"tool": "list_document_sections"} — let me know.',
    ],
)
def test_json_is_extracted_through_common_wrappers(text):
    assert extract_json(text) == {"tool": "list_document_sections"}


def test_braces_inside_strings_do_not_confuse_extraction():
    assert extract_json('{"summary": "nested } brace", "n": 1}') == {
        "summary": "nested } brace",
        "n": 1,
    }


@pytest.mark.parametrize("text", ["", "no json at all", "[1, 2, 3]", '{"unbalanced": '])
def test_non_objects_are_not_extracted(text):
    assert extract_json(text) is None


# ---------------------------------------------------------------- happy path
def test_a_tool_call_then_a_final_answer_produces_a_valid_output(document, policy):
    result, client = _run(
        ['{"tool": "list_document_sections"}', _final("COMPLIANT")], document, policy
    )

    assert result.output is not None
    assert result.output.status is ComplianceStatus.COMPLIANT
    assert result.trace.output_validation is OutputValidation.VALID
    assert result.trace.terminated_reason is TerminatedReason.FINAL_ANSWER
    assert result.trace.totals.num_llm_calls == 2
    assert result.trace.totals.num_tool_calls == 1
    assert result.trace.totals.num_tool_errors == 0
    assert result.harness_error == ""
    # The tool result must have been fed back, or the second call saw nothing new.
    assert "list_document_sections" in client.calls[1][1]


def test_tool_results_attribute_sections_and_rules_separately(document, policy):
    result, _ = _run(
        [
            '{"tool": "get_document_section", "arguments": {"section_id": "4.1"}}',
            '{"tool": "lookup_policy", "arguments": {"rule_id": "VALUE-PAY-001"}}',
            _final("COMPLIANT"),
        ],
        document,
        policy,
    )

    assert result.trace.sections_seen() == {"4.1"}
    assert result.trace.policy_rules_consulted() == {"VALUE-PAY-001"}


def test_the_system_prompt_is_sent_unmodified(document, policy):
    _, client = _run([_final("COMPLIANT")], document, policy)
    assert client.calls[0][0] == SYSTEM_PROMPT


def test_p1_text_is_frozen():
    """p1 is the measured baseline. Adding p2 must not change a character of it."""
    text = p1.SYSTEM_PROMPT + p1.USER_PROMPT + p1.TOOL_RESULT_PROMPT
    assert hashlib.sha256(text.encode()).hexdigest() == (
        "82abe6e458e45639b146255790112dc327189b5bee2774105b4d85ece99425ff"
    )


def test_p2_sends_its_own_prompt_and_lists_rule_ids(document, policy):
    result, client = _run(
        ['{"tool": "list_document_sections", "arguments": {}}', _final("COMPLIANT")],
        document,
        policy,
        prompt_version="p2",
    )
    system, first = client.calls[0]
    assert system == p2.SYSTEM_PROMPT
    for rule in policy.rules:
        assert f"{rule.rule_id} ({rule.clause})" in first
    assert "The policy id is not a rule id." in first
    # Only ids are given: rule statements still have to be looked up (safety checks S1, S8).
    assert not any(rule.statement in first for rule in policy.rules)
    assert "Result of list_document_sections" in client.calls[1][1]
    assert result.trace.config.prompt_version == "p2"


def test_unknown_prompt_version_is_refused(document, policy):
    with pytest.raises(ValueError, match="Unknown prompt_version"):
        _run([_final("COMPLIANT")], document, policy, prompt_version="p9")


# ---------------------------------------------------------------- repair budget
def test_one_malformed_reply_is_repaired_and_counted(document, policy):
    result, _ = _run(["I think the document is fine, honestly.", _final("COMPLIANT")], document, policy)

    assert result.output is not None
    assert result.trace.output_validation is OutputValidation.REPAIRED
    assert result.trace.retries == 1


def test_two_malformed_replies_end_the_trial_as_unparseable(document, policy):
    result, client = _run(["not json", "still not json", _final("COMPLIANT")], document, policy)

    assert result.output is None
    assert result.trace.output_validation is OutputValidation.UNPARSEABLE
    assert result.trace.terminated_reason is TerminatedReason.ERROR
    # The repair budget is one. A third response must never have been requested, or the rate at
    # which the model fails the output contract would be unmeasurable.
    assert len(client.responses) == 1
    assert result.trace.retries == 1


def test_a_final_answer_with_the_wrong_shape_is_repaired_once(document, policy):
    bad = json.dumps({"final_answer": {"status": "MAYBE"}})
    result, _ = _run([bad, _final("NEEDS_REVIEW")], document, policy)

    assert result.output is not None
    assert result.output.status is ComplianceStatus.NEEDS_REVIEW
    assert result.trace.output_validation is OutputValidation.REPAIRED
    assert any("required shape" in e for e in result.trace.errors)


def test_an_object_with_neither_key_is_treated_as_malformed(document, policy):
    result, _ = _run([json.dumps({"thinking": "hmm"}), _final("COMPLIANT")], document, policy)

    assert result.output is not None
    assert result.trace.retries == 1


# ---------------------------------------------------------------- tool discipline
def test_an_unauthorized_tool_is_returned_as_data_so_s6_can_count_it(document, policy):
    result, _ = _run(
        ['{"tool": "read_file", "arguments": {"path": "/etc/passwd"}}', _final("COMPLIANT")],
        document,
        policy,
    )

    errors = [e for e in result.trace.events if e.type is EventType.TOOL_ERROR]
    assert len(errors) == 1
    assert errors[0].tool == "read_file"
    assert "UNAUTHORIZED_TOOL" in (errors[0].error or "") or "UNAUTHORIZED_TOOL" in (
        errors[0].result_summary or ""
    )
    # The trial continued. Recovery after a tool error is itself a trajectory metric, so the loop
    # must not abort here.
    assert result.output is not None
    assert result.trace.totals.num_tool_errors == 1


def test_malformed_tool_arguments_do_not_crash_the_loop(document, policy):
    result, _ = _run(
        [
            '{"tool": "lookup_policy", "arguments": {"nonsense": true}}',
            '{"tool": "lookup_policy", "arguments": "not-an-object"}',
            _final("COMPLIANT"),
        ],
        document,
        policy,
    )

    assert result.output is not None
    assert result.trace.totals.num_tool_errors == 2


def test_repeated_identical_calls_are_counted_as_redundant(document, policy):
    call = '{"tool": "get_document_section", "arguments": {"section_id": "4.1"}}'
    result, _ = _run([call, call, _final("COMPLIANT")], document, policy)

    assert result.trace.totals.num_tool_calls == 2
    assert result.trace.totals.num_redundant_calls == 1


# ---------------------------------------------------------------- termination
def test_an_agent_that_never_answers_hits_max_steps(document, policy):
    result, _ = _run(['{"tool": "list_document_sections"}'] * 12, document, policy, max_steps=4)

    assert result.output is None
    assert result.trace.terminated_reason is TerminatedReason.MAX_STEPS
    # Its messages parsed fine; it simply never finished. Recording that as `unparseable` would
    # blame the output format for a failure to terminate.
    assert result.trace.output_validation is OutputValidation.NOT_PRODUCED
    assert result.trace.totals.num_llm_calls == 4


def test_a_quota_failure_is_recorded_as_a_harness_error_not_an_agent_error(document, policy):
    class Exhausted:
        model_name = model_version = runtime_version = "scripted"

        def generate(self, system, prompt):
            raise HarnessError("QUOTA_EXHAUSTED", "429 RESOURCE_EXHAUSTED")

    agent = Agent(Exhausted(), max_steps=4)
    result = agent.run(
        document, policy, config=_config(), experiment_id="test", case_id="DOC-TEST-1"
    )

    assert result.output is None
    assert "QUOTA_EXHAUSTED" in result.harness_error
    assert result.trace.terminated_reason is TerminatedReason.ERROR
    # Never `valid`. The first live run recorded a quota-killed trial as valid output.
    assert result.trace.output_validation is OutputValidation.NOT_PRODUCED


# ---------------------------------------------------------------- the scoring guard
def test_no_answer_never_scores_as_correct_on_a_compliant_case(document, policy, compliant_case):
    """The specific bug this guards against.

    A compliant case expects COMPLIANT with no findings. If an unparseable response were defaulted
    to "COMPLIANT, no findings", a total agent failure would be recorded as a correct answer, and
    the reported accuracy on the compliant category would be meaningless.
    """
    result, _ = _run(["not json", "still not json"], document, policy)
    row = no_answer_row(
        compliant_case,
        result.trace,
        experiment_id="test",
        run_id="r",
        agent_version="v1",
    )

    assert row.actual_status == NO_ANSWER_STATUS
    assert row.status_correct is False
    assert row.deterministic_result == "fail"
    assert row.findings_exact is False
    # Not measured, as distinct from measured as zero.
    assert row.finding_precision is None
    assert row.evidence_checked == 0
    assert row.evidence_accuracy is None
    # Producing nothing must not be rewarded with passing safety checks.
    assert row.safety_violations == 0
    assert set(row.safety_checks_skipped) >= {"S1", "S2", "S4", "S6", "S7", "S8"}
    assert row.harness_error == ""


def test_a_voided_trial_is_marked_so_analysis_can_exclude_it(document, policy, strict_case):
    result, _ = _run(["not json", "nope"], document, policy)
    row = no_answer_row(
        strict_case,
        result.trace,
        experiment_id="test",
        run_id="r",
        agent_version="v1",
        harness_error="QUOTA_EXHAUSTED: 429",
    )

    assert row.harness_error.startswith("QUOTA_EXHAUSTED")
    assert row.deterministic_result == "fail"


def test_rows_round_trip_through_jsonl(tmp_path, document, policy, compliant_case):
    from agent.schemas.loaders import read_jsonl, write_jsonl
    from agent.schemas.results import TrialRow

    result, _ = _run(["not json", "nope"], document, policy)
    row = no_answer_row(
        compliant_case, result.trace, experiment_id="test", run_id="r", agent_version="v1"
    )
    path = tmp_path / "trials.jsonl"
    assert write_jsonl(path, [row]) == 1
    assert read_jsonl(path, TrialRow)[0].actual_status == NO_ANSWER_STATUS


def test_traces_serialise_and_reload(document, policy, tmp_path):
    from agent.schemas.trace import Trace

    result, _ = _run(['{"tool": "list_document_sections"}', _final("COMPLIANT")], document, policy)
    path = tmp_path / "trace.json"
    path.write_text(result.trace.model_dump_json(indent=2), encoding="utf-8")
    reloaded = Trace.model_validate_json(path.read_text())

    assert reloaded.totals.num_tool_calls == 1
    assert reloaded.config.seed == 7


# ---------------------------------------------------------------- contract documentation
@pytest.mark.parametrize("prompt", [p1, p2], ids=["p1", "p2"])
def test_the_prompt_documents_every_enum_value_the_schema_accepts(prompt):
    """A value the schema accepts but the prompt never mentions is unreachable by construction.

    If the prompt and the schema drift apart, the agent is scored against a contract it was never
    given, which measures our documentation rather than its judgement.
    """
    for enum in (ComplianceStatus, FindingType, Severity):
        for member in enum:
            assert member.value in prompt.SYSTEM_PROMPT, f"{enum.__name__}.{member.value} not in prompt"


@pytest.mark.parametrize("prompt", [p1, p2], ids=["p1", "p2"])
def test_the_prompt_lists_exactly_the_authorized_tools(prompt, document, policy):
    from agent.tools.toolset import ToolSet

    for tool in ToolSet(document, policy).authorized_tools:
        assert tool in prompt.SYSTEM_PROMPT


# ---------------------------------------------------------------- client retry policy
def test_backoff_grows_and_is_capped():
    policy = QuotaPolicy(initial_backoff_seconds=2, backoff_multiplier=2, max_backoff_seconds=30)
    assert [policy.delay_for(i) for i in range(6)] == [2, 4, 8, 16, 30, 30]


def test_scripted_client_exhaustion_is_a_harness_error():
    client = ScriptedClient(responses=[])
    with pytest.raises(HarnessError):
        client.generate("s", "p")


def test_llm_response_defaults_do_not_invent_a_model_version():
    assert LLMResponse(text="x").model_version == ""


# ---------------------------------------------------------------- real client retry loop
class _FakeResponse:
    """Minimal stand-in for a `GenerateContentResponse`."""

    def __init__(self, text: str | None, version: str = "gemini-2.5-flash-002") -> None:
        self.text = text
        self.model_version = version
        self.usage_metadata = type(
            "U",
            (),
            {"prompt_token_count": 11, "candidates_token_count": 7, "thoughts_token_count": 0},
        )()
        self.candidates = [type("C", (), {"finish_reason": "STOP"})()]


def _gemini_with(monkeypatch, outcomes):
    """A `GeminiClient` whose transport yields `outcomes` in order. No key, no network."""
    from agent.llm import client as client_module

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    slept: list[float] = []
    gemini = client_module.GeminiClient(
        "gemini-2.5-flash",
        quota=QuotaPolicy(max_retries=3, initial_backoff_seconds=0.01),
        sleep=slept.append,
    )

    remaining = list(outcomes)

    def transport(**_kwargs):
        outcome = remaining.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gemini._client.models, "generate_content", transport)
    return gemini, slept


def test_a_rate_limit_is_retried_with_backoff_then_succeeds(monkeypatch):
    gemini, slept = _gemini_with(
        monkeypatch,
        [
            RuntimeError("ClientError: 429 RESOURCE_EXHAUSTED quota exceeded"),
            RuntimeError("ServerError: 503 UNAVAILABLE"),
            _FakeResponse('{"tool": "list_document_sections"}'),
        ],
    )
    response = gemini.generate("system", "prompt")

    assert response.text == '{"tool": "list_document_sections"}'
    assert len(slept) == 2, "both retryable failures should have waited"
    assert slept[1] > slept[0], "backoff should grow"
    # The provider-reported version is captured, since a hosted alias can move underneath us.
    assert response.model_version == "gemini-2.5-flash-002"
    assert gemini.model_version == "gemini-2.5-flash-002"


def test_a_bad_request_is_not_retried(monkeypatch):
    gemini, slept = _gemini_with(
        monkeypatch, [RuntimeError("ClientError: 400 INVALID_ARGUMENT bad field")]
    )
    with pytest.raises(HarnessError) as caught:
        gemini.generate("system", "prompt")

    assert caught.value.code == "PROVIDER_ERROR"
    assert slept == [], "a malformed request will fail identically on retry"


def test_exhausted_retries_raise_a_harness_error(monkeypatch):
    gemini, slept = _gemini_with(
        monkeypatch, [RuntimeError("429 RESOURCE_EXHAUSTED")] * 4
    )
    with pytest.raises(HarnessError) as caught:
        gemini.generate("system", "prompt")

    assert caught.value.code == "PROVIDER_ERROR"
    assert len(slept) == 3, "max_retries=3 allows three waits, then gives up"


def test_an_empty_response_is_retried_then_raised_as_empty_not_provider_error(monkeypatch):
    """A safety block, a truncation, or MALFORMED_FUNCTION_CALL all return no text.

    Observed live: Gemini 3 returned empty text with finish_reason MALFORMED_FUNCTION_CALL on
    three of eight requests in the first run, because it tried to call a function although none
    were declared. That is a provider outcome, not a reply, so it must not be parsed as one or
    charged to the agent as malformed output. It is retried once, not on the quota schedule: in
    run expA_p2-20261017T200247Z it recurred on every attempt at temperature 0.
    """
    gemini, slept = _gemini_with(
        monkeypatch,
        [_FakeResponse(None, version="gemini-3.5-flash-lite")] * 4,
    )
    with pytest.raises(HarnessError) as caught:
        gemini.generate("system", "prompt")

    assert caught.value.code == "EMPTY_RESPONSE"
    assert len(slept) == 1, "one retry, whatever max_retries allows"


def test_an_empty_response_that_recovers_is_not_an_error(monkeypatch):
    gemini, slept = _gemini_with(
        monkeypatch, [_FakeResponse(None), _FakeResponse('{"tool": "x"}')]
    )
    response = gemini.generate("system", "prompt")

    assert response.text == '{"tool": "x"}'
    assert len(slept) == 1


def test_the_runner_refuses_moving_aliases_and_previews(tmp_path):
    import yaml as _yaml

    from experiments.run_baseline import load_config

    base = _yaml.safe_load(
        (
            __import__("pathlib").Path("experiments/configs/baseline_v1.yaml")
        ).read_text(encoding="utf-8")
    )
    for bad in ("gemini-flash-latest", "gemini-3-flash-preview"):
        base["model"]["name"] = bad
        path = tmp_path / "bad.yaml"
        path.write_text(_yaml.safe_dump(base), encoding="utf-8")
        with pytest.raises(SystemExit, match="6.4"):
            load_config(path)


# ---------------------------------------------------------------- quota classification
_DAILY_429 = (
    "ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota', 'details': [{'@type': 'type.googleapis.com/google.rpc.QuotaFailure', "
    "'violations': [{'quotaId': 'GenerateRequestsPerDayPerProjectPerModel-FreeTier', "
    "'quotaValue': '20'}]}, {'@type': 'type.googleapis.com/google.rpc.RetryInfo', "
    "'retryDelay': '47s'}]}}"
)
_MINUTE_429 = (
    "ClientError: 429 RESOURCE_EXHAUSTED {'quotaId': "
    "'GenerateRequestsPerMinutePerProjectPerModel-FreeTier'} 'retryDelay': '12s'"
)


def test_a_daily_quota_is_not_retried(monkeypatch):
    """Observed in the first live run: 20 requests per day, retried for a minute, for nothing.

    A per-day budget cannot be waited out inside a run. Backing off against one spends real time
    to collect an identical rejection, and across a sweep it multiplies by the number of remaining
    trials.
    """
    gemini, slept = _gemini_with(monkeypatch, [RuntimeError(_DAILY_429)])
    with pytest.raises(HarnessError) as caught:
        gemini.generate("system", "prompt")

    assert caught.value.code == "DAILY_QUOTA_EXHAUSTED"
    assert slept == []


def test_a_per_minute_quota_is_retried_and_honours_the_advised_delay(monkeypatch):
    gemini, slept = _gemini_with(
        monkeypatch, [RuntimeError(_MINUTE_429), _FakeResponse('{"tool": "x"}')]
    )
    gemini.generate("system", "prompt")

    # The configured backoff was 0.01s. Guessing shorter than the provider's own hint would just
    # waste an attempt, so the hint wins.
    assert slept and slept[0] >= 12.0


def test_the_advised_delay_never_exceeds_the_configured_cap(monkeypatch):
    from agent.llm.client import GeminiClient

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    slept: list[float] = []
    gemini = GeminiClient(
        "gemini-2.5-flash",
        quota=QuotaPolicy(max_retries=2, initial_backoff_seconds=1, max_backoff_seconds=5),
        sleep=slept.append,
    )
    remaining = [RuntimeError(_MINUTE_429), _FakeResponse('{"tool": "x"}')]
    monkeypatch.setattr(
        gemini._client.models,
        "generate_content",
        lambda **_kw: (_ for _ in ()).throw(remaining.pop(0))
        if isinstance(remaining[0], Exception)
        else remaining.pop(0),
    )
    gemini.generate("system", "prompt")

    assert slept[0] <= 5 * 1.1, "a 47s hint must not override an operator-set 5s cap"


_WITHDRAWN_404 = (
    "ClientError: 404 NOT_FOUND. {'error': {'code': 404, 'message': 'This model "
    "models/gemini-2.5-flash-lite is no longer available to new users.', 'status': 'NOT_FOUND'}}"
)


def test_a_withdrawn_model_is_its_own_failure_class_and_is_not_retried(monkeypatch):
    """Observed live: a model listed by `models.list` returned 404 for a new key.

    This is the hosted-provider risk spec 6.3 records, arriving as a 404 rather than as silently
    different weights. It is not retryable and it voids the whole run, not one trial.
    """
    gemini, slept = _gemini_with(monkeypatch, [RuntimeError(_WITHDRAWN_404)])
    with pytest.raises(HarnessError) as caught:
        gemini.generate("system", "prompt")

    assert caught.value.code == "MODEL_UNAVAILABLE"
    assert slept == []


def test_quota_and_availability_failures_are_not_confused(monkeypatch):
    from agent.llm.client import _is_daily_quota, _is_unavailable

    assert _is_unavailable(_WITHDRAWN_404) and not _is_daily_quota(_WITHDRAWN_404)
    assert _is_daily_quota(_DAILY_429) and not _is_unavailable(_DAILY_429)


#: Live REF-2 stop, 2026-10-17: a per-minute 429 whose retry hint "26.964036119s" contains "403".
_PER_MINUTE_429 = (
    "ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your "
    "current quota. Please retry in 26.964036119s.', 'status': 'RESOURCE_EXHAUSTED', 'details': "
    "[{'quotaId': 'GenerateRequestsPerMinutePerProjectPerModel-FreeTier', 'quotaValue': '15'}, "
    "{'retryDelay': '26s'}]}}"
)


def test_status_codes_match_only_as_whole_numbers():
    from agent.llm.client import _is_daily_quota, _is_retryable, _is_unavailable

    assert not _is_unavailable(_PER_MINUTE_429)  # the "403" inside 26.964036119 is not a 403
    assert _is_retryable(_PER_MINUTE_429) and not _is_daily_quota(_PER_MINUTE_429)
    assert _is_unavailable("ClientError: 403 PERMISSION_DENIED")
    assert _is_unavailable("got HTTP 404.")
    assert not _is_retryable("bad request: field 1500 too long")


# ---------------------------------------------------------------- hidden reasoning cost
def test_thinking_tokens_are_recorded_and_counted_in_the_total(monkeypatch, document, policy):
    """Internal reasoning is charged, never returned, and cannot be switched off on Gemini 3.x.

    Leaving it out of `total_tokens` would understate the real cost of every trial, and leaving it
    out of the trace would make the hidden work unmeasurable. It cannot be made visible, so it is
    at least counted.
    """

    class Thinker:
        model_name = model_version = runtime_version = "scripted"

        def __init__(self) -> None:
            self.replies = ['{"tool": "list_document_sections"}', _final("COMPLIANT")]

        def generate(self, system, prompt):
            return LLMResponse(
                text=self.replies.pop(0),
                input_tokens=100,
                output_tokens=20,
                thinking_tokens=73,
                model_version="scripted",
            )

    agent = Agent(Thinker(), max_steps=4)
    result = agent.run(
        document, policy, config=_config(), experiment_id="test", case_id="DOC-TEST-1"
    )
    totals = result.trace.totals

    assert totals.thinking_tokens == 146
    assert totals.total_tokens == totals.input_tokens + totals.output_tokens + 146


def test_the_client_sends_a_thinking_level_not_a_budget(monkeypatch):
    """`thinking_budget = 0` worked on Gemini 2.5 and returns a 400 on Gemini 3.x."""
    from agent.llm import client as client_module

    monkeypatch.setenv("GOOGLE_API_KEY", "test-key-not-real")
    gemini = client_module.GeminiClient("gemini-3.5-flash-lite", thinking_level="MINIMAL")
    config = gemini._config("system")

    assert config.thinking_config.thinking_level == "MINIMAL"
    assert config.thinking_config.thinking_budget is None
