"""
Counter Sale endpoints (see counter_sale.py for the lifecycle). Additive: no table was added.
  POST   /billing/counter                     finish a customer's transaction (READY), safe to retry
  GET    /billing/counter                     list (paginated), status = READY | CONVERTED | CANCELLED | ALL
  GET    /billing/counter/{id}                one transaction with its lines (to review or reopen)
  POST   /billing/counter/{id}/convert        create ONE regular invoice from it (idempotent)
  DELETE /billing/counter/{id}                cancel a READY transaction
"""
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

import counter_sale
import schemas
from dependencies import AuthenticatedUser, fast_cache, get_current_user, get_db, require_permission
from routes.sale_routes import _BILLING_CONCURRENCY_LOCK

logger = logging.getLogger("expiryguard.routes.counter")
router = APIRouter(tags=["Counter Sale"])


@router.post("/billing/counter", status_code=201)
def finish_counter_customer(
    payload: schemas.CounterTxnCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    return counter_sale.create(db, current_user.id, payload)


@router.get("/billing/counter")
def list_counter_transactions(
    status: str = Query("READY"),
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return counter_sale.listing(db, current_user.id, status, search, skip, limit)


@router.get("/billing/counter/{held_id}")
def get_counter_transaction(
    held_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    return counter_sale.view(db, counter_sale.get(db, current_user.id, held_id), include_items=True)


@router.post("/billing/counter/{held_id}/convert")
def convert_counter_transaction(
    held_id: int,
    payload: schemas.CounterConvert,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    t0 = time.perf_counter()
    with _BILLING_CONCURRENCY_LOCK:                       # the same lock as POST /sales: one invoice is made at a time
        sale, already = counter_sale.convert(db, current_user.id, held_id, payload, current_user)
        tax_summary = []
        if getattr(sale, "tax_summary_json", None):
            try:
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                tax_summary = []
        fast_cache.invalidate_user(current_user.id)
    logger.info("[COUNTER] txn #%s -> sale #%s (%s) in %.0f ms", held_id, sale.id, "already converted" if already else "converted", (time.perf_counter() - t0) * 1000)
    return {
        "already_converted": already,
        "sale_id": sale.id,
        "bill_number": sale.bill_number,
        "total_amount": sale.total_amount,
        "tax_amount": getattr(sale, "tax_amount", None),
        "tax_summary": tax_summary,
        "pdf_url": f"/billing/{sale.id}/pdf",
        "transaction": counter_sale.view(db, counter_sale.get(db, current_user.id, held_id)),
    }


@router.delete("/billing/counter/{held_id}")
def cancel_counter_transaction(
    held_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    return counter_sale.cancel(db, current_user.id, held_id)
