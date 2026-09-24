"""
Product & Inventory Management Routes for DawaiFlow / ExpiryGuard.
Handles product creation, inventory listing, summary dashboards, intelligence recommendations,
smart alerts, product updating/deletion, catalog search, marked-for-return, and priority sales.
"""

import time
import logging
from typing import Optional, List, Dict, Any

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

logger = logging.getLogger("expiryguard.routes.products")

router = APIRouter(tags=["Product Inventory Management"])


@router.post("/products")
@router.post("/inventory/add")
def create_product(
    product: schemas.ProductCreate,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_CREATE")),
    db: Session = Depends(get_db),
):
    """Add a new product/batch to pharmacy inventory."""
    created = crud.create_product(db, product, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.get("/products")
@router.get("/inventory")
def read_products(
    page: Optional[int] = Query(None, ge=1),
    skip: Optional[int] = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    filter_key: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve paginated inventory products with optional filtering and search."""
    t0 = time.time()
    eff_skip = skip or 0
    if page and page > 1 and limit:
        eff_skip = (page - 1) * limit
    eff_filter = filter or filter_key

    cache_key = f"prods:{eff_skip}:{limit}:{search}:{eff_filter}:{sort_by}"
    cached_prods = fast_cache.get(current_user.id, cache_key)
    if cached_prods is not None:
        return JSONResponse(content=cached_prods)

    logger.info(f"[Inventory] Query user_id={current_user.id}, page={page}, limit={limit}, search={search}, filter={eff_filter}")
    result = crud.get_products(
        db=db,
        user_id=current_user.id,
        skip=eff_skip,
        limit=limit,
        search=search,
        filter_key=eff_filter,
        sort_by=sort_by,
    )
    elapsed_ms = (time.time() - t0) * 1000.0
    item_count = len(result["items"]) if isinstance(result, dict) and "items" in result else (len(result) if isinstance(result, list) else 0)
    logger.info(f"[Inventory] Returned {item_count} items in {elapsed_ms:.2f}ms")
    fast_cache.set(current_user.id, cache_key, result, ttl=20.0, tags=["products", "inventory"])
    return JSONResponse(content=result)


@router.get("/inventory/summary")
def get_inventory_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Lightweight SQL-aggregated Inventory Health Dashboard summary metrics."""
    return crud.get_inventory_summary(db=db, user_id=current_user.id)


@router.get("/inventory/intelligence", response_model=schemas.InventoryIntelligenceResponse)
def get_inventory_intelligence(
    category: Optional[str] = None,
    supplier_id: Optional[int] = None,
    priority_level: Optional[str] = None,
    debug: bool = False,
    limit: int = 100,
    offset: int = 0,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smart Restock & Inventory Intelligence decision engine analytics and priority recommendations."""
    cache_key = f"intelligence:{category}:{supplier_id}:{priority_level}:{limit}:{offset}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached:
        return cached

    res = crud.get_inventory_intelligence(
        db=db,
        user_id=current_user.id,
        category=category,
        supplier_id=supplier_id,
        priority_level=priority_level,
        debug=debug,
        limit=limit,
        offset=offset
    )
    fast_cache.set(current_user.id, cache_key, res, ttl=30, tags=["inventory", "intelligence"])
    return res


@router.get("/alerts")
def get_smart_alerts(
    category: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns deterministic smart alerts organized by category and priority."""
    return crud.get_smart_alerts(db, current_user.id, category)


@router.get("/alerts/summary")
def get_alert_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns unread alert count and critical notification metrics for badge UI."""
    return crud.get_alert_summary(db, current_user.id)


@router.get("/alerts/preferences")
def get_alert_preferences(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves user alert category toggles."""
    return crud.get_alert_preferences(db, current_user.id)


@router.put("/alerts/preferences")
@router.post("/alerts/preferences")
def update_alert_preferences(
    prefs: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates user alert category toggles."""
    return crud.update_alert_preferences(db, current_user.id, prefs)


@router.get("/products/{product_id}")
def get_product(
    product_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve single product details by ID."""
    prod = crud.get_product(db, product_id, current_user.id)
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


@router.put("/products/{product_id}")
def update_product(
    product_id: int,
    product_data: schemas.ProductCreate,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Update existing product details."""
    updated = crud.update_product(db, product_id, product_data, current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found or access denied")
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.put("/products/{product_id}/quantity")
def update_product_quantity(
    product_id: int,
    quantity_data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Update stock quantity for a product batch."""
    new_qty = quantity_data.get("quantity")
    if new_qty is None or not isinstance(new_qty, int):
        raise HTTPException(status_code=400, detail="Invalid quantity specified")

    updated = crud.update_product_quantity(db, product_id, new_qty, current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found or access denied")
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_DELETE")),
    db: Session = Depends(get_db),
):
    """Soft delete product from active inventory."""
    success = crud.delete_product(db, product_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found or already deleted")
    fast_cache.invalidate_user(current_user.id)
    return {"message": "Product deleted successfully"}


@router.get("/billing/search-products")
def billing_search_products_endpoint(
    query: str = Query("", description="Search query string"),
    search_mode: Optional[str] = Query("name", description="Search mode: name, barcode, composition"),
    limit: int = Query(15, ge=1, le=50),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fast medicine billing product search with inventory ranking."""
    return crud.get_billing_search_products(
        db=db,
        user_id=current_user.id,
        query=query,
        search_mode=search_mode,
        limit=limit,
    )


@router.get("/products/search", response_model=List[schemas.MedicineCatalogResponse])
@router.get("/catalog/search", response_model=List[schemas.MedicineCatalogResponse])
def search_medicine_catalog_endpoint(
    q: Optional[str] = Query(None, description="Search query string"),
    query: Optional[str] = Query(None, description="Search query string alias"),
    limit: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """Ultra-fast multi-tier medicine master catalog search."""
    search_q = q or query or ""
    if not search_q.strip():
        return []
    return crud.search_medicine_catalog(db, search_q.strip(), limit)


@router.get("/products/barcode/{barcode}")
def lookup_product_by_barcode(
    barcode: str,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Look up product by EAN/UPC barcode string."""
    prod = crud.get_product_by_barcode(db, current_user.id, barcode)
    if not prod:
        raise HTTPException(status_code=404, detail="No product matching this barcode was found in inventory.")
    return prod


@router.get("/marked-for-return")
def get_marked_for_return(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get items marked for supplier return."""
    return crud.get_marked_for_return(db, current_user.id)


@router.post("/marked-for-return")
def mark_product_for_return(
    data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Mark a product batch for return."""
    product_id = data.get("product_id")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id is required")

    return crud.mark_product_for_return(
        db,
        user_id=current_user.id,
        product_id=product_id,
        return_qty=data.get("return_qty", 1),
        notes=data.get("notes")
    )


@router.delete("/marked-for-return/{return_id}")
def remove_marked_for_return(
    return_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Remove item from marked for return list."""
    success = crud.remove_marked_for_return(db, current_user.id, return_id)
    if not success:
        raise HTTPException(status_code=404, detail="Return record not found")
    return {"message": "Removed from return list"}


@router.get("/priority-sales")
def get_priority_sales(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get products marked as priority sales items."""
    return crud.get_priority_sales(db, current_user.id)


@router.post("/priority-sales")
def mark_priority_sale(
    data: dict,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Mark product for priority FEFO counter sales focus."""
    product_id = data.get("product_id")
    if not product_id:
        raise HTTPException(status_code=400, detail="product_id is required")

    return crud.mark_priority_sale(
        db,
        user_id=current_user.id,
        product_id=product_id,
        notes=data.get("notes")
    )


@router.delete("/priority-sales/{priority_id}")
def remove_priority_sale(
    priority_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    """Remove product from priority sales list."""
    success = crud.remove_priority_sale(db, current_user.id, priority_id)
    if not success:
        raise HTTPException(status_code=404, detail="Priority sale record not found")
    return {"message": "Removed from priority list"}
