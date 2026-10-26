"""
Purchase drafts: a purchase that is saved while it is still being prepared.

A draft lives in its own table (models.PurchaseDraft). Saving, listing, reopening, editing or deleting a draft never
touches stock, supplier balances, purchase invoices, the supplier ledger or the purchase reports. The only thing that
posts a purchase is the purchase engine (purchase_entry.post_manual_purchase); it calls mark_finalized() inside its own
transaction, so a draft turns FINALIZED exactly when (and only when) the purchase was posted, and never twice.

Two kinds:
  MANUAL  the Add Manually / Search Medicine editor: the editor's header and rows are stored as JSON (payload)
  OCR     a scanned supplier bill: the corrections live on the document (document_review); the draft row is the
          pointer (document_id) plus header and estimate, one active draft per document
"""
import json
from datetime import date, datetime
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import crud
import models
import purchase_entry

MAX_PAYLOAD_BYTES = 1_000_000
MAX_ROWS = purchase_entry.MAX_LINES


def draft_ref(draft_id: int) -> str:
    return f"DRAFT-{int(draft_id):05d}"


class DraftSave(BaseModel):
    draft_id: Optional[int] = Field(default=None, ge=1)
    expected_version: Optional[int] = Field(default=None, ge=1)     # the version the editor loaded; a different one is refused
    supplier_id: Optional[int] = Field(default=None, ge=1)
    invoice_number: Optional[str] = Field(default=None, max_length=60)
    invoice_date: Optional[date] = None
    payload: dict = Field(default_factory=dict)


def _num(v) -> float:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _row_filled(r: dict) -> bool:
    return bool(str(r.get("name") or "").strip() or str(r.get("batch") or "").strip() or _num(r.get("qty")) or _num(r.get("rate")))


def estimate_rows(rows: list) -> tuple:
    """(filled line count, estimated total or None). An estimate from the numbers typed so far; never a posted amount."""
    filled = [r for r in rows if isinstance(r, dict) and _row_filled(r)]
    total, priced = 0.0, 0
    for r in filled:
        qty, rate = int(_num(r.get("qty"))), _num(r.get("rate"))
        if qty > 0 and rate > 0:
            total += purchase_entry.calc_line(qty, int(_num(r.get("free"))), rate, _num(r.get("disc")),
                                              _num(r.get("gst")) if str(r.get("gst") or "").strip() != "" else 12.0)["total"]
            priced += 1
    return len(filled), (round(total, 2) if priced else None)


def view(d: models.PurchaseDraft, supplier_name: Optional[str] = None, full: bool = False) -> dict:
    out = {
        "id": d.id, "reference": draft_ref(d.id), "source": d.source, "status": d.status,
        "supplier_id": d.supplier_id, "supplier_name": supplier_name, "document_id": d.document_id,
        "invoice_number": d.invoice_number, "invoice_date": d.invoice_date.isoformat() if d.invoice_date else None,
        "line_count": d.line_count, "estimated_total": d.estimated_total, "estimate_note": "Draft estimate, not a posted amount.",
        "version": d.version, "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        "purchase_invoice_id": d.purchase_invoice_id,
        "purchase_voucher_no": crud.purchase_voucher_no(d.purchase_invoice_id) if d.purchase_invoice_id else None,
    }
    if full:
        try:
            out["payload"] = json.loads(d.payload) if d.payload else {}
        except ValueError:
            out["payload"] = {}
    return out


def _supplier_name(db: Session, user_id: int, supplier_id: Optional[int]) -> Optional[str]:
    if not supplier_id:
        return None
    s = db.query(models.Supplier).filter(models.Supplier.id == supplier_id, models.Supplier.user_id == user_id).first()
    return s.name if s else None


