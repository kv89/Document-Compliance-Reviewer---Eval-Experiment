"""Prompt version p3: Experiment A2, output reliability (spec section 16).

p2 plus an output-format section, nothing else. Pre-registered in docs/decisions/decisions.md
(2026-10-25) before any live call. The p2 text is reused unchanged and is a strict prefix of the
p3 system prompt; the user prompt and the tool-result wrapper are p2's too.

The section answers the failures seen in run expA_p2-20261017T200247Z: 34 of 133 answers were
unparseable (fake "Result of ..." tool output the model wrote itself, Python-style dicts, prose, junk
tokens) and 7 cases returned empty replies on every attempt.
"""

from __future__ import annotations

from agent.prompts import p2
from agent.schemas.models import Policy

PROMPT_VERSION = "p3"

OUTPUT_FORMAT = """\

Output format. Every reply of yours is read by a program that parses it as JSON, so a reply that does \
not parse is lost:

- Your whole reply is exactly one JSON object. The first character is { and the last character is }. \
Nothing comes before it or after it.
- Use double quotes for every key and every string, and write null, true and false in lower case. \
Never use single quotes or Python-style dicts.
- Each reply is either one tool call or the final answer, never both and never more than one of \
either.
- Never write "Result of ..." or any tool output yourself. The system sends tool results to you. \
After you call a tool, stop and wait for its result.
- Never answer in prose and never wrap the JSON in markdown fences.
"""

SYSTEM_PROMPT = p2.SYSTEM_PROMPT + OUTPUT_FORMAT
USER_PROMPT = p2.USER_PROMPT
TOOL_RESULT_PROMPT = p2.TOOL_RESULT_PROMPT


def initial_prompt(policy: Policy) -> str:
    return p2.initial_prompt(policy)
