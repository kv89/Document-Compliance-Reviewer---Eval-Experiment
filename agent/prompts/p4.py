"""Prompt version p4: Experiment A3, tool-argument placement (spec section 16).

p3 plus one worked example, nothing else. Pre-registered in docs/decisions/decisions.md
(2026-10-26) before any live call. The p3 text is reused unchanged and is a strict prefix of the p4
system prompt; the user prompt and the tool-result wrapper are p3's too.

The section answers the failure seen in run expA2_p3-20261025T120453Z: all 136 measured traces open
with `{"tool": "lookup_policy", "rule_id": "CLAUSE-..."}`, with `rule_id` outside `arguments`. The
tool returns INVALID_ARGUMENTS and S6 flags 133 cases. p2 had none of these.
"""

from __future__ import annotations

from agent.prompts import p3
from agent.schemas.models import Policy

PROMPT_VERSION = "p4"

TOOL_ARGUMENTS = """\

Tool arguments. Every parameter of a tool goes inside the "arguments" object, never next to "tool". \
Correct:

{"tool": "lookup_policy", "arguments": {"rule_id": "CLAUSE-PAY-001"}}

Wrong, because rule_id is outside "arguments":

{"tool": "lookup_policy", "rule_id": "CLAUSE-PAY-001"}
"""

SYSTEM_PROMPT = p3.SYSTEM_PROMPT + TOOL_ARGUMENTS
USER_PROMPT = p3.USER_PROMPT
TOOL_RESULT_PROMPT = p3.TOOL_RESULT_PROMPT


def initial_prompt(policy: Policy) -> str:
    return p3.initial_prompt(policy)
