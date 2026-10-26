"""Prompt versions, selected by `RunConfig.prompt_version` (spec section 16, Experiment A).

The trace records the prompt version, so the agent takes the prompt from the same field. A run
cannot record one version and send another.
"""

from __future__ import annotations

from types import ModuleType

from agent.prompts import p1, p2, p3, p4
from agent.schemas.models import Policy

PROMPTS: dict[str, ModuleType] = {"p1": p1, "p2": p2, "p3": p3, "p4": p4}


def get_prompt(version: str) -> ModuleType:
    try:
        return PROMPTS[version]
    except KeyError:
        raise ValueError(
            f"Unknown prompt_version {version!r}; known versions: {sorted(PROMPTS)}"
        ) from None


def initial_prompt(version: str, policy: Policy) -> str:
    if version == "p1":
        return p1.initial_prompt(policy.policy_id, policy.policy_version)
    return get_prompt(version).initial_prompt(policy)
