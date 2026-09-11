import io
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side, Protection
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule
from openpyxl.drawing.image import Image as OpenPyxlImage

try:
    from PIL import Image as PILImage, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


def _create_infographic_image_bytes() -> io.BytesIO:
    """Generates an embedded PNG infographic for the 'How to Fill' guide sheet."""
    width, height = 1080, 520
    image = PILImage.new("RGB", (width, height), color="#0F172A") # Dark Slate Navy background
    draw = ImageDraw.Draw(image)

    try:
        font_title = ImageFont.truetype("arial.ttf", 22)
        font_header = ImageFont.truetype("arialbd.ttf", 16)
        font_body = ImageFont.truetype("arial.ttf", 12.5)
        font_body_bold = ImageFont.truetype("arialbd.ttf", 13)
    except IOError:
        font_title = font_header = font_body = font_body_bold = ImageFont.load_default()

    # Main Title Header Banner
    draw.rectangle([0, 0, width, 60], fill="#0F766E") # Emerald Teal Header
    draw.text((25, 18), "ExpiryGuard - Bulk Inventory Import Quick Reference Guide", fill="#FFFFFF", font=font_title)

    # Card 1: WHAT YOU NEED TO ADD (Green Border Card)
    draw.rounded_rectangle([25, 80, 525, 495], radius=12, fill="#1E293B", outline="#10B981", width=2)
    draw.rounded_rectangle([25, 80, 525, 125], radius=12, fill="#065F46")
    draw.rectangle([25, 105, 525, 125], fill="#065F46")
    draw.text((40, 93), "YES - WHAT YOU NEED TO ADD (Required)", fill="#ECFDF5", font=font_header)

    items_do = [
        ("Medicine Name *", "Full brand or generic name (e.g. Dolo 650mg Tablet)"),
        ("Batch Number *", "Unique batch ID printed on pack (e.g. DL7820)"),
        ("Expiry Date *", "Format strictly as DD-MM-YYYY (e.g. 30-11-2027)"),
        ("Pack Size Label *", "Packaging description (e.g. 10 Tablets)"),
        ("Stock Quantity *", "Number of full packs available (e.g. 50)"),
        ("Purchase Price *", "Net purchase rate per pack in RS (e.g. 18.50)"),
        ("MRP *", "Maximum Retail Price printed on pack (e.g. 33.60)")
    ]

    y_pos = 140
    for label, desc in items_do:
        draw.text((40, y_pos), label, fill="#34D399", font=font_body_bold)
        draw.text((180, y_pos), desc, fill="#F8FAFC", font=font_body)
        y_pos += 48

    # Card 2: WHAT NOT TO DO (Red Border Card)
    draw.rounded_rectangle([555, 80, 1055, 495], radius=12, fill="#1E293B", outline="#EF4444", width=2)
    draw.rounded_rectangle([555, 80, 1055, 125], radius=12, fill="#991B1B")
    draw.rectangle([555, 105, 1055, 125], fill="#991B1B")
    draw.text((570, 93), "NO - WHAT NOT TO DO (Avoid Mistakes)", fill="#FEF2F2", font=font_header)

    items_dont = [
        ("Header Column Names", "Do NOT rename, delete, or reorder column headers"),
        ("Currency Symbols", "Do NOT type RS or symbol inside numeric price cells"),
        ("Invalid Date Formats", "Do NOT use US format MM/DD/YYYY or month text"),
        ("Blank Required Cells", "Do NOT leave any required (*) cell empty"),
        ("Negative Numbers", "Do NOT enter negative stock quantities or prices"),
        ("Sample Data Rows", "Do NOT upload sample/example medicines in Data sheet"),
        ("Multiple Batches", "One medicine & batch combination per row only!")
    ]

    y_pos = 140
    for label, desc in items_dont:
        draw.text((570, y_pos), label, fill="#F87171", font=font_body_bold)
        draw.text((730, y_pos), desc, fill="#F8FAFC", font=font_body)
        y_pos += 48

    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)
    return img_byte_arr


