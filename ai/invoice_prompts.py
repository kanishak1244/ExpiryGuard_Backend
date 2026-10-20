"""
Invoice prompts for DawaiFlow / ExpiryGuard.

(Lives in ai/, NOT ai/prompts/: that folder is git-ignored, so production never received it and silently used an
inline copy of an older prompt.)

INVOICE_PROMPT        first reading: bill header, totals and the item table read ROW BY ROW.
INVOICE_VERIFY_PROMPT independent second reading (only run when the checks in ai/invoice_validation.py
                      flag a problem or the table is dense): reads the table COLUMN BY COLUMN and rebuilds the
                      rows, so a row/column slip in one reading is not repeated in the other.

The response shape is enforced by a JSON schema (see ai/invoice_service.py); these texts explain the reading
rules. Dates are returned exactly as printed; code converts them, so the model never "calculates" a date.
"""

_COMMON_RULES = """
TABLE READING RULES (most important):
1. Work ROW BY ROW. A row is ONE horizontal line of the item table, bounded by the grid lines of the bill.
   Copy values only from that row's own cells.
2. NEVER take a value from the row above or below. Boxed tables look similar line to line: use the grid lines.
   If a cell of THIS row is empty, blurred, cut off or hard to read, return null for that field and add the
   field name to "uncertain_fields". Do NOT look for the value in another row. Do NOT guess.
3. Decide each field by its COLUMN HEADER, not by how a value looks:
   - hsn_code: the HSN / HSN-SAC column. Digits only (4, 6 or 8 digits, usually 3004 or 3004xxxx). A date never
     belongs here.
   - batch_number: the Batch / Lot column. Letters and digits (e.g. 3W41, BRG03208B).
   - expiry_raw: the Expiry / Exp column, copied EXACTLY as printed (e.g. "03/28", "3/2028", "Mar-28"). Do not
     reformat or compute it.
   - quantity: billed quantity. free_qty: free / scheme quantity (for "10+2": quantity 10, free_qty 2), else 0.
   - purchase_price: PTR / Rate / Purchase rate. mrp: the M.R.P. column. NEVER copy one into the other, never
     compute MRP, and return null for mrp if the bill has no MRP column or the cell is empty.
   - discount_percent, gst_rate (total GST %: CGST+SGST or IGST), total_price (the printed line Amount / Value).
4. Copy printed numbers; do not recalculate. Remove currency symbols and commas from numbers.
5. Include EVERY item row of EVERY page, in order. Do not merge rows. Do not invent rows from the totals block.
6. rows_printed: the number of item rows you can see in the table(s) (count them separately from items).
7. Header and totals (supplier, invoice number, date, subtotal, discounts, taxes, total_amount): read them from
   the header and footer of the bill. total_amount ONLY from a net payable label (e.g. "Invoice Value Net", "Net
   Amount", "Grand Total", "Total Payable", "Bill Total"), never "Total MRP", balances or amount in words.
   invoice_date as YYYY-MM-DD. Use null for anything not printed.
8. No silent defaults: unreadable or absent means null (never 0, 1, 12 or a copy of another field).
"""

INVOICE_PROMPT = (
    """You are reading a supplier purchase invoice for an Indian pharmacy. The image(s) are consecutive pages or
photos of ONE invoice. Extract the header, the totals, and the item table into the required JSON.
"""
    + _COMMON_RULES
)

INVOICE_VERIFY_PROMPT = (
    """You are CHECKING a supplier purchase invoice for an Indian pharmacy (a second, independent reading). The
image(s) are consecutive pages or photos of ONE invoice. Extract the same JSON, but read the item table in a
different way:
  Step A: list every row by its serial number / medicine name, top to bottom, using the grid lines.
  Step B: read ONE COLUMN at a time from top to bottom (HSN, then batch, then expiry, then quantity, then
          free qty, then purchase rate, then MRP, then GST %, then amount).
  Step C: build row i from the i-th entry of each column. If a column has a gap or an entry is unreadable for a
          row, that row's field is null (add it to "uncertain_fields"); never shift values up or down a row.
"""
    + _COMMON_RULES
)
