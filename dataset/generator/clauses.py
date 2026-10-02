"""Clause library and document rendering for the synthetic dataset.

Documents are built from a structured specification and rendered to plain text. Nothing is written
by hand, so every case has a known provenance and the whole dataset is reproducible from a seed
(spec section 9).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

DOCUMENT_TITLE = "MASTER SERVICES AGREEMENT"


@dataclass(frozen=True)
class SectionSpec:
    section_id: str
    title: str
    body: str


@dataclass(frozen=True)
class DocumentSpec:
    """A document before rendering.

    Section order is the order of the list, which is also the order in the rendered text. Keeping
    the identifiers non-sequential in places (4.1, 12.3) is deliberate: an agent must not be able
    to guess identifiers from position.
    """

    customer: str
    vendor: str
    payment_days: int
    jurisdiction: str
    notice_days: int
    sections: tuple[SectionSpec, ...]

    def without(self, section_id: str) -> "DocumentSpec":
        return replace(
            self, sections=tuple(s for s in self.sections if s.section_id != section_id)
        )

    def replacing(self, section_id: str, body: str) -> "DocumentSpec":
        return replace(
            self,
            sections=tuple(
                SectionSpec(s.section_id, s.title, body) if s.section_id == section_id else s
                for s in self.sections
            ),
        )

    def appending(self, section: SectionSpec) -> "DocumentSpec":
        return replace(self, sections=self.sections + (section,))

    def section(self, section_id: str) -> SectionSpec | None:
        for s in self.sections:
            if s.section_id == section_id:
                return s
        return None


# Section identifiers are fixed across the dataset so that ground truth can reference them.
SEC_PARTIES = "1"
SEC_DEFINITIONS = "2"
SEC_SERVICES = "3"
SEC_PAYMENT = "4.1"
SEC_CONFIDENTIALITY = "5"
SEC_TERMINATION = "6"
SEC_LIABILITY = "7"
SEC_GOVERNING_LAW = "8"
SEC_NOTICES = "9"
SEC_PAYMENT_SCHEDULE = "12.3"  # appended only by the contradiction mutation

CUSTOMERS = ("Northwind Industries", "Meridian Logistics", "Calder Foods", "Ashcroft Retail")
VENDORS = ("Blue Harbour Systems", "Tessellate Analytics", "Orbit Data Works", "Cedarline Tech")
APPROVED_JURISDICTIONS = ("India", "Singapore", "England and Wales")


def payment_body(days: int) -> str:
    return (
        f"Customer shall pay all undisputed invoices within {days} days of receipt. "
        "Invoices are issued monthly in arrears."
    )


def governing_law_body(jurisdiction: str) -> str:
    return (
        f"This Agreement is governed by the laws of {jurisdiction}, "
        "and the parties submit to the exclusive jurisdiction of its courts."
    )


def compliant_spec(customer: str, vendor: str, payment_days: int, jurisdiction: str,
                   notice_days: int) -> DocumentSpec:
    """A fully compliant base document. Every mutation is applied to a copy of this."""
    sections = (
        SectionSpec(
            SEC_PARTIES,
            "Parties and Scope",
            f"This Agreement is made between {customer} (the Customer) and "
            f"{vendor} (the Vendor) for the provision of managed services.",
        ),
        SectionSpec(
            SEC_DEFINITIONS,
            "Definitions",
            "Capitalised terms have the meaning given in Schedule 1. "
            "Business Day means a day other than a Saturday, Sunday or public holiday.",
        ),
        SectionSpec(
            SEC_SERVICES,
            "Services",
            "The Vendor shall provide the services described in Schedule 2 with reasonable "
            "skill and care, and shall meet the service levels set out in Schedule 3.",
        ),
        SectionSpec(SEC_PAYMENT, "Payment Terms", payment_body(payment_days)),
        SectionSpec(
            SEC_CONFIDENTIALITY,
            "Confidentiality",
            "Each party shall keep the other party's Confidential Information secret and "
            "shall not disclose it except to personnel who need to know it.",
        ),
        SectionSpec(
            SEC_TERMINATION,
            "Termination",
            f"Either party may terminate this Agreement for convenience by giving "
            f"{notice_days} days written notice. Either party may terminate immediately "
            "for material breach that remains uncured after 14 days.",
        ),
        SectionSpec(
            SEC_LIABILITY,
            "Liability",
            "The total aggregate liability of each party under this Agreement is limited to "
            "the total fees paid in the twelve months preceding the claim.",
        ),
        SectionSpec(SEC_GOVERNING_LAW, "Governing Law", governing_law_body(jurisdiction)),
        SectionSpec(
            SEC_NOTICES,
            "Notices",
            "Notices must be given in writing to the addresses set out in Schedule 4 and "
            "are deemed received on the next Business Day after delivery.",
        ),
    )
    return DocumentSpec(
        customer=customer,
        vendor=vendor,
        payment_days=payment_days,
        jurisdiction=jurisdiction,
        notice_days=notice_days,
        sections=sections,
    )


DISTRACTOR_SECTIONS = (
    SectionSpec(
        "20",
        "Travel and Expenses",
        "Vendor personnel travelling at the Customer's request shall book economy class fares "
        "and shall submit receipts within 30 days of the trip.",
    ),
    SectionSpec(
        "21",
        "Site Access and Parking",
        "Vendor personnel attending Customer premises shall register at reception and may use "
        "the visitor car park on level 2 subject to availability.",
    ),
    SectionSpec(
        "22",
        "Equipment Return",
        "On completion of the engagement the Vendor shall return all Customer laptops, access "
        "cards and hardware tokens within 10 days.",
    ),
)


def render(spec: DocumentSpec) -> str:
    """Render a document specification to plain text.

    The output format is what the splitter expects: one `# ` title line, then `## <id>. <title>`
    headings. Rendering is pure and stable, so the same specification always produces the same
    bytes and therefore the same character offsets.
    """
    parts = [f"# {DOCUMENT_TITLE}\n\n"]
    for section in spec.sections:
        # A top-level identifier takes a trailing dot ("## 6. Termination"); a sub-clause does not
        # ("## 4.1 Payment Terms"). Cosmetic only: the splitter accepts both.
        suffix = "." if "." not in section.section_id else ""
        parts.append(f"## {section.section_id}{suffix} {section.title}\n{section.body}\n\n")
    return "".join(parts)
