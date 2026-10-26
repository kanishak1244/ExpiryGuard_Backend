"""
Supplier profile: the numbers and the linked-medicine stock status behind the Supplier & Vendor profile screen.

Read-only. Money comes from the same rule as the supplier ledger and the dashboard payables:
    owed = purchase invoices not marked PAID, minus supplier payments, minus purchase returns.

Linked medicine stock: one row per BATCH (a products row) that this supplier delivered or that is linked to the supplier.
The stock status is derived from what the system really recorded, never from "quantity is zero":
    received   = purchase lines (PurchaseItem)         sold      = sale lines of that batch (SaleItem, whole packs)
    returned   = purchase returns (PurchaseReturnItem) restocked = customer returns of those sales (returned_quantity)
A batch is RECONCILED when  received - (sold - restocked) - returned_to_supplier  equals the quantity on hand. Only then
is it certain that nothing else (manual stock edits, opening stock, loose-tablet sales) moved the stock.
The inventory keeps no lot provenance (which supplier's units a sale consumed), so sold / returned numbers are shown for a
batch only when this supplier is its single known source and the batch is reconciled; otherwise they are None and the
status falls back to what is certain (available quantity and expiry).
"""
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import crud
import models

STRIP_UNITS = ("strip", "pack", "box", "bottle")        # whole-pack sales, counted in the same unit as products.quantity


def _supplier_or_404(db: Session, user_id: int, supplier_id: int) -> models.Supplier:
    s = db.query(models.Supplier).filter(models.Supplier.id == supplier_id, models.Supplier.user_id == user_id).first()
    if not s:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return s


def profile(db: Session, user_id: int, supplier_id: int) -> dict:
    """Supplier details plus the figures that must equal the ledger / dashboard (computed by the same rule, in SQL)."""
    s = _supplier_or_404(db, user_id, supplier_id)
    PI = models.PurchaseInvoice
    total_purchased, count, last_date = db.query(
        func.coalesce(func.sum(PI.total_amount), 0.0), func.count(PI.id), func.max(PI.invoice_date)
    ).filter(PI.user_id == user_id, PI.supplier_id == supplier_id).one()
    owed = db.query(func.coalesce(func.sum(PI.total_amount), 0.0)).filter(
        PI.user_id == user_id, PI.supplier_id == supplier_id, func.upper(func.coalesce(PI.payment_status, "")) != "PAID").scalar() or 0.0
    paid = db.query(func.coalesce(func.sum(models.SupplierPayment.amount_paid), 0.0)).filter(
        models.SupplierPayment.user_id == user_id, models.SupplierPayment.supplier_id == supplier_id).scalar() or 0.0
    returned = db.query(func.coalesce(func.sum(models.PurchaseReturn.total_returned_value), 0.0)).filter(
        models.PurchaseReturn.user_id == user_id, models.PurchaseReturn.supplier_id == supplier_id).scalar() or 0.0
    payments_count = db.query(func.count(models.SupplierPayment.id)).filter(
        models.SupplierPayment.user_id == user_id, models.SupplierPayment.supplier_id == supplier_id).scalar() or 0
    returns_count = db.query(func.count(models.PurchaseReturn.id)).filter(
        models.PurchaseReturn.user_id == user_id, models.PurchaseReturn.supplier_id == supplier_id).scalar() or 0
    return {
        "id": s.id, "name": s.name, "contact_person": s.contact_person, "phone": s.phone, "email": s.email, "address": s.address,
        "gstin": s.gstin, "state": s.state, "payment_terms": s.payment_terms, "status": s.status, "notes": s.notes,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "purchase_count": int(count or 0), "total_purchased": round(float(total_purchased or 0.0), 2),
        "last_purchase_date": last_date.isoformat() if last_date else None,
        "total_paid": round(float(paid), 2), "total_returned": round(float(returned), 2),
        "balance_payable": round(float(owed) - float(paid) - float(returned), 2),
        "payments_count": int(payments_count), "returns_count": int(returns_count),
    }


def classify(qty: int, expiry: Optional[date], reconciled: bool, attributable: bool, sold_net: int, returned: int,
             shared_returns: int, today: date) -> tuple:
    """(status, note). Only claims what the recorded movements prove."""
    expired = bool(expiry and expiry < today)
    if qty > 0:
        if expired:
            return "Expired", "Past its expiry date; stock is still on hand."
        if attributable and sold_net > 0:
            return "Partially Sold", f"{sold_net} sold from this supplier's units; {qty} on hand."
        return "In Stock", ""
    # nothing on hand
    if reconciled:
        if attributable:
            if sold_net > 0:
                return "Sold Out", f"{sold_net} sold" + (f", {returned} returned to the supplier" if returned else "") + "."
            if returned > 0:
                return "Returned", f"{returned} returned to the supplier."
        elif sold_net > 0 and shared_returns == 0:
            return "Sold Out", "Whole batch sold (shared with other suppliers' units)."
    if expired:
        return "Expired", "Past its expiry date; the recorded movements do not fully explain the missing stock."
    return "Unavailable", "Stock is zero, but the recorded movements do not explain why (adjustment, loose sales or opening stock)."


