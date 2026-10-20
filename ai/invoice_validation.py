"""
Deterministic checks for supplier-invoice line items (no AI, no database).

The model reads the bill; this module decides what to trust. Every check is a pure function so it can be
unit-tested. A field that fails a STRUCTURAL check (unreadable expiry, a date in the HSN column, a batch that
looks like a date/price/HSN) is BLANKED and flagged: the user must type it. A field that is readable but
implausible (already expired, far future, arithmetic mismatch, MRP below purchase rate) is KEPT and flagged
so the user confirms it. Nothing is ever corrected or filled in silently, and MRP is never taken from the
purchase rate.
"""

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

# Plausible expiry window.
EXPIRY_GRACE_DAYS = 0            # an invoice line already expired is flagged
EXPIRY_MAX_YEARS_AHEAD = 5       # more than ~5 years ahead is flagged

# Arithmetic tolerance: the printed amount may differ from qty x rate by rounding.
AMOUNT_TOLERANCE_ABS = 1.00
AMOUNT_TOLERANCE_PCT = 0.02

# Bills with at least this many rows are "dense grids": they get the second verification pass.
DENSE_ROWS = 8

# Fields that decide what is saved to inventory; a pass disagreement on any of these blanks it.
CRITICAL_FIELDS = ("hsn_code", "batch_number", "expiry_date", "quantity", "free_qty", "purchase_price", "mrp",
                   "gst_rate", "total_price")


# --------------------------------------------------------------------------------------------------------
# Expiry
# --------------------------------------------------------------------------------------------------------

