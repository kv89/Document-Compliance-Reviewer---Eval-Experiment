"""Trace models (spec section 12).

Traces are the central artifact for blog posts 4 and 5 and the input to every tool and trajectory
evaluator. They are append-only: never edit a trace after a run.

`TRACE_SCHEMA_VERSION` exists because traces outlive the experiment that produced them and are
quoted directly in the blog series. Design v1 left them unversioned.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

TRACE_SCHEMA_VERSION = "1.2"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventType(str, Enum):
    LLM_CALL = "llm_call"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TOOL_ERROR = "tool_error"


class TerminatedReason(str, Enum):
    """Distinguishing these matters for trajectory evaluation (spec section 14 Layer 4)."""

    FINAL_ANSWER = "final_answer"
    MAX_STEPS = "max_steps"
    ERROR = "error"
    TIMEOUT = "timeout"


class OutputValidation(str, Enum):
    """How the agent's final answer was obtained.

    `NOT_PRODUCED` was added in schema 1.1 after the first live run recorded a trial killed by a
    quota rejection as `valid`. There had been no output at all, so calling it valid was simply
    false, and `unparseable` would have been equally wrong: nothing was ever offered to parse.
    The distinction matters because `unparseable` is an agent failure that counts against it,
    while a trial with no output may be either an agent failure (it never answered) or a voided
    trial (the infrastructure failed), and `harness_error` is what separates those two.
    """

    VALID = "valid"
    REPAIRED = "repaired"
    UNPARSEABLE = "unparseable"
    NOT_PRODUCED = "not_produced"


class RunConfig(_Model):
    """Everything needed to reproduce a run (spec section 6.2).

    `seed` is included. Design v1 omitted it, which left the reproducibility claim in section 28
    unsupportable.

    Inference is a hosted free-tier API (spec section 6.3), so `provider` and `model_version` are
    recorded: a hosted model alias can be re-pointed at new weights without notice, and the version
    the API reports back is the only per-run evidence of what actually answered. `quantization` and
    `num_ctx` are gone because neither is observable through a hosted API.
    """

    provider: str = ""
    model_name: str = ""
    model_tag: str = ""
    #: Provider-reported identifier for the weights that served this run.
    model_version: str = ""
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int | None = None
    seed: int | None = None
    max_output_tokens: int | None = None
    #: Lowest thinking setting the model accepts. Schema 1.2 replaced a numeric thinking budget:
    #: Gemini 3.x rejects `thinking_budget` with a 400 and its `thinking_level` floor is MINIMAL,
    #: so internal reasoning can be reduced but not switched off.
    thinking_level: str = ""
    max_steps: int = 12
    #: Client library version, e.g. "google-genai 2.25.0".
    runtime_version: str = ""
    python_version: str = ""
    hardware_id: str = ""
    prompt_version: str = ""
    tool_set_version: str = ""
    agent_version: str = ""
    dataset_version: str = ""
    policy_version: str = ""


class TraceEvent(_Model):
    seq: int = Field(ge=1)
    type: EventType
    tool: str | None = None
    arguments: dict[str, Any] | None = None
    ok: bool | None = None
    error: str | None = None
    result_summary: str | None = None
    # Section identifiers the tool result actually exposed to the agent. Required-information
    # coverage (spec section 13) is computed from these, which is what keeps the check
    # order-agnostic.
    sections_returned: list[str] = Field(default_factory=list)
    # Rule identifiers a successful lookup_policy result exposed to the agent. Kept separate from
    # sections_returned so that one field never carries two meanings.
    rules_returned: list[str] = Field(default_factory=list)
    latency_ms: int | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    #: Internal reasoning tokens the provider charged but never returned. Recorded because they are
    #: real work and real cost that the trace cannot otherwise see.
    thinking_tokens: int | None = None
    stop_reason: str | None = None


class TraceTotals(_Model):
    latency_ms: int = 0
    num_llm_calls: int = 0
    num_tool_calls: int = 0
    num_tool_errors: int = 0
    num_redundant_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    #: input + output + thinking. Thinking tokens are counted separately by the provider but are
    #: charged, so leaving them out would understate the cost of every trial.
    total_tokens: int = 0


class Trace(_Model):
    trace_schema_version: str = TRACE_SCHEMA_VERSION
    experiment_id: str
    case_id: str
    trial_id: int = Field(ge=1)
    run_id: str
    timestamp_utc: str
    config: RunConfig
    agent_input: dict[str, Any] = Field(default_factory=dict)
    events: list[TraceEvent] = Field(default_factory=list)
    retries: int = 0
    errors: list[str] = Field(default_factory=list)
    final_response_raw: str = ""
    final_decision: dict[str, Any] | None = None
    output_validation: OutputValidation = OutputValidation.VALID
    totals: TraceTotals = Field(default_factory=TraceTotals)
    terminated_reason: TerminatedReason = TerminatedReason.FINAL_ANSWER

    def tool_calls(self) -> list[TraceEvent]:
        return [e for e in self.events if e.type is EventType.TOOL_CALL]

    def sections_seen(self) -> set[str]:
        """Every section identifier any successful tool result exposed to the agent."""
        seen: set[str] = set()
        for e in self.events:
            if e.type is EventType.TOOL_RESULT and e.ok is not False:
                seen.update(e.sections_returned)
        return seen

    def policy_rules_consulted(self) -> set[str]:
        """Rule identifiers returned by successful lookup_policy calls."""
        consulted: set[str] = set()
        for e in self.events:
            if e.type is EventType.TOOL_RESULT and e.tool == "lookup_policy" and e.ok is not False:
                consulted.update(e.rules_returned)
        return consulted
