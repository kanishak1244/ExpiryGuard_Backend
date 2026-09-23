"""
Document Generation, Printing, Backup, and Import Routes for DawaiFlow / ExpiryGuard.
Handles invoice PDF rendering, ESC/POS thermal formatting, encrypted database backup/restore, and bulk Excel imports.
"""

import os
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
from pdf_generator import generate_invoice_pdf
import thermal_formatter
import backup_service
import import_service

logger = logging.getLogger("expiryguard.routes.documents")

router = APIRouter(tags=["Documents, Printing & Imports"])


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

    pdf_bytes = generate_invoice_pdf(sale, current_user)
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
