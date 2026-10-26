"""
Purchase Invoices and Supplier Management Routes for DawaiFlow / ExpiryGuard.
Handles purchase bill entry, stock intake, supplier catalog CRUD, ledger balances, and payment logs.
"""

import logging
from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from dependencies import (
    get_db,
    get_current_user,
    require_permission,
    AuthenticatedUser,
    fast_cache,
    limiter,
)
import models
import schemas
import crud
import purchase_entry
import purchase_drafts
import supplier_profile

logger = logging.getLogger("expiryguard.routes.purchases")

router = APIRouter(tags=["Purchase & Supplier Operations"])


@router.post("/purchases")
@router.post("/purchase-invoices")
def create_purchase_invoice(
    data: schemas.PurchaseInvoiceCreate,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Create purchase invoice, update stock inventory levels, and update supplier balance."""
    created = crud.create_purchase_invoice(db, data, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.get("/purchases")
@router.get("/purchase-invoices")
def get_purchase_invoices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    supplier_id: Optional[int] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get historical purchase invoices with optional supplier filter."""
    return crud.get_purchase_invoices(db, current_user.id, skip=skip, limit=limit, supplier_id=supplier_id)


@router.get("/purchases/list")
def list_purchase_documents(
    q: Optional[str] = Query(None, max_length=80),
    supplier_id: Optional[int] = Query(None, ge=1),
    status: Optional[str] = Query(None, pattern="^(?i:PAID|UNPAID|PARTIAL)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    """Purchase Management list: saved purchase invoices of this shop (read-only, server-side paging) + summary."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")
    return crud.list_purchase_documents(
        db, current_user.id, q=q, supplier_id=supplier_id, status=status,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )


@router.get("/purchases/detail/{purchase_id}")
def get_purchase_document_detail(
    purchase_id: int,
    supplier_id: Optional[int] = Query(None, ge=1),
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    """One saved purchase with supplier and medicine names (read-only)."""
    doc = crud.get_purchase_document_detail(db, current_user.id, purchase_id, supplier_id=supplier_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Purchase not found.")
    return doc


@router.post("/purchases/manual", status_code=201)
def post_manual_purchase(
    data: purchase_entry.ManualPurchaseCreate,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Add Manually: post one supplier invoice (stock, document, ledger) in a single transaction."""
    res = purchase_entry.post_manual_purchase(db, current_user.id, data)
    fast_cache.invalidate_user(current_user.id)
    return res


@router.post("/purchases/drafts")
def save_purchase_draft(
    data: purchase_drafts.DraftSave,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Save (create or update) a purchase draft. A draft posts nothing: no stock, no supplier balance, no purchase invoice."""
    return purchase_drafts.save_draft(db, current_user.id, data)


@router.get("/purchases/drafts")
def list_purchase_drafts(
    q: Optional[str] = Query(None, max_length=80),
    status: str = Query("DRAFT", pattern="^(?i:DRAFT|FINALIZED|ALL)$"),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    """Drafts of this pharmacy (server-side paging) with the accurate open-draft count."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=400, detail="date_from must not be after date_to.")
    return purchase_drafts.list_drafts(db, current_user.id, q=q, status=status, date_from=date_from, date_to=date_to,
                                       page=page, page_size=page_size)


@router.get("/purchases/drafts/{draft_id}")
def get_purchase_draft(
    draft_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    return purchase_drafts.get_draft(db, current_user.id, draft_id)


@router.delete("/purchases/drafts/{draft_id}")
def delete_purchase_draft(
    draft_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Delete a draft (the draft row only; a scanned bill stays in Documents)."""
    return purchase_drafts.delete_draft(db, current_user.id, draft_id)


@router.get("/purchases/check-duplicate")
def check_duplicate_supplier_invoice(
    supplier_id: int = Query(..., ge=1),
    invoice_number: str = Query(..., min_length=1, max_length=60),
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    """Is this supplier invoice number already saved for this supplier? (read-only)"""
    return purchase_entry.check_duplicate(db, current_user.id, supplier_id, invoice_number)


@router.get("/purchases/medicine-search")
def purchase_medicine_search(
    q: str = Query(..., min_length=1, max_length=80),
    limit: int = Query(12, ge=1, le=30),
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_VIEW")),
    db: Session = Depends(get_db),
):
    """Medicine suggestions for the purchase grid: this shop's medicines with batches, then the catalog (read-only)."""
    return purchase_entry.search_medicines(db, current_user.id, q, limit)


@router.get("/purchases/dashboard")
def get_purchases_dashboard(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get aggregated purchase dashboard summary metrics."""
    return crud.get_purchases_dashboard(db, current_user.id)


@router.get("/suppliers")
def get_suppliers(
    search: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve list of registered suppliers."""
    return crud.get_suppliers(db, current_user.id, search=search)


@router.post("/suppliers")
def create_supplier(
    supplier: schemas.SupplierCreate,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Register a new distributor/supplier."""
    created = crud.create_supplier(db, current_user.id, supplier)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.put("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    supplier: schemas.SupplierUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Update supplier profile details."""
    updated = crud.update_supplier(db, supplier_id, current_user.id, supplier)
    if not updated:
        raise HTTPException(status_code=404, detail="Supplier not found")
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.delete("/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Delete a supplier."""
    success = crud.delete_supplier(db, supplier_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Supplier not found or has linked invoices")
    fast_cache.invalidate_user(current_user.id)
    return {"message": "Supplier deleted successfully"}


@router.get("/suppliers/{supplier_id}/profile")
def get_supplier_profile(
    supplier_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Supplier details + purchase / payment / return figures (same rule as the ledger and dashboard). 404 if not this shop's."""
    return supplier_profile.profile(db, current_user.id, supplier_id)


@router.get("/suppliers/{supplier_id}/stock")
def get_supplier_stock(
    supplier_id: int,
    q: Optional[str] = Query(None, max_length=80),
    status: Optional[str] = Query(None, pattern="^(?i:In Stock|Partially Sold|Sold Out|Expired|Returned|Unavailable)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Linked medicine stock per batch with an evidence-based stock status (read-only, paged)."""
    return supplier_profile.stock(db, current_user.id, supplier_id, q=q, status=status, page=page, page_size=page_size)


@router.get("/suppliers/{supplier_id}/ledger")
def get_supplier_ledger(
    supplier_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    type: Optional[str] = Query(None, pattern="^(?i:PURCHASE|PAYMENT|RETURN)$"),
    newest_first: bool = False,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get ledger transaction history and outstanding balance for a supplier."""
    ledger = crud.get_supplier_ledger(db, current_user.id, supplier_id, page=page, page_size=page_size, entry_type=type, newest_first=newest_first)
    if ledger is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return ledger


@router.post("/supplier-payments")
def record_supplier_payment(
    data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Record a payment made to a supplier."""
    res = crud.record_supplier_payment(db, current_user.id, data)
    fast_cache.invalidate_user(current_user.id)
    return res
