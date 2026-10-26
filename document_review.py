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
import purchase_calc
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


def fill_hsn_gst(hsn, gst):
    """
    HSN and GST rate describe the same thing, so one can be filled from the other when a bill printed only one:
    GST from the HSN table, or the usual HSN for that rate. Returns (hsn, gst, note); note says what was filled in.
    Both missing -> (None, None, None): the user must give at least one.
    """
    import crud
    clean = str(hsn or "").strip().replace(".", "")
    table = crud.DEFAULT_HSN_TAX_MAPPINGS
    if clean and gst is None:
        for key in (clean, clean[:6], clean[:4]):
            m = next((x for x in table if x["hsn_code"] == key), None)
            if m:
                return hsn, float(m["gst_rate"]), f"GST {m['gst_rate']:g}% filled in from HSN {key}"
        return hsn, None, None
    if gst is not None and not clean:
        m = next((x for x in table if float(x["gst_rate"]) == float(gst) and x.get("category", "medicine") != "service"), None)
        if m:
            return m["hsn_code"], gst, f"HSN {m['hsn_code']} filled in from GST {gst:g}%"
    return hsn, gst, None


def _line_view(n: int, item: dict) -> dict:
    gst = _num(item.get("gst_rate") if item.get("gst_rate") is not None else item.get("gst_percentage"))
    hsn, gst, filled = fill_hsn_gst(item.get("hsn_code"), gst)
    return {
        "row": n,
        "product_name": (item.get("product_name") or "").strip() or None,
        "hsn_code": hsn, "gst_rate": gst, "tax_filled": filled,
        "batch_number": (str(item.get("batch_number") or "").strip() or None),
        "expiry_date": item.get("expiry_date"),
        "quantity": _num(item.get("quantity")), "free_qty": _num(item.get("free_qty")),
        "purchase_price": _num(item.get("purchase_price")), "mrp": _num(item.get("mrp")),
        "discount_percent": _num(item.get("discount_percent")), "total_price": _num(item.get("total_price")),
        "field_flags": item.get("field_flags") or {},
    }


HEADER_KEYS = ("subtotal", "scheme_amount", "cd_amount", "discount_amount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount",
               "other_amount", "total_amount")


def header_figures(eff: dict) -> dict:
    """What the bill printed in its totals block (OCR), overridden by the user's corrections. Never taken as truth: only compared."""
    ocr, cor = eff["ocr"], (eff["ocr"].get("corrected") or {})
    out = {k: _num(ocr.get(k)) for k in HEADER_KEYS}
    for k in ("discount_amount", "other_amount", "taxable_amount"):
        if cor.get(k) is not None:
            out[k] = _num(cor.get(k))
    disc = out.get("discount_amount") or 0.0
    if not disc and ((out.get("scheme_amount") or 0) or (out.get("cd_amount") or 0)):
        disc = (out.get("scheme_amount") or 0.0) + (out.get("cd_amount") or 0.0)
    out["discount"] = disc or None
    out["printed_total"] = eff.get("printed_total")
    return out


def invoice_inputs(eff: dict, lines: List[dict]) -> dict:
    """
    Decide, from the bill's own figures and without guessing, how the invoice-level parts are calculated:
      discount      the bill's discount is applied once: from the lines if they carry it, else as an invoice discount;
                    both present and different = conflicting, applied from the lines only and reported
      supply        IGST printed (and no CGST/SGST) -> inter-state
      price mode    inclusive only when the printed taxable amount proves it; unclear -> exclusive and reported
      rounding      to the rupee when the printed total is a whole rupee
    """
    h = header_figures(eff)
    cor = eff["ocr"].get("corrected") or {}
    notes = []
    priced = [l for l in lines if l["quantity"] and l["quantity"] > 0]
    line_disc = 0.0
    gross = 0.0
    for l in priced:
        g = float(purchase_calc.q2(purchase_calc.D(l["quantity"]) * purchase_calc.D(l["purchase_price"] or 0)))
        gross += g
        line_disc += float(purchase_calc.q2(purchase_calc.D(g) * purchase_calc.D(l["discount_percent"] or 0) / 100))
    hd = h.get("discount") or 0.0
    inv_disc = 0.0
    if hd > 0:
        if line_disc == 0:
            inv_disc = hd
            notes.append(f"Discount of ₹{hd:.2f} printed in the totals block is applied once, on the invoice.")
        elif abs(hd - line_disc) <= 1.0:
            notes.append("The bill's discount equals the discounts on its lines, so it is not applied a second time.")
        else:
            notes.append(f"Conflicting discounts: lines carry ₹{line_disc:.2f} but the totals block prints ₹{hd:.2f}. Only the line discounts were applied: check the bill.")
    igst, cg, sg = h.get("igst_amount") or 0.0, h.get("cgst_amount") or 0.0, h.get("sgst_amount") or 0.0
    interstate = bool(cor.get("interstate")) if cor.get("interstate") is not None else bool(igst > 0 and cg == 0 and sg == 0)
    rates = [l["gst_rate"] for l in priced if l["gst_rate"] is not None]
    mode = cor.get("prices_include_gst")
    if mode is None:
        mode = purchase_calc.infer_tax_mode(gross, line_disc + inv_disc, h.get("taxable_amount"), rates)
        if mode is None and h.get("taxable_amount"):
            notes.append("Could not tell from the bill whether its rates include GST; they were treated as excluding GST: check the bill.")
            mode = False
    printed = eff.get("printed_total")
    return {
        "invoice_discount_amount": inv_disc, "other_charges": h.get("other_amount") or 0.0, "interstate": interstate,
        "prices_include_gst": bool(mode), "round_to_rupee": bool(printed and abs(printed - round(printed)) < 1e-9),
        "printed": {"total": printed, "subtotal": h.get("subtotal"), "discount": hd or None, "taxable": h.get("taxable_amount"),
                    "cgst": h.get("cgst_amount"), "sgst": h.get("sgst_amount"), "igst": h.get("igst_amount"), "other": h.get("other_amount")},
        "notes": notes,
    }


