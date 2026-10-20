import json
import mimetypes
import os
import time
import re
import logging
from pathlib import Path
from typing import Union, Optional, List, Dict, Any
from PIL import Image
import cv2
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

logger = logging.getLogger("expiryguard.ai")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

API_KEY = os.getenv("GEMINI_API_KEY")

class _LazyGeminiClientProxy:
    """
    Lazy proxy for google.genai.Client to ensure the backend starts up successfully
    even if GEMINI_API_KEY is not immediately configured in production environment variables.
    """
    _instance = None

    def _get_client(self):
        if self._instance is not None:
            return self._instance
        key = os.getenv("GEMINI_API_KEY")
        if not key or key.strip().lower().startswith("your_") or "placeholder" in key.lower():
            raise ValueError(
                "GEMINI_API_KEY is missing or invalid. Please configure a valid Google Gemini API Key in your environment variables."
            )
        self._instance = genai.Client(api_key=key.strip())
        return self._instance

    def __getattr__(self, name):
        return getattr(self._get_client(), name)

client = _LazyGeminiClientProxy()
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.8-flash")

def log_ai_metrics(
    endpoint: str,
    action: str,
    model: str,
    success: bool,
    fallback_used: bool = False,
    latency: float = 0.0,
    in_tokens: int = 0,
    out_tokens: int = 0,
    error: Optional[str] = None,
):
    """Logs AI inference metrics for latency, token counts, and errors."""
    status_str = "SUCCESS" if success else "FAILED"
    logger.info(
        f"[AI_METRICS] {endpoint} | Action: {action} | Model: {model} | Status: {status_str} | "
        f"Latency: {latency:.2f}s | InTokens: {in_tokens} | OutTokens: {out_tokens}"
        + (f" | Error: {error}" if error else "")
    )

# Centralized Barcode/QR Code Map (Cost-Saving Interceptor)
BARCODE_MAP = {
    "8901138510839": {
        "product_name": "Dolo 650 Tablet",
        "brand": "Micro Labs",
        "batch_number": "B23491",
        "manufacturing_date": "2026-03-01",
        "expiry_date": "2029-03-01",
        "missing_fields": []
    },
    "8901089006000": {
        "product_name": "Crocin Advance",
        "brand": "GlaxoSmithKline",
        "batch_number": "C89211",
        "manufacturing_date": "2026-01-01",
        "expiry_date": "2028-12-01",
        "missing_fields": []
    }
}

PROMPT = """
You are an expert Indian pharmaceutical product label and package reader.

Extract ONLY the following information from the product label/package.

Return ONLY valid JSON.

Fields:
1. product_name: Full medicine name including strength/dosage if visible (e.g. Paracetamol 500mg)
2. brand: Manufacturer / Company / Marketing company name
3. batch_number: Batch or Lot number (e.g. B23491, BATCH No. ABC123)
4. manufacturing_date: Mfd date as YYYY-MM-DD or YYYY-MM-01 if month/year only
5. expiry_date: Expiry date as YYYY-MM-DD or YYYY-MM-01 if MM/YY or MM/YYYY
6. mrp: Maximum Retail Price printed on package (numeric float value like 35.0, 42.50, 120.0).

Price / MRP Rules:
- Look specifically for "MRP", "M.R.P.", "Max Retail Price", "Rs.", "₹", "INR", "Inclusive of all taxes".
- Do NOT assume the first number on package is MRP (e.g. don't confuse 500mg, 10's, HSN 3004 or batch numbers with MRP).
- Handle decimal MRPs correctly (e.g., ₹35.00 -> 35.0, Rs. 42.50 -> 42.5).
- If MRP cannot be confidently detected, return null. Do NOT guess or hallucinate.

Date Rules:
- Complete date: 25/11/2027 -> 2027-11-25
- Month/Year only: 11/2027 -> 2027-11-01

Output format:
{
  "product_name": "...",
  "brand": "...",
  "batch_number": "...",
  "manufacturing_date": "...",
  "expiry_date": "...",
  "mrp": null
}
"""

def optimize_image_bytes(image_bytes: bytes, max_size=(2560, 2560), quality=90) -> bytes:
    """
    Resizes and compresses raw image bytes in-memory using PIL / BytesIO.
    Preserves high resolution for multi-item billing & purchase invoice OCR.
    """
    try:
        import io
        if len(image_bytes) < 800 * 1024:  # If less than 800KB, skip to preserve raw clarity
            return image_bytes

        with Image.open(io.BytesIO(image_bytes)) as img:
            original_format = img.format or "JPEG"
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            output_io = io.BytesIO()
            save_format = "JPEG" if original_format in {"MPO", "PNG", "WEBP"} else original_format
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            img.save(output_io, format=save_format, quality=quality, optimize=True)
            return output_io.getvalue()
    except Exception as e:
        logger.warning(f"[IN-MEMORY OPTIMIZATION FAILED] {e}")
        return image_bytes

def optimize_image(file_path: Union[str, Path, bytes], max_size: tuple = (1600, 1600), quality: int = 85) -> Union[str, Path, bytes]:
    """
    Safely resizes and compresses image to speed up Gemini API processing while preserving text clarity.
    Supports file paths and raw byte strings.
    """
    try:
        if isinstance(file_path, bytes):
            return file_path
        
        path_str = str(file_path)
        if not os.path.exists(path_str) or path_str.lower().endswith(".pdf"):
            return file_path
        
        file_size = os.path.getsize(path_str)
        if file_size < 800 * 1024:
            return file_path

        with Image.open(path_str) as img:
            original_format = img.format or "JPEG"
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            save_format = "JPEG" if original_format == "MPO" else original_format
            img.save(path_str, format=save_format, quality=quality, optimize=True)
            
        new_size = os.path.getsize(path_str)
        logger.info(f"[IMAGE OPTIMIZATION] Optimized '{os.path.basename(path_str)}' from {file_size/1024:.1f}KB to {new_size/1024:.1f}KB")
    except Exception as e:
        logger.warning(f"[IMAGE OPTIMIZATION FAILED] {e}")
    return file_path


