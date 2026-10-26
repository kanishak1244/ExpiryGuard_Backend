"""
Supplier invoice reading (Gemini Vision) with row-by-row extraction, deterministic validation and a limited,
independent second pass. NOTHING is saved here: results go to a review screen and are saved only after the
user confirms (see routes/document_archive_routes.py /documents/{id}/confirm and the app's Save button).

Flow per bill (at most INVOICE_AI_MAX_CALLS = 2 Gemini calls, no retry loop, no model fallback chain):
  1. Pass 1: strict JSON schema, row-by-row prompt (ai/prompts/invoice_prompt.py).
  2. Deterministic checks in code (ai/invoice_validation.py): expiry, HSN, batch, arithmetic, totals, MRP,
     row count. Structurally wrong fields are blanked and flagged; implausible ones are kept and flagged.
  3. Pass 2 ONLY when a check found a real problem or the table is dense: a different (column-by-column)
     reading. Any field the two readings disagree on is blanked and flagged for the user.
Controls: INVOICE_AI_ENABLED kill switch, per-pharmacy daily call cap (INVOICE_AI_DAILY_CALLS), request timeout
(INVOICE_AI_TIMEOUT_SECONDS), identical-bill cache + in-flight lock (a client retry never starts a second scan).
"""

import copy
import hashlib
import json
import logging
import mimetypes
import os
import re
import threading
import time
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple

from dotenv import load_dotenv
from google.genai import types

from ai.invoice_prompts import INVOICE_PROMPT, INVOICE_VERIFY_PROMPT
from ai import invoice_validation as val
from ai.gemini_service import (
    client,
    GEMINI_PRIMARY_MODEL,
    log_ai_metrics,
)
from ai import usage_log

logger = logging.getLogger("expiryguard.ocr")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

# ----------------------------------------------------------------------------------------------------------
# Controls
# ----------------------------------------------------------------------------------------------------------

INVOICE_AI_MAX_CALLS = 2  # hard limit of Gemini calls for one bill


def invoice_ai_enabled() -> bool:
    """Kill switch: set INVOICE_AI_ENABLED=0 on Railway to stop every invoice Gemini call instantly."""
    return os.getenv("INVOICE_AI_ENABLED", "1").strip().lower() not in ("0", "false", "no", "off")


def _daily_cap() -> int:
    try:
        return int(os.getenv("INVOICE_AI_DAILY_CALLS", "60"))
    except ValueError:
        return 60


def _timeout_seconds() -> int:
    try:
        return max(10, int(os.getenv("INVOICE_AI_TIMEOUT_SECONDS", "75")))
    except ValueError:
        return 75


_USAGE: Dict[Tuple[Any, str], int] = {}
_USAGE_LOCK = threading.Lock()


def _reserve_call(user_id: Optional[int]) -> bool:
    """Counts one Gemini call for this pharmacy today; False when the daily cap is reached. (In memory: resets
    on restart, which only ever allows more calls after a deploy, never blocks a pharmacy wrongly.)"""
    if user_id is None:
        return True
    key = (user_id, date.today().isoformat())
    with _USAGE_LOCK:
        used = _USAGE.get(key, 0)
        if used >= _daily_cap():
            return False
        _USAGE[key] = used + 1
        return True


_CACHE: "OrderedDict[str, Tuple[float, dict]]" = OrderedDict()
_CACHE_TTL = 900.0
_CACHE_MAX = 64
_CACHE_LOCK = threading.Lock()
_INFLIGHT: Dict[str, threading.Lock] = {}
_INFLIGHT_LOCK = threading.Lock()


def _bill_key(user_id: Optional[int], image_items: List[Tuple[bytes, str]]) -> str:
    h = hashlib.sha256()
    h.update(str(user_id).encode())
    for data, _mime in image_items:
        h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def _cache_get(key: str) -> Optional[dict]:
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
        if hit and time.time() - hit[0] < _CACHE_TTL:
            return copy.deepcopy(hit[1])
        _CACHE.pop(key, None)
        return None