def stock(db: Session, user_id: int, supplier_id: int, q: Optional[str] = None, status: Optional[str] = None,
          page: int = 1, page_size: int = 25) -> dict:
    """Linked medicine stock of a supplier, one row per batch, with an honest stock status. Paged, a fixed number of queries."""
    _supplier_or_404(db, user_id, supplier_id)
    page, page_size = max(1, int(page or 1)), min(100, max(1, int(page_size or 25)))
    today = date.today()
    P, PI, PItem = models.Product, models.PurchaseInvoice, models.PurchaseItem

    linked = {r[0] for r in db.query(P.id).filter(P.user_id == user_id, P.is_deleted == False, P.supplier_id == supplier_id).all()}
    bought = {r[0] for r in db.query(PItem.product_id).join(PI, PI.id == PItem.purchase_invoice_id).filter(
        PI.user_id == user_id, PI.supplier_id == supplier_id).distinct().all()}
    ids = sorted(linked | bought)
    if not ids:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "counts": {}, "notes": _notes()}
    products = {p.id: p for p in db.query(P).filter(P.user_id == user_id, P.is_deleted == False, P.id.in_(ids)).all()}

    # purchase lines of these batches, from every supplier (to know whether the batch is shared)
    all_lines = (db.query(PItem.product_id, PItem.quantity, PI.supplier_id, PI.id, PI.invoice_number, PI.invoice_date)
                 .join(PI, PI.id == PItem.purchase_invoice_id).filter(PI.user_id == user_id, PItem.product_id.in_(ids))
                 .order_by(PI.invoice_date, PI.id).all())
    recv_all, recv_s, suppliers_of, last_inv = {}, {}, {}, {}
    for pid, qty, sid, inv_id, inv_no, inv_date in all_lines:
        recv_all[pid] = recv_all.get(pid, 0) + int(qty or 0)
        suppliers_of.setdefault(pid, set()).add(sid)
        if sid == supplier_id:
            recv_s[pid] = recv_s.get(pid, 0) + int(qty or 0)
            last_inv[pid] = (inv_id, inv_no, inv_date)

    sale_rows = (db.query(models.SaleItem.product_id, func.lower(func.coalesce(models.SaleItem.unit_type, "strip")),
                          func.sum(models.SaleItem.quantity), func.sum(models.SaleItem.returned_quantity))
                 .join(models.Sale, models.Sale.id == models.SaleItem.sale_id)
                 .filter(models.Sale.user_id == user_id, models.SaleItem.product_id.in_(ids))
                 .group_by(models.SaleItem.product_id, func.lower(func.coalesce(models.SaleItem.unit_type, "strip"))).all())
    sold, restocked, loose = {}, {}, set()
    for pid, unit, qty, ret in sale_rows:
        if unit in STRIP_UNITS:
            sold[pid] = sold.get(pid, 0) + int(qty or 0)
            restocked[pid] = restocked.get(pid, 0) + int(ret or 0)
        else:
            loose.add(pid)                                   # loose-tablet sales can open strips: quantity can no longer be reconciled

    ret_rows = (db.query(models.PurchaseReturnItem.product_id, models.PurchaseReturn.supplier_id, func.sum(models.PurchaseReturnItem.quantity))
                .join(models.PurchaseReturn, models.PurchaseReturn.id == models.PurchaseReturnItem.purchase_return_id)
                .filter(models.PurchaseReturn.user_id == user_id, models.PurchaseReturnItem.product_id.in_(ids))
                .group_by(models.PurchaseReturnItem.product_id, models.PurchaseReturn.supplier_id).all())
    ret_all, ret_s = {}, {}
    for pid, sid, qty in ret_rows:
        ret_all[pid] = ret_all.get(pid, 0) + int(qty or 0)
        if sid == supplier_id:
            ret_s[pid] = int(qty or 0)

    term = (q or "").strip().lower()
    out = []
    for pid in ids:
        p = products.get(pid)
        if not p:
            continue
        if term and term not in f"{p.product_name} {p.brand or ''} {p.batch_number or ''}".lower():
            continue
        on_hand = int(p.quantity or 0)
        received_total = recv_all.get(pid, 0)
        sold_net = sold.get(pid, 0) - restocked.get(pid, 0)
        reconciled = received_total > 0 and pid not in loose and (received_total - sold_net - ret_all.get(pid, 0)) == on_hand
        single = suppliers_of.get(pid, set()) == {supplier_id}
        attributable = reconciled and single
        st, note = classify(on_hand, p.expiry_date, reconciled, attributable, sold_net, ret_s.get(pid, 0), ret_all.get(pid, 0) - ret_s.get(pid, 0), today)
        inv = last_inv.get(pid)
        out.append({
            "product_id": pid, "product_name": p.product_name, "company": p.brand, "batch_number": p.batch_number,
            "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None, "mrp": p.unit_price,
            "purchase_id": inv[0] if inv else None, "invoice_number": inv[1] if inv else None,
            "purchase_date": inv[2].isoformat() if inv and inv[2] else None,
            "quantity_received": recv_s.get(pid) if pid in recv_s else None,
            "batch_received_total": received_total or None,
            "quantity_sold": sold_net if attributable else None,
            "quantity_returned": ret_s.get(pid, 0) if attributable else None,
            "available": on_hand, "status": st, "status_note": note,
            "shared_batch": len(suppliers_of.get(pid, set()) - {supplier_id}) > 0,
            "reconciled": reconciled,
            "source_recorded": pid in recv_s,
        })
    counts = {}
    for r in out:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    if status:
        out = [r for r in out if r["status"].lower() == status.strip().lower()]
    out.sort(key=lambda r: (r["product_name"].lower(), r["expiry_date"] or ""))
    total = len(out)
    return {"items": out[(page - 1) * page_size: page * page_size], "total": total, "page": page, "page_size": page_size,
            "counts": counts, "notes": _notes()}


def _notes() -> list:
    return [
        "Quantity received includes free units (they are not stored separately).",
        "Sold and returned quantities are shown only for a batch that this supplier alone delivered and whose recorded movements "
        "add up to the quantity on hand. DawaiFlow does not record which supplier's units a sale used, so shared or adjusted "
        "batches show only the available quantity.",
        "Purchase drafts are not received stock and never appear here.",
    ]
