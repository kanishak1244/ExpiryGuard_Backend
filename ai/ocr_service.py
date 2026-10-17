"""
ai/ocr_service.py
High-Accuracy Pure OCR & Computer Vision Pipeline for Indian Pharmacy Packaging.
STRICTLY FOR SELLING / BILLING WORKFLOW.
ALL GEMINI CALLS ARE 100% PAUSED / DISABLED.
"""

import re
import time
import logging
import hashlib
import threading
from collections import OrderedDict
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import cv2

logger = logging.getLogger("expiryguard.ocr_service")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Persistent Singleton for PaddleOCR to avoid re-initialization penalty
_PADDLE_OCR_ENGINE = None
_PADDLE_LOCK = threading.Lock()

# In-memory LRU cache for frame deduplication (size 64)
_IMAGE_CACHE_LOCK = threading.Lock()
_IMAGE_CACHE: OrderedDict[str, Dict[str, Any]] = OrderedDict()
MAX_CACHE_SIZE = 64


def get_cached_scan(raw_bytes: bytes) -> Optional[Dict[str, Any]]:
    """Returns cached OCR scan result if raw image bytes have been processed previously."""
    h = hashlib.sha256(raw_bytes).hexdigest()
    with _IMAGE_CACHE_LOCK:
        if h in _IMAGE_CACHE:
            _IMAGE_CACHE.move_to_end(h)
            logger.info(f"[OCR-DEDUPE] Returning cached OCR scan for image hash: {h[:12]}")
            return _IMAGE_CACHE[h]
    return None


def set_cached_scan(raw_bytes: bytes, result: Dict[str, Any]) -> None:
    """Caches scan result by SHA256 image fingerprint."""
    h = hashlib.sha256(raw_bytes).hexdigest()
    with _IMAGE_CACHE_LOCK:
        if len(_IMAGE_CACHE) >= MAX_CACHE_SIZE:
            _IMAGE_CACHE.popitem(last=False)
        _IMAGE_CACHE[h] = result


MONTH_NAME_TO_NUM = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    "january": "01", "february": "02", "march": "03", "april": "04",
    "june": "06", "july": "07", "august": "08", "september": "09",
    "october": "10", "november": "11", "december": "12",
}


def get_ocr_engine():
    """
    Initializes or returns the persistent thread-safe singleton PaddleOCR engine.
    Optimized:
    - PP-OCRv4 Mobile detection & recognition (~400ms CPU inference)
    - Document unwarping (UVDoc) and document orientation classification disabled for speed
    - Text detection limit side length set to 960 for optimal packaging character clarity
    """
    global _PADDLE_OCR_ENGINE
    if _PADDLE_OCR_ENGINE is None:
        with _PADDLE_LOCK:
            if _PADDLE_OCR_ENGINE is None:
                start_t = time.time()
                from paddleocr import PaddleOCR
                logger.info("[OCR_SERVICE] Initializing optimized PaddleOCR PP-OCRv4 mobile engine...")
                _PADDLE_OCR_ENGINE = PaddleOCR(
                    lang='en',
                    ocr_version='PP-OCRv4',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=True,
                    text_det_limit_side_len=960,
                )
                logger.info(f"[OCR_SERVICE] PaddleOCR PP-OCRv4 mobile initialized in {time.time() - start_t:.2f}s")
    return _PADDLE_OCR_ENGINE


# =====================================================================
# 1. IMAGE QUALITY & PREPROCESSING
# =====================================================================

def check_image_quality(gray_img: np.ndarray) -> Dict[str, Any]:
    """Evaluates blurriness (Laplacian variance) and lighting conditions."""
    laplacian_var = float(cv2.Laplacian(gray_img, cv2.CV_64F).var())
    mean_brightness = float(np.mean(gray_img))
    return {
        "laplacian_var": laplacian_var,
        "is_blurry": laplacian_var < 60.0,
        "brightness": mean_brightness,
        "is_low_light": mean_brightness < 70.0,
        "is_overexposed": mean_brightness > 215.0,
    }


