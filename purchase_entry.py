"""
Manual purchase entry (Purchase Management > Add Manually).

One server-side engine, one database transaction:
  checks the supplier and the supplier's invoice number (no duplicates), recalculates every amount here (the browser's
  numbers are only a preview), adds each line to its batch through crud.add_real_inventory_item (same batch rules as
  every other stock entry), writes the purchase document + lines + one stock-ledger row per line.
  The supplier balance is not stored: the ledger derives it from the purchase document (UNPAID owes, PAID does not).

Money rules (tax-exclusive, the only mode the system has):
  taxable = qty x rate - discount%      GST = taxable x gst%      line total = taxable + GST
  Free units are received at no charge: stock += qty + free, and the cost per received unit = taxable / (qty + free).
  The document stores the received quantity and that net unit cost, so quantity x unit cost always equals the taxable
  value. The original rate, discount % and free split are not stored on the document (no columns for them yet).
Nothing here is called by the list/detail screens; viewing never posts.
"""
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import crud
import models
import schemas

logger = logging.getLogger("expiryguard.purchase_entry")

MAX_LINES = 200


class ManualPurchaseLine(BaseModel):
    product_id: Optional[int] = Field(default=None, ge=1)     # an existing batch row of the medicine (copies its master data)
    product_name: str = Field(min_length=2, max_length=200)
    brand: Optional[str] = Field(default=None, max_length=200)
    composition: Optional[str] = Field(default=None, max_length=300)
    pack_size_label: Optional[str] = Field(default=None, max_length=100)
    units_per_pack: Optional[int] = Field(default=None, ge=1, le=1000)
    hsn_code: Optional[str] = Field(default=None, max_length=12)
    barcode: Optional[str] = Field(default=None, max_length=64)
    batch_number: str = Field(min_length=1, max_length=60)
    manufacturing_date: Optional[date] = None
    expiry_date: date
    quantity: int = Field(gt=0, le=1_000_000)
    free_quantity: int = Field(default=0, ge=0, le=1_000_000)
    purchase_rate: float = Field(ge=0, le=10_000_000)
    discount_percent: float = Field(default=0.0, ge=0, le=100)
    gst_rate: float = Field(default=12.0, ge=0, le=28)
    mrp: float = Field(gt=0, le=10_000_000)
    confirm_mrp_below_cost: bool = False

    @field_validator("product_name", "batch_number")
    @classmethod
    def _strip(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class ManualPurchaseCreate(BaseModel):
    supplier_id: int = Field(ge=1)
    invoice_number: str = Field(min_length=1, max_length=60)
    invoice_date: date
    payment_status: str = Field(default="UNPAID", pattern="^(?i:UNPAID|PAID)$")
    expected_total: Optional[float] = Field(default=None, ge=0)     # what the screen showed; refused if the server differs
    items: List[ManualPurchaseLine] = Field(min_length=1, max_length=MAX_LINES)

    @field_validator("invoice_number")
    @classmethod
    def _strip_inv(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be blank")
        return v


def calc_line(qty, free, rate, discount_percent, gst_rate) -> dict:
    """Amounts of one line (the single formula; the browser mirrors it in web/js/purchase_entry_core.js)."""
    r = crud._round_half_up
    gross = r(float(qty) * float(rate), 2)
    discount = r(gross * float(discount_percent or 0) / 100.0, 2)
    taxable = r(gross - discount, 2)
    gst = r(taxable * float(gst_rate or 0) / 100.0, 2)
    received = int(qty) + int(free or 0)
    return {
        "gross": gross, "discount": discount, "taxable": taxable, "gst": gst, "total": r(taxable + gst, 2),
        "received_qty": received, "net_unit_cost": r(taxable / received, 4) if received else 0.0,
    }


def calc_totals(lines: List[dict]) -> dict:
    r = crud._round_half_up
    return {
        "subtotal": r(sum(l["gross"] for l in lines), 2),
        "discount": r(sum(l["discount"] for l in lines), 2),
        "taxable": r(sum(l["taxable"] for l in lines), 2),
        "gst": r(sum(l["gst"] for l in lines), 2),
        "total": r(sum(l["total"] for l in lines), 2),
    }


def _norm_invoice(v: str) -> str:
    return (v or "").strip().lower()


def find_duplicate_invoice(db: Session, user_id: int, supplier_id: int, invoice_number: str):
    return db.query(models.PurchaseInvoice).filter(
        models.PurchaseInvoice.user_id == user_id,
        models.PurchaseInvoice.supplier_id == supplier_id,
        func.lower(func.trim(models.PurchaseInvoice.invoice_number)) == _norm_invoice(invoice_number),
    ).first()


def check_duplicate(db: Session, user_id: int, supplier_id: int, invoice_number: str) -> dict:
    dup = find_duplicate_invoice(db, user_id, supplier_id, invoice_number) if (invoice_number or "").strip() else None
    return {
        "is_duplicate": bool(dup),
        "purchase_id": dup.id if dup else None,
        "voucher_no": crud.purchase_voucher_no(dup.id) if dup else None,
        "invoice_date": dup.invoice_date.isoformat() if dup and dup.invoice_date else None,
        "total_amount": round(float(dup.total_amount or 0.0), 2) if dup else None,
    }


def search_medicines(db: Session, user_id: int, q: str, limit: int = 12) -> list:
    """
    Suggestions for the medicine cell: this shop's medicines first (with their batches, last cost, MRP and pack data),
    then catalog medicines the shop does not have yet. Read-only.
    """
    term = (q or "").strip()
    if len(term) < 2:
        return []
    like = f"%{term.lower()}%"
    P = models.Product
    rows = (
        db.query(P).filter(P.user_id == user_id, P.is_deleted == False, or_(
            func.lower(P.product_name).like(like), func.lower(func.coalesce(P.brand, "")).like(like),
            func.lower(func.coalesce(P.composition, "")).like(like), func.coalesce(P.barcode, "") == term))
        .order_by(P.product_name, P.expiry_date.desc()).limit(200).all()
    )
    by_name = {}
    for p in rows:
        key = p.product_name.strip().lower()
        entry = by_name.get(key)
        if entry is None:
            if len(by_name) >= limit:
                continue
            entry = by_name[key] = {
                "source": "shop", "product_id": p.id, "catalog_id": None, "product_name": p.product_name, "brand": p.brand,
                "composition": p.composition, "pack_size_label": p.pack_size_label,
                "units_per_pack": p.units_per_pack or p.tablets_per_strip, "hsn_code": p.hsn_code,
                "gst_rate": p.gst_rate, "barcode": p.barcode, "last_purchase_rate": p.purchase_price,
                "mrp": p.unit_price, "batches": [],
            }
        if len(entry["batches"]) < 8:
            entry["batches"].append({
                "product_id": p.id, "batch_number": p.batch_number, "expiry_date": p.expiry_date.isoformat() if p.expiry_date else None,
                "quantity": p.quantity, "mrp": p.unit_price, "purchase_price": p.purchase_price,
            })
    out = list(by_name.values())
    if len(out) < limit:
        C = models.MedicineCatalog
        catalog = (
            db.query(C).filter(or_(func.lower(C.product_name).like(like), func.lower(func.coalesce(C.brand, "")).like(like),
                                   func.lower(func.coalesce(C.composition, "")).like(like)))
            .order_by(func.lower(C.product_name).like(term.lower() + "%").desc(), C.product_name).limit(limit).all()
        )
        for c in catalog:
            if c.product_name.strip().lower() in by_name:
                continue
            out.append({
                "source": "catalog", "product_id": None, "catalog_id": c.id, "product_name": c.product_name, "brand": c.brand,
                "composition": c.composition, "pack_size_label": c.pack_size_label,
                "units_per_pack": c.units_per_pack or c.tablets_per_strip, "hsn_code": c.hsn_code, "gst_rate": c.gst_rate,
                "barcode": None, "last_purchase_rate": None, "mrp": c.default_price or None, "batches": [],
            })
            if len(out) >= limit:
                break
    return out


def _bad(detail: str, code: int = 400):
    raise HTTPException(status_code=code, detail=detail)


def post_manual_purchase(db: Session, user_id: int, data: ManualPurchaseCreate, document_id: Optional[int] = None) -> dict:
    """
    Post one purchase. All or nothing: any problem rolls back the document, the stock and the ledger rows together.
    document_id: the scanned supplier invoice this purchase confirms. It is locked, refused if already Verified, linked to
    the stock rows and marked Verified in the SAME transaction (so Verified always means the stock was posted).
    """
    today = date.today()
    if data.invoice_date > today + timedelta(days=1):
        _bad("Invoice date cannot be in the future.")
    try:
        supplier = (
            db.query(models.Supplier)
            .filter(models.Supplier.id == data.supplier_id, models.Supplier.user_id == user_id)
            .with_for_update().first()               # serialises two posts for the same supplier (Postgres)
        )
        doc = None
        if document_id:
            doc = (db.query(models.Document).filter(models.Document.id == document_id, models.Document.user_id == user_id)
                   .with_for_update().first())
            if not doc:
                _bad("Document not found.", 404)
            if str(doc.ocr_status or "").lower() == "verified":
                _bad("ALREADY_VERIFIED: This invoice was already confirmed and its stock added. Nothing was posted again.", 409)
        if not supplier:
            _bad("Supplier not found or access denied.", 404)
        if str(supplier.status or "Active").lower() == "inactive":
            _bad("This supplier is inactive. Re-activate it before posting a purchase.")
        dup = find_duplicate_invoice(db, user_id, data.supplier_id, data.invoice_number)
        if dup:
            _bad(f"DUPLICATE_INVOICE: Invoice {data.invoice_number} of {supplier.name} is already saved as "
                 f"{crud.purchase_voucher_no(dup.id)}. Open it instead of posting it again.", 409)

        # recalculate every amount here and compare with what the screen showed
        calcs = [calc_line(l.quantity, l.free_quantity, l.purchase_rate, l.discount_percent, l.gst_rate) for l in data.items]
        totals = calc_totals(calcs)
        if data.expected_total is not None and abs(totals["total"] - float(data.expected_total)) > 0.01:
            _bad(f"TOTAL_MISMATCH: The server calculated ₹{totals['total']:.2f} but the screen showed "
                 f"₹{float(data.expected_total):.2f}. Check the rates and refresh before saving.", 409)

        P = models.Product
        for n, l in enumerate(data.items, 1):
            if l.expiry_date < today:
                _bad(f"Row {n}: {l.product_name} batch {l.batch_number} is already expired ({l.expiry_date}).")
            if l.manufacturing_date and l.manufacturing_date >= l.expiry_date:
                _bad(f"Row {n}: manufacturing date must be before the expiry date.")
        # the same batch twice on one bill must agree on the expiry
        seen = {}
        for n, l in enumerate(data.items, 1):
            key = (l.product_name.lower(), l.batch_number.lower())
            if key in seen and seen[key] != l.expiry_date:
                _bad(f"Row {n}: batch {l.batch_number} of {l.product_name} appears twice with different expiry dates.")
            seen[key] = l.expiry_date

        invoice = models.PurchaseInvoice(
            user_id=user_id, supplier_id=supplier.id, invoice_number=data.invoice_number, invoice_date=data.invoice_date,
            total_amount=totals["total"], tax_amount=totals["gst"], payment_status=data.payment_status.upper(),
        )
        db.add(invoice)
        db.flush()

        stamp = f"{datetime.utcnow():%Y%m%d%H%M%S}"
        saved_lines = []
        for n, (l, c) in enumerate(zip(data.items, calcs), 1):
            template = db.query(P).filter(P.id == l.product_id, P.user_id == user_id).first() if l.product_id else None
            if l.product_id and not template:
                _bad(f"Row {n}: medicine #{l.product_id} was not found in your inventory.", 404)
            name = (template.product_name if template else l.product_name).strip()
            if not template:
                template = (db.query(P).filter(P.user_id == user_id, P.is_deleted == False,
                                               func.lower(P.product_name) == name.lower()).order_by(P.id.desc()).first())

            same_batch = (
                db.query(P).filter(P.user_id == user_id, P.is_deleted == False, func.lower(P.product_name) == name.lower(),
                                   func.lower(P.batch_number) == l.batch_number.lower()).with_for_update().all()
            )
            existing = next((p for p in same_batch if p.expiry_date == l.expiry_date), None)
            if same_batch and not existing:
                other = same_batch[0]
                _bad(f"Row {n}: batch {l.batch_number} of {name} already exists with expiry {other.expiry_date}. "
                     f"Check the expiry date, or use a different batch number.")

            units = l.units_per_pack or (template.units_per_pack or template.tablets_per_strip if template else None) or 10
            req = schemas.InventoryAddRequest(
                product_name=name, brand=l.brand or (template.brand if template else None),
                category=(template.category if template else None) or "allopathy",
                hsn_code=l.hsn_code or (template.hsn_code if template else None) or "3004",
                gst_rate=l.gst_rate, batch_number=existing.batch_number if existing else l.batch_number,
                quantity=c["received_qty"],
                purchase_price=c["net_unit_cost"], mrp=l.mrp, confirm_mrp_below_cost=l.confirm_mrp_below_cost,
                units_per_pack=units, expiry_date=l.expiry_date.isoformat(),
                manufacturing_date=l.manufacturing_date.isoformat() if l.manufacturing_date else None,
                supplier_id=supplier.id, invoice_number=data.invoice_number, document_id=document_id, duplicate_mode="auto",
            )
            was_new = existing is None
            prod = crud.add_real_inventory_item(db, req, user_id, do_commit=False)
            db.flush()
            prod.gst_rate = l.gst_rate                 # add_real_inventory_item reads 0% as "missing" and stores 12
            prod.gst_percentage = l.gst_rate
            if was_new:
                prod.composition = l.composition or (template.composition if template else None)
                prod.barcode = l.barcode or (template.barcode if template else None)
                prod.pack_size_label = l.pack_size_label or (template.pack_size_label if template else None)
            elif l.manufacturing_date and not prod.manufacturing_date:
                prod.manufacturing_date = l.manufacturing_date

            db.add(models.PurchaseItem(
                purchase_invoice_id=invoice.id, product_id=prod.id, batch_number=l.batch_number,
                quantity=c["received_qty"], purchase_price=c["net_unit_cost"], mrp=l.mrp, gst_rate=l.gst_rate,
                expiry_date=l.expiry_date,
            ))
            db.add(models.InventoryTransaction(
                transaction_id=f"PUR-{invoice.id}-{n}-{stamp}-{uuid.uuid4().hex[:6].upper()}",
                shop_id=user_id, product_id=prod.id, transaction_type="purchase", quantity=c["received_qty"],
                unit_price=l.mrp, purchase_price=c["net_unit_cost"], total_price=c["taxable"], final_price=c["taxable"],
            ))
            saved_lines.append({"row": n, "product_id": prod.id, "product_name": prod.product_name,
                                "batch_number": prod.batch_number, "new_batch": was_new, "received_qty": c["received_qty"],
                                "stock_after": prod.quantity, **c})

        if doc is not None:
            doc.supplier_id = supplier.id
            doc.invoice_number = data.invoice_number
            doc.invoice_date = data.invoice_date
            doc.item_count = len(saved_lines)
            doc.ocr_status = "Verified"
        db.commit()
    except Exception:
        db.rollback()
        raise

    crud.invalidate_products_cache(user_id)
    logger.info("manual purchase posted: user=%s supplier=%s invoice=%s id=%s total=%.2f lines=%d",
                user_id, data.supplier_id, data.invoice_number, invoice.id, totals["total"], len(saved_lines))
    return {
        "id": invoice.id, "voucher_no": crud.purchase_voucher_no(invoice.id), "invoice_number": invoice.invoice_number,
        "supplier_id": supplier.id, "supplier_name": supplier.name, "payment_status": invoice.payment_status,
        "totals": totals, "total_amount": totals["total"], "items_count": len(saved_lines), "lines": saved_lines,
    }
