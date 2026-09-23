import json
from typing import Dict, Any, List, Optional
from datetime import datetime


class EscPosBuilder:
    """
    Production-ready ESC/POS command builder for 58mm and 80mm thermal receipt printers.
    Generates standard byte streams compliant with Epson ESC/POS specifications.
    """

    # Commands
    ESC = b'\x1b'
    GS = b'\x1d'
    FS = b'\x1c'

    # Initialization
    INIT = ESC + b'@'

    # Text Alignment
    ALIGN_LEFT = ESC + b'a\x00'
    ALIGN_CENTER = ESC + b'a\x01'
    ALIGN_RIGHT = ESC + b'a\x02'

    # Text Emphasis & Sizing
    BOLD_ON = ESC + b'E\x01'
    BOLD_OFF = ESC + b'E\x00'
    DOUBLE_HEIGHT_ON = ESC + b'!\x10'
    DOUBLE_WIDTH_ON = ESC + b'!\x20'
    DOUBLE_SIZE_ON = ESC + b'!\x30'
    SIZE_NORMAL = ESC + b'!\x00'
    UNDERLINE_ON = ESC + b'-\x01'
    UNDERLINE_OFF = ESC + b'-\x00'

    # Paper Feed & Cut
    FEED_LINE = b'\n'
    CUT_PAPER_FULL = GS + b'V\x00'
    CUT_PAPER_PARTIAL = GS + b'V\x01'
    CUT_PAPER_FEED = GS + b'V\x42\x03'  # Feed 3 lines and cut

    # Cash Drawer Kick-out (Pulse)
    DRAWER_KICK = ESC + b'p\x00\x19\xfa'

    def __init__(self, paper_size: str = "80mm", encoding: str = "cp437"):
        self.paper_size = "58mm" if str(paper_size).strip().lower() == "58mm" else "80mm"
        # Standard column widths: 58mm is 32 columns; 80mm is 48 columns (or 42 on narrow font)
        self.line_width = 32 if self.paper_size == "58mm" else 48
        self.encoding = encoding
        self.buffer = bytearray()
        self.init_printer()

    def init_printer(self) -> "EscPosBuilder":
        self.buffer.extend(self.INIT)
        return self

    def feed(self, lines: int = 1) -> "EscPosBuilder":
        self.buffer.extend(self.FEED_LINE * max(1, lines))
        return self

    def align(self, alignment: str) -> "EscPosBuilder":
        align_lower = alignment.lower().strip()
        if align_lower == "center":
            self.buffer.extend(self.ALIGN_CENTER)
        elif align_lower == "right":
            self.buffer.extend(self.ALIGN_RIGHT)
        else:
            self.buffer.extend(self.ALIGN_LEFT)
        return self

    def text(self, text_str: str) -> "EscPosBuilder":
        try:
            encoded = text_str.encode(self.encoding, errors="replace")
        except Exception:
            encoded = text_str.encode("ascii", errors="replace")
        self.buffer.extend(encoded)
        return self

    def text_line(self, text_str: str) -> "EscPosBuilder":
        self.text(text_str)
        self.feed(1)
        return self

    def bold(self, enable: bool = True) -> "EscPosBuilder":
        self.buffer.extend(self.BOLD_ON if enable else self.BOLD_OFF)
        return self

    def double_size(self, enable: bool = True) -> "EscPosBuilder":
        self.buffer.extend(self.DOUBLE_SIZE_ON if enable else self.SIZE_NORMAL)
        return self

    def separator(self, char: str = "-") -> "EscPosBuilder":
        self.align("left")
        self.buffer.extend(self.SIZE_NORMAL)
        self.buffer.extend(self.BOLD_OFF)
        sep = (char * self.line_width)[:self.line_width]
        self.text_line(sep)
        return self

    def double_separator(self) -> "EscPosBuilder":
        return self.separator("=")

    def key_value_line(self, key: str, value: str, is_bold: bool = False) -> "EscPosBuilder":
        """Formats 'Key:                                   Value' matching exact line width."""
        if is_bold:
            self.bold(True)
        key_str = str(key)
        val_str = str(value)
        avail = self.line_width - len(key_str) - len(val_str)
        if avail >= 1:
            line = key_str + (" " * avail) + val_str
        else:
            # If too long, wrap
            line = key_str + " " + val_str
        self.text_line(line)
        if is_bold:
            self.bold(False)
        return self

    def cut_paper(self, feed_lines: int = 3) -> "EscPosBuilder":
        self.feed(feed_lines)
        self.buffer.extend(self.CUT_PAPER_FEED)
        return self

    def kick_cash_drawer(self) -> "EscPosBuilder":
        self.buffer.extend(self.DRAWER_KICK)
        return self

    def build_bytes(self) -> bytes:
        return bytes(self.buffer)


