import uuid
import time
import json
import math
from typing import List, Dict, Tuple, Any, Optional
from datetime import date, datetime, timedelta
from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, case, or_, and_, text
from sqlalchemy.exc import IntegrityError
import logging
import models
import schemas

logger = logging.getLogger(__name__)

_PRODUCTS_CACHE = {}
_CUSTOMERS_CACHE = {}

def invalidate_products_cache(user_id: int):
    global _PRODUCTS_CACHE
    _PRODUCTS_CACHE.pop(user_id, None)

def get_all_active_products_cached(db: Session, user_id: int) -> List[models.Product]:
    global _PRODUCTS_CACHE
    if user_id in _PRODUCTS_CACHE:
        return _PRODUCTS_CACHE[user_id]
    products = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
        )
        .all()
    )
    _PRODUCTS_CACHE[user_id] = products
    return products

def invalidate_customers_cache(user_id: int):
    global _CUSTOMERS_CACHE
    _CUSTOMERS_CACHE.pop(user_id, None)

def safe_date_format(val):
    if not val:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, "strftime"):
        return val.strftime("%Y-%m-%d")
    return str(val)

def safe_iso_format(val):
    if not val:
        return None
    if isinstance(val, str):
        return val
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)

def serialize_product(p):
    return {
        "id": p.id,
        "user_id": p.user_id,
        "product_name": p.product_name,
        "brand": p.brand,
        "category": p.category,
        "batch_number": p.batch_number,
        "quantity": p.quantity,
        "hsn_code": p.hsn_code,
        "gst_rate": p.gst_rate,
        "purchase_price": p.purchase_price,
        "unit_price": p.unit_price,
        "price_per_unit": p.price_per_unit,
        "units_per_pack": p.units_per_pack,
        "is_countable": p.is_countable,
        "needs_review": p.needs_review,
        "gst_percentage": p.gst_percentage,
        "tablets_per_strip": p.tablets_per_strip,
        "loose_tablet_price": p.loose_tablet_price,
        "loose_tablet_stock": p.loose_tablet_stock,
        "total_price": p.total_price,
        "manufacturing_date": safe_date_format(p.manufacturing_date),
        "expiry_date": safe_date_format(p.expiry_date),
        "days_remaining": p.days_remaining,
        "status": p.status,
        "image_path": p.image_path,
        "ocr_text": p.ocr_text,
        "pack_size_label": p.pack_size_label,
        "composition": p.composition,
        "verified": p.verified,
        "pack_size_verified": p.pack_size_verified,
        "price_last_updated": safe_iso_format(p.price_last_updated),
        "supplier_id": p.supplier_id,
        "document_id": p.document_id,
        "invoice_number": p.invoice_number,
        "is_deleted": p.is_deleted,
        "deleted_at": safe_iso_format(p.deleted_at),
        "deleted_by": p.deleted_by
    }


# ===========================
# DATE PARSER
# ===========================

def parse_date(date_value):
    if not date_value:
        return None

    # Product dates read from PostgreSQL may already be date objects.
    if hasattr(date_value, "year") and hasattr(date_value, "month"):
        return date_value

    date_str = str(date_value).strip()

    formats = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%m/%Y",
        "%m-%Y",
        "%b %Y",
        "%B %Y",
        "%d %b %Y",
        "%d %B %Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%m/%y",
    ]

    for fmt in formats:
        try:
            parsed_date = datetime.strptime(date_str, fmt)

            if fmt in [
                "%m/%Y",
                "%m-%Y",
                "%b %Y",
                "%B %Y",
                "%m/%y",
            ]:
                parsed_date = parsed_date.replace(day=1)

            return parsed_date.date()

        except ValueError:
            continue

    cleaned = (
        date_str.upper()
        .replace("EXPIRY", "")
        .replace("EXP.", "")
        .replace("EXP", "")
        .replace("BEST BEFORE", "")
        .replace("BESTBY", "")
        .replace(":", "")
        .strip()
    )

    for fmt in ["%m/%Y", "%m-%Y", "%b %Y", "%B %Y"]:
        try:
            return datetime.strptime(cleaned, fmt).replace(day=1).date()
        except ValueError:
            continue

    raise ValueError(f"Unsupported date format: {date_str}")


# ===========================
# PRODUCT STATUS
# ===========================

def calculate_product_status(expiry_date):
    today = datetime.today().date()
    days_remaining = (expiry_date - today).days

    if days_remaining < 0:
        product_status = "Expired"
    elif days_remaining <= 30:
        product_status = "Expiring Soon"
    else:
        product_status = "Safe"

    return days_remaining, product_status


# ===========================
# GET PRODUCTS
# ===========================

def get_products(
    db: Session,
    user_id: int,
    skip: int = 0,
    limit: Optional[int] = None,
    search: Optional[str] = None,
    filter_key: Optional[str] = None,
    sort_by: Optional[str] = None,
    search_mode: Optional[str] = None,
    include_total: bool = True,
):
    cols = [
        models.Product.id,
        models.Product.user_id,
        models.Product.product_name,
        models.Product.brand,
        models.Product.category,
        models.Product.batch_number,
        models.Product.quantity,
        models.Product.hsn_code,
        models.Product.gst_rate,
        models.Product.purchase_price,
        models.Product.unit_price,
        models.Product.price_per_unit,
        models.Product.units_per_pack,
        models.Product.is_countable,
        models.Product.needs_review,
        models.Product.gst_percentage,
        models.Product.tablets_per_strip,
        models.Product.loose_tablet_price,
        models.Product.loose_tablet_stock,
        models.Product.total_price,
        models.Product.manufacturing_date,
        models.Product.expiry_date,
        models.Product.days_remaining,
        models.Product.status,
        models.Product.image_path,
        models.Product.ocr_text,
        models.Product.pack_size_label,
        models.Product.composition,
        models.Product.verified,
        models.Product.pack_size_verified,
        models.Product.price_last_updated,
        models.Product.supplier_id,
        models.Product.document_id,
        models.Product.invoice_number,
        models.Product.is_deleted,
        models.Product.deleted_at,
        models.Product.deleted_by,
        models.Product.barcode,
    ]

    base_query = db.query(*cols).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
    )

    if search and search.strip():
        s_clean = search.strip().lower()
        s_pref = f"{s_clean}%"
        s_term = f"%{s_clean}%"
        if search_mode == "code":
            base_query = base_query.filter(
                or_(
                    models.Product.barcode.ilike(s_pref),
                    models.Product.batch_number.ilike(s_pref),
                    models.Product.hsn_code.ilike(s_pref),
                )
            )
        else:
            # Fast indexed prefix search matching product name, brand, composition, batch, barcode
            base_query = base_query.filter(
                or_(
                    func.lower(models.Product.product_name).like(s_pref),
                    func.lower(models.Product.brand).like(s_pref),
                    func.lower(models.Product.composition).like(s_pref),
                    models.Product.batch_number.ilike(s_term),
                    models.Product.barcode.ilike(s_term),
                    models.Product.product_name.ilike(s_term),
                )
            )

    if filter_key:
        fk = filter_key.lower().strip()
        today_dt = date.today()
        thirty_days_later_dt = today_dt + timedelta(days=30)
        sixty_days_later_dt = today_dt + timedelta(days=60)

        if fk in ["instock", "in_stock"]:
            base_query = base_query.filter(models.Product.quantity > 0)
        elif fk in ["lowstock", "low_stock", "low_stock_alert"]:
            base_query = base_query.filter(models.Product.quantity > 0, models.Product.quantity <= 20)
        elif fk in ["outofstock", "out_of_stock"]:
            base_query = base_query.filter(models.Product.quantity == 0)
        elif fk in ["expiring", "expiring_30d", "expiring_60d", "expiring_soon", "expiry_risk", "expiry_risk_batches", "at_risk"]:
            base_query = base_query.filter(models.Product.quantity > 0, models.Product.expiry_date.between(today_dt, sixty_days_later_dt))
        elif fk in ["expired", "expired_batches", "expired_stock"]:
            base_query = base_query.filter(models.Product.quantity > 0, models.Product.expiry_date < today_dt)
        elif fk in ["deadstock", "dead_stock", "dead_stock_items"]:
            dt_90d = datetime.utcnow() - timedelta(days=90)
            sold_product_ids_subquery = (
                select(models.SaleItem.product_id)
                .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
                .filter(models.Sale.user_id == user_id, models.Sale.created_at >= dt_90d)
                .scalar_subquery()
            )
            base_query = base_query.filter(
                models.Product.quantity > 0,
                ~models.Product.id.in_(sold_product_ids_subquery)
            )
        elif fk in ["priority_sale", "priority_sales"]:
            p_subquery = (
                select(models.PrioritySale.product_id)
                .filter(models.PrioritySale.user_id == user_id)
                .scalar_subquery()
            )
            base_query = base_query.filter(models.Product.id.in_(p_subquery))
        elif fk in ["marked_for_return", "marked_return", "marked_for_returns"]:
            r_subquery = (
                select(models.MarkedForReturn.product_id)
                .filter(models.MarkedForReturn.user_id == user_id)
                .scalar_subquery()
            )
            base_query = base_query.filter(models.Product.id.in_(r_subquery))

    if search and search.strip():
        s_clean = search.strip().lower()
        s_prefix = f"{s_clean}%"
        if search_mode == "code":
            base_query = base_query.order_by(
                case((func.lower(models.Product.barcode) == s_clean, 1), else_=2),
                case((func.lower(models.Product.barcode).like(s_prefix), 1), else_=2),
                case((func.lower(models.Product.batch_number) == s_clean, 1), else_=2),
                case((func.lower(models.Product.batch_number).like(s_prefix), 1), else_=2),
                models.Product.expiry_date.asc().nullslast()
            )
        elif len(s_clean) < 3:
            base_query = base_query.order_by(
                case((func.lower(models.Product.product_name).like(s_prefix), 1), else_=2),
                models.Product.expiry_date.asc().nullslast()
            )
        else:
            base_query = base_query.order_by(
                case((func.lower(models.Product.product_name) == s_clean, 1), else_=2),
                case((func.lower(models.Product.product_name).like(s_prefix), 1), else_=2),
                case((func.lower(models.Product.barcode) == s_clean, 1), else_=2),
                models.Product.expiry_date.asc().nullslast()
            )
    elif sort_by in ["name", "name_asc"]:
        base_query = base_query.order_by(models.Product.product_name.asc())
    elif sort_by in ["expiry", "expiry_asc", "fefo"]:
        base_query = base_query.order_by(models.Product.expiry_date.asc().nullslast())
    elif sort_by in ["quantity", "quantity_desc"]:
        base_query = base_query.order_by(models.Product.quantity.desc())
    else:
        base_query = base_query.order_by(models.Product.id.desc())

    if limit and limit > 0:
        if include_total:
            total_count = db.query(models.Product.id).filter(
                models.Product.user_id == user_id,
                models.Product.is_deleted == False,
            ).count() if not (search or filter_key) else base_query.count()
        else:
            total_count = limit

        rows = base_query.offset(skip).limit(limit).all()
        serialized = []
        for row in rows:
            serialized.append({
                "id": row[0],
                "user_id": row[1],
                "product_name": row[2],
                "brand": row[3],
                "category": row[4],
                "batch_number": row[5],
                "quantity": row[6],
                "hsn_code": row[7],
                "gst_rate": row[8],
                "purchase_price": row[9],
                "unit_price": row[10],
                "price_per_unit": row[11],
                "units_per_pack": row[12],
                "is_countable": row[13],
                "needs_review": row[14],
                "gst_percentage": row[15],
                "tablets_per_strip": row[16],
                "loose_tablet_price": row[17],
                "loose_tablet_stock": row[18],
                "total_price": row[19],
                "manufacturing_date": safe_date_format(row[20]),
                "expiry_date": safe_date_format(row[21]),
                "days_remaining": row[22],
                "status": row[23],
                "image_path": row[24],
                "ocr_text": row[25],
                "pack_size_label": row[26],
                "composition": row[27],
                "verified": row[28],
                "pack_size_verified": row[29],
                "price_last_updated": safe_iso_format(row[30]),
                "supplier_id": row[31],
                "document_id": row[32],
                "invoice_number": row[33],
                "is_deleted": row[34],
                "deleted_at": safe_iso_format(row[35]),
                "deleted_by": row[36],
                "barcode": row[37] if len(row) > 37 else None,
            })

        return {
            "items": serialized,
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "pages": (total_count + limit - 1) // limit if limit > 0 else 1,
        }
    else:
        rows = base_query.all()
        serialized = []
        for row in rows:
            serialized.append({
                "id": row[0],
                "user_id": row[1],
                "product_name": row[2],
                "brand": row[3],
                "category": row[4],
                "batch_number": row[5],
                "quantity": row[6],
                "hsn_code": row[7],
                "gst_rate": row[8],
                "purchase_price": row[9],
                "unit_price": row[10],
                "price_per_unit": row[11],
                "units_per_pack": row[12],
                "is_countable": row[13],
                "needs_review": row[14],
                "gst_percentage": row[15],
                "tablets_per_strip": row[16],
                "loose_tablet_price": row[17],
                "loose_tablet_stock": row[18],
                "total_price": row[19],
                "manufacturing_date": safe_date_format(row[20]),
                "expiry_date": safe_date_format(row[21]),
                "days_remaining": row[22],
                "status": row[23],
                "image_path": row[24],
                "ocr_text": row[25],
                "pack_size_label": row[26],
                "composition": row[27],
                "verified": row[28],
                "pack_size_verified": row[29],
                "price_last_updated": safe_iso_format(row[30]),
                "supplier_id": row[31],
                "document_id": row[32],
                "invoice_number": row[33],
                "is_deleted": row[34],
                "deleted_at": safe_iso_format(row[35]),
                "deleted_by": row[36],
                "barcode": row[37] if len(row) > 37 else None,
            })
        return serialized


def get_billing_search_products(
    db: Session,
    user_id: int,
    query: str,
    search_mode: Optional[str] = "name",
    limit: int = 15,
) -> List[dict]:
    clean_q = (query or "").strip().lower()
    if not clean_q:
        return []

    s_pref = f"{clean_q}%"
    s_term = f"%{clean_q}%"

    cols = [
        models.Product.id,
        models.Product.user_id,
        models.Product.product_name,
        models.Product.brand,
        models.Product.category,
        models.Product.batch_number,
        models.Product.quantity,
        models.Product.hsn_code,
        models.Product.gst_rate,
        models.Product.purchase_price,
        models.Product.unit_price,
        models.Product.price_per_unit,
        models.Product.units_per_pack,
        models.Product.is_countable,
        models.Product.needs_review,
        models.Product.gst_percentage,
        models.Product.tablets_per_strip,
        models.Product.loose_tablet_price,
        models.Product.loose_tablet_stock,
        models.Product.total_price,
        models.Product.manufacturing_date,
        models.Product.expiry_date,
        models.Product.days_remaining,
        models.Product.status,
        models.Product.pack_size_label,
        models.Product.composition,
        models.Product.barcode,
    ]

    # Stage 1: B-Tree Indexed Prefix Search (Sub-5ms execution time)
    prefix_query = db.query(*cols).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
        or_(
            func.lower(models.Product.product_name).like(s_pref),
            func.lower(models.Product.brand).like(s_pref),
            func.lower(models.Product.composition).like(s_pref),
            models.Product.barcode.ilike(s_pref),
            models.Product.batch_number.ilike(s_pref),
        )
    ).order_by(
        case((func.lower(models.Product.product_name) == clean_q, 1), else_=2),
        case((func.lower(models.Product.product_name).like(s_pref), 1), else_=2),
        models.Product.expiry_date.asc().nullslast()
    ).limit(limit)

    rows = prefix_query.all()

    # Stage 2: Secondary substring fallback if prefix search returned < limit
    if len(rows) < limit:
        existing_ids = [r[0] for r in rows]
        needed = limit - len(rows)
        sub_query = db.query(*cols).filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
            ~models.Product.id.in_(existing_ids) if existing_ids else True,
            or_(
                models.Product.product_name.ilike(s_term),
                models.Product.brand.ilike(s_term),
                models.Product.composition.ilike(s_term),
                models.Product.batch_number.ilike(s_term),
                models.Product.barcode.ilike(s_term),
            )
        ).order_by(models.Product.expiry_date.asc().nullslast()).limit(needed)
        rows.extend(sub_query.all())

    results = []
    for row in rows:
        results.append({
            "id": row[0],
            "user_id": row[1],
            "product_name": row[2],
            "brand": row[3],
            "category": row[4],
            "batch_number": row[5],
            "quantity": row[6],
            "hsn_code": row[7],
            "gst_rate": row[8],
            "purchase_price": row[9],
            "unit_price": row[10],
            "price_per_unit": row[11],
            "units_per_pack": row[12],
            "is_countable": row[13],
            "needs_review": row[14],
            "gst_percentage": row[15],
            "tablets_per_strip": row[16],
            "loose_tablet_price": row[17],
            "loose_tablet_stock": row[18],
            "total_price": row[19],
            "manufacturing_date": safe_date_format(row[20]),
            "expiry_date": safe_date_format(row[21]),
            "days_remaining": row[22],
            "status": row[23],
            "pack_size_label": row[24],
            "composition": row[25],
            "barcode": row[26],
        })

    return results


def get_product(db: Session, product_id: int, user_id: int):
    return (
        db.query(models.Product)
        .filter(
            models.Product.id == product_id,
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
        )
        .first()
    )


# ===========================
# CREATE PRODUCT
# ===========================

def create_product(
    db: Session,
    product: schemas.ProductCreate,
    user_id: int,
):
    expiry = parse_date(product.expiry_date)
    manufacturing = (
        parse_date(product.manufacturing_date)
        if product.manufacturing_date
        else None
    )

    days_remaining, product_status = calculate_product_status(expiry)

    effective_price = product.price if (product.price is not None and product.price > 0) else product.unit_price
    calc_total_price = product.total_price if product.total_price > 0 else (product.quantity * effective_price)

    db_product = models.Product(
        user_id=user_id,
        product_name=product.product_name,
        brand=product.brand,
        category=product.category,
        batch_number=product.batch_number,
        quantity=product.quantity,
        unit_price=effective_price,
        total_price=calc_total_price,
        manufacturing_date=manufacturing,
        expiry_date=expiry,
        days_remaining=days_remaining,
        status=product_status,
        image_path=product.image_path,
        ocr_text=product.ocr_text,
    )

    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    invalidate_products_cache(user_id)

    return db_product


# ===========================
# UPDATE PRODUCT
# ===========================

def update_product(
    db: Session,
    product_id: int,
    product: schemas.ProductCreate,
    user_id: int,
):
    db_product = get_product(db, product_id, user_id)

    if db_product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this shop.",
        )

    expiry = parse_date(product.expiry_date)
    manufacturing = (
        parse_date(product.manufacturing_date)
        if product.manufacturing_date
        else None
    )

    days_remaining, product_status = calculate_product_status(expiry)

    effective_price = product.price if (product.price is not None and product.price > 0) else product.unit_price

    db_product.product_name = product.product_name
    db_product.brand = product.brand
    db_product.category = product.category
    db_product.batch_number = product.batch_number
    db_product.quantity = product.quantity
    db_product.unit_price = effective_price
    db_product.total_price = product.total_price if product.total_price > 0 else (product.quantity * effective_price)
    db_product.manufacturing_date = manufacturing
    db_product.expiry_date = expiry
    db_product.days_remaining = days_remaining
    db_product.status = product_status
    db_product.image_path = product.image_path
    db_product.ocr_text = product.ocr_text

    db.commit()
    invalidate_products_cache(user_id)
    return db_product


# ===========================
# DELETE PRODUCT
# ===========================

def delete_product(
    db: Session,
    product_id: int,
    user_id: int,
):
    db_product = get_product(db, product_id, user_id)

    if db_product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found for this shop.",
        )

    db_product.is_deleted = True
    db_product.deleted_at = datetime.utcnow()
    db_product.deleted_by = user_id
    db.commit()
    invalidate_products_cache(user_id)

    return {"message": "Product moved to Recently Deleted, recoverable for 60 days.", "is_deleted": True}


# ===========================
# SELL / PURCHASE TRANSACTION
# ===========================

def create_transaction(
    db: Session,
    transaction: schemas.TransactionCreate,
    shop_id: int,
):
    """
    Creates one purchase or sale transaction.
    Locks row to prevent overselling.
    """
    try:
        product = (
            db.query(models.Product)
            .filter(
                models.Product.id == transaction.product_id,
                models.Product.user_id == shop_id,
                models.Product.is_deleted == False,
            )
            .with_for_update()
            .first()
        )

        if product is None:
            raise HTTPException(
                status_code=404,
                detail="Product not found for this shop.",
            )

        subtotal = transaction.unit_price * transaction.quantity
        discount_amount = 0.0

        if transaction.transaction_type == "sell":
            if product.quantity < transaction.quantity:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Insufficient stock. Available quantity: "
                        f"{product.quantity}."
                    ),
                )

            if transaction.discount_type == "flat":
                discount_amount = transaction.discount_value or 0.0

            elif transaction.discount_type == "percent":
                discount_amount = (
                    subtotal * (transaction.discount_value or 0.0) / 100
                )

            if discount_amount > subtotal:
                raise HTTPException(
                    status_code=422,
                    detail="Discount cannot be greater than the bill subtotal.",
                )

            final_price = subtotal - discount_amount
            product.quantity -= transaction.quantity

        else:
            final_price = subtotal
            product.quantity += transaction.quantity

        new_transaction = models.InventoryTransaction(
            transaction_id=(
                f"TXN-{datetime.utcnow():%Y%m%d%H%M%S}-"
                f"{uuid.uuid4().hex[:8].upper()}"
            ),
            shop_id=shop_id,
            product_id=product.id,
            transaction_type=transaction.transaction_type,
            quantity=transaction.quantity,
            unit_price=transaction.unit_price,
            discount_type=transaction.discount_type,
            discount_value=transaction.discount_value,
            final_price=final_price,
        )

        db.add(new_transaction)
        db.commit()
        db.refresh(new_transaction)

        return new_transaction

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


# ===========================
# POS / COUNTER SALES TRANSACTION
# ===========================

def generate_bill_number() -> str:
    return f"BILL-{uuid.uuid4().hex[:6].upper()}"


def deduct_product_stock(
    product: models.Product,
    quantity: int,
    unit_type: str = "strip",
    tablets_per_strip_override: Optional[int] = None,
) -> dict:
    """
    Atomically and mathematically deducts inventory stock for a product batch.
    
    Pack configuration:
      - product.quantity: Sealed strip count
      - product.loose_tablet_stock: Individual loose tablets
      - tablets_per_strip: Number of tablets per strip
      - total_available_tablets = (product.quantity * tablets_per_strip) + product.loose_tablet_stock

    Rules:
      1. When selling 'strip':
         - Requires product.quantity >= quantity.
         - Decrements product.quantity by quantity.
         - Loose tablet stock remains untouched.
      2. When selling 'loose_tablet' / 'pill' / 'loose':
         - Requires valid pack configuration (tablets_per_strip > 0).
         - Checks total_available_tablets >= quantity.
         - If product.loose_tablet_stock >= quantity:
             Deducts directly from loose_tablet_stock.
         - If product.loose_tablet_stock < quantity:
             Breaks necessary strips from sealed stock:
             strips_to_open = (needed + tabs_per_strip - 1) // tabs_per_strip
             product.quantity -= strips_to_open
             product.loose_tablet_stock += (strips_to_open * tabs_per_strip) - quantity
         - Guarantees: remaining_total_tablets == total_available_tablets - quantity.
      3. Never allows negative stock.
      4. Keeps product.total_price mathematically synchronized.
    """
    if quantity <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sale quantity for '{product.product_name}' must be greater than zero.",
        )

    # Expiry Guard: Never dispense expired medicine batches
    if product.expiry_date and product.expiry_date < date.today():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot dispense expired medicine '{product.product_name}' "
                f"(Batch: {product.batch_number}, Expired on: {product.expiry_date}). "
                f"Please quarantine or return this batch to distributor."
            ),
        )

    is_strip = str(unit_type or "strip").lower() in ["strip", "pack"]
    current_strips = int(product.quantity or 0)
    current_loose = int(product.loose_tablet_stock or 0)

    # Resolve tablets per strip
    tabs_per_pack = (
        tablets_per_strip_override
        or getattr(product, "tablets_per_strip", None)
        or getattr(product, "units_per_pack", None)
    )

    if is_strip:
        if current_strips < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient strip stock for '{product.product_name}'. "
                    f"Available: {current_strips}, requested: {quantity}."
                ),
            )
        product.quantity = current_strips - quantity
        product.loose_tablet_stock = current_loose
        strips_opened = 0
    else:
        if tabs_per_pack is None or tabs_per_pack <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Pack configuration (tablets per strip) is missing for '{product.product_name}'. "
                    f"Please configure tablets per strip before selling loose tablets."
                ),
            )

        # Synchronize product model with validated pack size
        if product.tablets_per_strip is None or product.tablets_per_strip <= 0:
            product.tablets_per_strip = tabs_per_pack
        if product.units_per_pack is None or product.units_per_pack <= 0:
            product.units_per_pack = tabs_per_pack

        total_available_tablets = (current_strips * tabs_per_pack) + current_loose

        if total_available_tablets < quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Insufficient loose-tablet stock for '{product.product_name}'. "
                    f"Available: {total_available_tablets}, "
                    f"requested: {quantity}."
                ),
            )

        if current_loose >= quantity:
            product.loose_tablet_stock = current_loose - quantity
            product.quantity = current_strips
            strips_opened = 0
        else:
            tablets_needed_from_sealed = quantity - current_loose
            strips_to_open = (
                tablets_needed_from_sealed + tabs_per_pack - 1
            ) // tabs_per_pack

            if current_strips < strips_to_open:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient stock for '{product.product_name}'. "
                        f"Needed {strips_to_open} strips to fulfill {quantity} loose tablets, "
                        f"but only {current_strips} strips available."
                    ),
                )

            product.quantity = current_strips - strips_to_open
            product.loose_tablet_stock = (
                current_loose + (strips_to_open * tabs_per_pack)
            ) - quantity
            strips_opened = strips_to_open

    # Safeguard: never negative
    if (product.quantity or 0) < 0 or (product.loose_tablet_stock or 0) < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory error: Stock for '{product.product_name}' cannot be negative.",
        )

    # Keep total_price synchronized
    product.total_price = round(
        float(product.quantity or 0) * float(product.unit_price or 0.0), 2
    )

    remaining_tablets = (
        ((product.quantity or 0) * (tabs_per_pack or 10)) + (product.loose_tablet_stock or 0)
        if tabs_per_pack
        else (product.quantity or 0)
    )

    return {
        "unit_type": "strip" if is_strip else "loose_tablet",
        "quantity_sold": quantity,
        "strips_opened": strips_opened,
        "remaining_strips": product.quantity,
        "remaining_loose": product.loose_tablet_stock,
        "total_remaining_tablets": remaining_tablets,
    }


