"""
Counter Sale: many walk-in customers entered quickly on the billing screen, each kept as its own transaction.

Lifecycle of one customer transaction (stored on the existing held-bill tables: no new table, no migration):
  DRAFT      the cashier is still entering it. Lives only on the billing screen (browser), never touches the server.
  READY      "Finish customer": saved on the server as a HELD bill whose notes carry the COUNTER marker.
             Stock is NOT deducted, no sale exists, reports are unaffected (held bills never do that).
  CONVERTED  "Convert to Bill": ONE regular sales invoice was created by the normal billing code (stock checked and
             deducted there, invoice number from the normal numbering). The held row becomes COMPLETED and keeps
             completed_sale_id, so the transaction and its invoice stay linked forever.
  CANCELLED  discarded while READY (the row stays as history).

Stock is deducted only by create_sale_transaction, once, when the invoice is created. Converting again returns the same
invoice (the invoice's idempotency key is derived from the held bill id, and a COMPLETED row is never converted twice).
"""
import json
import logging
from datetime import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

import crud
import models
import schemas

logger = logging.getLogger("expiryguard.counter_sale")

COUNTER_PREFIX = "COUNTER:"


def counter_marker(txn_id: str, ref: str) -> str:
    return f"{COUNTER_PREFIX}{txn_id}:{ref}"


def is_counter(held: models.HeldBill) -> bool:
    return bool(held and held.notes and str(held.notes).startswith(COUNTER_PREFIX))


def _parse_marker(notes: Optional[str]):
    parts = str(notes or "").split(":", 2)
    return (parts[1], parts[2]) if len(parts) == 3 else ("", "")


def counter_status(held: models.HeldBill) -> str:
    return {"HELD": "READY", "RESUMED": "READY", "COMPLETED": "CONVERTED", "CANCELLED": "CANCELLED"}.get(held.status, held.status)


def _snapshot_percent(held: models.HeldBill) -> list:
    try:
        return [(i or {}).get("discount_percent") for i in (json.loads(held.snapshot_json or "{}").get("items") or [])]
    except Exception:
        return []


def exact_total(held: models.HeldBill) -> float:
    """The invoice amount of these lines, with the invoice's own arithmetic (per-line CGST/SGST rounding), so the total
    shown for a READY transaction is the amount its invoice will have. (estimated_total is a rougher held-bill estimate.)"""
    r = crud._round_half_up
    total = 0.0
    for i in held.items:
        gross = r((i.quantity or 0) * (i.unit_price or 0.0), 2)
        taxable = max(0.0, r(gross - (i.discount or 0.0), 2))
        cgst = r(taxable * (r((i.gst_percentage or 0.0) / 2, 2) / 100), 2)
        total += r(taxable + cgst * 2, 2)
    return r(total, 2)


