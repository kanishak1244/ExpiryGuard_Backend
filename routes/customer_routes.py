"""
Customer Directory and Khata Ledger Management Routes for DawaiFlow / ExpiryGuard.
Handles customer directory CRUD, credit limit tracking, Khata outstanding ledger, and payment receipts.
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

logger = logging.getLogger("expiryguard.routes.customers")

router = APIRouter(tags=["Customer Directory & Khata Ledger"])


@router.get("/customers")
def get_customers(
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve list of customers with optional search filtering."""
    return crud.get_customers(db, current_user.id, search=search, skip=skip, limit=limit)


@router.post("/customers")
def create_customer(
    customer: schemas.CustomerCreate,
    current_user: AuthenticatedUser = Depends(require_permission("CUSTOMER_CREATE")),
    db: Session = Depends(get_db),
):
    """Add a new customer to directory."""
    created = crud.create_customer(db, customer, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.put("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    customer: schemas.CustomerCreate,
    current_user: AuthenticatedUser = Depends(require_permission("CUSTOMER_EDIT")),
    db: Session = Depends(get_db),
):
    """Update customer details."""
    updated = crud.update_customer(db, customer_id, customer, current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Customer not found")
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("CUSTOMER_DELETE")),
    db: Session = Depends(get_db),
):
    """Delete a customer record."""
    success = crud.delete_customer(db, customer_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Customer not found or has active pending balance")
    fast_cache.invalidate_user(current_user.id)
    return {"message": "Customer deleted successfully"}


@router.get("/customers/outstanding")
@router.get("/khata/outstanding")
def get_outstanding_customers(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of customers with positive Khata credit balances."""
    return crud.get_outstanding_customers(db, current_user.id)


@router.get("/khata/dashboard")
def get_khata_dashboard(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get overall Khata credit summary metrics."""
    return crud.get_khata_dashboard(db, current_user.id)


@router.get("/customers/{customer_id}/ledger")
def get_customer_ledger(
    customer_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get full ledger transaction history for a customer."""
    ledger = crud.get_customer_ledger(db, current_user.id, customer_id)
    if ledger is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return ledger


@router.post("/customer-payments")
@router.post("/khata/payment")
def record_customer_payment(
    data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("CUSTOMER_EDIT")),
    db: Session = Depends(get_db),
):
    """Record a credit payment/clearing entry from a customer."""
    res = crud.record_customer_payment(db, current_user.id, data)
    fast_cache.invalidate_user(current_user.id)
    return res