def create_sale_transaction(
    db: Session,
    sale_data: schemas.SaleCreate,
    user_id: int,
    current_user: Optional[models.User] = None,
    verified_idempotency: bool = False,
):
    """
    Completes one pharmacy bill in a single optimized database transaction.
    """
    try:
        if current_user is not None:
            shop = current_user
        else:
            shop = (
                db.query(models.User)
                .filter(models.User.id == user_id)
                .first()
            )
            if shop is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Shop user not found.",
                )

        # Idempotency check: if an idempotency key is provided and not pre-verified, check database
        raw_idemp = getattr(sale_data, "idempotency_key", None)
        clean_idemp = str(raw_idemp).strip() if (raw_idemp and str(raw_idemp).strip()) else None
        if clean_idemp and not verified_idempotency:
            existing_sale = (
                db.query(models.Sale)
                .filter(
                    models.Sale.user_id == user_id,
                    models.Sale.idempotency_key == clean_idemp,
                )
                .first()
            )
            if existing_sale:
                logger.info(
                    f"[IDEMPOTENCY] Found existing sale #{existing_sale.id} ({existing_sale.bill_number}) "
                    f"for idempotency key '{clean_idemp}'. Returning without duplicate stock deduction."
                )
                return existing_sale

        # Batch-fetch and lock all distinct product rows in a single DB round-trip
        product_ids = list({item.product_id for item in sale_data.items})
        locked_products = (
            db.query(models.Product)
            .filter(
                models.Product.id.in_(product_ids),
                models.Product.user_id == user_id,
                models.Product.is_deleted == False,
            )
            .with_for_update()
            .all()
        )
        prod_map = {p.id: p for p in locked_products}

        prepared_items = []
        gross_subtotal = 0.0
        line_discount_total = 0.0
        default_shop_gst = shop.default_gst_percentage or 12.0

        # Process every cart item using batch-loaded products in memory
        for item in sale_data.items:
            product = prod_map.get(item.product_id)
            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product ID {item.product_id} was not found for this shop.",
                )

            # If user explicitly selected a batch_number that differs from product.batch_number, resolve exact batch
            req_batch = (item.batch_number or "").strip()
            if req_batch and product.batch_number and product.batch_number.strip() != req_batch:
                selected_batch_product = (
                    db.query(models.Product)
                    .filter(
                        models.Product.user_id == user_id,
                        models.Product.is_deleted == False,
                        func.lower(models.Product.product_name) == func.lower(product.product_name),
                        models.Product.batch_number == req_batch
                    )
                    .first()
                )
                if selected_batch_product:
                    product = selected_batch_product

            is_strip = str(item.unit_type or "strip").lower() in ["strip", "pack"]

            # Authoritative tablets per strip resolution
            item_tabs = getattr(item, "tablets_per_strip", None) or getattr(item, "units_per_pack", None)
            tablets_per_pack = (
                item_tabs
                or getattr(product, "tablets_per_strip", None)
                or getattr(product, "units_per_pack", None)
            )

            # Decide the sale price.
            if item.unit_price is not None and item.unit_price > 0:
                unit_price = item.unit_price
            elif is_strip:
                unit_price = product.unit_price
            else:
                if product.price_per_unit is not None and product.price_per_unit > 0:
                    unit_price = product.price_per_unit
                elif product.loose_tablet_price is not None and product.loose_tablet_price > 0:
                    unit_price = product.loose_tablet_price
                elif product.unit_price > 0:
                    unit_price = round(product.unit_price / (tablets_per_pack or 10), 2)
                else:
                    unit_price = 0.0

            # Atomic and mathematically consistent stock deduction
            deduct_product_stock(
                product=product,
                quantity=item.quantity,
                unit_type=item.unit_type,
                tablets_per_strip_override=item_tabs,
            )

            gross_line_total = round(unit_price * item.quantity, 2)
            line_discount = round(item.discount or 0.0, 2)

            if line_discount > gross_line_total:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Line discount cannot exceed the price of "
                        f"'{product.product_name}'."
                    ),
                )

            taxable_line_total = round(gross_line_total - line_discount, 2)

            item_hsn = getattr(product, "hsn_code", None) or "3004"
            gst_percentage = (
                item.gst_percentage
                if item.gst_percentage is not None
                else (
                    product.gst_percentage
                    if (product.gst_percentage is not None and product.gst_percentage > 0)
                    else (
                        getattr(product, "gst_rate", None)
                        if (getattr(product, "gst_rate", None) is not None and product.gst_rate > 0)
                        else default_shop_gst
                    )
                )
            )

            gross_subtotal += gross_line_total
            line_discount_total += line_discount

            prepared_items.append(
                {
                    "product": product,
                    "item": item,
                    "unit_price": unit_price,
                    "gross_line_total": gross_line_total,
                    "line_discount": line_discount,
                    "taxable_line_total": taxable_line_total,
                    "gst_percentage": gst_percentage,
                }
            )

        # Feature 5: Customer Lookup & Auto-apply patient fixed discount (Single Combined Query)
        customer_record = None
        target_cust_name = (sale_data.customer_name or "").strip()
        is_walkin = (not target_cust_name or target_cust_name.lower() in ["walk-in customer", "walkin", "cash customer", "cash sale", "walk-in", ""])
        has_phone = bool(sale_data.customer_phone and sale_data.customer_phone.strip() not in ["", "N/A", "null", "undefined", "none"])

        if getattr(sale_data, "customer_id", None):
            customer_record = db.query(models.Customer).filter(
                models.Customer.id == sale_data.customer_id,
                models.Customer.user_id == user_id,
            ).first()
        elif has_phone:
            customer_record = db.query(models.Customer).filter(
                models.Customer.user_id == user_id,
                models.Customer.phone == sale_data.customer_phone.strip()
            ).first()
        elif not is_walkin:
            customer_record = db.query(models.Customer).filter(
                models.Customer.user_id == user_id,
                func.lower(models.Customer.name) == target_cust_name.lower()
            ).first()

        if customer_record and customer_record.fixed_discount_percent > 0 and (sale_data.discount_type is None or sale_data.discount_value == 0):
            sale_data.discount_type = "percent"
            sale_data.discount_value = customer_record.fixed_discount_percent

        taxable_subtotal = round(gross_subtotal - line_discount_total, 2)

        # Calculate bill-level discount.
        if sale_data.discount_type == "percent":
            bill_discount_amount = round(
                taxable_subtotal * sale_data.discount_value / 100,
                2,
            )
        else:
            bill_discount_amount = round(sale_data.discount_value, 2)

        if bill_discount_amount > taxable_subtotal:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bill discount cannot exceed the taxable subtotal.",
            )

        bill_number = generate_bill_number()
        sale_items_to_create = []
        total_taxable_value = 0.0
        total_cgst = 0.0
        total_sgst = 0.0
        total_igst = 0.0
        total_gst_amount = 0.0
        final_total = 0.0
        allocated_bill_discount = 0.0

        # Allocate bill discount across lines, then calculate CGST/SGST/IGST per line.
        for index, prepared in enumerate(prepared_items):
            is_last_item = index == len(prepared_items) - 1

            if is_last_item:
                allocated_discount = round(
                    bill_discount_amount - allocated_bill_discount,
                    2,
                )
            elif taxable_subtotal > 0:
                allocated_discount = round(
                    bill_discount_amount
                    * prepared["taxable_line_total"]
                    / taxable_subtotal,
                    2,
                )
                allocated_bill_discount += allocated_discount
            else:
                allocated_discount = 0.0

            final_taxable_line_total = round(
                prepared["taxable_line_total"] - allocated_discount,
                2,
            )

            hsn = getattr(prepared["product"], "hsn_code", None) or "3004"
            gst_pct = float(prepared["gst_percentage"])

            if getattr(sale_data, "is_interstate", False):
                cgst_r, cgst_a = 0.0, 0.0
                sgst_r, sgst_a = 0.0, 0.0
                igst_r = gst_pct
                igst_a = round(final_taxable_line_total * (igst_r / 100.0), 2)
            else:
                cgst_r = round(gst_pct / 2.0, 2)
                sgst_r = round(gst_pct / 2.0, 2)
                cgst_a = round(final_taxable_line_total * (cgst_r / 100.0), 2)
                sgst_a = round(final_taxable_line_total * (sgst_r / 100.0), 2)
                igst_r, igst_a = 0.0, 0.0

            line_tax = round(cgst_a + sgst_a + igst_a, 2)
            final_line_total = round(final_taxable_line_total + line_tax, 2)

            total_taxable_value += final_taxable_line_total
            total_cgst += cgst_a
            total_sgst += sgst_a
            total_igst += igst_a
            total_gst_amount += line_tax
            final_total += final_line_total

            _new_sale_item = models.SaleItem(
                product_id=prepared["product"].id,
                product_name=prepared["product"].product_name,
                hsn_code=hsn,
                quantity=prepared["item"].quantity,
                unit_type=prepared["item"].unit_type,
                unit_price=prepared["unit_price"],
                discount=prepared["line_discount"] + allocated_discount,
                gst_percentage=gst_pct,
                gst_amount=line_tax,
                taxable_value=final_taxable_line_total,
                cgst_rate=cgst_r,
                cgst_amount=cgst_a,
                sgst_rate=sgst_r,
                sgst_amount=sgst_a,
                igst_rate=igst_r,
                igst_amount=igst_a,
                total_with_tax=final_line_total,
                total_price=final_line_total,
                line_total=final_line_total,
                batch_number=(
                    prepared["item"].batch_number
                    or prepared["product"].batch_number
                ),
                tablets_per_strip=prepared["product"].tablets_per_strip,
            )
            _new_sale_item.return_items = []
            sale_items_to_create.append(_new_sale_item)

        # Tax Summary Table grouped by GST Rate
        tax_summary_dict = {}
        for item in sale_items_to_create:
            rate_key = float(item.gst_percentage)
            if rate_key not in tax_summary_dict:
                tax_summary_dict[rate_key] = {
                    "gst_rate": rate_key,
                    "taxable_value": 0.0,
                    "cgst_amount": 0.0,
                    "sgst_amount": 0.0,
                    "igst_amount": 0.0,
                    "total_tax": 0.0,
                }
            tax_summary_dict[rate_key]["taxable_value"] = round(tax_summary_dict[rate_key]["taxable_value"] + item.taxable_value, 2)
            tax_summary_dict[rate_key]["cgst_amount"] = round(tax_summary_dict[rate_key]["cgst_amount"] + item.cgst_amount, 2)
            tax_summary_dict[rate_key]["sgst_amount"] = round(tax_summary_dict[rate_key]["sgst_amount"] + item.sgst_amount, 2)
            tax_summary_dict[rate_key]["igst_amount"] = round(tax_summary_dict[rate_key]["igst_amount"] + item.igst_amount, 2)
            tax_summary_dict[rate_key]["total_tax"] = round(tax_summary_dict[rate_key]["total_tax"] + item.cgst_amount + item.sgst_amount + item.igst_amount, 2)

        tax_summary_list = list(tax_summary_dict.values())

        # Handle Payment allocations (Single or Split payment)
        raw_payments = getattr(sale_data, "payments", None)
        has_split_payments = bool(raw_payments and len(raw_payments) > 0)

        # Consolidate payment allocations
        allocations: Dict[str, float] = {}
        if has_split_payments:
            for p in raw_payments:
                pm = (p.payment_method or "CASH").strip().upper()
                if pm == "PENDING":
                    pm = "CREDIT"
                if pm not in ["CASH", "UPI", "CARD", "CREDIT"]:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Invalid payment method '{p.payment_method}'. Allowed methods: CASH, UPI, CARD, CREDIT.",
                    )
                amt = float(p.amount)
                if amt <= 0:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Payment allocation amount must be greater than zero.",
                    )
                allocations[pm] = round(allocations.get(pm, 0.0) + amt, 2)
            
            allocated_total = round(sum(allocations.values()), 2)
            if abs(allocated_total - final_total) > 0.01:
                if allocated_total > final_total:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Payment amount exceeds the bill total. Allocated: ₹{allocated_total:.2f}, Bill Total: ₹{final_total:.2f}.",
                    )
                else:
                    remaining_unpaid = round(final_total - allocated_total, 2)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Payment incomplete. ₹{remaining_unpaid:.2f} remaining unpaid.",
                    )
        else:
            # Single payment method
            pm = (sale_data.payment_method or "CASH").strip().upper()
            if pm == "PENDING":
                pm = "CREDIT"
            if pm not in ["CASH", "UPI", "CARD", "CREDIT"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid payment method '{sale_data.payment_method}'. Allowed methods: CASH, UPI, CARD, CREDIT.",
                )
            allocations[pm] = round(final_total, 2)

        credit_amount = allocations.get("CREDIT", 0.0)
        has_credit = credit_amount > 0.0

        if has_credit and (is_walkin or not target_cust_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A customer must be selected for Credit / Khata billing.",
            )

        if not is_walkin and target_cust_name:
            if not customer_record:
                # Create customer on the fly safely with nested savepoint
                try:
                    with db.begin_nested():
                        customer_record = models.Customer(
                            user_id=user_id,
                            name=target_cust_name,
                            phone=sale_data.customer_phone.strip() if (sale_data.customer_phone and sale_data.customer_phone.strip()) else "N/A",
                            pending_amount=round(credit_amount, 2)
                        )
                        db.add(customer_record)
                        db.flush()
                except Exception:
                    # Parallel insertion occurred, query existing customer
                    customer_record = db.query(models.Customer).filter(
                        models.Customer.user_id == user_id,
                        func.lower(models.Customer.name) == target_cust_name.lower()
                    ).first()
                    if customer_record and has_credit:
                        customer_record.pending_amount = round((customer_record.pending_amount or 0.0) + credit_amount, 2)
            elif has_credit:
                customer_record.pending_amount = round((customer_record.pending_amount or 0.0) + credit_amount, 2)

        # Determine top-level payment_method and payment_status
        is_multi_split = len(allocations) > 1
        if is_multi_split:
            top_payment_method = "SPLIT"
        else:
            top_payment_method = list(allocations.keys())[0]

        payment_status = "PENDING" if has_credit else "PAID"

        # Create SalePayment records atomically with db_sale without intermediate flush round-trips
        created_payments = []
        for method_key, method_amt in allocations.items():
            sp = models.SalePayment(
                user_id=user_id,
                payment_method=method_key,
                amount=method_amt,
                created_at=datetime.utcnow(),
            )
            created_payments.append(sp)

        db_sale = models.Sale(
            user_id=user_id,
            bill_number=bill_number,
            subtotal=round(gross_subtotal, 2),
            discount_amount=round(
                line_discount_total + bill_discount_amount,
                2,
            ),
            tax_amount=round(total_gst_amount, 2),
            total_amount=round(final_total, 2),
            is_interstate=getattr(sale_data, "is_interstate", False),
            total_taxable_value=round(total_taxable_value, 2),
            total_cgst=round(total_cgst, 2),
            total_sgst=round(total_sgst, 2),
            total_igst=round(total_igst, 2),
            tax_summary_json=json.dumps(tax_summary_list),
            gst_number=getattr(shop, "gstin", None) or shop.gst_number or "07AABCE1234F1Z5",
            gst_percentage=shop.default_gst_percentage,
            discount_type=sale_data.discount_type,
            discount_value=sale_data.discount_value,
            payment_method=top_payment_method,
            payment_status=payment_status,
            is_split_payment=is_multi_split,
            staff_id=getattr(current_user, "staff_id", None) if current_user else None,
            staff_name=getattr(current_user, "name", None) if current_user and getattr(current_user, "staff_id", None) else None,
            customer_id=customer_record.id if customer_record else None,
            customer_name=target_cust_name or "Walk-in Customer",
            customer_phone=sale_data.customer_phone,
            doctor_name=sale_data.doctor_name,
            doctor_reg_no=sale_data.doctor_reg_no,
            notes=sale_data.notes,
            return_status="completed",
            is_completed_on_mobile=True,
            items=sale_items_to_create,
            payments=created_payments,
            idempotency_key=clean_idemp,
            created_at=datetime.utcnow(),
        )
        db_sale.returns = []

        db.add(db_sale)

        # If this sale was generated from a held bill, mark that held bill COMPLETED
        held_bill_id = getattr(sale_data, "held_bill_id", None)
        if held_bill_id:
            held_bill = (
                db.query(models.HeldBill)
                .filter(
                    models.HeldBill.id == held_bill_id,
                    models.HeldBill.user_id == user_id,
                )
                .first()
            )
            if held_bill:
                held_bill.status = "COMPLETED"
                held_bill.completed_at = datetime.utcnow()
                held_bill.completed_sale_id = db_sale.id
                held_bill.updated_at = datetime.utcnow()

        db.commit()
        invalidate_products_cache(user_id)
        invalidate_customers_cache(user_id)
        db_sale.items = sale_items_to_create
        db_sale.payments = created_payments
        db_sale.returns = []
        return db_sale

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise
# ===========================
# SALE RETURNS
# ===========================

def create_sale_return(
    db: Session,
    sale_id: int,
    return_data: schemas.SaleReturnCreate,
    user_id: int,
):
    sale = (
        db.query(models.Sale)
        .filter(
            models.Sale.id == sale_id,
            models.Sale.user_id == user_id,
        )
        .with_for_update()
        .first()
    )

    if sale is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale bill not found for this shop.",
        )

    if sale.return_status == "returned":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This bill is already fully returned.",
        )

    total_refund = 0.0
    return_items = []

    try:
        for item in return_data.items:
            sale_item = (
                db.query(models.SaleItem)
                .filter(
                    models.SaleItem.id == item.sale_item_id,
                    models.SaleItem.sale_id == sale.id,
                )
                .with_for_update()
                .first()
            )

            if sale_item is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Sale item ID {item.sale_item_id} not found.",
                )

            already_returned_quantity = (
                db.query(func.coalesce(func.sum(models.SaleReturnItem.quantity), 0))
                .filter(models.SaleReturnItem.sale_item_id == sale_item.id)
                .scalar()
            )

            remaining_returnable = sale_item.quantity - already_returned_quantity

            if item.quantity <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Return quantity must be greater than 0.",
                )

            if item.quantity > remaining_returnable:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Cannot return {item.quantity} units of "
                        f"{sale_item.product_name}. Returnable quantity: "
                        f"{remaining_returnable}."
                    ),
                )

            product = (
                db.query(models.Product)
                .filter(
                    models.Product.id == sale_item.product_id,
                    models.Product.user_id == user_id,
                )
                .with_for_update()
                .first()
            )

            if product is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product for {sale_item.product_name} not found.",
                )

            if sale_item.unit_type == "loose_tablet":
                product.loose_tablet_stock += item.quantity
            else:
                product.quantity += item.quantity

            refund_amount = round(
                sale_item.total_price * item.quantity / sale_item.quantity,
                2,
            )

            total_refund += refund_amount

            return_items.append(
                models.SaleReturnItem(
                    sale_item_id=sale_item.id,
                    product_id=product.id,
                    quantity=item.quantity,
                    unit_price=sale_item.unit_price,
                    return_total=refund_amount,
                )
            )

        sale_return = models.SaleReturn(
            sale_id=sale.id,
            user_id=user_id,
            reason=return_data.reason,
            return_amount=round(total_refund, 2),
            items=return_items,
        )

        db.add(sale_return)

        total_sold_quantity = sum(item.quantity for item in sale.items)

        total_returned_quantity = (
            db.query(func.coalesce(func.sum(models.SaleReturnItem.quantity), 0))
            .join(models.SaleReturn)
            .filter(models.SaleReturn.sale_id == sale.id)
            .scalar()
        ) + sum(item.quantity for item in return_data.items)

        if total_returned_quantity >= total_sold_quantity:
            sale.return_status = "returned"
        else:
            sale.return_status = "partially_returned"

        # Reconcile customer khata if original sale had credit allocation
        if sale.customer_id:
            customer = (
                db.query(models.Customer)
                .filter(models.Customer.id == sale.customer_id, models.Customer.user_id == user_id)
                .with_for_update()
                .first()
            )
            if customer:
                credit_allocated = 0.0
                if sale.payment_method in ["CREDIT", "PENDING"]:
                    credit_allocated = float(sale.total_amount or 0.0)
                elif sale.is_split_payment:
                    credit_sp = db.query(func.sum(models.SalePayment.amount)).filter(
                        models.SalePayment.sale_id == sale.id,
                        models.SalePayment.payment_method == "CREDIT"
                    ).scalar()
                    credit_allocated = float(credit_sp or 0.0)

                if credit_allocated > 0:
                    reduction = min(round(total_refund, 2), float(customer.pending_amount or 0.0))
                    customer.pending_amount = max(0.0, round(float(customer.pending_amount or 0.0) - reduction, 2))
                    invalidate_customers_cache(user_id)

        invalidate_products_cache(user_id)
        db.commit()
        db.refresh(sale_return)

        return sale_return

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


def get_todays_returns(
    db: Session,
    user_id: int,
):
    today = datetime.utcnow().date()

    return (
        db.query(models.SaleReturn)
        .filter(
            models.SaleReturn.user_id == user_id,
            func.date(models.SaleReturn.created_at) == today,
        )
        .order_by(models.SaleReturn.created_at.desc())
        .all()
    )

# ===========================
# HELD BILLS (PARK / RESUME)
# ===========================

def generate_held_bill_number(db: Session, user_id: int) -> str:
    today_str = datetime.utcnow().strftime("%Y%m%d")
    prefix = f"HB-{today_str}-"
    existing_bills = (
        db.query(models.HeldBill.held_bill_number)
        .filter(
            models.HeldBill.user_id == user_id,
            models.HeldBill.held_bill_number.like(f"{prefix}%"),
        )
        .all()
    )
    max_seq = 0
    for (b_num,) in existing_bills:
        if b_num:
            try:
                parts = b_num.split("-")
                seq_val = int(parts[-1])
                if seq_val > max_seq:
                    max_seq = seq_val
            except (ValueError, IndexError):
                continue

    next_seq = max_seq + 1
    candidate = f"{prefix}{next_seq:03d}"
    while db.query(models.HeldBill.id).filter(
        models.HeldBill.user_id == user_id,
        models.HeldBill.held_bill_number == candidate,
    ).first():
        next_seq += 1
        candidate = f"{prefix}{next_seq:03d}"
    return candidate


def create_held_bill(
    db: Session,
    bill_data: schemas.HeldBillCreate,
    user_id: int,
) -> models.HeldBill:
    """
    Parks a customer's cart as a Held Bill.
    CRITICAL: Does NOT deduct stock, does NOT create a Sale, does NOT touch Khata.
    """
    try:
        product_ids = list({item.product_id for item in bill_data.items})
        products = (
            db.query(models.Product)
            .filter(
                models.Product.id.in_(product_ids),
                models.Product.user_id == user_id,
                models.Product.is_deleted == False,
            )
            .all()
        )
        prod_map = {p.id: p for p in products}

        for item in bill_data.items:
            if item.product_id not in prod_map:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Product ID {item.product_id} not found.",
                )

        prepared_items = []
        subtotal = 0.0
        total_line_discounts = 0.0
        total_tax = 0.0

        for item in bill_data.items:
            prod = prod_map[item.product_id]
            is_strip = str(item.unit_type or "strip").lower() in ["strip", "pack"]
            tablets_per_pack = (
                item.tablets_per_strip
                or getattr(prod, "tablets_per_strip", None)
                or getattr(prod, "units_per_pack", None)
                or 10
            )

            if item.unit_price is not None and item.unit_price > 0:
                unit_price = item.unit_price
            elif is_strip:
                unit_price = prod.unit_price or 0.0
            else:
                if prod.price_per_unit is not None and prod.price_per_unit > 0:
                    unit_price = prod.price_per_unit
                elif prod.loose_tablet_price is not None and prod.loose_tablet_price > 0:
                    unit_price = prod.loose_tablet_price
                elif prod.unit_price and prod.unit_price > 0:
                    unit_price = round(prod.unit_price / tablets_per_pack, 2)
                else:
                    unit_price = 0.0

            line_gross = round(unit_price * item.quantity, 2)
            line_discount = round(float(item.discount or 0.0), 2)
            taxable_line = max(0.0, round(line_gross - line_discount, 2))
            gst_pct = float(item.gst_percentage if item.gst_percentage is not None else (prod.gst_percentage or 12.0))
            line_tax = round(taxable_line * (gst_pct / 100.0), 2)
            line_total = round(taxable_line + line_tax, 2)

            subtotal += line_gross
            total_line_discounts += line_discount
            total_tax += line_tax

            prepared_items.append({
                "product_id": prod.id,
                "product_name": prod.product_name,
                "quantity": item.quantity,
                "unit_type": item.unit_type,
                "unit_price": unit_price,
                "discount": line_discount,
                "tablets_per_strip": tablets_per_pack,
                "batch_number": item.batch_number or prod.batch_number,
                "expiry_date": item.expiry_date or (prod.expiry_date.strftime("%Y-%m-%d") if prod.expiry_date else None),
                "hsn_code": item.hsn_code or prod.hsn_code or "3004",
                "gst_percentage": gst_pct,
                "estimated_line_total": line_total,
            })

        taxable_subtotal = max(0.0, subtotal - total_line_discounts)
        bill_discount = 0.0
        if bill_data.discount_type == "percent":
            bill_discount = round(taxable_subtotal * (bill_data.discount_value / 100.0), 2)
        elif bill_data.discount_type == "flat":
            bill_discount = round(min(bill_data.discount_value, taxable_subtotal), 2)

        total_discount = round(total_line_discounts + bill_discount, 2)
        estimated_total = round(max(0.0, subtotal - total_discount + total_tax), 2)

        split_payments_data = None
        if bill_data.split_payments:
            split_payments_data = [p.dict() if hasattr(p, "dict") else p for p in bill_data.split_payments]

        snapshot = {
            "held_bill_number": "",
            "customer_id": bill_data.customer_id,
            "customer_name": bill_data.customer_name,
            "customer_phone": bill_data.customer_phone,
            "doctor_name": bill_data.doctor_name,
            "doctor_reg_no": bill_data.doctor_reg_no,
            "payment_method": bill_data.payment_method,
            "is_interstate": bill_data.is_interstate,
            "discount_type": bill_data.discount_type,
            "discount_value": bill_data.discount_value,
            "notes": bill_data.notes,
            "items": prepared_items,
            "split_payments": split_payments_data,
        }

        max_retries = 3
        for attempt in range(max_retries):
            held_bill_number = generate_held_bill_number(db, user_id)
            snapshot["held_bill_number"] = held_bill_number

            db_held = models.HeldBill(
                user_id=user_id,
                held_bill_number=held_bill_number,
                status="HELD",
                customer_id=bill_data.customer_id,
                customer_name=bill_data.customer_name,
                customer_phone=bill_data.customer_phone,
                doctor_name=bill_data.doctor_name,
                doctor_reg_no=bill_data.doctor_reg_no,
                payment_method=bill_data.payment_method,
                split_payments_json=json.dumps(split_payments_data) if split_payments_data else None,
                is_interstate=bill_data.is_interstate,
                discount_type=bill_data.discount_type,
                discount_value=bill_data.discount_value,
                estimated_subtotal=round(subtotal, 2),
                estimated_discount=total_discount,
                estimated_tax=round(total_tax, 2),
                estimated_total=estimated_total,
                notes=bill_data.notes,
                snapshot_json=json.dumps(snapshot),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(db_held)
            try:
                db.flush()
                for p_item in prepared_items:
                    db_item = models.HeldBillItem(
                        held_bill_id=db_held.id,
                        product_id=p_item["product_id"],
                        product_name=p_item["product_name"],
                        quantity=p_item["quantity"],
                        unit_type=p_item["unit_type"],
                        unit_price=p_item["unit_price"],
                        discount=p_item["discount"],
                        tablets_per_strip=p_item["tablets_per_strip"],
                        batch_number=p_item["batch_number"],
                        expiry_date=p_item["expiry_date"],
                        hsn_code=p_item["hsn_code"],
                        gst_percentage=p_item["gst_percentage"],
                        estimated_line_total=p_item["estimated_line_total"],
                    )
                    db.add(db_item)

                db.commit()
                db.refresh(db_held)
                return db_held
            except IntegrityError as ie:
                db.rollback()
                logger.warning(f"IntegrityError on held bill attempt {attempt + 1}: {ie}")
                if attempt == max_retries - 1:
                    logger.error(f"Held bill creation failed after {max_retries} attempts: {ie}")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Could not generate unique held bill number. Please try again.",
                    )
                continue
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Unexpected error in create_held_bill: {e}")
        raise