def build_thermal_receipt_bytes(
    payload: Dict[str, Any],
    paper_size: str = "80mm",
    cut_paper: bool = True,
    open_drawer: bool = False,
    copies: int = 1,
    drawer_pulse: Optional[bool] = None,
) -> bytes:
    """
    Creates complete, pharmacy-formatted thermal receipt bytes from a frozen billing snapshot.
    Zero recalculation: uses exact values from payload.
    """
    if drawer_pulse is not None:
        open_drawer = drawer_pulse

    builder = EscPosBuilder(paper_size=paper_size)
    is_58mm = builder.line_width <= 32

    shop = payload.get("shop", {})
    bill = payload.get("sale") or payload
    items: List[Dict[str, Any]] = bill.get("items", []) or payload.get("items", [])
    if not bill.get("bill_number") and payload.get("invoice_number"):
        bill["bill_number"] = payload["invoice_number"]

    for copy_idx in range(max(1, copies)):
        if copy_idx > 0:
            builder.feed(2)
            builder.separator("*")
            builder.align("center")
            builder.bold(True)
            builder.text_line(f"--- DUPLICATE COPY {copy_idx + 1} ---")
            builder.bold(False)
            builder.separator("*")

        # -------------------------------------------------------------
        # 1. HEADER (Shop Info)
        # -------------------------------------------------------------
        builder.align("center")
        builder.double_size(True)
        builder.bold(True)
        shop_name = str(shop.get("shop_name") or shop.get("name") or "DAWAIFLOW PHARMACY").strip()
        builder.text_line(shop_name.upper())

        builder.double_size(False)
        builder.bold(False)

        address = str(shop.get("address") or "").strip()
        if address:
            # Wrap address if needed
            builder.text_line(address)

        phone = str(shop.get("phone") or "").strip()
        if phone:
            builder.text_line(f"Ph: {phone}")

        gstin = str(shop.get("gstin") or shop.get("gst_number") or "").strip()
        if gstin:
            builder.bold(True)
            builder.text_line(f"GSTIN: {gstin}")
            builder.bold(False)

        dl_no = str(shop.get("drug_license_no") or shop.get("drug_license") or "").strip()
        if dl_no:
            builder.text_line(f"DL No: {dl_no}")

        builder.feed(1)
        builder.bold(True)
        builder.text_line("TAX INVOICE / RETAIL BILL")
        builder.bold(False)

        # -------------------------------------------------------------
        # 2. INVOICE METADATA
        # -------------------------------------------------------------
        builder.separator("-")
        bill_no = bill.get("bill_number") or "BILL-N/A"
        date_raw = bill.get("created_at")
        if isinstance(date_raw, str):
            try:
                dt = datetime.fromisoformat(date_raw.replace("Z", "+00:00"))
                date_str = dt.strftime("%d/%m/%Y %I:%M %p")
            except Exception:
                date_str = date_raw[:16]
        elif isinstance(date_raw, datetime):
            date_str = date_raw.strftime("%d/%m/%Y %I:%M %p")
        else:
            date_str = datetime.now().strftime("%d/%m/%Y %I:%M %p")

        builder.key_value_line("Inv No:", bill_no, is_bold=True)
        builder.key_value_line("Date:", date_str)

        cust_name = str(bill.get("customer_name") or "Cash Customer").strip()
        if cust_name and cust_name.lower() != "cash customer":
            builder.key_value_line("Patient:", cust_name)

        cust_phone = str(bill.get("customer_phone") or "").strip()
        if cust_phone and cust_phone not in ["-", "N/A"]:
            builder.key_value_line("Phone:", cust_phone)

        doc_name = str(bill.get("doctor_name") or "").strip()
        doc_reg = str(bill.get("doctor_reg_no") or "").strip()
        if doc_name and doc_name not in ["-", "N/A"]:
            doc_str = f"Dr. {doc_name}"
            if doc_reg and doc_reg not in ["-", "N/A"]:
                doc_str += f" ({doc_reg})"
            builder.key_value_line("Doc:", doc_str)

        payment_mode = str(bill.get("payment_method") or "CASH").upper()
        builder.key_value_line("Payment:", payment_mode)

        # -------------------------------------------------------------
        # 3. LINE ITEMS
        # -------------------------------------------------------------
        builder.separator("=")

        if is_58mm:
            # 58mm: 32 columns compact layout
            # Line 1: Item Name
            # Line 2: Batch  Exp  Qty x Rate  Amt
            builder.align("left")
            builder.bold(True)
            builder.text_line("ITEM / BATCH / EXP     QTY  AMT")
            builder.bold(False)
            builder.separator("-")

            for idx, item in enumerate(items, 1):
                p_name = str(item.get("product_name") or "Item")
                batch = str(item.get("batch_number") or "-")
                exp = str(item.get("expiry_date") or item.get("expiry") or "-")
                qty = int(item.get("quantity") or 1)
                unit_type = str(item.get("unit_type") or "strip").lower()
                unit_lbl = "T" if unit_type in ["loose_tablet", "pill", "loose"] else "S"
                rate = float(item.get("unit_price") or 0.0)
                total = float(item.get("total_with_tax") or item.get("total_price") or item.get("line_total") or 0.0)
                discount = float(item.get("discount") or 0.0)

                # Line 1: Number + Medicine Name
                builder.bold(True)
                builder.text_line(f"{idx}. {p_name}")
                builder.bold(False)

                # Line 2: Batch, Exp, Qty and Amount
                # e.g.: "B:KC8250 Exp:12/26  2S 230.00"
                left_meta = f"B:{batch[:8]} E:{exp[:7]}"
                qty_rate = f"{qty}{unit_lbl}"
                amt_str = f"{total:.2f}"
                space_avail = builder.line_width - len(left_meta) - len(qty_rate) - len(amt_str) - 2
                spaces = " " * max(1, space_avail)
                builder.text_line(f"{left_meta} {qty_rate}{spaces}{amt_str}")

                if discount > 0:
                    builder.align("right")
                    builder.text_line(f"(Disc: -{discount:.2f})")
                    builder.align("left")
        else:
            # 80mm: 48 columns spacious layout
            # Col headers: ITEM              QTY   RATE    DISC   AMOUNT
            builder.align("left")
            builder.bold(True)
            # 48 width: 22 chars item, 5 qty, 7 rate, 6 disc, 8 amt
            hdr = f"{'ITEM':<22}{'QTY':>5}{'RATE':>7}{'DISC':>6}{'AMOUNT':>8}"
            builder.text_line(hdr)
            builder.bold(False)
            builder.separator("-")

            for idx, item in enumerate(items, 1):
                p_name = str(item.get("product_name") or "Item")
                batch = str(item.get("batch_number") or "-")
                exp = str(item.get("expiry_date") or item.get("expiry") or "-")
                qty = int(item.get("quantity") or 1)
                unit_type = str(item.get("unit_type") or "strip").lower()
                unit_lbl = "Tab" if unit_type in ["loose_tablet", "pill", "loose"] else "Str"
                rate = float(item.get("unit_price") or 0.0)
                total = float(item.get("total_with_tax") or item.get("total_price") or item.get("line_total") or 0.0)
                discount = float(item.get("discount") or 0.0)

                # Line 1: Medicine Name
                builder.bold(True)
                builder.text_line(f"{idx}. {p_name}")
                builder.bold(False)

                # Line 2: Batch details + table metrics
                batch_info = f"   B:{batch} Exp:{exp}"
                qty_str = f"{qty} {unit_lbl}"
                rate_str = f"{rate:.2f}"
                disc_str = f"{discount:.2f}" if discount > 0 else "-"
                amt_str = f"{total:.2f}"

                line2 = f"{batch_info:<22}{qty_str:>5}{rate_str:>7}{disc_str:>6}{amt_str:>8}"
                builder.text_line(line2)

        # -------------------------------------------------------------
        # 4. TOTALS & GST BREAKDOWN
        # -------------------------------------------------------------
        totals = payload.get("totals", {})
        subtotal = float(bill.get("subtotal") or bill.get("total_taxable_value") or totals.get("subtotal") or 0.0)
        bill_discount = float(bill.get("discount_amount") or totals.get("discount_amount") or 0.0)
        total_cgst = float(bill.get("total_cgst") or totals.get("cgst_amount") or 0.0)
        total_sgst = float(bill.get("total_sgst") or totals.get("sgst_amount") or 0.0)
        total_igst = float(bill.get("total_igst") or totals.get("igst_amount") or 0.0)
        tax_amount = float(bill.get("tax_amount") or (total_cgst + total_sgst + total_igst))
        grand_total = float(bill.get("total_amount") or totals.get("grand_total") or 0.0)

        builder.key_value_line("Taxable Subtotal:", f"INR {subtotal:.2f}")

        if bill_discount > 0:
            builder.key_value_line("Bill Discount:", f"-INR {bill_discount:.2f}")

        if total_igst > 0:
            builder.key_value_line("IGST:", f"INR {total_igst:.2f}")
        else:
            if total_cgst > 0:
                builder.key_value_line("CGST:", f"INR {total_cgst:.2f}")
            if total_sgst > 0:
                builder.key_value_line("SGST:", f"INR {total_sgst:.2f}")

        builder.separator("-")
        builder.double_size(True)
        builder.bold(True)
        builder.key_value_line("NET TOTAL:", f"Rs {grand_total:.2f}", is_bold=True)
        builder.double_size(False)
        builder.bold(False)

        raw_payments = bill.get("payments") or []
        if len(raw_payments) > 1:
            builder.separator("-")
            builder.bold(True)
            builder.text_line("PAYMENT BREAKDOWN (SPLIT):")
            builder.bold(False)
            for p in raw_payments:
                pm = p.get("payment_method", "").upper() if isinstance(p, dict) else getattr(p, "payment_method", "").upper()
                pa = float(p.get("amount", 0.0) if isinstance(p, dict) else getattr(p, "amount", 0.0))
                builder.key_value_line(f"  {pm}:", f"Rs {pa:.2f}")

        builder.separator("=")

        # -------------------------------------------------------------
        # 5. FOOTER & COMPLIANCE NOTES
        # -------------------------------------------------------------
        builder.align("center")
        terms = str(shop.get("terms_and_conditions") or "1. Goods once sold will not be returned.\n2. Expiry dates verified.").strip()
        for term_line in terms.split("\n"):
            if term_line.strip():
                builder.text_line(term_line.strip())

        builder.feed(1)
        builder.bold(True)
        builder.text_line("*** GET WELL SOON ***")
        builder.text_line(f"Powered by Dawaiflow POS")
        builder.bold(False)

    if open_drawer:
        builder.kick_cash_drawer()

    if cut_paper:
        builder.cut_paper(feed_lines=3)
    else:
        builder.feed(4)

    return builder.build_bytes()


# Convenience alias for desktop print agents
build_escpos_receipt = build_thermal_receipt_bytes
