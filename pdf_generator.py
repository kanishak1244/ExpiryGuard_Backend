import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


def number_to_words(number: float) -> str:
    """Helper to convert rupee amount to words for Indian Invoice standards."""
    try:
        units = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
        teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
        tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

        def _num_to_words(n):
            if n == 0:
                return ""
            elif n < 10:
                return units[n]
            elif n < 20:
                return teens[n - 10]
            elif n < 100:
                return tens[n // 10] + (" " + units[n % 10] if n % 10 != 0 else "")
            elif n < 1000:
                return units[n // 100] + " Hundred" + (" " + _num_to_words(n % 100) if n % 100 != 0 else "")
            elif n < 100000:
                return _num_to_words(n // 1000) + " Thousand" + (" " + _num_to_words(n % 1000) if n % 1000 != 0 else "")
            elif n < 10000000:
                return _num_to_words(n // 100000) + " Lakh" + (" " + _num_to_words(n % 100000) if n % 100000 != 0 else "")
            else:
                return _num_to_words(n // 10000000) + " Crore" + (" " + _num_to_words(n % 10000000) if n % 10000000 != 0 else "")

        rupees = int(number)
        paise = int(round((number - rupees) * 100))

        words = _num_to_words(rupees)
        if not words:
            words = "Zero"
        res = f"Rupees {words}"
        if paise > 0:
            res += f" and {_num_to_words(paise)} Paise"
        res += " Only"
        return res
    except Exception:
        return f"Rupees {number:.2f} Only"


def generate_invoice_pdf(sale_data: dict, shop_data: dict) -> bytes:
    """
    Generates a professional, GST-compliant Indian Retail Pharmacy Invoice PDF using ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20,
    )

# Pre-cached styles for high-speed PDF generation
_BASE_STYLES = getSampleStyleSheet()
_TITLE_STYLE = ParagraphStyle(
    'DocTitle',
    parent=_BASE_STYLES['Heading1'],
    fontName='Helvetica-Bold',
    fontSize=16,
    leading=18,
    textColor=colors.HexColor("#1b5e20"),
    alignment=1, # Center
)
_SUBTITLE_STYLE = ParagraphStyle(
    'SubTitle',
    parent=_BASE_STYLES['Normal'],
    fontName='Helvetica',
    fontSize=9,
    leading=12,
    alignment=1,
    textColor=colors.HexColor("#424242"),
)
_SECTION_HEADING = ParagraphStyle(
    'SectionHeading',
    parent=_BASE_STYLES['Heading3'],
    fontName='Helvetica-Bold',
    fontSize=10,
    leading=12,
    textColor=colors.HexColor("#2e7d32"),
)
_NORMAL_STYLE = ParagraphStyle(
    'Norm',
    parent=_BASE_STYLES['Normal'],
    fontName='Helvetica',
    fontSize=8,
    leading=10,
)
_BOLD_STYLE = ParagraphStyle(
    'BoldNorm',
    parent=_BASE_STYLES['Normal'],
    fontName='Helvetica-Bold',
    fontSize=8,
    leading=10,
)
_TABLE_CELL = ParagraphStyle(
    'TableCell',
    parent=_BASE_STYLES['Normal'],
    fontName='Helvetica',
    fontSize=7.5,
    leading=9,
)
_TABLE_CELL_BOLD = ParagraphStyle(
    'TableCellBold',
    parent=_BASE_STYLES['Normal'],
    fontName='Helvetica-Bold',
    fontSize=7.5,
    leading=9,
)


def generate_invoice_pdf(sale_data: dict, shop_data: dict) -> bytes:
    """
    Generates a professional, GST-compliant Indian Retail Pharmacy Invoice PDF using ReportLab.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20,
    )

    title_style = _TITLE_STYLE
    subtitle_style = _SUBTITLE_STYLE
    section_heading = _SECTION_HEADING
    normal_style = _NORMAL_STYLE
    bold_style = _BOLD_STYLE
    table_cell = _TABLE_CELL
    table_cell_bold = _TABLE_CELL_BOLD

    story = []

    # 1. Shop Header & GSTIN
    shop_name = shop_data.get("shop_name") or "ExpiryGuard Pharmacy"
    gstin = shop_data.get("gstin") or shop_data.get("gst_number") or "07AABCE1234F1Z5"
    address = shop_data.get("address") or "Main Market, New Delhi - 110001"
    phone = shop_data.get("phone") or "+91-9876543210"

    story.append(Paragraph(f"<b>{shop_name.upper()}</b>", title_style))
    story.append(Paragraph(f"{address} | Ph: {phone}", subtitle_style))
    story.append(Paragraph(f"<b>GSTIN: {gstin}</b>", subtitle_style))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2e7d32"), spaceBefore=2, spaceAfter=6))
    story.append(Paragraph("<b>TAX INVOICE / RETAIL BILL</b>", ParagraphStyle('CenterBold', parent=bold_style, alignment=1, fontSize=11)))
    story.append(Spacer(1, 6))

    # 2. Bill & Customer Metadata Table
    bill_no = sale_data.get("bill_number") or "BILL-1001"
    date_str = sale_data.get("created_at") or datetime.now().strftime("%d-%m-%Y %H:%M")
    if isinstance(date_str, datetime):
        date_str = date_str.strftime("%d-%m-%Y %H:%M")
    cust_name = sale_data.get("customer_name") or "Cash Customer"
    cust_phone = sale_data.get("customer_phone") or "-"
    payment_mode = sale_data.get("payment_method") or "CASH"
    doc_name = sale_data.get("doctor_name") or "-"
    doc_reg = sale_data.get("doctor_reg_no")
    doc_display = f"Dr. {doc_name}" if doc_name != "-" else "-"
    if doc_reg and doc_display != "-":
        doc_display += f" (Reg: {doc_reg})"

    meta_info = [
        [
            Paragraph(f"<b>Invoice No:</b> {bill_no}", normal_style),
            Paragraph(f"<b>Date:</b> {date_str}", normal_style),
        ],
        [
            Paragraph(f"<b>Customer Name:</b> {cust_name}", normal_style),
            Paragraph(f"<b>Customer Phone:</b> {cust_phone}", normal_style),
        ],
        [
            Paragraph(f"<b>Payment Method:</b> {payment_mode}", normal_style),
            Paragraph(f"<b>Prescribed By:</b> {doc_display}", normal_style),
        ],
    ]
    meta_table = Table(meta_info, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#f1f8e9")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#c8e6c9")),
        ('PADDING', (0,0), (-1,-1), 4),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 10))

    # 3. Full Line-Item Table
    items = sale_data.get("items") or []
    is_interstate = sale_data.get("is_interstate", False)

    if is_interstate:
        headers = ["S.No", "Product / Medicine", "HSN", "Qty", "Rate (₹)", "Taxable (₹)", "IGST %", "IGST (₹)", "Total (₹)"]
        col_widths = [25, 175, 45, 30, 50, 55, 45, 50, 65]
    else:
        headers = ["S.No", "Product / Medicine", "HSN", "Qty", "Rate (₹)", "Taxable (₹)", "CGST %", "CGST (₹)", "SGST %", "SGST (₹)", "Total (₹)"]
        col_widths = [22, 140, 40, 26, 45, 50, 38, 42, 38, 42, 57]

    table_data = [[Paragraph(f"<b>{h}</b>", table_cell_bold) for h in headers]]

    for idx, item in enumerate(items, 1):
        p_name = item.get("product_name") or item.get("product", {}).get("product_name", "Item")
        hsn = item.get("hsn_code") or "3004"
        qty = item.get("quantity") or 1
        rate = float(item.get("unit_price") or 0.0)
        taxable = float(item.get("taxable_value") or (rate * qty - float(item.get("discount") or 0)))
        total_item = float(item.get("total_with_tax") or item.get("total_price") or taxable)
        gst_pct = float(item.get("gst_percentage") or 12.0)

        if is_interstate:
            igst_amt = float(item.get("igst_amount") or (total_item - taxable))
            row = [
                Paragraph(str(idx), table_cell),
                Paragraph(p_name, table_cell),
                Paragraph(hsn, table_cell),
                Paragraph(str(qty), table_cell),
                Paragraph(f"{rate:.2f}", table_cell),
                Paragraph(f"{taxable:.2f}", table_cell),
                Paragraph(f"{gst_pct:.1f}%", table_cell),
                Paragraph(f"{igst_amt:.2f}", table_cell),
                Paragraph(f"{total_item:.2f}", table_cell),
            ]
        else:
            cgst_rate = float(item.get("cgst_rate") or (gst_pct / 2.0))
            sgst_rate = float(item.get("sgst_rate") or (gst_pct / 2.0))
            cgst_amt = float(item.get("cgst_amount") or round(taxable * (cgst_rate / 100), 2))
            sgst_amt = float(item.get("sgst_amount") or round(taxable * (sgst_rate / 100), 2))

            row = [
                Paragraph(str(idx), table_cell),
                Paragraph(p_name, table_cell),
                Paragraph(hsn, table_cell),
                Paragraph(str(qty), table_cell),
                Paragraph(f"{rate:.2f}", table_cell),
                Paragraph(f"{taxable:.2f}", table_cell),
                Paragraph(f"{cgst_rate:.1f}%", table_cell),
                Paragraph(f"{cgst_amt:.2f}", table_cell),
                Paragraph(f"{sgst_rate:.1f}%", table_cell),
                Paragraph(f"{sgst_amt:.2f}", table_cell),
                Paragraph(f"{total_item:.2f}", table_cell),
            ]
        table_data.append(row)

    items_table = Table(table_data, colWidths=col_widths)
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#e8f5e9")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#bdbdbd")),
        ('PADDING', (0,0), (-1,-1), 3),
        ('ALIGN', (3,0), (-1,-1), 'RIGHT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10))

    # 4. Tax Summary Table (Grouped by GST Rate)
    story.append(Paragraph("<b>Tax Summary Table (GST Compliance)</b>", section_heading))
    story.append(Spacer(1, 4))

    tax_summary = sale_data.get("tax_summary") or []
    if not tax_summary:
        # Compute tax summary dynamically if not passed directly
        rate_groups = {}
        for item in items:
            rate = float(item.get("gst_percentage") or 12.0)
            taxable = float(item.get("taxable_value") or 0.0)
            cgst = float(item.get("cgst_amount") or 0.0)
            sgst = float(item.get("sgst_amount") or 0.0)
            igst = float(item.get("igst_amount") or 0.0)

            if rate not in rate_groups:
                rate_groups[rate] = {"gst_rate": rate, "taxable_value": 0.0, "cgst_amount": 0.0, "sgst_amount": 0.0, "igst_amount": 0.0, "total_tax": 0.0}
            rate_groups[rate]["taxable_value"] += taxable
            rate_groups[rate]["cgst_amount"] += cgst
            rate_groups[rate]["sgst_amount"] += sgst
            rate_groups[rate]["igst_amount"] += igst
            rate_groups[rate]["total_tax"] += (cgst + sgst + igst)
        tax_summary = list(rate_groups.values())

    if is_interstate:
        tax_headers = ["GST Rate %", "Taxable Value (₹)", "IGST Amount (₹)", "Total Tax (₹)"]
        tax_widths = [120, 140, 140, 140]
        tax_rows = [[Paragraph(f"<b>{th}</b>", table_cell_bold) for th in tax_headers]]
        for ts in tax_summary:
            r = float(ts.get("gst_rate") or 0)
            tv = float(ts.get("taxable_value") or 0)
            igst = float(ts.get("igst_amount") or 0)
            tot_tax = float(ts.get("total_tax") or igst)
            tax_rows.append([
                Paragraph(f"{r:.1f}%", table_cell),
                Paragraph(f"{tv:.2f}", table_cell),
                Paragraph(f"{igst:.2f}", table_cell),
                Paragraph(f"{tot_tax:.2f}", table_cell),
            ])
    else:
        tax_headers = ["GST Rate %", "Taxable Value (₹)", "CGST Amount (₹)", "SGST Amount (₹)", "Total Tax (₹)"]
        tax_widths = [90, 115, 115, 115, 105]
        tax_rows = [[Paragraph(f"<b>{th}</b>", table_cell_bold) for th in tax_headers]]
        for ts in tax_summary:
            r = float(ts.get("gst_rate") or 0)
            tv = float(ts.get("taxable_value") or 0)
            cgst = float(ts.get("cgst_amount") or 0)
            sgst = float(ts.get("sgst_amount") or 0)
            tot_tax = float(ts.get("total_tax") or (cgst + sgst))
            tax_rows.append([
                Paragraph(f"{r:.1f}%", table_cell),
                Paragraph(f"{tv:.2f}", table_cell),
                Paragraph(f"{cgst:.2f}", table_cell),
                Paragraph(f"{sgst:.2f}", table_cell),
                Paragraph(f"{tot_tax:.2f}", table_cell),
            ])

    tax_table = Table(tax_rows, colWidths=tax_widths)
    tax_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#fff3e0")),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor("#ffe0b2")),
        ('PADDING', (0,0), (-1,-1), 3),
        ('ALIGN', (1,0), (-1,-1), 'RIGHT'),
    ]))
    story.append(tax_table)
    story.append(Spacer(1, 10))

    # 5. Grand Totals & Amount in Words
    total_taxable = float(sale_data.get("total_taxable_value") or sale_data.get("subtotal") or 0.0)
    total_tax = float(sale_data.get("tax_amount") or 0.0)
    grand_total = float(sale_data.get("total_amount") or 0.0)

    summary_info = [
        [Paragraph("<b>Total Taxable Value:</b>", normal_style), Paragraph(f"₹ {total_taxable:.2f}", normal_style)],
        [Paragraph("<b>Total Tax (GST):</b>", normal_style), Paragraph(f"₹ {total_tax:.2f}", normal_style)],
        [Paragraph("<b>Grand Total:</b>", ParagraphStyle('Gt', parent=bold_style, fontSize=10)), Paragraph(f"<b>₹ {grand_total:.2f}</b>", ParagraphStyle('GtVal', parent=bold_style, fontSize=10))],
    ]
    sum_table = Table(summary_info, colWidths=[380, 160])
    sum_table.setStyle(TableStyle([
        ('ALIGN', (1,0), (1,-1), 'RIGHT'),
        ('LINEABOVE', (0,2), (-1,2), 1, colors.HexColor("#1b5e20")),
        ('PADDING', (0,0), (-1,-1), 3),
    ]))
    story.append(sum_table)
    story.append(Spacer(1, 6))

    amount_words = number_to_words(grand_total)
    story.append(Paragraph(f"<b>Amount in Words:</b> {amount_words}", bold_style))
    story.append(Spacer(1, 12))

    # 6. Terms & Signature Footer
    terms = [
        Paragraph("<b>Terms & Conditions:</b><br/>1. Goods once sold will not be taken back.<br/>2. Scheduled drugs sold only on valid registered practitioner prescription.", ParagraphStyle('Tiny', parent=normal_style, fontSize=7, leading=8)),
        Paragraph("For <b>{}</b><br/><br/><br/>Authorized Signatory".format(shop_name), ParagraphStyle('RightBold', parent=bold_style, alignment=2, fontSize=8)),
    ]
    terms_table = Table([terms], colWidths=[340, 200])
    terms_table.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
    story.append(terms_table)

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