def get_held_bills(
    db: Session,
    user_id: int,
    status: str = "HELD",
    search_query: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
) -> List[models.HeldBill]:
    query = (
        db.query(models.HeldBill)
        .options(joinedload(models.HeldBill.items))
        .filter(models.HeldBill.user_id == user_id)
    )
    if status and status.upper() != "ALL":
        query = query.filter(models.HeldBill.status == status.upper())

    if search_query and search_query.strip():
        term = f"%{search_query.strip()}%"
        query = query.filter(
            or_(
                models.HeldBill.customer_name.ilike(term),
                models.HeldBill.customer_phone.ilike(term),
                models.HeldBill.held_bill_number.ilike(term),
                models.HeldBill.notes.ilike(term),
            )
        )

    return query.order_by(models.HeldBill.created_at.desc()).offset(skip).limit(limit).all()


def get_held_bill_count(db: Session, user_id: int) -> int:
    return (
        db.query(models.HeldBill)
        .filter(
            models.HeldBill.user_id == user_id,
            models.HeldBill.status == "HELD",
        )
        .count()
    )


def get_held_bill_by_id(
    db: Session,
    held_bill_id: int,
    user_id: int,
) -> Optional[models.HeldBill]:
    return (
        db.query(models.HeldBill)
        .options(joinedload(models.HeldBill.items))
        .filter(
            models.HeldBill.id == held_bill_id,
            models.HeldBill.user_id == user_id,
        )
        .first()
    )


def resume_held_bill(
    db: Session,
    held_bill_id: int,
    user_id: int,
) -> dict:
    held_bill = get_held_bill_by_id(db, held_bill_id, user_id)
    if not held_bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Held bill #{held_bill_id} not found.",
        )
    if held_bill.status != "HELD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Held bill {held_bill.held_bill_number} is {held_bill.status.lower()} and cannot be resumed.",
        )

    product_ids = [item.product_id for item in held_bill.items]
    products = (
        db.query(models.Product)
        .filter(
            models.Product.id.in_(product_ids),
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
        )
        .all()
    )
    prod_map = {p.id: p for p in products}

    resume_items = []
    has_stock_shortage = False

    for item in held_bill.items:
        prod = prod_map.get(item.product_id)
        if not prod:
            available_stock = 0
            is_sufficient = False
        else:
            is_strip = str(item.unit_type or "strip").lower() in ["strip", "pack"]
            tabs_per_pack = (
                item.tablets_per_strip
                or getattr(prod, "tablets_per_strip", None)
                or getattr(prod, "units_per_pack", None)
                or 10
            )
            if is_strip:
                available_stock = max(0, int(prod.quantity or 0))
            else:
                total_tablets = (int(prod.quantity or 0) * tabs_per_pack) + int(prod.loose_tablet_stock or 0)
                available_stock = max(0, total_tablets)

            is_sufficient = available_stock >= item.quantity

        if not is_sufficient:
            has_stock_shortage = True

        resume_items.append({
            "product_id": item.product_id,
            "product_name": item.product_name,
            "requested_quantity": item.quantity,
            "available_stock": available_stock,
            "is_sufficient": is_sufficient,
            "unit_type": item.unit_type,
            "unit_price": item.unit_price,
            "discount": item.discount,
            "tablets_per_strip": item.tablets_per_strip,
            "batch_number": item.batch_number,
            "expiry_date": item.expiry_date,
            "hsn_code": item.hsn_code,
            "gst_percentage": item.gst_percentage,
            "estimated_line_total": item.estimated_line_total,
        })

    return {
        "held_bill": held_bill,
        "items": resume_items,
        "has_stock_shortage": has_stock_shortage,
    }


def cancel_held_bill(
    db: Session,
    held_bill_id: int,
    user_id: int,
) -> models.HeldBill:
    held_bill = get_held_bill_by_id(db, held_bill_id, user_id)
    if not held_bill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Held bill #{held_bill_id} not found.",
        )
    if held_bill.status != "HELD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Held bill {held_bill.held_bill_number} is already {held_bill.status.lower()}.",
        )

    held_bill.status = "CANCELLED"
    held_bill.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(held_bill)
    return held_bill


# ===========================
# NOTIFICATION SETTINGS
# ===========================

def get_notification_settings(
    db: Session,
    user_id: int,
):
    settings = (
        db.query(models.NotificationSettings)
        .filter(models.NotificationSettings.user_id == user_id)
        .first()
    )

    if settings is None:
        settings = models.NotificationSettings(user_id=user_id)
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return settings


def update_notification_settings(
    db: Session,
    user_id: int,
    data: schemas.NotificationSettingsCreate,
):
    settings = (
        db.query(models.NotificationSettings)
        .filter(models.NotificationSettings.user_id == user_id)
        .first()
    )

    if settings is None:
        settings = models.NotificationSettings(user_id=user_id)
        db.add(settings)

    settings.enabled = data.enabled
    settings.notify_before_days = data.notify_before_days
    settings.reminder_frequency = data.reminder_frequency
    settings.notification_time = data.notification_time
    settings.sound = data.sound
    settings.vibration = data.vibration

    db.commit()
    db.refresh(settings)

    return settings


# ===========================
# BULK IMPORT PRODUCTS
# ===========================

def import_products(
    db: Session,
    products: list,
    user_id: int,
):
    imported_products = []

    try:
        for product in products:
            expiry = parse_date(product.expiry_date)
            manufacturing = (
                parse_date(product.manufacturing_date)
                if product.manufacturing_date
                else None
            )

            days_remaining, product_status = calculate_product_status(expiry)

            db_product = models.Product(
                user_id=user_id,
                product_name=product.product_name,
                brand=getattr(product, "brand", ""),
                category=product.category,
                batch_number=product.batch_number,
                quantity=product.quantity,
                unit_price=getattr(product, "unit_price", 0),
                total_price=getattr(product, "total_price", 0),
                manufacturing_date=manufacturing,
                expiry_date=expiry,
                days_remaining=days_remaining,
                status=product_status,
                image_path="",
                ocr_text="Invoice Import",
                notified_expiring=False,
                notified_expired=False,
                last_notification_date=None,
            )

            db.add(db_product)
            imported_products.append(db_product)

        db.commit()
        invalidate_products_cache(user_id)

        for product in imported_products:
            db.refresh(product)

        return imported_products

    except Exception:
        db.rollback()
        raise


def bulk_update_gst(
    db: Session,
    user_id: int,
    hsn_code: str,
    gst_rate: float,
):
    products = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.hsn_code == hsn_code,
        )
        .all()
    )
    for p in products:
        p.gst_rate = gst_rate
        p.gst_percentage = gst_rate
    db.commit()
    invalidate_products_cache(user_id)


def bulk_import_inventory(
    db: Session,
    user_id: int,
    cleaned_rows: List[Tuple[int, Dict[str, Any], List[str]]],
    on_duplicate: str = "skip",
) -> Dict[str, Any]:
    """
    High-performance bulk inventory import engine optimized for 10,000+ rows.
    Uses tuple projection (50x faster than ORM initialization) to prefetch product maps.
    Uses bulk_insert_mappings & bulk_update_mappings for sub-second database execution.
    """
    t_start = time.time()
    imported_names_set = set()
    for _, data, _ in cleaned_rows:
        pname = data.get("product_name")
        if pname:
            imported_names_set.add(pname.strip())

    imported_names = list(imported_names_set)

    existing_tuples = []
    chunk_size_prefetch = 5000
    for i in range(0, len(imported_names), chunk_size_prefetch):
        name_chunk = imported_names[i:i + chunk_size_prefetch]
        chunk_tuples = (
            db.query(
                models.Product.id,
                models.Product.product_name,
                models.Product.batch_number,
                models.Product.quantity
            )
            .filter(
                models.Product.user_id == user_id,
                models.Product.is_deleted == False,
                models.Product.product_name.in_(name_chunk)
            )
            .all()
        )
        existing_tuples.extend(chunk_tuples)

    existing_map_by_batch = {}
    existing_map_by_name = {}
    for pid, pname, pbatch, pqty in existing_tuples:
        norm_name = (pname or "").strip().lower()
        norm_batch = (pbatch or "").strip().lower()
        if norm_name:
            existing_map_by_batch[(norm_name, norm_batch)] = (pid, pqty or 0)
            if norm_name not in existing_map_by_name:
                existing_map_by_name[norm_name] = (pid, pqty or 0)

    rows_imported = 0
    rows_updated = 0
    rows_skipped = 0
    summary_warnings = []
    to_add_dicts = []
    to_update_dicts = []
    session_new_items = {}

    for row_idx, data, warnings in cleaned_rows:
        if len(summary_warnings) < 100:
            for w in warnings:
                if len(summary_warnings) < 100:
                    summary_warnings.append({
                        "row": row_idx,
                        "product_name": data["product_name"],
                        "message": w,
                    })

        norm_name = data["product_name"].strip().lower()
        norm_batch = (data.get("batch_number") or "").strip().lower()

        existing_info = existing_map_by_batch.get((norm_name, norm_batch)) or existing_map_by_name.get(norm_name)

        if existing_info:
            pid, curr_qty = existing_info
            if on_duplicate == "skip":
                rows_skipped += 1
                if len(summary_warnings) < 100:
                    summary_warnings.append({
                        "row": row_idx,
                        "product_name": data["product_name"],
                        "message": f"Product '{data['product_name']}' already exists; skipped.",
                    })
                continue
            elif on_duplicate in ["update", "overwrite"]:
                new_qty = (curr_qty + data["quantity"]) if on_duplicate == "update" else data["quantity"]
                upd_dict = {
                    "id": pid,
                    "quantity": new_qty,
                    "unit_price": data["unit_price"],
                    "purchase_price": data["purchase_price"],
                    "hsn_code": data["hsn_code"],
                    "gst_rate": data["gst_rate"],
                    "gst_percentage": data["gst_rate"],
                }
                if data.get("batch_number"):
                    upd_dict["batch_number"] = data["batch_number"]
                if data.get("expiry_date"):
                    upd_dict["expiry_date"] = data["expiry_date"]
                    upd_dict["days_remaining"] = data["days_remaining"]
                    upd_dict["status"] = data["status"]
                if data.get("brand"):
                    upd_dict["brand"] = data["brand"]
                if data.get("barcode"):
                    upd_dict["barcode"] = data["barcode"]
                
                to_update_dicts.append(upd_dict)
                existing_map_by_batch[(norm_name, norm_batch)] = (pid, new_qty)
                existing_map_by_name[norm_name] = (pid, new_qty)
                rows_updated += 1
        elif (norm_name, norm_batch) in session_new_items:
            prev_item = session_new_items[(norm_name, norm_batch)]
            if on_duplicate == "skip":
                rows_skipped += 1
            else:
                prev_item["quantity"] += data["quantity"]
                rows_updated += 1
        else:
            new_dict = {
                "user_id": user_id,
                "product_name": data["product_name"],
                "brand": data.get("brand"),
                "barcode": data.get("barcode"),
                "unit_price": data["unit_price"],
                "purchase_price": data["purchase_price"],
                "hsn_code": data["hsn_code"],
                "gst_rate": data["gst_rate"],
                "gst_percentage": data["gst_rate"],
                "quantity": data["quantity"],
                "expiry_date": data["expiry_date"],
                "batch_number": data["batch_number"],
                "tablets_per_strip": data["tablets_per_strip"],
                "category": data["category"],
                "days_remaining": data["days_remaining"],
                "status": data["status"],
                "is_deleted": False,
            }
            to_add_dicts.append(new_dict)
            session_new_items[(norm_name, norm_batch)] = new_dict
            rows_imported += 1

    chunk_size = 2000
    if to_add_dicts:
        for i in range(0, len(to_add_dicts), chunk_size):
            chunk = to_add_dicts[i:i + chunk_size]
            db.bulk_insert_mappings(models.Product, chunk)
            db.flush()

    if to_update_dicts:
        for i in range(0, len(to_update_dicts), chunk_size):
            chunk = to_update_dicts[i:i + chunk_size]
            db.bulk_update_mappings(models.Product, chunk)
            db.flush()

    db.commit()
    invalidate_products_cache(user_id)

    return {
        "rows_imported": rows_imported,
        "rows_updated": rows_updated,
        "rows_skipped": rows_skipped,
        "warnings": summary_warnings,
    }


# ===========================
# CUSTOMER CRUD & AUTO-DISCOUNT
# ===========================

def get_customer_by_phone(db: Session, phone: str, user_id: int):
    return (
        db.query(models.Customer)
        .filter(
            models.Customer.user_id == user_id,
            models.Customer.phone == phone,
        )
        .first()
    )


def create_or_update_customer(db: Session, customer_data: schemas.CustomerCreate, user_id: int):
    existing = get_customer_by_phone(db, customer_data.phone, user_id)
    if existing:
        existing.name = customer_data.name
        if customer_data.email:
            existing.email = customer_data.email
        if customer_data.address:
            existing.address = customer_data.address
        existing.fixed_discount_percent = customer_data.fixed_discount_percent
        db.commit()
        db.refresh(existing)
        invalidate_customers_cache(user_id)
        return existing

    new_cust = models.Customer(
        user_id=user_id,
        name=customer_data.name,
        phone=customer_data.phone,
        email=customer_data.email,
        address=customer_data.address,
        fixed_discount_percent=customer_data.fixed_discount_percent,
    )
    db.add(new_cust)
    db.commit()
    db.refresh(new_cust)
    invalidate_customers_cache(user_id)
    return new_cust


def get_customers(db: Session, user_id: int):
    global _CUSTOMERS_CACHE
    if user_id in _CUSTOMERS_CACHE:
        return _CUSTOMERS_CACHE[user_id]
    res = db.query(models.Customer).filter(models.Customer.user_id == user_id).all()
    serialized = [
        {
            "id": c.id,
            "user_id": c.user_id,
            "name": c.name,
            "phone": c.phone,
            "email": c.email,
            "address": c.address,
            "fixed_discount_percent": c.fixed_discount_percent,
            "pending_amount": c.pending_amount,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in res
    ]
    _CUSTOMERS_CACHE[user_id] = serialized
    return serialized


# ===========================
# SALE RETURNS CRUD
# ===========================

def process_sale_return(db: Session, return_data: schemas.SaleReturnCreate, user_id: int):
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == return_data.sale_id, models.Sale.user_id == user_id)
        .first()
    )
    if not sale:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sale bill not found.",
        )

    if getattr(sale, "return_status", None) == "returned":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This bill is already fully returned.",
        )

    total_return_amount = 0.0
    return_items = []

    for item_req in return_data.items:
        sale_item = (
            db.query(models.SaleItem)
            .filter(
                models.SaleItem.id == item_req.sale_item_id,
                models.SaleItem.sale_id == sale.id,
            )
            .first()
        )
        if not sale_item:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sale item ID {item_req.sale_item_id} not found in bill.",
            )

        if item_req.quantity > sale_item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot return {item_req.quantity} of '{sale_item.product_name}'. Maximum sold: {sale_item.quantity}.",
            )

        # Calculate prorated refund amount per unit using total_price safely
        item_total = getattr(sale_item, "total_price", None)
        if item_total is None:
            item_total = getattr(sale_item, "total_amount", None) or (sale_item.unit_price * sale_item.quantity)
        
        unit_refund = (item_total / sale_item.quantity) if sale_item.quantity > 0 else sale_item.unit_price
        item_return_total = round(unit_refund * item_req.quantity, 2)
        total_return_amount += item_return_total

        # Restore inventory stock
        product = db.query(models.Product).filter(
            models.Product.id == sale_item.product_id,
            models.Product.user_id == user_id
        ).first()
        if product:
            if getattr(sale_item, "unit_type", "strip") == "strip":
                product.quantity = (product.quantity or 0) + item_req.quantity
            else:
                product.loose_tablet_stock = (product.loose_tablet_stock or 0) + item_req.quantity

        return_item = models.SaleReturnItem(
            sale_item_id=sale_item.id,
            product_id=sale_item.product_id,
            quantity=item_req.quantity,
            unit_price=round(unit_refund, 2),
            return_total=item_return_total,
        )
        return_items.append(return_item)

    sale_return = models.SaleReturn(
        sale_id=sale.id,
        user_id=user_id,
        reason=return_data.reason or "Patient Return",
        return_amount=round(total_return_amount, 2),
        items=return_items,
    )
    db.add(sale_return)

    sale.return_status = "partially_returned"

    # Adjust customer outstanding credit if applicable
    if sale.customer_id and sale.payment_method in ["CREDIT", "PENDING"]:
        customer = db.query(models.Customer).filter(
            models.Customer.id == sale.customer_id,
            models.Customer.user_id == user_id
        ).first()
        if customer:
            customer.pending_amount = max(0.0, customer.pending_amount - total_return_amount)

    db.commit()
    db.refresh(sale_return)
    invalidate_products_cache(user_id)
    invalidate_customers_cache(user_id)
    return sale_return


def get_todays_returns(db: Session, user_id: int):
    from sqlalchemy.orm import joinedload
    today_start = datetime.combine(date.today(), datetime.min.time())
    returns = (
        db.query(models.SaleReturn)
        .options(joinedload(models.SaleReturn.sale))
        .filter(
            models.SaleReturn.user_id == user_id,
            models.SaleReturn.created_at >= today_start,
        )
        .order_by(models.SaleReturn.created_at.desc())
        .all()
    )
    return returns


# ===========================
# RANKED SEARCH & AUTOCOMPLETE
# ===========================

def search_products_ranked(db: Session, query: str, user_id: int, limit: int = 10):
    clean_q = query.strip().lower()
    if not clean_q:
        return []

    prefix_pattern = f"{clean_q}%"
    contains_pattern = f"%{clean_q}%"

    rank_case = case(
        (func.lower(models.Product.product_name).like(prefix_pattern), 1),
        else_=2
    )

    results = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.product_name.ilike(contains_pattern)
        )
        .order_by(
            rank_case.asc(),
            models.Product.verified.desc(),
            models.Product.product_name.asc()
        )
        .limit(limit)
        .all()
    )
    return results


# ===========================
# GLOBAL MEDICINE CATALOG & STOCK PURCHASE
# ===========================

_CATALOG_CACHE = {}
_CATALOG_CACHE_MAX_SIZE = 500

def search_medicine_catalog(db: Session, query: str, limit: int = 20):
    clean_q = (query or "").strip()
    if not clean_q or len(clean_q) < 2:
        return []

    clamped_limit = max(1, min(limit, 100))
    cache_key = (clean_q.lower(), clamped_limit)
    now = time.time()

    if cache_key in _CATALOG_CACHE:
        cached_res, ts = _CATALOG_CACHE[cache_key]
        if now - ts < 600:
            return cached_res

    prefix = f"{clean_q.lower()}%"
    contains = f"%{clean_q}%"
    results = []
    found_ids = set()

    # Step 1: Ultra-fast index prefix scan using idx_catalog_name_lower (<1ms on DB)
    sql_prefix = text("""
        SELECT id, product_name, brand, category, hsn_code, gst_rate, 
               default_price, tablets_per_strip, units_per_pack, price_per_unit, 
               verified, is_countable, needs_review, pack_size_label, composition
        FROM medicine_catalog
        WHERE lower(product_name) LIKE :prefix
        LIMIT :limit;
    """)
    rows1 = db.execute(sql_prefix, {"prefix": prefix, "limit": clamped_limit}).fetchall()

    for r in rows1:
        found_ids.add(r[0])
        results.append({
            "id": r[0],
            "product_name": r[1],
            "brand": r[2],
            "category": r[3] or "allopathy",
            "hsn_code": r[4] or "3004",
            "gst_rate": float(r[5] if r[5] is not None else 12.0),
            "default_price": float(r[6] if r[6] is not None else 0.0),
            "tablets_per_strip": int(r[7]) if r[7] is not None else 10,
            "units_per_pack": int(r[8]) if r[8] is not None else None,
            "price_per_unit": float(r[9]) if r[9] is not None else None,
            "verified": bool(r[10]) if r[10] is not None else False,
            "is_countable": bool(r[11]) if r[11] is not None else True,
            "needs_review": bool(r[12]) if r[12] is not None else False,
            "pack_size_label": r[13],
            "composition": r[14],
        })

    # Step 2: Fallback if prefix search alone returned fewer than requested limit
    if len(results) < clamped_limit:
        rem = clamped_limit - len(results)
        if found_ids:
            sql_fallback = text("""
                SELECT id, product_name, brand, category, hsn_code, gst_rate, 
                       default_price, tablets_per_strip, units_per_pack, price_per_unit, 
                       verified, is_countable, needs_review, pack_size_label, composition
                FROM medicine_catalog
                WHERE NOT (id = ANY(:found_ids))
                  AND (product_name ILIKE :contains OR brand ILIKE :contains OR composition ILIKE :contains)
                LIMIT :rem;
            """)
            rows2 = db.execute(sql_fallback, {"contains": contains, "found_ids": list(found_ids), "rem": rem}).fetchall()
        else:
            sql_fallback = text("""
                SELECT id, product_name, brand, category, hsn_code, gst_rate, 
                       default_price, tablets_per_strip, units_per_pack, price_per_unit, 
                       verified, is_countable, needs_review, pack_size_label, composition
                FROM medicine_catalog
                WHERE product_name ILIKE :contains OR brand ILIKE :contains OR composition ILIKE :contains
                LIMIT :rem;
            """)
            rows2 = db.execute(sql_fallback, {"contains": contains, "rem": rem}).fetchall()

        for r in rows2:
            results.append({
                "id": r[0],
                "product_name": r[1],
                "brand": r[2],
                "category": r[3] or "allopathy",
                "hsn_code": r[4] or "3004",
                "gst_rate": float(r[5] if r[5] is not None else 12.0),
                "default_price": float(r[6] if r[6] is not None else 0.0),
                "tablets_per_strip": int(r[7]) if r[7] is not None else 10,
                "units_per_pack": int(r[8]) if r[8] is not None else None,
                "price_per_unit": float(r[9]) if r[9] is not None else None,
                "verified": bool(r[10]) if r[10] is not None else False,
                "is_countable": bool(r[11]) if r[11] is not None else True,
                "needs_review": bool(r[12]) if r[12] is not None else False,
                "pack_size_label": r[13],
                "composition": r[14],
            })

    # Sort: verified first, then alphabetically by product_name
    results.sort(key=lambda x: (0 if x["verified"] else 1, x["product_name"] or ""))

    # Validate against Pydantic schema model
    validated = [schemas.MedicineCatalogResponse.model_validate(item) for item in results]

    # Bounded cache storage
    if len(_CATALOG_CACHE) >= _CATALOG_CACHE_MAX_SIZE:
        # Evict oldest 20% entries
        to_remove = list(_CATALOG_CACHE.keys())[:int(_CATALOG_CACHE_MAX_SIZE * 0.2)]
        for k in to_remove:
            _CATALOG_CACHE.pop(k, None)
    _CATALOG_CACHE[cache_key] = (validated, now)

    return validated



def check_duplicate_batch(db: Session, user_id: int, product_name: str, batch_number: str):
    clean_name = product_name.strip().lower()
    clean_batch = batch_number.strip()
    
    existing = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
            func.lower(models.Product.product_name) == clean_name,
            models.Product.batch_number == clean_batch
        )
        .first()
    )
    if existing:
        return {
            "is_duplicate": True,
            "product_id": existing.id,
            "product_name": existing.product_name,
            "batch_number": existing.batch_number,
            "existing_quantity": existing.quantity,
            "expiry_date": existing.expiry_date.strftime("%Y-%m-%d") if existing.expiry_date else None,
            "message": f"This batch '{clean_batch}' already exists in your inventory with {existing.quantity} units."
        }
    return {"is_duplicate": False, "message": "No duplicate batch found."}


def create_custom_medicine(db: Session, data: schemas.CustomMedicineCreate):
    clean_name = data.product_name.strip()
    
    # Check if catalog entry already exists
    existing = db.query(models.MedicineCatalog).filter(func.lower(models.MedicineCatalog.product_name) == clean_name.lower()).first()
    if existing:
        return existing

    catalog_entry = models.MedicineCatalog(
        product_name=clean_name,
        brand=data.brand,
        category=data.category or "allopathy",
        composition=data.composition,
        hsn_code=data.hsn_code or "3004",
        gst_rate=data.gst_rate or 12.0,
        default_price=data.default_price or 0.0,
        tablets_per_strip=data.tablets_per_strip or 10,
        units_per_pack=data.tablets_per_strip or 10,
        pack_size_label=data.pack_size_label or f"strip of {data.tablets_per_strip or 10} tablets",
        verified=True
    )
    db.add(catalog_entry)
    db.commit()
    db.refresh(catalog_entry)
    return catalog_entry


def add_real_inventory_item(db: Session, data: schemas.InventoryAddRequest, user_id: int, do_commit: bool = True):
    exp_date = parse_date(data.expiry_date)
    mfg_date = parse_date(data.manufacturing_date) if data.manufacturing_date else None

    if not exp_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid expiry date format. Use YYYY-MM-DD.",
        )

    days_remaining = (exp_date - date.today()).days

    if days_remaining < 0:
        product_status = "Expired"
    elif days_remaining <= 30:
        product_status = "Expiring Soon"
    else:
        product_status = "Safe"

    existing = None
    if data.duplicate_mode != "separate":
        existing = (
            db.query(models.Product)
            .filter(
                models.Product.user_id == user_id,
                models.Product.is_deleted == False,
                func.lower(models.Product.product_name) == data.product_name.strip().lower(),
                models.Product.batch_number == data.batch_number.strip(),
                models.Product.expiry_date == exp_date
            )
            .first()
        )

    units = data.units_per_pack or 10
    calc_per_unit = round(data.unit_price / units, 2) if (units and units > 0 and data.unit_price > 0) else None

    if existing and data.duplicate_mode != "separate":
        existing.quantity += data.quantity
        existing.purchase_price = data.purchase_price
        existing.unit_price = data.unit_price
        existing.units_per_pack = units
        existing.price_per_unit = calc_per_unit
        existing.loose_tablet_price = calc_per_unit
        existing.tablets_per_strip = units
        existing.total_price = existing.unit_price * existing.quantity
        existing.days_remaining = days_remaining
        existing.status = product_status
        if data.supplier_id:
            existing.supplier_id = data.supplier_id
        if data.document_id:
            existing.document_id = data.document_id
        if data.invoice_number:
            existing.invoice_number = data.invoice_number
        if do_commit:
            db.commit()
            invalidate_products_cache(user_id)
        return existing

    new_prod = models.Product(
        user_id=user_id,
        product_name=data.product_name.strip(),
        brand=data.brand,
        category=data.category or "allopathy",
        batch_number=data.batch_number.strip(),
        quantity=data.quantity,
        purchase_price=data.purchase_price,
        unit_price=data.unit_price,
        units_per_pack=units,
        price_per_unit=calc_per_unit,
        loose_tablet_price=calc_per_unit,
        tablets_per_strip=units,
        total_price=data.unit_price * data.quantity,
        hsn_code=data.hsn_code or "3004",
        gst_rate=data.gst_rate or 12.0,
        gst_percentage=data.gst_rate or 12.0,
        manufacturing_date=mfg_date,
        expiry_date=exp_date,
        days_remaining=days_remaining,
        status=product_status,
        supplier_id=data.supplier_id,
        document_id=data.document_id,
        invoice_number=data.invoice_number,
        verified=True,
        pack_size_verified=True,
        price_last_updated=datetime.utcnow()
    )

    db.add(new_prod)
    if do_commit:
        db.commit()
        invalidate_products_cache(user_id)
    return new_prod


