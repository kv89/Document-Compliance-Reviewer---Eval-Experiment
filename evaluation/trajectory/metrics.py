"""Deterministic tool and trajectory metrics, Layers 3 and 4 (spec section 14).

Everything here is computed from the trace alone, with no model involved. That is deliberate:
DeepEval's task-completion and step-efficiency metrics are LLM judges, and spec section 18 forbids
introducing a judge before deterministic evaluation is established. These metrics are what the
baseline reports instead.

None of them require a particular tool-call order. Spec section 13 is the thesis of the whole
experiment: an alternative sequence that obtains the same information is not an error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from agent.schemas.models import GroundTruthCase
from agent.schemas.trace import EventType, Trace


@dataclass(frozen=True)
class ToolMetrics:
    tool_calls: int
    tool_errors: int
    redundant_calls: int
    unused_results: int
    required_info_required: int
    required_info_satisfied: int

    @property
    def argument_validity(self) -> float | None:
        return None if self.tool_calls == 0 else 1 - (self.tool_errors / self.tool_calls)

    @property
    def required_info_coverage(self) -> float | None:
        if self.required_info_required == 0:
            return None
        return self.required_info_satisfied / self.required_info_required


@dataclass(frozen=True)
class TrajectoryMetrics:
    llm_calls: int
    steps: int
    retries: int
    loop_detected: bool
    recovered_after_error: bool
    terminated_reason: str


def _arg_key(event) -> str:
    return json.dumps({"tool": event.tool, "arguments": event.arguments or {}}, sort_keys=True)


def tool_metrics(trace: Trace, case: GroundTruthCase) -> ToolMetrics:
    calls = [e for e in trace.events if e.type is EventType.TOOL_CALL]
    errors = [e for e in trace.events if e.type is EventType.TOOL_ERROR]

    # A redundant call repeats an identical (tool, arguments) pair that already succeeded. The
    # first repeat is the redundancy, so the count is occurrences minus one.
    counts: dict[str, int] = {}
    for e in calls:
        key = _arg_key(e)
        counts[key] = counts.get(key, 0) + 1
    redundant = sum(n - 1 for n in counts.values() if n > 1)

    # A result the agent never used: a section was read but no finding cites it and the run
    # reported findings elsewhere. Reported as a signal, not an error - reading a section and
    # correctly concluding nothing is wrong about it is legitimate.
    cited_sections = {
        f["evidence"]["section_id"]
        for f in (trace.final_decision or {}).get("findings", [])
        if isinstance(f, dict) and isinstance(f.get("evidence"), dict)
    }
    unused = len(trace.sections_seen() - cited_sections) if cited_sections else 0

    sections_seen = trace.sections_seen()
    rules_seen = trace.policy_rules_consulted()
    required = case.required_information
    satisfied = sum(
        1
        for r in required
        if r.rule_id in rules_seen and set(r.must_consult_sections) <= sections_seen
    )

    return ToolMetrics(
        tool_calls=len(calls),
        tool_errors=len(errors),
        redundant_calls=redundant,
        unused_results=unused,
        required_info_required=len(required),
        required_info_satisfied=satisfied,
    )


def trajectory_metrics(trace: Trace, loop_threshold: int = 3) -> TrajectoryMetrics:
    calls = [e for e in trace.events if e.type is EventType.TOOL_CALL]
    counts: dict[str, int] = {}
    for e in calls:
        key = _arg_key(e)
        counts[key] = counts.get(key, 0) + 1

    # Did a tool error get followed by a different, successful call? That is recovery, and it is
    # worth distinguishing from an agent that errors and gives up.
    recovered = False
    error_seqs = [e.seq for e in trace.events if e.type is EventType.TOOL_ERROR]
    if error_seqs:
        first_error = min(error_seqs)
        recovered = any(
            e.type is EventType.TOOL_RESULT and e.ok is not False and e.seq > first_error
            for e in trace.events
        )

    return TrajectoryMetrics(
        llm_calls=sum(1 for e in trace.events if e.type is EventType.LLM_CALL),
        steps=len(trace.events),
        retries=trace.retries,
        loop_detected=any(n >= loop_threshold for n in counts.values()),
        recovered_after_error=recovered,
        terminated_reason=trace.terminated_reason.value,
    )