def save_draft(db: Session, user_id: int, data: DraftSave) -> dict:
    """Create or update a MANUAL draft. All-or-nothing; a failed save leaves the earlier saved draft untouched."""
    rows = data.payload.get("rows") if isinstance(data.payload, dict) else None
    rows = rows if isinstance(rows, list) else []
    if len(rows) > MAX_ROWS:
        raise HTTPException(status_code=400, detail=f"A draft can hold at most {MAX_ROWS} lines.")
    raw = json.dumps(data.payload, default=str)
    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="This draft is too large to save.")
    if not (data.supplier_id or (data.invoice_number or "").strip() or any(isinstance(r, dict) and _row_filled(r) for r in rows)):
        raise HTTPException(status_code=400, detail="Enter a supplier, an invoice number or at least one medicine before saving a draft.")
    try:
        sname = None
        if data.supplier_id:
            sname = _supplier_name(db, user_id, data.supplier_id)
            if not sname:
                raise HTTPException(status_code=404, detail="Supplier not found or access denied.")
        count, est = estimate_rows(rows)
        if data.draft_id:
            d = (db.query(models.PurchaseDraft).filter(models.PurchaseDraft.id == data.draft_id, models.PurchaseDraft.user_id == user_id)
                 .with_for_update().first())
            if not d:
                raise HTTPException(status_code=404, detail="Draft not found.")
            if d.source != "MANUAL":
                raise HTTPException(status_code=409, detail="This draft belongs to a scanned bill; continue it from the invoice review.")
            if d.status != "DRAFT":
                raise HTTPException(status_code=409, detail="DRAFT_FINALIZED: This draft was already posted as a purchase and can no longer be edited.")
            if data.expected_version is not None and data.expected_version != d.version:
                raise HTTPException(status_code=409, detail="DRAFT_CHANGED: This draft was saved from somewhere else after you opened it. "
                                                            "Reload it to see the latest version before saving again.")
            d.version += 1
        else:
            d = models.PurchaseDraft(user_id=user_id, source="MANUAL", status="DRAFT", version=1)
            db.add(d)
        d.supplier_id = data.supplier_id
        d.invoice_number = (data.invoice_number or "").strip() or None
        d.invoice_date = data.invoice_date
        d.payload = raw
        d.line_count, d.estimated_total = count, est
        db.commit()
        db.refresh(d)
    except Exception:
        db.rollback()
        raise
    return view(d, sname)


def list_drafts(db: Session, user_id: int, q: Optional[str] = None, status: str = "DRAFT", date_from: Optional[date] = None,
                date_to: Optional[date] = None, page: int = 1, page_size: int = 25) -> dict:
    D, S = models.PurchaseDraft, models.Supplier
    page, page_size = max(1, int(page or 1)), min(100, max(1, int(page_size or 25)))

    def filt(query):
        query = query.filter(D.user_id == user_id)
        st = (status or "DRAFT").upper()
        if st != "ALL":
            query = query.filter(D.status == st)
        if date_from:
            query = query.filter(func.date(D.updated_at) >= date_from)
        if date_to:
            query = query.filter(func.date(D.updated_at) <= date_to)
        term = (q or "").strip()
        if term:
            like = f"%{term.lower()}%"
            conds = [func.lower(func.coalesce(D.invoice_number, "")).like(like), func.lower(func.coalesce(S.name, "")).like(like)]
            digits = "".join(ch for ch in term if ch.isdigit())
            if term.upper().startswith("DRAFT") and digits:
                conds.append(D.id == int(digits))
            query = query.filter(or_(*conds))
        return query

    base = filt(db.query(D).outerjoin(S, S.id == D.supplier_id))
    total = base.with_entities(func.count(D.id)).scalar() or 0
    rows = (filt(db.query(D, S.name).outerjoin(S, S.id == D.supplier_id))
            .order_by(D.updated_at.desc(), D.id.desc()).offset((page - 1) * page_size).limit(page_size).all())
    return {"items": [view(d, name) for d, name in rows], "total": int(total), "page": page, "page_size": page_size,
            "draft_count": draft_count(db, user_id)}


def draft_count(db: Session, user_id: int) -> int:
    return int(db.query(func.count(models.PurchaseDraft.id)).filter(
        models.PurchaseDraft.user_id == user_id, models.PurchaseDraft.status == "DRAFT").scalar() or 0)


