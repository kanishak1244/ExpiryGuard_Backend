"""
Routes restored from app.py as it was before the modularisation refactor (commit 526c298), which dropped them.
Only routes that the web app, Flutter app or desktop print agent still call are restored, with the same paths,
schemas and behaviour as before. Helpers they need are copied from the same old app.py; shared auth, database,
cache and rate-limit objects are imported from dependencies (not duplicated).
"""

import os
import io
import re
import json
import time
import uuid
import logging
import mimetypes
from difflib import SequenceMatcher
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set, Union
from datetime import datetime, timedelta, date

import bcrypt
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Response, status, BackgroundTasks, Query, WebSocket, WebSocketDisconnect, Body
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from sqlalchemy import text, func, case, or_, and_, select
from slowapi import Limiter
from slowapi.util import get_remote_address

import models
import schemas
import crud
import permissions
from database import SessionLocal
from crypto_utils import encrypt_staff_password, decrypt_staff_password
from services import import_service, backup_service, migration_service
from dependencies import (
    ALGORITHM,
    AuthenticatedUser,
    SECRET_KEY,
    _AUTH_CACHE,
    FastCacheManager,
    fast_cache,
    get_current_user,
    get_db,
    limiter,
    require_permission,
    safe_hash_password,
)

logger = logging.getLogger("expiryguard.routes.restored")

router = APIRouter(tags=["Restored routes"])

BASE_DIR = Path(__file__).resolve().parent.parent  # repository root (this file lives in routes/)


ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}


ALLOWED_SPREADSHEET_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
}


MAX_FILE_SIZE_10MB = 10 * 1024 * 1024


MAX_FILE_SIZE_5MB = 5 * 1024 * 1024


MAX_IMAGE_PIXELS = 50_000_000


def check_file_size(file: UploadFile, max_size: int = MAX_FILE_SIZE_10MB):
    """Safely determines uploaded file size without loading contents fully into RAM or writing fully to disk."""
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed limit of {max_size // (1024 * 1024)} MB."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Could not validate upload file size: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Could not validate upload file size."
        )


def validate_file_content_and_magic(file_bytes: bytes, ext: str):
    """Validates file magic byte signatures and protects against decompression bombs or script uploads."""
    ext = ext.lower()
    FORBIDDEN_EXTENSIONS = {".exe", ".sh", ".bat", ".php", ".py", ".js", ".html", ".htm", ".svg", ".dll", ".so", ".cmd", ".vbs", ".ps1"}
    if ext in FORBIDDEN_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension '{ext}' is forbidden for security reasons.")

    if ext in [".jpg", ".jpeg"]:
        if not file_bytes.startswith(b"\xFF\xD8\xFF"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid JPEG image file signature.")
    elif ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid PNG image file signature.")
    elif ext == ".webp":
        if not (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]):
            raise HTTPException(status_code=400, detail="Corrupted or invalid WEBP image file signature.")
    elif ext == ".pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid PDF document file signature.")
    elif ext == ".xlsx":
        if not (file_bytes.startswith(b"PK\x03\x04") or file_bytes.startswith(b"PK\x05\x06")):
            raise HTTPException(status_code=400, detail="Corrupted or invalid Excel spreadsheet file signature.")
    elif ext == ".xls":
        if not (file_bytes.startswith(b"\xD0\xCF\x11\xE0") or file_bytes.startswith(b"PK\x03\x04")):
            raise HTTPException(status_code=400, detail="Corrupted or invalid legacy Excel file signature.")
    elif ext == ".csv":
        if b"\x00" in file_bytes[:1024]:
            raise HTTPException(status_code=400, detail="Binary data not allowed in CSV spreadsheet.")

    # Image pixel resolution & integrity check (Decompression Bomb & Corruption Protection)
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
            img = Image.open(io.BytesIO(file_bytes))
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Image dimensions ({width}x{height}) exceed maximum allowed resolution limits."
                )
        except HTTPException:
            raise
        except Exception as img_err:
            logger.warning(f"PIL Image verification error: {img_err}")
            raise HTTPException(status_code=400, detail="Corrupted or malformed image file content.")


security = HTTPBearer(auto_error=False)


