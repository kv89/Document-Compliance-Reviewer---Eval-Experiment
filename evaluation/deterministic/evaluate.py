"""Case evaluation: assemble the six layers into one trial row.

Strict cases are scored against a single correct answer. Accept-set cases are scored against the
most favourable defensible answer, and are reported as their own stratum rather than pooled into
the primary aggregates (spec section 8.3).

`deterministic_result` is the single pass/fail verdict: the status must be acceptable, the findings
must match exactly, the evidence must be fully correct where evidence is expected, and no safety
check may have failed. It is deliberately strict, because a looser definition would let a partially
right answer be reported as a success.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from agent.schemas.models import (
    AgentOutput,
    GroundTruthCase,
    Policy,
    ScoringMode,
)
from agent.schemas.results import TrialRow
from agent.schemas.trace import OutputValidation, Trace
from evaluation.deterministic import evidence as ev
from evaluation.deterministic import matching
from evaluation.safety.checks import CHECK_IDS, SafetyReport, evaluate as evaluate_safety
from evaluation.trajectory.metrics import tool_metrics, trajectory_metrics


@dataclass
class CaseEvaluation:
    """The full evaluation of one execution, before flattening to a row."""

    case: GroundTruthCase
    output: AgentOutput
    match: matching.MatchResult
    evidence: ev.EvidenceScore
    safety: SafetyReport
    status_correct: bool

    @property
    def passed(self) -> bool:
        evidence_ok = self.evidence.checked == 0 or self.evidence.accuracy == 1.0
        return (
            self.status_correct
            and self.match.exact
            and evidence_ok
            and self.safety.passed
        )


def evaluate_case(
    output: AgentOutput,
    case: GroundTruthCase,
    policy: Policy,
    document: str,
    trace: Trace | None = None,
) -> CaseEvaluation:
    if case.scoring_mode is ScoringMode.ACCEPT_SET:
        result = matching.best_match(case.accepted_finding_sets or [], output.findings)
    else:
        result = matching.match(case.expected_findings, output.findings)

    return CaseEvaluation(
        case=case,
        output=output,
        match=result,
        evidence=ev.score(result, case, document),
        safety=evaluate_safety(output, case, policy, document, trace),
        status_correct=output.status in case.accepted_statuses,
    )


def to_row(
    evaluation: CaseEvaluation,
    *,
    experiment_id: str,
    run_id: str,
    agent_version: str,
    trial_id: int = 1,
    trace: Trace | None = None,
    trace_path: str | None = None,
) -> TrialRow:
    case, result, evidence, safety = (
        evaluation.case,
        evaluation.match,
        evaluation.evidence,
        evaluation.safety,
    )

    tools = tool_metrics(trace, case) if trace else None
    trajectory = trajectory_metrics(trace) if trace else None
    config = trace.config if trace else None

    return TrialRow(
        experiment_id=experiment_id,
        run_id=run_id,
        agent_version=agent_version,
        prompt_version=config.prompt_version if config else "",
        tool_set_version=config.tool_set_version if config else "",
        model_name=config.model_name if config else "",
        model_tag=config.model_tag if config else "",
        temperature=config.temperature if config else None,
        seed=config.seed if config else None,
        provider=config.provider if config else "",
        model_version=config.model_version if config else "",
        runtime_version=config.runtime_version if config else "",
        hardware_id=config.hardware_id if config else "",
        dataset_version=case.dataset_version,
        policy_id=case.policy_id,
        policy_version=case.policy_version,
        case_id=case.case_id,
        case_category=case.category.value,
        scoring_mode=case.scoring_mode.value,
        trial_id=trial_id,
        expected_status=case.expected_status.value if case.expected_status else None,
        accepted_statuses=[s.value for s in case.accepted_statuses],
        actual_status=evaluation.output.status.value,
        status_correct=evaluation.status_correct,
        tp=result.tp,
        fp=result.fp,
        fn=result.fn,
        tp_strict=result.tp_strict,
        duplicate_findings=len(result.duplicates),
        finding_precision=result.precision,
        finding_recall=result.recall,
        finding_f1=result.f1,
        findings_exact=result.exact,
        findings_exact_lenient=result.exact_lenient,
        evidence_checked=evidence.checked,
        evidence_accuracy=evidence.accuracy,
        evidence_quote_verbatim=evidence.quote_verbatim,
        evidence_offsets_consistent=evidence.offsets_consistent,
        evidence_section_correct=evidence.section_correct,
        evidence_span_overlap=evidence.span_overlap if evidence.checked else None,
        fabricated_evidence_count=len(safety.violations.get("S2", [])),
        num_tool_calls=tools.tool_calls if tools else 0,
        num_tool_errors=tools.tool_errors if tools else 0,
        num_redundant_calls=tools.redundant_calls if tools else 0,
        argument_validity=tools.argument_validity if tools else None,
        required_info_coverage=tools.required_info_coverage if tools else None,
        num_llm_calls=trajectory.llm_calls if trajectory else 0,
        steps=trajectory.steps if trajectory else 0,
        retries=trajectory.retries if trajectory else 0,
        loop_detected=trajectory.loop_detected if trajectory else None,
        recovered_after_error=trajectory.recovered_after_error if trajectory else None,
        terminated_reason=trajectory.terminated_reason if trajectory else "not_applicable",
        safety_violations=safety.count,
        safety_violation_ids=safety.violated_ids,
        safety_checks_skipped=list(safety.skipped),
        latency_ms=trace.totals.latency_ms if trace else 0,
        input_tokens=trace.totals.input_tokens if trace else 0,
        output_tokens=trace.totals.output_tokens if trace else 0,
        thinking_tokens=trace.totals.thinking_tokens if trace else 0,
        total_tokens=trace.totals.total_tokens if trace else 0,
        output_validation=(
            trace.output_validation.value if trace else OutputValidation.VALID.value
        ),
        deterministic_result="pass" if evaluation.passed else "fail",
        trace_path=trace_path,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


#: `actual_status` for a trial in which the agent never produced a usable answer. Deliberately not
#: one of the three `ComplianceStatus` values, so that a non-answer can never be confused with an
#: answer during analysis.
NO_ANSWER_STATUS = "NO_ANSWER"


def no_answer_row(
    case: GroundTruthCase,
    trace: Trace,
    *,
    experiment_id: str,
    run_id: str,
    agent_version: str,
    trial_id: int = 1,
    trace_path: str | None = None,
    harness_error: str = "",
) -> TrialRow:
    """A row for a trial that produced no parseable answer.

    This exists so that `evaluate_case` is never handed an invented `AgentOutput`. Defaulting an
    unparseable response to, say, COMPLIANT with no findings would make it score as *correct* on
    every compliant case, which would quietly convert a total agent failure into a success. The
    outcome, evidence and safety metrics are therefore `None` or zero with `evidence_checked = 0`,
    which signals "not measured" rather than "measured as zero", and `status_correct` is False.

    `harness_error` separates the two reasons a trial can have no answer. An empty value means the
    agent failed, and the trial counts against it. A non-empty value means the infrastructure
    failed — a free-tier quota rejection, a network error — and analysis must exclude the trial
    rather than score it (spec section 6.3).
    """
    config = trace.config
    trajectory = trajectory_metrics(trace)
    tools = tool_metrics(trace, case)

    return TrialRow(
        experiment_id=experiment_id,
        run_id=run_id,
        agent_version=agent_version,
        prompt_version=config.prompt_version,
        tool_set_version=config.tool_set_version,
        model_name=config.model_name,
        model_tag=config.model_tag,
        temperature=config.temperature,
        seed=config.seed,
        provider=config.provider,
        model_version=config.model_version,
        runtime_version=config.runtime_version,
        hardware_id=config.hardware_id,
        dataset_version=case.dataset_version,
        policy_id=case.policy_id,
        policy_version=case.policy_version,
        case_id=case.case_id,
        case_category=case.category.value,
        scoring_mode=case.scoring_mode.value,
        trial_id=trial_id,
        expected_status=case.expected_status.value if case.expected_status else None,
        accepted_statuses=[s.value for s in case.accepted_statuses],
        actual_status=NO_ANSWER_STATUS,
        status_correct=False,
        tp=0,
        fp=0,
        fn=len(case.expected_findings),
        tp_strict=0,
        duplicate_findings=0,
        finding_precision=None,
        finding_recall=None,
        finding_f1=None,
        findings_exact=False,
        findings_exact_lenient=False,
        evidence_checked=0,
        evidence_accuracy=None,
        evidence_quote_verbatim=0,
        evidence_offsets_consistent=0,
        evidence_section_correct=0,
        evidence_span_overlap=None,
        fabricated_evidence_count=0,
        num_tool_calls=tools.tool_calls,
        num_tool_errors=tools.tool_errors,
        num_redundant_calls=tools.redundant_calls,
        argument_validity=tools.argument_validity,
        required_info_coverage=tools.required_info_coverage,
        num_llm_calls=trajectory.llm_calls,
        steps=trajectory.steps,
        retries=trajectory.retries,
        loop_detected=trajectory.loop_detected,
        recovered_after_error=trajectory.recovered_after_error,
        terminated_reason=trajectory.terminated_reason,
        # No output means no output to check, so the output-dependent safety checks are recorded as
        # skipped rather than passed. Counting them as passes would reward producing nothing.
        safety_violations=0,
        safety_violation_ids=[],
        safety_checks_skipped=list(CHECK_IDS),
        latency_ms=trace.totals.latency_ms,
        input_tokens=trace.totals.input_tokens,
        output_tokens=trace.totals.output_tokens,
        thinking_tokens=trace.totals.thinking_tokens,
        total_tokens=trace.totals.total_tokens,
        output_validation=trace.output_validation.value,
        deterministic_result="fail",
        harness_error=harness_error,
        trace_path=trace_path,
        timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
