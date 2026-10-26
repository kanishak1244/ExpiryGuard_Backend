"""
Invoice review workflow for scanned supplier bills (Documents & OCR Archive).

  review_view()         one read-only picture of a document: header, supplier link status, lines with their problems,
                        computed totals, and whether it can be confirmed (and why not)
  save_corrections()    store the user's corrections next to the untouched OCR result; never posts stock
  confirm_document()    post the reviewed invoice through the ONE purchase engine (purchase_entry.post_manual_purchase):
                        purchase document, stock, ledger and the Verified status in a single transaction

The OCR result stays in ocr_raw_json exactly as read from the bill; corrections live under its "corrected" key, so the
original reading is never lost and a re-run of OCR cannot silently overwrite them (see routes).
"""
import json
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

import crud
import models
import purchase_entry
from ai import invoice_validation as val

LINE_FIELDS = ("product_name", "brand", "hsn_code", "gst_rate", "batch_number", "expiry_date", "quantity", "free_qty",
               "purchase_price", "mrp", "discount_percent", "total_price", "manufacturing_date")
TOTAL_TOLERANCE_ABS = 5.0
TOTAL_TOLERANCE_PCT = 0.01


def parse_ocr(doc: models.Document) -> dict:
    try:
        data = json.loads(doc.ocr_raw_json) if doc.ocr_raw_json else {}
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def effective(doc: models.Document) -> dict:
    """What the review shows: the user's corrections where saved, otherwise the OCR reading."""
    ocr = parse_ocr(doc)
    cor = ocr.get("corrected") if isinstance(ocr.get("corrected"), dict) else None
    items = (cor.get("items") if cor and isinstance(cor.get("items"), list) else ocr.get("items")) or []
    return {
        "invoice_number": (cor.get("invoice_number") if cor else None) or doc.invoice_number or ocr.get("invoice_number"),
        "invoice_date": (cor.get("invoice_date") if cor else None) or (doc.invoice_date.isoformat() if doc.invoice_date else None) or ocr.get("invoice_date"),
        "printed_total": doc.total_amount if doc.total_amount else ocr.get("total_amount"),
        "items": [i for i in items if isinstance(i, dict)],
        "corrected": bool(cor),
        "corrected_at": cor.get("saved_at") if cor else None,
        "ocr": ocr,
    }


def _num(v) -> Optional[float]:
    return val.to_float(v)


def _line_view(n: int, item: dict) -> dict:
    return {
        "row": n,
        "product_name": (item.get("product_name") or "").strip() or None,
        "hsn_code": item.get("hsn_code"), "gst_rate": _num(item.get("gst_rate") if item.get("gst_rate") is not None else item.get("gst_percentage")),
        "batch_number": (str(item.get("batch_number") or "").strip() or None),
        "expiry_date": item.get("expiry_date"),
        "quantity": _num(item.get("quantity")), "free_qty": _num(item.get("free_qty")),
        "purchase_price": _num(item.get("purchase_price")), "mrp": _num(item.get("mrp")),
        "discount_percent": _num(item.get("discount_percent")), "total_price": _num(item.get("total_price")),
        "field_flags": item.get("field_flags") or {},
    }


def _line_problems(db: Session, user_id: int, line: dict, today: date) -> dict:
    """{blocking: [(field, message)], warnings: [...]} for one line, plus the medicine match."""
    blocking, warnings = [], []
    add = lambda field, msg: blocking.append({"field": field, "message": msg})
    if not line["product_name"]:
        add("product_name", "Medicine name is missing.")
    bad = val.validate_batch(line["batch_number"], line["hsn_code"])
    if bad:
        add("batch_number", f"Batch: {bad}.")
    if line["hsn_code"]:
        bad = val.validate_hsn(line["hsn_code"])
        if bad:
            add("hsn_code", f"HSN: {bad}.")
    iso, why = val.parse_expiry(line["expiry_date"])
    if not iso:
        add("expiry_date", f"Expiry: {why}.")
    elif iso < today.isoformat():
        add("expiry_date", "This batch is already expired.")
    if not line["quantity"] or line["quantity"] <= 0 or line["quantity"] != int(line["quantity"]):
        add("quantity", "Quantity must be a whole number of 1 or more.")
    if line["purchase_price"] is None or line["purchase_price"] < 0:
        add("purchase_price", "Purchase rate is missing.")
    if not line["mrp"] or line["mrp"] <= 0:
        add("mrp", "MRP is missing.")
    if line["gst_rate"] is None or not (0 <= line["gst_rate"] <= 28):
        add("gst_rate", "GST rate is missing or not between 0 and 28.")
    if line["discount_percent"] is not None and not (0 <= line["discount_percent"] <= 100):
        add("discount_percent", "Discount must be between 0 and 100%.")
    for f, why in (line["field_flags"] or {}).items():
        warnings.append({"field": f, "message": str(why)})
    why = val.check_mrp_vs_rate(line["mrp"], line["purchase_price"])
    if why:
        warnings.append({"field": "mrp", "message": why})

    match = {"status": "new", "text": "New medicine (will be created)"}
    if line["product_name"]:
        n = db.query(func.count(models.Product.id)).filter(
            models.Product.user_id == user_id, models.Product.is_deleted == False,
            func.lower(models.Product.product_name) == line["product_name"].lower()).scalar() or 0
        if n:
            match = {"status": "inventory", "text": f"In your inventory ({n} batch{'es' if n != 1 else ''})"}
        else:
            c = db.query(models.MedicineCatalog.id).filter(func.lower(models.MedicineCatalog.product_name) == line["product_name"].lower()).first()
            if c:
                match = {"status": "catalog", "text": "In the medicine catalog"}
    return {"blocking": blocking, "warnings": warnings, "match": match}


