"""
The ONE purchase-invoice calculation (Decimal arithmetic, no floats in the maths).

Every place that needs a purchase total uses this module: manual entry, OCR review, drafts and the posting engine
(`purchase_entry.post_manual_purchase`). The browser and the OCR model never compute a competing final total.

Policy (documented so it can be audited)
  money        Decimal, quantized to paise with ROUND_HALF_UP at every step named below; nothing is rounded to "make a total match".
  line         gross = qty x rate                      (free units are received at no charge, they never add money)
               line discount = gross x pct/100 (+ a fixed amount), never more than the gross
  invoice      one invoice-level discount (percent of the net lines, or a fixed amount) is shared over the lines in
               proportion to their value after line discounts; the shares add up to the discount to the paisa
  tax mode     exclusive: taxable = value after discounts, tax is added.
               inclusive (prices already contain GST): taxable = value x 100/(100+rate), tax = value - taxable.
               The tax is therefore never added a second time.
  tax          computed ONCE per GST rate on the SUM of taxable values of that rate (as an invoice's tax summary does),
               then shared back to the lines; intra-state: CGST = half (rounded), SGST = the rest; inter-state: IGST.
  other        freight / other charges (taxed at their own rate, default 0 %)
  total        taxable + tax + other charges. Rounding to the nearest rupee (the usual supplier convention) is applied
               only when asked for (`round_to_rupee`), and the round-off is reported as its own figure.
  reconcile    the calculated payable total is compared with the printed total within a configurable tolerance
               (PURCHASE_RECON_TOLERANCE rupees, default 1.00). Components (discount, taxable, CGST/SGST/IGST, other,
               round-off) are compared one by one so a difference can be explained. A difference is reported, never absorbed.
"""
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR, InvalidOperation
from typing import Dict, List, Optional

CENT = Decimal("0.01")
ZERO = Decimal("0")
HUNDRED = Decimal("100")
MAX_AMOUNT = Decimal("1000000000")          # sanity limit per figure (₹100 crore)


class CalcError(ValueError):
    """Invalid financial input (negative, not a number, absurdly large). Callers turn this into a 4xx."""


def D(value, name: str = "value") -> Decimal:
    """A Decimal from a number/text. Floats go through str() so 0.1 stays 0.1."""
    if value is None or value == "":
        return ZERO
    try:
        d = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        raise CalcError(f"{name} is not a number: {value!r}")
    if not d.is_finite():
        raise CalcError(f"{name} is not a finite number")
    return d