def parse_expiry(raw: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Parses an expiry as printed ("03/28", "3-2028", "Mar 2028", "2028-03", "2028-03-31") into an ISO date on the
    LAST day of that month (a medicine is usable through its expiry month). Returns (iso, None) or
    (None, reason). A full ISO day is kept as is; a bare year or anything else is rejected.
    """
    if raw is None:
        return None, "expiry missing"
    s = str(raw).strip()
    if not s:
        return None, "expiry missing"

    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            date(y, mo, d)
        except ValueError:
            return None, f"'{s}' is not a real date"
        return s, None

    m = re.fullmatch(r"(\d{4})[-/](\d{1,2})", s)            # 2028-03
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        return _month_end(y, mo, s)

    m = re.fullmatch(r"(\d{1,2})\s*[-/.]\s*(\d{4})", s)      # 3/2028, 03-2028
    if m:
        return _month_end(int(m.group(2)), int(m.group(1)), s)

    m = re.fullmatch(r"(\d{1,2})\s*[-/.]\s*(\d{2})", s)      # 03/28
    if m:
        return _month_end(2000 + int(m.group(2)), int(m.group(1)), s)

    m = re.fullmatch(r"([A-Za-z]{3,9})[\s.\-/]*(\d{2}|\d{4})", s)   # Mar 2028, MAR-28
    if m:
        months = {n.lower(): i for i, n in enumerate(calendar.month_abbr) if n}
        key = m.group(1)[:3].lower()
        if key in months:
            yr = int(m.group(2))
            return _month_end(yr + 2000 if yr < 100 else yr, months[key], s)

    return None, f"'{s}' is not a readable expiry"


def _month_end(year: int, month: int, original: str) -> Tuple[Optional[str], Optional[str]]:
    if not (1 <= month <= 12):
        return None, f"'{original}' has month {month}, which is not valid"
    if not (2000 <= year <= 2100):
        return None, f"'{original}' has an implausible year"
    return f"{year:04d}-{month:02d}-{calendar.monthrange(year, month)[1]:02d}", None


def check_expiry_range(iso: str, today: Optional[date] = None) -> Optional[str]:
    """Reason string when the expiry is already past or more than ~5 years ahead; None when plausible."""
    today = today or date.today()
    d = datetime.strptime(iso, "%Y-%m-%d").date()
    if d < today - timedelta(days=EXPIRY_GRACE_DAYS):
        return "expiry is already in the past"
    if d > today + timedelta(days=int(365.25 * EXPIRY_MAX_YEARS_AHEAD)):
        return f"expiry is more than {EXPIRY_MAX_YEARS_AHEAD} years ahead"
    return None


# --------------------------------------------------------------------------------------------------------
# Shape checks for text fields
# --------------------------------------------------------------------------------------------------------

_DATE_LIKE = re.compile(
    r"^\s*(\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2,4}|\d{1,2}\s*[-/.]\s*\d{2,4}|\d{4}\s*-\s*\d{1,2}(\s*-\s*\d{1,2})?)\s*$"
)
_MONTH_NAME_DATE = re.compile(r"^\s*[A-Za-z]{3,9}[\s.\-/]*\d{2,4}\s*$")
_PRICE_LIKE = re.compile(r"^\s*(?:rs\.?|₹)?\s*\d+[.,]\d{1,2}\s*$", re.IGNORECASE)


def looks_like_date(value: Any) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    if _DATE_LIKE.match(s) or (_MONTH_NAME_DATE.match(s) and re.search(r"(?i)jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", s)):
        return True
    return False


def looks_like_price(value: Any) -> bool:
    return bool(_PRICE_LIKE.match(str(value or "")))


def validate_hsn(value: Any) -> Optional[str]:
    """Reason when the HSN is not digits-only of length 4, 6 or 8; None when valid or empty."""
    s = str(value or "").strip()
    if not s:
        return None
    if looks_like_date(s):
        return "a date was read in the HSN column"
    if not s.isdigit():
        return "HSN must be digits only"
    if len(s) not in (4, 6, 8):
        return f"HSN has {len(s)} digits (must be 4, 6 or 8)"
    return None


def validate_batch(value: Any, hsn: Any = None) -> Optional[str]:
    """Reason when the batch is empty or looks like a date, an HSN code or a price; None when plausible."""
    s = str(value or "").strip()
    if not s:
        return "batch is empty"
    if looks_like_date(s):
        return "batch looks like a date"
    if looks_like_price(s):
        return "batch looks like a price"
    h = str(hsn or "").strip()
    if h and s == h and s.isdigit():
        return "batch is the same as the HSN code"
    return None


# --------------------------------------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------------------------------------

def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except ValueError:
        return None


def check_line_arithmetic(qty: Any, rate: Any, amount: Any, discount_pct: Any = None, gst_pct: Any = None) -> Optional[str]:
    """
    Reason when qty x rate cannot produce the printed line amount, trying the combinations a bill may print:
    gross, after the line discount, and either of those with GST added. None when one matches or a number is
    missing (nothing to check).
    """
    q, r, a = to_float(qty), to_float(rate), to_float(amount)
    if not q or not r or a is None:
        return None
    d = (to_float(discount_pct) or 0.0) / 100.0
    g = (to_float(gst_pct) or 0.0) / 100.0
    candidates = {q * r, q * r * (1 - d), q * r * (1 + g), q * r * (1 - d) * (1 + g)}
    tol = max(AMOUNT_TOLERANCE_ABS, AMOUNT_TOLERANCE_PCT * abs(a))
    if any(abs(c - a) <= tol for c in candidates):
        return None
    return f"quantity x rate (Rs.{q * r:.2f}) does not match the line amount (Rs.{a:.2f})"


def check_mrp_vs_rate(mrp: Any, rate: Any) -> Optional[str]:
    m, r = to_float(mrp), to_float(rate)
    if m is not None and r is not None and m > 0 and r > 0 and m < r:
        return f"MRP Rs.{m:.2f} is lower than the purchase rate Rs.{r:.2f}"
    return None


# --------------------------------------------------------------------------------------------------------
# One line item
# --------------------------------------------------------------------------------------------------------

def validate_item(item: Dict[str, Any], today: Optional[date] = None) -> Dict[str, str]:
    """
    Validates one normalised line item IN PLACE and returns {field: reason}.
    Blanks structurally wrong fields (expiry_date, hsn_code, batch_number); keeps readable-but-implausible
    values (past/far expiry, arithmetic, MRP < rate) and flags them. MRP is never filled from the rate.
    """
    flags: Dict[str, str] = {}

    iso, why = parse_expiry(item.get("expiry_date"))
    if iso is None:
        if item.get("expiry_date") not in (None, ""):
            flags["expiry_date"] = why or "expiry unreadable"
        else:
            flags["expiry_date"] = "expiry missing"
        item["expiry_date"] = ""
    else:
        item["expiry_date"] = iso
        reason = check_expiry_range(iso, today)
        if reason:
            flags["expiry_date"] = reason

    hsn_raw = item.get("hsn_code")
    hsn_reason = validate_hsn(hsn_raw)
    if hsn_reason:
        flags["hsn_code"] = hsn_reason
        item["hsn_code"] = ""

    batch_reason = validate_batch(item.get("batch_number"), hsn_raw)
    if batch_reason:
        flags["batch_number"] = batch_reason
        item["batch_number"] = ""

    if to_float(item.get("mrp")) in (None, 0.0):
        flags["mrp"] = "MRP missing: enter the MRP printed on the pack"
        item["mrp"] = None
    else:
        below = check_mrp_vs_rate(item.get("mrp"), item.get("purchase_price"))
        if below:
            flags["mrp"] = below

    if to_float(item.get("purchase_price")) in (None, 0.0):
        flags["purchase_price"] = "purchase rate missing"

    arith = check_line_arithmetic(
        item.get("quantity"), item.get("purchase_price"), item.get("total_price"),
        item.get("discount_percent"), item.get("gst_rate"),
    )
    if arith:
        flags["total_price"] = arith

    if not str(item.get("product_name") or "").strip():
        flags["product_name"] = "medicine name missing"
    if to_float(item.get("quantity")) in (None, 0.0):
        flags["quantity"] = "quantity missing"
    if item.get("gst_rate") is None:
        flags["gst_rate"] = "GST % missing"

    return flags


# --------------------------------------------------------------------------------------------------------
# Whole bill
# --------------------------------------------------------------------------------------------------------

def check_totals(items: List[Dict[str, Any]], printed_subtotal: Any) -> Optional[str]:
    """Reason when the sum of line amounts differs from the printed subtotal beyond rounding."""
    sub = to_float(printed_subtotal)
    amounts = [to_float(i.get("total_price")) for i in items]
    if not sub or any(a is None for a in amounts) or not amounts:
        return None
    total = sum(amounts)
    tol = max(AMOUNT_TOLERANCE_ABS * 2, AMOUNT_TOLERANCE_PCT * sub)
    if abs(total - sub) > tol:
        return f"line amounts add up to Rs.{total:.2f} but the bill subtotal is Rs.{sub:.2f}"
    return None


def check_row_count(extracted: int, printed_rows: Any) -> Optional[str]:
    n = to_float(printed_rows)
    if n is None or n <= 0:
        return None
    if int(n) != extracted:
        return f"the bill shows {int(n)} rows but {extracted} were extracted"
    return None


def is_dense(row_count: int) -> bool:
    return row_count >= DENSE_ROWS


# --------------------------------------------------------------------------------------------------------
# Two-pass comparison
# --------------------------------------------------------------------------------------------------------

def _norm(v: Any) -> str:
    return re.sub(r"[^a-z0-9.]", "", str(v if v is not None else "").lower())


def _name_key(item: Dict[str, Any]) -> str:
    return re.sub(r"[^a-z0-9]", "", str(item.get("product_name") or "").lower())[:14]


def compare_passes(first: List[Dict[str, Any]], second: List[Dict[str, Any]]) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Compares two independent extractions field by field. Returns (per-row {field: reason}, invoice-level notes).
    Any critical field where the passes differ (including value vs null) must be blanked by the caller: the
    user types it. Rows are matched by position when both passes found the same number of rows and the names
    agree; otherwise by product name, and an unmatched row has every critical field flagged.
    """
    notes: List[str] = []
    result: List[Dict[str, str]] = [dict() for _ in first]
    if len(first) != len(second):
        notes.append(f"the two readings found different row counts ({len(first)} vs {len(second)})")

    used = set()
    for i, a in enumerate(first):
        b = None
        if i < len(second) and (len(first) == len(second)) and _name_key(a) == _name_key(second[i]):
            b = second[i]
            used.add(i)
        else:
            for j, cand in enumerate(second):
                if j not in used and _name_key(cand) == _name_key(a) and _name_key(a):
                    b = cand
                    used.add(j)
                    break
        if b is None:
            for f in CRITICAL_FIELDS:
                result[i][f] = "this row was not confirmed by the second reading"
            continue
        for f in CRITICAL_FIELDS:
            av, bv = a.get(f), b.get(f)
            if f == "free_qty":  # "no free quantity" is printed as blank or 0 depending on the reading
                av, bv = av or 0, bv or 0
            x, y = _norm(av), _norm(bv)
            if x != y:
                result[i][f] = f"the two readings disagree ({a.get(f) if a.get(f) not in (None, '') else 'blank'} vs {b.get(f) if b.get(f) not in (None, '') else 'blank'})"
    return result, notes
