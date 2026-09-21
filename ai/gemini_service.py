import json
import mimetypes
import os
import time
import re
import logging
from pathlib import Path
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
GEMINI_PRIMARY_MODEL = os.getenv("GEMINI_PRIMARY_MODEL", "gemini-2.5-flash-lite")

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

def optimize_image_bytes(image_bytes: bytes, max_size=(1024, 1024), quality=70) -> bytes:
    """
    Resizes and compresses raw image bytes in-memory using PIL / BytesIO.
    Avoids disk read/write overhead for maximum pipeline speed.
    """
    try:
        import io
        if len(image_bytes) < 150 * 1024:  # If less than 150KB, skip to save CPU
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

def optimize_image(file_path: str, max_size=(1600, 1600), quality=80) -> str:
    """
    Resizes image if dimensions exceed max_size, and compresses it.
    Modifies the file in-place to reduce upload payload and token footprint.
    """
    try:
        if not os.path.exists(file_path) or file_path.lower().endswith(".pdf"):
            return file_path
        
        file_size = os.path.getsize(file_path)
        if file_size < 300 * 1024:  # If less than 300KB, skip to avoid over-compression
            return file_path

        with Image.open(file_path) as img:
            original_format = img.format or "JPEG"
            if img.width > max_size[0] or img.height > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # Avoid saving MPO format directly
            save_format = "JPEG" if original_format == "MPO" else original_format
            img.save(file_path, format=save_format, quality=quality, optimize=True)
            
        new_size = os.path.getsize(file_path)
        logger.info(f"[IMAGE OPTIMIZATION] Optimized '{os.path.basename(file_path)}' from {file_size/1024:.1f}KB to {new_size/1024:.1f}KB")
    except Exception as e:
        logger.warning(f"[IMAGE OPTIMIZATION FAILED] {e}")
    return file_path

def detect_and_lookup_barcode(image_path: str) -> dict | None:
    """
    Decodes barcode/QR code from the image using OpenCV.
    If match is found in the static map, returns the metadata immediately (saves API cost).
    """
    try:
        if image_path.lower().endswith(".pdf"):
            return None

        img = cv2.imread(image_path)
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
    return None

def log_ai_metrics(
    endpoint: str,
    scan_type: str,
    model_used: str,
    success: bool,
    fallback_used: bool,
    latency: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error: str = None
):
    """Logs detailed performance, cost, and usage metrics of AI operations."""
    logger.info(
        f"[AI_METRIC] Endpoint: {endpoint} | Scan Type: {scan_type} | Model: {model_used} | "
        f"Success: {success} | Fallback: {fallback_used} | Latency: {latency:.2f}s | "
        f"Tokens: In={input_tokens}, Out={output_tokens} | Error: {error}"
    )

def validate_label_data(data: dict) -> bool:
    """Validates that extracted medicine data matches minimum required format."""
    if not isinstance(data, dict):
        return False
    # If product name is missing or blank, the scan failed to recognize the medicine strip
    if not data.get("product_name") or not isinstance(data["product_name"], str) or not data["product_name"].strip():
        return False
    return True

def scan_label(image_path: str) -> dict:
    """
    Scan a product label using Gemini Vision.
    Implements barcode lookup, image optimization, schema validation, and retry logic.
    """
    start_time = time.time()
    
    # 1. Barcode-First Interception (100% Cost Saving)
    barcode_data = detect_and_lookup_barcode(image_path)
    if barcode_data:
        latency = time.time() - start_time
        log_ai_metrics("/scan-label", "label", "local-barcode-db", True, False, latency, 0, 0)
        return {
            "success": True,
            "needs_manual_review": False,
            "data": barcode_data,
            "error": None
        }

    # 2. Image Resizing & Compression
    optimize_image(image_path)

    image_file = Path(image_path)
    if not image_file.exists():
        return {
            "success": False,
            "needs_manual_review": True,
            "data": None,
            "error": "Image file not found."
        }

    mime_type, _ = mimetypes.guess_type(image_file)
    mime_type = mime_type or "image/jpeg"
    image_bytes = image_file.read_bytes()

    last_error = None
    target_model = GEMINI_PRIMARY_MODEL

    for attempt in range(2):
        try:
            config = types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json"
            )

            response = client.models.generate_content(
                model=target_model,
                contents=[
                    PROMPT,
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                ],
                config=config,
            )

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
            last_error = str(e)
            logger.warning(f"[SCAN_LABEL_WARNING] Model {target_model} attempt {attempt+1} failed: {e}")
            
            # Check for rate limit or server errors for quick retry
            is_transient = any(code in last_error for code in ("429", "503", "500", "UNAVAILABLE"))
            if not is_transient:
                break
            time.sleep(0.5 * (2 ** attempt))

    # All attempts failed or produced invalid schemas
    latency = time.time() - start_time
    log_ai_metrics("/scan-label", "label", GEMINI_PRIMARY_MODEL, False, False, latency, error=last_error)
    return {
        "success": False,
        "needs_manual_review": True,
        "data": None,
        "error": "Dawaiflow AI couldn't extract medicine details. Please try again or enter manually.",
    }