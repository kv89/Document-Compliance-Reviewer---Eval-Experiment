"""Find which generation parameters a model accepts (spec section 6.3).

A 400 INVALID_ARGUMENT does not say which argument was invalid, and the generation parameters we
rely on are not uniformly supported across model generations. This sends one minimal request per
parameter and reports what each model accepts, so the run configuration is set from measurement
rather than assumption.

Usage:
    export GOOGLE_API_KEY=...
    uv run python scripts/diagnose_model.py gemini-3.5-flash-lite
    uv run python scripts/diagnose_model.py gemini-3.5-flash-lite gemma-4-31b-it

Costs one request per probe, about eight per model.
"""

from __future__ import annotations

import sys

from google import genai
from google.genai import types

PROMPT = "Reply with the single word: ok"


def probes() -> list[tuple[str, dict]]:
    """Each probe adds one thing to the previous working baseline."""
    return [
        ("bare request", {}),
        ("temperature + top_p", {"temperature": 0.0, "top_p": 1.0}),
        ("max_output_tokens", {"max_output_tokens": 2048}),
        ("seed", {"seed": 7}),
        ("system_instruction", {"system_instruction": "You are terse."}),
        (
            "thinking_budget=0",
            {"thinking_config": types.ThinkingConfig(thinking_budget=0)},
        ),
        *[
            (
                f"thinking_level={level}",
                {"thinking_config": types.ThinkingConfig(thinking_level=level)},
            )
            for level in ("MINIMAL", "LOW")
        ],
        ("response_mime_type=application/json", {"response_mime_type": "application/json"}),
    ]


def run(client: genai.Client, model: str) -> None:
    print(f"\n=== {model} ===")
    accepted: list[str] = []
    for label, kwargs in probes():
        try:
            response = client.models.generate_content(
                model=model,
                contents=PROMPT,
                config=types.GenerateContentConfig(**kwargs),
            )
        except Exception as exc:  # noqa: BLE001 - reporting whatever the SDK raises is the point
            message = str(exc).replace("\n", " ")
            print(f"  REJECTED  {label}: {message[:160]}")
            continue

        usage = response.usage_metadata
        thoughts = getattr(usage, "thoughts_token_count", 0) or 0
        accepted.append(label)
        print(
            f"  ok        {label}: version={response.model_version} "
            f"thinking_tokens={thoughts} text={(response.text or '')[:30]!r}"
        )

    print(f"  accepted: {', '.join(accepted) or 'nothing'}")


def main() -> int:
    models = sys.argv[1:] or ["gemini-3.5-flash-lite"]
    client = genai.Client()
    for model in models:
        run(client, model)
    print(
        "\nSet the run config from the lines marked ok. A rejected parameter must be removed from "
        "`experiments/configs/*.yaml` and the omission recorded, because anything we cannot set is "
        "a reproducibility limit to disclose (spec section 6.2)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
