"""
AI Vision Scanning and Assistant Routes for DawaiFlow / ExpiryGuard.
Handles Gemini Vision multi-item shelf scan, single-strip camera scan, purchase bill invoice OCR, and RAG grounded chat.
"""

import re
import time
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, File, Request, Response, status
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
from ai import scan_fallback
from ai.gemini_service import scan_label
from ai.multi_item_scan_service import scan_multi_item
from ai.invoice_service import scan_invoice
from ai.ocr_service import extract_medicine_batch_from_image

logger = logging.getLogger("expiryguard.routes.ai")

router = APIRouter(tags=["AI Vision & Intelligence"])

ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE_10MB = 10 * 1024 * 1024


def _format_ai_error_exception(err_msg: str) -> HTTPException:
    """
    Maps an AI failure to an HTTP error. The client only ever sees plain "DawaiFlow AI" wording: the raw text
    (which can name the AI vendor, model, quota or key problems) goes to the server log, never to the user.
    Status codes are unchanged so older app versions keep working.
    """
    err_clean = re.sub(r'AI_KEY=\S+|Bearer \S+|AQ\.[A-Za-z0-9_\-]+', '[REDACTED]', str(err_msg or ""))
    err_lower = err_clean.lower()
    logger.warning("[AI SCAN] AI error (details hidden from client): %s", err_clean[:500])

    if "429" in err_clean or "quota" in err_lower or "resource_exhausted" in err_lower:
        return HTTPException(
            status_code=429,
            detail="DawaiFlow AI is busy right now. Please wait a minute and retry, or enter manually."
        )
    elif "401" in err_clean or "unauthorized" in err_lower or "invalid_api_key" in err_lower or "expired token" in err_lower or "invalid token" in err_lower:
        return HTTPException(
            status_code=401,
            detail="DawaiFlow AI is not available right now. Please enter manually or try again later."
        )
    elif "403" in err_clean or "permission" in err_lower or "forbidden" in err_lower:
        return HTTPException(
            status_code=403,
            detail="DawaiFlow AI is not available right now. Please enter manually or try again later."
        )
    elif "408" in err_clean or "timeout" in err_lower:
        return HTTPException(
            status_code=408,
            detail="DawaiFlow AI took too long. Please retry or enter manually."
        )
    elif "503" in err_clean or "unavailable" in err_lower:
        return HTTPException(
            status_code=503,
            detail="DawaiFlow AI is temporarily unavailable. Please retry or enter manually."
        )
    elif "504" in err_clean:
        return HTTPException(
            status_code=504,
            detail="DawaiFlow AI took too long. Please retry or enter manually."
        )
    elif "json" in err_lower or "schema" in err_lower or "parse" in err_lower:
        return HTTPException(
            status_code=422,
            detail="DawaiFlow AI could not read this clearly. Please retry or enter manually."
        )
    else:
        return HTTPException(
            status_code=502,
            detail="DawaiFlow AI could not read this. Please retry or enter manually."
        )


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
    db: Session = Depends(get_db),
):
    """
    Scans a single medicine strip/box image for camera billing using Gemini AI.
    """
    t_start = time.time()
    logger.info("[AI SCAN] request started endpoint=/scan-label user_id=%s", current_user.id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"

    file_bytes = file.file.read()
    if not file_bytes:
        duration_ms = int((time.time() - t_start) * 1000)
        logger.warning("[AI SCAN] response status: 400 | duration: %d ms | failure type: EmptyFile | failure message: Uploaded image file is empty.", duration_ms)
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    _validate_file_magic(file_bytes, ext)
    res = scan_label(file_bytes, user_id=current_user.id)
    if not res.get("success"):
        duration_ms = int((time.time() - t_start) * 1000)
        err_str = res.get("error") or "Failed to scan medicine label."
        logger.warning("[AI SCAN] response status: failure | duration: %d ms | failure type: AIServiceError | failure message: %s", duration_ms, err_str)
        raise _format_ai_error_exception(err_str)
    
    # Enrich with shop-scoped inventory matching
    data = res.get("data")
    if data and isinstance(data, dict):
        scanned_name = data.get("product_name") or data.get("brand") or ""
        batch = data.get("batch_number")
        if scanned_name:
            match_res = crud.match_scanned_medicine_to_inventory(
                db=db,
                user_id=current_user.id,
                scanned_name=scanned_name,
                batch_number=batch,
            )
            data["inventory_match"] = match_res
            if match_res.get("status") == "no_match":
                data["inventory_error"] = f"Medicine identified: '{scanned_name}', but no matching medicine was found in inventory/catalog."

    duration_ms = int((time.time() - t_start) * 1000)
    logger.info("[AI SCAN] response status: 200 | duration: %d ms", duration_ms)
    return res


@router.post("/scan-batch-label")
@router.post("/documents/scan-batch-label")
@router.post("/api/scan-batch-label")
@limiter.limit("60/minute")
def scan_batch_label_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Dedicated Camera Scanner Endpoint for Medicine Batch/Lot Extraction.
    Extracts ONLY the Batch/Lot number from packaging image via spatial OCR
    and performs immediate exact shop inventory lookup.
    """
    t_start = time.time()
    logger.info("[AI SCAN BATCH] request started endpoint=/scan-batch-label user_id=%s", current_user.id)

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        ext = ".jpg"

    file_bytes = file.file.read()
    if not file_bytes:
        duration_ms = int((time.time() - t_start) * 1000)
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

    _validate_file_magic(file_bytes, ext)

    # 1. Run Spatial OCR Batch Extractor
    ocr_res = extract_medicine_batch_from_image(file_bytes)

    if not ocr_res.get("success") or ocr_res.get("batch_number") == "BATCH_NOT_CONFIDENT":
        duration_ms = int((time.time() - t_start) * 1000)
        return {
            "success": False,
            "extracted_batch": "BATCH_NOT_CONFIDENT",
            "anchor": ocr_res.get("anchor"),
            "confidence": 0.0,
            "bbox": None,
            "associated_text": None,
            "inventory_match": {
                "found": False,
                "status": "batch_not_detected",
                "message": "Could not confidently locate BATCH/LOT label on packaging image."
            },
            "duration_ms": duration_ms
        }

    extracted_batch = ocr_res.get("batch_number")

    # 2. Direct Exact Shop Inventory Lookup using Batch Number as Primary Key
    lookup_res = crud.quick_batch_lookup(db=db, user_id=current_user.id, raw_batch_str=extracted_batch)

    duration_ms = int((time.time() - t_start) * 1000)
    logger.info(
        "[AI SCAN BATCH] status=200 duration=%d ms extracted_batch=%s anchor=%s found=%s",
        duration_ms,
        extracted_batch,
        ocr_res.get("anchor"),
        lookup_res.get("found"),
    )

    return {
        "success": True,
        "extracted_batch": extracted_batch,
        "anchor": ocr_res.get("anchor"),
        "confidence": ocr_res.get("confidence"),
        "bbox": ocr_res.get("bbox"),
        "associated_text": ocr_res.get("associated_text"),
        "inventory_match": lookup_res,
        "duration_ms": duration_ms
    }


@router.post("/scan-medicine-fallback")
@limiter.limit("30/minute")
def scan_medicine_fallback_endpoint(
    request: Request,
    file: UploadFile = File(...),
    ocr_batch: Optional[str] = Form(None),
    ocr_expiry: Optional[str] = Form(None),
    ocr_mrp: Optional[str] = Form(None),
    ocr_name: Optional[str] = Form(None),
    ocr_batch_conf: Optional[str] = Form(None),
    ocr_expiry_conf: Optional[str] = Form(None),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """
    Medicine pack scan fallback. The phone reads the pack with on-device OCR first and sends the photo here only
    when batch/expiry are missing or unclear. DawaiFlow AI is called only if the server kill switch is on and the
    pharmacy is under its caps; otherwise the OCR values come back with the unclear fields flagged.
    """
    file_bytes = file.file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded image file is empty.")
    _validate_file_magic(file_bytes, Path(file.filename or "").suffix.lower() or ".jpg")
    try:
        return scan_fallback.resolve_scan(file_bytes, {
            "batch": ocr_batch, "expiry": ocr_expiry, "mrp": ocr_mrp, "name": ocr_name,
            "batch_conf": ocr_batch_conf, "expiry_conf": ocr_expiry_conf,
        }, current_user.id)
    except Exception as exc:  # never crash the scanner: tell the app to enter manually
        logger.error("[SCAN_FALLBACK] unexpected error: %s", type(exc).__name__)
        return {"success": False, "scan_source": "failed", "batch_number": None, "expiry_date": None, "mrp": None,
                "medicine_name": None, "uncertain_fields": ["batch_number", "expiry_date"],
                "needs_manual_review": True, "gemini_calls": 0, "reason": "error",
                "message": "DawaiFlow AI could not read this. Please enter manually."}


@router.post("/scan-multi-item")
@router.post("/documents/scan-multi-item")
@router.post("/api/scan-multi-item")
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
    t_start = time.time()
    logger.info("[AI SCAN] request started endpoint=/scan-multi-item user_id=%s", current_user.id)

    try:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in ALLOWED_IMAGE_EXTENSIONS:
            ext = ".jpg"

        file_bytes = file.file.read()
        if not file_bytes:
            duration_ms = int((time.time() - t_start) * 1000)
            logger.warning("[AI SCAN] response status: 400 | duration: %d ms | failure type: EmptyFile | failure message: Uploaded image file is empty.", duration_ms)
            raise HTTPException(status_code=400, detail="Uploaded image file is empty.")

        _validate_file_magic(file_bytes, ext)
        res = scan_multi_item(file_bytes, user_id=current_user.id)

        if not res.get("success"):
            duration_ms = int((time.time() - t_start) * 1000)
            err_str = res.get("error") or "Failed to scan multi-item medicines."
            logger.warning("[AI SCAN] response status: failure | duration: %d ms | failure type: AIServiceError | failure message: %s", duration_ms, err_str)
            raise _format_ai_error_exception(err_str)

        items = res.get("items") or []
        if not items:
            duration_ms = int((time.time() - t_start) * 1000)
            logger.warning("[AI SCAN] response status: 422 | duration: %d ms | failure type: EmptyExtraction | failure message: No medicine items extracted", duration_ms)
            raise HTTPException(
                status_code=422,
                detail="AI response received, but no medicine information could be extracted from image. Please ensure packaging text is clearly visible."
            )

        # Enrich each extracted item with shop-scoped inventory matching
        unmatched_names = []
        for item in items:
            scanned_name = item.get("name") or ""
            batch = item.get("batch")
            strength = item.get("strength")
            if scanned_name:
                try:
                    match_res = crud.match_scanned_medicine_to_inventory(
                        db=db,
                        user_id=current_user.id,
                        scanned_name=scanned_name,
                        strength=strength,
                        batch_number=batch,
                    )
                    item["inventory_match"] = match_res
                    if match_res.get("status") == "no_match":
                        unmatched_names.append(scanned_name)
                except Exception as match_err:
                    logger.error("[AI SCAN] Inventory match error for '%s': %s", scanned_name, match_err, exc_info=True)
                    item["inventory_match"] = {
                        "status": "no_match",
                        "matched_product": None,
                        "catalog_item": None,
                        "message": f"Inventory lookup warning: {match_err}"
                    }

        if unmatched_names:
            res["inventory_error"] = f"Medicine identified: '{', '.join(unmatched_names)}', but no matching medicine was found in inventory/catalog."
            logger.info("[AI SCAN] Inventory matching warning: %s", res["inventory_error"])

        duration_ms = int((time.time() - t_start) * 1000)
        logger.info("[AI SCAN] response status: 200 | duration: %d ms | items_count: %d", duration_ms, len(items))
        return res
    except HTTPException:
        raise
    except Exception as exc:
        duration_ms = int((time.time() - t_start) * 1000)
        logger.error("[AI SCAN] Unhandled multi-item scan exception | duration: %d ms | error: %s", duration_ms, exc, exc_info=True)
        raise _format_ai_error_exception(str(exc))


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
        scan_res = scan_invoice(image_bytes_list, user_id=current_user.id)
        if not scan_res.get("success"):
            # The bill could not be read reliably (or automatic reading is off / capped): tell the app clearly and
            # let the user enter it manually. Same shape as a normal result with no rows, so older apps show
            # their "add items manually" prompt.
            return {
                "success": False,
                "items": [],
                "items_count": 0,
                "needs_review": True,
                "needs_manual_entry": True,
                "reason": scan_res.get("reason"),
                "error": scan_res.get("error") or "The invoice could not be read. Please enter it manually.",
            }

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
            "needs_manual_entry": False,
            "validation": invoice_data.get("validation"),
            "error": None
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"[SCAN_INVOICE_ENDPOINT_ERROR] {err}", exc_info=True)
        raise HTTPException(status_code=500, detail="DawaiFlow AI could not read this bill. Please retry or enter manually.")