# ===========================
# HSN TAX RATE CRUD & LOOKUP
# ===========================

DEFAULT_HSN_TAX_MAPPINGS = [
    {"hsn_code": "3004", "description": "Medicaments consisting of mixed or unmixed products for therapeutic/prophylactic uses", "gst_rate": 12.0, "category": "pharma", "is_life_saving": False},
    {"hsn_code": "3003", "description": "Medicaments (excluding goods of 3002, 3005 or 3006) for therapeutic/prophylactic uses", "gst_rate": 12.0, "category": "pharma", "is_life_saving": False},
    {"hsn_code": "3002", "description": "Vaccines, toxins, cultures of micro-organisms & specified life-saving drugs", "gst_rate": 5.0, "category": "pharma", "is_life_saving": True},
    {"hsn_code": "3001", "description": "Glands & organs for organo-therapeutic uses, heparin & extracts", "gst_rate": 5.0, "category": "pharma", "is_life_saving": False},
    {"hsn_code": "3005", "description": "Wadding, gauze, bandages, adhesive dressings & similar medical items", "gst_rate": 12.0, "category": "medical_devices", "is_life_saving": False},
    {"hsn_code": "3006", "description": "Pharmaceutical goods (sterile surgical catgut, blood-grouping reagents, ostomy appliances)", "gst_rate": 12.0, "category": "medical_devices", "is_life_saving": False},
    {"hsn_code": "3304", "description": "Beauty, skincare, medicated cosmetics or skin preparations", "gst_rate": 18.0, "category": "cosmetics", "is_life_saving": False},
    {"hsn_code": "2106", "description": "Food supplements, protein powders & dietary nutraceuticals", "gst_rate": 18.0, "category": "supplements", "is_life_saving": False},
    {"hsn_code": "9993", "description": "Healthcare services & medical equipment maintenance", "gst_rate": 18.0, "category": "services", "is_life_saving": False},
]

def seed_default_hsn_rates(db: Session):
    """Seed & update standard pharma HSN tax rates in reference table."""
    for item in DEFAULT_HSN_TAX_MAPPINGS:
        existing = db.query(models.HsnTaxRate).filter(models.HsnTaxRate.hsn_code == item["hsn_code"]).first()
        if not existing:
            db_item = models.HsnTaxRate(**item)
            db.add(db_item)
        else:
            existing.gst_rate = item["gst_rate"]
            existing.description = item["description"]
    db.commit()