def _cache_put(key: str, result: dict) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), copy.deepcopy(result))
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)


def reset_controls_for_tests() -> None:
    with _USAGE_LOCK:
        _USAGE.clear()
    with _CACHE_LOCK:
        _CACHE.clear()


# ----------------------------------------------------------------------------------------------------------
# Small helpers
# ----------------------------------------------------------------------------------------------------------

def _safe_float_nullable(value) -> Optional[float]:
    if value in ("", None):
        return None
    val_str = str(value).strip()
    is_negative = "-" in val_str or "(-)" in val_str or "minus" in val_str.lower()
    try:
        clean_val = re.sub(r"[^\d.]", "", val_str)
        if not clean_val:
            return None
        res = float(clean_val)
        return -res if is_negative else res
    except Exception:
        return None


def _safe_float(value, default: float = 0.0) -> float:
    val_ = _safe_float_nullable(value)
    return val_ if val_ is not None else default


def _safe_int_nullable(value) -> Optional[int]:
    if value in ("", None):
        return None
    try:
        clean_val = re.sub(r"[^\d.-]", "", str(value))
        return int(float(clean_val)) if clean_val else None
    except Exception:
        return None


def _normalize_date(date_str: str) -> str:
    """Normalises header dates (invoice date) to ISO YYYY-MM-DD; unknown formats are returned unchanged."""
    if not date_str or not isinstance(date_str, str):
        return ""
    clean = date_str.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", clean):
        return clean
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", clean)
    if m:
        day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return f"{year:04d}-{month:02d}-{day:02d}"
    return clean


def validate_invoice_data(data: dict) -> bool:
    """Parsed invoice JSON must have at least one item row with a name."""
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, list) or len(items) == 0:
        return False
    first_item = items[0]
    if not isinstance(first_item, dict) or not first_item.get("product_name"):
        return False
    return True


# ----------------------------------------------------------------------------------------------------------
# Response schema (strict shape: one object per table row)
# ----------------------------------------------------------------------------------------------------------

_SCHEMA_CACHE: List[Any] = []


def _response_schema():
    """Gemini response schema; None if this SDK version cannot build it (the prompt still defines the shape)."""
    if _SCHEMA_CACHE:
        return _SCHEMA_CACHE[0]
    try:
        S, T = types.Schema, types.Type

        def n(t):
            return S(type=t, nullable=True)

        item = S(
            type=T.OBJECT,
            properties={
                "row_no": n(T.INTEGER),
                "product_name": n(T.STRING),
                "brand": n(T.STRING),
                "hsn_code": n(T.STRING),
                "batch_number": n(T.STRING),
                "expiry_raw": n(T.STRING),
                "quantity": n(T.NUMBER),
                "free_qty": n(T.NUMBER),
                "unit": n(T.STRING),
                "purchase_price": n(T.NUMBER),
                "mrp": n(T.NUMBER),
                "discount_percent": n(T.NUMBER),
                "gst_rate": n(T.NUMBER),
                "total_price": n(T.NUMBER),
                "page_number": n(T.INTEGER),
                "uncertain_fields": S(type=T.ARRAY, items=S(type=T.STRING)),
            },
            required=["product_name", "hsn_code", "batch_number", "expiry_raw", "quantity", "purchase_price",
                      "mrp", "gst_rate", "total_price"],
        )
        header = {k: n(T.STRING) for k in ("supplier_name", "supplier_gstin", "supplier_phone", "supplier_email",
                                           "supplier_address", "invoice_number", "invoice_date",
                                           "total_amount_label")}
        header.update({k: n(T.NUMBER) for k in ("subtotal", "scheme_amount", "discount_amount", "cd_amount",
                                                "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount",
                                                "tax_amount", "other_amount", "total_amount")})
        header["rows_printed"] = n(T.INTEGER)
        header["items"] = S(type=T.ARRAY, items=item)
        schema = S(type=T.OBJECT, properties=header, required=["items"])
        _SCHEMA_CACHE.append(schema)
        return schema
    except Exception as e:  # pragma: no cover - SDK differences
        logger.warning("[INVOICE] Could not build response schema: %s", e)
        _SCHEMA_CACHE.append(None)
        return None