def generate_inventory_import_template() -> io.BytesIO:
    """
    Generates a clean, professional, directly-fillable Excel form template
    for ExpiryGuard bulk inventory onboarding, preserving 100% backend compatibility.

    Sheets:
    1. 'Data': Active data-entry sheet containing 12 exact columns, header formatting,
       visual required/optional indicators in header comments & background fills,
       data validation rules, and 600 preformatted blank data rows.
    2. 'How to Fill': Visual instruction guide sheet with required/optional cards,
       what NOT to do section, visual example table, embedded infographic, legend,
       and upload instructions.
    3. 'Example': Dedicated reference sheet showing example rows clearly marked as
       EXAMPLE ONLY - DO NOT UPLOAD.
    """
    wb = openpyxl.Workbook()

    # Define unified color palette & typography
    FONT_FAMILY = "Calibri"
    BRAND_TEAL = "0F766E"         # Deep Teal Accent
    BRAND_DARK_NAVY = "0F172A"    # Main Header Navy
    SLATE_HEADER_BG = "1E293B"    # Section Header Background
    REQUIRED_HEADER_BG = "064E3B"  # Required Column Header Dark Emerald
    OPTIONAL_HEADER_BG = "334155"  # Optional Column Header Slate
    SLATE_LIGHT_BG = "F8FAFC"     # Alternating Row Tint
    BORDER_COLOR = "CBD5E1"       # Light Grid Border
    WARNING_BG = "FEF2F2"         # Light Red Alert Fill
    WARNING_BORDER = "FCA5A5"     # Red Alert Border
    WARNING_TEXT = "991B1B"       # Dark Red Alert Text
    SUCCESS_BG = "ECFDF5"         # Light Green Card Fill
    SUCCESS_BORDER = "6EE7B7"     # Green Card Border
    SUCCESS_TEXT = "065F46"       # Dark Green Card Text

    thin_border = Border(
        left=Side(style="thin", color=BORDER_COLOR),
        right=Side(style="thin", color=BORDER_COLOR),
        top=Side(style="thin", color=BORDER_COLOR),
        bottom=Side(style="thin", color=BORDER_COLOR),
    )

    header_border = Border(
        left=Side(style="thin", color=BORDER_COLOR),
        right=Side(style="thin", color=BORDER_COLOR),
        top=Side(style="thin", color=BORDER_COLOR),
        bottom=Side(style="medium", color=BRAND_TEAL),
    )

    # =========================================================================
    # SHEET 1: Data (Active Data-Entry Sheet by default)
    # =========================================================================
    ws_data = wb.active
    ws_data.title = "Data"
    ws_data.views.sheetView[0].showGridLines = True

    # Exact 12 columns required by backend importer
    data_columns = [
        ("medicine_name", 32, True, "Required. Full brand or generic medicine name (e.g. Dolo 650mg Tablet)."),
        ("manufacturer", 24, False, "Optional. Pharmaceutical manufacturer or brand owner (e.g. Micro Labs Ltd)."),
        ("hsn_code", 14, False, "Optional. 4-digit or 6-digit Indian GST HSN code (default: 3004)."),
        ("batch_no", 18, True, "Required. Unique Batch/Lot number printed on packaging (e.g. DL7820)."),
        ("mfd_date", 16, False, "Optional. Manufacturing date formatted strictly as DD-MM-YYYY."),
        ("expiry_date", 16, True, "Required. Expiry date formatted strictly as DD-MM-YYYY (must be future date)."),
        ("pack_size_label", 18, True, "Required. Packaging unit label (e.g. 10 Tablets, 100ml Bottle)."),
        ("quantity", 14, True, "Required. Total sealed packs available in stock (whole number > 0)."),
        ("purchase_price", 18, True, "Required. Net purchase rate per pack in INR (numeric value without symbol)."),
        ("mrp", 16, True, "Required. Maximum Retail Price printed on pack in INR (numeric value without symbol)."),
        ("gst_percent", 14, False, "Optional. GST rate slab (0, 5, 12, 18, 28). Defaults to 12% if left blank."),
        ("rack_location", 18, False, "Optional. Cabinet, shelf, or rack location identifier (e.g. Rack-A2)."),
    ]

    # Header Row (Row 1)
    ws_data.row_dimensions[1].height = 32
    for col_idx, (col_name, width, is_req, comment_text) in enumerate(data_columns, start=1):
        cell = ws_data.cell(row=1, column=col_idx, value=col_name)
        cell.font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
        
        # Visually distinguish required vs optional header backgrounds without altering exact text
        fill_color = REQUIRED_HEADER_BG if is_req else OPTIONAL_HEADER_BG
        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = header_border
        
        # Add Excel Cell Comment explaining field requirement & format
        comment = openpyxl.comments.Comment(
            text=f"{'REQUIRED ★' if is_req else 'OPTIONAL'}\n\n{comment_text}",
            author="ExpiryGuard"
        )
        comment.width = 220
        comment.height = 70
        cell.comment = comment

        ws_data.column_dimensions[get_column_letter(col_idx)].width = width

    # Freeze Header Row & Position Default Cursor at First Data Entry Cell (A2)
    ws_data.freeze_panes = "A2"
    ws_data.views.sheetView[0].selection[0].activeCell = "A2"
    ws_data.views.sheetView[0].selection[0].sqref = "A2"
    ws_data.auto_filter.ref = f"A1:L601"

    # Pre-format 600 blank data-entry rows (Rows 2 to 601)
    regular_font = Font(name=FONT_FAMILY, size=11, color="0F172A")
    for r in range(2, 602):
        ws_data.row_dimensions[r].height = 22
        is_even = (r % 2 == 0)
        row_fill = PatternFill(
            start_color="FFFFFF" if is_even else SLATE_LIGHT_BG,
            end_color="FFFFFF" if is_even else SLATE_LIGHT_BG,
            fill_type="solid"
        )
        
        for c in range(1, 13):
            cell = ws_data.cell(row=r, column=c)
            cell.font = regular_font
            cell.fill = row_fill
            cell.border = thin_border

            # Column specific formatting & alignment
            if c in [5, 6]:  # mfd_date, expiry_date
                cell.number_format = "DD-MM-YYYY"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c == 8:  # quantity
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c in [9, 10]:  # purchase_price, mrp
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c in [3, 4, 11]:  # hsn_code, batch_no, gst_percent
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    # Data Validation Rules for Data Sheet
    # 1. GST Percent Dropdown Validation (0, 5, 12, 18, 28)
    gst_dv = DataValidation(
        type="list",
        formula1='"0,5,12,18,28"',
        allow_blank=True,
        showInputMessage=True,
        showErrorMessage=True,
    )
    gst_dv.error = "Please select a valid GST slab: 0, 5, 12, 18, or 28%."
    gst_dv.errorTitle = "Invalid GST Slab"
    gst_dv.prompt = "Select official GST rate slab (0%, 5%, 12%, 18%, 28%)."
    gst_dv.promptTitle = "GST Slab Selection"
    ws_data.add_data_validation(gst_dv)
    gst_dv.add("K2:K601")

    # 2. Quantity Validation (Whole number > 0)
    qty_dv = DataValidation(
        type="whole",
        operator="greaterThan",
        formula1=0,
        allow_blank=True,
        showErrorMessage=True,
    )
    qty_dv.error = "Quantity must be a positive whole number greater than 0."
    qty_dv.errorTitle = "Invalid Quantity"
    ws_data.add_data_validation(qty_dv)
    qty_dv.add("H2:H601")

    # 3. Purchase Price Validation (Decimal > 0)
    pp_dv = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1=0,
        allow_blank=True,
        showErrorMessage=True,
    )
    pp_dv.error = "Purchase price must be a positive numeric value in INR."
    pp_dv.errorTitle = "Invalid Purchase Price"
    ws_data.add_data_validation(pp_dv)
    pp_dv.add("I2:I601")

    # 4. MRP Validation (Decimal > 0)
    mrp_dv = DataValidation(
        type="decimal",
        operator="greaterThan",
        formula1=0,
        allow_blank=True,
        showErrorMessage=True,
    )
    mrp_dv.error = "MRP must be a positive numeric value in INR."
    mrp_dv.errorTitle = "Invalid MRP"
    ws_data.add_data_validation(mrp_dv)
    mrp_dv.add("J2:J601")

    # Conditional Formatting: Soft highlight for expired date cells if date < TODAY()
    red_fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")
    red_font = Font(name=FONT_FAMILY, size=10.5, color="991B1B", bold=True)
    ws_data.conditional_formatting.add(
        "F2:F601",
        CellIsRule(operator="lessThan", formula=["TODAY()"], fill=red_fill, font=red_font)
    )

    # Ensure Data sheet is fully unlocked and unprotected for seamless pharmacist editing & pasting
    ws_data.protection.sheet = False

    # =========================================================================
    # SHEET 2: How to Fill (Visual Pharmacist User Guide)
    # =========================================================================
    ws_guide = wb.create_sheet(title="How to Fill")
    ws_guide.views.sheetView[0].showGridLines = True

    # 1. Main Title Banner (Merged A1:F2)
    ws_guide.merge_cells("A1:F2")
    title_cell = ws_guide["A1"]
    title_cell.value = "ExpiryGuard — How to Fill Your Inventory Template"
    title_cell.font = Font(name=FONT_FAMILY, size=16, bold=True, color="FFFFFF")
    title_cell.fill = PatternFill(start_color=BRAND_TEAL, end_color=BRAND_TEAL, fill_type="solid")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")

    ws_guide.row_dimensions[1].height = 24
    ws_guide.row_dimensions[2].height = 24

    # Subtitle
    ws_guide["A4"].value = "Follow this quick visual guide to prepare your Excel file before uploading to ExpiryGuard."
    ws_guide["A4"].font = Font(name=FONT_FAMILY, size=11, bold=True, color=BRAND_DARK_NAVY)
    ws_guide.row_dimensions[4].height = 20

    # 2. Legend Box Section (Row 6 to 9)
    ws_guide.merge_cells("A6:F6")
    leg_header = ws_guide["A6"]
    leg_header.value = "FIELD LEGEND & REQUIREMENT GUIDE"
    leg_header.font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    leg_header.fill = PatternFill(start_color=SLATE_HEADER_BG, end_color=SLATE_HEADER_BG, fill_type="solid")
    leg_header.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_guide.row_dimensions[6].height = 24

    legend_rows = [
        ("★ Required Column", "Must be filled for every medicine row. Cannot be left blank.", "Dark Green Header"),
        ("Optional Column", "Can be left blank if unknown. Importer will apply standard pharmacy defaults.", "Slate Gray Header"),
        ("🟢 Valid Entry", "Numbers formatted as plain decimals (18.50), dates formatted as DD-MM-YYYY.", "Standard Format"),
    ]

    for idx, (sym, desc, note) in enumerate(legend_rows, start=7):
        ws_guide.row_dimensions[idx].height = 22
        bg = PatternFill(start_color=SLATE_LIGHT_BG if idx % 2 == 0 else "FFFFFF", end_color=SLATE_LIGHT_BG if idx % 2 == 0 else "FFFFFF", fill_type="solid")
        
        c1 = ws_guide.cell(row=idx, column=1, value=sym)
        c1.font = Font(name=FONT_FAMILY, size=10.5, bold=True, color=BRAND_DARK_NAVY)
        c1.fill = bg
        c1.border = thin_border
        c1.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        ws_guide.merge_cells(start_row=idx, start_column=2, end_row=idx, end_column=4)
        c2 = ws_guide.cell(row=idx, column=2, value=desc)
        c2.font = Font(name=FONT_FAMILY, size=10, color="334155")
        c2.fill = bg
        c2.border = thin_border
        c2.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        ws_guide.merge_cells(start_row=idx, start_column=5, end_row=idx, end_column=6)
        c3 = ws_guide.cell(row=idx, column=5, value=note)
        c3.font = Font(name=FONT_FAMILY, size=10, italic=True, color="64748B")
        c3.fill = bg
        c3.border = thin_border
        c3.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # 3. Card Section: WHAT YOU NEED TO ADD (Rows 11 to 19)
    ws_guide.merge_cells("A11:F11")
    add_header = ws_guide["A11"]
    add_header.value = "✅ WHAT YOU NEED TO ADD (Required Fields)"
    add_header.font = Font(name=FONT_FAMILY, size=11, bold=True, color=SUCCESS_TEXT)
    add_header.fill = PatternFill(start_color=SUCCESS_BG, end_color=SUCCESS_BG, fill_type="solid")
    add_header.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_guide.row_dimensions[11].height = 24

    req_fields_guide = [
        ("★ medicine_name", "Dolo 650mg Tablet", "Brand or generic medicine name as sold at counter."),
        ("★ batch_no", "DL7820", "Unique batch number printed on box or strip."),
        ("★ expiry_date", "30-11-2027", "Expiry date formatted as DD-MM-YYYY (must be future date)."),
        ("★ pack_size_label", "10 Tablets", "Packaging unit description (e.g. '10 Tablets', '100ml Bottle')."),
        ("★ quantity", "50", "Total sealed packs / strips available in stock (number > 0)."),
        ("★ purchase_price", "18.50", "Net purchase rate per pack in INR (numeric value only)."),
        ("★ mrp", "33.60", "Maximum Retail Price printed on pack in INR (numeric value only)."),
    ]

    for idx, (fname, ex_val, explain) in enumerate(req_fields_guide, start=12):
        ws_guide.row_dimensions[idx].height = 22
        bg = PatternFill(start_color=SUCCESS_BG if idx % 2 == 0 else "FFFFFF", end_color=SUCCESS_BG if idx % 2 == 0 else "FFFFFF", fill_type="solid")
        
        c1 = ws_guide.cell(row=idx, column=1, value=fname)
        c1.font = Font(name=FONT_FAMILY, size=10.5, bold=True, color=SUCCESS_TEXT)
        c1.fill = bg
        c1.border = thin_border
        c1.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        c2 = ws_guide.cell(row=idx, column=2, value=ex_val)
        c2.font = Font(name=FONT_FAMILY, size=10, italic=True, bold=True, color="0F172A")
        c2.fill = bg
        c2.border = thin_border
        c2.alignment = Alignment(horizontal="center", vertical="center")

        ws_guide.merge_cells(start_row=idx, start_column=3, end_row=idx, end_column=6)
        c3 = ws_guide.cell(row=idx, column=3, value=explain)
        c3.font = Font(name=FONT_FAMILY, size=10, color="334155")
        c3.fill = bg
        c3.border = thin_border
        c3.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # 4. Optional Fields Section (Rows 21 to 27)
    ws_guide.merge_cells("A21:F21")
    opt_header = ws_guide["A21"]
    opt_header.value = "🟢 OPTIONAL INFORMATION (Fill if available, or leave blank)"
    opt_header.font = Font(name=FONT_FAMILY, size=11, bold=True, color="1E293B")
    opt_header.fill = PatternFill(start_color=SLATE_LIGHT_BG, end_color=SLATE_LIGHT_BG, fill_type="solid")
    opt_header.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_guide.row_dimensions[21].height = 24

    opt_fields_guide = [
        ("manufacturer", "Micro Labs Ltd", "Pharmaceutical manufacturer or brand owner name."),
        ("hsn_code", "3004", "4-digit or 6-digit Indian HSN code (defaults to 3004 if blank)."),
        ("mfd_date", "15-01-2026", "Manufacturing date formatted as DD-MM-YYYY."),
        ("gst_percent", "12", "Applicable GST slab: 0, 5, 12, 18, or 28 (defaults to 12% if blank)."),
        ("rack_location", "Rack-A2 / Shelf-3", "Pharmacy storage cabinet, shelf, or rack identifier."),
    ]

    for idx, (fname, ex_val, explain) in enumerate(opt_fields_guide, start=22):
        ws_guide.row_dimensions[idx].height = 22
        bg = PatternFill(start_color=SLATE_LIGHT_BG if idx % 2 == 0 else "FFFFFF", end_color=SLATE_LIGHT_BG if idx % 2 == 0 else "FFFFFF", fill_type="solid")
        
        c1 = ws_guide.cell(row=idx, column=1, value=fname)
        c1.font = Font(name=FONT_FAMILY, size=10.5, bold=True, color="334155")
        c1.fill = bg
        c1.border = thin_border
        c1.alignment = Alignment(horizontal="left", vertical="center", indent=1)

        c2 = ws_guide.cell(row=idx, column=2, value=ex_val)
        c2.font = Font(name=FONT_FAMILY, size=10, italic=True, color="475569")
        c2.fill = bg
        c2.border = thin_border
        c2.alignment = Alignment(horizontal="center", vertical="center")

        ws_guide.merge_cells(start_row=idx, start_column=3, end_row=idx, end_column=6)
        c3 = ws_guide.cell(row=idx, column=3, value=explain)
        c3.font = Font(name=FONT_FAMILY, size=10, color="475569")
        c3.fill = bg
        c3.border = thin_border
        c3.alignment = Alignment(horizontal="left", vertical="center", indent=1)

    # 5. Section: WHAT NOT TO ADD (Rows 29 to 38)
    ws_guide.merge_cells("A29:F29")
    dont_header = ws_guide["A29"]
    dont_header.value = "❌ WHAT NOT TO ADD (Avoid Common Errors)"
    dont_header.font = Font(name=FONT_FAMILY, size=11, bold=True, color=WARNING_TEXT)
    dont_header.fill = PatternFill(start_color=WARNING_BG, end_color=WARNING_BG, fill_type="solid")
    dont_header.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_guide.row_dimensions[29].height = 24

    dont_items = [
        "❌ Do NOT rename, remove, or reorder column header names in the 'Data' sheet.",
        "❌ Do NOT type currency symbols like '₹' or 'Rs' inside purchase_price or mrp numeric cells.",
        "❌ Do NOT enter dates in US format (MM/DD/YYYY) or text format (e.g. 'Nov 2027'). Use DD-MM-YYYY.",
        "❌ Do NOT leave required columns (medicine_name, batch_no, expiry_date, etc.) empty.",
        "❌ Do NOT enter negative numbers for stock quantity or prices.",
        "❌ Do NOT upload sample/dummy medicine rows in the 'Data' sheet as actual inventory.",
        "❌ Do NOT merge cells or add extra title headings inside the 'Data' sheet table.",
        "❌ Note: Every medicine batch must occupy its own separate row.",
    ]

    for idx, rule_text in enumerate(dont_items, start=30):
        ws_guide.merge_cells(start_row=idx, start_column=1, end_row=idx, end_column=6)
        c = ws_guide.cell(row=idx, column=1, value=rule_text)
        c.font = Font(name=FONT_FAMILY, size=10, color="7F1D1D")
        c.fill = PatternFill(start_color=WARNING_BG, end_color=WARNING_BG, fill_type="solid")
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        c.border = thin_border
        ws_guide.row_dimensions[idx].height = 21

    # 6. Embedded Infographic Image (Rows 40 to 60)
    if HAS_PIL:
        try:
            img_buf = _create_infographic_image_bytes()
            img = OpenPyxlImage(img_buf)
            img.width = 750
            img.height = 360
            ws_guide.add_image(img, "A40")
            
            # Add breathing height space for rows occupied by image
            for r_img in range(40, 61):
                ws_guide.row_dimensions[r_img].height = 18
        except Exception:
            pass

    # 7. Upload Instructions Section (Rows 62 to 69)
    upload_start = 62
    ws_guide.merge_cells(start_row=upload_start, start_column=1, end_row=upload_start, end_column=6)
    up_header = ws_guide.cell(row=upload_start, column=1, value="🚀 HOW TO UPLOAD YOUR COMPLETED FILE")
    up_header.font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
    up_header.fill = PatternFill(start_color=BRAND_DARK_NAVY, end_color=BRAND_DARK_NAVY, fill_type="solid")
    up_header.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws_guide.row_dimensions[upload_start].height = 26

    steps = [
        "1. Switch to the 'Data' sheet (first sheet at the bottom).",
        "2. Fill in your inventory medicines row by row starting from Row 2.",
        "3. Check that all ★ required columns (medicine_name, batch_no, expiry_date, quantity, prices) are completed.",
        "4. Save this Excel file on your computer.",
        "5. Go to ExpiryGuard Web App -> Add Inventory -> Bulk Import.",
        "6. Upload your saved Excel file to instantly import all stock!",
    ]

    for idx, step_text in enumerate(steps, start=upload_start + 1):
        ws_guide.merge_cells(start_row=idx, start_column=1, end_row=idx, end_column=6)
        c = ws_guide.cell(row=idx, column=1, value=step_text)
        c.font = Font(name=FONT_FAMILY, size=10, bold=True, color="0F172A")
        c.fill = PatternFill(start_color=SLATE_LIGHT_BG, end_color=SLATE_LIGHT_BG, fill_type="solid")
        c.alignment = Alignment(horizontal="left", vertical="center", indent=1)
        c.border = thin_border
        ws_guide.row_dimensions[idx].height = 22

    # Column widths for How to Fill sheet
    guide_col_widths = {1: 24, 2: 24, 3: 20, 4: 20, 5: 22, 6: 22}
    for col_idx, w in guide_col_widths.items():
        ws_guide.column_dimensions[get_column_letter(col_idx)].width = w

    ws_guide.protection.sheet = False

    # =========================================================================
    # SHEET 3: Example (Dedicated reference sheet with sample rows)
    # =========================================================================
    ws_ex = wb.create_sheet(title="Example")
    ws_ex.views.sheetView[0].showGridLines = True

    # Banner Header (Row 1 to 2)
    ws_ex.merge_cells("A1:L2")
    ex_title = ws_ex["A1"]
    ex_title.value = "EXAMPLE ONLY — DO NOT UPLOAD THIS SHEET (REFERENCE GUIDE)"
    ex_title.font = Font(name=FONT_FAMILY, size=14, bold=True, color="FFFFFF")
    ex_title.fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")
    ex_title.alignment = Alignment(horizontal="center", vertical="center")
    ws_ex.row_dimensions[1].height = 22
    ws_ex.row_dimensions[2].height = 22

    # Explanation Subtitle (Row 4)
    ws_ex["A4"].value = "This sheet shows correctly formatted sample medicine rows. Copy/reference format here, but enter actual stock in the 'Data' sheet."
    ws_ex["A4"].font = Font(name=FONT_FAMILY, size=10.5, italic=True, color="7F1D1D")
    ws_ex.row_dimensions[4].height = 20

    # Table Header (Row 6)
    ws_ex.row_dimensions[6].height = 28
    for col_idx, (col_name, width, is_req, _) in enumerate(data_columns, start=1):
        cell = ws_ex.cell(row=6, column=col_idx, value=col_name)
        cell.font = Font(name=FONT_FAMILY, size=11, bold=True, color="FFFFFF")
        fill_color = REQUIRED_HEADER_BG if is_req else OPTIONAL_HEADER_BG
        cell.fill = PatternFill(start_color=fill_color, end_color=fill_color, fill_type="solid")
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = header_border
        ws_ex.column_dimensions[get_column_letter(col_idx)].width = width

    # Sample Data Rows (Rows 7 to 9)
    example_data_rows = [
        ["Augmentin 625 Duo Tablet", "GlaxoSmithKline", "3004", "AUG8921", "10-01-2026", "31-08-2027", "1x10 Tablets", 40, 142.50, 204.80, 12, "Rack-A1"],
        ["Pan 40 Tablet", "Alkem Laboratories", "3004", "PN4401", "05-02-2026", "30-01-2028", "1x15 Tablets", 100, 88.00, 155.00, 12, "Rack-B3"],
        ["Azee 500mg Tablet", "Cipla Ltd", "3004", "AZ5520", "12-12-2025", "30-11-2027", "1x5 Tablets", 60, 71.20, 119.50, 12, "Rack-C2"],
    ]

    for row_idx, row_vals in enumerate(example_data_rows, start=7):
        ws_ex.row_dimensions[row_idx].height = 22
        for col_idx, val in enumerate(row_vals, start=1):
            cell = ws_ex.cell(row=row_idx, column=col_idx, value=val)
            cell.font = Font(name=FONT_FAMILY, size=10.5, color="334155")
            cell.fill = PatternFill(start_color=SLATE_LIGHT_BG, end_color=SLATE_LIGHT_BG, fill_type="solid")
            cell.border = thin_border

            if col_idx in [5, 6]:
                cell.number_format = "DD-MM-YYYY"
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif col_idx == 8:
                cell.number_format = "#,##0"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in [9, 10]:
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif col_idx in [3, 4, 11]:
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

    ws_ex.protection.sheet = False

    # Ensure 'Data' sheet is active by default upon opening workbook
    wb.active = 0

    # Save to BytesIO stream
    output_stream = io.BytesIO()
    wb.save(output_stream)
    output_stream.seek(0)
    return output_stream
