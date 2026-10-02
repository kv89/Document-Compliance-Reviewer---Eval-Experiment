"""Model client (spec section 6.3).

Inference runs on the Google AI Studio free tier. Two things in here exist because of that choice
rather than because of the agent design, and both are measurement concerns:

1. **Quota rejections are not agent failures.** A free tier enforces requests per minute and per
   day. A rejected request says nothing about whether the agent can review a document, so it is
   retried with backoff and, if it still fails, raised as `HarnessError`. The runner records it in
   `harness_error` and the trial is excluded from every metric denominator. Scoring a 429 as a wrong
   answer would be the same class of measurement bug as silently truncating the context window.

2. **Thinking is floored, not disabled.** The model reasons internally and those tokens are never
   returned, so hidden reasoning is invisible to the trace and would leave the trajectory
   evaluation in section 14 Layer 4 blind to part of what the model did. Gemini 2.5 accepted
   `thinking_budget = 0`; Gemini 3.x rejects it with a 400 and offers a `thinking_level` whose
   lowest value is `MINIMAL`. Thinking therefore **cannot be turned off** on the baseline model.
   The floor is set explicitly and `thoughts_token_count` is recorded on every request, so the
   hidden work is at least counted and a provider default moving underneath us shows up in the
   data rather than silently altering results.

3. **Native function calling is switched off, and JSON output mode is switched on.** The agent
   speaks a JSON text protocol on purpose, so that an unauthorized tool name is something it can
   attempt and safety check S6 can count (see `agent/prompts/p1.py`). Gemini 3 is trained to route
   that kind of output into a function call instead: the first live run returned
   `finish_reason = MALFORMED_FUNCTION_CALL` with empty text on three of eight requests, because
   the model tried to call a function while no tools were declared. Disabling automatic function
   calling and asking for a JSON mime type keeps the model emitting text we can read. The
   underlying tension is worth recording rather than hiding: a provider's preferred interface and
   a measurable one are not always the same interface.

The `LLMClient` protocol exists so the agent loop never imports a provider. Tests drive the loop
with `ScriptedClient`, which needs no key and no network.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

#: Markers of a quota that resets daily rather than per minute. A per-day quota cannot be waited
#: out inside a run, so retrying one burns a minute of backoff to arrive at the same rejection. The
#: first live run did exactly that, twice. These are matched against the quota identifier Google
#: returns in the error body.
DAILY_QUOTA_MARKERS = ("PERDAY", "PER_DAY", "REQUESTSPERDAY")

#: Markers of a model that cannot be called at all: withdrawn, renamed, or not granted to this key.
#: Separated from other provider errors because no retry and no agent behaviour is involved, and
#: because the whole run is misconfigured rather than one trial being unlucky.
UNAVAILABLE_MARKERS = ("404", "NOT_FOUND", "IS NO LONGER AVAILABLE", "PERMISSION_DENIED", "403")

#: Substrings that identify a retryable infrastructure failure rather than a bad request. Matched
#: against the exception text because the free tier surfaces quota problems through several
#: different status codes.
RETRYABLE_MARKERS = (
    "429",
    "RESOURCE_EXHAUSTED",
    "500",
    "502",
    "503",
    "504",
    "UNAVAILABLE",
    "INTERNAL",
    "DEADLINE_EXCEEDED",
)


class HarnessError(RuntimeError):
    """An infrastructure failure. Never scored as agent behaviour."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


@dataclass(frozen=True)
class QuotaPolicy:
    """Retry schedule for free-tier rejections. Values come from the experiment config."""

    max_retries: int = 5
    initial_backoff_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 60.0

    def delay_for(self, attempt: int) -> float:
        """Backoff for a zero-indexed attempt, capped."""
        raw = self.initial_backoff_seconds * (self.backoff_multiplier**attempt)
        return min(raw, self.max_backoff_seconds)


