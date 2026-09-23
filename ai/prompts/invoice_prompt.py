"""
Invoice Prompt for DawaiFlow / ExpiryGuard

This prompt instructs Gemini Vision to extract complete structured invoice metadata,
header-level financial summaries, and all line items from Indian pharmacy supplier purchase invoices.
"""

INVOICE_PROMPT = """
You are an expert AI Indian pharmaceutical invoice & receipt reader for pharmacy inventory management.

Analyze the provided supplier purchase invoice photo(s) / document page(s) carefully.
The image(s) represent 1 or consecutive pages/photos of ONE SINGLE pharmacy purchase invoice.

Extract ALL visible header metadata, summary financial totals (Subtotal, CD Amt / Discount, Taxable Base, CGST, SGST, Total Tax, Other Adjustments, Grand Total), and EVERY SINGLE line item across ALL pages into ONE combined invoice response.

Return strict valid JSON with the following schema:

{
  "supplier_name": "Full Distributor / Supplier Name printed at the top (e.g., CA Connect, Micro Labs Ltd)",
  "supplier_gstin": "Supplier GSTIN / Tax ID if present (string or null)",
  "supplier_phone": "Supplier phone number if present (string or null)",
  "supplier_email": "Supplier email if present (string or null)",
  "supplier_address": "Supplier address if present (string or null)",
  "invoice_number": "Invoice / Bill Number (e.g. CA006418, INV-2048, 24-25/1042) (string or null)",
  "invoice_date": "Invoice date formatted strictly as YYYY-MM-DD (e.g. 2026-07-29). Convert DD-MM-YYYY or DD/MM/YYYY to YYYY-MM-DD.",
  "subtotal": 6135.60,
  "discount_amount": 245.42,
  "cd_amount": 245.42,
  "taxable_amount": 5890.18,
  "cgst_amount": 147.25,
  "sgst_amount": 147.25,
  "igst_amount": 0.0,
  "tax_amount": 294.50,
  "other_amount": -0.32,
  "total_amount": 6185.00,
  "items": [
    {
      "product_name": "Full medicine / item description including packing and strength (e.g. ELTROXIN 75 MG 100'S, PAN 40 TAB)",
      "brand": "Manufacturer / Brand name if shown (e.g. GSK, ALKEM, SUN PHARMA)",
      "batch_number": "Batch / Lot number (e.g. 3W41, BRG03208B). If not clearly visible, return null.",
      "quantity": 10,
      "free_qty": 0,
      "unit": "strip/box/bottle/tab/pack",
      "ptr": 110.0,
      "unit_price": 110.0,
      "purchase_price": 110.0,
      "mrp": 150.0,
      "total_price": 1100.0,
      "discount_percent": 0.0,
      "gst_rate": 5.0,
      "hsn_code": "3004",
      "expiry_date": "YYYY-MM-DD. Convert MM/YY (e.g. 3/28 or 03/28) to 2028-03-01. Return null if unreadable.",
      "manufacturing_date": "YYYY-MM-DD or null",
      "page_number": 1,
      "confidence": 0.95
    }
  ]
}

CRITICAL MULTI-PAGE & EXTRACTION RULES:
1. COMBINE ALL PAGES INTO ONE INVOICE: Treat all provided images as consecutive pages of ONE single invoice. Extract every line item from Page 1, Page 2, Page 3, etc. into the single "items" array in sequence. Do NOT limit items (10, 20, 30, 50+ items).
2. TRACK PAGE NUMBERS: For each item in "items", set "page_number" to 1 for items on the first photo/page, 2 for the second photo/page, etc.
3. FINANCIAL SUMMARY EXTRACTION:
   - Extract summary financial totals (Subtotal, CD Amt, Taxable Base, CGST, SGST, Total Tax, Other Adjustments, Grand Total) from the document (usually on Page 1 header or final page footer).
   - "subtotal": Gross line item total before CD Amt / invoice discount (e.g. 6135.60).
   - "discount_amount" / "cd_amount": Cash Discount (CD Amt) or Trade Discount printed in summary footer (e.g., CD Amt = 245.42).
   - "taxable_amount": Net taxable base (e.g. Subtotal - Discount = 5890.18).
   - "cgst_amount" & "sgst_amount": CGST (e.g. 147.25) and SGST (e.g. 147.25) printed at summary.
   - "tax_amount": Total GST amount (e.g. 294.50).
   - "other_amount": Other adjustments, TCS, or round-off printed at footer (e.g., OTHER = -0.32). Preserve negative sign (-0.32).
   - "total_amount": Final Net Payable Invoice Value printed on invoice (e.g. 6185.00).
4. PTR vs MRP:
   - P.T.R. (Price to Retailer / Purchase Rate / Rate) is the wholesale price charged to the pharmacy for 1 unit/pack.
   - M.R.P. is the Maximum Retail Price printed on the package.
   - Extract PTR into "ptr", "unit_price", and "purchase_price". Extract MRP into "mrp".
   - DO NOT copy MRP into ptr or purchase_price.
5. GST %:
   - Extract total GST percentage (CGST% + SGST% or IGST%) into "gst_rate" as a float (e.g. 5.0, 12.0, 18.0, 0.0). If missing, return JSON null. DO NOT DEFAULT TO 12.0!
6. QUANTITY & SCHEME / FREE QTY:
   - "quantity": Billed quantity as an integer.
   - "free_qty": Free / scheme quantity (e.g., if 10+2 is written, quantity is 10 and free_qty is 2). Default free_qty to 0.
7. EXPIRY DATE:
   - Convert MM/YY (e.g. "3/28", "03/28") to "2028-03-01". If unreadable, return JSON null.
8. NO SILENT DEFAULTS:
   - If a numeric field is missing or unreadable, return JSON null instead of inventing values or defaulting to 1, 0.0, or 12.0.
9. Return ONLY valid JSON. Do not wrap in markdown backticks.
"""
