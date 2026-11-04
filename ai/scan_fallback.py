"""
Medicine pack scan: DawaiFlow AI fallback behind the phone's on-device OCR.

The phone reads the pack first. Only when its batch / expiry are missing, invalid or low-confidence does it send
the photo here. Controls: GEMINI_FALLBACK_ENABLED kill switch (default OFF), per-pharmacy hourly + daily caps,
short timeout, at most one retry, image resize, identical-image cache. A Gemini failure never raises: the caller
gets the OCR values back with the uncertain fields flagged. Not used by the supplier invoice scan.
"""

import concurrent.futures
import copy
import hashlib
import io
import json
import logging
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("expiryguard.scan_fallback")

# Proposed "sufficient" confidence (pending approval; tune from real photos via env, no code change).
BATCH_MIN_CONF = float(os.getenv("SCAN_FALLBACK_BATCH_MIN_CONF", "0.80") or 0.80)
EXPIRY_MIN_CONF = float(os.getenv("SCAN_FALLBACK_EXPIRY_MIN_CONF", "0.80") or 0.80)

FALLBACK_PROMPT = """You read printed text on an Indian medicine pack (strip, box or bottle).
Return ONLY JSON: {"medicine_name": str|null, "batch_number": str|null, "expiry_date": str|null, "mrp": number|null}
Rules:
- batch_number: the value next to "Batch No.", "B.No.", "Lot". Never a date, a price, a licence number or a barcode.
- expiry_date: the EXP / Expiry date only, as YYYY-MM. Never the manufacturing (MFG/MFD) date.
- mrp: the printed Maximum Retail Price only. Never a purchase price, PTR, PTS, strength or pack size.
- If a value is not clearly readable return null. Never guess or invent a value."""