def _to_purchase(doc: models.Document, supplier_id: int, eff: dict, lines: List[dict], expected_total: Optional[float] = None,
                 allow_below_cost: bool = False):
    items = []
    for ln in lines:
        iso, _ = val.parse_expiry(ln["expiry_date"])
        mfg = None
        if ln.get("manufacturing_date"):
            mfg, _ = val.parse_expiry(ln["manufacturing_date"])
        it = {
            "product_name": ln["product_name"], "batch_number": ln["batch_number"], "expiry_date": iso,
            "quantity": int(ln["quantity"]), "free_quantity": int(ln["free_qty"] or 0), "purchase_rate": ln["purchase_price"],
            "discount_percent": ln["discount_percent"] or 0.0, "gst_rate": ln["gst_rate"], "mrp": ln["mrp"],
            "confirm_mrp_below_cost": allow_below_cost,
        }
        if ln["hsn_code"]:
            it["hsn_code"] = str(ln["hsn_code"]).strip()
        if mfg:
            it["manufacturing_date"] = mfg
        items.append(it)
    return purchase_entry.ManualPurchaseCreate(
        supplier_id=supplier_id, invoice_number=str(eff["invoice_number"]).strip(), invoice_date=eff["invoice_date"],
        payment_status="UNPAID", expected_total=expected_total, items=items,
    )


def review_view(db: Session, user_id: int, doc: models.Document) -> dict:
    eff = effective(doc)
    today = date.today()
    lines = [_line_view(n, it) for n, it in enumerate(eff["items"], 1)]
    for ln in lines:
        ln.update(_line_problems(db, user_id, ln, today))
    header_block = []
    hb = lambda field, msg: header_block.append({"field": field, "message": msg})

    supplier = db.query(models.Supplier).filter(models.Supplier.id == doc.supplier_id, models.Supplier.user_id == user_id).first() if doc.supplier_id else None
    if not supplier:
        hb("supplier", "Link a supplier before confirming.")
    inv_no = str(eff["invoice_number"] or "").strip()
    if not inv_no:
        hb("invoice_number", "Supplier invoice number is missing.")
    inv_date = None
    try:
        inv_date = datetime.strptime(str(eff["invoice_date"])[:10], "%Y-%m-%d").date() if eff["invoice_date"] else None
    except ValueError:
        inv_date = None
    if not inv_date:
        hb("invoice_date", "Invoice date is missing or not a valid date.")
    elif inv_date > today:
        hb("invoice_date", "Invoice date is in the future.")
    if not lines:
        hb("items", "No medicine lines were extracted.")
    if supplier and inv_no and purchase_entry.find_duplicate_invoice(db, user_id, supplier.id, inv_no):
        hb("invoice_number", f"Invoice {inv_no} of {supplier.name} is already saved as a purchase.")

    calc = [purchase_entry.calc_line(int(l["quantity"] or 0), int(l["free_qty"] or 0), l["purchase_price"] or 0.0,
                                     l["discount_percent"] or 0.0, l["gst_rate"] or 0.0) for l in lines
            if l["quantity"] and l["quantity"] > 0]
    totals = purchase_entry.calc_totals(calc) if calc else None
    notes = []
    printed = _num(eff["printed_total"])
    total_differs = False
    if totals and printed:
        tol = max(TOTAL_TOLERANCE_ABS, TOTAL_TOLERANCE_PCT * printed)
        if abs(totals["total"] - printed) > tol:
            total_differs = True
            notes.append(f"Computed total ₹{totals['total']:.2f} differs from the printed total ₹{printed:.2f}.")
    line_block = sum(len(l["blocking"]) for l in lines)
    verified = str(doc.ocr_status or "").lower() == "verified"
    failed = str(doc.ocr_status or "").lower() == "failed"
    blocking = list(header_block) + [{"field": f"row {l['row']} · {b['field']}", "message": b["message"]} for l in lines for b in l["blocking"]]
    return {
        "id": doc.id, "title": doc.title, "file_type": doc.file_type, "file_size": doc.file_size,
        "uploaded_at": doc.created_at.isoformat() if doc.created_at else None, "status": doc.ocr_status,
        "ocr_error": parse_ocr(doc).get("error") if failed else None,
        "corrected": eff["corrected"], "corrected_at": eff["corrected_at"],
        "supplier": {"id": supplier.id, "name": supplier.name, "gstin": supplier.gstin, "phone": supplier.phone} if supplier else None,
        "supplier_status": "linked" if supplier else ("needs_matching" if eff["ocr"].get("supplier_name") else "unlinked"),
        "extracted_supplier_name": eff["ocr"].get("supplier_name"),
        "invoice_number": inv_no or None, "invoice_date": inv_date.isoformat() if inv_date else (eff["invoice_date"] or None),
        "printed_total": printed, "computed": totals, "total_differs": total_differs, "notes": notes,
        "line_count": len(lines), "lines": lines, "raw_items": eff["items"], "blocking": blocking, "blocking_count": len(blocking),
        "can_confirm": not blocking and not verified and not failed, "can_edit": not verified,
        "verified": verified, "failed": failed,
    }


