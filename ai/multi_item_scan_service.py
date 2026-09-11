import json
import mimetypes
import os
import time
import re
import logging
from pathlib import Path

from google.genai import types

from ai.gemini_service import (
    client,
    GEMINI_PRIMARY_MODEL,
    log_ai_metrics,
    optimize_image,
    optimize_image_bytes,
)

logger = logging.getLogger("expiryguard.multi_item")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


MULTI_ITEM_PROMPT = """You are an expert Indian pharmaceutical vision reader for retail pharmacy billing.

Analyze this photo containing 1 to 7 distinct medicine packages, strips, boxes, or bottles.

Identify every distinct medicine visible in the image.

For each medicine, visually inspect the packaging and extract ONLY:
1. name: The PROMINENT COMMERCIAL BRAND / TRADE NAME printed in large, bold letters on the packaging (e.g. "PRE-ESO", "Dolo", "Pan", "Augmentin", "Crocin Advance", "Azithral").
   - CRITICAL: DO NOT return the smaller generic/salt chemical formulation (e.g. "Esomeprazole Gastro Resistant Tablets IP", "Paracetamol Tablets IP") as the medicine name when a clear commercial brand name exists.
2. strength: Strength or dosage variant (e.g. "40 mg", "650 mg", "625 mg", "500 mg"). If not visible, return null.
3. generic_name: The chemical composition / active salt name if visible (e.g. "Esomeprazole", "Paracetamol", "Amoxicillin and Potassium Clavulanate"). If not visible, return null.
4. batch: The Batch number or Lot number printed or embossed on the packaging (e.g. "ABC123", "B23491", "DL102").
   - CRITICAL: Distinguish batch number strictly from MFG/MFD dates, EXP dates, MRP prices (₹, Rs.), licence numbers, barcodes, and phone numbers.
   - If not clearly and confidently readable, return null. NEVER guess or hallucinate a batch number.
5. expiry: Expiry date printed on the packaging.
   - Recognize formats such as EXP 08/27, EXP 08/2027, EXPIRY 08/27, EXP DATE 08/2027.
   - Normalize to YYYY-MM or YYYY-MM-DD (e.g. "2027-08" or "2027-08-01").
   - CRITICAL: Never confuse MFG or MFD (manufacturing date) with EXP (expiry date).
   - If not clearly readable, return null. NEVER guess or hallucinate an expiry date.
6. pack_size: Strip count or pack size if visible (e.g. "10 Tablets", "15's", "100 ml"). If not visible, return null.
7. code: Barcode number, GTIN, or product code if visible. If not visible, return null.

CRITICAL RULES:
- Do NOT merge separate medicines into one item.
- Return separate items for every distinct package or strip visible (up to 7 items).
- Never invent or hallucinate batch numbers or expiry dates. Use null if unclear.
- No markdown commentary or extra text. Return ONLY valid JSON in this format:

{
  "medicines": [
    {
      "name": "string",
      "strength": "string or null",
      "generic_name": "string or null",
      "batch": "string or null",
      "expiry": "string or null",
      "pack_size": "string or null",
      "code": "string or null"
    }
  ]
}
"""


def detect_barcodes_from_bytes(image_bytes: bytes) -> list[str]:
    """
    Extracts all visible 1D barcodes and 2D QR codes from raw image bytes using OpenCV.
    Runs locally in <20ms to provide instant, 100% confidence barcode identification.
    """
    found_codes = []
    try:
        import numpy as np
        import cv2

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return []

        # 1. Multi-barcode detector
        try:
            bd = cv2.barcode.BarcodeDetector()
            retval, decoded_info, decoded_types, points = bd.detectAndDecodeMulti(img)
            if retval and decoded_info:
                for code in decoded_info:
                    clean = str(code).strip()
                    if clean and clean not in found_codes:
                        found_codes.append(clean)
        except Exception as e:
            logger.debug(f"[BARCODE_MULTI_DETECTION_DEBUG] {e}")

        # 2. Multi-QR code detector
        try:
            qrd = cv2.QRCodeDetector()
            retval, decoded_info, points, straight_qrcode = qrd.detectAndDecodeMulti(img)
            if retval and decoded_info:
                for code in decoded_info:
                    clean = str(code).strip()
                    if clean and clean not in found_codes:
                        found_codes.append(clean)
        except Exception as e:
            logger.debug(f"[QR_MULTI_DETECTION_DEBUG] {e}")

    except Exception as e:
        logger.warning(f"[BARCODE_SCAN_ERROR] {e}")

    return found_codes


