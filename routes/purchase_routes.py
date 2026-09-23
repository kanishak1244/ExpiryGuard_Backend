"""
Purchase Invoices and Supplier Management Routes for DawaiFlow / ExpiryGuard.
Handles purchase bill entry, stock intake, supplier catalog CRUD, ledger balances, and payment logs.
"""

import logging
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
    created = crud.create_supplier(db, supplier, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.put("/suppliers/{supplier_id}")
def update_supplier(
    supplier_id: int,
    supplier: schemas.SupplierCreate,
    current_user: AuthenticatedUser = Depends(require_permission("PURCHASE_CREATE")),
    db: Session = Depends(get_db),
):
    """Update supplier profile details."""
    updated = crud.update_supplier(db, supplier_id, supplier, current_user.id)
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


@router.get("/suppliers/{supplier_id}/ledger")
def get_supplier_ledger(
    supplier_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get ledger transaction history and outstanding balance for a supplier."""
    ledger = crud.get_supplier_ledger(db, current_user.id, supplier_id)
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
