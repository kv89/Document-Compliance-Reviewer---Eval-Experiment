"""The agent loop (spec sections 5, 11, 12).

One execution of this loop is one trial. It is a state machine over model output: the model replies
with JSON, the loop either dispatches a tool or accepts a final answer, and every transition is
appended to a `Trace`.

Design notes that are experimental decisions rather than implementation taste:

- **Malformed output gets exactly one repair attempt**, counted in `Trace.retries` and reflected in
  `output_validation` as `repaired`. Unlimited repair would hide how often the model fails to
  follow the output contract, which is a reportable result (spec section 11). Zero repair would
  conflate a formatting slip with a reasoning failure. One, counted, keeps both visible.
- **Tool errors are returned to the model, not raised.** An unauthorized tool name or a malformed
  argument set comes back as data so the agent has a chance to recover, and so safety check S6 can
  count the attempt. Whether the agent recovers is itself a Layer 4 metric.
- **The loop never corrects the agent's reasoning.** It does not fill in missing evidence offsets,
  normalise a severity or drop a finding for a rule that does not exist. Those are exactly the
  behaviours the safety evaluator exists to detect, so repairing them here would destroy the
  measurement.
- **Hitting `max_steps` is a recorded outcome, not an exception.** The trial ends with
  `terminated_reason = max_steps` and whatever the agent had produced, which is nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from agent.llm.client import HarnessError, LLMClient
from agent.prompts import p1
from agent.schemas.models import AgentOutput, Policy
from agent.schemas.trace import (
    EventType,
    OutputValidation,
    RunConfig,
    Trace,
    TraceEvent,
    TerminatedReason,
)
from agent.tools.toolset import ToolSet, rules_returned, sections_returned

AGENT_VERSION = "v1"

#: How many characters of a tool result are shown to the model. Generous enough that no section in
#: the dataset is truncated; present so a pathological result cannot blow the context window
#: silently, which would look like an agent failure but be a harness artifact.
MAX_RESULT_CHARS = 8000

_FENCE = re.compile(r"^\s*```(?:json)?\s*(?P<body>.*?)\s*```\s*$", re.DOTALL)

_REPAIR_PROMPT = """\
Your previous response could not be used: {problem}

Reply with a single valid JSON object and nothing else. Either one tool call, or a final answer in \
the documented shape.
"""


@dataclass
class AgentResult:
    """What one trial produced.

    `output` is None when the agent never produced a usable answer. It is deliberately not filled
    in with a default status: inventing a status would let an unparseable response be scored as if
    the agent had answered, which on a compliant case would register as a correct answer.
    """

    trace: Trace
    output: AgentOutput | None
    harness_error: str = ""


def extract_json(text: str) -> dict | None:
    """Pull one JSON object out of a model response, tolerating common wrappers.

    Tolerant about packaging (code fences, leading prose) and strict about content: the result must
    be a JSON object. This is a formatting allowance, not a semantic one, and it never alters the
    keys or values the model produced.
    """
    if not text:
        return None
    candidate = text.strip()
    fenced = _FENCE.match(candidate)
    if fenced:
        candidate = fenced.group("body").strip()

    for attempt in (candidate, _first_balanced_object(candidate)):
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _first_balanced_object(text: str) -> str | None:
    """The first balanced `{...}` run, ignoring braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