def save_corrections(db: Session, user_id: int, doc: models.Document, header: dict, items: List[dict]) -> models.Document:
    """Store corrections beside the OCR reading. Posts nothing; refused for a Verified document."""
    if str(doc.ocr_status or "").lower() == "verified":
        raise HTTPException(status_code=409, detail="This invoice is already verified and its stock was added. It can no longer be edited; "
                                                    "use a purchase return for corrections.")
    supplier_id = header.get("supplier_id")
    if supplier_id:
        sup = db.query(models.Supplier).filter(models.Supplier.id == supplier_id, models.Supplier.user_id == user_id).first()
        if not sup:
            raise HTTPException(status_code=404, detail="Supplier not found or access denied.")
    inv_date = header.get("invoice_date")
    if inv_date:
        try:
            datetime.strptime(str(inv_date)[:10], "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invoice date must be YYYY-MM-DD.")
    clean = []
    for n, it in enumerate(items, 1):
        row = {k: it.get(k) for k in LINE_FIELDS if k in it}
        clean.append(row)
    ocr = parse_ocr(doc)
    ocr["corrected"] = {
        "supplier_id": supplier_id, "invoice_number": (header.get("invoice_number") or "").strip() or None,
        "invoice_date": (str(inv_date)[:10] if inv_date else None), "total_amount": header.get("total_amount"),
        "items": clean, "saved_at": datetime.utcnow().isoformat() + "Z", "saved_by": user_id,
    }
    doc.ocr_raw_json = json.dumps(ocr, default=str)
    doc.supplier_id = supplier_id or None
    doc.invoice_number = ocr["corrected"]["invoice_number"]
    if inv_date:
        doc.invoice_date = datetime.strptime(str(inv_date)[:10], "%Y-%m-%d").date()
    if header.get("total_amount") is not None:
        doc.total_amount = float(header.get("total_amount") or 0.0)
    doc.item_count = len(clean)
    if str(doc.ocr_status or "").lower() in ("processing", "failed") and clean:
        doc.ocr_status = "Needs Review"
    db.commit()
    db.refresh(doc)
    return doc


def confirm_document(db: Session, user_id: int, doc: models.Document, acknowledge_warnings: bool = False) -> dict:
    """Confirm & Add to Stock for the document as the review shows it. One transaction, via the purchase engine."""
    status = str(doc.ocr_status or "").lower()
    if status == "verified":
        raise HTTPException(status_code=409, detail="ALREADY_VERIFIED: This invoice was already confirmed and its stock added. Nothing was posted again.")
    if status == "failed":
        raise HTTPException(status_code=409, detail="OCR failed for this document. Edit the bill details by hand and save them first.")
    view = review_view(db, user_id, doc)
    if view["blocking"]:
        first = "; ".join(f"{b['field']}: {b['message']}" for b in view["blocking"][:6])
        raise HTTPException(status_code=422, detail=f"REVIEW_INCOMPLETE: {view['blocking_count']} problem(s) must be fixed first. {first}")
    below_cost = [f"row {l['row']} {l['product_name']}" for l in view["lines"] if any(w["field"] == "mrp" and "lower than the purchase rate" in w["message"] for w in l["warnings"])]
    if (view["total_differs"] or below_cost) and not acknowledge_warnings:
        why = (" ".join(view["notes"]) + (" MRP is below the purchase rate for: " + ", ".join(below_cost) + "." if below_cost else "")).strip()
        raise HTTPException(status_code=409, detail="NEEDS_ACKNOWLEDGEMENT: " + why + " Check the bill, then confirm again to accept.")
    eff = effective(doc)
    lines = [_line_view(n, it) for n, it in enumerate(eff["items"], 1)]
    payload = _to_purchase(doc, doc.supplier_id, {"invoice_number": view["invoice_number"], "invoice_date": view["invoice_date"]}, lines,
                           allow_below_cost=bool(below_cost))
    res = purchase_entry.post_manual_purchase(db, user_id, payload, document_id=doc.id)
    return {"message": f"Invoice confirmed: {res['items_count']} medicine line(s) added to stock as {res['voucher_no']}.", **res}
