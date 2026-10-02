"""Deterministic section splitter for plain-text documents.

This is a splitter, not a document parser. Documents are plain text by design decision (spec
section 3.2): there is no PDF, no DOCX and no Docling dependency. A heavyweight parser whose input
was already structured would have added an untested link in which parse errors get scored as agent
errors.

Document format:

    # DOCUMENT TITLE

    ## 4.1 Payment Terms
    body text

Heading rule: a line starting with `## ` followed by a numeric section identifier and a title.
A single `# ` line is the document title and is not a section.

All offsets are character indices into the document string exactly as stored on disk. Evidence
checks S2 and S3 compare against these, so the splitter must never normalise whitespace, line
endings or case.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `## 4.1 Payment Terms` -> ("4.1", "Payment Terms"). The identifier is digits and dots only, so
#: a prose line that happens to start with ## cannot be mistaken for a section.
_HEADING = re.compile(r"^##[ \t]+(?P<section_id>\d+(?:\.\d+)*)[.)]?[ \t]+(?P<title>\S.*?)[ \t]*$")
_TITLE = re.compile(r"^#[ \t]+(?P<title>\S.*?)[ \t]*$")


@dataclass(frozen=True)
class Section:
    """One document section.

    `char_start` and `char_end` bound the body only. Evidence quotes come from the body, so
    bounding the heading as well would let a quote of the heading pass a body containment check.
    """

    section_id: str
    title: str
    body: str
    char_start: int
    char_end: int
    heading_start: int
    heading_end: int

    def contains(self, start: int, end: int) -> bool:
        return self.char_start <= start and end <= self.char_end


@dataclass(frozen=True)
class ParsedDocument:
    title: str
    sections: tuple[Section, ...]
    text: str

    def section(self, section_id: str) -> Section | None:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None

    @property
    def section_ids(self) -> tuple[str, ...]:
        return tuple(s.section_id for s in self.sections)

    def section_at(self, offset: int) -> Section | None:
        """Which section a character offset falls in. Used by search result attribution."""
        for s in self.sections:
            if s.char_start <= offset < s.char_end:
                return s
        return None


def split_document(text: str) -> ParsedDocument:
    """Split a document into sections. Pure function, no I/O, no mutation."""
    doc_title = ""
    headings: list[tuple[str, str, int, int]] = []  # section_id, title, heading_start, heading_end

    offset = 0
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\r\n")
        heading = _HEADING.match(stripped)
        if heading:
            headings.append(
                (
                    heading.group("section_id"),
                    heading.group("title"),
                    offset,
                    offset + len(stripped),
                )
            )
        elif not doc_title:
            title = _TITLE.match(stripped)
            if title:
                doc_title = title.group("title")
        offset += len(line)

    sections: list[Section] = []
    for i, (section_id, title, h_start, h_end) in enumerate(headings):
        body_start = h_end
        # Body runs to the start of the next heading, or to the end of the document.
        body_end = headings[i + 1][2] if i + 1 < len(headings) else len(text)
        sections.append(
            Section(
                section_id=section_id,
                title=title,
                body=text[body_start:body_end],
                char_start=body_start,
                char_end=body_end,
                heading_start=h_start,
                heading_end=h_end,
            )
        )

    return ParsedDocument(title=doc_title, sections=tuple(sections), text=text)


def duplicate_section_ids(doc: ParsedDocument) -> list[str]:
    """Duplicate identifiers would make get_document_section ambiguous.

    The generator asserts this is empty for every generated case.
    """
    seen: set[str] = set()
    dupes: list[str] = []
    for s in doc.sections:
        if s.section_id in seen:
            dupes.append(s.section_id)
        seen.add(s.section_id)
    return dupes