def detect_and_lookup_barcode(image_input: Union[str, Path, bytes]) -> dict | None:
    """
    Decodes barcode/QR code from the image using OpenCV.
    If match is found in the static map, returns the metadata immediately.
    """
    try:
        if isinstance(image_input, bytes):
            nparr = np.frombuffer(image_input, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        else:
            path_str = str(image_input)
            if path_str.lower().endswith(".pdf"):
                return None
            img = cv2.imread(path_str)

        if img is None:
            return None

        # Try Barcode Detector
        detector = cv2.barcode.BarcodeDetector()
        retval, decoded_info, decoded_type, points = detector.detectAndDecode(img)
        if retval and decoded_info:
            for code in decoded_info:
                clean_code = str(code).strip()
                if clean_code in BARCODE_MAP:
                    logger.info(f"[BARCODE] Decoded barcode '{clean_code}' from image. Direct match found.")
                    return BARCODE_MAP[clean_code]

        # Try QR Code Detector
        qr_detector = cv2.QRCodeDetector()
        val, qr_points, qr_straight = qr_detector.detectAndDecode(img)
        if val:
            clean_qr = str(val).strip()
            if clean_qr in BARCODE_MAP:
                logger.info(f"[QR CODE] Decoded QR '{clean_qr}' from image. Direct match found.")
                return BARCODE_MAP[clean_qr]
    except Exception as e:
        logger.warning(f"[BARCODE DETECTION FAILED] {e}")
def validate_label_data(data: dict) -> bool:
    """Validates extracted medicine label dictionary."""
    if not isinstance(data, dict):
        return False
    if data.get("product_name") or data.get("brand") or data.get("name"):
        return True
    return False


def scan_label(image_input: Union[str, Path, bytes], raw_bytes: Optional[bytes] = None, user_id: Optional[int] = None) -> dict:
    """
    Scan a product label using Gemini Vision.
    Implements barcode lookup, image optimization, schema validation, and retry logic.
    Supports both file paths (str/Path) and in-memory raw bytes.
    """
    start_time = time.time()
    mime_type = "image/jpeg"
    
    # 1. Barcode-First Interception
    barcode_data = detect_and_lookup_barcode(image_input if not raw_bytes else raw_bytes)
    if barcode_data:
        latency = time.time() - start_time
        log_ai_metrics("/scan-label", "label", "local-barcode-db", True, False, latency, 0, 0)
        return {
            "success": True,
            "needs_manual_review": False,
            "data": barcode_data,
            "error": None
        }

    # 2. Image Byte Acquisition
    if isinstance(image_input, bytes):
        image_bytes = optimize_image_bytes(image_input)
    elif raw_bytes is not None:
        image_bytes = optimize_image_bytes(raw_bytes)
    elif isinstance(image_input, (str, Path)):
        optimize_image(image_input)
        image_file = Path(image_input)
        if not image_file.exists():
            return {
                "success": False,
                "needs_manual_review": True,
                "data": None,
                "error": "Image file not found."
            }
        mime_guess, _ = mimetypes.guess_type(str(image_file))
        mime_type = mime_guess or "image/jpeg"
        image_bytes = image_file.read_bytes()
    else:
        return {
            "success": False,
            "needs_manual_review": True,
            "data": None,
            "error": "No valid image input provided."
        }

    target_model = GEMINI_PRIMARY_MODEL
    logger.info(f"[START_SALE_LABEL:TRY] Invoking Gemini Vision label scan with model: {target_model}")

    try:
        response = client.models.generate_content(
            model=target_model,
            contents=[
                PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            ],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )

        from ai import usage_log
        usage_log.record_response(response, feature="scan_label", outcome="success", shop_id=user_id,
                                  model=target_model, latency_ms=int((time.time() - start_time) * 1000))
        raw_text = response.text or ""
        # Strip potential markdown wrapper fences
        if raw_text.strip().startswith("```"):
            raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text.strip(), flags=re.IGNORECASE)
            raw_text = re.sub(r"\s*```$", "", raw_text)

        data = json.loads(raw_text)

        # Validate data schema
        if not validate_label_data(data):
            raise ValueError("Extracted JSON failed schema validation (missing product_name).")

        # Parse missing fields
        required_fields = ["product_name", "brand", "batch_number", "manufacturing_date", "expiry_date"]
        missing_fields = []
        for field in required_fields:
            value = data.get(field)
            if value is None or (isinstance(value, str) and value.strip() == ""):
                data[field] = None
                missing_fields.append(field)

        data["missing_fields"] = missing_fields

        # Success path
        latency = time.time() - start_time
        in_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        out_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
        
        log_ai_metrics("/scan-label", "label", target_model, True, False, latency, in_tokens, out_tokens)
        
        return {
            "success": True,
            "needs_manual_review": len(missing_fields) > 0,
            "data": data,
            "error": None,
        }

    except Exception as e:
        latency = time.time() - start_time
        logger.error(f"[SCAN_LABEL_ERROR] Model {target_model} scan failed: {e}")
        log_ai_metrics("/scan-label", "label", target_model, False, False, latency, error=str(e))
        return {
            "success": False,
            "needs_manual_review": True,
            "data": None,
            "error": f"DawaiFlow AI could not extract medicine details: {e}",  # internal: the route hides it from the client
        }