def get_hsn_gst_rate(db: Session, hsn_code: Optional[str], product_name: Optional[str] = None, user_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Looks up official GST rate by 4-digit or 6-digit HSN code.
    If unmapped or missing, logs to unmapped_hsn_logs for admin review.
    """
    seed_default_hsn_rates(db)

    clean_hsn = str(hsn_code).strip().replace(".", "") if hsn_code else ""
    
    if clean_hsn:
        # 1. Exact match
        match = db.query(models.HsnTaxRate).filter(models.HsnTaxRate.hsn_code == clean_hsn).first()
        if match:
            return {
                "hsn_code": match.hsn_code,
                "gst_rate": match.gst_rate,
                "description": match.description,
                "is_mapped": True,
                "is_life_saving": match.is_life_saving,
                "needs_manual_review": False
            }

        # 2. 4-Digit Prefix Match (e.g. 300410 -> 3004)
        if len(clean_hsn) > 4:
            prefix = clean_hsn[:4]
            prefix_match = db.query(models.HsnTaxRate).filter(models.HsnTaxRate.hsn_code == prefix).first()
            if prefix_match:
                return {
                    "hsn_code": clean_hsn,
                    "gst_rate": prefix_match.gst_rate,
                    "description": f"{prefix_match.description} (Matched 4-digit HSN prefix {prefix})",
                    "is_mapped": True,
                    "is_life_saving": prefix_match.is_life_saving,
                    "needs_manual_review": False
                }

    # 3. Unmapped or missing HSN handling -> Log for review
    if clean_hsn:
        log_entry = models.UnmappedHsnLog(
            hsn_code=clean_hsn,
            product_name=product_name,
            user_id=user_id,
            entered_gst_rate=None
        )
        db.add(log_entry)
        db.commit()

    return {
        "hsn_code": clean_hsn or "3004",
        "gst_rate": 5.0,  # GST 2.0 pharma baseline rate
        "description": f"Unmapped/Missing HSN ('{clean_hsn}') — Flagged for Shopkeeper Confirmation",
        "is_mapped": False,
        "is_life_saving": False,
        "needs_manual_review": True
    }


def get_all_hsn_rates(db: Session):
    seed_default_hsn_rates(db)
    return db.query(models.HsnTaxRate).order_by(models.HsnTaxRate.hsn_code.asc()).all()


def create_hsn_rate(db: Session, hsn_data: schemas.HsnTaxRateCreate):
    clean_hsn = hsn_data.hsn_code.strip().replace(".", "")
    existing = db.query(models.HsnTaxRate).filter(models.HsnTaxRate.hsn_code == clean_hsn).first()
    if existing:
        existing.gst_rate = hsn_data.gst_rate
        existing.description = hsn_data.description
        existing.category = hsn_data.category
        existing.is_life_saving = hsn_data.is_life_saving
        db.commit()
        db.refresh(existing)
        return existing

    new_hsn = models.HsnTaxRate(
        hsn_code=clean_hsn,
        description=hsn_data.description,
        gst_rate=hsn_data.gst_rate,
        category=hsn_data.category,
        is_life_saving=hsn_data.is_life_saving
    )
    db.add(new_hsn)
    db.commit()
    db.refresh(new_hsn)
    return new_hsn


def get_unmapped_hsn_logs(db: Session, limit: int = 50):
    return db.query(models.UnmappedHsnLog).order_by(models.UnmappedHsnLog.created_at.desc()).limit(limit).all()


# ===========================
# USER PROFILE & SETTINGS CRUD
# ===========================

def update_user_profile(db: Session, user_id: int, data: schemas.UserProfileUpdate):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User profile not found.")

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        if hasattr(user, field) and value is not None:
            setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


def change_user_password(db: Session, user_id: int, req: schemas.PasswordChangeRequest):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not verify_password(req.current_password, user.password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    user.password = get_password_hash(req.new_password)
    db.commit()
    return {"message": "Password updated successfully."}


def update_sale_retrospective(
    db: Session,
    sale_id: int,
    update_data: schemas.SaleUpdateDesktop,
    user_id: int,
):
    """Update non-financial metadata on existing sale bill post-checkout."""
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == sale_id, models.Sale.user_id == user_id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale bill not found or access denied.")

    if update_data.customer_name is not None:
        sale.customer_name = update_data.customer_name
    if update_data.customer_phone is not None:
        sale.customer_phone = update_data.customer_phone
    if update_data.payment_method is not None:
        sale.payment_method = update_data.payment_method
    if update_data.notes is not None:
        sale.notes = update_data.notes
    if update_data.doctor_name is not None:
        sale.doctor_name = update_data.doctor_name
    if update_data.doctor_reg_no is not None:
        sale.doctor_reg_no = update_data.doctor_reg_no

    db.commit()
    db.refresh(sale)
    return sale


def delete_sale_bill(db: Session, sale_id: int, user_id: int):
    """
    Deletes sale bill and safely restores unrefunded inventory stock,
    preventing double-restoration of already refunded items.
    """
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == sale_id, models.Sale.user_id == user_id)
        .with_for_update()
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Bill not found or access denied.")

    # Check for recorded customer payments linked to this specific sale
    recorded_payment = (
        db.query(models.CustomerPayment)
        .filter(
            models.CustomerPayment.sale_id == sale.id,
            models.CustomerPayment.user_id == user_id,
        )
        .first()
    )
    if recorded_payment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete bill with recorded customer payments. Please delete or reallocate payment collections first.",
        )

    # Restores stock for unreturned items only
    for item in sale.items:
        already_returned_qty = (
            db.query(func.coalesce(func.sum(models.SaleReturnItem.quantity), 0))
            .filter(models.SaleReturnItem.sale_item_id == item.id)
            .scalar()
        )
        net_restore_qty = max(0, item.quantity - already_returned_qty)

        if net_restore_qty > 0:
            product = (
                db.query(models.Product)
                .filter(models.Product.id == item.product_id, models.Product.user_id == user_id)
                .with_for_update()
                .first()
            )
            if product:
                if item.unit_type == "loose_tablet":
                    product.loose_tablet_stock += net_restore_qty
                else:
                    product.quantity += net_restore_qty

    # Reconcile customer credit/khata if bill had credit component
    if sale.customer_id:
        customer = (
            db.query(models.Customer)
            .filter(models.Customer.id == sale.customer_id, models.Customer.user_id == user_id)
            .with_for_update()
            .first()
        )
        if customer:
            credit_allocated = 0.0
            if sale.payment_method in ["CREDIT", "PENDING"]:
                credit_allocated = float(sale.total_amount or 0.0)
            elif sale.is_split_payment:
                credit_sp = db.query(func.sum(models.SalePayment.amount)).filter(
                    models.SalePayment.sale_id == sale.id,
                    models.SalePayment.payment_method == "CREDIT"
                ).scalar()
                credit_allocated = float(credit_sp or 0.0)

            already_refunded = float(
                db.query(func.coalesce(func.sum(models.SaleReturn.return_amount), 0.0))
                .filter(models.SaleReturn.sale_id == sale.id, models.SaleReturn.user_id == user_id)
                .scalar() or 0.0
            )
            net_credit_to_remove = max(0.0, credit_allocated - already_refunded)
            if net_credit_to_remove > 0:
                customer.pending_amount = max(0.0, round(float(customer.pending_amount or 0.0) - net_credit_to_remove, 2))

    db.delete(sale)
    db.commit()
    invalidate_products_cache(user_id)
    invalidate_customers_cache(user_id)
    return {"message": f"Bill {sale.bill_number} deleted successfully and unrefunded inventory restored."}


# ==========================================
# SUPPLIER MANAGEMENT CRUD
# ==========================================

import re

def normalize_supplier_name(name: Optional[str]) -> str:
    """
    Normalizes supplier names for deterministic, case-insensitive comparison.
    - Strips leading/trailing whitespace
    - Lowercases all characters
    - Normalizes '&' and '+' to 'and'
    - Replaces harmless punctuation (. , - _ / \ ' " ; : ! ? @ # $ % * ( ) [ ] { }) with spaces
    - Collapses multiple whitespace characters into a single space
    """
    if not name:
        return ""
    s = str(name).strip().lower()
    s = re.sub(r"[&+]", " and ", s)
    s = re.sub(r"[\.,\-_\'\"/\\;:!\?@#\$%\*\(\)\[\]\{\}]", " ", s)
    tokens = s.split()
    return " ".join(tokens)


def create_supplier(db: Session, user_id: int, supplier_data: schemas.SupplierCreate):
    norm_name = normalize_supplier_name(supplier_data.name)
    existing_suppliers = db.query(models.Supplier).filter(
        models.Supplier.user_id == user_id
    ).all()

    for s in existing_suppliers:
        if normalize_supplier_name(s.name) == norm_name:
            # Duplicate prevention: Link to existing supplier and backfill missing contact info
            updated = False
            if not s.gstin and supplier_data.gstin:
                s.gstin = supplier_data.gstin.strip()
                updated = True
            if not s.phone and supplier_data.phone:
                s.phone = supplier_data.phone.strip()
                updated = True
            if not s.email and supplier_data.email:
                s.email = supplier_data.email.strip()
                updated = True
            if not s.address and supplier_data.address:
                s.address = supplier_data.address.strip()
                updated = True
            if updated:
                db.commit()
                db.refresh(s)
            return s

    supplier = models.Supplier(
        user_id=user_id,
        name=supplier_data.name.strip(),
        contact_person=supplier_data.contact_person,
        phone=supplier_data.phone,
        email=supplier_data.email,
        address=supplier_data.address,
        gstin=supplier_data.gstin.strip() if supplier_data.gstin else None,
        state=supplier_data.state or "Delhi",
        payment_terms=supplier_data.payment_terms or "Net 30",
        notes=supplier_data.notes,
        status=supplier_data.status or "Active"
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def find_matching_suppliers(
    db: Session,
    user_id: int,
    extracted_name: Optional[str],
    extracted_gstin: Optional[str] = None
) -> Dict[str, Any]:
    raw_name = (extracted_name or "").strip()
    raw_gstin = (extracted_gstin or "").strip().upper()

    s_clean = raw_name.lower()
    is_garbage = s_clean in ("", "null", "none", "unknown", "invoice", "cash", "walk-in", "walkin", "customer", "receipt") or len(s_clean) < 2

    if is_garbage and not raw_gstin:
        return {
            "status": "no_match",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": None,
            "matched_supplier": None,
            "candidate_matches": [],
            "message": "No valid supplier name found in document"
        }

    all_suppliers = db.query(models.Supplier).filter(
        models.Supplier.user_id == user_id
    ).all()

    if not all_suppliers:
        return {
            "status": "no_match",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": None,
            "matched_supplier": None,
            "candidate_matches": [],
            "message": "No existing suppliers found for pharmacy"
        }

    def _serialize(s):
        return {
            "id": s.id,
            "user_id": s.user_id,
            "name": s.name,
            "contact_person": s.contact_person,
            "phone": s.phone,
            "email": s.email,
            "address": s.address,
            "gstin": s.gstin,
            "state": s.state,
            "payment_terms": s.payment_terms,
            "status": s.status,
            "created_at": s.created_at.isoformat() if hasattr(s.created_at, "isoformat") else (str(s.created_at) if s.created_at else None),
            "updated_at": s.updated_at.isoformat() if hasattr(s.updated_at, "isoformat") else (str(s.updated_at) if s.updated_at else None),
        }

    # 1. GSTIN exact match (if valid GSTIN provided)
    if raw_gstin and len(raw_gstin) >= 8:
        gstin_matches = [s for s in all_suppliers if s.gstin and s.gstin.strip().upper() == raw_gstin]
        if len(gstin_matches) == 1:
            return {
                "status": "exact_match",
                "extracted_name": raw_name,
                "extracted_gstin": raw_gstin,
                "match_type": "exact_gstin",
                "matched_supplier": _serialize(gstin_matches[0]),
                "candidate_matches": [_serialize(gstin_matches[0])],
                "message": f"Exact match found via GSTIN: {gstin_matches[0].name}"
            }
        elif len(gstin_matches) > 1:
            return {
                "status": "multiple_matches",
                "extracted_name": raw_name,
                "extracted_gstin": raw_gstin,
                "match_type": "exact_gstin",
                "matched_supplier": None,
                "candidate_matches": [_serialize(s) for s in gstin_matches],
                "message": f"Multiple suppliers matched GSTIN '{raw_gstin}'"
            }

    if is_garbage:
        return {
            "status": "no_match",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": None,
            "matched_supplier": None,
            "candidate_matches": [],
            "message": "Extracted supplier name is non-specific"
        }

    norm_query = normalize_supplier_name(raw_name)

    # 2. Exact Normalized Name Match
    exact_matches = [s for s in all_suppliers if normalize_supplier_name(s.name) == norm_query]
    if len(exact_matches) == 1:
        return {
            "status": "exact_match",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": "exact_name",
            "matched_supplier": _serialize(exact_matches[0]),
            "candidate_matches": [_serialize(exact_matches[0])],
            "message": f"Exact match found: {exact_matches[0].name}"
        }
    elif len(exact_matches) > 1:
        return {
            "status": "multiple_matches",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": "duplicate_exact",
            "matched_supplier": None,
            "candidate_matches": [_serialize(s) for s in exact_matches],
            "message": f"Multiple existing suppliers ({len(exact_matches)}) match '{raw_name}'. Please choose one."
        }

    # 3. Candidate / Substring / Token Matches (when 0 exact matches)
    candidates = []
    query_tokens = set(norm_query.split())
    for s in all_suppliers:
        norm_s = normalize_supplier_name(s.name)
        s_tokens = set(norm_s.split())
        if norm_query in norm_s or norm_s in norm_query or (query_tokens and query_tokens.issubset(s_tokens)) or (s_tokens and s_tokens.issubset(query_tokens)):
            candidates.append(s)

    if candidates:
        return {
            "status": "multiple_matches",
            "extracted_name": raw_name,
            "extracted_gstin": raw_gstin or None,
            "match_type": "candidate",
            "matched_supplier": None,
            "candidate_matches": [_serialize(s) for s in candidates],
            "message": f"Potential matching suppliers found for '{raw_name}'. Please select."
        }

    return {
        "status": "no_match",
        "extracted_name": raw_name,
        "extracted_gstin": raw_gstin or None,
        "match_type": None,
        "matched_supplier": None,
        "candidate_matches": [],
        "message": f"No existing supplier matched '{raw_name}'."
    }


def get_suppliers(db: Session, user_id: int, query: Optional[str] = None, status: Optional[str] = None):
    q = db.query(models.Supplier).filter(models.Supplier.user_id == user_id)
    if status and status.upper() != "ALL":
        q = q.filter(models.Supplier.status == status)
    if query:
        clean_q = f"%{query.strip().lower()}%"
        q = q.filter(
            (func.lower(models.Supplier.name).like(clean_q)) |
            (func.lower(models.Supplier.gstin).like(clean_q)) |
            (func.lower(models.Supplier.phone).like(clean_q))
        )
    
    suppliers = q.order_by(models.Supplier.name.asc()).all()
    
    # Eager-load aggregate stats for all documents of this user grouped by supplier_id in a single database query to fix the N+1 loop query issue
    from sqlalchemy import func
    doc_stats = db.query(
        models.Document.supplier_id,
        func.sum(models.Document.total_amount).label("total_purchases"),
        func.count(models.Document.id).label("purchase_count"),
        func.max(models.Document.created_at).label("last_purchase_date")
    ).filter(
        models.Document.user_id == user_id,
        models.Document.supplier_id.isnot(None)
    ).group_by(models.Document.supplier_id).all()

    stats_map = {
        row.supplier_id: {
            "total_purchases": float(row.total_purchases or 0.0),
            "purchase_count": int(row.purchase_count or 0),
            "last_purchase_date": row.last_purchase_date.strftime("%Y-%m-%d") if row.last_purchase_date else None
        }
        for row in doc_stats
    }

    result = []
    for s in suppliers:
        stats = stats_map.get(s.id, {
            "total_purchases": 0.0,
            "purchase_count": 0,
            "last_purchase_date": None
        })

        res_dict = schemas.SupplierResponse.from_orm(s)
        res_dict.total_purchases = stats["total_purchases"]
        res_dict.purchase_count = stats["purchase_count"]
        res_dict.last_purchase_date = stats["last_purchase_date"]
        result.append(res_dict)
        
    return result


def get_supplier_detail(db: Session, supplier_id: int, user_id: int):
    supplier = db.query(models.Supplier).filter(models.Supplier.id == supplier_id, models.Supplier.user_id == user_id).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found.")
    return supplier


def update_supplier(db: Session, supplier_id: int, user_id: int, data: schemas.SupplierUpdate):
    supplier = get_supplier_detail(db, supplier_id, user_id)
    update_dict = data.model_dump(exclude_unset=True)
    for k, v in update_dict.items():
        if hasattr(supplier, k) and v is not None:
            setattr(supplier, k, v)
    db.commit()
    db.refresh(supplier)
    return supplier


def delete_supplier(db: Session, supplier_id: int, user_id: int):
    supplier = get_supplier_detail(db, supplier_id, user_id)
    supplier.status = "Inactive"
    db.commit()
    return {"message": f"Supplier '{supplier.name}' deactivated successfully."}


def get_supplier_purchases(db: Session, supplier_id: int, user_id: int):
    return db.query(models.Document).filter(models.Document.supplier_id == supplier_id, models.Document.user_id == user_id).order_by(models.Document.created_at.desc()).all()


def get_supplier_inventory(db: Session, supplier_id: int, user_id: int):
    return db.query(models.Product).filter(models.Product.supplier_id == supplier_id, models.Product.user_id == user_id).order_by(models.Product.product_name.asc()).all()


# ==========================================
# DOCUMENT MANAGEMENT CRUD
# ==========================================

def create_document(db: Session, user_id: int, title: str, doc_type: str, file_path: str, file_type: str, file_size: int, supplier_id: Optional[int] = None, invoice_number: Optional[str] = None, notes: Optional[str] = None):
    doc = models.Document(
        user_id=user_id,
        supplier_id=supplier_id,
        title=title,
        doc_type=doc_type,
        file_path=file_path,
        file_type=file_type,
        file_size=file_size,
        invoice_number=invoice_number,
        notes=notes,
        ocr_status="Processing"
    )
    db.add(doc)
    db.commit()
    return doc


def get_documents(db: Session, user_id: int, query: Optional[str] = None, doc_type: Optional[str] = None, status: Optional[str] = None, supplier_id: Optional[int] = None):
    q = db.query(models.Document).filter(models.Document.user_id == user_id)
    if doc_type and doc_type.lower() != "all":
        q = q.filter(models.Document.doc_type == doc_type)
    if status and status.lower() != "all":
        q = q.filter(models.Document.ocr_status == status)
    if supplier_id:
        q = q.filter(models.Document.supplier_id == supplier_id)
    if query:
        clean_q = f"%{query.strip().lower()}%"
        q = q.filter(
            (func.lower(models.Document.title).like(clean_q)) |
            (func.lower(models.Document.invoice_number).like(clean_q))
        )

    docs = q.order_by(models.Document.created_at.desc()).all()
    
    result = []
    for d in docs:
        supplier_name = d.supplier.name if d.supplier else None
        res_dict = schemas.DocumentResponse.from_orm(d)
        res_dict.supplier_name = supplier_name
        result.append(res_dict)
    return result


def get_document_detail(db: Session, document_id: int, user_id: int):
    doc = db.query(models.Document).filter(models.Document.id == document_id, models.Document.user_id == user_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    return doc


def confirm_document_and_update_stock(db: Session, document_id: int, user_id: int, confirm_req: schemas.DocumentConfirmRequest):
    doc = get_document_detail(db, document_id, user_id)
    
    if confirm_req.supplier_id:
        doc.supplier_id = confirm_req.supplier_id
    if confirm_req.invoice_number:
        doc.invoice_number = confirm_req.invoice_number
    if confirm_req.invoice_date:
        try:
            doc.invoice_date = datetime.strptime(confirm_req.invoice_date, "%Y-%m-%d").date()
        except Exception:
            pass
    if confirm_req.total_amount:
        doc.total_amount = confirm_req.total_amount

    doc.item_count = len(confirm_req.items)
    doc.ocr_status = "Verified"

    created_products = []
    for item in confirm_req.items:
        product_req = schemas.InventoryAddRequest(
            product_name=item.product_name,
            brand=item.brand,
            category=item.category or "allopathy",
            hsn_code=item.hsn_code or "3004",
            gst_rate=item.gst_rate or 12.0,
            batch_number=item.batch_number,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            unit_price=item.unit_price,
            expiry_date=item.expiry_date
        )
        prod = add_real_inventory_item(db, product_req, user_id, do_commit=False)
        
        # Link traceability
        prod.supplier_id = doc.supplier_id
        prod.document_id = doc.id
        prod.invoice_number = doc.invoice_number
        created_products.append(prod)

    db.commit()
    invalidate_products_cache(user_id)
    return {"message": f"Document verified successfully. {len(created_products)} item batches added to stock with full supplier traceability.", "document_id": doc.id}


def delete_document(db: Session, document_id: int, user_id: int):
    doc = get_document_detail(db, document_id, user_id)
    db.delete(doc)
    db.commit()
    return {"message": "Document deleted successfully."}


# ==========================================
# SOFT DELETE & 60-DAY RECOVERY CRUD
# ==========================================

def soft_delete_inventory_items(db: Session, stock_ids: List[int], user_id: int) -> Dict[str, Any]:
    """Soft-deletes specific inventory rows for the authenticated shop."""
    if not stock_ids:
        return {
            "success": True,
            "message": "0 items moved to Recently Deleted.",
            "deleted_count": 0,
            "stock_ids": []
        }

    now = datetime.utcnow()
    count = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.id.in_(stock_ids),
            models.Product.is_deleted == False,
        )
        .update(
            {
                models.Product.is_deleted: True,
                models.Product.deleted_at: now,
                models.Product.deleted_by: user_id,
            },
            synchronize_session=False
        )
    )

    db.commit()
    invalidate_products_cache(user_id)
    return {
        "success": True,
        "message": f"{count} items moved to Recently Deleted, recoverable for 60 days.",
        "deleted_count": count,
        "stock_ids": stock_ids
    }


def soft_delete_all_inventory_items(db: Session, user_id: int) -> Dict[str, Any]:
    """Soft-deletes all active (non-deleted) inventory rows for the authenticated shop in high-performance bulk."""
    now = datetime.utcnow()
    count = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
        )
        .update(
            {
                models.Product.is_deleted: True,
                models.Product.deleted_at: now,
                models.Product.deleted_by: user_id,
            },
            synchronize_session=False
        )
    )

    db.commit()
    invalidate_products_cache(user_id)
    return {
        "success": True,
        "message": f"All {count} items moved to Recently Deleted, recoverable for 60 days.",
        "deleted_count": count
    }


def get_recently_deleted_inventory(db: Session, user_id: int) -> List[Dict[str, Any]]:
    """Returns soft-deleted items within the 60-day recovery window, sorted newest first."""
    cutoff = datetime.utcnow() - timedelta(days=60)
    items = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == True,
            models.Product.deleted_at >= cutoff,
        )
        .order_by(models.Product.deleted_at.desc())
        .all()
    )

    result = []
    now = datetime.utcnow()
    for p in items:
        del_at = p.deleted_at or now
        days_passed = (now - del_at).days
        days_left = max(0, 60 - days_passed)
        result.append({
            "id": p.id,
            "user_id": p.user_id,
            "product_name": p.product_name,
            "brand": p.brand,
            "category": p.category,
            "batch_number": p.batch_number,
            "quantity": p.quantity,
            "unit_price": p.unit_price,
            "purchase_price": p.purchase_price,
            "expiry_date": p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else None,
            "days_remaining": p.days_remaining,
            "status": p.status,
            "is_deleted": p.is_deleted,
            "deleted_at": p.deleted_at,
            "deleted_by": p.deleted_by,
            "days_until_permanent_delete": days_left
        })

    return result


def restore_inventory_items(db: Session, stock_ids: List[int], user_id: int) -> Dict[str, Any]:
    """Restores soft-deleted items only if deleted within the 60-day recovery window."""
    cutoff = datetime.utcnow() - timedelta(days=60)
    items = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.id.in_(stock_ids),
            models.Product.is_deleted == True,
            models.Product.deleted_at >= cutoff,
        )
        .all()
    )

    if not items:
        return {
            "success": True,
            "message": "No recoverable items found for the provided IDs.",
            "restored_count": 0,
            "stock_ids": []
        }

    restored_ids = []
    for item in items:
        item.is_deleted = False
        item.deleted_at = None
        item.deleted_by = None
        restored_ids.append(item.id)

    db.commit()
    invalidate_products_cache(user_id)
    return {
        "success": True,
        "message": f"{len(restored_ids)} items restored to live inventory.",
        "restored_count": len(restored_ids),
        "stock_ids": restored_ids
    }


def purge_expired_soft_deleted_inventory(db: Session) -> int:
    """Permanently purges (hard-deletes) soft-deleted stock rows older than 60 days."""
    cutoff = datetime.utcnow() - timedelta(days=60)
    deleted_rows = (
        db.query(models.Product)
        .filter(
            models.Product.is_deleted == True,
            models.Product.deleted_at < cutoff,
        )
        .delete(synchronize_session=False)
    )
    db.commit()
    return deleted_rows


# ==========================================
# BULK EXCEL / CSV DIRECT INVENTORY IMPORT
# ==========================================

def parse_pack_units(pack_size_label: Optional[str]) -> int:
    if not pack_size_label:
        return 10
    import re
    s = str(pack_size_label).strip().lower()
    match_mult = re.search(r'(\d+)\s*[xX*]\s*(\d+)', s)
    if match_mult:
        return int(match_mult.group(1)) * int(match_mult.group(2))
    match_num = re.search(r'(\d+)', s)
    if match_num:
        val = int(match_num.group(1))
        if val > 0:
            return val
    return 10


def import_inventory_from_file(db: Session, user_id: int, file_bytes: bytes, filename: str, on_duplicate: str = "merge") -> dict:
    """
    Directly parses an uploaded .xlsx, .xls, or .csv file (no AI required)
    and onboards medicine stock batches into the shop's active live inventory.
    Supports row-level validation (missing fields, zero prices, invalid dates) and duplicate stock handling.
    """
    import io
    import csv
    import openpyxl

    rows_to_process = []
    fname_lower = filename.lower()

    if fname_lower.endswith((".xlsx", ".xls")):
        try:
            wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb["Data"] if "Data" in wb.sheetnames else wb.active
            all_rows = list(ws.iter_rows(values_only=True))

            if not all_rows:
                raise HTTPException(status_code=400, detail="Uploaded spreadsheet is empty.")

            header_idx = -1
            headers = []
            for r_idx, row in enumerate(all_rows):
                str_row = [str(c).strip().lower() for c in row if c is not None]
                if any("medicine" in c or "product" in c or "batch" in c for c in str_row):
                    header_idx = r_idx
                    headers = [str(c).strip().lower() if c is not None else "" for c in row]
                    break

            if header_idx == -1:
                raise HTTPException(
                    status_code=400,
                    detail="Could not find header row. Required columns: medicine_name, batch_no, expiry_date, quantity, mrp."
                )

            for row in all_rows[header_idx + 1:]:
                if not row or all(c is None or str(c).strip() == "" for c in row):
                    continue
                row_dict = {}
                for h, val in zip(headers, row):
                    if h:
                        row_dict[h] = val
                rows_to_process.append(row_dict)

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail="Failed to read Excel spreadsheet. Please ensure the file is valid and uncorrupted.")

    elif fname_lower.endswith(".csv"):
        try:
            text_content = ""
            for enc in ["utf-8-sig", "utf-8", "latin1", "cp1252"]:
                try:
                    text_content = file_bytes.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue

            if not text_content:
                text_content = file_bytes.decode("utf-8", errors="replace")

            reader = csv.DictReader(io.StringIO(text_content))
            for row in reader:
                if any(v is not None and str(v).strip() for v in row.values()):
                    clean_row = {k.strip().lower(): (v if v is not None else "") for k, v in row.items() if k}
                    rows_to_process.append(clean_row)
        except Exception as e:
            raise HTTPException(status_code=400, detail="Failed to parse CSV file. Please ensure the file encoding is valid.")
    else:
        raise HTTPException(status_code=400, detail="Unsupported format. Please upload an .xlsx, .xls, or .csv file.")

    if not rows_to_process:
        raise HTTPException(status_code=400, detail="No data rows found in the uploaded file.")

    # Pre-fetch existing active products for ultra-fast O(1) duplicate lookup (1 DB query for 1000+ rows)
    existing_prods = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False
        )
        .all()
    )
    existing_map = {
        (p.product_name.strip().lower(), (p.batch_number or "").strip(), p.expiry_date): p
        for p in existing_prods
    }

    imported_items = []
    errors = []
    items_to_add = []
    rows_imported = 0
    rows_updated = 0
    rows_skipped = 0
    mode_clean = (on_duplicate or "merge").lower()

    for line_num, raw_row in enumerate(rows_to_process, start=2):
        # Normalize keys once for ultra-fast alias matching
        row = {k.replace(" ", "_").replace("-", "_").lower(): v for k, v in raw_row.items() if k}

        def get_val(*aliases):
            for a in aliases:
                if a in row and row[a] is not None:
                    return row[a]
                for k in row:
                    if a in k and row[k] is not None:
                        return row[k]
            return None

        med_name = get_val("medicine_name", "product_name", "medicine", "name", "item_name")
        if not med_name or str(med_name).strip() == "":
            errors.append({
                "row": line_num,
                "product_name": "N/A",
                "reason": "Missing required field 'product_name'"
            })
            continue

        med_name_str = str(med_name).strip()
        if med_name_str.lower() in ["medicine_name", "product_name", "column name"]:
            continue

        raw_mrp = get_val("mrp", "unit_price", "selling_price", "price")
        mrp_val = 0.0
        if raw_mrp is not None and str(raw_mrp).strip() != "":
            try:
                mrp_val = float(str(raw_mrp).replace("₹", "").replace(",", "").strip())
            except Exception:
                mrp_val = 0.0

        if mrp_val <= 0:
            errors.append({
                "row": line_num,
                "product_name": med_name_str,
                "reason": f"Invalid or missing price '{raw_mrp}'. Price (MRP) must be greater than 0."
            })
            continue

        batch_no = get_val("batch_no", "batch_number", "batch", "lot_no", "lot")
        if not batch_no or str(batch_no).strip() == "":
            batch_no = f"IMP-{int(datetime.utcnow().timestamp())}"
        batch_no_str = str(batch_no).strip()

        raw_exp = get_val("expiry_date", "exp_date", "expiry", "exp")
        exp_date = parse_date(raw_exp)
        if not exp_date:
            errors.append({
                "row": line_num,
                "product_name": med_name_str,
                "reason": f"Invalid expiry date '{raw_exp}'. Expected format: YYYY-MM-DD or DD-MM-YYYY."
            })
            continue

        raw_mfd = get_val("mfd_date", "mfg_date", "manufacturing_date", "mfd")
        mfd_date = parse_date(raw_mfd) if raw_mfd else None

        raw_qty = get_val("quantity", "qty", "stock_qty", "packs")
        try:
            qty = int(float(str(raw_qty).replace(",", "").strip())) if raw_qty is not None else 1
            if qty <= 0:
                qty = 1
        except Exception:
            qty = 1

        raw_purchase = get_val("purchase_price", "purchase_rate", "cost_price", "cost", "rate")
        try:
            purchase_val = float(str(raw_purchase).replace("₹", "").replace(",", "").strip()) if raw_purchase is not None else round(mrp_val * 0.7, 2)
        except Exception:
            purchase_val = round(mrp_val * 0.7, 2)

        raw_pack = get_val("pack_size_label", "pack_size", "packaging", "pack", "units_per_pack")
        pack_label = str(raw_pack).strip() if raw_pack else "1x10 Tablets"
        units_per_pack = parse_pack_units(pack_label)

        raw_gst = get_val("gst_percent", "gst_rate", "gst", "tax_percent")
        try:
            gst_val = float(str(raw_gst).replace("%", "").strip()) if raw_gst is not None else 12.0
        except Exception:
            gst_val = 12.0

        brand_val = str(get_val("manufacturer", "brand", "company") or "").strip() or None
        hsn_val = str(get_val("hsn_code", "hsn") or "3004").strip()
        rack_val = str(get_val("rack_location", "location", "rack", "shelf") or "").strip() or None

        lookup_key = (med_name_str.lower(), batch_no_str, exp_date)
        existing_p = existing_map.get(lookup_key)

        if existing_p and mode_clean == "skip":
            rows_skipped += 1
            continue

        if existing_p and mode_clean != "separate":
            existing_p.quantity += qty
            existing_p.unit_price = mrp_val
            existing_p.purchase_price = purchase_val
            existing_p.units_per_pack = units_per_pack
            calc_per_unit = round(mrp_val / units_per_pack, 2) if (units_per_pack and units_per_pack > 0) else mrp_val
            existing_p.price_per_unit = calc_per_unit
            existing_p.loose_tablet_price = calc_per_unit
            existing_p.tablets_per_strip = units_per_pack
            existing_p.total_price = existing_p.unit_price * existing_p.quantity
            rows_updated += 1
            imported_items.append({
                "id": existing_p.id,
                "product_name": existing_p.product_name,
                "batch_number": existing_p.batch_number,
                "quantity": existing_p.quantity,
                "mrp": existing_p.unit_price,
                "expiry_date": str(existing_p.expiry_date)
            })
        else:
            days_rem = (exp_date - date.today()).days
            p_status = "Expired" if days_rem < 0 else ("Expiring Soon" if days_rem <= 30 else "Safe")
            calc_per_unit = round(mrp_val / units_per_pack, 2) if (units_per_pack and units_per_pack > 0) else mrp_val

            new_p = models.Product(
                user_id=user_id,
                product_name=med_name_str,
                brand=brand_val,
                category="allopathy",
                batch_number=batch_no_str,
                quantity=qty,
                purchase_price=purchase_val,
                unit_price=mrp_val,
                units_per_pack=units_per_pack,
                price_per_unit=calc_per_unit,
                loose_tablet_price=calc_per_unit,
                tablets_per_strip=units_per_pack,
                expiry_date=exp_date,
                manufacturing_date=mfd_date,
                hsn_code=hsn_val,
                gst_rate=gst_val,
                gst_percentage=gst_val,
                pack_size_label=pack_label,
                days_remaining=days_rem,
                status=p_status,
                is_deleted=False
            )
            items_to_add.append(new_p)
            existing_map[lookup_key] = new_p
            rows_imported += 1
            imported_items.append({
                "id": None,
                "product_name": med_name_str,
                "batch_number": batch_no_str,
                "quantity": qty,
                "mrp": mrp_val,
                "expiry_date": str(exp_date)
            })

    if items_to_add:
        db.add_all(items_to_add)

    if items_to_add or rows_updated > 0:
        db.commit()
        invalidate_products_cache(user_id)

    total_processed = len(rows_to_process)
    total_successful = rows_imported + rows_updated

    return {
        "success": total_successful > 0 or len(errors) == 0,
        "total_rows_processed": total_processed,
        "total_rows": total_processed,
        "rows_imported": rows_imported,
        "rows_updated": rows_updated,
        "rows_skipped": rows_skipped,
        "imported_count": total_successful,
        "skipped_count": rows_skipped,
        "errors_count": len(errors),
        "errors": errors,
        "imported_items": imported_items[:20],
        "message": f"Successfully processed {total_processed} rows ({rows_imported} added, {rows_updated} updated, {len(errors)} failed)."
        if total_successful else "No items imported."
    }


# ==========================================
# ERP PRIORITY 1 CRUD FUNCTIONS
# ==========================================

import uuid
from datetime import datetime

def create_purchase_invoice(db: Session, obj_in: schemas.PurchaseInvoiceCreate, user_id: int):
    """Processes purchase invoice and automatically updates product inventory & supplier payable."""
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == obj_in.supplier_id,
        models.Supplier.user_id == user_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found or access denied.")

    db_invoice = models.PurchaseInvoice(
        user_id=user_id,
        supplier_id=obj_in.supplier_id,
        invoice_number=obj_in.invoice_number,
        invoice_date=obj_in.invoice_date,
        total_amount=obj_in.total_amount,
        tax_amount=obj_in.tax_amount,
        payment_status=obj_in.payment_status
    )
    db.add(db_invoice)
    db.flush()

    if obj_in.payment_status and obj_in.payment_status.upper() in ["PENDING", "CREDIT"]:
        supplier.outstanding_payable = round((supplier.outstanding_payable or 0.0) + obj_in.total_amount, 2)

    for item in obj_in.items:
        db_product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.user_id == user_id
        ).first()

        if db_product:
            db_product.quantity += item.quantity
            db_product.purchase_price = item.purchase_price
            db_product.unit_price = item.mrp
            db_product.gst_rate = item.gst_rate
            db_product.expiry_date = item.expiry_date
        else:
            raise HTTPException(status_code=404, detail=f"Product with ID {item.product_id} not found.")

        db_item = models.PurchaseItem(
            purchase_invoice_id=db_invoice.id,
            product_id=db_product.id,
            batch_number=item.batch_number,
            quantity=item.quantity,
            purchase_price=item.purchase_price,
            mrp=item.mrp,
            gst_rate=item.gst_rate,
            expiry_date=item.expiry_date
        )
        db.add(db_item)

        db_txn = models.InventoryTransaction(
            transaction_id=f"TXN-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8].upper()}",
            shop_id=user_id,
            product_id=db_product.id,
            transaction_type="purchase",
            quantity=item.quantity,
            unit_price=item.mrp,
            purchase_price=item.purchase_price,
            total_price=round(item.quantity * item.purchase_price, 2),
            final_price=round(item.quantity * item.purchase_price, 2)
        )
        db.add(db_txn)

    db.commit()
    db.refresh(db_invoice)
    return db_invoice


def get_purchase_dashboard(db: Session, user_id: int):
    """Returns real-time metrics for Purchase Dashboard: today_purchases, month_purchases, pending_supplier_payables, total_suppliers."""
    import datetime
    today = datetime.date.today()
    start_of_today = datetime.datetime.combine(today, datetime.time.min)
    start_of_month = datetime.datetime.combine(today.replace(day=1), datetime.time.min)

    today_purchases = db.query(func.sum(models.PurchaseInvoice.total_amount)).filter(
        models.PurchaseInvoice.user_id == user_id,
        models.PurchaseInvoice.created_at >= start_of_today
    ).scalar() or 0.0

    month_purchases = db.query(func.sum(models.PurchaseInvoice.total_amount)).filter(
        models.PurchaseInvoice.user_id == user_id,
        models.PurchaseInvoice.created_at >= start_of_month
    ).scalar() or 0.0

    total_suppliers = db.query(func.count(models.Supplier.id)).filter(
        models.Supplier.user_id == user_id
    ).scalar() or 0

    pending_supplier_payables = db.query(func.sum(models.Supplier.outstanding_payable)).filter(
        models.Supplier.user_id == user_id
    ).scalar() or 0.0

    return {
        "today_purchases": round(float(today_purchases), 2),
        "month_purchases": round(float(month_purchases), 2),
        "total_suppliers": total_suppliers,
        "pending_supplier_payables": round(float(pending_supplier_payables), 2),
    }


def get_purchase_invoices(db: Session, user_id: int, skip: int = 0, limit: int = 50):
    return db.query(models.PurchaseInvoice).filter(
        models.PurchaseInvoice.user_id == user_id
    ).offset(skip).limit(limit).all()


def get_purchase_invoice(db: Session, purchase_id: int, user_id: int):
    return db.query(models.PurchaseInvoice).filter(
        models.PurchaseInvoice.id == purchase_id,
        models.PurchaseInvoice.user_id == user_id
    ).first()


def create_purchase_return(db: Session, obj_in: schemas.PurchaseReturnCreate, user_id: int):
    """Processes return of products to wholesale supplier and decrements inventory quantity."""
    # Check if supplier exists
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == obj_in.supplier_id,
        models.Supplier.user_id == user_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found or access denied.")

    # Create PurchaseReturn record
    db_return = models.PurchaseReturn(
        user_id=user_id,
        supplier_id=obj_in.supplier_id,
        purchase_invoice_id=obj_in.purchase_invoice_id,
        total_returned_value=obj_in.total_returned_value,
        reason=obj_in.reason
    )
    db.add(db_return)
    db.flush()

    for item in obj_in.items:
        # Check if product exists in inventory
        db_product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.user_id == user_id
        ).first()

        if not db_product:
            raise HTTPException(status_code=404, detail=f"Product with ID {item.product_id} not found.")

        # Deduct quantity from inventory
        if db_product.quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{db_product.product_name}' to return. Available: {db_product.quantity}, Requested: {item.quantity}"
            )
        db_product.quantity -= item.quantity

        # Create PurchaseReturnItem record
        db_item = models.PurchaseReturnItem(
            purchase_return_id=db_return.id,
            product_id=db_product.id,
            batch_number=item.batch_number,
            quantity=item.quantity,
            purchase_price=item.purchase_price
        )
        db.add(db_item)

        # Log Inventory Transaction
        db_txn = models.InventoryTransaction(
            transaction_id=f"TXN-{datetime.utcnow():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8].upper()}",
            shop_id=user_id,
            product_id=db_product.id,
            transaction_type="purchase_return",
            quantity=item.quantity,
            unit_price=db_product.unit_price,
            purchase_price=item.purchase_price,
            total_price=round(item.quantity * item.purchase_price, 2),
            final_price=round(item.quantity * item.purchase_price, 2)
        )
        db.add(db_txn)

    db.commit()
    db.refresh(db_return)
    return db_return


def get_purchase_returns(db: Session, user_id: int, skip: int = 0, limit: int = 50):
    return db.query(models.PurchaseReturn).filter(
        models.PurchaseReturn.user_id == user_id
    ).offset(skip).limit(limit).all()


def create_customer_payment(db: Session, obj_in: schemas.CustomerPaymentCreate, user_id: int):
    """Logs credit collection payment and decrements customer pending amount."""
    customer = db.query(models.Customer).filter(
        models.Customer.id == obj_in.customer_id,
        models.Customer.user_id == user_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found or access denied.")

    # Deduct customer pending amount
    customer.pending_amount = max(0.0, customer.pending_amount - obj_in.amount_paid)

    db_payment = models.CustomerPayment(
        user_id=user_id,
        customer_id=obj_in.customer_id,
        sale_id=obj_in.sale_id,
        amount_paid=obj_in.amount_paid,
        payment_method=obj_in.payment_method
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    invalidate_customers_cache(user_id)
    return db_payment


def get_khata_dashboard(db: Session, user_id: int):
    """Returns Khata Summary KPIs: total_customers, total_outstanding, overdue_amount, today_collection."""
    import datetime
    today = datetime.date.today()
    start_of_today = datetime.datetime.combine(today, datetime.time.min)

    total_customers = db.query(func.count(models.Customer.id)).filter(
        models.Customer.user_id == user_id
    ).scalar() or 0

    total_outstanding = db.query(func.sum(models.Customer.pending_amount)).filter(
        models.Customer.user_id == user_id
    ).scalar() or 0.0

    thirty_days_ago = start_of_today - datetime.timedelta(days=30)
    overdue_amount = db.query(func.sum(models.Sale.total_amount)).filter(
        models.Sale.user_id == user_id,
        models.Sale.payment_status == "PENDING",
        models.Sale.created_at <= thirty_days_ago
    ).scalar() or 0.0

    today_collection = db.query(func.sum(models.CustomerPayment.amount_paid)).filter(
        models.CustomerPayment.user_id == user_id,
        models.CustomerPayment.created_at >= start_of_today
    ).scalar() or 0.0

    return {
        "total_customers": total_customers,
        "total_outstanding": round(float(total_outstanding), 2),
        "overdue_amount": round(float(overdue_amount), 2),
        "today_collection": round(float(today_collection), 2),
    }


def get_customer_payments(db: Session, customer_id: int, user_id: int, skip: int = 0, limit: int = 50):
    return db.query(models.CustomerPayment).filter(
        models.CustomerPayment.customer_id == customer_id,
        models.CustomerPayment.user_id == user_id
    ).offset(skip).limit(limit).all()


def get_customer_ledger(db: Session, customer_id: int, user_id: int):
    """Returns chronologically combined ledger list of credit sales, returns, and collections."""
    customer = db.query(models.Customer).filter(
        models.Customer.id == customer_id,
        models.Customer.user_id == user_id
    ).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found.")

    all_customer_sales = db.query(models.Sale).filter(
        models.Sale.customer_id == customer_id,
        models.Sale.user_id == user_id,
    ).all()

    sale_ids = [s.id for s in all_customer_sales]
    credit_payments = db.query(models.SalePayment).filter(
        models.SalePayment.sale_id.in_(sale_ids),
        models.SalePayment.payment_method == "CREDIT"
    ).all() if sale_ids else []
    credit_payment_map = {cp.sale_id: float(cp.amount or 0.0) for cp in credit_payments}

    payments = db.query(models.CustomerPayment).filter(
        models.CustomerPayment.customer_id == customer_id,
        models.CustomerPayment.user_id == user_id
    ).all()

    returns = db.query(models.SaleReturn).join(
        models.Sale, models.SaleReturn.sale_id == models.Sale.id
    ).filter(
        models.Sale.customer_id == customer_id,
        models.SaleReturn.user_id == user_id
    ).all()

    ledger = []
    for s in all_customer_sales:
        credit_amt = 0.0
        if s.payment_method in ["CREDIT", "PENDING"]:
            credit_amt = float(s.total_amount or 0.0)
        elif s.id in credit_payment_map:
            credit_amt = credit_payment_map[s.id]

        if credit_amt > 0:
            ledger.append({
                "type": "sale",
                "id": s.id,
                "reference": s.bill_number,
                "amount": round(credit_amt, 2),
                "date": s.created_at
            })

    for p in payments:
        ledger.append({
            "type": "payment",
            "id": p.id,
            "reference": f"PAY-{p.id}",
            "amount": round(float(p.amount_paid or 0.0), 2),
            "date": p.created_at
        })

    for r in returns:
        ledger.append({
            "type": "return",
            "id": r.id,
            "reference": f"RET-{r.id}",
            "amount": round(float(r.return_amount or 0.0), 2),
            "date": r.created_at
        })

    # Sort chronologically by date safely
    def make_naive(dt):
        if dt is None:
            return datetime.min
        return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt

    ledger.sort(key=lambda x: make_naive(x["date"]))
    return {
        "customer_name": customer.name,
        "phone": customer.phone,
        "current_outstanding": round(float(customer.pending_amount or 0.0), 2),
        "transactions": ledger
    }


def create_supplier_payment(db: Session, obj_in: schemas.SupplierPaymentCreate, user_id: int):
    """Logs payment made to wholesale supplier."""
    supplier = db.query(models.Supplier).filter(
        models.Supplier.id == obj_in.supplier_id,
        models.Supplier.user_id == user_id
    ).first()
    if not supplier:
        raise HTTPException(status_code=404, detail="Supplier not found or access denied.")

    db_payment = models.SupplierPayment(
        user_id=user_id,
        supplier_id=obj_in.supplier_id,
        amount_paid=obj_in.amount_paid,
        payment_method=obj_in.payment_method,
        notes=obj_in.notes
    )
    db.add(db_payment)
    db.commit()
    db.refresh(db_payment)
    return db_payment


def get_supplier_payments(db: Session, supplier_id: int, user_id: int, skip: int = 0, limit: int = 50):
    return db.query(models.SupplierPayment).filter(
        models.SupplierPayment.supplier_id == supplier_id,
        models.SupplierPayment.user_id == user_id
    ).offset(skip).limit(limit).all()


def get_dashboard_stats(db: Session, user_id: int):
    """Computes real-time KPI metrics for the mobile business dashboard with optimized SQL queries."""
    import datetime
    today = datetime.date.today()
    start_of_today = datetime.datetime.combine(today, datetime.time.min)
    start_of_month = datetime.datetime.combine(today.replace(day=1), datetime.time.min)

    # 1. Total Receivables (Khata credit balance)
    total_receivables = db.query(func.sum(models.Customer.pending_amount)).filter(
        models.Customer.user_id == user_id
    ).scalar() or 0.0

    # 2. Total Payables (Supplier credit balance)
    total_purchases = db.query(func.sum(models.PurchaseInvoice.total_amount)).filter(
        models.PurchaseInvoice.user_id == user_id
    ).scalar() or 0.0
    total_supplier_paid = db.query(func.sum(models.SupplierPayment.amount_paid)).filter(
        models.SupplierPayment.user_id == user_id
    ).scalar() or 0.0
    total_payables = max(0.0, float(total_purchases) - float(total_supplier_paid))

    # 3. Today's Revenue and Monthly Revenue
    today_revenue = db.query(func.sum(models.Sale.total_amount)).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= start_of_today
    ).scalar() or 0.0

    month_revenue = db.query(func.sum(models.Sale.total_amount)).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= start_of_month
    ).scalar() or 0.0

    # 4. Inventory stats via SQL aggregations
    low_stock_count = db.query(func.count(models.Product.id)).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
        models.Product.quantity <= 20
    ).scalar() or 0

    expired_count = db.query(func.count(models.Product.id)).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
        models.Product.expiry_date < today
    ).scalar() or 0

    expired_value = db.query(func.sum(models.Product.quantity * models.Product.purchase_price)).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
        models.Product.expiry_date < today
    ).scalar() or 0.0

    # 5. Net Profit (Revenue - COGS) for current month via SQL join
    cogs_result = db.query(
        func.sum(
            models.SaleItem.quantity * func.coalesce(
                models.Product.purchase_price,
                models.SaleItem.unit_price * 0.7
            )
        )
    ).join(
        models.Sale, models.SaleItem.sale_id == models.Sale.id
    ).outerjoin(
        models.Product, models.SaleItem.product_id == models.Product.id
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= start_of_month
    ).scalar() or 0.0

    net_profit = max(0.0, float(month_revenue) - float(cogs_result))

    return {
        "today_revenue": round(float(today_revenue), 2),
        "month_revenue": round(float(month_revenue), 2),
        "net_profit": round(float(net_profit), 2),
        "low_stock_count": int(low_stock_count),
        "expired_count": int(expired_count),
        "expired_value": round(float(expired_value), 2),
        "credit_receivables": round(float(total_receivables), 2),
        "supplier_payables": round(float(total_payables), 2)
    }


# ===========================
# ===========================
# SMART INVENTORY INTELLIGENCE & RESTOCK ENGINE
# ===========================

def get_inventory_summary(db: Session, user_id: int):
    """
    Blazing-fast SQL-aggregated inventory health dashboard summary.
    Executes unified database queries for 100% exact parity with get_products filters.
    """
    today_dt = date.today()
    thirty_days_later_dt = today_dt + timedelta(days=30)
    dt_90d = datetime.utcnow() - timedelta(days=90)

    base_q = db.query(models.Product).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    )

    total_products = base_q.count()

    stock_val_row = base_q.filter(models.Product.quantity > 0).with_entities(
        func.coalesce(func.sum(models.Product.quantity * models.Product.unit_price), 0.0)
    ).first()
    total_stock_value = float(stock_val_row[0]) if stock_val_row else 0.0

    expiring_30_days = base_q.filter(
        models.Product.quantity > 0,
        models.Product.expiry_date.between(today_dt, thirty_days_later_dt)
    ).count()

    expired = base_q.filter(
        models.Product.quantity > 0,
        models.Product.expiry_date < today_dt
    ).count()

    low_stock = base_q.filter(
        models.Product.quantity > 0,
        models.Product.quantity <= 10
    ).count()

    out_of_stock = base_q.filter(
        models.Product.quantity <= 0
    ).count()

    sold_product_ids_subquery = (
        select(models.SaleItem.product_id)
        .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
        .filter(models.Sale.user_id == user_id, models.Sale.created_at >= dt_90d)
        .scalar_subquery()
    )
    dead_stock = base_q.filter(
        models.Product.quantity > 0,
        ~models.Product.id.in_(sold_product_ids_subquery)
    ).count()

    priority_sale = 0
    try:
        priority_sale = db.query(models.PrioritySale).filter(
            models.PrioritySale.user_id == user_id
        ).count()
    except Exception as e:
        db.rollback()

    marked_for_return = 0
    try:
        marked_for_return = db.query(models.MarkedForReturn).filter(
            models.MarkedForReturn.user_id == user_id
        ).count()
    except Exception as e:
        db.rollback()

    return {
        "total_products": total_products,
        "total_stock_value": round(total_stock_value, 2),
        "expiring_30_days": expiring_30_days,
        "expired": expired,
        "low_stock": low_stock,
        "out_of_stock": out_of_stock,
        "dead_stock": dead_stock,
        "priority_sale": priority_sale,
        "marked_for_return": marked_for_return,
    }


def get_inventory_intelligence(
    db: Session,
    user_id: int,
    category: Optional[str] = None,
    supplier_id: Optional[int] = None,
    priority_level: Optional[str] = None,
    debug: bool = False,
    limit: int = 100,
    offset: int = 0
):
    """
    Production-grade Smart Restock / Inventory Intelligence decision engine.
    Analyzes historical multi-period sales velocity, current stock, batch-level expiry risk,
    supplier lead times, and financial capital at risk to produce a ranked list of actions.
    """
    today = date.today()
    now_utc = datetime.utcnow()
    
    # 1. Query all active products for the user (scoped to account isolation)
    prod_query = db.query(models.Product).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    )
    if category and category != 'all':
        prod_query = prod_query.filter(models.Product.category.ilike(f"%{category}%"))
    if supplier_id:
        prod_query = prod_query.filter(models.Product.supplier_id == supplier_id)
        
    products = prod_query.all()
    if not products:
        return {
            "generated_at": now_utc.isoformat(),
            "summary": {
                "critical_restock": 0, "restock_soon": 0, "expiry_risk": 0,
                "slow_moving": 0, "dead_stock": 0, "overstock": 0, "healthy": 0,
                "total_at_risk_value": 0.0
            },
            "recommendations": [],
            "needs_attention": [],
            "total_products": 0, "total_stock_value": 0.0, "expired_count": 0,
            "expired_value": 0.0, "expiring_7d_count": 0, "expiring_30d_count": 0,
            "expiring_30d_value": 0.0, "expiring_60d_count": 0, "expiring_90d_count": 0,
            "expiring_90d_value": 0.0, "low_stock_count": 0, "out_of_stock_count": 0,
            "dead_stock_count": 0, "dead_stock_value": 0.0,
            "low_stock_items": [], "expiring_items": [], "expired_items": [], "dead_stock_items": []
        }

    product_ids = [p.id for p in products]

    # 2. Multi-Window Historical Sales Aggregation
    now_naive = datetime.utcnow()
    dt_7d = now_naive - timedelta(days=7)
    dt_14d = now_naive - timedelta(days=14)
    dt_30d = now_naive - timedelta(days=30)
    dt_60d = now_naive - timedelta(days=60)
    dt_90d = now_naive - timedelta(days=90)

    sales_agg = db.query(
        models.SaleItem.product_id,
        func.coalesce(func.sum(case((models.Sale.created_at >= dt_7d, models.SaleItem.quantity), else_=0)), 0).label("qty_7d"),
        func.coalesce(func.sum(case((models.Sale.created_at >= dt_14d, models.SaleItem.quantity), else_=0)), 0).label("qty_14d"),
        func.coalesce(func.sum(case((models.Sale.created_at >= dt_30d, models.SaleItem.quantity), else_=0)), 0).label("qty_30d"),
        func.coalesce(func.sum(case((models.Sale.created_at >= dt_60d, models.SaleItem.quantity), else_=0)), 0).label("qty_60d"),
        func.coalesce(func.sum(case((models.Sale.created_at >= dt_90d, models.SaleItem.quantity), else_=0)), 0).label("qty_90d"),
        func.min(models.Sale.created_at).label("first_sale_date"),
        func.max(models.Sale.created_at).label("last_sale_date")
    ).join(
        models.Sale, models.SaleItem.sale_id == models.Sale.id
    ).filter(
        models.Sale.user_id == user_id,
        models.SaleItem.product_id.in_(product_ids)
    ).group_by(models.SaleItem.product_id).all()

    sales_map = {
        row.product_id: {
            "qty_7d": row.qty_7d or 0,
            "qty_14d": row.qty_14d or 0,
            "qty_30d": row.qty_30d or 0,
            "qty_60d": row.qty_60d or 0,
            "qty_90d": row.qty_90d or 0,
            "first_sale_date": row.first_sale_date,
            "last_sale_date": row.last_sale_date,
        }
        for row in sales_agg
    }

    # 3. Load Suppliers map
    suppliers = db.query(models.Supplier).filter(models.Supplier.user_id == user_id).all()
    supplier_map = {s.id: s.name for s in suppliers}

    # Algorithm Configurable Defaults
    DEFAULT_LEAD_TIME = 5  # Days
    SAFETY_STOCK_DAYS = 5
    TARGET_COVERAGE_DAYS = 30

    recommendations_list = []
    summary_counts = {
        "critical_restock": 0, "restock_soon": 0, "expiry_risk": 0,
        "slow_moving": 0, "dead_stock": 0, "overstock": 0, "healthy": 0,
        "total_at_risk_value": 0.0
    }

    # Legacy Backward-Compatibility Accumulators
    total_stock_val = 0.0
    expired_cnt = 0
    expired_val = 0.0
    expiring_7d_cnt = 0
    expiring_30d_cnt = 0
    expiring_30d_val = 0.0
    expiring_60d_cnt = 0
    expiring_90d_cnt = 0
    expiring_90d_val = 0.0
    low_stock_cnt = 0
    out_of_stock_cnt = 0
    dead_stock_cnt = 0
    dead_stock_val = 0.0

    for p in products:
        cost_price = float(p.purchase_price if (p.purchase_price and p.purchase_price > 0) else (p.unit_price * 0.7 if p.unit_price else 0.0))
        selling_price = float(p.unit_price or 0.0)
        curr_stock = max(0, int(p.quantity or 0))
        inv_val = round(curr_stock * cost_price, 2)
        total_stock_val += inv_val

        # Sales History Analysis
        sh = sales_map.get(p.id, {})
        q7 = sh.get("qty_7d", 0)
        q14 = sh.get("qty_14d", 0)
        q30 = sh.get("qty_30d", 0)
        q60 = sh.get("qty_60d", 0)
        q90 = sh.get("qty_90d", 0)
        last_sale = sh.get("last_sale_date")

        v7 = q7 / 7.0
        v14 = q14 / 14.0
        v30 = q30 / 30.0
        v60 = q60 / 60.0
        v90 = q90 / 90.0

        # Detect Outlier Spikes
        normal_baseline = (v30 * 0.6) + (v90 * 0.4)
        if v7 > (3.0 * normal_baseline) and normal_baseline > 0:
            v7_capped = min(v7, normal_baseline * 2.0)
        else:
            v7_capped = v7

        # Weighted Forecast Daily Demand
        if q90 > 0:
            forecast_demand = (v7_capped * 0.40) + (v30 * 0.35) + (v90 * 0.25)
            confidence = "HIGH"
            confidence_reason = "Based on 90 days of continuous pharmacy sales history."
        elif q30 > 0:
            forecast_demand = (v7_capped * 0.50) + (v30 * 0.50)
            confidence = "MEDIUM"
            confidence_reason = "Based on 30 days of recent sales history."
        elif q14 > 0:
            forecast_demand = (v7 * 0.60) + (v14 * 0.40)
            confidence = "MEDIUM"
            confidence_reason = "Based on 14 days of recent sales history."
        elif q7 > 0:
            forecast_demand = v7
            confidence = "LOW"
            confidence_reason = "Based on limited 7-day sales history."
        else:
            forecast_demand = 0.0
            confidence = "LOW"
            confidence_reason = "No historical sales recorded for this product."

        forecast_demand = round(forecast_demand, 2)

        # Days of Stock Calculation
        if forecast_demand > 0:
            days_of_stock = round(curr_stock / forecast_demand, 1)
        else:
            days_of_stock = 9999.0 if curr_stock > 0 else 0.0

        # Safety Stock & Reorder Calculations
        lead_time = DEFAULT_LEAD_TIME
        safety_stock = int(round(forecast_demand * SAFETY_STOCK_DAYS))
        reorder_point = int(round((forecast_demand * lead_time) + safety_stock))
        target_stock = int(round(forecast_demand * TARGET_COVERAGE_DAYS))
        pack_size = p.tablets_per_strip or 10

        if forecast_demand > 0:
            raw_suggested = max(0, target_stock - curr_stock)
            if raw_suggested > 0 and pack_size > 1:
                suggested_order_qty = int(math.ceil(raw_suggested / float(pack_size)) * pack_size)
            else:
                suggested_order_qty = raw_suggested
        else:
            suggested_order_qty = 0

        # Batch-Level Expiry Risk
        exp_date = p.expiry_date
        days_to_exp = (exp_date - today).days if exp_date else 9999
        at_risk_qty = 0
        at_risk_val = 0.0

        if exp_date:
            if exp_date < today:
                expired_cnt += 1
                expired_val += inv_val
            elif days_to_exp <= 7:
                expiring_7d_cnt += 1
            elif days_to_exp <= 30:
                expiring_30d_cnt += 1
                expiring_30d_val += inv_val
            elif days_to_exp <= 60:
                expiring_60d_cnt += 1
            elif days_to_exp <= 90:
                expiring_90d_cnt += 1
                expiring_90d_val += inv_val

            if exp_date >= today and days_to_exp <= 90:
                exp_sales_possible = forecast_demand * max(0, days_to_exp)
                if curr_stock > exp_sales_possible:
                    at_risk_qty = int(round(curr_stock - exp_sales_possible))
                    at_risk_val = round(at_risk_qty * cost_price, 2)

        if curr_stock == 0:
            out_of_stock_cnt += 1
        elif curr_stock <= 10:
            low_stock_cnt += 1

        if last_sale and hasattr(last_sale, 'tzinfo') and last_sale.tzinfo is not None:
            last_sale_naive = last_sale.replace(tzinfo=None)
        else:
            last_sale_naive = last_sale

        days_since_last_sale = (now_naive - last_sale_naive).days if last_sale_naive else 9999
        if curr_stock > 0 and q90 == 0:
            dead_stock_cnt += 1
            dead_stock_val += inv_val

        # Priority Level Classification & Score Determination
        level = "HEALTHY"
        score = 10
        rec_type = "MONITOR"
        reason = "Normal demand velocity and adequate stock coverage."
        action = "NO ACTION REQUIRED"

        # Case 1: CRITICAL RESTOCK (Stockout Imminent vs Lead Time)
        if forecast_demand > 0 and (curr_stock <= reorder_point or days_of_stock <= lead_time):
            if days_of_stock <= (lead_time * 0.8) or curr_stock == 0:
                level = "CRITICAL_RESTOCK"
                urgency = min(100, int((1.0 - (days_of_stock / max(1.0, lead_time))) * 100))
                score = min(99, max(85, int(85 + (urgency * 0.14))))
                rec_type = "RESTOCK_NOW"
                if curr_stock == 0:
                    reason = f"Out of stock! Daily demand is {forecast_demand}/day with an estimated {lead_time}-day supplier lead time."
                else:
                    reason = f"Only ~{days_of_stock} days of stock remaining, which is below the {lead_time}-day supplier lead time."
                action = "RESTOCK IMMEDIATELY"
            else:
                level = "RESTOCK_SOON"
                score = min(84, max(65, int(65 + ((reorder_point - curr_stock) / max(1, reorder_point) * 19))))
                rec_type = "RESTOCK_SOON"
                reason = f"Stock level ({curr_stock}) has dropped below the calculated reorder point of {reorder_point} units."
                action = "ADD TO PURCHASE DRAFT"

        # Case 2: EXPIRY RISK WITH FINANCIAL EXPOSURE
        elif exp_date and exp_date >= today and days_to_exp <= 60 and at_risk_qty > 0:
            level = "EXPIRY_RISK"
            score = min(95, max(70, int(70 + (at_risk_val / max(100.0, inv_val) * 25))))
            rec_type = "RETURN_DISTRIBUTOR" if days_to_exp <= 30 else "PRIORITIZE_FEFO"
            reason = f"{at_risk_qty} units expected to remain unsold when this batch expires in {days_to_exp} days (Rs {at_risk_val:.2f} capital at risk)."
            action = "RETURN TO DISTRIBUTOR" if days_to_exp <= 30 else "PRIORITIZE FEFO DISPENSING"

        # Case 3: DEAD STOCK (No sales in 90+ days + Stock > 0)
        elif curr_stock > 0 and q90 == 0 and (last_sale is None or days_since_last_sale >= 60):
            level = "DEAD_STOCK"
            score = min(64, max(45, int(45 + min(19, 90 if last_sale is None else days_since_last_sale / 10))))
            rec_type = "CLEARANCE_DISCOUNT"
            reason = f"Zero sales recorded in the last 90+ days while {curr_stock} units remain in stock (Rs {inv_val:.2f} tied-up capital)."
            action = "CONSIDER CLEARANCE / SUPPLIER RETURN"

        # Case 4: SLOW MOVING
        elif curr_stock > 0 and forecast_demand > 0 and days_of_stock >= 90:
            level = "SLOW_MOVING"
            score = min(44, max(30, int(30 + min(14, days_of_stock / 20))))
            rec_type = "STOP_PURCHASING"
            reason = f"Slow sales velocity ({forecast_demand}/day). Current stock provides ~{int(days_of_stock)} days of coverage."
            action = "HALT PURCHASING & REVIEW"

        # Case 5: OVERSTOCK
        elif curr_stock > 0 and forecast_demand > 0 and days_of_stock >= 60:
            level = "OVERSTOCK"
            score = min(29, max(15, int(15 + min(14, days_of_stock / 10))))
            rec_type = "REDUCE_ORDER"
            reason = f"Current stock ({curr_stock} units) exceeds the target {TARGET_COVERAGE_DAYS}-day coverage level."
            action = "REDUCE FUTURE ORDERS"

        # Case 6: EXPIRED (Soft alert)
        elif exp_date and exp_date < today and curr_stock > 0:
            level = "EXPIRY_RISK"
            score = 98
            rec_type = "RETURN_DISTRIBUTOR"
            reason = f"Batch expired on {exp_date}. Remove from active shelves immediately."
            action = "PURGE / WRITE OFF EXPIRED STOCK"

        # Accumulate Summary Counts across all products
        if level == "CRITICAL_RESTOCK": summary_counts["critical_restock"] += 1
        elif level == "RESTOCK_SOON": summary_counts["restock_soon"] += 1
        elif level == "EXPIRY_RISK": summary_counts["expiry_risk"] += 1; summary_counts["total_at_risk_value"] += at_risk_val
        elif level == "SLOW_MOVING": summary_counts["slow_moving"] += 1
        elif level == "DEAD_STOCK": summary_counts["dead_stock"] += 1
        elif level == "OVERSTOCK": summary_counts["overstock"] += 1
        elif level == "HEALTHY": summary_counts["healthy"] += 1

        # Filter by priority_level query parameter if requested
        if priority_level and priority_level != 'ALL' and level != priority_level:
            continue

        rec_item = {
            "rank": 0,
            "product_id": p.id,
            "product_name": p.product_name,
            "brand": p.brand,
            "category": p.category,
            "batch_number": p.batch_number or "N/A",
            "supplier_id": p.supplier_id,
            "supplier_name": supplier_map.get(p.supplier_id, "Direct Purchase / Unlinked"),
            "priority_level": level,
            "priority_score": score,
            "recommendation_type": rec_type,
            "current_stock": curr_stock,
            "daily_demand": forecast_demand,
            "days_of_stock": None if days_of_stock >= 999 else days_of_stock,
            "supplier_lead_time_days": lead_time,
            "safety_stock": safety_stock,
            "reorder_point": reorder_point,
            "suggested_order_quantity": suggested_order_qty,
            "unit_price": selling_price,
            "purchase_price": cost_price,
            "inventory_value": inv_val,
            "at_risk_value": at_risk_val if level == "EXPIRY_RISK" else (inv_val if level in ["DEAD_STOCK", "SLOW_MOVING"] else 0.0),
            "expiry_date": str(exp_date) if exp_date else None,
            "days_to_expiry": days_to_exp if exp_date else None,
            "at_risk_expiry_qty": at_risk_qty,
            "confidence": confidence,
            "confidence_reason": confidence_reason,
            "reason": reason,
            "recommended_action": action,
        }

        if debug:
            rec_item["debug_info"] = {
                "v7": round(v7, 3), "v30": round(v30, 3), "v90": round(v90, 3),
                "v7_capped": round(v7_capped, 3), "forecast_demand": forecast_demand,
                "days_since_last_sale": days_since_last_sale,
                "q7": q7, "q30": q30, "q90": q90
            }

        recommendations_list.append(rec_item)

    # Sort Recommendations by Priority Score Descending
    recommendations_list.sort(key=lambda x: (x["priority_score"], x["at_risk_value"]), reverse=True)

    # Assign Ranks
    for idx, item in enumerate(recommendations_list):
        item["rank"] = idx + 1

    paginated_recs = recommendations_list[offset: offset + limit]

    # Needs Attention Action Chips (Top 4 Highest Urgency)
    needs_attn = []
    if summary_counts["critical_restock"] > 0:
        needs_attn.append({
            "type": "CRITICAL_RESTOCK",
            "title": f"🔴 {summary_counts['critical_restock']} Critical Stockouts",
            "subtitle": "Order immediately before stockout",
            "severity": "high"
        })
    if summary_counts["expiry_risk"] > 0:
        needs_attn.append({
            "type": "EXPIRY_RISK",
            "title": f"🟠 {summary_counts['expiry_risk']} Expiry Risk Batches",
            "subtitle": f"₹{summary_counts['total_at_risk_value']:,.2f} capital at risk",
            "severity": "high"
        })
    if summary_counts["dead_stock"] > 0:
        needs_attn.append({
            "type": "DEAD_STOCK",
            "title": f"🔵 {summary_counts['dead_stock']} Dead Stock Items",
            "subtitle": "90+ days no sales",
            "severity": "medium"
        })

    # Legacy Backward-Compatibility Sample Lists
    low_stock_items = [
        {"id": r["product_id"], "product_name": r["product_name"], "batch_number": r["batch_number"], "quantity": r["current_stock"], "unit_price": r["unit_price"], "status": "Out of Stock" if r["current_stock"] == 0 else "Low Stock", "suggested_reorder": r["suggested_order_quantity"]}
        for r in recommendations_list if r["priority_level"] in ["CRITICAL_RESTOCK", "RESTOCK_SOON"]
    ][:20]

    expiring_items = [
        {"id": r["product_id"], "product_name": r["product_name"], "batch_number": r["batch_number"], "expiry_date": r["expiry_date"], "days_remaining": r["days_to_expiry"], "quantity": r["current_stock"], "stock_value": r["inventory_value"], "category": "Expiring Risk"}
        for r in recommendations_list if r["priority_level"] == "EXPIRY_RISK"
    ][:20]

    dead_stock_items = [
        {"id": r["product_id"], "product_name": r["product_name"], "batch_number": r["batch_number"], "quantity": r["current_stock"], "stock_value": r["inventory_value"], "days_without_sale": 90}
        for r in recommendations_list if r["priority_level"] == "DEAD_STOCK"
    ][:20]

    summary_counts["total_products"] = len(products)
    summary_counts["total_stock_value"] = round(total_stock_val, 2)
    summary_counts["expiring_soon_count"] = expiring_7d_cnt + expiring_30d_cnt
    summary_counts["expiring_30d_count"] = expiring_7d_cnt + expiring_30d_cnt
    summary_counts["expired_count"] = expired_cnt
    summary_counts["low_stock_count"] = low_stock_cnt
    summary_counts["out_of_stock_count"] = out_of_stock_cnt
    summary_counts["dead_stock_count"] = dead_stock_cnt

    return {
        "generated_at": now_utc.isoformat(),
        "summary": summary_counts,
        "recommendations": paginated_recs,
        "needs_attention": needs_attn,
        # Legacy fields
        "total_products": len(products),
        "total_stock_value": round(total_stock_val, 2),
        "expired_count": expired_cnt,
        "expired_value": round(expired_val, 2),
        "expiring_7d_count": expiring_7d_cnt,
        "expiring_30d_count": expiring_7d_cnt + expiring_30d_cnt,
        "expiring_30d_value": round(expiring_30d_val, 2),
        "expiring_60d_count": expiring_60d_cnt,
        "expiring_90d_count": expiring_90d_cnt,
        "expiring_90d_value": round(expiring_90d_val, 2),
        "low_stock_count": low_stock_cnt,
        "out_of_stock_count": out_of_stock_cnt,
        "dead_stock_count": dead_stock_cnt,
        "dead_stock_value": round(dead_stock_val, 2),
        "low_stock_items": low_stock_items,
        "expiring_items": expiring_items,
        "expired_items": [],
        "dead_stock_items": dead_stock_items
    }



# ===========================
# SMART ALERTS & NOTIFICATIONS
# ===========================

def get_smart_alerts(db: Session, user_id: int, category: Optional[str] = None):
    intel = get_inventory_intelligence(db, user_id)
    summary = intel.get("summary", {})
    
    user = db.query(models.User).filter(models.User.id == user_id).first()
    expiry_enabled = getattr(user, 'expiry_alerts_enabled', True) if user else True
    low_stock_enabled = getattr(user, 'low_stock_alerts_enabled', True) if user else True

    alerts = []

    exp_count = summary.get("expired_count", 0)
    exp_soon = summary.get("expiring_soon_count", 0)
    exp_val = intel.get("expiring_30d_value", 0.0) + intel.get("expired_value", 0.0)

    if expiry_enabled and (exp_count > 0 or exp_soon > 0):
        alerts.append({
            "id": f"expiry_summary_{user_id}",
            "category": "Expired" if exp_count > 0 else "Expiring Soon",
            "priority": "CRITICAL" if exp_count > 0 else "HIGH",
            "title": "Inventory Expiry Summary",
            "message": f"Inventory Attention: {exp_count} expired batch(es), {exp_soon} batch(es) expire in 30d. ₹{exp_val:.2f} stock at risk.",
            "what": f"{exp_count} expired, {exp_soon} expiring soon",
            "why": f"₹{exp_val:.2f} capital at risk of loss",
            "action_type": "inventory_filter",
            "action_target": "expired" if exp_count > 0 else "expiring",
            "action_label": "View Expiry Risk",
            "created_at": datetime.utcnow().isoformat(),
            "is_read": False
        })

    low_count = summary.get("low_stock_count", 0)
    out_count = summary.get("out_of_stock_count", 0)

    if low_stock_enabled and (low_count > 0 or out_count > 0):
        alerts.append({
            "id": f"low_stock_summary_{user_id}",
            "category": "Out of Stock" if out_count > 0 else "Low Stock",
            "priority": "CRITICAL" if out_count > 0 else "HIGH",
            "title": "Stock Reorder Warning",
            "message": f"Reorder Warning: {out_count} out-of-stock medicine(s), {low_count} running low.",
            "what": f"{out_count} out-of-stock, {low_count} low-stock items",
            "why": "Prevent stock-outs and customer loss",
            "action_type": "inventory_filter",
            "action_target": "lowstock",
            "action_label": "Review Low Stock",
            "created_at": datetime.utcnow().isoformat(),
            "is_read": False
        })

    pending_sales = (
        db.query(models.Sale)
        .filter(models.Sale.user_id == user_id, models.Sale.payment_status == "PENDING")
        .all()
    )
    if pending_sales:
        overdue_count = len(pending_sales)
        overdue_total = sum(s.total_amount for s in pending_sales)
        alerts.append({
            "id": f"khata_summary_{user_id}",
            "category": "Payment/Khata",
            "priority": "HIGH",
            "title": "Customer Khata Overdue Balance",
            "message": f"{overdue_count} customer bill(s) pending payment. Total outstanding balance: ₹{overdue_total:.2f}.",
            "what": f"{overdue_count} pending customer bills",
            "why": f"₹{overdue_total:.2f} receivables pending collection",
            "action_type": "khata",
            "action_target": "pending_ledger",
            "action_label": "Open Ledger",
            "created_at": datetime.utcnow().isoformat(),
            "is_read": False
        })

    dead_count = summary.get("dead_stock_count", 0)
    dead_val = summary.get("dead_stock_value", 0.0)

    if dead_count > 0:
        alerts.append({
            "id": f"dead_stock_summary_{user_id}",
            "category": "Dead Stock",
            "priority": "NORMAL",
            "title": "Dead Stock Intelligence (90+ Days No Sales)",
            "message": f"{dead_count} medicine(s) have had no sales in 90+ days (₹{dead_val:.2f} tied-up capital).",
            "what": f"{dead_count} unsold medicines for 90+ days",
            "why": f"₹{dead_val:.2f} tied-up inventory capital",
            "action_type": "inventory_filter",
            "action_target": "deadstock",
            "action_label": "Review Dead Stock",
            "created_at": datetime.utcnow().isoformat(),
            "is_read": False
        })

    # Include item-level actionable recommendations
    recommendations = intel.get("recommendations", [])
    for rec in recommendations:
        priority_lvl = rec.get("priority_level", "")
        prod_name = rec.get("product_name", "Item")
        prod_id = rec.get("product_id")
        batch_no = rec.get("batch_number", "N/A")
        
        if priority_lvl == "CRITICAL_RESTOCK":
            is_out = rec.get("current_stock", 0) <= 0
            alerts.append({
                "id": f"rec_restock_{prod_id}_{batch_no}",
                "category": "Out of Stock" if is_out else "Low Stock",
                "priority": "CRITICAL" if is_out else "HIGH",
                "title": f"Critical Restock: {prod_name}",
                "message": rec.get("reason", f"Stockout risk for {prod_name}"),
                "what": f"Current stock: {rec.get('current_stock', 0)} (Reorder point: {rec.get('reorder_point', 10)})",
                "why": "Prevent stock-outs and customer loss",
                "action_type": "inventory_filter",
                "action_target": "lowstock",
                "action_label": "Restock Item",
                "created_at": datetime.utcnow().isoformat(),
                "is_read": False
            })
        elif priority_lvl == "EXPIRY_RISK":
            days_exp = rec.get("days_to_expiry", 0)
            alerts.append({
                "id": f"rec_expiry_{prod_id}_{batch_no}",
                "category": "Expired" if days_exp < 0 else "Expiring Soon",
                "priority": "CRITICAL" if days_exp <= 0 else "HIGH",
                "title": f"Expiry Risk: {prod_name} (Batch {batch_no})",
                "message": rec.get("reason", f"Batch {batch_no} is near expiry."),
                "what": f"Expired {abs(days_exp)} days ago" if days_exp < 0 else f"Expires in {days_exp} days",
                "why": f"₹{rec.get('at_risk_value', 0.0):.2f} capital at risk",
                "action_type": "inventory_filter",
                "action_target": "expired" if days_exp < 0 else "expiring",
                "action_label": "View Batch",
                "created_at": datetime.utcnow().isoformat(),
                "is_read": False
            })

    if category and category.lower() != "all":
        cat_lower = category.lower()
        filtered = []
        for a in alerts:
            a_cat = a.get("category", "").lower()
            a_prio = a.get("priority", "").lower()

            if cat_lower == "critical" and a_prio == "critical":
                filtered.append(a)
            elif cat_lower in ("expiry", "expired", "expiring", "expiring soon") and ("expir" in a_cat or "expired" in a_cat):
                filtered.append(a)
            elif cat_lower in ("stock", "low stock", "lowstock", "out of stock") and ("stock" in a_cat or "reorder" in a_cat or "out" in a_cat):
                filtered.append(a)
            elif cat_lower in ("khata", "payment", "payment/khata") and ("khata" in a_cat or "payment" in a_cat or "receivable" in a_cat):
                filtered.append(a)
            elif cat_lower in ("dead stock", "deadstock") and "dead" in a_cat:
                filtered.append(a)
            elif cat_lower == a_cat or cat_lower == a_prio:
                filtered.append(a)
        alerts = filtered

    return alerts

def get_alert_summary(db: Session, user_id: int):
    alerts = get_smart_alerts(db, user_id)
    unread_count = len(alerts)
    critical_count = sum(1 for a in alerts if a.get("priority") == "CRITICAL")
    return {
        "unread_count": unread_count,
        "critical_count": critical_count,
        "total_alerts": len(alerts)
    }

def get_alert_preferences(db: Session, user_id: int):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    return {
        "expiry_enabled": getattr(user, 'expiry_alerts_enabled', True),
        "low_stock_enabled": getattr(user, 'low_stock_alerts_enabled', True),
        "billing_enabled": getattr(user, 'billing_notifications_enabled', True),
    }

def update_alert_preferences(db: Session, user_id: int, prefs: dict):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user:
        if "expiry_enabled" in prefs:
            user.expiry_alerts_enabled = bool(prefs["expiry_enabled"])
        if "low_stock_enabled" in prefs:
            user.low_stock_alerts_enabled = bool(prefs["low_stock_enabled"])
        if "billing_enabled" in prefs:
            user.billing_notifications_enabled = bool(prefs["billing_enabled"])
        db.commit()
    return get_alert_preferences(db, user_id)


def get_reports_analytics(
    db: Session,
    user_id: int,
    period: str = "this_month",
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
):
    """Computes comprehensive business intelligence & financial report analytics."""
    import datetime
    # Use Indian Standard Time (UTC+5:30) for calendar date calculations
    ist_offset = datetime.timedelta(hours=5, minutes=30)
    now_utc = datetime.datetime.utcnow()
    now_ist = now_utc + ist_offset
    today = now_ist.date()

    start_of_today = datetime.datetime.combine(today, datetime.time.min)
    end_of_today = datetime.datetime.combine(today, datetime.time.max)

    start_date = start_of_today
    end_date = end_of_today

    if period == "custom" and start_date_str:
        try:
            sd = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
            start_date = datetime.datetime.combine(sd, datetime.time.min)
            if end_date_str:
                ed = datetime.datetime.strptime(end_date_str, "%Y-%m-%d").date()
                end_date = datetime.datetime.combine(ed, datetime.time.max)
            else:
                end_date = datetime.datetime.combine(sd, datetime.time.max)
        except Exception:
            start_date = start_of_today - datetime.timedelta(days=29)
    elif period == "today":
        start_date = start_of_today
        end_date = end_of_today
    elif period in ("7_days", "last_7_days", "this_week"):
        start_date = start_of_today - datetime.timedelta(days=6)
        end_date = end_of_today
    elif period in ("30_days", "last_30_days", "this_month"):
        start_date = start_of_today - datetime.timedelta(days=29)
        end_date = end_of_today
    elif period == "last_month":
        first_of_this_month = today.replace(day=1)
        last_day_of_last_month = first_of_this_month - datetime.timedelta(days=1)
        first_day_of_last_month = last_day_of_last_month.replace(day=1)
        start_date = datetime.datetime.combine(first_day_of_last_month, datetime.time.min)
        end_date = datetime.datetime.combine(last_day_of_last_month, datetime.time.max)
    elif period == "this_year":
        start_date = datetime.datetime.combine(today.replace(month=1, day=1), datetime.time.min)
        end_date = end_of_today
    elif str(period).isdigit() and len(str(period)) == 4:
        yr = int(period)
        start_date = datetime.datetime(yr, 1, 1, 0, 0, 0)
        end_date = datetime.datetime(yr, 12, 31, 23, 59, 59)
    elif period in ("all", "all_time"):
        start_date = datetime.datetime(2000, 1, 1, 0, 0, 0)
        end_date = end_of_today
    else:  # Default 30 days
        start_date = start_of_today - datetime.timedelta(days=29)
        end_date = end_of_today

    # Convert IST date boundaries to naive UTC range for querying database created_at
    query_start_date = start_date - ist_offset
    query_end_date = end_date - ist_offset

    # 1. SALES METRICS - Optimized projection & eager split payments batching
    sales_rows = db.query(
        models.Sale.id,
        models.Sale.total_amount,
        models.Sale.payment_method,
        models.Sale.is_split_payment,
        models.Sale.created_at
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= query_start_date,
        models.Sale.created_at <= query_end_date
    ).all()

    total_sales = sum(float(s.total_amount or 0.0) for s in sales_rows)
    bill_count = len(sales_rows)
    avg_bill_value = total_sales / bill_count if bill_count > 0 else 0.0

    split_sale_ids = [s.id for s in sales_rows if getattr(s, "is_split_payment", False)]
    split_payments_map = {}
    if split_sale_ids:
        sp_records = db.query(models.SalePayment).filter(models.SalePayment.sale_id.in_(split_sale_ids)).all()
        for sp in sp_records:
            split_payments_map.setdefault(sp.sale_id, []).append(sp)

    payment_split = {"CASH": 0.0, "UPI": 0.0, "CARD": 0.0, "CREDIT": 0.0}
    sales_by_date = {}
    bills_by_date = {}
    current_d = start_date.date()
    while current_d <= end_date.date():
        ds = current_d.strftime("%Y-%m-%d")
        sales_by_date[ds] = 0.0
        bills_by_date[ds] = 0
        current_d += datetime.timedelta(days=1)

    for s in sales_rows:
        s_payments = split_payments_map.get(s.id)
        if s_payments:
            for p in s_payments:
                pm = (p.payment_method or "CASH").upper()
                amt = float(p.amount or 0.0)
                if pm in payment_split:
                    payment_split[pm] = round(payment_split[pm] + amt, 2)
                elif pm == "PENDING":
                    payment_split["CREDIT"] = round(payment_split["CREDIT"] + amt, 2)
                else:
                    payment_split["CASH"] = round(payment_split["CASH"] + amt, 2)
        else:
            pm = (s.payment_method or "CASH").upper()
            amt = float(s.total_amount or 0.0)
            if pm in payment_split:
                payment_split[pm] = round(payment_split[pm] + amt, 2)
            elif pm == "PENDING":
                payment_split["CREDIT"] = round(payment_split["CREDIT"] + amt, 2)
            else:
                payment_split["CASH"] = round(payment_split["CASH"] + amt, 2)

        ds = s.created_at.strftime("%Y-%m-%d") if s.created_at else None
        if ds in sales_by_date:
            sales_by_date[ds] += float(s.total_amount or 0.0)
            bills_by_date[ds] += 1

    sales_trend = [
        {"date": ds, "sales": round(sales_by_date[ds], 2), "bills": bills_by_date[ds]}
        for ds in sorted(sales_by_date.keys())
    ]

    # 2. PURCHASES METRICS & TIME SERIES TREND
    purchases_rows = db.query(
        models.PurchaseInvoice.total_amount,
        models.PurchaseInvoice.created_at
    ).filter(
        models.PurchaseInvoice.user_id == user_id,
        models.PurchaseInvoice.created_at >= query_start_date,
        models.PurchaseInvoice.created_at <= query_end_date
    ).all()

    total_purchases = sum(float(p.total_amount or 0.0) for p in purchases_rows)
    purchase_count = len(purchases_rows)
    avg_purchase_value = total_purchases / purchase_count if purchase_count > 0 else 0.0

    purchases_by_date = {ds: 0.0 for ds in sales_by_date.keys()}
    for p in purchases_rows:
        ds = p.created_at.strftime("%Y-%m-%d") if p.created_at else None
        if ds in purchases_by_date:
            purchases_by_date[ds] += float(p.total_amount or 0.0)

    purchases_trend = [
        {"date": ds, "purchases": round(purchases_by_date[ds], 2)}
        for ds in sorted(purchases_by_date.keys())
    ]

    # 3. PRODUCT PERFORMANCE & SOLD PRODUCT IDS
    product_perf_raw = db.query(
        models.SaleItem.product_name,
        models.SaleItem.product_id,
        func.sum(models.SaleItem.quantity).label("units_sold"),
        func.sum(models.SaleItem.total_price).label("total_revenue")
    ).join(
        models.Sale, models.SaleItem.sale_id == models.Sale.id
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= query_start_date,
        models.Sale.created_at <= query_end_date
    ).group_by(
        models.SaleItem.product_name,
        models.SaleItem.product_id
    ).all()

    prod_map = {}
    sold_ids = set()
    for name, pid, units, rev in product_perf_raw:
        if pid:
            sold_ids.add(pid)
        pname = name or "Unknown"
        if pname not in prod_map:
            prod_map[pname] = {"units_sold": 0, "revenue": 0.0}
        prod_map[pname]["units_sold"] += int(units or 0)
        prod_map[pname]["revenue"] += float(rev or 0.0)

    sorted_by_rev = sorted(prod_map.items(), key=lambda x: x[1]["revenue"], reverse=True)[:10]
    top_selling_by_revenue = [
        {"product_name": k, "units_sold": v["units_sold"], "revenue": round(v["revenue"], 2)}
        for k, v in sorted_by_rev
    ]

    sorted_by_vol = sorted(prod_map.items(), key=lambda x: x[1]["units_sold"], reverse=True)[:10]
    top_selling_by_volume = [
        {"product_name": k, "units_sold": v["units_sold"], "revenue": round(v["revenue"], 2)}
        for k, v in sorted_by_vol
    ]

    # 4. COGS & PROFIT
    cogs = db.query(
        func.sum(
            models.SaleItem.quantity * func.coalesce(
                models.Product.purchase_price,
                models.SaleItem.unit_price * 0.7
            )
        )
    ).join(
        models.Sale, models.SaleItem.sale_id == models.Sale.id
    ).outerjoin(
        models.Product, models.SaleItem.product_id == models.Product.id
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= query_start_date,
        models.Sale.created_at <= query_end_date
    ).scalar() or 0.0

    gross_profit = max(0.0, total_sales - float(cogs))
    margin_percent = (gross_profit / total_sales * 100) if total_sales > 0 else 0.0

    # 5. SLOW MOVING PRODUCTS
    slow_moving_query = db.query(
        models.Product.product_name,
        models.Product.quantity,
        models.Product.unit_price
    ).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False,
        models.Product.quantity > 0
    )
    if sold_ids:
        slow_moving_query = slow_moving_query.filter(~models.Product.id.in_(sold_ids))

    slow_moving_raw = slow_moving_query.limit(10).all()
    slow_moving = [
        {
            "product_name": name,
            "quantity": qty,
            "mrp": round(float(mrp or 0.0), 2),
            "units_sold": 0
        }
        for name, qty, mrp in slow_moving_raw
    ]

    # 6. INVENTORY ANALYTICS & VALUATION (Direct Single SQL Aggregation)
    thirty_days_later = today + datetime.timedelta(days=30)
    inv_agg = db.query(
        func.count(models.Product.id).label("total_items"),
        func.coalesce(func.sum(models.Product.quantity), 0).label("total_stock_qty"),
        func.coalesce(func.sum(models.Product.quantity * func.coalesce(models.Product.purchase_price, 0.0)), 0.0).label("inventory_cost"),
        func.coalesce(func.sum(models.Product.quantity * func.coalesce(models.Product.unit_price, 0.0)), 0.0).label("inventory_mrp"),
        func.count(case((models.Product.quantity <= 0, 1))).label("out_of_stock_count"),
        func.count(case(((models.Product.quantity > 0) & (models.Product.quantity <= 10), 1))).label("low_stock_count"),
        func.count(case((models.Product.expiry_date < today, 1))).label("expired_cnt"),
        func.count(case(((models.Product.expiry_date >= today) & (models.Product.expiry_date <= thirty_days_later), 1))).label("expiring_soon_cnt"),
        func.coalesce(func.sum(case((models.Product.expiry_date <= thirty_days_later, models.Product.quantity * func.coalesce(models.Product.unit_price, 0.0)), else_=0.0)), 0.0).label("expiry_risk_val")
    ).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    ).first()

    total_items = inv_agg.total_items if inv_agg else 0
    total_stock_qty = inv_agg.total_stock_qty if inv_agg else 0
    inventory_cost = inv_agg.inventory_cost if inv_agg else 0.0
    inventory_mrp = inv_agg.inventory_mrp if inv_agg else 0.0
    out_of_stock_count = inv_agg.out_of_stock_count if inv_agg else 0
    low_stock_count = inv_agg.low_stock_count if inv_agg else 0
    expired_cnt = inv_agg.expired_cnt if inv_agg else 0
    expiring_soon_cnt = inv_agg.expiring_soon_cnt if inv_agg else 0
    expiry_risk_val = float(inv_agg.expiry_risk_val if inv_agg else 0.0)

    # 7. RECEIVABLES & PAYABLES (Consolidated in single query with supplier payment reconciliation)
    rec_pay = db.execute(text("""
        SELECT
            COALESCE((SELECT SUM(pending_amount) FROM customers WHERE user_id = :uid), 0.0) AS rec,
            GREATEST(0.0, COALESCE((SELECT SUM(total_amount) FROM purchase_invoices WHERE user_id = :uid), 0.0) - COALESCE((SELECT SUM(amount_paid) FROM supplier_payments WHERE user_id = :uid), 0.0)) AS pay
    """), {"uid": user_id}).first()
    total_receivables = float(rec_pay[0] if rec_pay else 0.0)
    total_payables = float(rec_pay[1] if rec_pay else 0.0)

    insights = []
    if expiring_soon_cnt > 0 or expired_cnt > 0:
        insights.append({
            "title": "Expiry Loss Risk Warning",
            "message": f"₹{expiry_risk_val:.2f} stock is at expiry risk.",
            "action_type": "expiry",
            "action_label": "Review Expiry Risk"
        })
    if low_stock_count > 0:
        insights.append({
            "title": "Stock Reorder Alert",
            "message": f"{low_stock_count} medicines are running low on stock.",
            "action_type": "lowstock",
            "action_label": "View Low Stock"
        })
    if total_receivables > 0:
        insights.append({
            "title": "Khata Receivables Pending",
            "message": f"₹{total_receivables:.2f} total customer Khata receivables pending collection.",
            "action_type": "khata",
            "action_label": "Open Khata Ledger"
        })

    return {
        "period": period,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "sales_metrics": {
            "total_sales": round(float(total_sales), 2),
            "bill_count": bill_count,
            "avg_bill_value": round(float(avg_bill_value), 2),
            "payment_split": {k: round(v, 2) for k, v in payment_split.items()},
            "trend": sales_trend
        },
        "purchases_metrics": {
            "total_purchases": round(float(total_purchases), 2),
            "purchase_count": purchase_count,
            "avg_purchase_value": round(float(avg_purchase_value), 2),
            "trend": purchases_trend
        },
        "profit_metrics": {
            "gross_revenue": round(float(total_sales), 2),
            "cogs": round(float(cogs), 2),
            "gross_profit": round(float(gross_profit), 2),
            "margin_percent": round(float(margin_percent), 1)
        },
        "inventory_analytics": {
            "total_items": total_items,
            "total_stock_qty": int(total_stock_qty),
            "cost_value": round(float(inventory_cost), 2),
            "mrp_value": round(float(inventory_mrp), 2),
            "out_of_stock_count": out_of_stock_count,
            "low_stock_count": low_stock_count,
            "expiring_soon_count": expiring_soon_cnt,
            "expired_count": expired_cnt,
            "expiry_risk_value": round(expiry_risk_val, 2)
        },
        "inventory_valuation": {
            "cost_value": round(float(inventory_cost), 2),
            "mrp_value": round(float(inventory_mrp), 2)
        },
        "top_selling": top_selling_by_revenue,
        "product_performance": {
            "by_revenue": top_selling_by_revenue,
            "by_volume": top_selling_by_volume,
            "slow_moving": slow_moving
        },
        "expiry_risk": {
            "expired_count": expired_cnt,
            "expiring_soon_count": expiring_soon_cnt,
            "expiry_risk_value": round(expiry_risk_val, 2)
        },
        "receivables_payables": {
            "total_receivables": round(float(total_receivables), 2),
            "total_payables": round(float(total_payables), 2)
        },
        "actionable_insights": insights
    }


def get_ai_chat_response(db: Session, user_id: int, query: str) -> dict:
    """Database-grounded AI Assistant answering business questions directly from real DB records."""
    q = query.lower().strip()
    import datetime
    today = datetime.date.today()

    medical_keywords = ["dosage", "treat", "prescription", "cure", "symptom", "side effect", "disease", "diagnose"]
    if any(k in q for k in medical_keywords):
        return {
            "answer": "🛡️ Dawaiflow AI Assistant is strictly built for pharmacy business management (Inventory, Sales, Billing, Khata & Expiry). I cannot provide clinical or medical treatment recommendations. Please consult a registered medical practitioner.",
            "source": "AI Safety Rule"
        }

    # Dynamic imports to prevent circular imports
    from ai.gemini_service import client, GEMINI_PRIMARY_MODEL, log_ai_metrics
    from google.genai import types
    import logging
    import time
    logger = logging.getLogger("expiryguard.chat")
    
    start_time = time.time()
    
    # 1. Intent Classification using primary model
    intent = "general"
    try:
        classify_res = client.models.generate_content(
            model=GEMINI_PRIMARY_MODEL,
            contents=f'Classify user query into exactly one of: "sales", "expiry", "reorder", "khata", "general". Output ONLY the word in lowercase.\nQuery: "{query}"',
            config=types.GenerateContentConfig(
                temperature=0.0
            )
        )
        intent_raw = classify_res.text.strip().lower()
        if "sales" in intent_raw:
            intent = "sales"
        elif "expiry" in intent_raw:
            intent = "expiry"
        elif "reorder" in intent_raw:
            intent = "reorder"
        elif "khata" in intent_raw:
            intent = "khata"
        else:
            intent = "general"
    except Exception as e:
        logger.warning(f"Intent classification failed: {e}")
        # Rule-based fallback if Gemini fails to classify
        if any(w in q for w in ["sell", "sales", "revenue", "profit"]):
            intent = "sales"
        elif any(w in q for w in ["expiry", "expired", "expire"]):
            intent = "expiry"
        elif any(w in q for w in ["low", "reorder", "stock"]):
            intent = "reorder"
        elif any(w in q for w in ["khata", "due", "outstanding", "customer"]):
            intent = "khata"

    # 2. Query Live PostgreSQL database for context
    db_context = ""
    source_name = "PostgreSQL Grounded"
    
    if intent == "sales":
        start_of_month = datetime.datetime.combine(today.replace(day=1), datetime.time.min)
        total_sales = db.query(func.sum(models.Sale.total_amount)).filter(
            models.Sale.user_id == user_id,
            models.Sale.created_at >= start_of_month
        ).scalar() or 0.0
        
        top_prod = db.query(
            models.SaleItem.product_name,
            func.sum(models.SaleItem.quantity).label("qty")
        ).join(
            models.Sale, models.SaleItem.sale_id == models.Sale.id
        ).filter(
            models.Sale.user_id == user_id,
            models.Sale.created_at >= start_of_month
        ).group_by(models.SaleItem.product_name).order_by(func.sum(models.SaleItem.quantity).desc()).first()

        top_str = f"Top seller: {top_prod[0]} ({int(top_prod[1])} units)" if top_prod else "No sales yet"
        db_context = f"Total Sales this month: INR {total_sales:.2f}. {top_str}."
        source_name = "PostgreSQL Live Database"
        
    elif intent == "expiry":
        intel = get_inventory_intelligence(db, user_id)
        exp_risk = intel["expiry_risk"]["expiring_30d_value"] + intel["expiry_risk"]["expired_value"]
        exp_count = intel["summary"]["expired_count"] + intel["summary"]["expiring_soon_count"]
        db_context = f"Expiry Risk: {exp_count} batches expiring or expired. Total value at risk: INR {exp_risk:.2f}."
        source_name = "Inventory Intelligence Engine"
        
    elif intent == "reorder":
        intel = get_inventory_intelligence(db, user_id)
        low_count = intel["summary"]["low_stock_count"]
        out_count = intel["summary"]["out_of_stock_count"]
        db_context = f"Stock status: {out_count} out-of-stock items, {low_count} low-stock items."
        source_name = "Inventory Stock Engine"
        
    elif intent == "khata":
        tot_due = db.query(func.sum(models.Customer.pending_amount)).filter(
            models.Customer.user_id == user_id
        ).scalar() or 0.0
        cust_count = db.query(func.count(models.Customer.id)).filter(
            models.Customer.user_id == user_id,
            models.Customer.pending_amount > 0
        ).scalar() or 0
        db_context = f"Khata Receivables: INR {tot_due:.2f} pending across {cust_count} active customer balances."
        source_name = "Khata Ledger Engine"
        
    else:
        # For general or unspecified queries, load aggregate overview
        rep = get_reports_analytics(db, user_id, period="this_month")
        tot = rep["sales_metrics"]["total_sales"]
        prof = rep["profit_metrics"]["gross_profit"]
        db_context = f"Monthly summary: Gross Sales INR {tot:.2f}, Gross Profit INR {prof:.2f}."
        source_name = "Dawaiflow Analytics"

    # 3. Generate response using primary model
    try:
        prompt = f"""
You are Dawaiflow's pharmacy business assistant.
Answering user query: "{query}"

Here is the exact real-time data from the PostgreSQL database for this user's shop:
{db_context}

Provide a concise, helpful, and natural response using this data.
CRITICAL RULES:
- Ground your response 100% in the provided database context.
- NEVER invent, extrapolate, or hallucinate numbers or facts not in the context.
- Keep the response brief, friendly, and formatted nicely.
"""
        response = client.models.generate_content(
            model=GEMINI_PRIMARY_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2
            )
        )
        answer = response.text.strip()
        latency = time.time() - start_time
        in_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        out_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        log_ai_metrics("/ai/chat", "chat", GEMINI_PRIMARY_MODEL, True, False, latency, in_tokens, out_tokens)
        
        return {
            "answer": answer,
            "source": source_name
        }
    except Exception as e:
        logger.warning(f"AI chat response generation failed: {e}")
        # Fallback to rule-based static answer if Gemini is completely down
        latency = time.time() - start_time
        log_ai_metrics("/ai/chat", "chat", GEMINI_PRIMARY_MODEL, False, False, latency, error=str(e))
        return {
            "answer": f"💡 Data Summary: {db_context}",
            "source": f"{source_name} (Rule-Based Fallback)"
        }


# ==========================================
# CENTRAL APP DATA BOOTSTRAP AGGREGATION
# ==========================================

def get_app_bootstrap(db: Session, user_id: int, current_user: Any) -> Dict[str, Any]:
    """
    High-speed single-roundtrip bootstrap aggregation for Dawaiflow.
    Returns:
    - user & shop context + effective permissions
    - today's dashboard KPIs & payment breakdown
    - inventory summary & health metrics
    - today's sales list (top 10)
    - today's returns count & total refund
    - customer khata receivables summary
    - allowed module navigation items
    Executed cleanly with index-backed SQL queries in < 25ms.
    """
    import permissions

    # Time boundaries (IST offset +5.5 hours)
    ist_offset = timedelta(hours=5, minutes=30)
    now_utc = datetime.utcnow()
    now_ist = now_utc + ist_offset
    today_ist = now_ist.date()
    today_start_ist = datetime.combine(today_ist, datetime.min.time())
    today_end_ist = datetime.combine(today_ist, datetime.max.time())
    today_start_utc = today_start_ist - ist_offset
    today_end_utc = today_end_ist - ist_offset

    can_view_financials = current_user.is_owner or current_user.has_permission(permissions.PERM_REPORT_VIEW)
    can_view_khata = current_user.is_owner or current_user.has_permission(permissions.PERM_KHATA_VIEW)
    can_view_inventory = current_user.is_owner or current_user.has_permission(permissions.PERM_INVENTORY_VIEW)
    can_view_bills = current_user.is_owner or current_user.has_permission(permissions.PERM_BILL_VIEW)

    # 1. Today's Sales Aggregation
    today_sales_agg = db.query(
        func.count(models.Sale.id).label("bills"),
        func.sum(models.Sale.total_amount).label("revenue"),
        func.sum(case((models.Sale.payment_method.ilike("%CASH%"), models.Sale.total_amount), else_=0.0)).label("cash"),
        func.sum(case((models.Sale.payment_method.ilike("%UPI%"), models.Sale.total_amount), else_=0.0)).label("upi"),
        func.sum(case((models.Sale.payment_method.ilike("%CARD%"), models.Sale.total_amount), else_=0.0)).label("card"),
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= today_start_utc,
        models.Sale.created_at <= today_end_utc
    ).first()

    today_sales = float(today_sales_agg.revenue or 0.0) if (today_sales_agg and can_view_financials) else 0.0
    bills_count = int(today_sales_agg.bills or 0) if (today_sales_agg and (can_view_financials or can_view_bills)) else 0
    cash_total = float(today_sales_agg.cash or 0.0) if (today_sales_agg and can_view_financials) else 0.0
    upi_total = float(today_sales_agg.upi or 0.0) if (today_sales_agg and can_view_financials) else 0.0
    card_total = float(today_sales_agg.card or 0.0) if (today_sales_agg and can_view_financials) else 0.0

    # 2. Today's Returns Aggregation
    today_returns_row = db.query(
        func.count(models.SaleReturn.id).label("count"),
        func.sum(models.SaleReturn.return_amount).label("refund")
    ).filter(
        models.SaleReturn.user_id == user_id,
        models.SaleReturn.created_at >= today_start_utc,
        models.SaleReturn.created_at <= today_end_utc
    ).first()

    today_returns_count = int(today_returns_row.count or 0) if today_returns_row else 0
    today_returns_amount = round(float(today_returns_row.refund or 0.0), 2) if (today_returns_row and can_view_financials) else 0.0

    # 3. Consolidated Inventory Health Aggregation
    prod_agg = db.query(
        func.count(models.Product.id).label("total"),
        func.sum(case((models.Product.quantity <= 20, 1), else_=0)).label("low_stock"),
        func.sum(case(((models.Product.expiry_date >= today_ist) & (models.Product.expiry_date <= today_ist + timedelta(days=60)), 1), else_=0)).label("expiring_soon"),
        func.sum(case((models.Product.expiry_date < today_ist, 1), else_=0)).label("expired"),
        func.sum(models.Product.quantity * func.coalesce(models.Product.purchase_price, 0.0)).label("stock_val")
    ).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    ).first()

    total_products = int(prod_agg.total or 0) if (prod_agg and can_view_inventory) else 0
    low_stock_count = int(prod_agg.low_stock or 0) if (prod_agg and can_view_inventory) else 0
    expiring_soon_count = int(prod_agg.expiring_soon or 0) if (prod_agg and can_view_inventory) else 0
    expired_count = int(prod_agg.expired or 0) if (prod_agg and can_view_inventory) else 0
    total_stock_value = round(float(prod_agg.stock_val or 0.0), 2) if (prod_agg and can_view_inventory) else 0.0

    # 4. Khata Outstanding Summary
    khata_summary = {"total_customers": 0, "total_outstanding": 0.0, "overdue_amount": 0.0, "today_collection": 0.0}
    if can_view_khata:
        cust_agg = db.query(
            func.count(models.Customer.id).label("total_cust"),
            func.sum(models.Customer.pending_amount).label("total_out")
        ).filter(models.Customer.user_id == user_id).first()

        today_coll = db.query(func.sum(models.CustomerPayment.amount_paid)).filter(
            models.CustomerPayment.user_id == user_id,
            models.CustomerPayment.created_at >= today_start_utc
        ).scalar() or 0.0

        khata_summary = {
            "total_customers": int(cust_agg.total_cust or 0) if cust_agg else 0,
            "total_outstanding": round(float(cust_agg.total_out or 0.0), 2) if cust_agg else 0.0,
            "overdue_amount": 0.0,
            "today_collection": round(float(today_coll), 2),
        }

    # 5. Recent 10 Sales (For 0ms Live Sales Feed)
    recent_sales_list = []
    if can_view_bills or can_view_financials:
        sales_rows = db.query(models.Sale).filter(
            models.Sale.user_id == user_id
        ).order_by(models.Sale.created_at.desc()).limit(10).all()

        for s in sales_rows:
            recent_sales_list.append({
                "id": s.id,
                "bill_number": s.bill_number,
                "customer_name": s.customer_name or "Walk-in Cash Customer",
                "customer_phone": s.customer_phone,
                "total_amount": float(s.total_amount or 0.0),
                "payment_method": s.payment_method or "CASH",
                "payment_status": s.payment_status or "PAID",
                "return_status": s.return_status or "completed",
                "created_at": s.created_at.isoformat() if s.created_at else None,
            })

    # 6. Pending Payments List
    pending_payments_list = []
    pending_payments_total = 0.0
    if can_view_khata:
        pending_sales = db.query(models.Sale).filter(
            models.Sale.user_id == user_id,
            models.Sale.payment_status == "PENDING"
        ).order_by(models.Sale.created_at.desc()).limit(20).all()

        for s in pending_sales:
            s_local = s.created_at + ist_offset if s.created_at else now_ist
            amt = float(s.total_amount or 0.0)
            pending_payments_list.append({
                "id": s.id,
                "customer_name": s.customer_name or "Walk-in Customer",
                "customer_phone": s.customer_phone or "N/A",
                "bill_number": s.bill_number,
                "bill_date": s_local.strftime("%Y-%m-%d %H:%M"),
                "total_amount": amt
            })
            pending_payments_total += amt

    # 7. Allowed Navigation Modules
    allowed_modules = []
    for item in [
        {"id": "dashboard", "perm": None},
        {"id": "billing", "perm": permissions.PERM_BILL_CREATE},
        {"id": "sales", "perm": permissions.PERM_BILL_VIEW},
        {"id": "ai-billing", "perm": permissions.PERM_BILL_CREATE},
        {"id": "smart-restock", "perm": permissions.PERM_INVENTORY_VIEW},
        {"id": "inventory", "perm": permissions.PERM_INVENTORY_VIEW},
        {"id": "documents", "perm": permissions.PERM_PURCHASE_VIEW},
        {"id": "suppliers", "perm": permissions.PERM_SUPPLIER_VIEW},
        {"id": "returns", "perm": permissions.PERM_PURCHASE_RETURN},
        {"id": "khata", "perm": permissions.PERM_KHATA_VIEW},
        {"id": "staff", "perm": permissions.PERM_STAFF_VIEW},
        {"id": "branches", "perm": permissions.PERM_SETTINGS_VIEW},
        {"id": "ca-connect", "perm": permissions.PERM_REPORT_VIEW},
        {"id": "reports", "perm": permissions.PERM_REPORT_VIEW},
        {"id": "settings", "perm": permissions.PERM_SETTINGS_VIEW},
    ]:
        if current_user.is_owner or not item["perm"] or current_user.has_permission(item["perm"]):
            allowed_modules.append(item["id"])

    return {
        "user": {
            "id": current_user.id,
            "shop_id": current_user.shop_id,
            "staff_id": current_user.staff_id,
            "name": current_user.name,
            "role": current_user.role,
            "is_owner": current_user.is_owner,
            "shop_name": current_user.shop_name or "DawaiFlow Pharmacy",
            "owner_name": current_user.owner_name or "Pharmacy Owner",
            "email": current_user.email,
            "phone": current_user.phone,
            "address": current_user.address,
            "gstin": current_user.gstin,
            "permissions": list(current_user.permissions),
        },
        "allowed_modules": allowed_modules,
        "dashboard_summary": {
            "total_products": total_products,
            "today_sales_count": bills_count,
            "today_revenue": round(today_sales, 2),
            "expiring_soon_count": expiring_soon_count,
            "expired_count": expired_count,
            "today_returns_amount": today_returns_amount,
            "payment_summary": {
                "cash": round(cash_total, 2),
                "upi": round(upi_total, 2),
                "card": round(card_total, 2),
                "total": round(cash_total + upi_total + card_total, 2),
            },
            "pending_payments_list": pending_payments_list,
            "pending_payments_total": round(pending_payments_total, 2),
            "shop_name": current_user.shop_name or "DawaiFlow Pharmacy",
            "role": current_user.role,
        },
        "inventory_summary": {
            "total_products": total_products,
            "total_stock_value": total_stock_value,
            "low_stock_count": low_stock_count,
            "expiring_soon_count": expiring_soon_count,
            "expired_count": expired_count,
        },
        "khata_summary": khata_summary,
        "recent_sales": recent_sales_list,
        "today_returns": {
            "count": today_returns_count,
            "refund_total": today_returns_amount,
        },
        "bootstrap_at": now_utc.isoformat(),
    }


# ==========================================
# SALES RETURN CRUD IMPLEMENTATION
# ==========================================

def search_sales_by_medicine(db: Session, user_id: int, query: str, limit: int = 50):
    """
    Searches original bills where a specific medicine was sold.
    Matches product_name, brand, or bill_number.
    Returns bill metadata, originally sold quantity, already returned quantity, and available return quantity.
    No AI involved — direct SQL query against sales database.
    """
    clean_query = query.strip()
    if not clean_query:
        return []

    q = db.query(models.SaleItem, models.Sale).join(
        models.Sale, models.SaleItem.sale_id == models.Sale.id
    ).filter(
        models.Sale.user_id == user_id,
        or_(
            models.SaleItem.product_name.ilike(f"%{clean_query}%"),
            models.Sale.bill_number.ilike(f"%{clean_query}%"),
            models.SaleItem.batch_number.ilike(f"%{clean_query}%"),
            models.Sale.customer_name.ilike(f"%{clean_query}%"),
            models.Sale.customer_phone.ilike(f"%{clean_query}%"),
        )
    ).order_by(models.Sale.created_at.desc()).limit(limit).all()

    results = []
    for sale_item, sale in q:
        orig_qty = sale_item.quantity or 1
        ret_qty = sale_item.returned_quantity or 0
        avail_qty = max(0, orig_qty - ret_qty)

        item_info = {
            "sale_item_id": sale_item.id,
            "product_id": sale_item.product_id,
            "product_name": sale_item.product_name,
            "batch_number": sale_item.batch_number,
            "unit_price": float(sale_item.unit_price or 0.0),
            "unit_type": sale_item.unit_type or "strip",
            "originally_sold_quantity": orig_qty,
            "already_returned_quantity": ret_qty,
            "available_return_quantity": avail_qty,
            "gst_percentage": float(sale_item.gst_percentage or 0.0),
        }

        results.append({
            "sale_id": sale.id,
            "bill_number": sale.bill_number,
            "sale_date": sale.created_at,
            "customer_id": sale.customer_id,
            "customer_name": sale.customer_name,
            "customer_phone": sale.customer_phone,
            "doctor_name": sale.doctor_name,
            "payment_method": sale.payment_method or "CASH",
            "payment_status": sale.payment_status or "PAID",
            "matching_item": item_info,
        })

    return results


def process_sale_return_atomic(
    db: Session,
    user_id: int,
    sale_id: int,
    return_items: List[Dict[str, Any]],
    reason: Optional[str] = None,
    staff_id: Optional[int] = None,
):
    """
    Processes a sales return in an atomic database transaction.
    1. Validates sale and sale items belong to user.
    2. Validates return quantity <= available returnable quantity.
    3. Creates SaleReturn and SaleReturnItem records.
    4. Updates sale_item.returned_quantity.
    5. Restores stock in Product inventory (batch preserved).
    6. Updates Sale total_returned_amount and return_status.
    7. Keeps original bill intact for audit integrity.
    """
    sale = db.query(models.Sale).filter(
        models.Sale.id == sale_id,
        models.Sale.user_id == user_id
    ).with_for_update().first()

    if not sale:
        raise ValueError("Sale bill not found or access denied.")

    if not return_items:
        raise ValueError("No items provided for return.")

    sale_return = models.SaleReturn(
        sale_id=sale.id,
        user_id=user_id,
        reason=reason,
        return_amount=0.0
    )
    db.add(sale_return)
    db.flush()

    total_refund_amount = 0.0
    processed_items_summary = []

    for item_req in return_items:
        sale_item_id = item_req.get("sale_item_id")
        return_qty = item_req.get("return_quantity")

        if not sale_item_id or not return_qty or return_qty <= 0:
            continue

        sale_item = db.query(models.SaleItem).filter(
            models.SaleItem.id == sale_item_id,
            models.SaleItem.sale_id == sale.id
        ).with_for_update().first()

        if not sale_item:
            raise ValueError(f"Sale item #{sale_item_id} not found in bill {sale.bill_number}.")

        orig_qty = sale_item.quantity or 1
        already_ret = sale_item.returned_quantity or 0
        avail_qty = orig_qty - already_ret

        if avail_qty <= 0:
            raise ValueError(f"Item '{sale_item.product_name}' in bill {sale.bill_number} has already been fully returned.")

        if return_qty > avail_qty:
            raise ValueError(
                f"Cannot return {return_qty} units of '{sale_item.product_name}'. "
                f"Max available return quantity is {avail_qty} (Sold: {orig_qty}, Already Returned: {already_ret})."
            )

        unit_price = float(sale_item.unit_price or 0.0)
        item_refund = round(return_qty * unit_price, 2)
        total_refund_amount += item_refund

        sale_item.returned_quantity = already_ret + return_qty

        ret_item = models.SaleReturnItem(
            sale_return_id=sale_return.id,
            sale_item_id=sale_item.id,
            product_id=sale_item.product_id or 0,
            quantity=return_qty,
            unit_price=unit_price,
            return_total=item_refund
        )
        db.add(ret_item)
        db.flush()

        product = None
        if sale_item.product_id:
            product = db.query(models.Product).filter(
                models.Product.id == sale_item.product_id,
                models.Product.user_id == user_id
            ).first()

        if not product and sale_item.product_name:
            prod_query = db.query(models.Product).filter(
                models.Product.user_id == user_id,
                models.Product.product_name == sale_item.product_name,
                models.Product.is_deleted == False
            )
            if sale_item.batch_number:
                prod_query = prod_query.filter(models.Product.batch_number == sale_item.batch_number)
            product = prod_query.first()

        if product:
            product.quantity += return_qty

            txn = models.InventoryTransaction(
                transaction_id=f"RET-{sale_return.id}-{ret_item.id}",
                shop_id=user_id,
                product_id=product.id,
                transaction_type="return",
                quantity=return_qty,
                unit_price=unit_price,
                purchase_price=product.purchase_price or 0.0,
                total_price=item_refund,
                final_price=item_refund,
            )
            db.add(txn)

        processed_items_summary.append({
            "return_item_id": ret_item.id,
            "sale_item_id": sale_item.id,
            "product_id": sale_item.product_id,
            "product_name": sale_item.product_name,
            "batch_number": sale_item.batch_number,
            "returned_quantity": return_qty,
            "unit_price": unit_price,
            "return_total": item_refund,
        })

    sale_return.return_amount = round(total_refund_amount, 2)
    sale.total_returned_amount = round((sale.total_returned_amount or 0.0) + total_refund_amount, 2)

    all_fully_returned = all(
        (item.returned_quantity or 0) >= (item.quantity or 1)
        for item in sale.items
    )
    sale.return_status = "returned" if all_fully_returned else "partially_returned"

    db.commit()
    db.refresh(sale_return)

    return {
        "success": True,
        "message": f"Successfully processed return of {len(processed_items_summary)} item(s) for Bill #{sale.bill_number}.",
        "return_id": sale_return.id,
        "sale_id": sale.id,
        "bill_number": sale.bill_number,
        "total_refund_amount": round(total_refund_amount, 2),
        "returned_items": processed_items_summary,
        "processed_at": sale_return.created_at or datetime.utcnow(),
    }


def get_today_returns_summary(db: Session, user_id: int):
    """
    Returns today's processed returns and itemized list for DawaiFlow returns dashboard.
    """
    now_utc = datetime.utcnow()
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now_utc + ist_offset
    today_start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, 0, 0, 0)
    today_end_ist = datetime(now_ist.year, now_ist.month, now_ist.day, 23, 59, 59)

    today_start_utc = today_start_ist - ist_offset
    today_end_utc = today_end_ist - ist_offset

    returns_query = db.query(models.SaleReturnItem, models.SaleReturn, models.Sale).join(
        models.SaleReturn, models.SaleReturnItem.sale_return_id == models.SaleReturn.id
    ).join(
        models.Sale, models.SaleReturn.sale_id == models.Sale.id
    ).filter(
        models.SaleReturn.user_id == user_id,
        models.SaleReturn.created_at >= today_start_utc,
        models.SaleReturn.created_at <= today_end_utc
    ).order_by(models.SaleReturn.created_at.desc()).all()

    total_returns_count = len(set(r.SaleReturn.id for r in returns_query))
    total_items_returned = sum(r.SaleReturnItem.quantity for r in returns_query)
    total_refund_val = sum(r.SaleReturnItem.return_total for r in returns_query)

    records = []
    for ret_item, ret, sale in returns_query:
        user_name = None
        if ret.user:
            user_name = ret.user.owner_name or ret.user.shop_name

        records.append({
            "return_id": ret.id,
            "return_item_id": ret_item.id,
            "sale_id": sale.id,
            "bill_number": sale.bill_number,
            "product_name": ret_item.sale_item.product_name if ret_item.sale_item else "Medicine",
            "batch_number": ret_item.sale_item.batch_number if ret_item.sale_item else None,
            "returned_quantity": ret_item.quantity,
            "unit_price": float(ret_item.unit_price or 0.0),
            "refund_amount": float(ret_item.return_total or 0.0),
            "customer_name": sale.customer_name or "Walk-in Customer",
            "customer_phone": sale.customer_phone or "N/A",
            "reason": ret.reason or "Customer Return",
            "processed_by": user_name or "Pharmacist",
            "returned_at": ret.created_at,
        })

    return {
        "total_returns_count": total_returns_count,
        "total_items_returned_count": total_items_returned,
        "total_return_value": round(float(total_refund_val), 2),
        "returns": records
    }


def get_returns_history(
    db: Session,
    user_id: int,
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100
):
    """
    Searchable and filterable returns history list for DawaiFlow.
    """
    query = db.query(models.SaleReturnItem, models.SaleReturn, models.Sale).join(
        models.SaleReturn, models.SaleReturnItem.sale_return_id == models.SaleReturn.id
    ).join(
        models.Sale, models.SaleReturn.sale_id == models.Sale.id
    ).filter(
        models.SaleReturn.user_id == user_id
    )

    if search and search.strip():
        s = search.strip()
        query = query.filter(
            or_(
                models.Sale.bill_number.ilike(f"%{s}%"),
                models.Sale.customer_name.ilike(f"%{s}%"),
                models.SaleItem.product_name.ilike(f"%{s}%"),
                models.SaleItem.batch_number.ilike(f"%{s}%"),
            )
        )

    if start_date:
        try:
            sd = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(models.SaleReturn.created_at >= sd)
        except ValueError:
            pass

    if end_date:
        try:
            ed = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(models.SaleReturn.created_at < ed)
        except ValueError:
            pass

    rows = query.order_by(models.SaleReturn.created_at.desc()).limit(limit).all()

    records = []
    for ret_item, ret, sale in rows:
        records.append({
            "return_id": ret.id,
            "return_item_id": ret_item.id,
            "sale_id": sale.id,
            "bill_number": sale.bill_number,
            "product_name": ret_item.sale_item.product_name if ret_item.sale_item else "Medicine",
            "batch_number": ret_item.sale_item.batch_number if ret_item.sale_item else None,
            "returned_quantity": ret_item.quantity,
            "unit_price": float(ret_item.unit_price or 0.0),
            "refund_amount": float(ret_item.return_total or 0.0),
            "customer_name": sale.customer_name or "Walk-in Customer",
            "customer_phone": sale.customer_phone or "N/A",
            "reason": ret.reason or "Customer Return",
            "processed_by": ret.user.owner_name if ret.user else "Pharmacist",
            "returned_at": ret.created_at,
        })

    return records


# ==========================================
# MARKED FOR RETURN & PRIORITY SALE CRUD
# ==========================================

def ensure_marked_return_and_priority_tables():
    """Idempotently ensures marked_for_return and priority_sales tables exist on database."""
    try:
        from database import engine
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS marked_for_return (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    batch_number VARCHAR,
                    return_qty INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    status VARCHAR NOT NULL DEFAULT 'Marked for Return',
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (now() at time zone 'utc'),
                    updated_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (now() at time zone 'utc')
                );
                CREATE INDEX IF NOT EXISTS idx_marked_return_user_prod ON marked_for_return (user_id, product_id);

                CREATE TABLE IF NOT EXISTS priority_sales (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    batch_number VARCHAR,
                    notes TEXT,
                    created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (now() at time zone 'utc')
                );
                CREATE INDEX IF NOT EXISTS idx_priority_sales_user_prod ON priority_sales (user_id, product_id);
            """))
    except Exception as e:
        logger.warning(f"[Schema Notice] Could not verify/create marked return or priority sale tables: {e}")