class Agent:
    """Reviews one document against one policy. Constructed fresh per trial (spec section 21)."""

    version = AGENT_VERSION

    def __init__(
        self,
        client: LLMClient,
        *,
        max_steps: int = 12,
        max_result_chars: int = MAX_RESULT_CHARS,
    ) -> None:
        self._client = client
        self._max_steps = max_steps
        self._max_result_chars = max_result_chars

    def run(
        self,
        document: str,
        policy: Policy,
        *,
        config: RunConfig,
        experiment_id: str,
        case_id: str,
        trial_id: int = 1,
        run_id: str = "",
    ) -> AgentResult:
        tools = ToolSet(document, policy)
        trace = Trace(
            experiment_id=experiment_id,
            case_id=case_id,
            trial_id=trial_id,
            run_id=run_id,
            timestamp_utc=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            config=config,
            agent_input={
                "policy_id": policy.policy_id,
                "policy_version": policy.policy_version,
                "document_chars": len(document),
            },
        )

        transcript = p1.initial_prompt(policy.policy_id, policy.policy_version)
        seq = 0
        repaired = False
        pending_problem: str | None = None

        for _step in range(self._max_steps):
            prompt = transcript if pending_problem is None else (
                transcript + "\n\n" + _REPAIR_PROMPT.format(problem=pending_problem)
            )
            try:
                response = self._client.generate(p1.SYSTEM_PROMPT, prompt)
            except HarnessError as exc:
                # Infrastructure failure. The trial is void, not wrong.
                trace.terminated_reason = TerminatedReason.ERROR
                trace.output_validation = OutputValidation.NOT_PRODUCED
                trace.errors.append(str(exc))
                _finalise_totals(trace)
                return AgentResult(trace=trace, output=None, harness_error=str(exc))

            seq += 1
            trace.events.append(
                TraceEvent(
                    seq=seq,
                    type=EventType.LLM_CALL,
                    result_summary=_clip(response.text, 400),
                    latency_ms=response.latency_ms,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    thinking_tokens=response.thinking_tokens,
                    stop_reason=response.stop_reason or None,
                )
            )
            if response.model_version and not trace.config.model_version:
                trace.config.model_version = response.model_version

            message = extract_json(response.text)
            if message is None:
                outcome = self._handle_bad_message(
                    trace, "it was not a single JSON object", repaired
                )
                if outcome is not None:
                    trace.final_response_raw = response.text
                    return outcome
                repaired = True
                pending_problem = "it was not a single JSON object"
                continue

            if "final_answer" in message:
                trace.final_response_raw = response.text
                trace.final_decision = message["final_answer"]
                try:
                    output = AgentOutput.model_validate(message["final_answer"])
                except Exception as exc:  # noqa: BLE001 - pydantic raises its own error type
                    problem = f"the final answer did not match the required shape ({exc})"
                    outcome = self._handle_bad_message(trace, problem, repaired)
                    if outcome is not None:
                        return outcome
                    repaired = True
                    pending_problem = problem
                    continue

                trace.terminated_reason = TerminatedReason.FINAL_ANSWER
                trace.output_validation = (
                    OutputValidation.REPAIRED if repaired else OutputValidation.VALID
                )
                _finalise_totals(trace)
                return AgentResult(trace=trace, output=output)

            if "tool" in message:
                pending_problem = None
                transcript = self._dispatch(trace, tools, message, transcript)
                seq = trace.events[-1].seq
                continue

            problem = 'the object had neither a "tool" key nor a "final_answer" key'
            outcome = self._handle_bad_message(trace, problem, repaired)
            if outcome is not None:
                trace.final_response_raw = response.text
                return outcome
            repaired = True
            pending_problem = problem

        trace.terminated_reason = TerminatedReason.MAX_STEPS
        # The agent's messages parsed fine; it simply never finished. That is not the same failure
        # as emitting something unparseable, and conflating them would misattribute the cause.
        trace.output_validation = OutputValidation.NOT_PRODUCED
        trace.errors.append(f"reached max_steps={self._max_steps} without a final answer")
        _finalise_totals(trace)
        return AgentResult(trace=trace, output=None)

    # ------------------------------------------------------------------ internals
    def _handle_bad_message(
        self, trace: Trace, problem: str, already_repaired: bool
    ) -> AgentResult | None:
        """Return a finished result if the repair budget is spent, else None to retry once."""
        trace.errors.append(problem)
        if already_repaired:
            trace.terminated_reason = TerminatedReason.ERROR
            trace.output_validation = OutputValidation.UNPARSEABLE
            _finalise_totals(trace)
            return AgentResult(trace=trace, output=None)
        trace.retries += 1
        return None

    def _dispatch(
        self,
        trace: Trace,
        tools: ToolSet,
        message: dict,
        transcript: str,
    ) -> str:
        name = message.get("tool")
        arguments = message.get("arguments") or {}
        if not isinstance(arguments, dict):
            arguments = {"__malformed__": arguments}
        name = name if isinstance(name, str) else str(name)

        seq = trace.events[-1].seq + 1
        trace.events.append(
            TraceEvent(seq=seq, type=EventType.TOOL_CALL, tool=name, arguments=arguments)
        )

        result = tools.call(name, arguments)
        ok = "error" not in result
        trace.events.append(
            TraceEvent(
                seq=seq + 1,
                type=EventType.TOOL_RESULT if ok else EventType.TOOL_ERROR,
                tool=name,
                arguments=arguments,
                ok=ok,
                error=None if ok else str(result.get("error")),
                result_summary=_clip(json.dumps(result, sort_keys=True), 400),
                sections_returned=sections_returned(name, result) if ok else [],
                rules_returned=rules_returned(name, result) if ok else [],
            )
        )

        rendered = _clip(json.dumps(result, indent=2, sort_keys=True), self._max_result_chars)
        return transcript + "\n\n" + p1.TOOL_RESULT_PROMPT.format(
            tool=name, arguments=json.dumps(arguments, sort_keys=True), result=rendered
        )


def _clip(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [clipped, {len(text)} chars total]"


def _finalise_totals(trace: Trace) -> None:
    """Derive totals from events. Never recorded independently of the events they summarise."""
    totals = trace.totals
    totals.num_llm_calls = sum(1 for e in trace.events if e.type is EventType.LLM_CALL)
    totals.num_tool_calls = sum(1 for e in trace.events if e.type is EventType.TOOL_CALL)
    totals.num_tool_errors = sum(1 for e in trace.events if e.type is EventType.TOOL_ERROR)
    totals.latency_ms = sum(e.latency_ms or 0 for e in trace.events)
    totals.input_tokens = sum(e.input_tokens or 0 for e in trace.events)
    totals.output_tokens = sum(e.output_tokens or 0 for e in trace.events)
    totals.thinking_tokens = sum(e.thinking_tokens or 0 for e in trace.events)
    totals.total_tokens = totals.input_tokens + totals.output_tokens + totals.thinking_tokens

    seen: set[tuple[str, str]] = set()
    redundant = 0
    for event in trace.events:
        if event.type is not EventType.TOOL_CALL:
            continue
        key = (event.tool or "", json.dumps(event.arguments or {}, sort_keys=True))
        if key in seen:
            redundant += 1
        seen.add(key)
    totals.num_redundant_calls = redundant
