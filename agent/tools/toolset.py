"""The four agent tools (spec section 10), tool set version t1.

Contract, identical for every tool:

* Return a JSON-serialisable dict. Never raise into the agent loop.
* On failure return {"error": CODE, "message": ..., ...recovery hints}. Tool errors are a Layer 3
  measurement and a recovery opportunity for the agent, so they must reach the agent as data.
* Pure reads. No tool modifies the document, the policy or any state (spec section 27).

`list_document_sections` is in the baseline set, not deferred as design v1 proposed. Without a
discovery tool the agent must guess section identifiers, so argument_correctness would have
measured the absence of an affordance rather than the agent's reasoning (spec section 10).
"""

from __future__ import annotations

import re
from typing import Any, Callable

from agent.schemas.models import Policy
from agent.tools.splitter import ParsedDocument, split_document

TOOL_SET_VERSION = "t1"

MAX_SEARCH_RESULTS = 5
TOKEN_MATCH_CEILING = 0.9
SNIPPET_RADIUS = 80

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class ToolError(dict):
    """A tool failure, returned rather than raised."""

    def __init__(self, code: str, message: str, **extra: Any) -> None:
        super().__init__(error=code, message=message, **extra)


class ToolSet:
    """Tools bound to one document and one policy.

    Constructed fresh per trial. Each trial starts from clean state with no shared mutable objects
    (spec section 21).
    """

    version = TOOL_SET_VERSION

    def __init__(self, document: str, policy: Policy) -> None:
        self._text = document
        self._doc: ParsedDocument = split_document(document)
        self._policy = policy
        self.call_log: list[tuple[str, dict[str, Any], bool]] = []

    # ------------------------------------------------------------------ tool 1
    def list_document_sections(self) -> dict[str, Any]:
        """Return the available sections. Discovery tool."""
        return {
            "document_title": self._doc.title,
            "sections": [
                {"section_id": s.section_id, "title": s.title} for s in self._doc.sections
            ],
        }

    # ------------------------------------------------------------------ tool 2
    def get_document_section(self, section_id: str) -> dict[str, Any]:
        """Return one section verbatim, with the offsets evidence must cite."""
        if not isinstance(section_id, str) or not section_id.strip():
            return ToolError(
                "INVALID_ARGUMENTS",
                "section_id must be a non-empty string",
                valid_section_ids=list(self._doc.section_ids),
            )
        section = self._doc.section(section_id.strip())
        if section is None:
            return ToolError(
                "UNKNOWN_SECTION",
                f"No section {section_id!r} in this document",
                valid_section_ids=list(self._doc.section_ids),
            )
        return {
            "section_id": section.section_id,
            "title": section.title,
            "body": section.body,
            "char_start": section.char_start,
            "char_end": section.char_end,
        }

    # ------------------------------------------------------------------ tool 3
    def search_document(self, query: str) -> dict[str, Any]:
        """Search document text.

        Version t1 is case-insensitive substring matching with a token-overlap fallback. This is
        the deliberate retrieval baseline: experiment B replaces it with BM25, which keeps
        "improved retrieval" inside the no-vector-database limit of spec section 27.

        Ties are broken by section identifier so that results are byte-identical across runs.
        Non-deterministic result ordering would contaminate the trial-consistency measurement.
        """
        if not isinstance(query, str) or not query.strip():
            return ToolError("INVALID_ARGUMENTS", "query must be a non-empty string")

        q = query.strip()
        q_lower = q.lower()
        q_tokens = set(_tokens(q))
        results: list[dict[str, Any]] = []

        for section in self._doc.sections:
            body_lower = section.body.lower()
            hit = body_lower.find(q_lower)
            if hit != -1:
                start = section.char_start + hit
                end = start + len(q)
                score = 1.0
            elif q_tokens:
                overlap = len(q_tokens & set(_tokens(section.body)))
                if overlap == 0:
                    continue
                # Scaled below 1.0 so an exact substring match always outranks full token
                # overlap. Without the cap both paths score 1.0 and ranking becomes arbitrary.
                score = round(TOKEN_MATCH_CEILING * overlap / len(q_tokens), 4)
                start, end = section.char_start, section.char_start + len(q)
            else:
                continue

            snip_start = max(section.char_start, start - SNIPPET_RADIUS)
            snip_end = min(section.char_end, end + SNIPPET_RADIUS)
            results.append(
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "snippet": self._text[snip_start:snip_end],
                    "char_start": start,
                    "char_end": end,
                    "score": score,
                }
            )

        results.sort(key=lambda r: (-r["score"], r["section_id"]))
        return {
            "query": q,
            "match_count": len(results),
            "results": results[:MAX_SEARCH_RESULTS],
        }

    # ------------------------------------------------------------------ tool 4
    def lookup_policy(
        self, rule_id: str | None = None, clause: str | None = None
    ) -> dict[str, Any]:
        """Return policy rules by identifier or by clause. One of the two is required."""
        if rule_id is None and clause is None:
            return ToolError(
                "INVALID_ARGUMENTS",
                "Provide rule_id or clause",
                valid_rule_ids=sorted(self._policy.rule_ids),
            )

        rules = list(self._policy.rules)
        if rule_id is not None:
            if not isinstance(rule_id, str):
                return ToolError("INVALID_ARGUMENTS", "rule_id must be a string")
            rules = [r for r in rules if r.rule_id == rule_id.strip()]
            if not rules:
                return ToolError(
                    "UNKNOWN_RULE",
                    f"No rule {rule_id!r} in policy {self._policy.policy_id}",
                    valid_rule_ids=sorted(self._policy.rule_ids),
                )
        if clause is not None:
            if not isinstance(clause, str):
                return ToolError("INVALID_ARGUMENTS", "clause must be a string")
            wanted = clause.strip().lower()
            rules = [r for r in rules if r.clause.lower() == wanted]
            if not rules:
                return ToolError(
                    "UNKNOWN_CLAUSE",
                    f"No rule for clause {clause!r}",
                    valid_clauses=sorted({r.clause for r in self._policy.rules}),
                )

        return {
            "policy_id": self._policy.policy_id,
            "policy_version": self._policy.policy_version,
            "rules": [r.model_dump(mode="json") for r in rules],
        }

    # ------------------------------------------------------------------ dispatch
    @property
    def authorized_tools(self) -> tuple[str, ...]:
        return (
            "list_document_sections",
            "get_document_section",
            "search_document",
            "lookup_policy",
        )

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Dispatch a named tool call.

        Rejects unauthorized tool names and malformed argument sets. Both are S6 safety violations,
        and both are returned as data so the agent gets a chance to recover and the evaluator gets
        a chance to count the attempt.
        """
        arguments = dict(arguments or {})
        if name not in self.authorized_tools:
            result = ToolError(
                "UNAUTHORIZED_TOOL",
                f"Tool {name!r} is not available",
                authorized_tools=list(self.authorized_tools),
            )
            self.call_log.append((name, arguments, False))
            return result

        fn: Callable[..., dict[str, Any]] = getattr(self, name)
        try:
            result = fn(**arguments)
        except TypeError as exc:
            result = ToolError("INVALID_ARGUMENTS", str(exc))
        self.call_log.append((name, arguments, "error" not in result))
        return result


def sections_returned(tool: str, result: dict[str, Any]) -> list[str]:
    """Section identifiers a tool result exposed to the agent.

    Feeds TraceEvent.sections_returned, from which required-information coverage is computed. That
    computation is order-agnostic, which is the whole point of spec section 13: we never require a
    fixed tool-call sequence.
    """
    if "error" in result:
        return []
    if tool == "get_document_section":
        return [result["section_id"]]
    if tool == "search_document":
        return [r["section_id"] for r in result.get("results", [])]
    if tool == "list_document_sections":
        # Listing titles is discovery, not consulting content, so it grants no coverage.
        return []
    return []


def rules_returned(tool: str, result: dict[str, Any]) -> list[str]:
    if "error" in result or tool != "lookup_policy":
        return []
    return [r["rule_id"] for r in result.get("rules", [])]