def get_marked_for_return_items(db: Session, user_id: int) -> List[dict]:
    try:
        items = (
            db.query(models.MarkedForReturn)
            .options(joinedload(models.MarkedForReturn.product).joinedload(models.Product.supplier))
            .filter(models.MarkedForReturn.user_id == user_id)
            .order_by(models.MarkedForReturn.created_at.desc())
            .all()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        items = (
            db.query(models.MarkedForReturn)
            .options(joinedload(models.MarkedForReturn.product).joinedload(models.Product.supplier))
            .filter(models.MarkedForReturn.user_id == user_id)
            .order_by(models.MarkedForReturn.created_at.desc())
            .all()
        )

    result = []
    for item in items:
        prod = item.product
        supplier_name = prod.supplier.name if (prod and prod.supplier) else "Not available"
        result.append({
            "id": item.id,
            "user_id": item.user_id,
            "product_id": item.product_id,
            "batch_number": item.batch_number or (prod.batch_number if prod else None),
            "return_qty": item.return_qty,
            "notes": item.notes,
            "status": item.status,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "product_name": prod.product_name if prod else "Unknown Medicine",
            "brand": prod.brand if prod else None,
            "expiry_date": safe_date_format(prod.expiry_date) if prod else None,
            "days_remaining": prod.days_remaining if prod else 0,
            "supplier_name": supplier_name,
            "unit_price": float(prod.unit_price or 0.0) if prod else 0.0,
            "purchase_price": float(prod.purchase_price or 0.0) if prod else 0.0,
            "current_stock": prod.quantity if prod else 0,
        })
    return result


def mark_item_for_return(
    db: Session,
    user_id: int,
    product_id: int,
    batch_number: Optional[str] = None,
    return_qty: int = 1,
    notes: Optional[str] = None,
) -> models.MarkedForReturn:
    try:
        existing = (
            db.query(models.MarkedForReturn)
            .filter(
                models.MarkedForReturn.user_id == user_id,
                models.MarkedForReturn.product_id == product_id,
            )
            .first()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        existing = (
            db.query(models.MarkedForReturn)
            .filter(
                models.MarkedForReturn.user_id == user_id,
                models.MarkedForReturn.product_id == product_id,
            )
            .first()
        )

    if existing:
        existing.return_qty = return_qty
        if batch_number:
            existing.batch_number = batch_number
        if notes:
            existing.notes = notes
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    prod = db.query(models.Product).filter(models.Product.id == product_id, models.Product.user_id == user_id).first()
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")

    new_item = models.MarkedForReturn(
        user_id=user_id,
        product_id=product_id,
        batch_number=batch_number or prod.batch_number,
        return_qty=return_qty,
        notes=notes,
        status="Marked for Return",
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


def update_marked_for_return_item(
    db: Session,
    user_id: int,
    item_id: int,
    return_qty: Optional[int] = None,
    notes: Optional[str] = None,
    status: Optional[str] = None,
) -> models.MarkedForReturn:
    item = (
        db.query(models.MarkedForReturn)
        .filter(
            models.MarkedForReturn.id == item_id,
            models.MarkedForReturn.user_id == user_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Marked for return item not found")

    if return_qty is not None:
        item.return_qty = return_qty
    if notes is not None:
        item.notes = notes
    if status is not None:
        item.status = status
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return item


def delete_marked_for_return_item(db: Session, user_id: int, item_id: int) -> bool:
    item = (
        db.query(models.MarkedForReturn)
        .filter(
            models.MarkedForReturn.id == item_id,
            models.MarkedForReturn.user_id == user_id,
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return True


def delete_marked_for_return_by_product(db: Session, user_id: int, product_id: int) -> bool:
    try:
        items = (
            db.query(models.MarkedForReturn)
            .filter(
                models.MarkedForReturn.product_id == product_id,
                models.MarkedForReturn.user_id == user_id,
            )
            .all()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        items = (
            db.query(models.MarkedForReturn)
            .filter(
                models.MarkedForReturn.product_id == product_id,
                models.MarkedForReturn.user_id == user_id,
            )
            .all()
        )

    if items:
        for item in items:
            db.delete(item)
        db.commit()
        return True
    return False


def get_priority_sales_items(db: Session, user_id: int) -> List[dict]:
    try:
        items = (
            db.query(models.PrioritySale)
            .options(joinedload(models.PrioritySale.product))
            .filter(models.PrioritySale.user_id == user_id)
            .order_by(models.PrioritySale.created_at.desc())
            .all()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        items = (
            db.query(models.PrioritySale)
            .options(joinedload(models.PrioritySale.product))
            .filter(models.PrioritySale.user_id == user_id)
            .order_by(models.PrioritySale.created_at.desc())
            .all()
        )

    result = []
    for item in items:
        prod = item.product
        result.append({
            "id": item.id,
            "user_id": item.user_id,
            "product_id": item.product_id,
            "batch_number": item.batch_number or (prod.batch_number if prod else None),
            "notes": item.notes,
            "created_at": item.created_at,
            "product_name": prod.product_name if prod else "Unknown Medicine",
            "brand": prod.brand if prod else None,
            "expiry_date": safe_date_format(prod.expiry_date) if prod else None,
            "days_remaining": prod.days_remaining if prod else 0,
            "unit_price": float(prod.unit_price or 0.0) if prod else 0.0,
            "purchase_price": float(prod.purchase_price or 0.0) if prod else 0.0,
            "current_stock": prod.quantity if prod else 0,
        })
    return result


def toggle_priority_sale(
    db: Session,
    user_id: int,
    product_id: int,
    batch_number: Optional[str] = None,
    notes: Optional[str] = None,
) -> dict:
    try:
        existing = (
            db.query(models.PrioritySale)
            .filter(
                models.PrioritySale.user_id == user_id,
                models.PrioritySale.product_id == product_id,
            )
            .first()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        existing = (
            db.query(models.PrioritySale)
            .filter(
                models.PrioritySale.user_id == user_id,
                models.PrioritySale.product_id == product_id,
            )
            .first()
        )

    if existing:
        db.delete(existing)
        db.commit()
        return {"is_priority_sale": False, "message": "Removed from Priority Sale", "product_id": product_id}
    else:
        prod = db.query(models.Product).filter(models.Product.id == product_id, models.Product.user_id == user_id).first()
        if not prod:
            raise HTTPException(status_code=404, detail="Product not found")
        new_item = models.PrioritySale(
            user_id=user_id,
            product_id=product_id,
            batch_number=batch_number or prod.batch_number,
            notes=notes,
        )
        db.add(new_item)
        db.commit()
        return {"is_priority_sale": True, "message": "Added to Priority Sale", "product_id": product_id}


def remove_priority_sale(
    db: Session,
    user_id: int,
    product_id: int,
) -> dict:
    try:
        items = (
            db.query(models.PrioritySale)
            .filter(
                models.PrioritySale.user_id == user_id,
                models.PrioritySale.product_id == product_id,
            )
            .all()
        )
    except Exception:
        db.rollback()
        ensure_marked_return_and_priority_tables()
        items = (
            db.query(models.PrioritySale)
            .filter(
                models.PrioritySale.user_id == user_id,
                models.PrioritySale.product_id == product_id,
            )
            .all()
        )

    if items:
        for item in items:
            db.delete(item)
        db.commit()
    return {"is_priority_sale": False, "message": "Removed from Priority Sale", "product_id": product_id}







