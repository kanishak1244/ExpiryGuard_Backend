"""
Document Generation, Printing, Backup, and Import Routes for DawaiFlow / ExpiryGuard.
Handles invoice PDF rendering, ESC/POS thermal formatting, encrypted database backup/restore, and bulk Excel imports.
"""

import os
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Request, Response, status
from fastapi.responses import FileResponse, Response, JSONResponse
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
from services.pdf_generator import generate_invoice_pdf
from services import thermal_formatter
from services import backup_service
from services import import_service

logger = logging.getLogger("expiryguard.routes.documents")

router = APIRouter(tags=["Documents, Printing & Imports"])


_SAMPLE_GSTIN = "07AABCE1234F1Z5"


def _invoice_pdf_inputs(sale, current_user):
    """Plain dictionaries for the PDF writer (it reads dict keys, not database objects)."""
    tax_summary = []
    if getattr(sale, "tax_summary_json", None):
        try:
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            tax_summary = []
    sale_dict = {
        "bill_number": sale.bill_number,
        "created_at": sale.created_at,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "payment_method": sale.payment_method,
        "doctor_name": sale.doctor_name,
        "doctor_reg_no": getattr(sale, "doctor_reg_no", None),
        "is_interstate": sale.is_interstate,
        "subtotal": sale.subtotal,
        "discount_amount": sale.discount_amount,
        "tax_amount": sale.tax_amount,
        "total_amount": sale.total_amount,
        "total_taxable_value": sale.total_taxable_value,
        "total_cgst": sale.total_cgst,
        "total_sgst": sale.total_sgst,
        "total_igst": sale.total_igst,
        "tax_summary": tax_summary,
        "items": [
            {
                "product_name": item.product_name,
                "hsn_code": getattr(item, "hsn_code", None) or "3004",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount": item.discount,
                "gst_percentage": item.gst_percentage,
                "taxable_value": item.taxable_value,
                "cgst_rate": item.cgst_rate,
                "cgst_amount": item.cgst_amount,
                "sgst_rate": item.sgst_rate,
                "sgst_amount": item.sgst_amount,
                "igst_rate": item.igst_rate,
                "igst_amount": item.igst_amount,
                "total_with_tax": item.total_with_tax,
                "total_price": item.total_price,
            }
            for item in sale.items
        ],
    }
    # Accounts registered without a GSTIN were saved with a sample GSTIN; never print that on an invoice.
    gstin = getattr(current_user, "gstin", None) or getattr(current_user, "gst_number", None)
    if gstin == _SAMPLE_GSTIN:
        gstin = getattr(current_user, "gst_number", None)
        if gstin == _SAMPLE_GSTIN:
            gstin = None
    shop_dict = {
        "shop_name": current_user.shop_name,
        "gstin": gstin,
        "address": getattr(current_user, "address", None),
        "phone": getattr(current_user, "phone", None),
    }
    return sale_dict, shop_dict


@router.get("/billing/{sale_id}/pdf")
@router.get("/sales/{sale_id}/pdf")
def get_sale_invoice_pdf(
    sale_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate and return print-ready GST Tax Invoice PDF for a sale transaction."""
    sale = crud.get_sale_by_id(db, sale_id, current_user.id)
    if not sale:
        raise HTTPException(status_code=404, detail="Sale invoice not found")

    pdf_bytes = generate_invoice_pdf(*_invoice_pdf_inputs(sale, current_user))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=Invoice_{sale.bill_number}.pdf",
            "Cache-Control": "no-cache, no-store, must-revalidate",
        },
    )


@router.get("/billing/{sale_id}/thermal")
def get_sale_thermal_format(
    sale_id: int,
    width: str = Query("3inch", description="2inch or 3inch thermal paper width"),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Generate formatted thermal receipt string for bluetooth/ESC-POS thermal printers."""
    sale = crud.get_sale_by_id(db, sale_id, current_user.id)
    if not sale:
        raise HTTPException(status_code=404, detail="Sale invoice not found")

    formatted_text = thermal_formatter.format_thermal_receipt(sale, current_user, paper_width=width)
    return {"thermal_text": formatted_text, "bill_number": sale.bill_number}


@router.post("/import/inventory")
@router.post("/documents/import-excel")
def import_inventory_spreadsheet(
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_CREATE")),
    db: Session = Depends(get_db),
):
    """Bulk import products/stock inventory from Excel (.xlsx/.xls) or CSV files."""
    filename = file.filename or ""
    ext = Path(filename).suffix.lower()
    if ext not in [".xlsx", ".xls", ".csv"]:
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload an Excel (.xlsx) or CSV file.")

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    res = import_service.import_inventory_from_bytes(db, file_bytes, current_user.id, filename)
    fast_cache.invalidate_user(current_user.id)
    return res


@router.get("/backup/download")
def download_encrypted_backup(
    current_user: AuthenticatedUser = Depends(require_permission("SETTINGS_EDIT")),
    db: Session = Depends(get_db),
):
    """Generate and download encrypted JSON backup of all pharmacy data."""
    backup_data = backup_service.export_user_backup(db, current_user.id)
    return JSONResponse(
        content=backup_data,
        headers={"Content-Disposition": f"attachment; filename=DawaiFlow_Backup_{current_user.id}.json"}
    )


@router.post("/backup/restore")
def restore_encrypted_backup(
    payload: dict,
    current_user: AuthenticatedUser = Depends(require_permission("SETTINGS_EDIT")),
    db: Session = Depends(get_db),
):
    """Restore pharmacy data from JSON backup payload."""
    res = backup_service.restore_user_backup(db, current_user.id, payload)
    fast_cache.invalidate_user(current_user.id)
    return res
