import json
import logging
import mimetypes
import os
import re
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from ai.prompts.invoice_prompt import INVOICE_PROMPT

logger = logging.getLogger("expiryguard.ocr")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

API_KEY = os.getenv("GEMINI_API_KEY")
INVOICE_MODEL = os.getenv("GEMINI_INVOICE_MODEL", "gemini-3.6-flash")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

client = genai.Client(api_key=API_KEY)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value in ("", None):
            return default
        # Remove currency symbols or commas if present
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
    Examples:
      - '2026-07-29' -> '2026-07-29'
      - '29-07-2026' or '29/07/2026' -> '2026-07-29'
      - '3/28' or '03/28' -> '2028-03-01'
      - '09/2028' -> '2028-09-01'
    """
    if not date_str or not isinstance(date_str, str):
        return ""
    
    clean = date_str.strip()
    
    # 1. Already YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        return clean
    
    # 2. DD-MM-YYYY or DD/MM/YYYY
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    
    # 3. MM/YY or MM-YY (e.g., 3/28 -> 2028-03-01)
    m = re.match(r"^(\d{1,2})[-/](\d{2})$", clean)
    if m:
        month, short_year = int(m.group(1)), int(m.group(2))
        full_year = 2000 + short_year
        return f"{full_year:04d}-{month:02d}-01"
    
    # 4. MM/YYYY or MM-YYYY (e.g., 09/2028 -> 2028-09-01)
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


def scan_invoice(image_path: str) -> dict:
    """
    Scan supplier invoice using Gemini Vision.
    Returns:
    {
        "success": bool,
        "data": {
            "supplier_name": str,
            "supplier_gstin": str,
            "invoice_number": str,
            "invoice_date": str,
            "total_amount": float,
            "subtotal": float,
            "tax_amount": float,
            "items": list[dict]
        },
        "error": str | None
    }
    """
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
        if image_file.suffix.lower() == ".pdf":
            mime_type = "application/pdf"
        else:
            mime_type = "image/jpeg"

    image_bytes = image_file.read_bytes()
    logger.info(f"[OCR:START] Scanning invoice document: {image_path} ({len(image_bytes)} bytes, mime: {mime_type}) using {INVOICE_MODEL}")

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=INVOICE_MODEL,
                contents=[
                    INVOICE_PROMPT,
                    types.Part.from_bytes(
                        data=image_bytes,
                        mime_type=mime_type,
                    ),
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                ),
            )

            raw_text = response.text or "{}"
            logger.info(f"[OCR:RAW_RESPONSE]\n{raw_text}")

            # Clean potential code block fences if any slipped through
            cleaned_text = raw_text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r"^```(?:json)?\s*", "", cleaned_text)
                cleaned_text = re.sub(r"\s*```$", "", cleaned_text)

            result = json.loads(cleaned_text)

            # Extract header metadata
            raw_inv_date = result.get("invoice_date", "")
            norm_inv_date = _normalize_date(str(raw_inv_date))
            
            raw_total = _safe_float(result.get("total_amount") or result.get("grand_total") or result.get("net_amount"))
            raw_subtotal = _safe_float(result.get("subtotal"))
            raw_tax = _safe_float(result.get("tax_amount"))

            raw_items = result.get("items", [])
            if not isinstance(raw_items, list):
                raw_items = []

            normalized_items = [_normalize_item(it) for it in raw_items if isinstance(it, dict)]

            # If total_amount wasn't detected but items have prices, compute sum
            if raw_total == 0.0 and normalized_items:
                raw_total = round(sum(it["total_price"] for it in normalized_items), 2)

            invoice = {
                "supplier_name": str(result.get("supplier_name") or "").strip(),
                "supplier_gstin": str(result.get("supplier_gstin") or "").strip(),
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

            return {
                "success": True,
                "data": invoice,
                "error": None
            }

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[OCR:ATTEMPT_{attempt+1}_FAILED] {error_msg}")
            if "429" in error_msg and attempt < 2:
                time.sleep(2 ** attempt)
                continue

            logger.error(f"[OCR:FINAL_ERROR] Failed to extract invoice: {error_msg}")
            return {
                "success": False,
                "data": None,
                "error": error_msg
            }