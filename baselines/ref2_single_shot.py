"""REF-2: single-shot LLM baseline, no tools (spec section 15.1).

It answers the question "does the agent loop and tool set add anything over putting the document
and policy directly into the prompt?"

The entire policy and the full raw document are supplied in a single prompt. The model is asked for
the exact same structured output JSON (`status`, `findings`, `summary`). No tools are provided.
"""

from __future__ import annotations

from typing import Protocol

from agent.agent import extract_json
from agent.schemas.models import AgentOutput, ComplianceStatus, GroundTruthCase, Policy

VERSION = "ref2"

SYSTEM_PROMPT = """\
You are a compliance reviewer. You review one document against one policy and report whether the \
document complies.

You are given the complete policy and the entire document text. You do not have tools.

Respond with a single JSON object and nothing else. No markdown fences, no commentary.

Expected output format:
{
  "status": "COMPLIANT" | "NON_COMPLIANT" | "NEEDS_REVIEW",
  "findings": [
    {
      "rule_id": "the policy rule that is violated",
      "finding_type": "MISSING_CLAUSE" | "POLICY_VIOLATION" | "CONTRADICTION" | "AMBIGUOUS",
      "clause": "the clause name from the policy rule",
      "severity": "LOW" | "MEDIUM" | "HIGH",
      "description": "what is wrong",
      "evidence": {
        "section_id": "the section the quote came from",
        "quote": "text copied exactly from the document",
        "char_start": 0,
        "char_end": 0
      }
    }
  ],
  "summary": "one or two sentences"
}

Rules:
- Every quote must be copied character for character from the document.
- char_start and char_end are the exact 0-indexed character offsets of that quote in the document text.
- Use MISSING_CLAUSE when the document does not contain a required clause at all; set evidence to null.
- Take rule_id, clause and severity from the policy rule itself.
- Report COMPLIANT only if you found no violation (findings must be an empty list).
- Use NEEDS_REVIEW when the document is genuinely ambiguous.
"""

USER_PROMPT_TEMPLATE = """\
### POLICY: {policy_id} (version {policy_version})

Rules:
{policy_rules}

### DOCUMENT:
{document_text}

Review the document against the policy and output your JSON verdict now.
"""


class LLMClient(Protocol):
    def generate(self, system: str, prompt: str) -> object: ...


def format_rules(policy: Policy) -> str:
    lines = []
    for r in policy.rules:
        clause_desc = f" [{r.clause}]" if r.clause else ""
        lines.append(f"- Rule {r.rule_id}{clause_desc}: {r.statement} (Severity: {r.severity.value})")
    return "\n".join(lines)


def build_prompt(policy: Policy, document: str) -> str:
    return USER_PROMPT_TEMPLATE.format(
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        policy_rules=format_rules(policy),
        document_text=document,
    )


def run(
    document: str,
    policy: Policy,
    case: GroundTruthCase,
    client: LLMClient | None = None,
) -> tuple[AgentOutput | None, dict]:
    """Execute the single-shot prompt against client.

    Returns (AgentOutput, metadata) where metadata contains token usage, model info and the raw
    response text, which the runner stores in a trace. A HarnessError from the client propagates:
    an infrastructure failure is the runner's to void, never this baseline's to score.
    """
    del case  # ground truth never leaked to model
    if client is None:
        raise ValueError("REF-2 requires an LLM client instance.")

    prompt = build_prompt(policy, document)
    resp = client.generate(SYSTEM_PROMPT, prompt)

    metadata = {
        "input_tokens": getattr(resp, "input_tokens", 0),
        "output_tokens": getattr(resp, "output_tokens", 0),
        "thinking_tokens": getattr(resp, "thinking_tokens", 0),
        "model_version": getattr(resp, "model_version", ""),
        "latency_ms": getattr(resp, "latency_ms", 0),
        "stop_reason": getattr(resp, "stop_reason", ""),
        "raw_text": getattr(resp, "text", ""),
    }

    text = getattr(resp, "text", "")
    data = extract_json(text)
    if data is None:
        return None, metadata

    # If wrapped in final_answer (like agent output), unwrap it
    if "final_answer" in data and isinstance(data["final_answer"], dict):
        data = data["final_answer"]

    try:
        output = AgentOutput.model_validate(data)
        return output, metadata
    except Exception:
        return None, metadata