def fallback_enabled() -> bool:
    """Kill switch. Default OFF: only an explicit true/1/yes/on turns Gemini on."""
    return os.getenv("GEMINI_FALLBACK_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _timeout_seconds() -> int:
    return max(3, _int_env("GEMINI_FALLBACK_TIMEOUT_SECONDS", 12))


_USAGE: Dict[Tuple[Any, str], int] = {}
_USAGE_LOCK = threading.Lock()
_CACHE: "OrderedDict[str, Tuple[float, dict]]" = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 900.0
_CACHE_MAX = 64


def reset_controls_for_tests() -> None:
    with _USAGE_LOCK:
        _USAGE.clear()
    with _CACHE_LOCK:
        _CACHE.clear()


def _reserve_call(user_id: Optional[int]) -> bool:
    """Counts one Gemini call for this pharmacy in the current hour and day; False when either cap is reached."""
    now = datetime.now()
    hour_key = (user_id, now.strftime("%Y%m%d%H"))
    day_key = (user_id, now.strftime("%Y%m%d"))
    with _USAGE_LOCK:
        if _USAGE.get(hour_key, 0) >= _int_env("GEMINI_FALLBACK_HOURLY_CALLS", 30):
            return False
        if _USAGE.get(day_key, 0) >= _int_env("GEMINI_FALLBACK_DAILY_CALLS", 120):
            return False
        _USAGE[hour_key] = _USAGE.get(hour_key, 0) + 1
        _USAGE[day_key] = _USAGE.get(day_key, 0) + 1
        return True


# ---------------------------------------------------------------- validation (same rules as the OCR engine)

def normalize_expiry(value: Any) -> Optional[str]:
    """Accepts YYYY-MM[-DD], MM/YY, MM/YYYY, YYYY/MM. Returns YYYY-MM (2020-2040) or None."""
    if value is None:
        return None
    s = str(value).strip().replace(" ", "").replace(".", "/")
    m = re.match(r"^(\d{4})[-/](\d{1,2})(?:[-/]\d{1,2})?$", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    else:
        m = re.match(r"^(\d{1,2})[-/](\d{2}|\d{4})$", s)
        if not m:
            return None
        month, year = int(m.group(1)), int(m.group(2))
        if year < 100:
            year += 2000
    if 1 <= month <= 12 and 2020 <= year <= 2040:
        return f"{year:04d}-{month:02d}"
    return None


def clean_batch(value: Any, mrp: Optional[float] = None) -> Optional[str]:
    """Batch must pass the OCR engine's format filter and must not equal the price."""
    if value is None:
        return None
    from ai.ocr_service import is_valid_batch_candidate
    s = re.sub(r"\s+", "", str(value)).upper()
    if not s or not is_valid_batch_candidate(s):
        return None
    if mrp is not None and s.replace(".", "", 1).isdigit():
        try:
            if abs(float(s) - float(mrp)) < 0.005:
                return None
        except ValueError:
            pass
    return s


def clean_mrp(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        v = float(str(value).replace(",", "").replace("₹", "").strip())
    except (TypeError, ValueError):
        return None
    return round(v, 2) if 0 < v < 100000 else None


def _to_float(v: Any) -> Optional[float]:
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- Gemini call

def _compress(image_bytes: bytes) -> Tuple[bytes, str]:
    """Always downscale to <= 1600 px JPEG q80 before sending; on any problem send the original."""
    try:
        from PIL import Image
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            img.thumbnail((1600, 1600))
            out = io.BytesIO()
            img.save(out, format="JPEG", quality=80, optimize=True)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, "image/jpeg"


def _call_gemini(image_bytes: bytes) -> dict:
    """One Gemini request, hard-bounded by the timeout. Raises on failure (caller degrades to OCR)."""
    from google.genai import types
    from ai.gemini_service import client, GEMINI_PRIMARY_MODEL
    data, mime = _compress(image_bytes)
    timeout = _timeout_seconds()

    def _run():
        return client.models.generate_content(
            model=GEMINI_PRIMARY_MODEL,
            contents=[FALLBACK_PROMPT, types.Part.from_bytes(data=data, mime_type=mime)],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                http_options=types.HttpOptions(timeout=timeout * 1000),
            ),
        )

    ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        response = ex.submit(_run).result(timeout=timeout + 2)
    finally:
        ex.shutdown(wait=False)
    try:
        from ai import usage_log
        usage_log.record_response(response, feature="scan_label", outcome="success", model=GEMINI_PRIMARY_MODEL)
    except Exception:
        pass
    text = (response.text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("unexpected reply shape")
    return parsed


def _call_with_one_retry(image_bytes: bytes) -> Tuple[Optional[dict], int, Optional[str]]:
    calls, last = 0, None
    for attempt in range(2):  # first try + at most one retry
        calls += 1
        try:
            return _call_gemini(image_bytes), calls, None
        except Exception as exc:  # noqa: BLE001 - any failure degrades to the OCR result
            last = type(exc).__name__
            msg = str(exc)
            retryable = isinstance(exc, (concurrent.futures.TimeoutError, TimeoutError)) or any(
                t in msg for t in ("503", "429", "UNAVAILABLE"))
            if not retryable:
                break
            if attempt == 0:
                time.sleep(0.4)
    return None, calls, last


# ---------------------------------------------------------------- decision + merge

def _ocr_field_state(ocr: Dict[str, Any]) -> Dict[str, Any]:
    """Validates the phone's OCR values. A value is 'trusted' when valid AND confidence >= threshold
    (confidence missing -> the phone only sends validated values, so valid format counts as trusted)."""
    mrp = clean_mrp(ocr.get("mrp"))
    batch = clean_batch(ocr.get("batch"), mrp)
    expiry = normalize_expiry(ocr.get("expiry"))
    bc, ec = _to_float(ocr.get("batch_conf")), _to_float(ocr.get("expiry_conf"))
    return {
        "batch": batch, "expiry": expiry, "mrp": mrp, "name": (str(ocr.get("name")).strip() or None) if ocr.get("name") else None,
        "batch_ok": bool(batch) and (bc is None or bc >= BATCH_MIN_CONF),
        "expiry_ok": bool(expiry) and (ec is None or ec >= EXPIRY_MIN_CONF),
    }


def _result(source: str, st: Dict[str, Any], g: Optional[dict], calls: int, t0: float,
            batch_ok: bool, expiry_ok: bool, reason: Optional[str] = None) -> dict:
    batch, expiry, mrp, name = st["batch"], st["expiry"], st["mrp"], st["name"]
    if g:
        g_mrp = clean_mrp(g.get("mrp"))
        # Gemini only fills what OCR did not already trust; a trusted OCR value is never overwritten.
        if not batch_ok:
            batch = clean_batch(g.get("batch_number"), g_mrp if mrp is None else mrp) or (batch if st["batch_ok"] else None)
        if not expiry_ok:
            expiry = normalize_expiry(g.get("expiry_date")) or (expiry if st["expiry_ok"] else None)
        if mrp is None:
            mrp = g_mrp
        if not name and g.get("medicine_name"):
            name = str(g["medicine_name"]).strip() or None
    elif source != "ocr":
        # No Gemini value available: keep only what OCR trusts, blank the rest.
        batch = batch if batch_ok else None
        expiry = expiry if expiry_ok else None
    uncertain = [f for f, v in (("batch_number", batch), ("expiry_date", expiry)) if not v]
    latency_ms = int((time.time() - t0) * 1000)
    logger.info("[SCAN_FALLBACK] path=%s gemini_calls=%d latency_ms=%d uncertain=%s reason=%s",
                source, calls, latency_ms, ",".join(uncertain) or "-", reason or "-")
    return {
        "success": bool(batch or expiry or name),
        "scan_source": source,                      # ocr | fallback | ocr_partial | failed
        "batch_number": batch,
        "expiry_date": expiry,
        "mrp": mrp,
        "medicine_name": name,
        "uncertain_fields": uncertain,
        "needs_manual_review": bool(uncertain),
        "gemini_calls": calls,
        "reason": reason,
        "message": ("Please check the highlighted fields." if uncertain else None),
        "latency_ms": latency_ms,
    }


def resolve_scan(image_bytes: bytes, ocr: Dict[str, Any], user_id: Optional[int]) -> dict:
    """OCR first; Gemini only when batch/expiry are not both trusted. Never raises."""
    t0 = time.time()
    st = _ocr_field_state(ocr or {})
    if st["batch_ok"] and st["expiry_ok"]:
        return _result("ocr", st, None, 0, t0, True, True)

    def degrade(reason: str, calls: int = 0) -> dict:
        src = "failed" if not (st["batch_ok"] or st["expiry_ok"]) else "ocr_partial"
        return _result(src, st, None, calls, t0, st["batch_ok"], st["expiry_ok"], reason)

    if not fallback_enabled():
        return degrade("fallback_off")
    key = hashlib.sha256(str(user_id).encode() + hashlib.sha256(image_bytes).digest()).hexdigest()
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            g, cached = copy.deepcopy(hit[1]), True
        else:
            g, cached = None, False
    calls = 0
    if not cached:
        if not _reserve_call(user_id):
            return degrade("cap_reached")
        g, calls, err = _call_with_one_retry(image_bytes)
        if g is None:
            return degrade("fallback_failed", calls)
        with _CACHE_LOCK:
            _CACHE[key] = (time.time(), copy.deepcopy(g))
            while len(_CACHE) > _CACHE_MAX:
                _CACHE.popitem(last=False)
    return _result("fallback", st, g, calls, t0, st["batch_ok"], st["expiry_ok"], "cache_hit" if cached else None)