class _Calls:
    def __init__(self, user_id: Optional[int] = None, pages: Optional[int] = None):
        self.n = 0
        self.latency = 0.0
        self.user_id = user_id
        self.pages = pages
        self.bill_id = usage_log.new_bill_id()  # ties this bill's readings together in ai_usage_log


def _call_gemini(prompt: str, image_items: List[Tuple[bytes, str]], calls: _Calls) -> dict:
    """ONE Gemini request (counted). Raises on failure; never retries."""
    calls.n += 1
    contents: List[Any] = [prompt]
    for data, mime in image_items:
        contents.append(types.Part.from_bytes(data=data, mime_type=mime))
    kwargs: Dict[str, Any] = dict(
        temperature=0.0,
        response_mime_type="application/json",
        http_options=types.HttpOptions(timeout=_timeout_seconds() * 1000),
    )
    schema = _response_schema()
    if schema is not None:
        kwargs["response_schema"] = schema
    try:
        if "media_resolution" in types.GenerateContentConfig.model_fields:
            kwargs["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_HIGH
    except Exception:
        pass
    t0 = time.time()
    feature = "invoice_read" if calls.n == 1 else "invoice_second_pass"
    try:
        response = client.models.generate_content(
            model=GEMINI_PRIMARY_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(**kwargs),
        )
    except Exception as e:
        usage_log.record(feature=feature, outcome="timeout" if "timeout" in type(e).__name__.lower() else "error",
                         shop_id=calls.user_id, model=GEMINI_PRIMARY_MODEL, call_no=calls.n, bill_id=calls.bill_id,
                         pages=calls.pages, latency_ms=int((time.time() - t0) * 1000))
        raise
    calls.latency += time.time() - t0
    _usage = usage_log.usage_from_response(response)
    try:
        in_tokens = response.usage_metadata.prompt_token_count if response.usage_metadata else 0
        out_tokens = response.usage_metadata.candidates_token_count if response.usage_metadata else 0
    except Exception:
        in_tokens = out_tokens = 0
    log_ai_metrics("/scan-invoice", "invoice", GEMINI_PRIMARY_MODEL, True, False, time.time() - t0, in_tokens, out_tokens)

    text = (response.text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    result = None
    try:
        result = json.loads(text)
        if not isinstance(result, dict):
            raise ValueError("Gemini did not return a JSON object")
        return result
    finally:  # the call was paid for even if the reply was unusable
        usage_log.record(feature=feature, outcome="success" if isinstance(result, dict) else "error",
                         shop_id=calls.user_id, model=GEMINI_PRIMARY_MODEL, usage=_usage, call_no=calls.n,
                         bill_id=calls.bill_id, pages=calls.pages,
                         rows=len(result.get("items") or []) if isinstance(result, dict) and isinstance(result.get("items"), list) else None,
                         latency_ms=int((time.time() - t0) * 1000))


# ----------------------------------------------------------------------------------------------------------
# Item normalisation (no defaults, no inferred values)
# ----------------------------------------------------------------------------------------------------------

_FIELD_ALIASES = {"expiry_raw": "expiry_date", "expiry": "expiry_date", "ptr": "purchase_price",
                  "unit_price": "purchase_price", "rate": "purchase_price", "batch": "batch_number",
                  "hsn": "hsn_code", "qty": "quantity", "amount": "total_price", "gst": "gst_rate"}


def _normalize_item(item: dict) -> dict:
    """Maps one model row to the app's item shape. Missing stays missing: nothing is defaulted or computed."""
    qty = _safe_int_nullable(item.get("quantity") if item.get("quantity") is not None else item.get("qty"))
    free = _safe_int_nullable(item.get("free_qty") if item.get("free_qty") is not None else item.get("scheme_qty"))
    rate = _safe_float_nullable(
        item.get("purchase_price") if item.get("purchase_price") is not None
        else (item.get("ptr") if item.get("ptr") is not None else item.get("unit_price")))
    raw_exp = item.get("expiry_raw") if item.get("expiry_raw") not in (None, "") else (item.get("expiry_date") or item.get("expiry"))
    uncertain = [(_FIELD_ALIASES.get(str(f), str(f))) for f in (item.get("uncertain_fields") or []) if f]
    return {
        "row_no": _safe_int_nullable(item.get("row_no")),
        "product_name": str(item.get("product_name") or item.get("name") or "").strip(),
        "brand": str(item.get("brand") or "").strip(),
        "category": str(item.get("category") or "allopathy").strip(),
        "quantity": qty if qty and qty > 0 else None,
        "free_qty": free if free is not None and free >= 0 else None,
        "unit": str(item.get("unit") or "strip").strip(),
        "purchase_price": rate,
        "mrp": _safe_float_nullable(item.get("mrp")),
        "discount_percent": _safe_float_nullable(item.get("discount_percent") if item.get("discount_percent") is not None else item.get("dis_percent")),
        "gst_rate": _safe_float_nullable(item.get("gst_rate") if item.get("gst_rate") is not None else item.get("gst_percent")),
        "total_price": _safe_float_nullable(item.get("total_price") if item.get("total_price") is not None else item.get("amount")),
        "batch_number": str(item.get("batch_number") or item.get("batch") or "").strip(),
        "expiry_date": str(raw_exp or "").strip(),
        "hsn_code": re.sub(r"\s+", "", str(item.get("hsn_code") or item.get("hsn") or "")),
        "manufacturing_date": "",
        "page_number": _safe_int_nullable(item.get("page_number")) or 1,
        "uncertain_fields": uncertain,
        "notes": "",
    }


def _dedupe(items: List[dict]) -> List[dict]:
    """Drops an identical row repeated by overlapping photos of the same page."""
    out, seen = [], set()
    for it in items:
        name = re.sub(r"[^a-z0-9]", "", (it.get("product_name") or "").lower())
        batch = re.sub(r"[^a-z0-9]", "", (it.get("batch_number") or "").lower())
        if name and batch:
            sig = f"{name}|{batch}|{it.get('quantity')}|{it.get('purchase_price')}|{it.get('expiry_date')}"
            if sig in seen:
                continue
            seen.add(sig)
        out.append(it)
    return out


def _parse_pass(result: dict) -> Tuple[List[dict], Optional[int]]:
    raw_items = result.get("items") or []
    items = _dedupe([_normalize_item(it) for it in raw_items if isinstance(it, dict)])
    return items, _safe_int_nullable(result.get("rows_printed"))


_FIELD_LABELS = {
    "product_name": "Medicine name", "hsn_code": "HSN", "batch_number": "Batch", "expiry_date": "Expiry",
    "quantity": "Quantity", "free_qty": "Free qty", "purchase_price": "Purchase rate", "mrp": "MRP",
    "gst_rate": "GST %", "total_price": "Amount",
}

_BLANK_NUMERIC = ("quantity", "free_qty", "purchase_price", "mrp", "gst_rate", "total_price")


def _blank(item: dict, field: str) -> None:
    item[field] = None if field in _BLANK_NUMERIC else ""


def _is_plain_missing(reason: str) -> bool:
    """A value that is simply absent from the bill (no MRP column, no expiry printed...). Reading again cannot
    help, so it does not trigger the second reading."""
    return "missing" in reason.lower()


# ----------------------------------------------------------------------------------------------------------
# One bill
# ----------------------------------------------------------------------------------------------------------

def _validate_all(items: List[dict], printed_rows: Optional[int], printed_subtotal: Any) -> Tuple[List[Dict[str, str]], List[str]]:
    flags = []
    for it in items:
        f = val.validate_item(it)
        for fld in it.get("uncertain_fields") or []:
            if fld in val.CRITICAL_FIELDS and fld not in f and it.get(fld) not in (None, ""):
                f[fld] = "the reader was not sure of this value"
                _blank(it, fld)
        flags.append(f)
    notes = []
    rc = val.check_row_count(len(items), printed_rows)
    if rc:
        notes.append(rc)
    tot = val.check_totals(items, printed_subtotal)
    if tot:
        notes.append(tot)
    return flags, notes


def _needs_second_pass(flags: List[Dict[str, str]], notes: List[str], row_count: int) -> bool:
    """Second reading only for a real integrity problem or a dense grid; a merely absent value (no MRP column,
    no GST printed) cannot be fixed by reading again and does not trigger it."""
    if val.is_dense(row_count):
        return True
    if notes:
        return True
    return any(not _is_plain_missing(reason) for f in flags for reason in f.values())


def _merge(first: List[dict], first_flags: List[Dict[str, str]], second: List[dict]) -> List[Dict[str, str]]:
    """Blanks and flags every critical field the two readings disagree on."""
    for it in second:
        val.validate_item(it)  # same normalisation (e.g. expiry to a date) so values are comparable
    cmp_flags, _ = val.compare_passes(first, second)
    merged = []
    for it, f, c in zip(first, first_flags, cmp_flags):
        f = dict(f)
        for fld, reason in c.items():
            _blank(it, fld)
            f[fld] = reason
        merged.append(f)
    return merged


def _header_and_reconciliation(result: dict, items: List[dict]) -> dict:
    raw_subtotal = _safe_float(result.get("subtotal"))
    raw_scheme = _safe_float(result.get("scheme_amount"))
    raw_cd = _safe_float(result.get("cd_amount"))
    raw_disc = _safe_float(result.get("discount_amount"))
    if raw_disc == 0.0 and (raw_scheme > 0 or raw_cd > 0):
        raw_disc = round(raw_scheme + raw_cd, 2)
    raw_taxable = _safe_float(result.get("taxable_amount"))
    raw_cgst = _safe_float(result.get("cgst_amount"))
    raw_sgst = _safe_float(result.get("sgst_amount"))
    raw_igst = _safe_float(result.get("igst_amount"))
    raw_tax = _safe_float(result.get("tax_amount"))
    if raw_cgst > 0 or raw_sgst > 0 or raw_igst > 0:
        raw_tax = round(raw_cgst + raw_sgst + raw_igst, 2)
    raw_other = _safe_float(result.get("other_amount"))
    raw_total = _safe_float_nullable(result.get("total_amount"))          # missing stays None: never a genuine 0.00
    if raw_total is not None and raw_total <= 0:
        raw_total = None
    label = str(result.get("total_amount_label") or "").strip()

    calculated_subtotal = round(sum((it.get("total_price") or 0.0) for it in items), 2)
    effective_discounts = raw_disc if raw_disc > 0 else (raw_scheme + raw_cd)
    calculated_taxable = round(max(0.0, raw_subtotal - effective_discounts), 2) if raw_subtotal else 0.0
    calculated_net_total = round(raw_taxable + raw_tax + raw_other, 2) if raw_taxable else 0.0
    subtotal_match = (not raw_subtotal) or abs(raw_subtotal - calculated_subtotal) <= max(2.0, 0.02 * raw_subtotal)
    net_match = (raw_total is None or not calculated_net_total) or abs(raw_total - calculated_net_total) <= 1.0

    reconciliation = {
        "subtotal_status": "PASS" if subtotal_match else "REVIEW",
        "calculated_subtotal": calculated_subtotal,
        "printed_subtotal": raw_subtotal,
        "subtotal_diff": round(raw_subtotal - calculated_subtotal, 2),
        "discount_status": "PASS",
        "scheme_amount": raw_scheme,
        "cd_amount": raw_cd,
        "total_discount": effective_discounts,
        "taxable_status": "PASS" if (not raw_taxable or abs(raw_taxable - calculated_taxable) <= 1.0) else "REVIEW",
        "calculated_taxable": calculated_taxable,
        "printed_taxable": raw_taxable,
        "gst_status": "PASS",
        "cgst_amount": raw_cgst,
        "sgst_amount": raw_sgst,
        "igst_amount": raw_igst,
        "total_gst": raw_tax,
        "net_total_status": "PASS" if net_match else "REVIEW",
        "calculated_net_total": calculated_net_total,
        "printed_net_total": raw_total,
        "printed_total_status": "READ" if raw_total is not None else "MISSING",
        "net_total_diff": round(raw_total - calculated_net_total, 2) if raw_total is not None else None,
        "total_amount_label": label,
        "overall_status": "PASS" if (subtotal_match and net_match) else "REVIEW",
    }
    return {
        "supplier_name": str(result.get("supplier_name") or "").strip(),
        "supplier_gstin": str(result.get("supplier_gstin") or "").strip(),
        "supplier_phone": str(result.get("supplier_phone") or "").strip(),
        "supplier_email": str(result.get("supplier_email") or "").strip(),
        "supplier_address": str(result.get("supplier_address") or "").strip(),
        "invoice_number": str(result.get("invoice_number") or "").strip(),
        "invoice_date": _normalize_date(str(result.get("invoice_date") or "")),
        "subtotal": raw_subtotal,
        "scheme_amount": raw_scheme,
        "cd_amount": raw_cd,
        "discount_amount": raw_disc,
        "taxable_amount": raw_taxable,
        "cgst_amount": raw_cgst,
        "sgst_amount": raw_sgst,
        "igst_amount": raw_igst,
        "tax_amount": raw_tax,
        "other_amount": raw_other,
        "total_amount": raw_total,
        "total_amount_label": label,
        "reconciliation": reconciliation,
    }


def _finish_items(items: List[dict], flags: List[Dict[str, str]], bill_notes: List[str], incomplete: bool) -> List[dict]:
    """Adds the per-field flags and the legacy review fields (needs_review / review_reasons / ptr / unit_price)."""
    totals_bad = any("add up to" in n for n in bill_notes)
    out = []
    for it, f in zip(items, flags):
        reasons = [f"{_FIELD_LABELS.get(k, k)}: {v}" for k, v in f.items()]
        needs = bool(f) or incomplete or totals_bad
        if totals_bad and not f:
            reasons.append("Bill total does not match the line amounts: verify every row against the bill")
        if incomplete:
            reasons.append("The verification reading could not be completed: verify this row against the bill")
        it = dict(it)
        it.pop("uncertain_fields", None)
        it["unit_price"] = it.get("purchase_price")
        it["ptr"] = it.get("purchase_price")
        it["confidence"] = 0.4 if f else (0.7 if needs else 0.95)
        it["field_flags"] = f
        it["needs_review"] = needs
        it["review_reasons"] = reasons
        out.append(it)
    return out


def _manual_entry(error: str, reason: str, calls: int = 0) -> dict:
    return {"success": False, "data": None, "error": error, "needs_manual_entry": True,
            "reason": reason, "gemini_calls": calls}


def scan_invoice(image_input: Union[str, Path, bytes, List[Union[str, Path, bytes]]],
                 mime_type: str = "image/jpeg", user_id: Optional[int] = None) -> dict:
    """
    Reads one supplier invoice. Returns {"success", "data", "error", ...}; on any failure the result has
    needs_manual_entry=True so the app lets the user type the bill. Never saves anything.
    """
    inputs = image_input if isinstance(image_input, list) else [image_input]
    image_items: List[Tuple[bytes, str]] = []
    for inp in inputs:
        if isinstance(inp, (str, Path)):
            f = Path(str(inp))
            if not f.exists():
                logger.error("[INVOICE] file not found")
                continue
            guessed, _ = mimetypes.guess_type(f)
            image_items.append((f.read_bytes(), guessed or ("application/pdf" if f.suffix.lower() == ".pdf" else "image/jpeg")))
        elif isinstance(inp, bytes):
            image_items.append((inp, mime_type))
    if not image_items:
        return _manual_entry("No valid invoice image was provided.", "no_image")

    if not invoice_ai_enabled():
        return _manual_entry("Automatic invoice reading is switched off. Please enter the bill manually.", "disabled")

    key = _bill_key(user_id, image_items)
    with _INFLIGHT_LOCK:
        lock = _INFLIGHT.setdefault(key, threading.Lock())
    with lock:
        cached = _cache_get(key)
        if cached is not None:
            cached.setdefault("data", {}).setdefault("validation", {})["from_cache"] = True
            usage_log.record(feature="invoice_read", outcome="cache_hit", shop_id=user_id, model=GEMINI_PRIMARY_MODEL,
                             zero_cost=True, bill_id=usage_log.new_bill_id(), pages=len(image_items))
            return cached
        result = _scan_uncached(image_items, user_id)
        if result.get("success"):
            _cache_put(key, result)
        return result


def _scan_uncached(image_items: List[Tuple[bytes, str]], user_id: Optional[int]) -> dict:
    t0 = time.time()
    calls = _Calls(user_id=user_id, pages=len(image_items))

    if not _reserve_call(user_id):
        return _manual_entry("The daily limit for automatic invoice reading is reached. Please enter the bill manually.", "daily_cap")

    try:
        r1 = _call_gemini(INVOICE_PROMPT, image_items, calls)
    except Exception as e:
        logger.warning("[INVOICE] first reading failed: %s", type(e).__name__)
        log_ai_metrics("/scan-invoice", "invoice", GEMINI_PRIMARY_MODEL, False, False, time.time() - t0, error=type(e).__name__)
        return _manual_entry("The invoice could not be read. Please retake the photo or enter the bill manually.", "gemini_failed", calls.n)

    items1, printed1 = _parse_pass(r1)
    if not items1:
        return _manual_entry("No item rows could be read from this bill. Please enter it manually.", "no_rows", calls.n)

    flags, notes = _validate_all(items1, printed1, r1.get("subtotal"))
    dense = val.is_dense(len(items1))
    second_needed = _needs_second_pass(flags, notes, len(items1))
    passes_used, incomplete = 1, False

    if second_needed:
        if calls.n >= INVOICE_AI_MAX_CALLS or not _reserve_call(user_id):
            incomplete = True
            notes.append("verification reading skipped (call limit reached)")
        else:
            try:
                r2 = _call_gemini(INVOICE_VERIFY_PROMPT, image_items, calls)
                items2, _printed2 = _parse_pass(r2)
                flags = _merge(items1, flags, items2)
                passes_used = 2
                cmp_notes = val.compare_passes(items1, items2)[1]
                notes.extend(cmp_notes)
            except Exception as e:
                logger.warning("[INVOICE] verification reading failed: %s", type(e).__name__)
                incomplete = True
                notes.append("verification reading failed")

    items = _finish_items(items1, flags, notes, incomplete)
    invoice = _header_and_reconciliation(r1, items)
    flagged_rows = sum(1 for it in items if it["field_flags"])
    invoice["items"] = items
    invoice["validation"] = {
        "passes_used": passes_used,
        "gemini_calls": calls.n,
        "rows_extracted": len(items),
        "rows_printed": printed1,
        "dense_grid": dense,
        "flagged_rows": flagged_rows,
        "notes": notes,
        "verification_incomplete": incomplete,
        "from_cache": False,
    }
    invoice["needs_manual_entry"] = False

    logger.info(
        "[INVOICE] rows=%d flagged_rows=%d passes=%d gemini_calls=%d dense=%s notes=%d latency=%.1fs",
        len(items), flagged_rows, passes_used, calls.n, dense, len(notes), time.time() - t0,
    )
    return {"success": True, "data": invoice, "error": None, "gemini_calls": calls.n}
