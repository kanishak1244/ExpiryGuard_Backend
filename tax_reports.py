"""
Sales tax figures for the reports (GST summary on CA Connect, GSTR-1 / GSTR-3B summaries, Reports & Analytics).

One rule for every report:
  - Sales of the period come from what was saved on each bill line (taxable value, CGST/SGST/IGST, GST amount, total),
    never recomputed from a guessed rate.
  - Sales returns are counted in the period the RETURN happened (as a credit note would be): the returned share of a line
    is returned quantity / sold quantity of that line, applied to the line's saved taxable value and tax.
  - Net = gross sales - returns.
Read-only.
"""
from typing import Optional

from sqlalchemy.orm import Session

import models


def gst_value(*candidates, default: float = 12.0) -> float:
    """First rate that is actually set. 0 % is a real rate (exempt medicines), only a missing value falls back."""
    for c in candidates:
        if c is None or c == "":
            continue
        try:
            return float(c)
        except (TypeError, ValueError):
            continue
    return float(default)


def product_gst_rate(product, default: float = 12.0) -> float:
    """
    GST rate of a medicine. The products table keeps it twice (gst_percentage, gst_rate). Both 0 means an exempt
    medicine: 0 %. Only when the two disagree (an old row with one of them left at 0) is the non-zero one used, and only
    when neither is set does the shop default apply.
    """
    vals = [float(v) for v in (getattr(product, "gst_percentage", None), getattr(product, "gst_rate", None)) if v is not None]
    if not vals:
        return float(default)
    nonzero = [v for v in vals if v > 0]
    return nonzero[0] if nonzero else 0.0


def _line_values(item: "models.SaleItem") -> dict:
    """Saved tax figures of one bill line; old lines without them are derived from the line total and rate."""
    taxable = float(item.taxable_value or 0.0)
    gst = float(item.gst_amount or 0.0)
    total = float(item.total_with_tax or 0.0)
    if taxable <= 0 and gst <= 0:
        rate = gst_value(item.gst_percentage, default=0.0)
        total = float(item.total_with_tax or item.total_price or 0.0)
        taxable = total / (1.0 + rate / 100.0) if rate else total
        gst = total - taxable
        cgst = sgst = gst / 2.0
        igst = 0.0
    else:
        cgst, sgst, igst = float(item.cgst_amount or 0.0), float(item.sgst_amount or 0.0), float(item.igst_amount or 0.0)
        if not (cgst or sgst or igst) and gst:
            cgst = sgst = gst / 2.0
        if total <= 0:
            total = taxable + gst
    return {"taxable": taxable, "gst": gst, "cgst": cgst, "sgst": sgst, "igst": igst, "total": total}


def sales_tax_breakdown(db: Session, user_id: int, start_utc, end_utc) -> dict:
    """Gross sales, returns and net figures for [start_utc, end_utc] (naive UTC), plus an HSN summary net of returns."""
    from crud import _round_half_up as r

    keys = ("taxable", "gst", "cgst", "sgst", "igst", "total")
    gross = dict.fromkeys(keys, 0.0)
    ret = dict.fromkeys(keys, 0.0)
    hsn = {}

    def hsn_row(code, rate):
        k = (code or "3004", rate)
        if k not in hsn:
            hsn[k] = {"hsn_code": code or "3004", "gst_rate": rate, "quantity": 0, "taxable_amount": 0.0, "cgst_amount": 0.0,
                      "sgst_amount": 0.0, "igst_amount": 0.0, "total_tax": 0.0, "total_amount": 0.0}
        return hsn[k]

    S, SI = models.Sale, models.SaleItem
    sales = db.query(S.id).filter(S.user_id == user_id, S.created_at >= start_utc, S.created_at <= end_utc)
    bill_count = sales.count()
    items = db.query(SI).join(S, S.id == SI.sale_id).filter(S.user_id == user_id, S.created_at >= start_utc, S.created_at <= end_utc).all()
    for it in items:
        v = _line_values(it)
        for k in keys:
            gross[k] += v[k]
        row = hsn_row((it.hsn_code or "").strip(), gst_value(it.gst_percentage, default=0.0))
        row["quantity"] += int(it.quantity or 0)
        row["taxable_amount"] += v["taxable"]
        row["cgst_amount"] += v["cgst"]
        row["sgst_amount"] += v["sgst"]
        row["igst_amount"] += v["igst"]
        row["total_tax"] += v["gst"]
        row["total_amount"] += v["total"]

    R, RI = models.SaleReturn, models.SaleReturnItem
    returned = (db.query(RI, SI).join(R, R.id == RI.sale_return_id).join(SI, SI.id == RI.sale_item_id)
                .filter(R.user_id == user_id, R.created_at >= start_utc, R.created_at <= end_utc).all())
    return_count = db.query(R.id).filter(R.user_id == user_id, R.created_at >= start_utc, R.created_at <= end_utc).count()
    refunded = 0.0
    for ri, it in returned:
        sold = int(it.quantity or 0)
        if sold <= 0:
            continue
        share = min(1.0, int(ri.quantity or 0) / sold)
        v = _line_values(it)
        for k in keys:
            ret[k] += v[k] * share
        refunded += float(ri.return_total or 0.0)
        row = hsn_row((it.hsn_code or "").strip(), gst_value(it.gst_percentage, default=0.0))
        row["quantity"] -= int(ri.quantity or 0)
        row["taxable_amount"] -= v["taxable"] * share
        row["cgst_amount"] -= v["cgst"] * share
        row["sgst_amount"] -= v["sgst"] * share
        row["igst_amount"] -= v["igst"] * share
        row["total_tax"] -= v["gst"] * share
        row["total_amount"] -= v["total"] * share

    rr = lambda d: {k: r(d[k], 2) for k in keys}
    g, rt = rr(gross), rr(ret)
    net = {k: r(g[k] - rt[k], 2) for k in keys}
    hsn_rows = []
    for row in sorted(hsn.values(), key=lambda x: (x["hsn_code"], x["gst_rate"])):
        hsn_rows.append({k: (r(v, 2) if isinstance(v, float) and k != "gst_rate" else v) for k, v in row.items()})
    return {
        "bill_count": bill_count, "return_count": return_count,
        "gross": g, "returns": rt, "net": net,
        "refunded_amount": r(refunded, 2),
        "hsn": hsn_rows,
    }


def purchase_tax(db: Session, user_id: int, start_date, end_date) -> dict:
    """
    Purchases of the period by INVOICE date (an entry without an invoice date falls back to its entry date).
    Taxable value = invoice total - GST on the invoice.
    """
    from datetime import datetime, time, timedelta
    from sqlalchemy import and_, func, or_
    from crud import _round_half_up as r
    PI = models.PurchaseInvoice
    ist = timedelta(hours=5, minutes=30)
    start_utc = datetime.combine(start_date, time.min) - ist
    end_utc = datetime.combine(end_date, time.max) - ist
    total, tax, count = db.query(func.coalesce(func.sum(PI.total_amount), 0.0), func.coalesce(func.sum(PI.tax_amount), 0.0), func.count(PI.id)).filter(
        PI.user_id == user_id,
        or_(and_(PI.invoice_date.isnot(None), PI.invoice_date >= start_date, PI.invoice_date <= end_date),
            and_(PI.invoice_date.is_(None), PI.created_at >= start_utc, PI.created_at <= end_utc)),
    ).one()
    return {"count": int(count or 0), "total": r(float(total), 2), "tax": r(float(tax), 2), "taxable": r(float(total) - float(tax), 2)}