@dataclass
class LLMResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    latency_ms: int = 0
    #: Provider-reported version of the weights that served this request. Mandatory per spec 6.2:
    #: a hosted alias can be re-pointed at new weights, and this is the only record of what ran.
    model_version: str = ""
    stop_reason: str = ""


class LLMClient(Protocol):
    """What the agent loop needs from a model. Deliberately minimal."""

    model_name: str
    model_version: str
    runtime_version: str

    def generate(self, system: str, prompt: str) -> LLMResponse: ...


@dataclass
class ScriptedClient:
    """Returns pre-written responses in order. For tests and for offline development.

    The agent loop is a state machine over model output, and a scripted client lets every branch of
    it be tested without a key, a network or a quota: a malformed JSON reply, an unauthorized tool
    name, a step limit, a refusal to stop. None of those are reliably reproducible against a real
    model, which is exactly why they must not be tested against one.
    """

    responses: list[str]
    model_name: str = "scripted"
    model_version: str = "scripted"
    runtime_version: str = "scripted"
    calls: list[tuple[str, str]] = field(default_factory=list)

    def generate(self, system: str, prompt: str) -> LLMResponse:
        self.calls.append((system, prompt))
        if not self.responses:
            raise HarnessError("SCRIPT_EXHAUSTED", "ScriptedClient ran out of responses")
        text = self.responses.pop(0)
        return LLMResponse(
            text=text,
            input_tokens=len(prompt.split()),
            output_tokens=len(text.split()),
            model_version=self.model_version,
            stop_reason="STOP",
        )