def q2(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def _nonneg(d: Decimal, name: str) -> Decimal:
    if d < 0:
        raise CalcError(f"{name} cannot be negative")
    if d > MAX_AMOUNT:
        raise CalcError(f"{name} is too large")
    return d


def tolerance() -> Decimal:
    try:
        t = Decimal(os.getenv("PURCHASE_RECON_TOLERANCE", "1.00"))
    except InvalidOperation:
        t = Decimal("1.00")
    return t if t >= 0 else Decimal("1.00")


def _share(total: Decimal, weights: List[Decimal]) -> List[Decimal]:
    """Split `total` (paise) over `weights` proportionally; the parts add up to exactly `total`."""
    total = q2(total)
    s = sum(weights, ZERO)
    n = len(weights)
    if n == 0:
        return []
    if s <= 0 or total == 0:
        return [ZERO] * n
    raw = [total * w / s for w in weights]
    parts = [r.quantize(CENT, rounding=ROUND_FLOOR) for r in raw]
    left = int(((total - sum(parts, ZERO)) / CENT).to_integral_value())
    order = sorted(range(n), key=lambda i: raw[i] - parts[i], reverse=True)
    for i in order[: max(0, left)]:
        parts[i] += CENT
    return parts


def calc_invoice(lines: List[dict], *, invoice_discount_percent=0, invoice_discount_amount=0, other_charges=0, other_charges_gst=0,
                 interstate: bool = False, prices_include_gst: bool = False, round_to_rupee: bool = False) -> dict:
    """
    lines: [{qty, free, rate, disc_percent, disc_amount, gst_rate}] (any of free/disc_* may be missing).
    Returns plain floats rounded to paise, plus per-line and per-rate detail.
    """
    inv_pct = _nonneg(D(invoice_discount_percent, "invoice discount %"), "invoice discount %")
    inv_amt = _nonneg(D(invoice_discount_amount, "invoice discount"), "invoice discount")
    if inv_pct > HUNDRED:
        raise CalcError("invoice discount % cannot exceed 100")
    if inv_pct > 0 and inv_amt > 0:
        raise CalcError("give the invoice discount as a percentage OR an amount, not both")
    other = _nonneg(D(other_charges, "other charges"), "other charges")
    other_rate = _nonneg(D(other_charges_gst, "GST on other charges"), "GST on other charges")

    rows = []
    for n, l in enumerate(lines, 1):
        qty = _nonneg(D(l.get("qty"), f"row {n} quantity"), f"row {n} quantity")
        free = _nonneg(D(l.get("free"), f"row {n} free quantity"), f"row {n} free quantity")
        rate = _nonneg(D(l.get("rate"), f"row {n} rate"), f"row {n} rate")
        dpct = _nonneg(D(l.get("disc_percent"), f"row {n} discount %"), f"row {n} discount %")
        damt = _nonneg(D(l.get("disc_amount"), f"row {n} discount"), f"row {n} discount")
        gst = _nonneg(D(l.get("gst_rate"), f"row {n} GST rate"), f"row {n} GST rate")
        if dpct > HUNDRED:
            raise CalcError(f"row {n} discount % cannot exceed 100")
        if gst > 28:
            raise CalcError(f"row {n} GST rate cannot exceed 28")
        gross = q2(qty * rate)
        disc = min(gross, q2(gross * dpct / HUNDRED) + q2(damt))
        rows.append({"qty": qty, "free": free, "rate": rate, "gst": gst, "gross": gross, "line_discount": disc, "net": gross - disc})

    net_sum = sum((r["net"] for r in rows), ZERO)
    inv_disc = q2(net_sum * inv_pct / HUNDRED) if inv_pct > 0 else q2(inv_amt)
    if inv_disc > net_sum:
        raise CalcError("the invoice discount is larger than the invoice value")
    for r, share in zip(rows, _share(inv_disc, [r["net"] for r in rows])):
        r["invoice_discount"] = share
        r["value"] = r["net"] - share                      # value after all discounts (tax-inclusive when prices include GST)

    groups: Dict[Decimal, dict] = {}
    for r in rows:
        groups.setdefault(r["gst"], {"rate": r["gst"], "idx": []})["idx"].append(r)
    taxable_total = tax_total = ZERO
    out_groups = []
    for rate in sorted(groups):
        g = groups[rate]
        members = g["idx"]
        value_sum = sum((m["value"] for m in members), ZERO)
        if prices_include_gst:
            taxable = q2(value_sum * HUNDRED / (HUNDRED + rate))
            tax = value_sum - taxable
        else:
            taxable = value_sum
            tax = q2(taxable * rate / HUNDRED)
        for m, t_sh, x_sh in zip(members, _share(taxable, [m["value"] for m in members]), _share(tax, [m["value"] for m in members])):
            m["taxable"], m["tax"] = t_sh, x_sh
        if interstate:
            cgst, sgst, igst = ZERO, ZERO, tax
        else:
            cgst = q2(tax / 2)
            sgst, igst = tax - cgst, ZERO
        out_groups.append({"rate": float(rate), "taxable": float(taxable), "tax": float(tax), "cgst": float(cgst), "sgst": float(sgst), "igst": float(igst)})
        taxable_total += taxable
        tax_total += tax
    cg = sum((D(g["cgst"]) for g in out_groups), ZERO)
    sg = sum((D(g["sgst"]) for g in out_groups), ZERO)
    ig = sum((D(g["igst"]) for g in out_groups), ZERO)

    other_tax = q2(other * other_rate / HUNDRED)
    other_total = other + other_tax
    if other_tax:
        if interstate:
            ig += other_tax
        else:
            half = q2(other_tax / 2)
            cg += half
            sg += other_tax - half
        tax_total += other_tax

    before = taxable_total + tax_total + other
    payable = before.quantize(Decimal("1"), rounding=ROUND_HALF_UP) if round_to_rupee else before
    payable = q2(payable)
    lines_out = []
    for r in rows:
        received = r["qty"] + r["free"]
        cost = (r["taxable"] / received).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP) if received > 0 else ZERO
        lines_out.append({
            "received_qty": int(received), "gross": float(r["gross"]), "line_discount": float(r["line_discount"]),
            "invoice_discount_share": float(r["invoice_discount"]), "taxable": float(r["taxable"]), "gst_rate": float(r["gst"]),
            "tax": float(r["tax"]), "total": float(r["taxable"] + r["tax"]), "net_unit_cost": float(cost),
        })
    return {
        "lines": lines_out, "tax_groups": out_groups,
        "totals": {
            "gross": float(sum((r["gross"] for r in rows), ZERO)),
            "line_discount": float(sum((r["line_discount"] for r in rows), ZERO)),
            "invoice_discount": float(inv_disc),
            "discount": float(sum((r["line_discount"] for r in rows), ZERO) + inv_disc),
            "taxable": float(taxable_total), "cgst": float(cg), "sgst": float(sg), "igst": float(ig), "tax": float(tax_total),
            "other_charges": float(other_total), "total_before_round": float(q2(before)),
            "round_off": float(payable - q2(before)), "payable": float(payable),
        },
        "policy": {"tax_mode": "inclusive" if prices_include_gst else "exclusive", "supply": "inter-state" if interstate else "intra-state",
                   "rounded_to_rupee": bool(round_to_rupee), "tax_computed": "once per GST rate on the sum of taxable values"},
    }


