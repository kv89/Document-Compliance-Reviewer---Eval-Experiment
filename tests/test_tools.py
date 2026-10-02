"""Tool contract tests.

The contract under test: tools never raise, failures arrive as data with recovery hints, and reads
are pure. Those three properties are what make Layer 3 and Layer 5 measurable rather than
inferable.
"""

from __future__ import annotations

import pytest

from agent.schemas.loaders import load_policy
from agent.tools.toolset import ToolSet, rules_returned, sections_returned

DOC = (
    "# MASTER SERVICES AGREEMENT\n"
    "\n"
    "## 4.1 Payment Terms\n"
    "Customer shall pay all invoices within 60 days of receipt.\n"
    "\n"
    "## 8.2 Liability\n"
    "Liability of either party is unlimited and uncapped.\n"
)


@pytest.fixture
def tools() -> ToolSet:
    return ToolSet(DOC, load_policy("POL-001"))


def test_list_sections_is_discovery_only(tools):
    out = tools.list_document_sections()
    assert [s["section_id"] for s in out["sections"]] == ["4.1", "8.2"]
    assert "body" not in out["sections"][0]


def test_get_section_returns_citable_offsets(tools):
    out = tools.get_document_section("4.1")
    assert DOC[out["char_start"] : out["char_end"]] == out["body"]


def test_get_section_tolerates_surrounding_whitespace(tools):
    assert tools.get_document_section(" 4.1 ")["section_id"] == "4.1"


def test_unknown_section_returns_recovery_hint(tools):
    out = tools.get_document_section("99")
    assert out["error"] == "UNKNOWN_SECTION"
    assert out["valid_section_ids"] == ["4.1", "8.2"]


def test_empty_section_id_is_an_argument_error(tools):
    assert tools.get_document_section("  ")["error"] == "INVALID_ARGUMENTS"


def test_search_substring_offsets_are_exact(tools):
    hit = tools.search_document("within 60 days")["results"][0]
    assert hit["section_id"] == "4.1"
    assert hit["score"] == 1.0
    assert DOC[hit["char_start"] : hit["char_end"]] == "within 60 days"


def test_search_is_case_insensitive(tools):
    assert tools.search_document("LIABILITY")["match_count"] >= 1


def test_search_falls_back_to_token_overlap(tools):
    """No substring match, but the tokens are present. Partial score, not a miss."""
    out = tools.search_document("uncapped liability")
    assert out["results"][0]["section_id"] == "8.2"
    assert 0 < out["results"][0]["score"] < 1.0


def test_search_miss_returns_empty_not_error(tools):
    out = tools.search_document("zzzz")
    assert out["match_count"] == 0 and "error" not in out


def test_search_ordering_is_deterministic(tools):
    first = tools.search_document("liability payment terms")
    for _ in range(5):
        assert tools.search_document("liability payment terms") == first


def test_lookup_policy_by_rule_id(tools):
    out = tools.lookup_policy(rule_id="VALUE-PAY-001")
    assert out["rules"][0]["params"]["value"] == 45


def test_lookup_policy_by_clause_returns_every_matching_rule(tools):
    ids = {r["rule_id"] for r in tools.lookup_policy(clause="Payment Terms")["rules"]}
    assert ids == {"CLAUSE-PAY-001", "VALUE-PAY-001"}


def test_lookup_policy_requires_an_argument(tools):
    out = tools.lookup_policy()
    assert out["error"] == "INVALID_ARGUMENTS"
    assert "VALUE-PAY-001" in out["valid_rule_ids"]


def test_unknown_rule_lists_valid_rule_ids(tools):
    out = tools.lookup_policy(rule_id="VALUE-PAY-999")
    assert out["error"] == "UNKNOWN_RULE"
    assert len(out["valid_rule_ids"]) == 5


def test_unauthorized_tool_is_refused_as_data(tools):
    out = tools.call("get_full_document")
    assert out["error"] == "UNAUTHORIZED_TOOL"
    assert "get_full_document" not in out["authorized_tools"]


def test_dispatch_never_raises_on_bad_arguments(tools):
    assert tools.call("search_document", {"wrong_kwarg": "x"})["error"] == "INVALID_ARGUMENTS"
    assert tools.call("get_document_section", {})["error"] == "INVALID_ARGUMENTS"


def test_call_log_records_success_and_failure(tools):
    tools.call("list_document_sections")
    tools.call("get_document_section", {"section_id": "99"})
    assert [ok for _, _, ok in tools.call_log] == [True, False]


def test_tools_do_not_mutate_the_document(tools):
    before = DOC
    tools.call("search_document", {"query": "liability"})
    tools.call("get_document_section", {"section_id": "4.1"})
    assert DOC == before


def test_coverage_attribution(tools):
    """list_document_sections grants no content coverage; reading and searching do."""
    assert sections_returned("list_document_sections", tools.list_document_sections()) == []
    assert sections_returned("get_document_section", tools.get_document_section("4.1")) == ["4.1"]
    assert sections_returned("search_document", tools.search_document("liability")) == ["8.2"]
    assert sections_returned("get_document_section", tools.get_document_section("99")) == []


def test_rule_attribution(tools):
    assert rules_returned("lookup_policy", tools.lookup_policy(rule_id="ENUM-LAW-001")) == [
        "ENUM-LAW-001"
    ]
    assert rules_returned("lookup_policy", tools.lookup_policy(rule_id="nope")) == []


def test_exact_substring_outranks_full_token_overlap(tools):
    """Regression: both paths once scored 1.0, which made ranking arbitrary."""
    out = tools.search_document("uncapped liability")
    assert out["results"][0]["score"] == 0.9
