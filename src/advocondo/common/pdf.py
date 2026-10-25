"""Builds simple PDF documents (title, label/value sections and tables) with ReportLab.

The document is described with plain data (`PdfDocument`), so each story only
decides what goes in it: the agreement PDF (US24) today, the Client report (US39)
later.
"""

import io
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Flowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PDF_CONTENT_TYPE = "application/pdf"

HEADER_BACKGROUND = colors.HexColor("#E8ECF1")
GRID_COLOR = colors.HexColor("#B8C0CC")
# Long values (an address) wrap inside their cell.
VALUE_STYLE = ParagraphStyle("value", fontName="Helvetica", fontSize=10, leading=12)
LABEL_STYLE = ParagraphStyle("label", parent=VALUE_STYLE, fontName="Helvetica-Bold")


@dataclass(frozen=True)
class PdfSection:
    """A titled list of "label: value" lines."""

    title: str
    rows: Sequence[tuple[str, str]]


@dataclass(frozen=True)
class PdfTable:
    title: str
    header: Sequence[str]
    rows: Sequence[Sequence[str]]
    # Optional last line in bold, such as a total.
    footer: Sequence[str] | None = None


@dataclass(frozen=True)
class PdfDocument:
    title: str
    subtitle: str = ""
    blocks: Sequence[PdfSection | PdfTable] = field(default_factory=tuple)


def format_money(value: Decimal) -> str:
    """5500 -> "R$ 5.500,00", as the front shows it."""
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def format_date(value: date) -> str:
    return value.strftime("%d/%m/%Y")


def render_pdf(document: PdfDocument) -> bytes:
    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    template = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        title=document.title,
        author="Advocondo",
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )
    story: list[Flowable] = [Paragraph(_text(document.title), styles["Title"])]
    if document.subtitle:
        story.append(Paragraph(_text(document.subtitle), styles["Normal"]))
    for block in document.blocks:
        story.append(Spacer(1, 0.5 * cm))
        story.append(Paragraph(_text(block.title), styles["Heading2"]))
        if isinstance(block, PdfSection):
            story.append(_section_table(block))
        else:
            story.append(_data_table(block))
    template.build(story)
    return buffer.getvalue()


def _text(value: str) -> str:
    """Paragraph reads a small markup language, so <, > and & must be escaped."""
    return escape(value)


def _section_table(section: PdfSection) -> Table:
    rows = [
        [Paragraph(_text(label), LABEL_STYLE), Paragraph(_text(value), VALUE_STYLE)]
        for label, value in section.rows
    ]
    table = Table(rows, colWidths=[5 * cm, None], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return table


def _data_table(data: PdfTable) -> Table:
    rows = [list(data.header), *(list(row) for row in data.rows)]
    if data.footer is not None:
        rows.append(list(data.footer))
    # The header repeats at the top of every page when the table breaks.
    table = Table(rows, repeatRows=1, hAlign="LEFT")
    style = TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), HEADER_BACKGROUND),
            ("GRID", (0, 0), (-1, -1), 0.5, GRID_COLOR),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
        ]
    )
    if data.footer is not None:
        style.add("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold")
    table.setStyle(style)
    return table