def require_owner(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Dependency that strictly enforces that the user is the Pharmacy Shop Owner."""
    if not current_user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: This operation is restricted exclusively to the pharmacy shop owner.",
        )
    return current_user


@router.get("/dashboard")
def dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    products = crud.get_products(db, current_user.id)
    total = len(products)
    safe, expiring, expired = 0, 0, 0

    for product in products:
        if product.status == "Safe":
            safe += 1
        elif product.status == "Expiring Soon":
            expiring += 1
        elif product.status == "Expired":
            expired += 1

    return {
        "total": total,
        "safe": safe,
        "expiring": expiring,
        "expired": expired,
    }


@router.get("/hsn/lookup", response_model=schemas.HsnLookupResponse)
def lookup_hsn_gst_rate(
    hsn_code: str,
    product_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Looks up official GST rate for an HSN code. Logs unmapped HSN codes for admin review."""
    return crud.get_hsn_gst_rate(db=db, hsn_code=hsn_code, product_name=product_name, user_id=current_user.id)


@router.get("/hsn/rates", response_model=List[schemas.HsnTaxRateResponse])
def get_hsn_rates(
    db: Session = Depends(get_db),
):
    """Returns all registered HSN-to-GST rate mappings."""
    return crud.get_all_hsn_rates(db)


@router.post("/hsn/rates", response_model=schemas.HsnTaxRateResponse, status_code=201)
def add_or_update_hsn_rate(
    hsn_data: schemas.HsnTaxRateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Add or update an HSN code GST rate mapping in the reference table."""
    return crud.create_hsn_rate(db=db, hsn_data=hsn_data)


@router.get("/hsn/unmapped-logs", response_model=List[schemas.UnmappedHsnLogResponse])
def get_unmapped_hsn_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists unmapped HSN codes flagged during billing/inventory entry."""
    return crud.get_unmapped_hsn_logs(db=db, limit=limit)


@router.get("/user/profile", response_model=schemas.User)
def get_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Fetches full profile, pharmacy information & settings for logged-in user or staff."""
    user_dict = {
        col.name: getattr(current_user._user, col.name)
        for col in current_user._user.__table__.columns
    }
    user_dict["staff_id"] = current_user.staff_id
    user_dict["role"] = current_user.role
    user_dict["name"] = current_user.name
    user_dict["is_owner"] = current_user.is_owner
    user_dict["permissions"] = list(current_user.permissions)
    return user_dict


@router.put("/user/profile", response_model=schemas.User)
def update_user_profile(
    data: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Updates pharmacy details, preferences, theme, language, and notification settings."""
    if not current_user.is_owner and not current_user.has_permission(permissions.PERM_SETTINGS_EDIT):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: Only pharmacy owners or authorized managers can update store profile."
        )
    updated_user = crud.update_user_profile(db=db, user_id=current_user.id, data=data)
    # Refresh cached sessions for this pharmacy so the new profile is used immediately.
    for _k in [k for k in list(_AUTH_CACHE.keys()) if str(k).startswith(f"u:{current_user.id}:")]:
        _AUTH_CACHE.pop(_k, None)
    fast_cache.invalidate_user(current_user.id)
    user_dict = {
        col.name: getattr(updated_user, col.name)
        for col in updated_user.__table__.columns
    }
    user_dict["staff_id"] = current_user.staff_id
    user_dict["role"] = current_user.role
    user_dict["name"] = current_user.name
    user_dict["is_owner"] = current_user.is_owner
    user_dict["permissions"] = list(current_user.permissions)
    return user_dict


@router.post("/user/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    req: schemas.PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Secured endpoint to change account password."""
    return crud.change_user_password(db=db, user_id=current_user.id, req=req)


def _parse_gst_period_dates(period_str: Optional[str] = None):
    from datetime import datetime
    import calendar
    now = datetime.utcnow()

    if not period_str:
        start_dt = datetime(now.year, now.month, 1, 0, 0, 0)
        _, last_day = calendar.monthrange(now.year, now.month)
        end_dt = datetime(now.year, now.month, last_day, 23, 59, 59)
        period_label = now.strftime("%B %Y")
        period_code = now.strftime("%Y-%m")
        return start_dt, end_dt, period_label, period_code

    p_str = period_str.strip()
    try:
        if "-Q" in p_str:
            parts = p_str.split("-Q")
            year = int(parts[0])
            quarter = int(parts[1])
            q_start_month = 3 * (quarter - 1) + 1
            q_end_month = q_start_month + 2
            start_dt = datetime(year, q_start_month, 1, 0, 0, 0)
            _, last_day = calendar.monthrange(year, q_end_month)
            end_dt = datetime(year, q_end_month, last_day, 23, 59, 59)
            return start_dt, end_dt, f"Q{quarter} {year}", p_str
        elif "-" in p_str:
            parts = p_str.split("-")
            year = int(parts[0])
            month = int(parts[1])
            start_dt = datetime(year, month, 1, 0, 0, 0)
            _, last_day = calendar.monthrange(year, month)
            end_dt = datetime(year, month, last_day, 23, 59, 59)
            dt_obj = datetime(year, month, 1)
            return start_dt, end_dt, dt_obj.strftime("%B %Y"), p_str
    except Exception:
        pass

    start_dt = datetime(now.year, now.month, 1, 0, 0, 0)
    _, last_day = calendar.monthrange(now.year, now.month)
    end_dt = datetime(now.year, now.month, last_day, 23, 59, 59)
    return start_dt, end_dt, now.strftime("%B %Y"), now.strftime("%Y-%m")


@router.get("/api/gst/gstr1-summary")
def get_gstr1_summary(
    period: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns detailed GSTR-1 breakdown (B2B, B2C, HSN summary, Output Tax)."""
    from sqlalchemy.orm import selectinload

    start_dt, end_dt, period_label, period_code = _parse_gst_period_dates(period)

    sales = (
        db.query(models.Sale)
        .options(selectinload(models.Sale.items))
        .filter(
            models.Sale.user_id == current_user.id,
            models.Sale.created_at >= start_dt,
            models.Sale.created_at <= end_dt,
        )
        .order_by(models.Sale.created_at.desc())
        .all()
    )

    b2b_sales = []
    b2c_taxable = 0.0
    b2c_cgst = 0.0
    b2c_sgst = 0.0
    b2c_igst = 0.0
    b2c_total_tax = 0.0
    b2c_total_amount = 0.0
    b2c_count = 0

    hsn_dict = {}

    for s in sales:
        has_gstin = bool(s.gst_number and s.gst_number.strip() and s.gst_number != "07AABCE1234F1Z5")
        is_b2b_bill = has_gstin or (s.customer_name and "b2b" in s.customer_name.lower())

        s_taxable = round(s.total_taxable_value or s.subtotal, 2)
        s_cgst = round(s.total_cgst, 2)
        s_sgst = round(s.total_sgst, 2)
        s_igst = round(s.total_igst, 2)
        s_tax = round(s.tax_amount, 2)
        s_total = round(s.total_amount, 2)

        if is_b2b_bill:
            b2b_sales.append({
                "bill_number": s.bill_number,
                "date": s.created_at.strftime("%Y-%m-%d") if s.created_at else "",
                "customer_name": s.customer_name or "B2B Client",
                "gstin": s.gst_number or "N/A",
                "taxable_value": s_taxable,
                "cgst": s_cgst,
                "sgst": s_sgst,
                "igst": s_igst,
                "total_tax": s_tax,
                "total_amount": s_total,
            })
        else:
            b2c_count += 1
            b2c_taxable += s_taxable
            b2c_cgst += s_cgst
            b2c_sgst += s_sgst
            b2c_igst += s_igst
            b2c_total_tax += s_tax
            b2c_total_amount += s_total

        # HSN breakdown from sale items
        for item in s.items:
            hsn = getattr(item, 'hsn_code', None) or "3004"
            rate = float(getattr(item, 'gst_percentage', None) or getattr(item, 'gst_rate', None) or s.gst_percentage or 12.0)
            item_taxable = float(getattr(item, 'line_total', None) or (item.quantity * item.unit_price))
            item_tax = float(getattr(item, 'taxable_value', None) or (item_taxable * rate / 100.0))

            if hsn not in hsn_dict:
                hsn_dict[hsn] = {
                    "hsn_code": hsn,
                    "description": "Medicines / Pharma Supplies",
                    "gst_rate": rate,
                    "total_quantity": 0,
                    "taxable_value": 0.0,
                    "gst_amount": 0.0,
                }
            hsn_dict[hsn]["total_quantity"] += item.quantity
            hsn_dict[hsn]["taxable_value"] += item_taxable
            hsn_dict[hsn]["gst_amount"] += item_tax

    # Format HSN summary list
    hsn_summary = [
        {
            "hsn_code": k,
            "description": v["description"],
            "gst_rate": round(v["gst_rate"], 1),
            "total_quantity": v["total_quantity"],
            "taxable_value": round(v["taxable_value"], 2),
            "gst_amount": round(v["gst_amount"], 2),
        }
        for k, v in hsn_dict.items()
    ]

    total_taxable = round(sum(s.total_taxable_value or s.subtotal for s in sales), 2)
    total_cgst = round(sum(s.total_cgst for s in sales), 2)
    total_sgst = round(sum(s.total_sgst for s in sales), 2)
    total_igst = round(sum(s.total_igst for s in sales), 2)
    total_tax = round(sum(s.tax_amount for s in sales), 2)

    return {
        "period": period_code,
        "period_label": period_label,
        "gstin": getattr(current_user, "gstin", None) or current_user.gst_number or "07AABCE1234F1Z5",
        "pharmacy_name": current_user.shop_name or "Pharmacy",
        "totals": {
            "total_invoices": len(sales),
            "b2b_count": len(b2b_sales),
            "b2c_count": b2c_count,
            "taxable_value": total_taxable,
            "cgst": total_cgst,
            "sgst": total_sgst,
            "igst": total_igst,
            "total_output_tax": total_tax,
        },
        "b2b_sales": b2b_sales,
        "b2c_summary": {
            "count": b2c_count,
            "taxable_value": round(b2c_taxable, 2),
            "cgst": round(b2c_cgst, 2),
            "sgst": round(b2c_sgst, 2),
            "igst": round(b2c_igst, 2),
            "total_tax": round(b2c_total_tax, 2),
            "total_amount": round(b2c_total_amount, 2),
        },
        "hsn_summary": hsn_summary,
    }


@router.get("/api/gst/gstr3b-summary")
def get_gstr3b_summary(
    period: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns detailed GSTR-3B tax computation summary (3.1 Outward, 4 ITC, 5 Net Tax)."""
    from sqlalchemy.orm import selectinload

    start_dt, end_dt, period_label, period_code = _parse_gst_period_dates(period)

    sales = (
        db.query(models.Sale)
        .filter(
            models.Sale.user_id == current_user.id,
            models.Sale.created_at >= start_dt,
            models.Sale.created_at <= end_dt,
        )
        .all()
    )

    purchases = (
        db.query(models.PurchaseInvoice)
        .filter(
            models.PurchaseInvoice.user_id == current_user.id,
            models.PurchaseInvoice.created_at >= start_dt,
            models.PurchaseInvoice.created_at <= end_dt,
        )
        .all()
    )

    outward_taxable = sum(s.total_taxable_value or s.subtotal for s in sales)
    outward_cgst = sum(s.total_cgst for s in sales)
    outward_sgst = sum(s.total_sgst for s in sales)
    outward_igst = sum(s.total_igst for s in sales)
    outward_tax = sum(s.tax_amount for s in sales)

    itc_taxable = sum(p.subtotal for p in purchases)
    itc_total_tax = sum(p.tax_amount for p in purchases)
    itc_igst = sum(p.tax_amount if getattr(p, 'is_interstate', False) else 0.0 for p in purchases)
    itc_cgst = (itc_total_tax - itc_igst) / 2.0
    itc_sgst = (itc_total_tax - itc_igst) / 2.0

    net_cgst = max(0.0, outward_cgst - itc_cgst)
    net_sgst = max(0.0, outward_sgst - itc_sgst)
    net_igst = max(0.0, outward_igst - itc_igst)
    net_total = max(0.0, outward_tax - itc_total_tax)

    return {
        "period": period_code,
        "period_label": period_label,
        "gstin": getattr(current_user, "gstin", None) or current_user.gst_number or "07AABCE1234F1Z5",
        "pharmacy_name": current_user.shop_name or "Pharmacy",
        "section_3_1_outward_supplies": {
            "taxable_value": round(outward_taxable, 2),
            "cgst": round(outward_cgst, 2),
            "sgst": round(outward_sgst, 2),
            "igst": round(outward_igst, 2),
            "total_tax": round(outward_tax, 2),
        },
        "section_4_eligible_itc": {
            "purchase_subtotal": round(itc_taxable, 2),
            "cgst": round(itc_cgst, 2),
            "sgst": round(itc_sgst, 2),
            "igst": round(itc_igst, 2),
            "total_itc": round(itc_total_tax, 2),
        },
        "section_5_net_liability": {
            "cgst_payable": round(net_cgst, 2),
            "sgst_payable": round(net_sgst, 2),
            "igst_payable": round(net_igst, 2),
            "total_net_payable": round(net_total, 2),
        }
    }


@router.get("/reports/export/sales")
def export_sales_csv(
    re_export: bool = False,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
):
    """Exports sales transactions & bills to CSV format and marks them exported once generation succeeds."""
    import csv
    import io

    query = db.query(models.Sale).filter(models.Sale.user_id == current_user.id)
    if not re_export:
        query = query.filter(models.Sale.is_exported == False)

    sales = query.order_by(models.Sale.created_at.desc()).all()
    exported_count = len(sales)
    
    # 1. Generate CSV content in memory safely
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill Number", "Date", "Customer Name", "Customer Phone", "Payment Method", "Taxable Amount (INR)", "Tax Amount (INR)", "Grand Total (INR)", "Status"])
    
    for s in sales:
        writer.writerow([
            s.bill_number,
            s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else "",
            s.customer_name or "N/A",
            s.customer_phone or "N/A",
            s.payment_method or "CASH",
            f"{s.total_taxable_value:.2f}",
            f"{s.tax_amount:.2f}",
            f"{s.total_amount:.2f}",
            s.return_status or "completed"
        ])
    
    csv_content = output.getvalue()
    output.close()

    # 2. Only after CSV content is generated completely and successfully, mark these exact bills as exported
    if sales:
        sale_ids = [s.id for s in sales]
        now_dt = datetime.utcnow()
        # Batch update in DB
        db.query(models.Sale).filter(
            models.Sale.id.in_(sale_ids),
            models.Sale.user_id == current_user.id
        ).update(
            {
                models.Sale.is_exported: True,
                models.Sale.exported_at: now_dt
            },
            synchronize_session=False
        )
        db.commit()

        # Invalidate sales cache for current user so live sales feed immediately excludes them
        fast_cache.invalidate_user(current_user.id, tag="sales")

    headers = {
        "Content-Disposition": "attachment; filename=dawaiflow_sales_export.csv",
        "X-Exported-Count": str(exported_count),
        "Access-Control-Expose-Headers": "X-Exported-Count, Content-Disposition"
    }
    return Response(content=csv_content, media_type="text/csv", headers=headers)


@router.get("/api/sales/search-by-medicine")
def search_sales_by_medicine_endpoint(
    query: str = Query(..., min_length=1, description="Medicine name, barcode, or bill number"),
    limit: int = 50,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.search_sales_by_medicine(db=db, user_id=current_user.id, query=query, limit=limit)


@router.post("/api/sales/returns", response_model=schemas.ProcessReturnResponse)
def process_sale_return_endpoint(
    req: schemas.ProcessReturnRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return_items_data = [item.dict() for item in req.items]
        res = crud.process_sale_return_atomic(
            db=db,
            user_id=current_user.id,
            sale_id=req.sale_id,
            return_items=return_items_data,
            reason=req.reason,
            staff_id=getattr(current_user, "staff_id", None)
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process return: {str(e)}")


@router.get("/api/sales/returns")
def get_returns_history_endpoint(
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_returns_history(
        db=db,
        user_id=current_user.id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@router.get("/reports/export/inventory")
def export_inventory_csv(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
):
    """Exports active shop inventory to CSV format."""
    import csv
    import io

    products = db.query(models.Product).filter(models.Product.user_id == current_user.id).order_by(models.Product.product_name.asc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Product Name", "Brand", "Category", "Batch Number", "Quantity", "Purchase Price (INR)", "Selling Price (INR)", "Per-Pill Price (INR)", "HSN Code", "GST Rate (%)", "Expiry Date", "Status"])
    
    for p in products:
        writer.writerow([
            p.product_name,
            p.brand or "",
            p.category or "allopathy",
            p.batch_number or "",
            p.quantity,
            f"{p.purchase_price:.2f}",
            f"{p.unit_price:.2f}",
            f"{p.price_per_unit:.2f}" if p.price_per_unit else "N/A",
            p.hsn_code or "3004",
            p.gst_rate or 12.0,
            p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else "",
            p.status or "Safe"
        ])
    
    output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=dawaiflow_inventory_export.csv"})


class GmailOAuthConnectRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = "http://localhost:8000/ca-connect/gmail/callback"
    refresh_token: Optional[str] = None
    google_email: Optional[str] = None


@router.post("/ca-connect/gmail/connect")
def connect_gmail_oauth(
    req: GmailOAuthConnectRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Exchanges Google OAuth code or saves refresh token securely for the authenticated shop (Owner only)."""
    from services.google_gmail_service import encrypt_token, get_google_oauth_credentials, get_google_user_email
    import os
    import requests

    refresh_tok = req.refresh_token
    user_gmail = req.google_email

    if not refresh_tok and req.code:
        # Exchange authorization code for tokens
        client_id = os.getenv("GOOGLE_CLIENT_ID", "mock-client-id")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "mock-client-secret")

        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": req.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": req.redirect_uri or "http://localhost:8000/ca-connect/gmail/callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        )

        if token_resp.status_code == 200:
            token_data = token_resp.json()
            refresh_tok = token_data.get("refresh_token")
            access_tok = token_data.get("access_token")

            if access_tok and not user_gmail:
                # Fetch google user email from token
                uinfo = requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_tok}"},
                    timeout=10,
                )
                if uinfo.status_code == 200:
                    user_gmail = uinfo.json().get("email")

    # If mock/testing mode where code is provided as direct refresh token string
    if not refresh_tok and req.code and "1//" in req.code:
        refresh_tok = req.code

    if not refresh_tok:
        # Allow dev/testing fallback if explicit code passed in test suite
        refresh_tok = req.code or f"mock_refresh_token_{current_user.shop_id}"

    if not user_gmail or not user_gmail.strip():
        user_gmail = current_user.email or f"shopkeeper_{current_user.shop_id}@gmail.com"

    user_gmail = user_gmail.strip().lower()
    enc_token = encrypt_token(refresh_tok)

    existing = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.shop_id).first()
    if existing:
        existing.google_email = user_gmail
        existing.encrypted_refresh_token = enc_token
        existing.updated_at = datetime.utcnow()
    else:
        existing = models.UserGoogleOAuth(
            user_id=current_user.shop_id,
            google_email=user_gmail,
            encrypted_refresh_token=enc_token,
            scopes="https://www.googleapis.com/auth/gmail.send"
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)

    return {
        "success": True,
        "connected": True,
        "google_email": user_gmail,
        "message": f"Gmail connected successfully. Connected account: {user_gmail}"
    }


@router.get("/api/inventory/import-template")
@router.get("/inventory/import-template")
def download_inventory_import_template(
    current_user: models.User = Depends(get_current_user),
):
    """
    Generates and returns a downloadable, professional-grade .xlsx template
    for bulk inventory onboarding and updates (openpyxl).
    Structured into 'Instructions' (active) and 'Data' sheets with validation rules.
    """
    from services import template_generator
    stream = template_generator.generate_inventory_import_template()
    
    headers = {
        "Content-Disposition": 'attachment; filename="DawaiFlow_Inventory_Import_Template.xlsx"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post("/api/inventory/import")
@router.post("/inventory/import")
async def import_inventory_file(
    file: UploadFile = File(...),
    on_duplicate: str = "merge",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Directly uploads and parses an .xlsx, .xls, or .csv inventory spreadsheet (no AI required),
    bulk-importing all valid medicine batches directly into the authenticated shop's inventory.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    check_file_size(file)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return crud.import_inventory_from_file(
        db=db,
        user_id=current_user.id,
        file_bytes=file_bytes,
        filename=file.filename,
        on_duplicate=on_duplicate,
    )


@router.get("/suppliers/{supplier_id}/purchases", response_model=List[schemas.DocumentResponse])
def get_supplier_purchases(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    """Get purchase invoices associated with supplier."""
    return crud.get_supplier_purchases(db=db, supplier_id=supplier_id, user_id=current_user.id)


@router.get("/suppliers/{supplier_id}/inventory", response_model=List[schemas.Product])
def get_supplier_inventory(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    return crud.get_supplier_inventory(db=db, supplier_id=supplier_id, user_id=current_user.id)


@router.post("/suppliers/{supplier_id}/payments", response_model=schemas.SupplierPaymentResponse, status_code=201)
def pay_supplier_invoice(
    supplier_id: int,
    payment: schemas.SupplierPaymentCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_EDIT)),
    db: Session = Depends(get_db),
):
    """Log a payment made to wholesale distributor."""
    if payment.supplier_id != supplier_id:
        raise HTTPException(status_code=400, detail="Supplier ID mismatch.")
    return crud.create_supplier_payment(db=db, obj_in=payment, user_id=current_user.id)


@router.get("/suppliers/{supplier_id}/payments", response_model=List[schemas.SupplierPaymentResponse])
def get_supplier_payment_history(
    supplier_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
    db: Session = Depends(get_db),
):
    """Get history of payments made to a wholesale distributor."""
    return crud.get_supplier_payments(db=db, supplier_id=supplier_id, user_id=current_user.id)


@router.get("/purchases/{purchase_id}", response_model=schemas.PurchaseInvoiceResponse)
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
):
    """Retrieve detailed items of a single purchase invoice."""
    db_invoice = crud.get_purchase_invoice(db=db, purchase_id=purchase_id, user_id=current_user.id)
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Purchase invoice not found.")
    return db_invoice


@router.post("/purchases/returns", response_model=schemas.PurchaseReturnResponse, status_code=201)
def create_purchase_return(
    ret_in: schemas.PurchaseReturnCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_RETURN)),
):
    """Process return of products to wholesale supplier and decrement stock."""
    return crud.create_purchase_return(db=db, obj_in=ret_in, user_id=current_user.id)


@router.get("/purchases/returns", response_model=List[schemas.PurchaseReturnResponse])
def list_purchase_returns(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
):
    """Retrieve history of registered purchase returns."""
    return crud.get_purchase_returns(db=db, user_id=current_user.id, skip=skip, limit=limit)


@router.post("/sales/{sale_id}/settle")
@router.put("/sales/{sale_id}/settle")
@router.patch("/sales/{sale_id}/settle")
def settle_pending_sale(
    sale_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marks a pending payment sale as settled/cleared and zeroes out/reduces customer pending balance."""
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == sale_id, models.Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale bill not found.")

    sale.payment_status = "PAID"
    if sale.customer_id:
        db.query(models.Customer).filter(
            models.Customer.id == sale.customer_id,
            models.Customer.user_id == current_user.id
        ).update(
            {models.Customer.pending_amount: func.greatest(0.0, models.Customer.pending_amount - sale.total_amount)},
            synchronize_session=False
        )

    db.commit()
    return {
        "success": True,
        "message": f"Bill {sale.bill_number} marked as settled.",
        "sale_id": sale.id,
        "payment_status": "PAID"
    }


@router.post("/api/inventory/delete")
@router.post("/api/inventory/delete-stock")
@router.post("/inventory/delete")
@router.post("/inventory/delete-stock")
@limiter.limit("60/minute")
def delete_inventory_stock(
    request: Request,
    payload: schemas.InventoryDeleteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Selective soft-delete for inventory stock items.
    Marks rows as deleted with a 60-day recovery window.
    """
    ids = payload.get_ids()
    if not ids:
        raise HTTPException(status_code=400, detail="No stock IDs provided for deletion.")
    res = crud.soft_delete_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@router.post("/api/inventory/delete-all")
@router.post("/inventory/delete-all")
@limiter.limit("60/minute")
def delete_all_inventory_stock(
    request: Request,
    payload: Optional[schemas.InventoryDeleteAllRequest] = Body(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bulk soft-delete for all active stock items belonging to the authenticated shop.
    Supports 60-day recovery window.
    """
    res = crud.soft_delete_all_inventory_items(
        db=db,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@router.get("/api/inventory/deleted", response_model=List[schemas.DeletedProductResponse])
@router.get("/inventory/deleted", response_model=List[schemas.DeletedProductResponse])
def get_recently_deleted_stock(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all soft-deleted inventory items within the 60-day recovery window.
    Includes calculated days remaining until permanent deletion.
    """
    return crud.get_recently_deleted_inventory(
        db=db,
        user_id=current_user.id
    )


@router.post("/api/inventory/restore")
@router.post("/api/inventory/restore-stock")
@router.post("/inventory/restore")
@router.post("/inventory/restore-stock")
@limiter.limit("60/minute")
def restore_inventory_stock(
    request: Request,
    payload: schemas.InventoryRestoreRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Restores soft-deleted inventory items back to live stock
    if deleted within the 60-day recovery window.
    """
    ids = payload.get_ids()
    if not ids:
        raise HTTPException(status_code=400, detail="No stock IDs provided for restoration.")
    res = crud.restore_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@router.post("/search-product", response_model=List[schemas.Product])
def search_products(
    query: str, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """Searches products by name or category for the current shop."""
    if not query.strip():
        return []
    
    return db.query(models.Product).filter(
        models.Product.user_id == current_user.id,
        (models.Product.product_name.ilike(f"%{query}%")) | 
        (models.Product.category.ilike(f"%{query}%"))
    ).limit(20).all()


@router.get("/items/search")
def search_items_voice(
    q: str = Query("", description="Query string: medicine name, brand, salt, or HSN code"),
    shop_id: Optional[int] = Query(None, description="Optional shop ID (defaults to current authenticated user)"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Intelligent search endpoint for Voice Billing & POS autocomplete:
    1. Extracts 4-8 digit HSN codes from speech (e.g. 'HSN 300490' or '3004').
    2. Prioritizes exact HSN code match within active shop inventory.
    3. If no HSN found or matched, computes fuzzy similarity against product names,
       brands, and compositions scoped to the user's shop with FEFO ordering.
    """
    raw_query = (q or "").strip()
    if not raw_query:
        return {"query": "", "items": [], "hsn_match": False}

    if shop_id is not None and shop_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot access inventory of another shop.",
        )
    target_user_id = current_user.id

    # 1. Check for 4-8 digit HSN code pattern in speech input
    hsn_matches = re.findall(r"\b\d{4,8}\b", raw_query)
    if hsn_matches:
        for candidate_hsn in hsn_matches:
            hsn_items = (
                db.query(models.Product)
                .filter(
                    models.Product.user_id == target_user_id,
                    models.Product.is_deleted == False,
                    models.Product.hsn_code.ilike(f"%{candidate_hsn}%")
                )
                .order_by(models.Product.expiry_date.asc())
                .limit(limit)
                .all()
            )
            if hsn_items:
                serialized = [crud.serialize_product(item) for item in hsn_items]
                for s in serialized:
                    s["similarity"] = 1.0
                    s["matched_by"] = "hsn"
                return {
                    "query": raw_query,
                    "hsn_code": candidate_hsn,
                    "hsn_match": True,
                    "items": serialized
                }

    # 2. Text / Voice fuzzy & substring search scoped to shop
    clean_q = raw_query.lower()
    clean_no_punct = re.sub(r"[^\w\s]", " ", clean_q).strip()

    # Base query for shop's active inventory
    inventory_items = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == target_user_id,
            models.Product.is_deleted == False
        )
        .order_by(models.Product.expiry_date.asc())
        .all()
    )

    scored_items = []
    for item in inventory_items:
        p_name = (item.product_name or "").lower()
        p_brand = (item.brand or "").lower()
        p_comp = (item.composition or "").lower()
        p_hsn = (item.hsn_code or "").lower()

        # Check exact substring
        if clean_q in p_name or clean_no_punct in p_name:
            score = 1.0 if clean_q == p_name else 0.85
        elif clean_q in p_brand or clean_q in p_comp or clean_q in p_hsn:
            score = 0.75
        else:
            # Fuzzy SequenceMatcher on name and full text
            ratio_name = SequenceMatcher(None, clean_no_punct, p_name).ratio()
            # Also check individual words for multi-word medicine names
            words = p_name.split()
            max_word_ratio = max([SequenceMatcher(None, clean_no_punct, w).ratio() for w in words] or [0.0])
            score = max(ratio_name, max_word_ratio * 0.8)

        if score >= 0.35:
            s_item = crud.serialize_product(item)
            s_item["similarity"] = round(score, 3)
            s_item["matched_by"] = "voice_fuzzy"
            scored_items.append((score, s_item))

    # Sort descending by similarity score, then ascending by expiry (FEFO)
    scored_items.sort(key=lambda x: (-x[0], x[1].get("expiry_date") or "9999-12-31"))
    final_items = [x[1] for x in scored_items[:limit]]

    # If inventory matches are few, complement with medicine catalog
    if len(final_items) < limit:
        remaining = limit - len(final_items)
        existing_names = set(i["product_name"].lower() for i in final_items if i.get("product_name"))
        cat_matches = crud.search_medicine_catalog(db, query=clean_q, limit=remaining)
        for cat in cat_matches:
            if cat.product_name and cat.product_name.lower() in existing_names:
                continue
            cat_score = round(SequenceMatcher(None, clean_no_punct, cat.product_name.lower()).ratio(), 3)
            cat_dict = {
                "id": cat.id + 900000,
                "user_id": target_user_id,
                "product_name": cat.product_name,
                "brand": cat.brand or "General",
                "category": "General",
                "batch_number": "CATALOG-NEW",
                "quantity": 50,
                "hsn_code": cat.hsn_code or "3004",
                "gst_rate": cat.gst_rate or 12.0,
                "gst_percentage": cat.gst_rate or 12.0,
                "purchase_price": (cat.default_price or 50.0) * 0.75,
                "unit_price": cat.default_price or 50.0,
                "price_per_unit": cat.price_per_unit,
                "units_per_pack": cat.tablets_per_strip or 10,
                "tablets_per_strip": cat.tablets_per_strip or 10,
                "loose_tablet_price": cat.price_per_unit or ((cat.default_price or 50.0) / (cat.tablets_per_strip or 10)),
                "total_price": cat.default_price or 50.0,
                "expiry_date": "2028-12-31",
                "days_remaining": 365,
                "status": "Safe",
                "composition": cat.composition or "",
                "similarity": max(cat_score, 0.6),
                "matched_by": "catalog_fuzzy",
                "is_inventory": False
            }
            final_items.append(cat_dict)

    return {
        "query": raw_query,
        "hsn_match": False,
        "items": final_items
    }


@router.post("/transaction/purchase/bulk", status_code=201)
def process_bulk_purchase(
    payload: schemas.BulkPurchaseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Saves reviewed supplier-invoice items to this shop's inventory.

    A product is added to an existing stock row only when product name,
    batch number, and expiry date all match.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items to ingest.")

    # MRP rules (crud.validate_mrp): every line needs its MRP, never the purchase price. All lines are
    # checked before anything is saved.
    line_mrp = []
    for item in payload.items:
        crud.validate_scanned_line_for_save(item.product_name, item.batch_number, item.hsn_code)
        explicit = item.mrp is not None and item.mrp > 0
        line_mrp.append(
            crud.validate_mrp(
                item.mrp if explicit else item.selling_price,
                item.purchase_price,
                name=item.product_name,
                explicit_mrp=explicit,
                confirm_below_cost=item.confirm_mrp_below_cost,
            )
        )

    saved_products = []

    try:
        for item, mrp_value in zip(payload.items, line_mrp):
            existing = (
                db.query(models.Product)
                .filter(
                    models.Product.user_id == current_user.id,
                    models.Product.product_name.ilike(item.product_name.strip()),
                    models.Product.batch_number == item.batch_number,
                    models.Product.expiry_date == item.expiry_date,
                )
                .with_for_update()
                .first()
            )

            if existing:
                # Same product + batch + expiry: increase only that batch stock.
                existing.quantity += item.quantity
                existing.purchase_price = item.purchase_price

                existing.unit_price = mrp_value
                if item.hsn_code:
                    existing.hsn_code = item.hsn_code
                if item.gst_rate is not None:
                    existing.gst_rate = item.gst_rate
                    existing.gst_percentage = item.gst_rate

                existing.total_price = existing.purchase_price * existing.quantity

                if item.brand:
                    existing.brand = item.brand

                if item.category:
                    existing.category = item.category

                # Mark verified by physical AI camera scan
                existing.verified = True
                existing.pack_size_verified = True
                existing.price_last_updated = datetime.utcnow()

                saved_products.append(existing)
                continue

            # A new batch / expiry date gets its own inventory record.
            days_remaining = (item.expiry_date - datetime.utcnow().date()).days

            if days_remaining < 0:
                product_status = "Expired"
            elif days_remaining <= 30:
                product_status = "Expiring Soon"
            else:
                product_status = "Safe"

                        # Save directly into your Product table
            new_product = models.Product(
                user_id=current_user.id,
                product_name=item.product_name.strip(),
                brand=item.brand,
                category=item.category or "AI Scanned",
                batch_number=item.batch_number,
                quantity=item.quantity,
                purchase_price=item.purchase_price,
                unit_price=mrp_value,
                hsn_code=item.hsn_code or "3004",
                gst_rate=item.gst_rate if item.gst_rate is not None else 12.0,
                gst_percentage=item.gst_rate if item.gst_rate is not None else 12.0,
                total_price=item.purchase_price * item.quantity,
                manufacturing_date=item.manufacturing_date,
                expiry_date=item.expiry_date,
                days_remaining=days_remaining,
                status=product_status,
                verified=True,
                pack_size_verified=True,
                price_last_updated=datetime.utcnow(),
            )

            db.add(new_product)
            saved_products.append(new_product)

        db.commit()

        for product in saved_products:
            db.refresh(product)

        return {
            "success": True,
            "message": f"{len(saved_products)} invoice items saved to inventory.",
            "products": [
                {
                    "id": product.id,
                    "product_name": product.product_name,
                    "quantity": product.quantity,
                    "purchase_price": product.purchase_price,
                    "selling_price": product.unit_price,
                    "manufacturing_date": product.manufacturing_date,
                    "expiry_date": product.expiry_date,
                    "status": product.status,
                }
                for product in saved_products
            ],
        }

    except Exception:
        db.rollback()
        raise


@router.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    """Secure image upload endpoint with authentication, MIME validation, and randomized filename."""
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        file_ext = ".jpg"

    check_file_size(file, MAX_FILE_SIZE_10MB)
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(contents, file_ext)

    uploads_dir = Path("uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"img_{uuid.uuid4().hex[:16]}{file_ext}"
    target_path = (uploads_dir / safe_filename).resolve()

    if not target_path.is_relative_to(uploads_dir):
        raise HTTPException(status_code=400, detail="Invalid target file path.")

    with open(target_path, "wb") as buffer:
        buffer.write(contents)

    return {"imagePath": f"uploads/{safe_filename}"}


class TokenRequest(BaseModel):
    token: str


@router.post("/save_token")
def save_token(
    data: TokenRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_token = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.token == data.token)
        .first()
    )

    if existing_token:
        existing_token.user_id = current_user.id
    else:
        existing_user = (
            db.query(models.DeviceToken)
            .filter(models.DeviceToken.user_id == current_user.id)
            .first()
        )
        if existing_user:
            existing_user.token = data.token
        else:
            db.add(models.DeviceToken(user_id=current_user.id, token=data.token))

    db.commit()
    return {"message": "Token saved successfully"}


@router.post("/import/inventory/preview", response_model=schemas.ImportPreviewResponse)
@router.post("/inventory/import-preview", response_model=schemas.ImportPreviewResponse)
async def preview_inventory_import(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user)
):
    """
    Step 1: Upload Excel/CSV inventory file.
    Parses file headers, performs automatic column header mapping detection,
    caches file temporarily, and returns the preview mapping to the user.
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_SPREADSHEET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{file_ext}'. Allowed spreadsheet types: {', '.join(sorted(ALLOWED_SPREADSHEET_EXTENSIONS))}"
        )

    check_file_size(file, MAX_FILE_SIZE_5MB)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(content, file_ext)

    try:
        df = import_service.read_file_to_dataframe(content, file.filename)
        if df.empty:
            raise HTTPException(status_code=400, detail="File contains no rows.")

        file_headers = [str(c).strip() for c in df.columns if str(c).strip()]
        if not file_headers:
            raise HTTPException(status_code=400, detail="File has no valid column headers.")

        detected_mapping, unmapped = import_service.auto_detect_mapping(file_headers)
        preview_id = import_service.save_temp_dataframe(df)

        preview_slice_json = df.head(10).fillna("").to_json(orient="records", date_format="iso")
        preview_slice = json.loads(preview_slice_json)

        return schemas.ImportPreviewResponse(
            preview_id=preview_id,
            filename=file.filename or "uploaded_spreadsheet",
            total_rows=len(df),
            file_headers=file_headers,
            detected_mapping=detected_mapping,
            unmapped_columns=unmapped,
            preview_data=preview_slice,
        )
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Import preview parse error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")


@router.post("/import/inventory/confirm", response_model=schemas.ImportSummaryResponse)
@router.post("/inventory/import-confirm", response_model=schemas.ImportSummaryResponse)
def confirm_inventory_import(
    payload: schemas.ImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Step 2: Confirm or correct the column mapping and execute bulk inventory import.
    Validates each row, skips/updates duplicates, and returns import report summary.
    """
    df = import_service.load_temp_dataframe(payload.preview_id)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="Import preview session expired or not found. Please upload file again.")

    cleaned_rows = []
    errors = []

    records = df.to_dict(orient="records")
    for idx, row in enumerate(records):
        row_num = idx + 1
        cleaned_data, warnings, error_reason = import_service.validate_and_normalize_row(
            row=row,
            mapping=payload.column_mapping,
            row_index=row_num
        )
        if error_reason:
            if len(errors) < 100:
                clean_raw = {k: (str(v) if pd.notna(v) else "") for k, v in row.items()}
                errors.append(schemas.ImportErrorItem(
                    row=row_num,
                    raw_data=clean_raw,
                    reason=error_reason
                ))
        elif cleaned_data:
            cleaned_rows.append((row_num, cleaned_data, warnings))

    import_result = crud.bulk_import_inventory(
        db=db,
        user_id=current_user.id,
        cleaned_rows=cleaned_rows,
        on_duplicate=payload.on_duplicate or "skip"
    )

    import_service.cleanup_temp_cache(payload.preview_id)

    warnings_list = [
        schemas.ImportWarningItem(
            row=w["row"],
            product_name=w["product_name"],
            message=w["message"]
        ) for w in import_result["warnings"]
    ]

    return schemas.ImportSummaryResponse(
        total_rows_processed=len(df),
        rows_imported=import_result["rows_imported"],
        rows_updated=import_result["rows_updated"],
        rows_skipped=import_result["rows_skipped"],
        warnings_count=len(warnings_list),
        errors_count=len(errors),
        warnings=warnings_list,
        errors=errors
    )


def download_inventory_import_template():
    """
    Returns standardized inventory import template file (.xlsx or .csv).
    Allows users to download standard structure before bulk uploading medicines.
    """
    template_path = os.path.join(str(BASE_DIR), "DawaiFlow_Inventory_Import_Template.xlsx")
    if os.path.exists(template_path):
        return FileResponse(
            path=template_path,
            filename="DawaiFlow_Inventory_Import_Template.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    csv_content = (
        "product_name,brand,category,batch_number,expiry_date,quantity,mrp,purchase_price,hsn_code,gst_rate,tablets_per_strip,barcode\n"
        "Dolo 650mg Tablet,Micro Labs,allopathy,B2026-01,2027-12-31,50,30.00,24.00,3004,12.0,15,8901234567890\n"
        "Azithral 500mg Tablet,Alembic,allopathy,AZ-102,2026-10-31,20,120.00,96.00,3004,12.0,5,8902222222222\n"
        "Pan 40mg Tablet,Alkem,allopathy,PN-889,2027-06-30,30,90.00,72.00,3004,12.0,10,8904444444444\n"
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=DawaiFlow_Inventory_Import_Template.csv"}
    )


@router.post("/customers/{customer_id}/payments", response_model=schemas.CustomerPaymentResponse, status_code=201)
def collect_customer_payment(
    customer_id: int,
    payment: schemas.CustomerPaymentCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_PAYMENT)),
    db: Session = Depends(get_db),
):
    """Log credit payment collection from customer (Khata settlement)."""
    if payment.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="Customer ID mismatch.")
    pay = crud.create_customer_payment(db=db, obj_in=payment, user_id=current_user.id)
    fast_cache.invalidate_tag(current_user.id, "customers")
    fast_cache.invalidate_tag(current_user.id, "khata")
    fast_cache.invalidate_tag(current_user.id, "dashboard")
    return pay


@router.get("/customers/{customer_id}/payments", response_model=List[schemas.CustomerPaymentResponse])
def get_customer_payment_history(
    customer_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_VIEW)),
    db: Session = Depends(get_db),
):
    """Get collection history of credit payments for a customer."""
    return crud.get_customer_payments(db=db, customer_id=customer_id, user_id=current_user.id)


@router.post("/billing/returns", response_model=schemas.SaleReturnResponse)
def process_sale_return(
    payload: schemas.SaleReturnCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_BILL_CREATE)),
    db: Session = Depends(get_db),
):
    """
    Feature 4: One-Tap Return processing.
    Restores returned items to inventory, records SaleReturn, and returns prorated refund summary.
    """
    return crud.process_sale_return(db, return_data=payload, user_id=current_user.id)


@router.get("/billing/returns/today", response_model=List[schemas.SaleReturnResponse])
def get_todays_returns_billing(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_BILL_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Feature 4: Retrieve all returns processed today for "Today's Returns" dashboard view.
    """
    returns = crud.get_todays_returns(db, user_id=current_user.id)
    for r in returns:
        if not getattr(r, 'bill_number', None) and r.sale:
            r.bill_number = r.sale.bill_number
    return returns


@router.get("/reports/sales")
@router.get("/reports/summary")
def get_reports_summary(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Web App Reports Summary Endpoint.
    Returns 7-day sales breakdown, top selling items, and expiring stock report.
    """
    user_id = current_user.id
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    # 1. 7-Day Sales Breakdown
    recent_sales = (
        db.query(models.Sale.created_at, models.Sale.total_amount)
        .filter(models.Sale.user_id == user_id, models.Sale.created_at >= seven_days_ago)
        .all()
    )

    daily_map = {}
    for i in range(7):
        day_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_map[day_str] = {"date": day_str, "revenue": 0.0, "count": 0}

    for s_created, s_amount in recent_sales:
        day_str = s_created.strftime("%Y-%m-%d") if isinstance(s_created, datetime) else str(s_created)[:10]
        if day_str in daily_map:
            daily_map[day_str]["revenue"] += (s_amount or 0.0)
            daily_map[day_str]["count"] += 1

    daily_sales = [daily_map[k] for k in sorted(daily_map.keys())]

    # 2. Top Selling Products (Aggregated in SQL)
    top_selling_rows = (
        db.query(
            models.SaleItem.product_name,
            func.sum(models.SaleItem.quantity).label("quantity_sold"),
            func.sum(models.SaleItem.total_price).label("total_revenue")
        )
        .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
        .filter(models.Sale.user_id == user_id)
        .group_by(models.SaleItem.product_name)
        .order_by(func.sum(models.SaleItem.quantity).desc())
        .limit(5)
        .all()
    )

    top_selling = [
        {
            "product_name": r.product_name or "Unknown Medicine",
            "quantity_sold": int(r.quantity_sold or 0),
            "total_revenue": round(float(r.total_revenue or 0.0), 2)
        }
        for r in top_selling_rows
    ]

    # 3. Expiring Products List
    expiring_products = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
            models.Product.days_remaining != None,
            models.Product.days_remaining <= 60,
        )
        .order_by(models.Product.days_remaining.asc())
        .limit(20)
        .all()
    )

    expiring_list = [
        {
            "id": p.id,
            "product_name": p.product_name,
            "batch_number": p.batch_number or "N/A",
            "quantity": p.quantity or 0,
            "expiry_date": str(p.expiry_date) if p.expiry_date else "N/A",
            "days_remaining": p.days_remaining if p.days_remaining is not None else 0,
            "status": p.status or "Safe",
        }
        for p in expiring_products
    ]

    return {
        "daily_sales": daily_sales,
        "top_selling_products": top_selling,
        "expiring_products": expiring_list,
    }


def _serialize_staff_member(staff: models.StaffMember) -> schemas.StaffMemberResponse:
    perms = permissions.get_role_permissions(
        permissions.normalize_role(staff.role),
        staff.permissions_json,
    )
    return schemas.StaffMemberResponse(
        id=staff.id,
        user_id=staff.user_id,
        name=staff.name,
        phone=staff.phone,
        email=staff.email,
        username=staff.username,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
        permissions=list(perms),
        last_login=staff.last_login,
        created_at=staff.created_at,
    )


@router.patch("/staff/{staff_id}/toggle-status", response_model=schemas.StaffMemberResponse)
def toggle_staff_status(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Toggle a staff member's active/inactive status immediately."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    staff.status = "INACTIVE" if (staff.status or "ACTIVE").upper() == "ACTIVE" else "ACTIVE"
    db.commit()
    db.refresh(staff)

    # Invalidate cache so any active session is immediately blocked
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)
    fast_cache.invalidate_tag(current_user.id, "staff")

    return _serialize_staff_member(staff)


@router.post("/staff/{staff_id}/reset-password")
def reset_staff_password(
    staff_id: int,
    req: schemas.StaffPasswordReset,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Reset a staff member's login password."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    new_pwd = req.new_password.strip()
    staff.password = safe_hash_password(new_pwd)
    staff.encrypted_password = encrypt_staff_password(new_pwd)
    db.commit()

    # Invalidate cache
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)

    return {"message": f"Password for '{staff.name}' has been successfully reset."}


@router.get("/staff/{staff_id}/credentials", response_model=schemas.StaffCredentialResponse)
def get_staff_credentials(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve plaintext staff login credentials (OWNER ONLY).
    Strictly accessible ONLY by the authenticated Pharmacy Owner who owns this shop.
    """
    if not current_user.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Only the pharmacy owner can view staff credentials.",
        )

    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    decrypted_pwd = decrypt_staff_password(staff.encrypted_password) if staff.encrypted_password else None

    return schemas.StaffCredentialResponse(
        staff_id=staff.id,
        name=staff.name,
        username=staff.username or "",
        password=decrypted_pwd,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
    )


@router.put("/staff/{staff_id}/credentials", response_model=schemas.StaffCredentialResponse)
def update_staff_credentials(
    staff_id: int,
    req: schemas.StaffCredentialUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update staff username and/or password (OWNER ONLY).
    Strictly accessible ONLY by the authenticated Pharmacy Owner who owns this shop.
    """
    if not current_user.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Only the pharmacy owner can update staff credentials.",
        )

    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Update username if provided
    if req.username is not None:
        new_username = req.username.strip()
        if not new_username:
            raise HTTPException(status_code=400, detail="Username cannot be empty.")
        
        # Check collision only if changed
        if new_username != staff.username:
            existing_user = db.query(models.StaffMember).filter(
                models.StaffMember.username == new_username,
                models.StaffMember.user_id == current_user.id,
                models.StaffMember.id != staff_id,
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail=f"Username '{new_username}' is already in use for this pharmacy. Please choose another.",
                )
            staff.username = new_username

    # Update password if provided
    if req.password is not None:
        new_pwd = req.password.strip()
        if len(new_pwd) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")
        staff.password = safe_hash_password(new_pwd)
        staff.encrypted_password = encrypt_staff_password(new_pwd)

    db.commit()
    db.refresh(staff)

    # Invalidate cache so old session/credentials don't linger
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)

    decrypted_pwd = decrypt_staff_password(staff.encrypted_password) if staff.encrypted_password else None

    return schemas.StaffCredentialResponse(
        staff_id=staff.id,
        name=staff.name,
        username=staff.username or "",
        password=decrypted_pwd,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
    )


@router.patch("/branches/{branch_id}/toggle-status")
def toggle_store_branch_status(
    branch_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """Toggle active/inactive status of a store branch."""
    branch = db.query(models.StoreBranch).filter(
        models.StoreBranch.id == branch_id,
        models.StoreBranch.user_id == current_user.id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Store branch not found")

    new_status = "INACTIVE" if branch.status == "ACTIVE" else "ACTIVE"
    branch.status = new_status
    db.commit()
    db.refresh(branch)
    fast_cache.invalidate_tag(current_user.id, "branches")
    return {"message": f"Branch status changed to {new_status}", "status": new_status}


_EXPIRY_SUMMARY_CACHE = {}


@router.get("/expiry/summary")
def get_smart_expiry_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calculates actionable batch counts, stock values, and item lists across non-overlapping expiry time windows."""
    now_ts = time.time()
    user_cache = _EXPIRY_SUMMARY_CACHE.get(current_user.id)
    if user_cache and (now_ts - user_cache["timestamp"] < 30): # 30 second TTL
        return user_cache["data"]

    from services.notification_service import calculate_expiry_digest_buckets
    res = calculate_expiry_digest_buckets(current_user.id, db, include_items=True)
    summary_data = {
        "expired": {"count": res["buckets"]["expired"]["count"], "stock_value": round(res["buckets"]["expired"]["stock_value"], 2), "items": res["buckets"]["expired"]["items"]},
        "expiring_1m": {"count": res["buckets"]["1m"]["count"], "stock_value": round(res["buckets"]["1m"]["stock_value"], 2), "items": res["buckets"]["1m"]["items"]},
        "expiring_3m": {"count": res["buckets"]["3m"]["count"], "stock_value": round(res["buckets"]["3m"]["stock_value"], 2), "items": res["buckets"]["3m"]["items"]},
        "expiring_6m": {"count": res["buckets"]["6m"]["count"], "stock_value": round(res["buckets"]["6m"]["stock_value"], 2), "items": res["buckets"]["6m"]["items"]},
        "expiring_9m": {"count": res["buckets"]["9m"]["count"], "stock_value": round(res["buckets"]["9m"]["stock_value"], 2), "items": res["buckets"]["9m"]["items"]},
        "total_at_risk_value": res["total_at_risk_value"],
        "total_at_risk_count": res["total_at_risk_count"],
        "notification_preview": {
            "title": res["notification_title"],
            "body": res["notification_body"],
        }
    }
    _EXPIRY_SUMMARY_CACHE[current_user.id] = {"timestamp": now_ts, "data": summary_data}
    return summary_data


@router.get("/expiry/items")
def get_smart_expiry_items(
    range_type: str = "1m", # expired, 1m, 3m, 6m, 9m
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves batch-level expiry item details for a specific non-overlapping bucket."""
    from services.notification_service import calculate_expiry_digest_buckets
    res = calculate_expiry_digest_buckets(current_user.id, db, include_items=True)
    
    key_map = {
        "expired": "expired",
        "1m": "1m",
        "7d": "1m",
        "30d": "1m",
        "3m": "3m",
        "60d": "3m",
        "90d": "3m",
        "6m": "6m",
        "9m": "9m",
    }
    target_key = key_map.get(range_type, "1m")
    items = res["buckets"].get(target_key, {}).get("items", [])
    items.sort(key=lambda x: x["days_remaining"])
    return items


@router.get("/notifications/settings")
def get_notification_settings_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetches user notification preferences including Expiry Review Digest options."""
    settings = db.query(models.NotificationSettings).filter(
        models.NotificationSettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = models.NotificationSettings(
            user_id=current_user.id,
            enabled=True,
            digest_enabled=True,
            digest_days="Tuesday,Friday",
            digest_time="09:00",
            reminder_frequency="twice_weekly",
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "enabled": settings.enabled,
        "digest_enabled": getattr(settings, 'digest_enabled', True),
        "digest_days": getattr(settings, 'digest_days', "Tuesday,Friday"),
        "digest_time": getattr(settings, 'digest_time', "09:00"),
        "reminder_frequency": settings.reminder_frequency or "twice_weekly",
        "notification_time": settings.notification_time or "09:00",
        "sound": settings.sound,
        "vibration": settings.vibration,
    }


@router.post("/notifications/settings")
def save_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Saves user notification preferences including Expiry Review Digest options."""
    settings = db.query(models.NotificationSettings).filter(
        models.NotificationSettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = models.NotificationSettings(user_id=current_user.id)
        db.add(settings)

    if "enabled" in payload:
        settings.enabled = bool(payload["enabled"])
    if "digest_enabled" in payload:
        settings.digest_enabled = bool(payload["digest_enabled"])
    if "digest_days" in payload:
        settings.digest_days = str(payload["digest_days"])
    if "digest_time" in payload:
        settings.digest_time = str(payload["digest_time"])
        settings.notification_time = str(payload["digest_time"])
    if "sound" in payload:
        settings.sound = bool(payload["sound"])
    if "vibration" in payload:
        settings.vibration = bool(payload["vibration"])

    db.commit()
    db.refresh(settings)
    return {"status": "success", "message": "Notification preferences saved successfully."}


@router.post("/notifications/test-digest")
def trigger_test_expiry_digest_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers an immediate Expiry Review Digest notification for the current user."""
    from services.notification_service import send_expiry_digest_notifications, calculate_expiry_digest_buckets
    digest = calculate_expiry_digest_buckets(current_user.id, db)
    send_expiry_digest_notifications(force_send=True)

    return {
        "status": "success",
        "message": f"Expiry Review Digest sent for {current_user.shop_name}.",
        "digest_summary": {
            "title": digest["notification_title"],
            "body": digest["notification_body"],
            "total_at_risk_count": digest["total_at_risk_count"],
            "total_at_risk_value": digest["total_at_risk_value"],
        }
    }


@router.post("/expiry/action")
def execute_expiry_action(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Executes actionable expiry tasks (Mark Return, Priority Sale, Adjust Stock)."""
    product_id = payload.get("product_id")
    action = payload.get("action") # "mark_return", "priority_sale", "adjust_stock"
    
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.user_id == current_user.id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product batch not found")

    if action == "mark_return":
        product.status = "Marked for Return"
        db.commit()
        return {"status": "success", "message": f"{product.product_name} marked for supplier return."}

    elif action == "priority_sale":
        product.status = "Priority Sale"
        db.commit()
        return {"status": "success", "message": f"{product.product_name} added to Priority Sale list."}

    elif action == "adjust_stock":
        new_qty = payload.get("new_quantity", 0)
        product.quantity = max(0, new_qty)
        if product.quantity == 0:
            product.status = "Out of Stock"
        db.commit()
        return {"status": "success", "message": f"Stock adjusted for {product.product_name}."}

    return {"status": "error", "message": "Unknown action"}


class PrinterConnectionManager:
    """Manages active WebSocket connections from Desktop Print Agents."""

    def __init__(self):
        # user_id -> List of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"[PRINTER_WS] Agent connected for user_id {user_id}. Total active: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"[PRINTER_WS] Agent disconnected for user_id {user_id}")

    def is_agent_online(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))

    async def push_print_job(self, user_id: int, job_data: dict) -> bool:
        """Pushes print job to all connected desktop print agents for this shop."""
        connections = self.active_connections.get(user_id, [])
        if not connections:
            return False

        message = json.dumps({
            "type": "NEW_PRINT_JOB",
            "job": job_data,
        })

        sent_any = False
        dead_connections = []
        for ws in connections:
            try:
                await ws.send_text(message)
                sent_any = True
            except Exception as e:
                logger.warning(f"[PRINTER_WS] Failed to send job to agent: {e}")
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(user_id, dead)

        return sent_any


printer_manager = PrinterConnectionManager()


def _build_job_payload_dict(sale: models.Sale, shop: models.User, printer: Optional[models.PrinterDevice] = None) -> dict:
    """Freezes complete finalized snapshot of bill + shop details for the thermal print job."""
    items_list = []
    for item in sale.items:
        items_list.append({
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit_type": getattr(item, "unit_type", "strip") or "strip",
            "unit_price": float(item.unit_price or 0.0),
            "discount": float(item.discount or 0.0),
            "total_with_tax": float(item.total_with_tax or item.total_price or 0.0),
            "line_total": float(item.line_total or item.total_price or 0.0),
            "batch_number": getattr(item, "batch_number", "-") or "-",
            "expiry_date": getattr(item, "expiry_date", None) or (item.product.expiry_date.strftime("%m/%y") if getattr(item, "product", None) and getattr(item.product, "expiry_date", None) else "-"),
            "tablets_per_strip": getattr(item, "tablets_per_strip", 10) or 10,
            "hsn_code": getattr(item, "hsn_code", "3004") or "3004",
            "gst_percentage": float(item.gst_percentage or 0.0),
        })

    tax_summary = []
    if sale.tax_summary_json:
        try:
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            tax_summary = []

    return {
        "sale": {
            "id": sale.id,
            "bill_number": sale.bill_number,
            "created_at": sale.created_at.isoformat() if sale.created_at else datetime.utcnow().isoformat(),
            "customer_name": sale.customer_name or "Cash Customer",
            "customer_phone": sale.customer_phone or "",
            "payment_method": sale.payment_method or "CASH",
            "doctor_name": sale.doctor_name or "",
            "doctor_reg_no": sale.doctor_reg_no or "",
            "subtotal": float(sale.subtotal or 0.0),
            "discount_amount": float(sale.discount_amount or 0.0),
            "tax_amount": float(sale.tax_amount or 0.0),
            "total_amount": float(sale.total_amount or 0.0),
            "total_taxable_value": float(sale.total_taxable_value or 0.0),
            "total_cgst": float(sale.total_cgst or 0.0),
            "total_sgst": float(sale.total_sgst or 0.0),
            "total_igst": float(sale.total_igst or 0.0),
            "tax_summary": tax_summary,
            "items": items_list,
        },
        "shop": {
            "shop_name": shop.shop_name or "DawaiFlow Pharmacy",
            "owner_name": shop.owner_name or "",
            "gstin": getattr(shop, "gstin", None) or shop.gst_number or "07AABCE1234F1Z5",
            "address": getattr(shop, "address", None) or "Main Market, New Delhi - 110001",
            "phone": getattr(shop, "phone", None) or "+91-9876543210",
            "drug_license_no": getattr(shop, "drug_license_no", None) or "DL-2026-PHARMA-01",
            "terms_and_conditions": getattr(shop, "terms_and_conditions", None) or "1. Goods once sold will not be returned.\n2. Expiry dates checked at sales time.",
        },
        "printer": {
            "printer_system_name": printer.printer_system_name if printer else None,
            "paper_size": printer.paper_size if printer else "80mm",
            "settings": json.loads(printer.settings_json) if printer and printer.settings_json else {},
        } if printer else None,
    }


def _create_print_job_internal(
    db: Session,
    sale_id: int,
    user: models.User,
    printer_id: Optional[int] = None,
    copies: int = 1,
    force_print_again: bool = False,
    paper_size: Optional[str] = None,
) -> models.PrintJob:
    """Internal helper to idempotently create or return a print job for a sale."""
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id, models.Sale.user_id == user.id).first()
    if not sale:
        raise HTTPException(status_code=404, detail=f"Bill ID {sale_id} not found.")

    # Idempotency check: if not forcing print again, check for existing PENDING or PRINTING job
    if not force_print_again:
        existing_job = (
            db.query(models.PrintJob)
            .filter(
                models.PrintJob.user_id == user.id,
                models.PrintJob.sale_id == sale_id,
                models.PrintJob.status.in_(["PENDING", "PRINTING"]),
            )
            .order_by(models.PrintJob.created_at.desc())
            .first()
        )
        if existing_job:
            return existing_job

    # Resolve target printer
    target_printer = None
    if printer_id:
        target_printer = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.id == printer_id,
            models.PrinterDevice.user_id == user.id,
        ).first()

    if not target_printer:
        target_printer = (
            db.query(models.PrinterDevice)
            .filter(models.PrinterDevice.user_id == user.id, models.PrinterDevice.is_default == True)
            .first()
        )

    resolved_paper_size = paper_size or (target_printer.paper_size if target_printer else "80mm")

    payload_dict = _build_job_payload_dict(sale, user, target_printer)
    payload_json = json.dumps(payload_dict)

    job = models.PrintJob(
        user_id=user.id,
        printer_id=target_printer.id if target_printer else None,
        sale_id=sale.id,
        invoice_number=sale.bill_number,
        status="PENDING",
        copies=max(1, copies),
        paper_size=resolved_paper_size,
        payload_json=payload_json,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/printers/register", response_model=schemas.PrinterDeviceResponse)
def register_printer_device(
    payload: schemas.PrinterDeviceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Registers or updates a printer discovered by the desktop print agent or mobile app."""
    existing = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id,
        models.PrinterDevice.printer_system_name == payload.printer_system_name,
    ).first()

    if payload.is_default:
        # Clear default flag on existing printers
        db.query(models.PrinterDevice).filter(
            models.PrinterDevice.user_id == current_user.id
        ).update({"is_default": False})

    if existing:
        existing.device_name = payload.device_name
        existing.connection_type = payload.connection_type
        existing.paper_size = payload.paper_size
        existing.is_default = payload.is_default
        existing.is_online = True
        existing.last_seen_at = datetime.utcnow()
        if payload.settings_json:
            existing.settings_json = payload.settings_json
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Check if first printer for user
        has_any = db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == current_user.id).first()
        is_def = True if not has_any else payload.is_default

        printer = models.PrinterDevice(
            user_id=current_user.id,
            device_name=payload.device_name,
            printer_system_name=payload.printer_system_name,
            connection_type=payload.connection_type,
            paper_size=payload.paper_size,
            is_default=is_def,
            is_online=True,
            last_seen_at=datetime.utcnow(),
            settings_json=payload.settings_json,
        )
        db.add(printer)
        db.commit()
        db.refresh(printer)
        return printer


@router.get("/printers", response_model=List[schemas.PrinterDeviceResponse])
def list_printers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists all registered printers for the shop with live online/offline status."""
    printers = (
        db.query(models.PrinterDevice)
        .filter(models.PrinterDevice.user_id == current_user.id)
        .order_by(models.PrinterDevice.is_default.desc(), models.PrinterDevice.device_name.asc())
        .all()
    )

    # Dynamic check: if agent websocket is connected, mark online
    agent_online = printer_manager.is_agent_online(current_user.id)
    for p in printers:
        if agent_online:
            # Online if agent is connected and seen in last 10 mins
            if p.last_seen_at and (datetime.utcnow() - p.last_seen_at).total_seconds() < 600:
                p.is_online = True
        else:
            p.is_online = False

    return printers


@router.put("/printers/{printer_id}/default", response_model=schemas.PrinterDeviceResponse)
def set_default_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Sets the chosen printer as default for this pharmacy."""
    printer = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.id == printer_id,
        models.PrinterDevice.user_id == current_user.id,
    ).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer device not found.")

    db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id
    ).update({"is_default": False})

    printer.is_default = True
    db.commit()
    db.refresh(printer)
    return printer


@router.delete("/printers/{printer_id}")
def delete_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Removes a registered printer device."""
    printer = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.id == printer_id,
        models.PrinterDevice.user_id == current_user.id,
    ).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer device not found.")

    db.delete(printer)
    db.commit()
    return {"success": True, "message": f"Printer '{printer.device_name}' removed."}


@router.get("/printers/status", response_model=schemas.PrinterStatusSummaryResponse)
def get_printer_status_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Returns overall printer readiness for mobile UI display (🟢 Ready, 🟡 Print Pending, 🔴 Offline)."""
    printers = db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == current_user.id).all()
    default_p = next((p for p in printers if p.is_default), printers[0] if printers else None)
    agent_online = printer_manager.is_agent_online(current_user.id)

    pending_count = (
        db.query(func.count(models.PrintJob.id))
        .filter(models.PrintJob.user_id == current_user.id, models.PrintJob.status == "PENDING")
        .scalar()
        or 0
    )

    online_count = len(printers) if agent_online else 0

    if not printers:
        label = "No Printer Setup"
        color = "grey"
    elif agent_online:
        if pending_count > 0:
            label = "Print Pending"
            color = "yellow"
        else:
            label = "Printer Ready"
            color = "green"
    else:
        if pending_count > 0:
            label = "Printer Offline — Bill Queued"
            color = "yellow"
        else:
            label = "Printer Offline"
            color = "red"

    return schemas.PrinterStatusSummaryResponse(
        has_printer=bool(printers),
        has_online_printer=agent_online and bool(printers),
        default_printer=schemas.PrinterDeviceResponse.from_orm(default_p) if default_p else None,
        online_count=online_count,
        pending_jobs_count=pending_count,
        status_label=label,
        status_color=color,
    )


@router.post("/print-jobs", response_model=schemas.PrintJobResponse, status_code=201)
async def create_print_job_endpoint(
    payload: schemas.PrintJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Creates a print job for a finalized bill and notifies connected print agents in real-time."""
    job = _create_print_job_internal(
        db=db,
        sale_id=payload.sale_id,
        user=current_user,
        printer_id=payload.printer_id,
        copies=payload.copies,
        force_print_again=payload.force_print_again,
        paper_size=payload.paper_size,
    )

    # Push to connected Desktop Print Agent in background
    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": json.loads(job.payload_json),
    }
    background_tasks.add_task(printer_manager.push_print_job, current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


@router.get("/print-jobs", response_model=List[schemas.PrintJobResponse])
def get_print_jobs(
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists print jobs for the pharmacy with optional status filter (PENDING, PRINTED, FAILED)."""
    q = db.query(models.PrintJob).filter(models.PrintJob.user_id == current_user.id)
    if status_filter:
        q = q.filter(models.PrintJob.status == status_filter.upper())

    jobs = q.order_by(models.PrintJob.created_at.desc()).limit(limit).all()
    results = []
    for j in jobs:
        res = schemas.PrintJobResponse.from_orm(j)
        if j.printer:
            res.printer_name = j.printer.device_name
        results.append(res)
    return results


@router.post("/print-jobs/{job_id}/retry", response_model=schemas.PrintJobResponse)
async def retry_print_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Re-queues a failed or cancelled print job safely without creating duplicate bills."""
    job = db.query(models.PrintJob).filter(
        models.PrintJob.id == job_id,
        models.PrintJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Print job not found.")

    job.status = "PENDING"
    job.retry_count += 1
    job.error_message = None
    job.failed_at = None
    db.commit()
    db.refresh(job)

    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": json.loads(job.payload_json),
    }
    background_tasks.add_task(printer_manager.push_print_job, current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


@router.post("/print-jobs/test-print", response_model=schemas.PrintJobResponse)
async def trigger_test_print(
    printer_id: Optional[int] = None,
    paper_size: str = "80mm",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Generates a test print job to verify connectivity between desktop agent and thermal printer."""
    # Find printer
    target_p = None
    if printer_id:
        target_p = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.id == printer_id,
            models.PrinterDevice.user_id == current_user.id,
        ).first()

    if not target_p:
        target_p = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.user_id == current_user.id,
            models.PrinterDevice.is_default == True,
        ).first()

    # Synthetic test sale payload
    test_payload = {
        "sale": {
            "id": 0,
            "bill_number": f"TEST-{datetime.now().strftime('%H%M%S')}",
            "created_at": datetime.utcnow().isoformat(),
            "customer_name": "Test Customer",
            "customer_phone": "+91-9876543210",
            "payment_method": "TEST MODE",
            "doctor_name": "Dr. Dawaiflow",
            "doctor_reg_no": "TEST-01",
            "subtotal": 100.0,
            "discount_amount": 0.0,
            "tax_amount": 12.0,
            "total_amount": 112.0,
            "total_taxable_value": 100.0,
            "total_cgst": 6.0,
            "total_sgst": 6.0,
            "total_igst": 0.0,
            "items": [
                {
                    "product_name": "Dawaiflow POS Test Medicine 500mg",
                    "quantity": 1,
                    "unit_type": "strip",
                    "unit_price": 100.0,
                    "discount": 0.0,
                    "total_with_tax": 112.0,
                    "line_total": 112.0,
                    "batch_number": "TST-2026",
                    "expiry_date": "12/28",
                    "gst_percentage": 12.0,
                }
            ],
        },
        "shop": {
            "shop_name": current_user.shop_name or "Dawaiflow Pharmacy",
            "owner_name": current_user.owner_name or "",
            "gstin": getattr(current_user, "gstin", None) or current_user.gst_number or "07AABCE1234F1Z5",
            "address": getattr(current_user, "address", None) or "Pharmacy Test Counter, Main City",
            "phone": getattr(current_user, "phone", None) or "+91-9876543210",
            "drug_license_no": getattr(current_user, "drug_license_no", None) or "DL-TEST-2026",
            "terms_and_conditions": "Thermal Printer Test Successful!\nDawaiflow Production Bridge Ready.",
        },
        "printer": {
            "printer_system_name": target_p.printer_system_name if target_p else None,
            "paper_size": target_p.paper_size if target_p else paper_size,
        } if target_p else None,
    }

    job = models.PrintJob(
        user_id=current_user.id,
        printer_id=target_p.id if target_p else None,
        sale_id=None,
        invoice_number=f"TEST-{datetime.now().strftime('%H%M%S')}",
        status="PENDING",
        copies=1,
        paper_size=target_p.paper_size if target_p else paper_size,
        payload_json=json.dumps(test_payload),
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Push to desktop agent
    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": test_payload,
    }
    await printer_manager.push_print_job(current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


@router.post("/printer-agent/poll")
def poll_pending_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Fallback HTTP polling endpoint for Desktop Print Agents in environments where
    corporate firewalls or proxies sever persistent WebSocket connections.
    """
    pending = (
        db.query(models.PrintJob)
        .filter(models.PrintJob.user_id == current_user.id, models.PrintJob.status == "PENDING")
        .order_by(models.PrintJob.created_at.asc())
        .limit(10)
        .all()
    )

    # Mark user's printers as online since agent is polling
    db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id
    ).update({"is_online": True, "last_seen_at": datetime.utcnow()})
    db.commit()

    jobs_data = []
    for j in pending:
        jobs_data.append({
            "job_id": j.id,
            "user_id": j.user_id,
            "sale_id": j.sale_id,
            "invoice_number": j.invoice_number,
            "copies": j.copies,
            "paper_size": j.paper_size,
            "payload": json.loads(j.payload_json),
        })

    return {"jobs": jobs_data}


@router.post("/printer-agent/ack")
def acknowledge_job_status(
    payload: schemas.PrintJobStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HTTP endpoint for agent to report successful transmission or errors."""
    update_data = {"status": payload.status}
    if payload.status == "PRINTING":
        update_data["claimed_at"] = datetime.utcnow()
    elif payload.status == "PRINTED":
        update_data["printed_at"] = datetime.utcnow()
    elif payload.status == "FAILED":
        update_data["failed_at"] = datetime.utcnow()
        update_data["error_message"] = payload.error_message

    rows_updated = db.query(models.PrintJob).filter(
        models.PrintJob.id == payload.job_id,
        models.PrintJob.user_id == current_user.id,
    ).update(update_data)

    if not rows_updated:
        raise HTTPException(status_code=404, detail="Print job not found.")

    db.commit()
    return {"success": True, "job_id": payload.job_id, "status": payload.status}


class CreateBackupRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/backup/create")
@router.post("/api/backup/create")
def api_create_backup(
    payload: Optional[CreateBackupRequest] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Creates a manual encrypted backup for the authenticated shop owner."""
    try:
        notes = payload.notes if payload else None
        record = backup_service.create_backup(
            db=db,
            user_id=current_user.id,
            backup_type="MANUAL",
            notes=notes,
        )
        return {
            "success": True,
            "message": "Backup generated and encrypted successfully.",
            "backup": {
                "backup_id": record.backup_id,
                "file_name": record.filename,
                "file_size": record.file_size_bytes,
                "backup_type": record.backup_type,
                "status": record.status,
                "checksum": record.checksum_sha256,
                "record_counts": json.loads(record.record_counts_json) if record.record_counts_json else {},
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "notes": record.notes,
            },
        }
    except Exception as e:
        logger.error(f"[BACKUP ERROR] Manual backup creation failed for shop {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@router.get("/backup/history")
@router.get("/api/backup/history")
def api_get_backup_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Retrieves backup history and latest safety snapshot status for the authenticated shop owner."""
    try:
        history = backup_service.get_backup_history(db=db, user_id=current_user.id, limit=limit)
        return {"success": True, "backups": history}
    except Exception as e:
        logger.error(f"[BACKUP ERROR] Failed to fetch history for shop {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch backup history: {str(e)}")


@router.get("/backup/download/{backup_id}")
@router.get("/api/backup/download/{backup_id}")
def api_download_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Securely downloads an encrypted backup archive (.dfbk). Restricted to shop owner."""
    record = db.query(models.BackupRecord).filter(
        models.BackupRecord.backup_id == backup_id,
        models.BackupRecord.user_id == current_user.id,
    ).first()

    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Backup file not found or has been removed.")

    return FileResponse(
        path=record.file_path,
        filename=record.filename,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{record.filename}"',
            "X-Backup-Checksum": record.checksum_sha256 or "",
        },
    )


@router.post("/backup/upload-restore")
@router.post("/api/backup/upload-restore")
async def api_upload_and_restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Accepts an uploaded .dfbk backup archive and executes atomic restoration with safety backup."""
    if not file.filename.endswith(".dfbk"):
        raise HTTPException(
            status_code=400,
            detail="Invalid backup format. Only encrypted .dfbk archives are supported.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = backup_service.restore_backup(
            db=db,
            user_id=current_user.id,
            backup_file_bytes=file_bytes,
            initiated_by_name=current_user.owner_name or current_user.shop_name or "Owner",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error restoring backup from upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Restoration failed: {e}")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Restore failed."))

    return result


@router.delete("/backup/{backup_id}")
@router.delete("/api/backup/{backup_id}")
def api_delete_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Deletes a backup archive and its database log entry."""
    success = backup_service.delete_backup(db=db, user_id=current_user.id, backup_id=backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found or could not be deleted.")
    return {"success": True, "message": "Backup removed successfully."}


@router.post("/api/migration/upload")
@router.post("/migration/historical-bills")
async def api_upload_migration_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """
    Uploads historical bills file (PDF, CSV, Excel), returns job_id immediately,
    and starts asynchronous background processing.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a valid filename.")

    allowed_exts = [".pdf", ".csv", ".xlsx", ".xls", ".txt"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed formats: PDF, CSV, Excel (.xlsx, .xls)."
        )

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(status_code=413, detail="File size exceeds maximum allowed limit of 50MB.")

    temp_dir = BASE_DIR / "temp_migrations"
    os.makedirs(temp_dir, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
    temp_file_path = str(temp_dir / safe_filename)

    with open(temp_file_path, "wb") as f:
        f.write(contents)

    migration_code = migration_service.generate_migration_code(db)
    is_large = len(contents) > 3 * 1024 * 1024

    migration = models.DataMigration(
        user_id=current_user.id,
        migration_code=migration_code,
        migration_type="OLD_BILLS",
        source_software="OTHER",
        file_name=file.filename,
        file_format=ext.replace(".", "").upper(),
        file_size_bytes=len(contents),
        status="uploading",
        current_stage="uploading",
        current_stage_label="Uploading file...",
        current_message="Reading file...",
        processed_count=0,
        total_count=0,
        is_large_file=is_large,
        progress_percentage=10,
        created_at=datetime.utcnow()
    )
    db.add(migration)
    db.commit()
    db.refresh(migration)

    # Dispatch asynchronous background processing
    background_tasks.add_task(
        migration_service.process_migration_background,
        migration.id,
        current_user.id,
        temp_file_path,
        file.filename
    )

    return {
        "job_id": migration.migration_code,
        "migration_id": migration.id,
        "migration_code": migration.migration_code,
        "status": "queued",
        "stage": "uploading",
        "message": "Reading file...",
        "processed": 0,
        "total": 0,
        "percentage": 10,
        "is_large_file": is_large
    }


@router.get("/api/migration/active")
def api_get_active_migration(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Returns any active migration currently in PROCESSING state for page refresh recovery."""
    active = migration_service.get_active_migration(db=db, user_id=current_user.id)
    return {"active": active}


@router.get("/api/migration/preview/{migration_id}")
def api_get_migration_preview(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Retrieves parsed preview records for a migration batch."""
    try:
        return migration_service.get_migration_preview_by_id(db=db, user_id=current_user.id, migration_id=migration_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch migration preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/migration/confirm/{migration_id}")
def api_confirm_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Commits or confirms a historical migration batch."""
    try:
        result = migration_service.commit_migration(db=db, user_id=current_user.id, migration_id=migration_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Migration commit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/migration/status/{migration_id}")
@router.get("/migration/historical-bills/{migration_id}/status")
def api_get_migration_status(
    migration_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Polls real-time progress status of an active or completed migration by ID or job code."""
    try:
        # Check if migration_id is integer ID or migration_code string
        if str(migration_id).isdigit():
            m_id = int(migration_id)
        else:
            mig = db.query(models.DataMigration).filter(
                models.DataMigration.migration_code == migration_id,
                models.DataMigration.user_id == current_user.id
            ).first()
            if not mig:
                raise HTTPException(status_code=404, detail=f"Job {migration_id} not found.")
            m_id = mig.id

        return migration_service.get_migration_status(db=db, user_id=current_user.id, migration_id=m_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/migration/rollback/{migration_id}")
def api_rollback_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """
    Rolls back an imported migration batch, deleting all associated historical
    sales and items while leaving live transactions and inventory untouched.
    """
    try:
        result = migration_service.rollback_migration(db=db, user_id=current_user.id, migration_id=migration_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Migration rollback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/migration/history")
def api_get_migration_history(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Returns list of past data migration batches for the pharmacy."""
    try:
        return migration_service.get_migration_history(db=db, user_id=current_user.id)
    except Exception as e:
        logger.error(f"Failed to fetch migration history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/migration/errors/{migration_id}/export")
def api_export_migration_errors(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Exports CSV of errors and skipped records from a migration."""
    errors = db.query(models.MigrationError).filter(
        models.MigrationError.migration_id == migration_id,
        models.MigrationError.user_id == current_user.id
    ).order_by(models.MigrationError.id.asc()).all()

    output = io.StringIO()
    writer = pd.DataFrame([{
        "Row Number": e.row_number,
        "Bill Identifier": e.bill_identifier,
        "Error Type": e.error_type,
        "Reason": e.reason,
        "Recorded At": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else ""
    } for e in errors])

    csv_data = writer.to_csv(index=False)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=migration_errors_{migration_id}.csv"}
    )


@router.get("/returns/marked")
def api_get_marked_for_return(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Fetch all batches currently marked for return for the logged in tenant."""
    try:
        return crud.get_marked_for_return_items(db, current_user.id)
    except Exception as e:
        logger.error(f"[Marked Returns GET Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve marked for return items")


@router.post("/returns/marked")
def api_mark_item_for_return(
    data: schemas.MarkedForReturnCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Mark a specific product/batch for supplier return without stock deduction."""
    try:
        item = crud.mark_item_for_return(
            db=db,
            user_id=current_user.id,
            product_id=data.product_id,
            batch_number=data.batch_number,
            return_qty=data.return_qty,
            notes=data.notes,
        )
        fast_cache.invalidate_tag(current_user.id, "dashboard")
        return {"message": "Item marked for return successfully", "id": item.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Marked Return POST Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to mark item for return")


@router.put("/returns/marked/{item_id}")
def api_update_marked_for_return(
    item_id: int,
    data: schemas.MarkedForReturnUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Update quantity, notes, or status of a marked return item."""
    try:
        item = crud.update_marked_for_return_item(
            db=db,
            user_id=current_user.id,
            item_id=item_id,
            return_qty=data.return_qty,
            notes=data.notes,
            status=data.status,
        )
        fast_cache.invalidate_tag(current_user.id, "dashboard")
        return {"message": "Marked return updated successfully", "id": item.id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Marked Return PUT Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to update marked return")


@router.delete("/returns/marked/{item_id}")
def api_delete_marked_for_return(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Remove item from marked for return list."""
    try:
        crud.delete_marked_for_return_item(db, current_user.id, item_id)
        fast_cache.invalidate_tag(current_user.id, "dashboard")
        return {"message": "Item removed from marked for return"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Marked Return DELETE Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to remove marked return item")


@router.delete("/returns/marked/product/{product_id}")
def api_delete_marked_for_return_by_product(
    product_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Remove product from marked for return list."""
    try:
        crud.delete_marked_for_return_by_product(db, current_user.id, product_id)
        fast_cache.invalidate_tag(current_user.id, "dashboard")
        return {"message": "Product removed from marked for return"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Marked Return DELETE Product Error] {e}")
        raise HTTPException(status_code=500, detail="Failed to remove product from marked returns")
