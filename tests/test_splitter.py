"""Splitter tests.

Offsets are the foundation of the evidence invariants S2 and S3, so they are tested at character
precision. If the splitter is wrong, every evidence metric in the experiment is wrong.
"""

from __future__ import annotations

from agent.tools.splitter import duplicate_section_ids, split_document

DOC = (
    "# MASTER SERVICES AGREEMENT\n"
    "\n"
    "## 1. Definitions\n"
    "Terms have their ordinary meaning.\n"
    "\n"
    "## 4.1 Payment Terms\n"
    "Customer shall pay all invoices within 60 days of receipt.\n"
    "\n"
    "## 8.2 Liability\n"
    "Liability of either party is unlimited.\n"
)


def test_title_and_section_ids():
    doc = split_document(DOC)
    assert doc.title == "MASTER SERVICES AGREEMENT"
    assert doc.section_ids == ("1", "4.1", "8.2")


def test_body_offsets_are_exact():
    doc = split_document(DOC)
    for section in doc.sections:
        assert DOC[section.char_start : section.char_end] == section.body


def test_body_excludes_its_own_heading():
    doc = split_document(DOC)
    section = doc.section("4.1")
    assert "Payment Terms" not in section.body
    assert "within 60 days" in section.body


def test_last_section_runs_to_end_of_document():
    doc = split_document(DOC)
    assert doc.section("8.2").char_end == len(DOC)


def test_sections_do_not_overlap():
    doc = split_document(DOC)
    spans = [(s.char_start, s.char_end) for s in doc.sections]
    for (_, end), (start, _) in zip(spans, spans[1:]):
        assert end <= start


def test_quote_offsets_resolve_inside_the_owning_section():
    """The exact operation an evidence check performs."""
    doc = split_document(DOC)
    quote = "within 60 days"
    start = DOC.index(quote)
    end = start + len(quote)
    assert DOC[start:end] == quote
    assert doc.section_at(start).section_id == "4.1"
    assert doc.section("4.1").contains(start, end)


def test_prose_line_starting_with_hashes_is_not_a_section():
    text = "## 1. Real\nbody\n## not a numbered heading\nmore body\n"
    doc = split_document(text)
    assert doc.section_ids == ("1",)
    assert "## not a numbered heading" in doc.section("1").body


def test_crlf_offsets_are_not_normalised():
    """Offsets are measured against stored bytes, so line endings must pass through untouched."""
    text = "# T\r\n\r\n## 2.1 X\r\nalpha beta\r\n"
    doc = split_document(text)
    section = doc.section("2.1")
    assert text[section.char_start : section.char_end] == section.body
    assert "\r\n" in section.body


def test_document_with_no_sections():
    doc = split_document("# Title only\n\nSome prose.\n")
    assert doc.sections == ()
    assert doc.section("1") is None


def test_duplicate_section_ids_are_detected():
    doc = split_document("## 1. A\nx\n## 1. B\ny\n")
    assert duplicate_section_ids(doc) == ["1"]