def preprocess_image(img_bgr: np.ndarray) -> Tuple[np.ndarray, Dict[str, Any]]:
    """
    Dynamically applies computer vision preprocessing based on image quality:
    - Downscales giant images to max 1200px for optimal OCR speed (< 1s).
    - FAST PATH: If quality is already sharp and balanced, avoids expensive filters.
    - Glare attenuation for reflective aluminum blister foil.
    - CLAHE adaptive contrast enhancement for low-light packaging.
    - Bilateral filtering to preserve crisp character edges.
    """
    h, w = img_bgr.shape[:2]
    max_dim = 1600
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    quality = check_image_quality(gray)

    # FAST PATH: Skip expensive filtering if image is already sharp and evenly lit
    if not quality["is_low_light"] and not quality["is_overexposed"] and quality["laplacian_var"] >= 120.0:
        return img_bgr, quality

    processed = img_bgr.copy()

    # 1. Glare Attenuation (Reflective Blister Foil)
    if quality["is_overexposed"] or np.max(gray) > 250:
        glare_mask = cv2.threshold(gray, 245, 255, cv2.THRESH_BINARY)[1]
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        glare_mask = cv2.dilate(glare_mask, kernel, iterations=1)
        processed[glare_mask > 0] = (processed[glare_mask > 0] * 0.75).astype(np.uint8)

    # 2. Low-light / Contrast Enhancement (CLAHE)
    if quality["is_low_light"] or quality["laplacian_var"] < 120.0:
        lab = cv2.cvtColor(processed, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
        l_enhanced = clahe.apply(l_channel)
        lab_enhanced = cv2.merge((l_enhanced, a_channel, b_channel))
        processed = cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    # 3. Edge-Preserving Denoising for small print
    if quality["laplacian_var"] < 120.0:
        processed = cv2.bilateralFilter(processed, d=5, sigmaColor=40, sigmaSpace=40)

    return processed, quality


# =====================================================================
# 2. BARCODE / QR DECODING (Priority 1)
# =====================================================================

def detect_barcodes_and_qrs(img_bgr: np.ndarray) -> List[Dict[str, Any]]:
    """
    Decodes 1D barcodes and 2D QR codes using OpenCV.
    Returns list of dicts with 'code', 'type', and bounding box 'bbox' (x, y, w, h).
    """
    results = []
    try:
        # Barcode detector
        bd = cv2.barcode.BarcodeDetector()
        retval, decoded_info, decoded_types, points = bd.detectAndDecodeMulti(img_bgr)
        if retval and decoded_info:
            for code, c_type, pts in zip(decoded_info, decoded_types, points):
                clean = str(code).strip()
                if clean and not any(r["code"] == clean for r in results):
                    pts = np.int32(pts)
                    x, y, w, h = cv2.boundingRect(pts)
                    results.append({"code": clean, "type": "BARCODE", "bbox": (x, y, w, h)})
    except Exception as e:
        logger.debug(f"[BARCODE_DETECTION_DEBUG] {e}")

    try:
        # QR Code detector
        qrd = cv2.QRCodeDetector()
        retval, decoded_info, points, _ = qrd.detectAndDecodeMulti(img_bgr)
        if retval and decoded_info:
            for code, pts in zip(decoded_info, points):
                clean = str(code).strip()
                if clean and not any(r["code"] == clean for r in results):
                    pts = np.int32(pts)
                    x, y, w, h = cv2.boundingRect(pts)
                    results.append({"code": clean, "type": "QR", "bbox": (x, y, w, h)})
    except Exception as e:
        logger.debug(f"[QR_DETECTION_DEBUG] {e}")

    return results


# =====================================================================
# 3. PHARMACEUTICAL TEXT EXTRACTION & NORMALIZATION
# =====================================================================

def normalize_text_spacing(text: str) -> str:
    """Standardizes spacing, hyphens, and removes common trademark symbols."""
    text = re.sub(r"[®™©*•]", " ", text)
    text = re.sub(r"[\t\r\n]+", " ", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def fix_ocr_substitutions(text: str, context: str = "generic") -> str:
    """
    Handles common OCR confusion (0/O, 1/I/l, 5/S, 8/B).
    Context 'digits': replace letters with numbers (e.g. in '65O mg' -> '650 mg').
    Context 'generic': cleans up common pharmaceutical abbreviations.
    """
    if context == "digits":
        # Multi-pass letter-to-digit conversion (e.g. 5OO -> 500, 1OOO -> 1000)
        for _ in range(4):
            text = re.sub(r"(\d)[oO]", r"\g<1>0", text)
            text = re.sub(r"[oO](\d)", r"0\g<1>", text)
            text = re.sub(r"(\d)[iIl]", r"\g<1>1", text)
            text = re.sub(r"[iIl](\d)", r"1\g<1>", text)
            text = re.sub(r"(\d)[sS]", r"\g<1>5", text)
            text = re.sub(r"[sS](\d)", r"5\g<1>", text)
            text = re.sub(r"(\d)[bB]", r"\g<1>8", text)
            text = re.sub(r"[bB](\d)", r"8\g<1>", text)
        # Also handle letter right before unit: e.g. 1Omg -> 10mg, 5Omg -> 50mg
        text = re.sub(r"(^|\s)[oO](\d)", r"\g<1>0\2", text)
        text = re.sub(r"(^|\s)[iIl](\d)", r"\g<1>1\2", text)
        text = re.sub(r"(\d)[oO](\s*(?:mg|mcg|g|ml|iu))\b", r"\g<1>0\2", text, flags=re.IGNORECASE)
    return text


def extract_strength(text: str) -> Optional[Tuple[str, float]]:
    """Extracts dosage strength (e.g. '650 mg', '40mg', '500 mg', '5 ml', '1% w/v', '625')."""
    text_fixed = fix_ocr_substitutions(text, context="digits")
    # First check with explicit unit
    pattern_with_unit = r"\b(\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%|w/v|w/w|tabs?|caps?))\b"
    m = re.search(pattern_with_unit, text_fixed, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip(), 0.95
    # Check for standalone pharma dosage numbers
    m_num = re.search(r"\b(1000|650|625|500|400|250|200|150|100|80|75|50|40|25|20|10|5)\b", text_fixed)
    if m_num:
        return m_num.group(1).strip(), 0.90
    return None


def extract_pack_size(text: str) -> Optional[str]:
    """Extracts pack size (e.g. '10 Tablets', '15 Capsules', '10's', '100 ml')."""
    pattern = r"\b(\d+\s*(?:tablets?|capsules?|tabs?|caps?|\'s|ml|vials?|ampoules?|sachets?))\b"
    m = re.search(pattern, text, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def polygon_to_bbox(box: Any) -> List[int]:
    """Converts OCR box representation (polygon coordinates or bounding rect) into [x1, y1, x2, y2]."""
    if box is None:
        return [0, 0, 0, 0]
    try:
        arr = np.array(box, dtype=np.float32)
        if arr.ndim == 2 and arr.shape[0] >= 3:
            x_min = int(np.min(arr[:, 0]))
            y_min = int(np.min(arr[:, 1]))
            x_max = int(np.max(arr[:, 0]))
            y_max = int(np.max(arr[:, 1]))
            return [x_min, y_min, x_max, y_max]
        elif arr.ndim == 1 and len(arr) >= 4:
            return [int(arr[0]), int(arr[1]), int(arr[2]), int(arr[3])]
    except Exception:
        pass
    return [0, 0, 0, 0]


# Match Batch / Lot Label Anchors across all variations and OCR noise (L0T, B.N0, BATCH N0, etc.)
BATCH_LABEL_ANCHOR_REGEX = re.compile(
    r"^(?:B\.?\s*N[O0]\.?|B\s*N[O0]|BNO|BATCH\s*N[O0]\.?|BATCH\s*N[O0]|BATCH\s*NUMBER|BATCH|L[O0]T\s*N[O0]\.?|L[O0]T\s*N[O0]|L[O0]T\s*NUMBER|L[O0]T)\b[:.-]*",
    re.IGNORECASE,
)

# Search inside text for batch label prefix
BATCH_LABEL_SEARCH_REGEX = re.compile(
    r"\b(?:B\.?\s*N[O0]\.?|B\s*N[O0]|BNO|BATCH\s*N[O0]\.?|BATCH\s*N[O0]|BATCH\s*NUMBER|BATCH|L[O0]T\s*N[O0]\.?|L[O0]T\s*N[O0]|L[O0]T\s*NUMBER|L[O0]T)\b[:.-]*",
    re.IGNORECASE,
)

# Disqualify labels for other fields (MFD, EXP, MRP, Licence No, GST, etc.)
IGNORED_FIELD_LABEL_REGEX = re.compile(
    r"\b(?:MFD|MFG|MANUFACTURED|MFD\.?|MFG\.?|EXP|EXPIRY|USE\s*BEFORE|BEST\s*BEFORE|EXP\.?|"
    r"MRP|MAX\s*RETAIL\s*PRICE|MAX\s*RETAIL|MAX\.?\s*RETAIL|MAX|RETAIL|PRICE|RS\.?|INR|₹|"
    r"M\.?L\.?N[O0]\.?|LICENCE\s*N[O0]\.?|LICENSE\s*N[O0]\.?|MFG\.?\s*LIC|DL\.?\s*N[O0]|LIC\.?\s*N[O0]|"
    r"GST|HSN|COMPOSITION|STRENGTH)\b",
    re.IGNORECASE,
)


def is_valid_batch_candidate(cand: str) -> bool:
    """
    Strict validation to ensure token is an authentic batch/lot number and NOT:
    MRP, price, GST, lic number, phone number, date, composition strength, or packaging boilerplate.
    """
    if not cand or len(cand) < 3 or len(cand) > 20:
        return False

    cand_upper = cand.strip().upper()
    # Strip trailing or leading punctuation
    cand_upper = cand_upper.strip(" :.,;!?)]}\"'\\-/#=")

    if len(cand_upper) < 3 or len(cand_upper) > 20:
        return False

    # 1. Disqualify price / MRP (e.g. 125.00, Rs. 150, ₹171.04, MRP)
    if re.search(r"[₹$]|(?:\b(?:RS|MRP|PRICE|INCL|TAXES|TAX)\b)|\.\d{2}$", cand_upper):
        return False

    # 2. Disqualify dates (e.g. 05/25, 08/2027, 2026-03, 03/2026)
    if re.match(r"^\d{1,2}[/-]\d{2,4}$", cand_upper) or re.match(r"^\d{4}[/-]\d{1,2}$", cand_upper):
        return False

    # 3. Disqualify Mfg / Exp keywords
    if re.search(r"\b(?:EXP|MFG|MFD|DATE|USE|BEFORE|BEST)\b", cand_upper):
        return False

    # 4. Disqualify license numbers (e.g. G/25/1042, Mfg Lic No, DL No, PD-198A when associated with M.L.No)
    if re.search(r"\b(?:LIC|LICENSE|L\.NO|G/|MFG\.?\s*LIC|DL\.?NO|M\.L\.NO)\b", cand_upper):
        return False

    # 5. Disqualify dosage strength (e.g. 40MG, 650MG, 500MG, 10ML, 100ML)
    if re.match(r"^\d+\s*(?:MG|MCG|ML|G|GM|IU|%)$", cand_upper):
        return False

    # 6. Disqualify long phone numbers or barcodes (> 8 pure digits without letters)
    if re.match(r"^\d{9,}$", cand_upper):
        return False

    # 7. Disqualify packaging terminology
    if cand_upper in {"TABLET", "TABLETS", "CAPSULE", "CAPSULES", "STRIP", "BLISTER", "DOSE", "KEEP", "OUT", "REACH", "STORE", "COOL", "DRY", "PLACE", "MAX", "RETAIL", "MAXRETAIL"}:
        return False

    # 8. Must contain at least one alphanumeric character
    if not re.search(r"[A-Z0-9]", cand_upper):
        return False

    return True


def isolate_and_clean_batch_string(raw_str: str) -> Optional[str]:
    """
    Isolates the batch number from neighbouring packaging fields (MRP, MAX.RETAIL, MFD, EXP, etc.),
    strips leading/trailing punctuation, preserves internal hyphens/slashes, and enforces
    the final-character digit requirement.
    Returns the cleaned upper-case batch string if valid, or None if uncertain/invalid (e.g. ends in a letter).
    """
    if not raw_str:
        return None

    val = str(raw_str).strip()

    # 1. Stop at space-separated packaging field label boundaries
    # E.g. "26231140 MFD: 03/2026 EXP: 08/2027" -> "26231140"
    # E.g. "AC826005 MAX.RETAIL" -> "AC826005"
    # E.g. "IPL25212 MRP ₹124.00" -> "IPL25212"
    label_boundary_pattern = re.compile(
        r"(?:\s+|[.:;\-,/\\]+)(?:"
        r"MAX\.?\s*RETAIL|MAX\.?\s*RETAIL\s*PRICE|MAX\b|RETAIL\b|"
        r"MRP|M\.?R\.?P\.?|PRICE|RS\.?|INR|₹|"
        r"MFD|MFG|MANUFACTURED|EXP|EXPIRY|USE\s*BEFORE|BEST\s*BEFORE|"
        r"M\.?L\.?N[O0]\.?|LICENCE|LICENSE|LIC\.?\s*N[O0]\.?|DL\.?\s*N[O0]|"
        r"GST|HSN|COMPOSITION|STRENGTH|NET|PACK"
        r")\b.*$",
        re.IGNORECASE
    )
    val = label_boundary_pattern.sub("", val).strip()

    # 2. Stop at attached packaging field labels (concatenated without space due to OCR merging/misreading)
    # E.g. "AC826005MAXRETAN" -> "AC826005"
    # E.g. "AC826005MAX.RETAIL" -> "AC826005"
    # E.g. "AC826005MRP" -> "AC826005"
    # E.g. "AC826005MFD" -> "AC826005"
    attached_label_pattern = re.compile(
        r"(?<=[A-Z0-9])(?:"
        r"MAX\.?\s*RETAIL|MAXRETAIL|MAXRETAN|MAXRETA|MAXRET|MAXRTL|MAX|RETAIL|"
        r"MRP|M\.?R\.?P\.?|PRICE|RS|INR|"
        r"MFD|MFG|MANUFACTURED|EXP|EXPIRY|"
        r"M\.?L\.?N[O0]\.?|LICENCE|LICENSE|LIC|DL|GST|HSN"
        r")(?!\d).*$",
        re.IGNORECASE
    )
    val = attached_label_pattern.sub("", val).strip()

    # 3. Strip leading & trailing punctuation
    # Punctuation to remove from ends: ., ,, :, ;, !, ?, ), ], }, >, ", ', \, -, /
    val = val.strip(" :.,;!?)]}\"'\\-/#=")

    if not val:
        return None

    # 4. Check if basic candidate criteria are satisfied (length, not a date/price/boilplate, etc.)
    if not is_valid_batch_candidate(val):
        return None

    # 5. Final-character digit requirement:
    # Extracted batch number must end in a digit (0-9).
    # If it ends in a letter (e.g. ABC123X), DO NOT silently truncate it; mark as uncertain (return None).
    if not val[-1].isdigit():
        logger.info(f"[BATCH_VALIDATION] Rejected candidate '{val}' because final character '{val[-1]}' is not a digit.")
        return None

    return val.upper()


def extract_batch_from_crop(
    patch_bgr: np.ndarray,
    ocr_engine,
) -> Tuple[Optional[str], float]:
    """
    Staged targeted micro-OCR pipeline on a cropped batch stamp:
    Pass A: Raw crop
    If Pass A yields a high-confidence batch (score >= 0.85), returns immediately (< 500ms).
    If ambiguous or low-confidence:
    Pass B: Contrast-enhanced grayscale (CLAHE)
    Pass C: Adaptive thresholded (Otsu binarization)
    Consensus voting selects the most reliable batch number.
    """
    if patch_bgr is None or patch_bgr.size == 0 or patch_bgr.shape[0] < 8 or patch_bgr.shape[1] < 12:
        return None, 0.0

    batch_token_cleaner = re.compile(r"^(?:B\.?\s*N[O0]\.?|Batch\s*(?:N[O0]\.?)?|L[O0]t\s*(?:N[O0]\.?)?|L[O0]T|#|:)[\s.:=-]*", re.IGNORECASE)

    def _eval_pass(img):
        cands = {}
        try:
            res = ocr_engine.predict(img)
            for r in res:
                texts = r.get("rec_texts") or []
                scores = r.get("rec_scores") or []
                for t, s in zip(texts, scores):
                    t_clean = str(t).strip()
                    val = batch_token_cleaner.sub("", t_clean).strip(" :.=-").upper()
                    clean_tok = isolate_and_clean_batch_string(val)
                    if clean_tok:
                        cands[clean_tok] = float(s)
                    else:
                        for tok in val.split():
                            c_sub = isolate_and_clean_batch_string(tok)
                            if c_sub:
                                cands[c_sub] = float(s)
                                break
        except Exception as e:
            logger.debug(f"[BATCH_CROP_PASS_ERROR] {e}")
        return cands

    # Pass A: Raw crop
    pass_a = _eval_pass(patch_bgr)
    if pass_a:
        best_cand, best_score = max(pass_a.items(), key=lambda x: x[1])
        if best_score >= 0.85:
            return best_cand, round(best_score, 2)

    # Secondary passes if Pass A was inconclusive or low confidence
    candidate_votes: Dict[str, List[float]] = {}
    for k, v in pass_a.items():
        candidate_votes.setdefault(k, []).append(v)

    # Pass B: CLAHE enhanced
    gray = cv2.cvtColor(patch_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(4, 4))
    enhanced_gray = clahe.apply(gray)
    pass_b = _eval_pass(cv2.cvtColor(enhanced_gray, cv2.COLOR_GRAY2BGR))
    for k, v in pass_b.items():
        candidate_votes.setdefault(k, []).append(v)

    # Pass C: Otsu binarization
    _, thresh = cv2.threshold(enhanced_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    pass_c = _eval_pass(cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR))
    for k, v in pass_c.items():
        candidate_votes.setdefault(k, []).append(v)

    if not candidate_votes:
        return None, 0.0

    ranked = sorted(
        candidate_votes.items(),
        key=lambda item: (len(item[1]), sum(item[1]) / len(item[1])),
        reverse=True,
    )

    best_cand, scores = ranked[0]
    mean_conf = sum(scores) / len(scores)
    consensus_conf = min(mean_conf + (0.05 * (len(scores) - 1)), 1.0)
    if consensus_conf < 0.60:
        return None, 0.0

    return best_cand, round(consensus_conf, 2)


def extract_batch_spatially(
    all_boxes: List[Any],
    all_texts: List[str],
    all_scores: List[float],
    img_shape: Optional[Tuple[int, int]] = None,
    ocr_engine = None,
    processed_img: Optional[np.ndarray] = None,
    raw_img: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """
    CORE SPATIAL BATCH EXTRACTION ENGINE:
    1. Identifies BATCH/LOT label anchors (handling OCR noise like L0T, B.N0, BATCH N0).
    2. Determines the value spatially associated with the anchor:
       - Priority 1: High-resolution un-downscaled micro-crop OCR around anchor stamp.
       - Priority 2: Text immediately to the RIGHT on the same line (or embedded in same text line).
       - Priority 3: Text immediately BELOW the anchor.
       - Priority 4: Bounding-box spatial proximity.
    3. Strictly filters out values associated with MFD, EXP, MRP, M.L.NO, GST, etc.
    4. Validates batch format and returns structured spatial result.
    """
    if not all_texts:
        return {
            "success": False,
            "batch_number": "BATCH_NOT_CONFIDENT",
            "anchor": None,
            "confidence": 0.0,
            "bbox": None,
            "associated_text": None,
            "message": "No text detected in OCR."
        }

    norm_boxes = [polygon_to_bbox(b) for b in all_boxes]

    items = []
    for idx, (text, score, box) in enumerate(zip(all_texts, all_scores, norm_boxes)):
        items.append({
            "text": str(text).strip(),
            "score": float(score),
            "box": box,
            "index": idx,
        })

    candidates = []

    for item in items:
        text = item["text"]
        box = item["box"]
        score = item["score"]

        # Check if line contains a BATCH/LOT label anchor
        m_anchor = BATCH_LABEL_SEARCH_REGEX.search(text)
        if not m_anchor:
            continue

        raw_anchor = m_anchor.group(0).strip(" :.-")
        matched_span = m_anchor.span()

        # 1. PRIORITY 1: High-Resolution Targeted Micro-Crop OCR on un-downscaled raw_img
        crop_target_img = raw_img if raw_img is not None else processed_img
        if crop_target_img is not None and ocr_engine is not None and box and (box[2] - box[0]) > 5:
            x1, y1, x2, y2 = box[:4]
            h = y2 - y1
            w = x2 - x1
            img_h, img_w = crop_target_img.shape[:2]

            # Scale box coordinates if raw_img shape differs from processed_img shape
            if processed_img is not None and raw_img is not None and processed_img.shape[:2] != raw_img.shape[:2]:
                sy = raw_img.shape[0] / float(processed_img.shape[0])
                sx = raw_img.shape[1] / float(processed_img.shape[1])
                crop_x1 = max(0, int((x1 - 5) * sx))
                crop_y1 = max(0, int((y1 - 8) * sy))
                crop_x2 = min(img_w, int((x2 + w * 3.5) * sx))
                crop_y2 = min(img_h, int((y2 + h * 1.8) * sy))
            else:
                crop_x1 = max(0, x1 - 5)
                crop_y1 = max(0, y1 - 8)
                crop_x2 = min(img_w, x2 + int(w * 3.5))
                crop_y2 = min(img_h, y2 + int(h * 1.8))

            if crop_x2 > crop_x1 + 10 and crop_y2 > crop_y1 + 8:
                patch = crop_target_img[crop_y1:crop_y2, crop_x1:crop_x2]
                crop_batch, crop_conf = extract_batch_from_crop(patch, ocr_engine)
                if crop_batch:
                    clean_crop = isolate_and_clean_batch_string(crop_batch)
                    if clean_crop:
                        candidates.append({
                            "batch": clean_crop,
                            "anchor": raw_anchor.upper(),
                            "confidence": crop_conf,
                            "priority": 1,
                            "bbox": [crop_x1, crop_y1, crop_x2, crop_y2],
                            "associated_text": text,
                            "distance": 0.0,
                        })

        # 2. PRIORITY 2: Same-line embedded text value (text after label)
        remainder = text[matched_span[1]:].strip(" :.=-")
        if remainder:
            clean_cand = isolate_and_clean_batch_string(remainder)
            if clean_cand:
                candidates.append({
                    "batch": clean_cand,
                    "anchor": raw_anchor.upper(),
                    "confidence": min(score + 0.05, 1.0),
                    "priority": 2,
                    "bbox": box,
                    "associated_text": text,
                    "distance": 0.5,
                })

        # 3. PRIORITY 3: Text immediately to the RIGHT on the same line in a subsequent OCR box
        x1_a, y1_a, x2_a, y2_a = box
        h_a = max(y2_a - y1_a, 1)

        for other in items:
            if other["index"] == item["index"]:
                continue

            o_text = other["text"]
            o_box = other["box"]
            x1_o, y1_o, x2_o, y2_o = o_box
            h_o = max(y2_o - y1_o, 1)

            # Check if other line is on the same line (vertical overlap / center alignment)
            v_overlap = min(y2_a, y2_o) - max(y1_a, y1_o)
            cy_diff = abs(((y1_a + y2_a) / 2.0) - ((y1_o + y2_o) / 2.0))

            is_same_line = (v_overlap > 0.3 * min(h_a, h_o)) or (cy_diff < max(h_a, h_o) * 0.75)
            is_to_right = x1_o >= (x1_a - 15)

            if is_same_line and is_to_right:
                if IGNORED_FIELD_LABEL_REGEX.search(o_text):
                    continue

                clean_cand = isolate_and_clean_batch_string(o_text)
                if clean_cand:
                    dist = abs(x1_o - x2_a)
                    candidates.append({
                        "batch": clean_cand,
                        "anchor": raw_anchor.upper(),
                        "confidence": min((score + other["score"]) / 2.0 + 0.05, 1.0),
                        "priority": 3,
                        "bbox": o_box,
                        "associated_text": f"{text} {o_text}",
                        "distance": dist,
                    })

        # 4. PRIORITY 4: Text box immediately BELOW the anchor
        for other in items:
            if other["index"] == item["index"]:
                continue

            o_text = other["text"]
            o_box = other["box"]
            x1_o, y1_o, x2_o, y2_o = o_box

            is_below = y1_o >= (y1_a - 5) and (y1_o - y2_a) <= (h_a * 2.5)
            h_overlap = min(x2_a, x2_o) - max(x1_a, x1_o)
            cx_diff = abs(((x1_a + x2_a) / 2.0) - ((x1_o + x2_o) / 2.0))

            is_aligned_below = (h_overlap > 0.2 * min(x2_a - x1_a, x2_o - x1_o)) or (cx_diff < max(x2_a - x1_a, x2_o - x1_o) * 1.2)

            if is_below and is_aligned_below:
                if IGNORED_FIELD_LABEL_REGEX.search(o_text):
                    continue

                clean_cand = isolate_and_clean_batch_string(o_text)
                if clean_cand:
                    v_dist = y1_o - y2_a
                    candidates.append({
                        "batch": clean_cand,
                        "anchor": raw_anchor.upper(),
                        "confidence": min((score + other["score"]) / 2.0, 0.95),
                        "priority": 4,
                        "bbox": o_box,
                        "associated_text": f"{text}\n{o_text}",
                        "distance": v_dist,
                    })

    if not candidates:
        return {
            "success": False,
            "batch_number": "BATCH_NOT_CONFIDENT",
            "anchor": None,
            "confidence": 0.0,
            "bbox": None,
            "associated_text": None,
            "message": "No confident batch label spatial match detected."
        }

    # Rank candidates by (priority ASC, distance ASC, confidence DESC)
    candidates.sort(key=lambda c: (c["priority"], c["distance"], -c["confidence"]))

    best = candidates[0]
    if best["confidence"] < 0.55:
        return {
            "success": False,
            "batch_number": "BATCH_NOT_CONFIDENT",
            "anchor": best["anchor"],
            "confidence": round(best["confidence"], 2),
            "bbox": best["bbox"],
            "associated_text": best["associated_text"],
            "message": "Extracted candidate confidence is below confidence threshold."
        }

    return {
        "success": True,
        "batch_number": best["batch"],
        "anchor": best["anchor"],
        "confidence": round(best["confidence"], 2),
        "bbox": best["bbox"],
        "associated_text": best["associated_text"],
        "message": f"Successfully extracted batch '{best['batch']}' associated with anchor '{best['anchor']}'."
    }


def extract_medicine_batch_from_image(
    raw_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Stand-alone camera scanner engine to extract ONLY the batch/lot number from a packaging image.
    Executes:
      1. OpenCV Image Decode & Dynamic Preprocessing.
      2. PaddleOCR Mobile Text Detection & Bounding Boxes.
      3. Core Spatial Batch Anchor Extraction Engine.
    Returns structured JSON with extracted batch, anchor, confidence, and bounding box.
    """
    t_start = time.perf_counter()
    nparr = np.frombuffer(raw_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img_bgr is None:
        return {
            "success": False,
            "batch_number": "BATCH_NOT_CONFIDENT",
            "anchor": None,
            "confidence": 0.0,
            "bbox": None,
            "associated_text": None,
            "ocr_latency_ms": 0.0,
            "error": "Failed to decode uploaded packaging image."
        }

    processed_img, quality_info = preprocess_image(img_bgr)
    ocr_engine = get_ocr_engine()

    t_ocr0 = time.perf_counter()
    ocr_results = ocr_engine.predict(processed_img)
    ocr_ms = (time.perf_counter() - t_ocr0) * 1000.0

    all_texts: List[str] = []
    all_scores: List[float] = []
    all_boxes: List[Any] = []

    for res in ocr_results:
        rec_texts = res.get("rec_texts") if res.get("rec_texts") is not None else []
        rec_scores = res.get("rec_scores") if res.get("rec_scores") is not None else []
        rec_boxes = res.get("rec_boxes") if res.get("rec_boxes") is not None else []
        for t, s, b in zip(rec_texts, rec_scores, rec_boxes):
            t_str = str(t).strip()
            if t_str and float(s) > 0.30:
                all_texts.append(t_str)
                all_scores.append(float(s))
                all_boxes.append(b)

    spatial_res = extract_batch_spatially(
        all_boxes=all_boxes,
        all_texts=all_texts,
        all_scores=all_scores,
        img_shape=processed_img.shape,
        ocr_engine=ocr_engine,
        processed_img=processed_img,
        raw_img=img_bgr,
    )

    total_ms = (time.perf_counter() - t_start) * 1000.0
    spatial_res["ocr_latency_ms"] = round(total_ms, 1)
    return spatial_res


def extract_batch_dedicated_pipeline(
    processed_img: Optional[np.ndarray],
    all_boxes: List[List[int]],
    all_texts: List[str],
    all_scores: List[float],
    ocr_engine,
) -> Tuple[Optional[str], float]:
    """
    Dedicated Batch Number Pipeline using Spatial Anchor Extractor:
    Locates BATCH / LOT anchors and extracts spatially associated value.
    Returns (batch, confidence). If confidence < 0.55, returns (None, 0.0) without guessing.
    """
    spatial_res = extract_batch_spatially(
        all_boxes=all_boxes,
        all_texts=all_texts,
        all_scores=all_scores,
        img_shape=processed_img.shape if processed_img is not None else None,
        ocr_engine=ocr_engine,
        processed_img=processed_img,
    )

    if spatial_res.get("success") and spatial_res.get("batch_number") != "BATCH_NOT_CONFIDENT":
        return spatial_res["batch_number"], spatial_res["confidence"]

    return None, 0.0



def extract_batch_number(lines_with_scores: List[Tuple[str, float]]) -> Tuple[Optional[str], float]:
    """
    Robust batch/lot number pattern recognition for Indian packaging.
    Patterns:
    - B.No: ABC123, Batch No: ABC123, Batch: ABC123, LOT: ABC123, B.NO. ABC123
    Discriminates against dates, MRP, and barcodes. Never hallucinates.
    """
    batch_pattern = (
        r"(?:B\.?\s*No\.?|Batch\s*(?:No\.?|#)?|Lot\s*(?:No\.?|#)?|B\.?\s*NUM)"
        r"[\s.:=-]*([A-Z0-9/\-.:]{3,30})"
    )

    # 1. Search in individual lines
    for line, score in lines_with_scores:
        if re.search(r"(?:MFG|EXP|EXPIRY|DATE)", line, re.IGNORECASE) and not re.search(r"B\.?No", line, re.IGNORECASE):
            continue

        m = re.search(batch_pattern, line, re.IGNORECASE)
        if m:
            clean_cand = isolate_and_clean_batch_string(m.group(1))
            if clean_cand:
                return clean_cand, min(score + 0.05, 1.0)

    # 2. Search across combined adjacent lines (e.g. line 1: "B.No:", line 2: "ABC123")
    for i in range(len(lines_with_scores) - 1):
        line1, s1 = lines_with_scores[i]
        line2, s2 = lines_with_scores[i + 1]
        if re.search(r"^(?:B\.?\s*No\.?|Batch\s*No\.?|Lot\s*No\.?)\s*[:.-]?$", line1.strip(), re.IGNORECASE):
            clean_cand = isolate_and_clean_batch_string(line2)
            if clean_cand:
                return clean_cand, min(s2, 0.95)

    return None, 0.0


def extract_expiry_date(lines_with_scores: List[Tuple[str, float]]) -> Tuple[Optional[str], float, Optional[str]]:
    """
    Extracts and standardizes expiry date to YYYY-MM.
    Strictly discriminates between MFG (manufacturing) and EXP (expiry).
    Formats supported:
    - MM/YY, MM/YYYY, MM-YY, MM-YYYY, MMM YYYY, MMM-YY
    Returns (expiry_str, confidence, mfg_str)
    """
    mfg_result = None
    exp_result = None
    exp_conf = 0.0

    def parse_date_str(d_str: str) -> Optional[str]:
        d_str = d_str.strip().replace(" ", "").replace(".", "/").replace("-", "/")
        # Format MM/YYYY
        m1 = re.match(r"^(\d{1,2})/(\d{4})$", d_str)
        if m1:
            month, year = int(m1.group(1)), int(m1.group(2))
            if 1 <= month <= 12 and 2020 <= year <= 2040:
                return f"{year:04d}-{month:02d}"

        # Format MM/YY
        m2 = re.match(r"^(\d{1,2})/(\d{2})$", d_str)
        if m2:
            month, yy = int(m2.group(1)), int(m2.group(2))
            year = 2000 + yy
            if 1 <= month <= 12 and 2020 <= year <= 2040:
                return f"{year:04d}-{month:02d}"

        # Format YYYY/MM
        m3 = re.match(r"^(\d{4})/(\d{1,2})$", d_str)
        if m3:
            year, month = int(m3.group(1)), int(m3.group(2))
            if 1 <= month <= 12 and 2020 <= year <= 2040:
                return f"{year:04d}-{month:02d}"

        return None

    def parse_named_month(d_str: str) -> Optional[str]:
        d_str = d_str.strip()
        # e.g. "AUG 2027" or "AUG-27" or "AUG/27"
        m = re.search(r"\b([a-zA-Z]{3,9})[\s/-]*(\d{2,4})\b", d_str)
        if m:
            mon_name = m.group(1).lower()
            year_val = m.group(2)
            if mon_name in MONTH_NAME_TO_NUM:
                month_num = MONTH_NAME_TO_NUM[mon_name]
                year_num = int(year_val)
                if year_num < 100:
                    year_num += 2000
                if 2020 <= year_num <= 2040:
                    return f"{year_num:04d}-{month_num}"
        return None

    # Step 1: Scan for MFG / MFD to separate out manufacturing date
    for line, score in lines_with_scores:
        if re.search(r"\b(?:MFG|MFD|Mfg\.?\s*Date|Manufactur)\b", line, re.IGNORECASE):
            dm = re.search(r"(\d{1,2}[/-]\d{2,4})", line)
            if dm:
                parsed = parse_date_str(dm.group(1))
                if parsed:
                    mfg_result = parsed
            else:
                named = parse_named_month(line)
                if named:
                    mfg_result = named

    # Step 2: Scan explicitly for EXP / Expiry
    for line, score in lines_with_scores:
        # Check if line contains Expiry indicator
        if re.search(r"\b(?:EXP|EXPIRY|Exp\.?\s*Date|Use\s*Before|Best\s*Before)\b", line, re.IGNORECASE):
            dm = re.search(r"(\d{1,2}[/-]\d{2,4})", line)
            if dm:
                parsed = parse_date_str(dm.group(1))
                if parsed and parsed != mfg_result:
                    exp_result = parsed
                    exp_conf = min(score + 0.05, 1.0)
                    break
            else:
                named = parse_named_month(line)
                if named and named != mfg_result:
                    exp_result = named
                    exp_conf = min(score + 0.05, 1.0)
                    break

    # Step 3: If no explicit EXP label, look for date patterns that differ from MFG
    if not exp_result:
        for line, score in lines_with_scores:
            if re.search(r"\b(?:MFG|MFD)\b", line, re.IGNORECASE):
                continue
            dm = re.search(r"\b(\d{1,2}[/-]\d{2,4})\b", line)
            if dm:
                parsed = parse_date_str(dm.group(1))
                # Expiry is typically in future (>= 2024) and not equal to MFG
                if parsed and parsed != mfg_result:
                    exp_result = parsed
                    exp_conf = max(score - 0.1, 0.70)
                    break

    return exp_result, exp_conf, mfg_result


def clean_medicine_name(raw_name: str) -> str:
    """Normalizes medicine brand name (strip packaging descriptors, trademark symbols)."""
    name = normalize_text_spacing(raw_name)
    # Remove packaging words from title if trailing
    name = re.sub(
        r"\b(?:Tablets?|Capsules?|Syrup|Suspension|Injection|Gel|Ointment|Drop|Strip|Blister)\b",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    name = re.sub(r"\b(?:I\.?P\.?|B\.?P\.?|U\.?S\.?P\.?)\b", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s{2,}", " ", name)
    return name


# Common Active Pharmaceutical Ingredients (Generic Salts) in Indian Market
COMMON_GENERIC_SALTS = [
    "esomeprazole", "pantoprazole", "rabeprazole", "omeprazole", "lansoprazole",
    "paracetamol", "acetaminophen", "ibuprofen", "diclofenac", "aceclofenac",
    "serratiopeptidase", "azithromycin", "amoxicillin", "clavulanic", "clavulanate",
    "cefixime", "ciprofloxacin", "ofloxacin", "ornidazole", "metronidazole",
    "doxycycline", "levofloxacin", "cefpodoxime", "telmisartan", "amlodipine",
    "losartan", "metoprolol", "atenolol", "hydrochlorothiazide", "ramipril",
    "atorvastatin", "rosuvastatin", "metformin", "glimepiride", "gliclazide",
    "vildagliptin", "sitagliptin", "teneligliptin", "dapagliflozin", "empagliflozin",
    "montelukast", "levocetirizine", "cetirizine", "fexofenadine", "bilastine",
    "chlorpheniramine", "dextromethorphan", "phenylephrine", "ambroxol", "guaiphenesin",
    "terbutaline", "salbutamol", "budesonide", "formoterol", "domperidone",
    "ondansetron", "itopride", "ranitidine", "famotidine", "clopidogrel", "aspirin",
    "pregabalin", "gabapentin", "methylcobalamin", "mecobalamin", "folic acid",
    "calcium", "vitamin d3", "cholecalciferol", "zinc", "iron", "ferrous ascorbate",
    "levothyroxine", "thyroxine", "tramadol", "alprazolam", "clonazepam", "linezolid",
]

# Packaging formulation descriptors and regulatory boilerplate to penalize/disqualify
COMPOSITION_AND_BOILERPLATE_REGEX = re.compile(
    r"\b("
    r"Gastro\s*Resistant|Enteric\s*Coated|Film\s*Coated|Sugar\s*Coated|Dispersible|Effervescent|"
    r"Sustained\s*Release|Extended\s*Release|Modified\s*Release|Controlled\s*Release|Prolonged\s*Release|"
    r"Mouth\s*Dissolving|Chewable|Sublingual|Tablets?\s*(?:IP|BP|USP)|Capsules?\s*(?:IP|BP|USP)|"
    r"Injections?\s*(?:IP|BP|USP)|Suspensions?\s*(?:IP|BP|USP)|Syrups?\s*(?:IP|BP|USP)|"
    r"Drops?\s*(?:IP|BP|USP)|Ointments?\s*(?:IP|BP|USP)|Gels?\s*(?:IP|BP|USP)|"
    r"SR|CR|ER|XR|PR|MD|DT|MR|FC|EC|"
    r"Each\s+(?:film\s+coated\s+|enteric\s+coated\s+|uncoated\s+)?(?:tablet|capsule|ml|gm|vial)\s+contains|"
    r"Composition|Excipients|Colour|Preservative|As\s+prescribed\s+by|"
    r"Schedule\s+[HH1X]|Prescription\s+Drug|Warning|Caution|Keep\s+out\s+of\s+reach|Not\s+for\s+injection|"
    r"Store\s+in\s+a\s+cool|Store\s+below|Protect\s+from\s+light|Protect\s+from\s+moisture|"
    r"Manufactured\s+by|Marketed\s+by|Mfd\.?\s*by|Mkt\.?\s*by|Mfg\.?\s*Lic|Plot\s*No|Industrial\s*Area|"
    r"Regd\.?\s*Office|Corporate\s*Office|Customer\s*Care|Marketed\s*in\s*India|For\s+sale\s+in\s*India|"
    r"Batch\s*No|Lot\s*No|B\.?\s*No|Mfg\.?\s*Date|Exp\.?\s*Date|M\.?R\.?P\.?|Inclusive\s+of\s+all\s+taxes|"
    r"Trade\s*Mark|Registered\s*Trade\s*Mark|All\s*Rights\s*Reserved"
    r")\b",
    re.IGNORECASE
)


def extract_generic_name(text: str) -> Optional[str]:
    """Identifies generic pharmaceutical active chemical salts from composition text."""
    text_lower = text.lower()
    for salt in COMMON_GENERIC_SALTS:
        m = re.search(
            rf"\b{re.escape(salt)}(?:\s+(?:hydrochloride|sodium|potassium|maleate|succinate|tartrate|mesylate|phosphate|hcl|trihydrate))?\b",
            text_lower,
            re.IGNORECASE,
        )
        if m:
            return m.group(0).title()
    return None


def identify_prominent_brand_name(
    cluster_items: List[Tuple[str, float, List[int]]],
) -> Dict[str, Any]:
    """
    Visual Text Hierarchy Engine:
    Selects the prominent commercial brand name based on font size (height), box area,
    and distinct brand name typography, while strictly disqualifying composition descriptions,
    generic drug formulations, warnings, and regulatory boilerplate.

    Returns:
        {
            "medicine_name": str,  # Clean brand name (e.g. "PRE-ESO")
            "brand_name": str,     # Brand name (e.g. "PRE-ESO")
            "display_name": str,   # Display name with strength (e.g. "PRE-ESO 40")
            "strength": str,       # Strength (e.g. "40 mg")
            "generic_name": str,   # Generic chemical salt if detected (e.g. "Esomeprazole")
            "confidence": float,
        }
    """
    if not cluster_items:
        return {
            "medicine_name": None,
            "brand_name": None,
            "display_name": None,
            "strength": None,
            "generic_name": None,
            "confidence": 0.0,
        }

    # 1. Compute bounding box geometries and maximum dimensions in cluster
    heights = []
    areas = []
    for item in cluster_items:
        box = item[2]
        h = max(box[3] - box[1], 1)
        w = max(box[2] - box[0], 1)
        heights.append(h)
        areas.append(h * w)

    max_h = max(heights) if heights else 1
    max_area = max(areas) if areas else 1

    # 2. Extract cluster-wide generic salt and strength signals
    extracted_generic = None
    extracted_cluster_strength = None

    for text, score, _ in cluster_items:
        if not extracted_generic:
            gen = extract_generic_name(text)
            if gen:
                extracted_generic = gen

        if not extracted_cluster_strength:
            st_info = extract_strength(text)
            if st_info:
                extracted_cluster_strength = st_info[0]

    # 3. Score candidate lines for Brand Name prominence
    candidates = []

    for idx, (text, score, box) in enumerate(cluster_items):
        clean_line = normalize_text_spacing(text)

        # Disqualify dates, batch, price lines, empty lines
        if not clean_line or len(clean_line) < 2:
            continue
        if re.search(r"^(?:B\.?No|Batch|Exp|Mfg|Date|Rs\.?|Price|₹|MRP|\d+$)", clean_line, re.IGNORECASE):
            continue
        if re.match(r"^\d{1,2}[/-]\d{2,4}$", clean_line):
            continue

        h = heights[idx]
        area = areas[idx]
        font_ratio = h / float(max_h)
        area_ratio = area / float(max_area)

        # Base Visual Hierarchy Score: Font height is the strongest signal of brand prominence
        prominence_score = (font_ratio * 6.0) + (area_ratio * 2.0) + (score * 2.0)

        # COMPOSITION PENALTY: Heavily penalize generic formulations and boilerplate
        has_composition_markers = bool(COMPOSITION_AND_BOILERPLATE_REGEX.search(clean_line))
        has_generic_salt = bool(extract_generic_name(clean_line))

        if has_composition_markers:
            prominence_score -= 10.0

        if has_generic_salt and clean_line.lower().startswith(has_generic_salt if isinstance(has_generic_salt, str) else ""):
            prominence_score -= 6.0

        # BRAND PATTERN BONUSES
        tokens = clean_line.split()
        num_tokens = len(tokens)

        # A. Short title (1-3 words) is typical for commercial medicine brands
        if 1 <= num_tokens <= 3:
            prominence_score += 2.5
        elif num_tokens > 5:
            prominence_score -= 3.0  # Sentences/descriptions are not brand names

        # B. Distinctive brand hyphenation or alphanumeric (e.g. PRE-ESO, PAN-D, DOLO-650, TELMA-40)
        if re.search(r"\b[A-Z0-9]+-[A-Z0-9]+\b", clean_line):
            prominence_score += 3.5

        # C. Uppercase or Title Case
        if clean_line.isupper():
            prominence_score += 1.5

        # D. Embedded or adjacent dosage number (e.g. "PRE-ESO 40", "DOLO 650", "PAN 40")
        dosage_match = re.search(r"\b(1000|650|625|500|400|250|200|150|100|80|75|50|40|25|20|10|5)\b", clean_line)
        if dosage_match:
            prominence_score += 2.0

        candidates.append({
            "raw_text": text,
            "clean_text": clean_line,
            "score": score,
            "prominence": prominence_score,
            "dosage_match": dosage_match.group(1) if dosage_match else None,
        })

    if not candidates:
        return {
            "medicine_name": None,
            "brand_name": None,
            "display_name": None,
            "strength": extracted_cluster_strength,
            "generic_name": extracted_generic,
            "confidence": 0.0,
        }

    # Pick top candidate with highest visual prominence
    candidates.sort(key=lambda c: c["prominence"], reverse=True)
    best = candidates[0]
    best_text = best["clean_text"]
    best_conf = best["score"]

    # 4. Extract Brand Name and Strength from best candidate
    # e.g. "PRE-ESO 40" -> Brand: "PRE-ESO", Strength: "40 mg"
    brand_candidate = best_text
    strength_from_brand = None

    # Check if brand text ends with or includes strength
    m_end_num = re.search(r"^(.*?)\s+([0-9]+(?:\.[0-9]+)?\s*(?:mg|mcg|g|ml|iu|%)?)$", best_text, re.IGNORECASE)
    if m_end_num:
        brand_candidate = m_end_num.group(1).strip()
        num_part = m_end_num.group(2).strip()
        # Ensure strength has mg/ml or fallback
        if not re.search(r"[a-z%]", num_part, re.IGNORECASE):
            strength_from_brand = f"{num_part} mg"
        else:
            strength_from_brand = num_part
    elif best["dosage_match"]:
        # e.g. "PRE-ESO 40"
        num = best["dosage_match"]
        brand_candidate = re.sub(rf"\b{num}\b", "", best_text).strip()
        strength_from_brand = f"{num} mg"

    final_strength = strength_from_brand or extracted_cluster_strength

    # Clean brand candidate
    clean_brand = clean_medicine_name(brand_candidate)
    if not clean_brand:
        clean_brand = best_text

    # Construct final display name: e.g. "PRE-ESO 40" or "DOLO 650"
    if final_strength:
        clean_num = final_strength.split()[0]
        if clean_num not in clean_brand:
            display_name = f"{clean_brand} {clean_num}"
        else:
            display_name = clean_brand
    else:
        display_name = clean_brand

    return {
        "medicine_name": clean_brand,
        "brand_name": clean_brand,
        "display_name": display_name,
        "strength": final_strength,
        "generic_name": extracted_generic,
        "confidence": best_conf,
    }


# =====================================================================
# 4. SPATIAL REGION CLUSTERING (5–7 MEDICINES IN ONE PHOTO)
# =====================================================================

def cluster_text_regions(
    boxes: List[List[int]],
    texts: List[str],
    scores: List[float],
    img_shape: Tuple[int, int],
) -> List[List[Tuple[str, float, List[int]]]]:
    """
    Clusters detected text bounding boxes [x1, y1, x2, y2] into 1 to 7 distinct
    medicine packaging regions using spatial proximity and layout hierarchy.
    """
    if not boxes:
        return []

    items_data = list(zip(texts, scores, boxes))
    n = len(items_data)
    if n <= 1:
        return [items_data]

    h_img, w_img = img_shape[:2]

    # Calculate bounding box centers and dimensions
    centers = []
    for t, s, b in items_data:
        x1, y1, x2, y2 = b
        centers.append(((x1 + x2) / 2.0, (y1 + y2) / 2.0, x2 - x1, y2 - y1))

    # Adjacency matrix for spatial clustering
    # Two text boxes belong to the same package if vertical/horizontal separation
    # is within a realistic package footprint threshold (relative to image dimensions)
    adj = [[] for _ in range(n)]
    x_thresh = w_img * 0.28
    y_thresh = h_img * 0.22

    for i in range(n):
        cx1, cy1, w1, h1 = centers[i]
        for j in range(i + 1, n):
            cx2, cy2, w2, h2 = centers[j]
            dx = abs(cx1 - cx2)
            dy = abs(cy1 - cy2)

            # Same cluster condition: within package bounds
            if dx < x_thresh and dy < y_thresh:
                adj[i].append(j)
                adj[j].append(i)

    # Connected component graph traversal
    visited = [False] * n
    clusters = []

    for i in range(n):
        if not visited[i]:
            cluster_indices = []
            queue = [i]
            visited[i] = True
            while queue:
                curr = queue.pop(0)
                cluster_indices.append(curr)
                for neighbor in adj[curr]:
                    if not visited[neighbor]:
                        visited[neighbor] = True
                        queue.append(neighbor)
            # Sort lines top-to-bottom within the package
            cluster_indices.sort(key=lambda idx: items_data[idx][2][1])
            clusters.append([items_data[idx] for idx in cluster_indices])

    # Limit to top clusters with meaningful content (up to 7 items max)
    clusters.sort(key=lambda c: len(c), reverse=True)
    return clusters[:7]


# =====================================================================
# 5. FULL OCR MULTI-ITEM SCAN ENTRYPOINT
# =====================================================================

def scan_multi_item_ocr(
    raw_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Dawaiflow OCR V2 — High-Accuracy Pure OCR & Computer Vision Pipeline:
    1. Image Deduplication & Frame Fingerprint Cache (< 1ms)
    2. Image Decoding (< 10ms)
    3. OpenCV Barcode Priority Scan (< 20ms)
    4. Image Quality Check + Dynamic Preprocessing Fast-Path (< 20ms)
    5. PaddleOCR PP-OCRv4 Mobile Text Detection & Recognition (~400ms)
    6. Spatial Region Clustering (Separates 1 to 7 medicine packages)
    7. Dedicated Visual Hierarchy Brand Name Extraction
    8. Dedicated 3-Pass Batch Crop Pipeline with Token Validation
    9. Dedicated Expiry Date Pipeline with Strict MFG Discrimination
    10. Detailed Stage-by-Stage Performance Telemetry Logging

    STRICTLY ZERO GEMINI INVOCATIONS.
    """
    # 1. Deduplication / Frame Cache
    cached = get_cached_scan(raw_bytes)
    if cached:
        return cached

    t_start = time.perf_counter()

    # 2. Decode in-memory image
    t0 = time.perf_counter()
    nparr = np.frombuffer(raw_bytes, np.uint8)
    img_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    decode_ms = (time.perf_counter() - t0) * 1000.0

    if img_bgr is None:
        return {
            "success": False,
            "items": [],
            "detected_barcodes": [],
            "error": "Failed to decode uploaded image.",
            "primary_engine": "PaddleOCR PP-OCRv4 Mobile + OpenCV Barcode OCR",
            "ocr_latency": 0.0,
            "total_latency": 0.0,
            "performance_breakdown": {"total_ms": 0.0},
        }

    # 3. Barcode Priority Scan (Instant < 20ms)
    t0 = time.perf_counter()
    detected_barcodes_info = detect_barcodes_and_qrs(img_bgr)
    detected_barcodes = [b["code"] for b in detected_barcodes_info]
    barcode_ms = (time.perf_counter() - t0) * 1000.0

    # 4. Dynamic Computer Vision Preprocessing
    t0 = time.perf_counter()
    processed_img, quality_info = preprocess_image(img_bgr)
    prep_ms = (time.perf_counter() - t0) * 1000.0

    # 5. PaddleOCR Mobile Text Detection & Recognition
    ocr_engine = get_ocr_engine()
    t0 = time.perf_counter()
    ocr_results = ocr_engine.predict(processed_img)
    ocr_ms = (time.perf_counter() - t0) * 1000.0

    # Flatten text, scores, boxes
    all_texts: List[str] = []
    all_scores: List[float] = []
    all_boxes: List[List[int]] = []

    for res in ocr_results:
        rec_texts = res.get("rec_texts") if res.get("rec_texts") is not None else []
        rec_scores = res.get("rec_scores") if res.get("rec_scores") is not None else []
        rec_boxes = res.get("rec_boxes") if res.get("rec_boxes") is not None else []
        for t, s, b in zip(rec_texts, rec_scores, rec_boxes):
            t_str = str(t).strip()
            if t_str and float(s) > 0.30:  # Filter out low-confidence background noise
                all_texts.append(t_str)
                all_scores.append(float(s))
                all_boxes.append(list(b) if isinstance(b, (list, tuple, np.ndarray)) else [0, 0, 0, 0])

    # 6. Spatial Region Clustering (Separate 1 to 7 medicines)
    t0 = time.perf_counter()
    clusters = cluster_text_regions(all_boxes, all_texts, all_scores, processed_img.shape)
    region_ms = (time.perf_counter() - t0) * 1000.0

    extracted_items = []
    name_total_ms = 0.0
    batch_total_ms = 0.0
    exp_total_ms = 0.0

    for cluster_idx, cluster in enumerate(clusters):
        lines_with_scores = [(item[0], item[1]) for item in cluster]
        cluster_texts = [item[0] for item in cluster]
        cluster_scores = [item[1] for item in cluster]
        cluster_boxes = [item[2] for item in cluster]
        full_cluster_text = " ".join(cluster_texts)

        # 7. Dedicated Batch Number Pipeline
        t_batch = time.perf_counter()
        batch_val, batch_conf = extract_batch_dedicated_pipeline(
            processed_img=processed_img,
            all_boxes=cluster_boxes,
            all_texts=cluster_texts,
            all_scores=cluster_scores,
            ocr_engine=ocr_engine,
        )
        batch_total_ms += (time.perf_counter() - t_batch) * 1000.0

        # 8. Dedicated Expiry Date Pipeline
        t_exp = time.perf_counter()
        expiry_val, exp_conf, mfg_val = extract_expiry_date(lines_with_scores)
        exp_total_ms += (time.perf_counter() - t_exp) * 1000.0

        # 9. Strength & Pack Size
        strength_info = extract_strength(full_cluster_text)
        detected_strength = strength_info[0] if strength_info else None
        detected_pack = extract_pack_size(full_cluster_text)

        # 10. Medicine Name & Generic Formulation (Visual Hierarchy Engine)
        t_name = time.perf_counter()
        brand_info = identify_prominent_brand_name(cluster)
        name_total_ms += (time.perf_counter() - t_name) * 1000.0

        display_name = brand_info["display_name"]
        medicine_name = brand_info["medicine_name"]
        brand_name = brand_info["brand_name"]
        generic_name = brand_info["generic_name"]
        detected_strength = brand_info["strength"] or (strength_info[0] if strength_info else None)
        name_conf = brand_info["confidence"]

        # 11. Associate nearby Barcode if present
        associated_code = None
        if cluster_idx < len(detected_barcodes):
            associated_code = detected_barcodes[cluster_idx]
        elif detected_barcodes:
            associated_code = detected_barcodes[0]

        # Only retain valid medicine candidates
        if display_name or medicine_name or associated_code or batch_val:
            overall_conf = round((name_conf * 0.45) + (batch_conf * 0.30) + (exp_conf * 0.25), 2)
            extracted_items.append({
                "name": display_name or medicine_name or "Unknown Medicine",
                "medicine_name": medicine_name or display_name,
                "brand_name": brand_name,
                "generic_name": generic_name,
                "code": associated_code,
                "strength": detected_strength,
                "batch": batch_val,
                "batch_confidence": round(batch_conf, 2),
                "expiry": expiry_val,
                "pack_size": detected_pack,
                "confidence": {
                    "name": round(name_conf, 2),
                    "batch": round(batch_conf, 2),
                    "expiry": round(exp_conf, 2),
                    "overall": overall_conf,
                },
                "manufacturing_date": mfg_val,
            })

    total_ms = (time.perf_counter() - t_start) * 1000.0

    # Log Detailed Performance Telemetry
    logger.info(
        f"\n[OCR-PERF]\n"
        f"Image decode:       {decode_ms:6.1f} ms\n"
        f"Image preprocess:   {prep_ms:6.1f} ms\n"
        f"Barcode scan:       {barcode_ms:6.1f} ms\n"
        f"Region detection:   {region_ms:6.1f} ms\n"
        f"Full Text OCR:      {ocr_ms:6.1f} ms\n"
        f"Name OCR:           {name_total_ms:6.1f} ms\n"
        f"Batch Crop OCR:     {batch_total_ms:6.1f} ms\n"
        f"Expiry Extract:     {exp_total_ms:6.1f} ms\n"
        f"Total Pipeline:     {total_ms:6.1f} ms"
    )

    response_dict = {
        "success": True,
        "items": extracted_items,
        "detected_barcodes": detected_barcodes,
        "error": None,
        "primary_engine": "PaddleOCR PP-OCRv4 Mobile + OpenCV Barcode OCR",
        "ocr_latency": round(ocr_ms, 1),
        "total_latency": round(total_ms / 1000.0, 3),
        "image_quality": quality_info,
        "performance_breakdown": {
            "image_decode_ms": round(decode_ms, 1),
            "image_preprocess_ms": round(prep_ms, 1),
            "barcode_ms": round(barcode_ms, 1),
            "region_detection_ms": round(region_ms, 1),
            "ocr_ms": round(ocr_ms, 1),
            "name_ocr_ms": round(name_total_ms, 1),
            "batch_ocr_ms": round(batch_total_ms, 1),
            "expiry_ocr_ms": round(exp_total_ms, 1),
            "total_ms": round(total_ms, 1),
        },
    }

    set_cached_scan(raw_bytes, response_dict)
    return response_dict