def _clean_json_text(text: str) -> str:
    """Removes accidental Markdown fences from Gemini output."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def _clean_str(val) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    return s


def validate_multi_item_data(data: dict) -> bool:
    """Validates that multi-item scanner output is structured correctly."""
    if not isinstance(data, dict):
        return False
    if "medicines" in data and isinstance(data["medicines"], list):
        return True
    if "items" in data and isinstance(data["items"], list):
        return True
    return False


def scan_multi_item(image_path: str | None = None, raw_bytes: bytes | None = None, mime_type: str = "image/jpeg") -> dict:
    """
    Scans one image containing 1-7 medicines using OpenCV multi-barcode + gemini-3.1-flash-lite.
    Supports direct in-memory raw_bytes processing to avoid disk I/O latency.
    Zero fallback cascade, non-thinking configuration, fast visual OCR extraction.
    """
    start_time = time.time()
    
    # 1. In-memory or file-based byte acquisition
    comp_start = time.time()
    if raw_bytes is not None:
        image_bytes = optimize_image_bytes(raw_bytes)
    elif image_path is not None:
        optimize_image(image_path)
        image_file = Path(image_path)
        if not image_file.exists():
            return {
                "success": False,
                "items": [],
                "detected_barcodes": [],
                "error": "Image file not found.",
                "latency": 0.0,
            }
        mime_type, _ = mimetypes.guess_type(str(image_file))
        mime_type = mime_type or "image/jpeg"
        image_bytes = image_file.read_bytes()
    else:
        return {
            "success": False,
            "items": [],
            "detected_barcodes": [],
            "error": "No image input provided.",
            "latency": 0.0,
        }

    comp_latency = (time.time() - comp_start) * 1000.0
    logger.info(f"[PERF] Image compression & preparation: {comp_latency:.2f}ms")

    # 2. Barcode-First Interception: Run OpenCV multi-barcode detector
    bc_start = time.time()
    detected_barcodes = detect_barcodes_from_bytes(image_bytes)
    bc_latency = (time.time() - bc_start) * 1000.0
    if detected_barcodes:
        logger.info(f"[BARCODE_FIRST] Detected {len(detected_barcodes)} barcode(s) in {bc_latency:.1f}ms: {detected_barcodes}")

    last_error = None
    target_model = GEMINI_PRIMARY_MODEL  # gemini-3.1-flash-lite

    # Non-thinking configuration for maximum OCR speed
    thinking_config = None
    try:
        thinking_config = types.ThinkingConfig(thinking_budget=0)
    except Exception:
        pass

    for attempt in range(2):
        try:
            config_args = {
                "temperature": 0.0,
                "response_mime_type": "application/json",
            }
            if thinking_config:
                config_args["thinking_config"] = thinking_config

            config = types.GenerateContentConfig(**config_args)

            gemini_start = time.time()
            response = client.models.generate_content(
                model=target_model,
                contents=[
                    MULTI_ITEM_PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=config,
            )
            gemini_latency = time.time() - gemini_start

            raw_text = response.text or ""
            cleaned_text = _clean_json_text(raw_text)
            parsed = json.loads(cleaned_text)

            # Validate schema
            if not validate_multi_item_data(parsed):
                raise ValueError("Multi-item scan output failed schema validation.")

            raw_items = parsed.get("medicines") or parsed.get("items") or []
            extracted_items = []
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                name = _clean_str(item.get("name"))
                code = _clean_str(item.get("code"))
                strength = _clean_str(item.get("strength"))
                generic_name = _clean_str(item.get("generic_name"))
                batch = _clean_str(item.get("batch"))
                expiry = _clean_str(item.get("expiry"))
                pack_size = _clean_str(item.get("pack_size"))
                form = _clean_str(item.get("form"))

                # Keep item if at least name or code is present
                if name or code:
                    extracted_items.append({
                        "name": name,
                        "code": code,
                        "strength": strength,
                        "generic_name": generic_name,
                        "batch": batch,
                        "expiry": expiry,
                        "pack_size": pack_size,
                        "form": form,
                    })

            total_latency = time.time() - start_time
            in_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
            out_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
            
            log_ai_metrics(
                "/scan-multi-item",
                "multi_item_ocr",
                target_model,
                True,
                False,
                total_latency,
                in_tokens,
                out_tokens
            )

            logger.info(
                f"[MULTI_ITEM_SCAN] Success: detected {len(extracted_items)} items | "
                f"Gemini Latency: {gemini_latency:.2f}s | Total Latency: {total_latency:.2f}s"
            )

            return {
                "success": True,
                "items": extracted_items,
                "detected_barcodes": detected_barcodes,
                "error": None,
                "primary_engine": "Dawaiflow AI",
                "gemini_latency": gemini_latency,
                "ocr_latency": 0.0,
                "total_latency": total_latency,
            }

        except Exception as exc:
            last_error = str(exc)
            logger.warning(f"[MULTI_ITEM_WARNING] Model {target_model} attempt {attempt+1} failed: {exc}")
            
            is_transient = any(code in last_error for code in ("503", "429", "500", "UNAVAILABLE"))
            if not is_transient:
                break
            time.sleep(0.3)

    # Failed without invoking fallback model
    total_latency = time.time() - start_time
    log_ai_metrics(
        "/scan-multi-item",
        "multi_item_ocr",
        target_model,
        False,
        False,
        total_latency,
        error=last_error
    )
    return {
        "success": False,
        "items": [],
        "detected_barcodes": detected_barcodes,
        "error": last_error or "Failed to extract medicine information from image.",
        "primary_engine": "Dawaiflow AI",
        "gemini_latency": 0.0,
        "ocr_latency": 0.0,
        "total_latency": total_latency,
    }