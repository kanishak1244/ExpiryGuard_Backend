"""
Script to parse TECH_MAP.md and compile it into a publication-quality PDF
named TECH_MAP.pdf using ReportLab 5.0.
"""

import os
import re
import html
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
    KeepTogether,
    Preformatted,
)

BASE_DIR = Path(__file__).resolve().parent.parent
MD_PATH = BASE_DIR / "TECH_MAP.md"
PDF_PATH = BASE_DIR / "TECH_MAP.pdf"


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and stamp total page count:
    'Page X of Y' in the running footer, plus running headers.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, total_pages):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        # Skip running header on cover/first page
        if self._pageNumber > 1:
            # Running Header
            self.drawString(40, 805, "DawaiFlow (ExpiryGuard) — Technical Architecture & Product Map")
            self.drawRightString(A4[0] - 40, 805, "Confidential — For Internal Leadership")
            self.setStrokeColor(colors.HexColor("#cbd5e1"))
            self.setLineWidth(0.5)
            self.line(40, 798, A4[0] - 40, 798)

        # Running Footer (on all pages)
        self.setStrokeColor(colors.HexColor("#e2e8f0"))
        self.setLineWidth(0.5)
        self.line(40, 45, A4[0] - 40, 45)

        self.drawString(40, 32, "DawaiFlow Pharmacy OS • Comprehensive Technical Architecture Map")
        page_str = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(A4[0] - 40, 32, page_str)
        self.restoreState()


def clean_markdown_inline(text: str) -> str:
    """
    Escapes raw XML entities and converts markdown bold, italic, inline code, and links
    to ReportLab-supported XML tags.
    """
    if not text:
        return ""

    # Normalize literal ampersand first (not already part of an entity)
    text = re.sub(r"&(?!(amp|lt|gt|quot|apos);)", "&amp;", text)
    # Escape angle brackets
    text = text.replace("<", "&lt;").replace(">", "&gt;")

    # Convert code blocks `code`
    text = re.sub(r"`([^`]+)`", r'<font face="Courier" color="#0369a1"><b>\1</b></font>', text)

    # Convert links [label](url) -> label (with color)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r'<font color="#0f766e"><u>\1</u></font>', text)

    # Convert bold **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)

    # Convert italic *text*
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)

    return text