def _num(v):
    try:
        return None if v is None or v == "" else D(v)
    except CalcError:
        return None


def reconcile(calc: dict, printed: Optional[dict], tol: Optional[Decimal] = None) -> dict:
    """
    Compare the calculation with what the supplier printed. printed keys (all optional): total, subtotal, discount,
    taxable, cgst, sgst, igst, other, round_off. Never changes the calculation.
    """
    tol = tolerance() if tol is None else Decimal(str(tol))
    printed = printed or {}
    t = calc["totals"]
    comp_tol = {"total": tol, "subtotal": tol, "discount": tol, "taxable": tol, "other": tol, "round_off": Decimal("0.50"),
                "cgst": Decimal("0.10"), "sgst": Decimal("0.10"), "igst": Decimal("0.10")}
    mine = {"subtotal": t["gross"], "discount": t["discount"], "taxable": t["taxable"], "cgst": t["cgst"], "sgst": t["sgst"], "igst": t["igst"],
            "other": t["other_charges"], "round_off": t["round_off"], "total": t["payable"]}
    labels = {"subtotal": "Gross line amount", "discount": "Discount", "taxable": "Taxable amount", "cgst": "CGST", "sgst": "SGST", "igst": "IGST",
              "other": "Other charges", "round_off": "Round-off", "total": "Invoice total"}
    comps = []
    for k in ("subtotal", "discount", "taxable", "cgst", "sgst", "igst", "other", "round_off", "total"):
        p = _num(printed.get(k))
        if p is None:
            continue
        diff = q2(D(mine[k]) - p)
        comps.append({"key": k, "label": labels[k], "printed": float(p), "calculated": mine[k], "difference": float(diff),
                      "ok": abs(diff) <= comp_tol[k]})
    pt = _num(printed.get("total"))
    diff = q2(D(t["payable"]) - pt) if pt is not None else None
    ok = None if diff is None else abs(diff) <= tol
    causes = []
    if diff is not None and not ok:
        bad = [c for c in comps if c["key"] != "total" and not c["ok"]]
        for c in sorted(bad, key=lambda c: abs(c["difference"]), reverse=True):
            causes.append(f"{c['label']}: calculated {c['calculated']:.2f} but the bill prints {c['printed']:.2f} (difference {c['difference']:+.2f}).")
        pd_ = _num(printed.get("discount"))
        if pd_ and pd_ > 0 and t["discount"] == 0:
            causes.insert(0, f"The bill shows a discount of {float(pd_):.2f} but none was applied in the calculation.")
        if not causes:
            causes.append("The printed components agree with the calculation, so a line amount, a rate or a missing/extra charge on the bill is the likely source: check the lines against the bill.")
    state = "MISSING_PRINTED_TOTAL" if pt is None else ("MATCHED" if ok else "MISMATCH")
    return {
        "state": state,
        "status": "NO_PRINTED_TOTAL" if pt is None else ("PASS" if ok else "REVIEW"),
        "printed_total": float(pt) if pt is not None else None, "calculated_total": t["payable"],
        "difference": float(diff) if diff is not None else None, "tolerance": float(tol),
        "components": comps, "likely_causes": causes,
    }


def infer_tax_mode(gross: float, discount: float, printed_taxable: Optional[float], rates: List[float], tol: float = 1.0) -> Optional[bool]:
    """
    Do the printed rates already include GST? Decided only from the printed taxable amount:
    gross - discount == taxable -> exclusive (False); (gross - discount) x 100/(100+rate) == taxable -> inclusive (True);
    neither / not enough data -> None (the caller flags it instead of guessing).
    """
    if printed_taxable is None or not rates:
        return None
    base = D(gross) - D(discount)
    pt = D(printed_taxable)
    if abs(base - pt) <= Decimal(str(tol)):
        return False
    r = D(max(rates))
    if abs(q2(base * HUNDRED / (HUNDRED + r)) - pt) <= Decimal(str(tol)):
        return True
    return None
