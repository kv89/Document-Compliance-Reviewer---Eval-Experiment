"""Trial row: one evaluated execution (spec section 23).

JSONL is the source of truth. SQLite is a derived convenience view built later by a loader script,
not the primary record.

Every field exists because some consumer needs it. `case_category` is here because per-category
reporting is impossible without it. `prompt_version`, `tool_set_version` and `seed` are here
because experiments A, E and F vary them. `terminated_reason` and `output_validation` are here
because a failed run must be visible in the data rather than missing from it: silently dropping
malformed runs would inflate every other metric.

Schema 1.1 replaced the Ollama-specific `ollama_version` with a provider-neutral triple of
`provider`, `model_version` and `runtime_version`, because inference moved to a hosted API. The
important one is `model_version`: a hosted model alias such as `gemini-2.5-flash` can be re-pointed
at new weights without notice, so the version string the API reports back is the only per-trial
record of what actually answered. A local model tag used to be immutable; this one is not, and
section 28's reproducibility claim depends on having captured it.

`harness_error` exists because a rate-limit rejection or a network failure is not an agent failure.
Counting a quota 429 as a wrong answer would corrupt every denominator, so these trials are marked
and excluded at analysis time rather than scored.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

RESULTS_SCHEMA_VERSION = "1.2"


class TrialRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # identity and configuration
    experiment_id: str
    run_id: str
    agent_version: str
    prompt_version: str = ""
    tool_set_version: str = ""
    model_name: str = ""
    model_tag: str = ""
    temperature: float | None = None
    seed: int | None = None
    provider: str = ""
    #: Version string reported by the provider for the weights that served this trial.
    model_version: str = ""
    #: Client library or server version, e.g. "google-genai 2.25.0" or "ollama 0.3.12".
    runtime_version: str = ""
    hardware_id: str = ""
    dataset_version: str
    policy_id: str
    policy_version: str

    case_id: str
    case_category: str
    scoring_mode: str
    trial_id: int = Field(ge=1)

    # Layer 1, outcome
    expected_status: str | None
    accepted_statuses: list[str]
    actual_status: str
    status_correct: bool
    tp: int
    fp: int
    fn: int
    tp_strict: int
    duplicate_findings: int
    finding_precision: float | None
    finding_recall: float | None
    finding_f1: float | None
    findings_exact: bool
    findings_exact_lenient: bool

    # Layer 2, evidence
    evidence_checked: int
    evidence_accuracy: float | None
    evidence_quote_verbatim: int
    evidence_offsets_consistent: int
    evidence_section_correct: int
    evidence_span_overlap: float | None
    fabricated_evidence_count: int

    # Layer 3, tools
    num_tool_calls: int
    num_tool_errors: int
    num_redundant_calls: int
    argument_validity: float | None
    required_info_coverage: float | None

    # Layer 4, trajectory (deterministic only in the baseline)
    num_llm_calls: int
    steps: int
    retries: int
    loop_detected: bool | None
    recovered_after_error: bool | None
    terminated_reason: str
    #: Non-empty when the trial failed for an infrastructure reason (rate limit, network, provider
    #: error) rather than an agent reason. Such trials are excluded from metric denominators.
    harness_error: str = ""

    # Layer 5, safety
    safety_violations: int
    safety_violation_ids: list[str]
    safety_checks_skipped: list[str]

    # Layer 6, efficiency
    latency_ms: int
    input_tokens: int
    output_tokens: int
    #: Internal reasoning tokens: charged by the provider, never returned, invisible to the trace.
    #: Schema 1.2. Included in `total_tokens`, because excluding them understates the cost of every trial.
    thinking_tokens: int = 0
    total_tokens: int

    # grading provenance
    output_validation: str
    deterministic_result: str  # pass | fail
    llm_judge_result: str | None = None
    judge_model: str | None = None
    judge_prompt_version: str | None = None
    judge_input_profile: str | None = None
    rubric_version: str | None = None
    human_result: str | None = None
    human_reviewer_id: str | None = None

    trace_path: str | None = None
    timestamp_utc: str
    results_schema_version: str = RESULTS_SCHEMA_VERSION
