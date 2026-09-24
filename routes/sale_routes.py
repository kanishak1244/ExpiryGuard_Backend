"""
POS, Billing, and Sales Operations Routes for DawaiFlow / ExpiryGuard.
Handles counter checkout, 1-tap billing, idempotency locks, sales history,
held bills (park/resume), sale returns, and split payments.
"""

import time
import json
import uuid
import logging
import threading
from typing import Optional, List, Dict, Any, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
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

logger = logging.getLogger("expiryguard.routes.sales")

router = APIRouter(tags=["POS & Billing Operations"])

_RECENT_SALES_CACHE: Dict[str, Tuple[Any, float]] = {}
_BILLING_CONCURRENCY_LOCK = threading.Lock()


def _get_idempotent_sale_or_key(
    request: Request,
    sale_data: schemas.SaleCreate,
    current_user_id: int,
    db: Optional[Session] = None,
) -> Tuple[Optional[Any], str]:
    """
    Deterministic idempotency verification to prevent duplicate checkout submissions.
    """
    client_key = (
        getattr(sale_data, "idempotency_key", None)
        or request.headers.get("x-idempotency-key")
        or request.headers.get("x-request-id")
    )

    if client_key and str(client_key).strip():
        clean_key = str(client_key).strip()
        sale_data.idempotency_key = clean_key
        cache_key = f"{current_user_id}:{clean_key}"

        now = time.time()
        expired = [k for k, (_, ts) in _RECENT_SALES_CACHE.items() if now - ts > 120]
        for k in expired:
            _RECENT_SALES_CACHE.pop(k, None)

        if cache_key in _RECENT_SALES_CACHE:
            cached_sale, ts = _RECENT_SALES_CACHE[cache_key]
            if now - ts < 120:
                logger.info(f"[IDEMPOTENCY] Cache hit for key {cache_key}. Duplicate transaction prevented.")
                return cached_sale, cache_key

        if db is not None:
            existing_sale = (
                db.query(models.Sale)
                .filter(
                    models.Sale.user_id == current_user_id,
                    models.Sale.idempotency_key == clean_key,
                )
                .first()
            )
            if existing_sale:
                logger.info(f"[IDEMPOTENCY] DB hit for key {cache_key}. Existing bill {existing_sale.bill_number} returned.")
                _RECENT_SALES_CACHE[cache_key] = (existing_sale, now)
                return existing_sale, cache_key

        return None, cache_key

    fallback_key = f"srv_{uuid.uuid4().hex}"
    sale_data.idempotency_key = fallback_key
    return None, f"{current_user_id}:{fallback_key}"


