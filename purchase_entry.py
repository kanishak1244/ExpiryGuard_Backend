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
import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Session

import crud
import models
import purchase_calc
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
    discount_amount: float = Field(default=0.0, ge=0, le=10_000_000)      # a fixed discount on this line (rupees)
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
    invoice_discount_percent: float = Field(default=0.0, ge=0, le=100)   # one invoice-level discount: percent OR amount
    invoice_discount_amount: float = Field(default=0.0, ge=0, le=1_000_000_000)
    other_charges: float = Field(default=0.0, ge=0, le=1_000_000_000)    # freight / other charges
    other_charges_gst: float = Field(default=0.0, ge=0, le=28)
    interstate: bool = False                                              # IGST instead of CGST + SGST
    prices_include_gst: bool = False                                      # rates already contain GST
    round_to_rupee: bool = False                                          # supplier rounds the payable to the nearest rupee
    printed_total: Optional[float] = Field(default=None, ge=0)            # what the supplier printed (reconciliation only)
    draft_id: Optional[int] = Field(default=None, ge=1)             # the saved draft this purchase finalizes (marked FINALIZED with the posting)
    items: List[ManualPurchaseLine] = Field(min_length=1, max_length=MAX_LINES)

    @field_validator("invoice_number")
    @classmethod
    def _strip_inv(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("must not be blank")
        return v


def calc_line(qty, free, rate, discount_percent, gst_rate) -> dict:
    """Amounts of one line, from the one calculation (purchase_calc). Kept for the draft estimate and the tests."""
    c = purchase_calc.calc_invoice([{"qty": qty, "free": free, "rate": rate, "disc_percent": discount_percent, "gst_rate": gst_rate}])
    ln = c["lines"][0]
    return {"gross": ln["gross"], "discount": ln["line_discount"], "taxable": ln["taxable"], "gst": ln["tax"], "total": ln["total"],
            "received_qty": ln["received_qty"], "net_unit_cost": ln["net_unit_cost"]}


def calc_totals(lines: List[dict]) -> dict:
    r = crud._round_half_up
    return {
        "subtotal": r(sum(l["gross"] for l in lines), 2),
        "discount": r(sum(l["discount"] for l in lines), 2),
        "taxable": r(sum(l["taxable"] for l in lines), 2),
        "gst": r(sum(l["gst"] for l in lines), 2),
        "total": r(sum(l["total"] for l in lines), 2),
    }


class CalcLine(BaseModel):
    quantity: float = Field(default=0, ge=0, le=1_000_000)
    free_quantity: float = Field(default=0, ge=0, le=1_000_000)
    purchase_rate: float = Field(default=0, ge=0, le=10_000_000)
    discount_percent: float = Field(default=0.0, ge=0, le=100)
    discount_amount: float = Field(default=0.0, ge=0, le=10_000_000)
    gst_rate: float = Field(default=12.0, ge=0, le=28)


class CalcRequest(BaseModel):
    """Everything the calculation needs and nothing else, so an unfinished screen can be previewed."""
    items: List[CalcLine] = Field(default_factory=list, max_length=MAX_LINES)
    invoice_discount_percent: float = Field(default=0.0, ge=0, le=100)
    invoice_discount_amount: float = Field(default=0.0, ge=0, le=1_000_000_000)
    other_charges: float = Field(default=0.0, ge=0, le=1_000_000_000)
    other_charges_gst: float = Field(default=0.0, ge=0, le=28)
    interstate: bool = False
    prices_include_gst: bool = False
    round_to_rupee: bool = False
    printed_total: Optional[float] = Field(default=None, ge=0)


def calculate(data) -> dict:
    """The authoritative calculation of a purchase (manual, OCR, draft or preview): lines, tax groups, totals and reconciliation."""
    try:
        calc = purchase_calc.calc_invoice(
            [{"qty": l.quantity, "free": l.free_quantity, "rate": l.purchase_rate, "disc_percent": l.discount_percent,
              "disc_amount": l.discount_amount, "gst_rate": l.gst_rate} for l in data.items],
            invoice_discount_percent=data.invoice_discount_percent, invoice_discount_amount=data.invoice_discount_amount,
            other_charges=data.other_charges, other_charges_gst=data.other_charges_gst, interstate=data.interstate,
            prices_include_gst=data.prices_include_gst, round_to_rupee=data.round_to_rupee)
    except purchase_calc.CalcError as exc:
        raise HTTPException(status_code=422, detail=f"CALC_INVALID: {exc}")
    calc["reconciliation"] = purchase_calc.reconcile(calc, {"total": data.printed_total} if data.printed_total is not None else None)
    return calc


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


def _like_escape(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_medicines(db: Session, user_id: int, q: str, limit: int = 12) -> list:
    """
    Medicine-master suggestions for the manual purchase grid. Read-only, server-side, indexed.

    The master is every medicine this shop ever registered (every non-deleted stock record, WHATEVER its stock: zero,
    out of stock, expired, no live batch) plus the global catalog. Stock is never used as a filter.
    A medicine appears once. Names that START with the text come first, then names that contain it, then matches on
    manufacturer / composition. Only reusable medicine data is returned (name, manufacturer, composition, pack, HSN, GST
    and the previous purchase rate / MRP as REFERENCE); no batch number, expiry, quantity or any other batch data.
    """
    term = (q or "").strip()
    if len(term) < 2:
        return []
    limit = max(1, min(int(limit or 12), 30))
    esc_term = _like_escape(term.lower())
    contains, prefix = f"%{esc_term}%", f"{esc_term}%"
    P, C = models.Product, models.MedicineCatalog

    def rank(name_col):
        return case((name_col.ilike(prefix, escape="\\"), 0), (name_col.ilike(contains, escape="\\"), 1), else_=2)

    # --- this shop's medicines: one row per medicine name, best rank first
    key = func.lower(func.trim(P.product_name))
    shop_rank = rank(P.product_name)
    names = (
        db.query(key.label("k"), func.min(shop_rank).label("r"))
        .filter(P.user_id == user_id, P.is_deleted == False, or_(
            P.product_name.ilike(contains, escape="\\"), func.coalesce(P.brand, "").ilike(contains, escape="\\"),
            func.coalesce(P.composition, "").ilike(contains, escape="\\"), func.coalesce(P.barcode, "") == term))
        .group_by(key).order_by(func.min(shop_rank), key).limit(limit).all()
    )
    shop_out = []
    if names:
        ranks = {n.k: n.r for n in names}
        rows = (db.query(P).filter(P.user_id == user_id, P.is_deleted == False, key.in_(list(ranks)))
                .order_by(P.id.desc()).all())                       # newest record first
        by_name = {}
        for p in rows:
            by_name.setdefault(p.product_name.strip().lower(), []).append(p)
        for k, plist in by_name.items():
            latest = plist[0]
            pick = lambda attr: next((getattr(x, attr) for x in plist if getattr(x, attr)), None)   # newest non-empty value
            rate, mrp = pick("purchase_price"), pick("unit_price")
            shop_out.append((ranks.get(k, 2), 0, k, {
                "source": "shop", "product_id": latest.id, "catalog_id": None, "product_name": latest.product_name,
                "brand": pick("brand"), "composition": pick("composition"), "pack_size_label": pick("pack_size_label"),
                "units_per_pack": pick("units_per_pack") or pick("tablets_per_strip"), "hsn_code": latest.hsn_code,
                "gst_rate": latest.gst_rate, "barcode": pick("barcode"),
                "last_purchase_rate": rate, "mrp": mrp, "selling_rate": mrp,     # the selling rate is the MRP in DawaiFlow
                "batches": [],                                                   # batch data is never suggested
            }))
    seen = {k for _, _, k, _ in shop_out}

    # --- global catalog, medicines this shop does not have
    cat_rank = rank(C.product_name)
    catalog = (
        db.query(C, cat_rank.label("r"))
        .filter(or_(C.product_name.ilike(contains, escape="\\"), func.coalesce(C.brand, "").ilike(contains, escape="\\"),
                    func.coalesce(C.composition, "").ilike(contains, escape="\\")))
        .order_by(cat_rank, C.product_name).limit(limit + len(seen)).all()
    )
    cat_out = []
    for c, r in catalog:
        k = c.product_name.strip().lower()
        if k in seen:
            continue
        seen.add(k)
        cat_out.append((r, 1, k, {
            "source": "catalog", "product_id": None, "catalog_id": c.id, "product_name": c.product_name, "brand": c.brand,
            "composition": c.composition, "pack_size_label": c.pack_size_label,
            "units_per_pack": c.units_per_pack or c.tablets_per_strip, "hsn_code": c.hsn_code, "gst_rate": c.gst_rate,
            "barcode": None, "last_purchase_rate": None, "mrp": c.default_price or None, "selling_rate": c.default_price or None,
            "batches": [],
        }))
    merged = sorted(shop_out + cat_out, key=lambda x: (x[0], x[1], x[2]))
    return [m[3] for m in merged[:limit]]


def ensure_search_indexes() -> None:
    """
    Trigram (pg_trgm) indexes so '%text%' suggestions stay fast with 50,000+ medicines. PostgreSQL only; every statement is
    IF NOT EXISTS and a failure is logged and ignored (search still works, just slower).
    """
    try:
        from database import engine
        if engine.dialect.name != "postgresql":
            return
        stmts = [
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
            "CREATE INDEX IF NOT EXISTS idx_products_trgm_name ON products USING gin (product_name gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS idx_products_trgm_brand ON products USING gin (brand gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS idx_products_trgm_comp ON products USING gin (composition gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_name ON medicine_catalog USING gin (product_name gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_brand ON medicine_catalog USING gin (brand gin_trgm_ops)",
            "CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_comp ON medicine_catalog USING gin (composition gin_trgm_ops)",
        ]
        for sql in stmts:
            try:
                with engine.begin() as conn:
                    conn.execute(text(sql))
            except Exception as e:                       # e.g. extension not permitted: keep going, search still works
                logger.warning("[Search indexes] %s -> %s", sql.split(" ON ")[0][:70], str(e)[:120])
    except Exception as e:
        logger.warning("[Search indexes] skipped: %s", str(e)[:120])


def _bad(detail: str, code: int = 400):
    raise HTTPException(status_code=code, detail=detail)


def post_manual_purchase(db: Session, user_id: int, data: ManualPurchaseCreate, document_id: Optional[int] = None,
                         override_reason: Optional[str] = None) -> dict:
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
        calc = calculate(data)
        calcs = calc["lines"]
        ct = calc["totals"]
        totals = {"subtotal": ct["gross"], "discount": ct["discount"], "invoice_discount": ct["invoice_discount"], "taxable": ct["taxable"],
                  "gst": ct["tax"], "cgst": ct["cgst"], "sgst": ct["sgst"], "igst": ct["igst"], "other_charges": ct["other_charges"],
                  "round_off": ct["round_off"], "total": ct["payable"]}
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
        snapshot = {"totals": calc["totals"], "tax_groups": calc["tax_groups"], "policy": calc["policy"], "reconciliation": calc["reconciliation"],
                    "inputs": {"invoice_discount_percent": data.invoice_discount_percent, "invoice_discount_amount": data.invoice_discount_amount,
                               "other_charges": data.other_charges, "interstate": data.interstate, "prices_include_gst": data.prices_include_gst,
                               "round_to_rupee": data.round_to_rupee},
                    "posted_by": user_id, "posted_at": datetime.utcnow().isoformat() + "Z", "purchase_id": invoice.id}
        if override_reason:
            snapshot["override"] = {"reason": override_reason, "by": user_id, "at": snapshot["posted_at"],
                                    "printed_total": calc["reconciliation"].get("printed_total"), "calculated_total": ct["payable"],
                                    "difference": calc["reconciliation"].get("difference")}
        if data.draft_id or document_id:
            import purchase_drafts                       # drafts finalize in this same transaction, never separately
            purchase_drafts.mark_finalized(db, user_id, invoice.id, draft_id=data.draft_id, document_id=document_id, calculation=snapshot)

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
            try:
                parsed = json.loads(doc.ocr_raw_json) if doc.ocr_raw_json else {}
                parsed = parsed if isinstance(parsed, dict) else {}
            except ValueError:
                parsed = {}
            parsed["calculation"] = snapshot
            if override_reason:
                parsed.setdefault("override_audit", []).append(snapshot["override"])
            doc.ocr_raw_json = json.dumps(parsed, default=str)
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
        "reconciliation": calc["reconciliation"],
    }