def view(db: Session, held: models.HeldBill, include_items: bool = False) -> dict:
    txn_id, ref = _parse_marker(held.notes)
    invoice = None
    if held.completed_sale_id:
        invoice = db.query(models.Sale.bill_number).filter(models.Sale.id == held.completed_sale_id).scalar()
    out = {
        "id": held.id,
        "txn_id": txn_id,
        "ref": ref,
        "status": counter_status(held),
        "held_bill_number": held.held_bill_number,
        "customer_name": held.customer_name,
        "customer_phone": held.customer_phone,
        "items_count": len(held.items),
        "estimated_total": held.estimated_total,
        "total": exact_total(held),
        "created_at": held.created_at.isoformat() + "Z" if held.created_at else None,
        "completed_at": held.completed_at.isoformat() + "Z" if held.completed_at else None,
        "completed_sale_id": held.completed_sale_id,
        "invoice_number": invoice,
    }
    if include_items:
        ids = [i.product_id for i in held.items]
        prods = {p.id: p for p in db.query(models.Product).filter(
            models.Product.id.in_(ids), models.Product.user_id == held.user_id).all()} if ids else {}
        pcts = _snapshot_percent(held)
        items = []
        for idx, it in enumerate(held.items):
            p = prods.get(it.product_id)
            items.append({
                "product_id": it.product_id,
                "product_name": it.product_name,
                "batch_number": it.batch_number,
                "expiry_date": it.expiry_date,
                "quantity": it.quantity,
                "unit_type": it.unit_type,
                "unit_price": it.unit_price,
                "discount": it.discount,
                "discount_percent": pcts[idx] if idx < len(pcts) else None,
                "tablets_per_strip": it.tablets_per_strip,
                "hsn_code": it.hsn_code,
                "gst_percentage": it.gst_percentage,
                "estimated_line_total": it.estimated_line_total,
                # what the batch looks like NOW (the screen re-validates it when the transaction is reopened)
                "live": None if p is None else {
                    "mrp": p.unit_price, "price_per_unit": p.price_per_unit or p.loose_tablet_price,
                    "units_per_pack": p.units_per_pack or p.tablets_per_strip, "stock": p.quantity,
                    "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
                    "brand": p.brand, "composition": p.composition, "pack_size_label": p.pack_size_label,
                    "is_expired": crud.is_batch_expired(p.expiry_date),
                },
            })
        out["items"] = items
    return out


def _find_by_txn(db: Session, user_id: int, txn_id: str) -> Optional[models.HeldBill]:
    return (
        db.query(models.HeldBill)
        .options(joinedload(models.HeldBill.items))
        .filter(models.HeldBill.user_id == user_id, models.HeldBill.notes.like(f"{COUNTER_PREFIX}{txn_id}:%"))
        .order_by(models.HeldBill.id.desc())
        .first()
    )


def get(db: Session, user_id: int, held_id: int, lock: bool = False) -> models.HeldBill:
    if lock:                                                # serialises two converts of the same transaction (Postgres)
        db.query(models.HeldBill.id).filter(models.HeldBill.id == held_id, models.HeldBill.user_id == user_id).with_for_update().first()
    held = (db.query(models.HeldBill).options(joinedload(models.HeldBill.items))
            .filter(models.HeldBill.id == held_id, models.HeldBill.user_id == user_id).first())
    if not held or not is_counter(held):
        raise HTTPException(status_code=404, detail="Counter sale transaction not found.")
    return held


def create(db: Session, user_id: int, payload: schemas.CounterTxnCreate) -> dict:
    """'Finish customer': keep this customer's lines on the server as READY. Retrying with the same txn_id never duplicates."""
    existing = _find_by_txn(db, user_id, payload.txn_id)
    if existing is not None and existing.status != "CANCELLED":
        return view(db, existing, include_items=True)
    ref = payload.ref.strip()
    held = crud.create_held_bill(
        db=db,
        bill_data=schemas.HeldBillCreate(
            customer_name=(payload.customer_name or "").strip() or None,
            customer_phone=(payload.customer_phone or "").strip() or None,
            payment_method="CASH",
            notes=counter_marker(payload.txn_id, ref),
            items=payload.items,
        ),
        user_id=user_id,
    )
    if payload.replaces_id:
        old = db.query(models.HeldBill).filter(models.HeldBill.id == payload.replaces_id, models.HeldBill.user_id == user_id).first()
        if old is not None and is_counter(old) and old.status == "HELD" and old.id != held.id:
            old.status = "CANCELLED"                       # the edited version replaces it; the old row stays as history
            old.updated_at = datetime.utcnow()
            db.commit()
    return view(db, get(db, user_id, held.id), include_items=True)


