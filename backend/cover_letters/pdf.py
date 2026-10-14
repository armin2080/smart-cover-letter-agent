"""Server-side PDF rendering for cover letters (ReportLab).

The client downloads the result of ``GET /api/cover-letters/{id}/pdf/`` as a
binary blob, so this returns raw PDF bytes.
"""

from __future__ import annotations

import re
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "cover-letter"


def filename_for(company: str, job_title: str) -> str:
    """Download filename, e.g. ``cover-letter-morrow-senior-ux-designer.pdf``."""

    return f"cover-letter-{_slug(company)}-{_slug(job_title)}.pdf"


def render_pdf(
    *,
    content: str,
    company: str = "",
    job_title: str = "",
    candidate_name: str = "",
    contact_lines: list[str] | None = None,
) -> bytes:
    """Render a cover letter to PDF bytes."""

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"{job_title} — {company}".strip(" —") or "Cover letter",
        author=candidate_name or "Smart Cover Letter Agent",
    )

    heading_style = ParagraphStyle(
        "CoverHeading",
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        spaceAfter=2,
    )
    contact_style = ParagraphStyle(
        "CoverContact",
        fontName="Times-Roman",
        fontSize=9.5,
        leading=13,
        textColor="#475467",
    )
    subject_style = ParagraphStyle(
        "CoverSubject",
        fontName="Times-Bold",
        fontSize=11.5,
        leading=16,
        spaceBefore=10,
    )
    body_style = ParagraphStyle(
        "CoverBody",
        fontName="Times-Roman",
        fontSize=11,
        leading=16.5,
        alignment=TA_JUSTIFY,
        spaceAfter=9,
    )

    story = []

    if candidate_name:
        story.append(Paragraph(escape(candidate_name), heading_style))

    for line in contact_lines or []:
        if line:
            story.append(Paragraph(escape(line), contact_style))

    if candidate_name or contact_lines:
        story.append(Spacer(1, 8 * mm))

    if job_title and company:
        story.append(Paragraph(escape(f"Application for {job_title} — {company}"), subject_style))
        story.append(Spacer(1, 4 * mm))

    # Split into paragraphs so ReportLab can paginate and justify properly.
    paragraphs = [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]
    for block in paragraphs:
        # Preserve single newlines as line breaks inside a paragraph.
        text = "<br/>".join(escape(line) for line in block.splitlines())
        story.append(Paragraph(text, body_style))

    if not paragraphs:
        story.append(Paragraph("(This cover letter is empty.)", body_style))

    document.build(story)
    return buffer.getvalue()


def safe_paragraph(content: str) -> list[str]:
    """Expose paragraph splitting for callers that need it (e.g. previews)."""

    return [block.strip() for block in re.split(r"\n\s*\n", content) if block.strip()]


__all__ = ["render_pdf", "filename_for", "safe_paragraph", "KeepTogether"]