def get_draft(db: Session, user_id: int, draft_id: int) -> dict:
    d = db.query(models.PurchaseDraft).filter(models.PurchaseDraft.id == draft_id, models.PurchaseDraft.user_id == user_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return view(d, _supplier_name(db, user_id, d.supplier_id), full=True)


def delete_draft(db: Session, user_id: int, draft_id: int) -> dict:
    """Removes the draft row only. A scanned bill and its corrections stay in the Documents archive."""
    try:
        d = (db.query(models.PurchaseDraft).filter(models.PurchaseDraft.id == draft_id, models.PurchaseDraft.user_id == user_id)
             .with_for_update().first())
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found.")
        if d.status != "DRAFT":
            raise HTTPException(status_code=409, detail="This draft was already posted as a purchase, so it is kept as history.")
        db.delete(d)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"message": f"{draft_ref(draft_id)} deleted.", "id": draft_id}


def upsert_ocr_draft(db: Session, user_id: int, doc: models.Document, supplier_id: Optional[int], invoice_number: Optional[str],
                     invoice_date: Optional[date], line_count: int, estimated_total: Optional[float]) -> dict:
    """One active draft per scanned bill: saving again updates it (no duplicates). The bill's data stays on the document."""
    if str(doc.ocr_status or "").lower() == "verified":
        raise HTTPException(status_code=409, detail="This invoice is already verified and its stock was added; it cannot be saved as a draft.")
    try:
        d = (db.query(models.PurchaseDraft).filter(models.PurchaseDraft.user_id == user_id, models.PurchaseDraft.document_id == doc.id,
                                                   models.PurchaseDraft.status == "DRAFT").with_for_update().first())
        if d:
            d.version += 1
        else:
            d = models.PurchaseDraft(user_id=user_id, document_id=doc.id, source="OCR", status="DRAFT", version=1)
            db.add(d)
        d.supplier_id, d.invoice_number, d.invoice_date = supplier_id, (invoice_number or None), invoice_date
        d.line_count, d.estimated_total = line_count, estimated_total
        db.commit()
        db.refresh(d)
    except Exception:
        db.rollback()
        raise
    return view(d, _supplier_name(db, user_id, d.supplier_id))


def mark_finalized(db: Session, user_id: int, invoice_id: int, draft_id: Optional[int] = None, document_id: Optional[int] = None,
                   calculation: Optional[dict] = None) -> None:
    """
    Called by the purchase engine inside its own transaction (no commit here). Turns the draft FINALIZED and links the
    purchase. A draft that is not an open DRAFT of this pharmacy is refused, so a retry or a second tab cannot post twice.
    """
    if draft_id:
        d = (db.query(models.PurchaseDraft).filter(models.PurchaseDraft.id == draft_id, models.PurchaseDraft.user_id == user_id)
             .with_for_update().first())
        if not d:
            raise HTTPException(status_code=404, detail="Draft not found.")
        if d.status != "DRAFT":
            raise HTTPException(status_code=409, detail="DRAFT_FINALIZED: This draft was already posted as a purchase. Nothing was posted again.")
        drafts = [d]
    elif document_id:
        drafts = (db.query(models.PurchaseDraft).filter(models.PurchaseDraft.user_id == user_id, models.PurchaseDraft.document_id == document_id,
                                                        models.PurchaseDraft.status == "DRAFT").with_for_update().all())
    else:
        return
    for d in drafts:
        d.status = "FINALIZED"
        d.purchase_invoice_id = invoice_id
        if calculation is not None:                       # how the posted total was calculated, kept with the draft
            try:
                pl = json.loads(d.payload) if d.payload else {}
                pl = pl if isinstance(pl, dict) else {}
            except ValueError:
                pl = {}
            pl["calculation"] = calculation
            d.payload = json.dumps(pl, default=str)
        d.finalized_at = datetime.utcnow()
