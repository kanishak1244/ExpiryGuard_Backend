"""
AI Vision Scanning and Assistant Routes for DawaiFlow / ExpiryGuard.
Handles Gemini Vision multi-item shelf scan, single-strip camera scan, purchase bill invoice OCR, and RAG grounded chat.
"""

import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Request, Response, status
from sqlalchemy.orm import Session

from dependencies import (
    get_db,
    get_current_user,
    require_permission,
    AuthenticatedUser,
    limiter,
)
import models
import schemas
import crud
from ai.gemini_service import scan_label
from ai.multi_item_scan_service import scan_multi_item
from ai.invoice_service import scan_invoice

logger = logging.getLogger("expiryguard.routes.ai")

router = APIRouter(tags=["AI Vision & Intelligence"])

ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_10MB = 10 * 1024 * 1024


def _validate_file_magic(file_bytes: bytes, ext: str):
    ext = ext.lower()
    if ext in [".jpg", ".jpeg"] and not file_bytes.startswith(b"\xFF\xD8\xFF"):
        raise HTTPException(status_code=400, detail="Invalid JPEG image file signature.")
    elif ext == ".png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(status_code=400, detail="Invalid PNG image file signature.")
    elif ext == ".webp" and not (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]):
        raise HTTPException(status_code=400, detail="Invalid WEBP image file signature.")
    elif ext == ".pdf" and not file_bytes.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Invalid PDF document file signature.")


@router.post("/ai/chat")
@limiter.limit("20/minute")
def ai_chat_endpoint(
    request: Request,
    payload: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Grounded Multilingual Pharmacy AI Assistant Chat RAG Endpoint.
    """
    user_query = payload.get("query") or payload.get("message") or payload.get("text")
    if not user_query or not str(user_query).strip():
        raise HTTPException(status_code=400, detail="Query message is required.")

    return crud.get_ai_chat_response(db, current_user.id, str(user_query).strip())


@router.post("/scan-label")
@router.post("/documents/scan-label")
@limiter.limit("60/minute")
def scan_single_label_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Scans a single medicine strip/box image for camera billing using Gemini AI.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    _validate_file_magic(file_bytes, ext)
    res = scan_label(file_bytes)
    if not res.get("success"):
        raise HTTPException(status_code=502, detail=res.get("error") or "Failed to scan medicine label.")
    return res


@router.post("/scan-multi-item")
@limiter.limit("60/minute")
def scan_multi_item_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scans multiple medicine strips/boxes on counter shelf using Gemini Vision AI.
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"

    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    _validate_file_magic(file_bytes, ext)
    res = scan_multi_item(file_bytes)
    return res


@router.post("/scan-invoice")
@limiter.limit("30/hour")
def scan_invoice_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Scans single or multi-page purchase bill invoice documents using Gemini Vision OCR.
    """
    upload_list = []
    if files and len(files) > 0:
        upload_list = files
    elif file is not None:
        upload_list = [file]

    if not upload_list:
        raise HTTPException(status_code=400, detail="No invoice files provided.")

    image_bytes_list = []
    for f in upload_list:
        ext = Path(f.filename or "").suffix.lower()
        if ext not in ALLOWED_DOC_EXTENSIONS:
            ext = ".jpg"

        file_bytes = f.file.read()
        if not file_bytes:
            continue

        _validate_file_magic(file_bytes, ext)
        image_bytes_list.append(file_bytes)

    if not image_bytes_list:
        raise HTTPException(status_code=400, detail="Uploaded invoice files were empty or invalid.")

    try:
        scan_res = scan_invoice(image_bytes_list)
        if not scan_res.get("success"):
            raise HTTPException(
                status_code=502,
                detail=scan_res.get("error") or "Failed to scan purchase invoice."
            )

        invoice_data = scan_res.get("data", {})
        
        supplier_match = None
        s_name = (invoice_data.get("supplier_name") or "").strip()
        if s_name:
            supplier_match = crud.find_matching_suppliers(
                db=db,
                user_id=current_user.id,
                extracted_name=s_name,
                extracted_gstin=invoice_data.get("supplier_gstin")
            )

        items = invoice_data.get("items", [])
        has_review = any(it.get("needs_review") for it in items)

        return {
            "success": True,
            "invoice_number": invoice_data.get("invoice_number"),
            "invoice_date": invoice_data.get("invoice_date"),
            "supplier_name": invoice_data.get("supplier_name"),
            "supplier_gstin": invoice_data.get("supplier_gstin"),
            "supplier_phone": invoice_data.get("supplier_phone"),
            "supplier_address": invoice_data.get("supplier_address"),
            "supplier_match": supplier_match,
            "subtotal": invoice_data.get("subtotal"),
            "scheme_amount": invoice_data.get("scheme_amount"),
            "cd_amount": invoice_data.get("cd_amount"),
            "discount_amount": invoice_data.get("discount_amount"),
            "taxable_amount": invoice_data.get("taxable_amount"),
            "cgst_amount": invoice_data.get("cgst_amount"),
            "sgst_amount": invoice_data.get("sgst_amount"),
            "igst_amount": invoice_data.get("igst_amount"),
            "tax_amount": invoice_data.get("tax_amount"),
            "other_amount": invoice_data.get("other_amount"),
            "total_amount": invoice_data.get("total_amount"),
            "total_amount_label": invoice_data.get("total_amount_label"),
            "reconciliation": invoice_data.get("reconciliation"),
            "items": items,
            "items_count": len(items),
            "needs_review": has_review,
            "error": None
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"[SCAN_INVOICE_ENDPOINT_ERROR] {err}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Invoice OCR error: {err}")