def calculate_document(eff: dict, lines: List[dict]) -> Optional[dict]:
    """The authoritative calculation of a scanned bill (None when no line can be priced yet)."""
    priced = [l for l in lines if l["quantity"] and l["quantity"] > 0 and l["purchase_price"] is not None]
    if not priced:
        return None
    inp = invoice_inputs(eff, lines)
    try:
        calc = purchase_calc.calc_invoice(
            [{"qty": l["quantity"], "free": l["free_qty"] or 0, "rate": l["purchase_price"], "disc_percent": l["discount_percent"] or 0,
              "gst_rate": l["gst_rate"] or 0} for l in priced],
            invoice_discount_amount=inp["invoice_discount_amount"], other_charges=inp["other_charges"], interstate=inp["interstate"],
            prices_include_gst=inp["prices_include_gst"], round_to_rupee=inp["round_to_rupee"])
    except purchase_calc.CalcError as exc:
        return {"error": str(exc), "inputs": inp}
    calc["reconciliation"] = purchase_calc.reconcile(calc, inp["printed"])
    calc["inputs"] = inp
    return calc


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
    if line["gst_rate"] is None and not line["hsn_code"]:
        add("gst_rate", "Neither HSN nor GST rate was read: enter at least one (the other is filled in from it).")
    elif line["gst_rate"] is None:
        add("gst_rate", "GST rate is missing and this HSN is not in the rate table: enter the GST rate.")
    elif not (0 <= line["gst_rate"] <= 28):
        add("gst_rate", "GST rate must be between 0 and 28.")
    if line.get("tax_filled"):
        warnings.append({"field": "gst_rate" if line["tax_filled"].startswith("GST") else "hsn_code", "message": line["tax_filled"] + " (check against the bill)."})
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
                 allow_below_cost: bool = False, raw_eff: Optional[dict] = None):
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
    inp = invoice_inputs(raw_eff, lines) if raw_eff is not None else {}
    return purchase_entry.ManualPurchaseCreate(
        supplier_id=supplier_id, invoice_number=str(eff["invoice_number"]).strip(), invoice_date=eff["invoice_date"],
        payment_status="UNPAID", expected_total=expected_total, items=items,
        invoice_discount_amount=inp.get("invoice_discount_amount", 0.0), other_charges=inp.get("other_charges", 0.0),
        interstate=inp.get("interstate", False), prices_include_gst=inp.get("prices_include_gst", False),
        round_to_rupee=inp.get("round_to_rupee", False), printed_total=inp.get("printed", {}).get("total"),
    )


def _active_draft(db: Session, user_id: int, document_id: int) -> Optional[dict]:
    d = db.query(models.PurchaseDraft).filter(models.PurchaseDraft.user_id == user_id, models.PurchaseDraft.document_id == document_id,
                                              models.PurchaseDraft.status == "DRAFT").first()
    if not d:
        return None
    import purchase_drafts
    return {"id": d.id, "reference": purchase_drafts.draft_ref(d.id), "version": d.version,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None}


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

    calc = calculate_document(eff, lines)
    notes = []
    printed = _num(eff["printed_total"])
    total_differs = False
    totals = None
    recon = None
    if calc and calc.get("error"):
        hb("total", "The invoice figures cannot be calculated: " + calc["error"])
    elif calc:
        ct = calc["totals"]
        totals = {"total": ct["payable"], "taxable": ct["taxable"], "gst": ct["tax"], "discount": ct["discount"], "gross": ct["gross"],
                  "cgst": ct["cgst"], "sgst": ct["sgst"], "igst": ct["igst"], "other_charges": ct["other_charges"], "round_off": ct["round_off"]}
        recon = calc["reconciliation"]
        total_differs = recon["status"] == "REVIEW"
        notes.extend(calc["inputs"]["notes"])
        if total_differs:
            notes.insert(0, f"Calculated total ₹{recon['calculated_total']:.2f} differs from the printed total ₹{recon['printed_total']:.2f} by ₹{abs(recon['difference']):.2f}.")
            notes.extend(recon["likely_causes"])
        for l, cl in zip([x for x in lines if x["quantity"] and x["quantity"] > 0 and x["purchase_price"] is not None], calc["lines"]):
            tp = l.get("total_price")
            if tp is not None and abs(tp - cl["gross"]) > 1.0 and abs(tp - (cl["gross"] - cl["line_discount"])) > 1.0:
                l["warnings"].append({"field": "total_price", "message": f"Printed line amount ₹{tp:.2f} differs from quantity × rate ₹{cl['gross']:.2f}."})
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
        "reconciliation": recon, "header_figures": {k: v for k, v in header_figures(eff).items() if k in ("discount_amount", "other_amount", "discount")},
        "calculation_policy": calc["policy"] if calc and not calc.get("error") else None,
        "tax_groups": calc["tax_groups"] if calc and not calc.get("error") else [],
        "line_count": len(lines), "lines": lines, "raw_items": eff["items"], "blocking": blocking, "blocking_count": len(blocking),
        "can_confirm": not blocking and not verified and not failed, "can_edit": not verified,
        "verified": verified, "failed": failed, "draft": _active_draft(db, user_id, doc.id),
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
        **{k: header.get(k) for k in ("discount_amount", "other_amount", "taxable_amount", "interstate", "prices_include_gst") if header.get(k) is not None},
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