@router.post("/sales", response_model=schemas.SaleResponse, status_code=201)
def complete_sale(
    request: Request,
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    """Mobile Counter 1-Tap Checkout Endpoint with concurrency locking and idempotency protection."""
    t0 = time.perf_counter()
    with _BILLING_CONCURRENCY_LOCK:
        cached_sale, cache_key = _get_idempotent_sale_or_key(request, sale_data, current_user.id, db=db)
        if cached_sale:
            return cached_sale

        sale = crud.create_sale_transaction(
            db=db,
            sale_data=sale_data,
            user_id=current_user.id,
            current_user=current_user,
            verified_idempotency=True,
        )
        t1 = time.perf_counter()

        tax_summary = []
        if sale.tax_summary_json:
            try:
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                tax_summary = []

        sale.tax_summary = tax_summary
        sale.pdf_url = f"/billing/{sale.id}/pdf"

        _RECENT_SALES_CACHE[cache_key] = (sale, time.time())
        fast_cache.invalidate_user(current_user.id)

        t2 = time.perf_counter()
        logger.info(f"[BILLING] Sale #{sale.id} completed | DB: {(t1 - t0)*1000:.2f}ms | Total: {(t2 - t0)*1000:.2f}ms")
        return sale


@router.post("/billing/confirm", response_model=schemas.SaleResponse, status_code=201)
def confirm_billing_sale(
    request: Request,
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    """Confirm counter checkout, deduct stock, and return invoice payload with PDF link."""
    t0 = time.perf_counter()
    with _BILLING_CONCURRENCY_LOCK:
        cached_sale, cache_key = _get_idempotent_sale_or_key(request, sale_data, current_user.id, db=db)
        if cached_sale:
            return cached_sale

        sale = crud.create_sale_transaction(
            db=db,
            sale_data=sale_data,
            user_id=current_user.id,
            current_user=current_user,
            verified_idempotency=True,
        )
        t1 = time.perf_counter()

        tax_summary = []
        if sale.tax_summary_json:
            try:
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                tax_summary = []

        sale.tax_summary = tax_summary
        sale.pdf_url = f"/billing/{sale.id}/pdf"

        _RECENT_SALES_CACHE[cache_key] = (sale, time.time())
        fast_cache.invalidate_user(current_user.id)

        t2 = time.perf_counter()
        logger.info(f"[BILLING_CONFIRM] Sale #{sale.id} confirmed | DB: {(t1 - t0)*1000:.2f}ms | Total: {(t2 - t0)*1000:.2f}ms")
        return sale


@router.get("/sales")
@router.get("/sales/history")
def get_sales_history(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    search: Optional[str] = None,
    payment_method: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    period: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sales_type: Optional[str] = None,
    include_exported: Optional[bool] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve historical sales transactions with filtering."""
    return crud.get_sales_history(
        db=db,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        search=search,
        payment_method=payment_method,
        start_date=start_date,
        end_date=end_date,
        period=period,
        from_date=from_date,
        to_date=to_date,
        sales_type=sales_type,
    )


@router.get("/sales/{sale_id}")
def get_sale_details(
    sale_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get single sale transaction details."""
    sale = crud.get_sale_by_id(db, sale_id, current_user.id)
    if not sale:
        raise HTTPException(status_code=404, detail="Sale transaction not found")
    return sale


# Held Bills Endpoints

@router.post("/billing/held", response_model=schemas.HeldBillResponse, status_code=201)
def create_held_bill(
    payload: schemas.HeldBillCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Parks current cart as a held bill without deducting stock or creating a sale."""
    return crud.create_held_bill(db=db, bill_data=payload, user_id=current_user.id)


@router.get("/billing/held", response_model=List[schemas.HeldBillResponse])
def get_held_bills(
    status: str = "HELD",
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Lists held bills with optional search and status filtering."""
    return crud.get_held_bills(
        db=db,
        user_id=current_user.id,
        status=status,
        search_query=search,
        skip=skip,
        limit=limit,
    )


@router.get("/billing/held/count")
def get_held_bill_count(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns active held bills count for badge UI."""
    count = crud.get_held_bill_count(db=db, user_id=current_user.id)
    return {"count": count}


@router.get("/billing/held/{held_bill_id}", response_model=schemas.HeldBillResponse)
def get_held_bill_by_id(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Gets details for a single held bill."""
    held_bill = crud.get_held_bill_by_id(db=db, held_bill_id=held_bill_id, user_id=current_user.id)
    if not held_bill:
        raise HTTPException(status_code=404, detail=f"Held bill #{held_bill_id} not found.")
    return held_bill


@router.post("/billing/held/{held_bill_id}/resume", response_model=schemas.HeldBillResponse)
def resume_held_bill(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Resumes a held bill and marks it as RESUMED."""
    res = crud.resume_held_bill(db=db, held_bill_id=held_bill_id, user_id=current_user.id)
    if not res:
        raise HTTPException(status_code=404, detail=f"Held bill #{held_bill_id} not found or already processed.")
    return res


@router.delete("/billing/held/{held_bill_id}")
def cancel_held_bill(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Cancels/discards a held bill."""
    success = crud.cancel_held_bill(db=db, held_bill_id=held_bill_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Held bill #{held_bill_id} not found.")
    return {"message": "Held bill cancelled successfully."}


# Returns Endpoints

@router.get("/returns")
@router.get("/sale-returns")
def get_sale_returns(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get list of past customer return transactions."""
    return crud.get_sale_returns(db, current_user.id, skip=skip, limit=limit)


@router.post("/returns")
@router.post("/sale-returns")
def process_customer_return(
    data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
    db: Session = Depends(get_db),
):
    """Process customer return, restock inventory batch, and issue refund/credit."""
    res = crud.process_customer_return(db, current_user.id, data)
    fast_cache.invalidate_user(current_user.id)
    return res
