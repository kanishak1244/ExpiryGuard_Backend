import json
import logging
import mimetypes
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google.genai import types

from ai.prompts.invoice_prompt import INVOICE_PROMPT
from ai.gemini_service import (
    client,
    GEMINI_PRIMARY_MODEL,
    log_ai_metrics,
    optimize_image,
)

logger = logging.getLogger("expiryguard.ocr")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        clean_val = re.sub(r"[^\d.-]", "", str(value))
        return float(clean_val) if clean_val else default
    except Exception:
        return default


def _safe_int(value, default: int = 1) -> int:
    try:
        if value in ("", None):
            return default
        clean_val = re.sub(r"[^\d.-]", "", str(value))
        return int(float(clean_val)) if clean_val else default
    except Exception:
        return default


def _normalize_date(date_str: str) -> str:
    """
    Normalizes various date formats to ISO YYYY-MM-DD.
    """
    if not date_str or not isinstance(date_str, str):
        return ""
    
    clean = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        return clean
    
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    
    m = re.match(r"^(\d{1,2})[-/](\d{2})$", clean)
    if m:
        month, short_year = int(m.group(1)), int(m.group(2))
        full_year = 2000 + short_year
        return f"{full_year:04d}-{month:02d}-01"
    
    m = re.match(r"^(\d{1,2})[-/](\d{4})$", clean)
    if m:
        month, year = int(m.group(1)), int(m.group(2))
        return f"{year:04d}-{month:02d}-01"
    
    return clean


def _normalize_item(item: dict) -> dict:
    """
    Ensures every product has all required fields with proper types.
    """
    qty = _safe_int(item.get("quantity"), default=1)
    u_price = _safe_float(item.get("unit_price"), default=0.0)
    t_price = _safe_float(item.get("total_price"), default=0.0)
    
    if t_price == 0.0 and u_price > 0:
        t_price = round(u_price * qty, 2)
    elif u_price == 0.0 and t_price > 0 and qty > 0:
        u_price = round(t_price / qty, 2)

    return {
        "product_name": str(item.get("product_name") or "").strip(),
        "brand": str(item.get("brand") or "").strip(),
        "category": str(item.get("category") or "allopathy").strip(),
        "quantity": max(1, qty),
        "unit": str(item.get("unit") or "strip").strip(),
        "unit_price": u_price,
        "purchase_price": u_price,
        "total_price": t_price,
        "mrp": _safe_float(item.get("mrp") or u_price),
        "batch_number": str(item.get("batch_number") or "").strip(),
        "manufacturing_date": _normalize_date(str(item.get("manufacturing_date") or "")),
        "expiry_date": _normalize_date(str(item.get("expiry_date") or "")),
        "hsn_code": str(item.get("hsn_code") or "3004").strip(),
        "gst_rate": _safe_float(item.get("gst_rate"), default=12.0),
        "confidence": _safe_float(item.get("confidence"), default=1.0),
        "notes": str(item.get("notes") or "").strip()
    }


def validate_invoice_data(data: dict) -> bool:
    """
    Validates parsed invoice JSON structures.
    Requires at least one item row to pass.
    """
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return False
    first_item = items[0]
    if not isinstance(first_item, dict) or not first_item.get("product_name"):
        return False
    return True


def scan_invoice(image_path: str) -> dict:
    """
    Scan supplier invoice using Gemini Vision.
    Features image optimization, schema validation, and retry logic.
    """
    start_time = time.time()
    
    # 1. Optimize Image (Resize & Compress)
    optimize_image(image_path)

    image_file = Path(image_path)
    if not image_file.exists():
        logger.error(f"[OCR] File not found: {image_path}")
        return {
            "success": False,
            "data": None,
            "error": "Image file not found."
        }

    mime_type, _ = mimetypes.guess_type(image_file)
    if mime_type is None:
        mime_type = "application/pdf" if image_file.suffix.lower() == ".pdf" else "image/jpeg"

    image_bytes = image_file.read_bytes()
    logger.info(f"[OCR:START] Scanning invoice document: {image_path} ({len(image_bytes)} bytes, mime: {mime_type})")

    last_error = None
    target_model = GEMINI_PRIMARY_MODEL

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=target_model,
                contents=[
                    INVOICE_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )

            raw_text = response.text or "{}"
            logger.info(f"[OCR:RAW_RESPONSE]\n{raw_text}")

            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text, flags=re.IGNORECASE)
                cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

            result = json.loads(cleaned_text)

            # Validate invoice structure
            if not validate_invoice_data(result):
                raise ValueError("Extracted invoice JSON failed schema validation (no items found).")

            # Extract header metadata
            raw_inv_date = result.get("invoice_date", "")
            norm_inv_date = _normalize_date(str(raw_inv_date))
            
            raw_total = _safe_float(result.get("total_amount") or result.get("grand_total") or result.get("net_amount"))
            raw_subtotal = _safe_float(result.get("subtotal"))
            raw_tax = _safe_float(result.get("tax_amount"))

            raw_items = result.get("items", [])
            normalized_items = [_normalize_item(it) for it in raw_items if isinstance(it, dict)]

            # Compute total if missing
            if raw_total == 0.0 and normalized_items:
                raw_total = round(sum(it["total_price"] for it in normalized_items), 2)

            invoice = {
                "supplier_name": str(result.get("supplier_name") or "").strip(),
                "supplier_gstin": str(result.get("supplier_gstin") or "").strip(),
                "supplier_phone": str(result.get("supplier_phone") or "").strip(),
                "supplier_email": str(result.get("supplier_email") or "").strip(),
                "supplier_address": str(result.get("supplier_address") or "").strip(),
                "invoice_number": str(result.get("invoice_number") or "").strip(),
                "invoice_date": norm_inv_date,
                "total_amount": raw_total,
                "subtotal": raw_subtotal,
                "tax_amount": raw_tax,
                "items": normalized_items
            }

            logger.info(
                f"[OCR:SUCCESS] Extracted Invoice: #{invoice['invoice_number']} | Date: {invoice['invoice_date']} | "
                f"Supplier: '{invoice['supplier_name']}' | Total: ₹{invoice['total_amount']} | Line Items: {len(normalized_items)}"
            )

            latency = time.time() - start_time
            in_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            out_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            
            log_ai_metrics("/documents/{id}/ocr", "invoice", target_model, True, False, latency, in_tokens, out_tokens)

            return {
                "success": True,
                "data": invoice,
                "error": None
            }

        except Exception as e:
            last_error = str(e)
            logger.warning(f"[OCR_WARNING] Model {target_model} attempt {attempt+1} failed: {e}")
            
            is_transient = any(code in last_error for code in ("429", "503", "500", "UNAVAILABLE"))
            if not is_transient:
                break
            time.sleep(0.5 * (2 ** attempt))

    # All attempts failed
    latency = time.time() - start_time
    log_ai_metrics("/documents/{id}/ocr", "invoice", GEMINI_PRIMARY_MODEL, False, False, latency, error=last_error)
    return {
        "success": False,
        "data": None,
        "error": "Dawaiflow AI was unable to parse this invoice. Please ensure the image is clear or upload an Excel/CSV file."
    }