def confirm_document(db: Session, user_id: int, doc: models.Document, acknowledge_warnings: bool = False,
                     override_reason: Optional[str] = None) -> dict:
    """
    Confirm & Add to Stock for the document as the review shows it. One transaction, via the purchase engine.
    A calculated total that does not reconcile with the printed total (beyond the tolerance) is refused unless the user gives
    a reason; the reason, user, time and both totals are then kept on the document (override_audit).
    """
    status = str(doc.ocr_status or "").lower()
    if status == "verified":
        raise HTTPException(status_code=409, detail="ALREADY_VERIFIED: This invoice was already confirmed and its stock added. Nothing was posted again.")
    if status == "failed":
        raise HTTPException(status_code=409, detail="OCR failed for this document. Edit the bill details by hand and save them first.")
    view = review_view(db, user_id, doc)
    if view["blocking"]:
        first = "; ".join(f"{b['field']}: {b['message']}" for b in view["blocking"][:6])
        raise HTTPException(status_code=422, detail=f"REVIEW_INCOMPLETE: {view['blocking_count']} problem(s) must be fixed first. {first}")
    reason = (override_reason or "").strip()
    if view["total_differs"] and len(reason) < 5:
        recon = view["reconciliation"]
        raise HTTPException(status_code=409, detail=(
            f"RECONCILIATION_FAILED: calculated ₹{recon['calculated_total']:.2f} vs printed ₹{recon['printed_total']:.2f} "
            f"(difference ₹{recon['difference']:+.2f}, tolerance ₹{recon['tolerance']:.2f}). " + " ".join(recon["likely_causes"]) +
            " Correct the bill details, or confirm with an override reason."))
    below_cost = [f"row {l['row']} {l['product_name']}" for l in view["lines"] if any(w["field"] == "mrp" and "lower than the purchase rate" in w["message"] for w in l["warnings"])]
    if below_cost and not acknowledge_warnings:
        raise HTTPException(status_code=409, detail="NEEDS_ACKNOWLEDGEMENT: MRP is below the purchase rate for: " + ", ".join(below_cost) +
                                                    ". Check the bill, then confirm again to accept.")
    eff = effective(doc)
    lines = [_line_view(n, it) for n, it in enumerate(eff["items"], 1)]
    payload = _to_purchase(doc, doc.supplier_id, {"invoice_number": view["invoice_number"], "invoice_date": view["invoice_date"]}, lines,
                           expected_total=view["computed"]["total"] if view["computed"] else None, allow_below_cost=bool(below_cost), raw_eff=eff)
    res = purchase_entry.post_manual_purchase(db, user_id, payload, document_id=doc.id, override_reason=reason if view["total_differs"] else None)
    return {"message": f"Invoice confirmed: {res['items_count']} medicine line(s) added to stock as {res['voucher_no']}.", **res}


def save_as_draft(db: Session, user_id: int, doc: models.Document, header: Optional[dict] = None, items: Optional[List[dict]] = None) -> dict:
    """
    Save as Draft for a scanned bill: optionally store the user's corrections first, then keep one open purchase draft
    pointing at the document. Nothing is posted and the document status does not change (it is not Verified).
    """
    import purchase_drafts
    if str(doc.ocr_status or "").lower() == "verified":
        raise HTTPException(status_code=409, detail="This invoice is already verified and its stock was added; it cannot be saved as a draft.")
    if header is not None or items is not None:
        save_corrections(db, user_id, doc, header or {}, items or [])
    view = review_view(db, user_id, doc)
    try:
        inv_date = datetime.strptime(str(view["invoice_date"])[:10], "%Y-%m-%d").date() if view.get("invoice_date") else None
    except ValueError:
        inv_date = None
    total = view["computed"]["total"] if view.get("computed") else None
    draft = purchase_drafts.upsert_ocr_draft(db, user_id, doc, doc.supplier_id, view.get("invoice_number"), inv_date, view["line_count"], total)
    return {"draft": draft, "review": review_view(db, user_id, doc)}