def listing(db: Session, user_id: int, status_filter: str = "READY", search: Optional[str] = None, skip: int = 0, limit: int = 50) -> dict:
    q = db.query(models.HeldBill).filter(models.HeldBill.user_id == user_id, models.HeldBill.notes.like(f"{COUNTER_PREFIX}%"))
    wanted = (status_filter or "ALL").upper()
    if wanted == "READY":
        q = q.filter(models.HeldBill.status.in_(["HELD", "RESUMED"]))
    elif wanted == "CONVERTED":
        q = q.filter(models.HeldBill.status == "COMPLETED")
    elif wanted == "CANCELLED":
        q = q.filter(models.HeldBill.status == "CANCELLED")
    if search and search.strip():
        raw = search.strip().replace("%", "").replace("_", "")
        term = f"%{raw}%"
        q = q.filter(or_(models.HeldBill.notes.ilike(f"{COUNTER_PREFIX}%:%{raw}%"),      # the reference (after the second colon), not the id
                         models.HeldBill.customer_name.ilike(term), models.HeldBill.held_bill_number.ilike(term)))
    total = q.count()
    rows = (q.options(joinedload(models.HeldBill.items)).order_by(models.HeldBill.created_at.desc(), models.HeldBill.id.desc())
            .offset(max(0, skip)).limit(max(1, min(limit, 100))).all())
    return {"items": [view(db, r) for r in rows], "total": total, "skip": skip, "limit": limit}


def cancel(db: Session, user_id: int, held_id: int) -> dict:
    held = get(db, user_id, held_id, lock=True)
    if held.status == "CANCELLED":
        return view(db, held)
    if held.status == "COMPLETED":
        raise HTTPException(status_code=409, detail="This transaction was already converted to a bill and cannot be cancelled.")
    held.status = "CANCELLED"
    held.updated_at = datetime.utcnow()
    db.commit()
    return view(db, held)


def convert(db: Session, user_id: int, held_id: int, payload: schemas.CounterConvert, current_user) -> tuple:
    """
    Convert one READY transaction into a regular invoice. Returns (sale, already_converted).
    Nothing is changed when the invoice cannot be created (expired / not enough stock / price above MRP ...): the
    transaction stays READY with every line as it was, and the normal billing error is returned.
    """
    held = get(db, user_id, held_id, lock=True)
    if held.status == "COMPLETED":
        sale = None
        if held.completed_sale_id:
            sale = db.query(models.Sale).filter(models.Sale.id == held.completed_sale_id, models.Sale.user_id == user_id).first()
        if sale is None:                                    # rows converted before the link was stored: find the invoice by its key
            txn_id, _ref = _parse_marker(held.notes)
            sale = db.query(models.Sale).filter(models.Sale.user_id == user_id,
                                                models.Sale.idempotency_key == f"counter-{held.id}-{txn_id[:12]}").first()
            if sale is not None and not held.completed_sale_id:
                held.completed_sale_id = sale.id
                db.commit()
        if sale is not None:
            return sale, True                               # a retry: the same invoice, never a second one
    if held.status == "CANCELLED":
        raise HTTPException(status_code=409, detail="This transaction was cancelled and cannot be converted.")
    if not held.items:
        raise HTTPException(status_code=422, detail="This transaction has no products.")

    txn_id, ref = _parse_marker(held.notes)
    sale_data = schemas.SaleCreate(
        items=[
            schemas.SaleItemCreate(
                product_id=i.product_id,
                quantity=i.quantity,
                unit_price=i.unit_price,
                unit_type=i.unit_type if i.unit_type in ("strip", "loose_tablet", "loose", "pack", "unit", "pill") else "strip",
                tablets_per_strip=i.tablets_per_strip or None,
                batch_number=i.batch_number,
                discount=i.discount or 0.0,
                gst_percentage=i.gst_percentage,
            )
            for i in held.items
        ],
        payment_method=payload.payment_method,
        customer_name=(payload.customer_name or held.customer_name or "Walk-in Customer"),
        customer_phone=(payload.customer_phone or held.customer_phone),
        notes=f"Counter Sale {ref} ({txn_id[:8]})",
        held_bill_id=held.id,
        idempotency_key=f"counter-{held.id}-{txn_id[:12]}",
    )
    sale = crud.create_sale_transaction(db=db, sale_data=sale_data, user_id=user_id, current_user=current_user)
    return sale, False