class GeminiClient:
    """Google AI Studio free tier via the `google-genai` client.

    The key is read from the environment and is never written to a config file, a trace or a result
    row (spec section 6.3).
    """

    def __init__(
        self,
        model_name: str,
        *,
        temperature: float = 0.0,
        top_p: float = 1.0,
        top_k: int | None = None,
        seed: int | None = None,
        max_output_tokens: int | None = 2048,
        thinking_level: str | None = "MINIMAL",
        quota: QuotaPolicy | None = None,
        api_key_env: str = "GOOGLE_API_KEY",
        sleep=time.sleep,
    ) -> None:
        from google import genai  # imported lazily so milestone 1 needs no SDK

        key = os.environ.get(api_key_env) or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise HarnessError(
                "NO_API_KEY",
                f"Set {api_key_env}. The key is read from the environment only, never from a file.",
            )

        self._genai = genai
        self._client = genai.Client(api_key=key)
        self.model_name = model_name
        #: Filled in from the first response. Empty until then, and never guessed.
        self.model_version = ""
        self.runtime_version = f"google-genai {getattr(genai, '__version__', 'unknown')}"
        self._temperature = temperature
        self._top_p = top_p
        self._top_k = top_k
        self._seed = seed
        self._max_output_tokens = max_output_tokens
        self._thinking_level = thinking_level
        self._quota = quota or QuotaPolicy()
        self._sleep = sleep

    def _config(self, system: str):
        from google.genai import types

        kwargs: dict = {
            "system_instruction": system,
            "temperature": self._temperature,
            "top_p": self._top_p,
            "max_output_tokens": self._max_output_tokens,
            # No tools are declared, so any function call the model attempts can only fail. Saying
            # so explicitly stops the SDK interpreting our JSON as a call attempt.
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
            # A mime type, deliberately without a `response_schema`. The schema would have the
            # provider enforce the output shape, which is exactly what section 11 needs to measure
            # the agent doing for itself: a repaired or malformed answer is a result, not a defect
            # to be engineered away.
            "response_mime_type": "application/json",
        }
        if self._top_k is not None:
            kwargs["top_k"] = self._top_k
        if self._seed is not None:
            kwargs["seed"] = self._seed
        if self._thinking_level is not None:
            kwargs["thinking_config"] = types.ThinkingConfig(
                thinking_level=self._thinking_level
            )
        return types.GenerateContentConfig(**kwargs)

    def generate(self, system: str, prompt: str) -> LLMResponse:
        last_error = ""
        for attempt in range(self._quota.max_retries + 1):
            started = time.monotonic()
            try:
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=self._config(system),
                )
            except Exception as exc:  # noqa: BLE001 - the SDK raises several unrelated types
                last_error = f"{type(exc).__name__}: {exc}"
                if _is_unavailable(last_error):
                    raise HarnessError("MODEL_UNAVAILABLE", last_error) from exc
                if _is_daily_quota(last_error):
                    # Nothing to wait for. The budget is gone until the quota window rolls over,
                    # so fail immediately and let the runner stop the sweep rather than spend a
                    # minute of backoff per remaining trial to collect identical rejections.
                    raise HarnessError("DAILY_QUOTA_EXHAUSTED", last_error) from exc
                if not _is_retryable(last_error) or attempt == self._quota.max_retries:
                    raise HarnessError("PROVIDER_ERROR", last_error) from exc
                # Prefer the provider's own retry hint when it gives one: guessing a backoff that
                # is shorter than the real reset just wastes an attempt.
                advised = _advised_delay(last_error)
                delay = max(advised, self._quota.delay_for(attempt)) if advised else (
                    self._quota.delay_for(attempt)
                )
                delay = min(delay, self._quota.max_backoff_seconds)
                # Jitter so repeated cases in a sweep do not retry in lockstep and re-collide.
                self._sleep(delay * (1.0 + random.random() * 0.1))
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            usage = response.usage_metadata
            version = response.model_version or ""
            if version:
                self.model_version = version
            text = response.text
            reason = _finish_reason(response)
            if text is None or not text.strip():
                # The provider returned no text. Observed live as MALFORMED_FUNCTION_CALL: the model
                # tried to emit a function call, and because no tools are declared nothing came
                # back. There is no agent output to judge, so this must not be parsed as an answer
                # or charged to the agent as a malformed one. It is also not deterministic, so one
                # more attempt is worth making before the trial is written off.
                last_error = f"empty response (finish reason {reason!r})"
                if attempt == self._quota.max_retries:
                    raise HarnessError("EMPTY_RESPONSE", last_error)
                self._sleep(self._quota.delay_for(attempt) * (1.0 + random.random() * 0.1))
                continue
            return LLMResponse(
                text=text,
                input_tokens=getattr(usage, "prompt_token_count", 0) or 0,
                output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
                thinking_tokens=getattr(usage, "thoughts_token_count", 0) or 0,
                latency_ms=latency_ms,
                model_version=version,
                stop_reason=reason,
            )

        raise HarnessError("QUOTA_EXHAUSTED", last_error or "retries exhausted")


def _is_retryable(error_text: str) -> bool:
    upper = error_text.upper()
    return any(marker in upper for marker in RETRYABLE_MARKERS)


def _is_unavailable(error_text: str) -> bool:
    """Is the model itself uncallable, making every trial in the run void?

    A model can appear in `models.list` and still be closed to new keys. The first Flash-Lite run
    hit exactly that: a 404 saying the model "is no longer available to new users". Retrying or
    continuing the sweep would produce one void trial per case.
    """
    upper = error_text.upper()
    return any(marker in upper for marker in UNAVAILABLE_MARKERS)


def _is_daily_quota(error_text: str) -> bool:
    """Is this a per-day quota, which no amount of in-run backoff can clear?"""
    upper = error_text.upper().replace("-", "")
    return any(marker in upper for marker in DAILY_QUOTA_MARKERS)


def _advised_delay(error_text: str) -> float:
    """The provider's own `retryDelay` hint, in seconds, or 0 if it gave none."""
    match = re.search(r"retryDelay['\"]?:\s*['\"]?(\d+(?:\.\d+)?)s", error_text)
    if match:
        return float(match.group(1))
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", error_text)
    return float(match.group(1)) if match else 0.0


def _finish_reason(response) -> str:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    reason = getattr(candidates[0], "finish_reason", None)
    return getattr(reason, "name", None) or str(reason or "")
