"""
Web "Add Stock" flow routes: duplicate-batch check, custom catalogue medicine, and multi-item stock entry.

Restored from app.py as it was before the modularisation refactor (commit 526c298), which left them out
(the web Add Stock screen returned 404). Stock entry now enforces the MRP rules in crud.validate_mrp.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from dependencies import get_db, get_current_user, AuthenticatedUser
import schemas
import crud

router = APIRouter(tags=["Inventory Stock Entry"])


@router.post("/inventory/check-duplicate")
def check_inventory_duplicate_batch(
    data: schemas.DuplicateBatchCheckRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Checks if a medicine + batch number already exists in shop inventory."""
    return crud.check_duplicate_batch(
        db=db, user_id=current_user.id, product_name=data.product_name, batch_number=data.batch_number
    )


@router.post("/catalog/create-custom", response_model=schemas.MedicineCatalogResponse)
def create_custom_catalog_medicine(
    data: schemas.CustomMedicineCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a custom medicine in the reference catalogue when it is not found."""
    return crud.create_custom_medicine(db=db, data=data)


@router.post("/inventory/batch-add")
def batch_add_inventory_stock(
    data: schemas.BatchInventoryAddRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Adds several stock entries. Every line's MRP is checked first, so nothing is saved if one is invalid."""
    for item in data.items:
        explicit = item.mrp is not None and item.mrp > 0
        crud.validate_mrp(
            item.mrp if explicit else item.unit_price,
            item.purchase_price,
            name=item.product_name,
            explicit_mrp=explicit,
            confirm_below_cost=item.confirm_mrp_below_cost,
        )
    created_items = []
    for item in data.items:
        prod = crud.add_real_inventory_item(db=db, data=item, user_id=current_user.id)
        created_items.append(prod.id)
    return {
        "message": f"Successfully added {len(created_items)} medicine stock items to inventory.",
        "count": len(created_items),
        "product_ids": created_items,
    }
