"""
GST rate of one purchase-invoice line: where it comes from, how far it can be trusted, and when it is simply unknown.

Order (first that applies wins; each result says which source it came from):
  1. invoice_line     the rate printed on this bill line and read by OCR, when it is a valid GST slab for the invoice date and
                      OCR did not flag it as uncertain; or a rate the user typed / confirmed in the editor ("user_verified")
  2. product_master  this pharmacy's own stock: every batch of the same medicine carries ONE rate (a rate it was bought and
                      sold with before). Two different rates = ambiguous, not guessed.
  3. hsn_table       the HSN -> rate table, dated. It is only a SUGGESTION: one HSN (e.g. 3004) covers medicines taxed at
                      different rates, so an HSN-derived rate must be acknowledged by the user before the bill is confirmed.
  4. none            nothing reliable: the line is blocked until the user gives the rate.
Never: a silent 0 %, a single default rate for all medicines, or a rate that is not a valid slab on the invoice date.

Slabs by date (GST Council change effective 22 Sep 2025: the 12 % and 28 % slabs were removed and most medicines moved
from 12 % to 5 %). This table is the developer's reading of that change and must be confirmed with the pharmacy's CA.
"""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

import models

SLAB_CHANGE = date(2025, 9, 22)
SLABS_BEFORE = (0.0, 0.25, 3.0, 5.0, 12.0, 18.0, 28.0)
SLABS_FROM = (0.0, 0.25, 3.0, 5.0, 18.0, 40.0)

# HSN prefix -> [(valid_from, valid_until, rate)]. Anything not listed is unknown for that date (never guessed).
HSN_RATES = {
    "3004": [(None, date(2025, 9, 21), 12.0), (SLAB_CHANGE, None, 5.0)],
    "3003": [(None, date(2025, 9, 21), 12.0), (SLAB_CHANGE, None, 5.0)],
    "3002": [(None, date(2025, 9, 21), 5.0)],
    "3001": [(None, date(2025, 9, 21), 5.0)],
}


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return date.today()


def valid_slabs(on: date) -> tuple:
    return SLABS_FROM if on >= SLAB_CHANGE else SLABS_BEFORE


def is_valid_slab(rate: float, on: date) -> bool:
    return any(abs(float(rate) - s) < 1e-9 for s in valid_slabs(on))


def hsn_rate(hsn: Optional[str], on: date) -> Optional[float]:
    clean = str(hsn or "").strip().replace(".", "").replace(" ", "")
    if len(clean) < 4:
        return None
    for key in (clean[:4],):
        for start, end, rate in HSN_RATES.get(key, []):
            if (start is None or on >= start) and (end is None or on <= end):
                return rate
    return None


def product_master_rate(db: Session, user_id: int, name: str):
    """(rate, None) when all this shop's batches of the medicine agree; (None, 'ambiguous') when they differ; (None, None) if unknown."""
    if not name:
        return None, None
    from tax_reports import product_gst_rate
    rows = db.query(models.Product).filter(models.Product.user_id == user_id, models.Product.is_deleted == False,
                                           func.lower(models.Product.product_name) == name.strip().lower()).all()
    rates = {round(product_gst_rate(p, default=-1.0), 4) for p in rows}
    rates.discard(-1.0)
    if len(rates) == 1:
        return rates.pop(), None
    return (None, "ambiguous") if len(rates) > 1 else (None, None)


def resolve(db: Session, user_id: int, line: dict, invoice_date) -> dict:
    """
    -> {"rate": float|None, "source": str|None, "needs_ack": bool, "note": str|None, "error": str|None}
    line keys used: gst_rate, hsn_code, product_name, field_flags, uncertain_fields, gst_verified.
    """
    on = as_date(invoice_date)
    printed = line.get("gst_rate")
    flagged = "gst_rate" in (line.get("field_flags") or {}) or "gst_rate" in (line.get("uncertain_fields") or [])
    verified = bool(line.get("gst_verified"))
    note = None

    if printed is not None:
        if not any(abs(float(printed) - x) < 1e-9 for x in set(SLABS_BEFORE) | set(SLABS_FROM)):
            slabs = ", ".join(f"{x:g}" for x in valid_slabs(on))
            return {"rate": None, "source": None, "needs_ack": False, "note": None,
                    "error": f"GST {printed:g}% is not a GST rate (valid for {on.isoformat()}: {slabs}). Correct the rate."}
        if not is_valid_slab(printed, on) and not verified:
            slabs = ", ".join(f"{x:g}" for x in valid_slabs(on))
            return {"rate": float(printed), "source": "invoice_line_dated", "needs_ack": True, "error": None,
                    "note": f"GST {printed:g}% is not a standard rate for an invoice dated {on.isoformat()} (standard: {slabs}). Check it against the bill."}
        if verified:
            return {"rate": float(printed), "source": "user_verified", "needs_ack": False, "note": None, "error": None}
        if not flagged:
            rate, amb = product_master_rate(db, user_id, line.get("product_name") or "")
            if rate is not None and abs(rate - float(printed)) > 1e-9:
                note = f"Your stock records {line.get('product_name')} at {rate:g}% but the bill line says {float(printed):g}%: check the bill."
            return {"rate": float(printed), "source": "invoice_line", "needs_ack": False, "note": note, "error": None}
        note = "OCR was not sure about this GST rate: check it against the bill."
        return {"rate": float(printed), "source": "invoice_line_uncertain", "needs_ack": True, "note": note, "error": None}

    rate, amb = product_master_rate(db, user_id, line.get("product_name") or "")
    if rate is not None and is_valid_slab(rate, on):
        return {"rate": rate, "source": "product_master", "needs_ack": False,
                "note": f"GST {rate:g}% taken from your stock records of this medicine (not printed on the bill line).", "error": None}
    if amb:
        note = "Your stock has this medicine at different GST rates, so none was assumed. "
    h = hsn_rate(line.get("hsn_code"), on)
    if h is not None:
        return {"rate": h, "source": "hsn_table", "needs_ack": True,
                "note": f"GST {h:g}% suggested from HSN {line.get('hsn_code')} for {on.isoformat()}. One HSN covers medicines taxed at different rates: check it against the bill.", "error": None}
    why = "Neither a GST rate nor a known HSN was read" if not str(line.get("hsn_code") or "").strip() else f"HSN {line.get('hsn_code')} is not in the rate table for {on.isoformat()}"
    return {"rate": None, "source": None, "needs_ack": False, "note": None,
            "error": f"{note or ''}{why}: enter the GST rate shown on the bill."}