def build_pdf():
    if not MD_PATH.exists():
        print(f"Error: {MD_PATH} not found.")
        return

    raw_text = MD_PATH.read_text(encoding="utf-8")
    lines = raw_text.splitlines()

    doc = SimpleDocTemplate(
        str(PDF_PATH),
        pagesize=A4,
        leftMargin=40,
        rightMargin=40,
        topMargin=50,
        bottomMargin=55,
    )

    printable_width = A4[0] - 80  # 595.27 - 80 = 515.27

    # Base Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "DocTitle",
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#0f3d2e"),
        spaceAfter=6,
    )

    subtitle_style = ParagraphStyle(
        "DocSubtitle",
        fontName="Helvetica-Oblique",
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#475569"),
        spaceAfter=12,
    )

    h1_style = ParagraphStyle(
        "Heading1_Custom",
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#065f46"),
        spaceBefore=16,
        spaceAfter=8,
        keepWithNext=True,
    )

    h2_style = ParagraphStyle(
        "Heading2_Custom",
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=15,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=12,
        spaceAfter=6,
        keepWithNext=True,
    )

    h3_style = ParagraphStyle(
        "Heading3_Custom",
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#334155"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True,
    )

    body_style = ParagraphStyle(
        "Body_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=5,
    )

    bullet_style = ParagraphStyle(
        "Bullet_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
        leftIndent=15,
        firstLineIndent=-10,
        spaceAfter=3,
    )

    blockquote_style = ParagraphStyle(
        "Blockquote_Custom",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#0f5132"),
        backColor=colors.HexColor("#ecfdf5"),
        borderColor=colors.HexColor("#10b981"),
        borderWidth=1,
        borderPadding=6,
        spaceBefore=6,
        spaceAfter=8,
    )

    code_line_style = ParagraphStyle(
        "CodeLine_Custom",
        fontName="Courier",
        fontSize=7,
        leading=9.2,
        textColor=colors.HexColor("#0f172a"),
    )

    table_cell_style = ParagraphStyle(
        "TableCell_Custom",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1e293b"),
    )

    table_header_style = ParagraphStyle(
        "TableHeader_Custom",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10.5,
        textColor=colors.white,
    )

    flowables = []

    in_code_block = False
    code_block_lines = []
    code_block_lang = ""

    in_table = False
    table_rows = []

    def flush_table():
        nonlocal table_rows, in_table
        if not table_rows:
            in_table = False
            return

        col_count = max(len(row) for row in table_rows)
        # Pad shorter rows
        for row in table_rows:
            while len(row) < col_count:
                row.append("")

        # Determine column widths based on column count
        if col_count == 4:
            # Tech Stack table: Name, Job, Why, Where
            col_widths = [printable_width * 0.18, printable_width * 0.30, printable_width * 0.32, printable_width * 0.20]
        elif col_count == 5:
            # Risks table: Risk, Severity, Explanation, Impact, Solution
            col_widths = [printable_width * 0.20, printable_width * 0.10, printable_width * 0.26, printable_width * 0.22, printable_width * 0.22]
        else:
            w = printable_width / col_count
            col_widths = [w] * col_count

        processed_table_data = []
        for row_idx, row in enumerate(table_rows):
            processed_row = []
            is_header = (row_idx == 0)
            style_to_use = table_header_style if is_header else table_cell_style
            for cell_text in row:
                formatted = clean_markdown_inline(cell_text.strip())
                processed_row.append(Paragraph(formatted, style_to_use))
            processed_table_data.append(processed_row)

        t = Table(processed_table_data, colWidths=col_widths, repeatRows=1)
        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#065f46")),
            ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
            ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#065f46")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
        # Alternate row backgrounds
        for r_i in range(1, len(processed_table_data)):
            bg = colors.HexColor("#f8fafc") if r_i % 2 == 1 else colors.white
            t_style.append(("BACKGROUND", (0, r_i), (-1, r_i), bg))

        t.setStyle(TableStyle(t_style))
        flowables.append(Spacer(1, 4))
        flowables.append(t)
        flowables.append(Spacer(1, 8))
        table_rows = []
        in_table = False

    def flush_code_block():
        nonlocal code_block_lines, in_code_block, code_block_lang
        if not code_block_lines:
            in_code_block = False
            return

        # Render code block in a framed light-grey container
        code_paragraphs = []
        for cl in code_block_lines:
            # Escape XML entities for code
            escaped = html.escape(cl).replace(" ", "&nbsp;")
            code_paragraphs.append([Paragraph(escaped if escaped else "&nbsp;", code_line_style)])

        col_w = [printable_width]
        code_table = Table(code_paragraphs, colWidths=col_w)
        code_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
            ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))

        flowables.append(Spacer(1, 4))
        flowables.append(code_table)
        flowables.append(Spacer(1, 8))

        code_block_lines = []
        in_code_block = False
        code_block_lang = ""

    i = 0
    total_lines = len(lines)
    while i < total_lines:
        line = lines[i]

        # 1. Code blocks (```)
        if line.startswith("```"):
            if not in_code_block:
                if in_table:
                    flush_table()
                in_code_block = True
                code_block_lang = line[3:].strip()
                code_block_lines = []
            else:
                flush_code_block()
            i += 1
            continue

        if in_code_block:
            code_block_lines.append(line)
            i += 1
            continue

        stripped = line.strip()

        # 2. Markdown Table Detection
        if stripped.startswith("|") and stripped.endswith("|"):
            # Check if separator row like | :--- | :--- |
            if re.match(r"^\|(\s*:?-+:?\s*\|)+$", stripped):
                # Skip separator line
                i += 1
                continue
            cells = [c for c in stripped.split("|")[1:-1]]
            table_rows.append(cells)
            in_table = True
            i += 1
            continue
        else:
            if in_table:
                flush_table()

        # 3. Blank line
        if not stripped:
            i += 1
            continue

        # 4. Horizontal Rule
        if stripped in ("---", "***", "___"):
            flowables.append(Spacer(1, 4))
            flowables.append(HRFlowable(width="100%", thickness=0.75, color=colors.HexColor("#cbd5e1"), spaceAfter=8, spaceBefore=4))
            i += 1
            continue

        # 5. Headings
        if line.startswith("# "):
            title_text = clean_markdown_inline(line[2:])
            flowables.append(Paragraph(title_text, title_style))
            flowables.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#065f46"), spaceAfter=10, spaceBefore=2))
            i += 1
            continue

        if line.startswith("## "):
            h1_text = clean_markdown_inline(line[3:])
            flowables.append(Paragraph(h1_text, h1_style))
            flowables.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#059669"), spaceAfter=6, spaceBefore=2))
            i += 1
            continue

        if line.startswith("### "):
            h2_text = clean_markdown_inline(line[4:])
            flowables.append(Paragraph(h2_text, h2_style))
            i += 1
            continue

        if line.startswith("#### "):
            h3_text = clean_markdown_inline(line[5:])
            flowables.append(Paragraph(h3_text, h3_style))
            i += 1
            continue

        # 6. Blockquote (> ...)
        if stripped.startswith("> "):
            bq_text = clean_markdown_inline(stripped[2:])
            flowables.append(Paragraph(bq_text, blockquote_style))
            i += 1
            continue

        # 7. Unordered Lists (* item, - item)
        bullet_match = re.match(r"^(\s*)[*\-]\s+(.*)$", line)
        if bullet_match:
            indent = len(bullet_match.group(1))
            item_text = clean_markdown_inline(bullet_match.group(2))
            b_style = ParagraphStyle(
                f"Bullet_{indent}",
                parent=bullet_style,
                leftIndent=15 + indent * 8,
            )
            flowables.append(Paragraph(f"&bull;&nbsp;&nbsp;{item_text}", b_style))
            i += 1
            continue

        # 8. Ordered Lists (1. item)
        num_match = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if num_match:
            indent = len(num_match.group(1))
            num_str = num_match.group(2)
            item_text = clean_markdown_inline(num_match.group(3))
            n_style = ParagraphStyle(
                f"Num_{indent}",
                parent=bullet_style,
                leftIndent=15 + indent * 8,
            )
            flowables.append(Paragraph(f"<b>{num_str}.</b>&nbsp;&nbsp;{item_text}", n_style))
            i += 1
            continue

        # 9. Standard Paragraph Body Text
        p_text = clean_markdown_inline(stripped)
        flowables.append(Paragraph(p_text, body_style))
        i += 1

    if in_table:
        flush_table()
    if in_code_block:
        flush_code_block()

    print(f"Compiling PDF with {len(flowables)} flowable elements...")
    doc.build(flowables, canvasmaker=NumberedCanvas)
    print(f"SUCCESS: PDF created at {PDF_PATH}")


if __name__ == "__main__":
    build_pdf()
