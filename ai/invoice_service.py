import json
import logging
import mimetypes
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

from dotenv import load_dotenv
from google.genai import types

try:
    from ai.prompts.invoice_prompt import INVOICE_PROMPT
except (ImportError, ModuleNotFoundError):
    INVOICE_PROMPT = """
You are an expert AI Indian pharmaceutical invoice & receipt reader for pharmacy inventory management.

Analyze the provided supplier purchase invoice photo(s) / document page(s) carefully.
The image(s) represent 1 or consecutive pages/photos of ONE SINGLE pharmacy purchase invoice.

Extract ALL visible header metadata, summary financial totals (Subtotal, CD Amt / Discount, Taxable Base, CGST, SGST, Total Tax, Other Adjustments, Grand Total), and EVERY SINGLE line item across ALL pages into ONE combined invoice response.

Return strict valid JSON with the following schema:

{
  "supplier_name": "Full Distributor / Supplier Name printed at the top (e.g., CA Connect, Micro Labs Ltd)",
  "supplier_gstin": "Supplier GSTIN / Tax ID if present (string or null)",
  "supplier_phone": "Supplier phone number if present (string or null)",
  "supplier_email": "Supplier email if present (string or null)",
  "supplier_address": "Supplier address if present (string or null)",
  "invoice_number": "Invoice / Bill Number (e.g. CA006418, INV-2048, 24-25/1042) (string or null)",
  "invoice_date": "Invoice date formatted strictly as YYYY-MM-DD (e.g. 2026-07-29). Convert DD-MM-YYYY or DD/MM/YYYY to YYYY-MM-DD.",
  "subtotal": 6135.60,
  "scheme_amount": 83.79,
  "discount_amount": 83.79,
  "cd_amount": 245.42,
  "taxable_amount": 5806.39,
  "cgst_amount": 147.25,
  "sgst_amount": 147.25,
  "igst_amount": 0.0,
  "tax_amount": 294.50,
  "other_amount": -0.32,
  "total_amount": 6100.57,
  "total_amount_label": "Invoice Value Net",
  "items": [
    {
      "product_name": "Full medicine / item description including packing and strength (e.g. ELTROXIN 75 MG 100'S, PAN 40 TAB)",
      "brand": "Manufacturer / Brand name if shown (e.g. GSK, ALKEM, SUN PHARMA)",
      "batch_number": "Batch / Lot number (e.g. 3W41, BRG03208B). If not clearly visible, return null.",
      "quantity": 10,
      "free_qty": 0,
      "unit": "strip/box/bottle/tab/pack",
      "ptr": 110.0,
      "unit_price": 110.0,
      "purchase_price": 110.0,
      "mrp": 150.0,
      "total_price": 1100.0,
      "discount_percent": 0.0,
      "gst_rate": 5.0,
      "hsn_code": "3004",
      "expiry_date": "YYYY-MM-DD. Convert MM/YY (e.g. 3/28 or 03/28) to 2028-03-01. Return null if unreadable.",
      "manufacturing_date": "YYYY-MM-DD or null",
      "page_number": 1,
      "confidence": 0.95
    }
  ]
}

CRITICAL MULTI-PAGE & EXTRACTION RULES:
1. COMBINE ALL PAGES INTO ONE INVOICE: Treat all provided images as consecutive pages of ONE single invoice. Extract every line item from Page 1, Page 2, Page 3, etc. into the single "items" array in sequence. Do NOT limit items (10, 20, 30, 50+ items).
2. TRACK PAGE NUMBERS: For each item in "items", set "page_number" to 1 for items on the first photo/page, 2 for the second photo/page, etc.
3. FINANCIAL SUMMARY EXTRACTION:
   - Extract summary financial totals (Subtotal, Scheme Amt, CD Amt, Taxable Base, CGST, SGST, Total Tax, Other Adjustments, Grand Total) from the document (usually on Page 1 header or final page footer).
   - "subtotal": Gross line item total before discounts (e.g. 6135.60 or sum of Qty * PTR).
   - "scheme_amount": Trade / Scheme discount printed in summary footer (e.g., Scheme Amt = 83.79). If none, set 0.0.
   - "cd_amount": Cash Discount (CD Amt / CD %) printed in summary footer (e.g., CD Amt = 245.42). If none, set 0.0.
   - "discount_amount": Total discount (sum of scheme_amount + cd_amount or total line discounts).
   - "taxable_amount": Net taxable base (e.g. Subtotal - Scheme - CD = 5806.39).
   - "cgst_amount" & "sgst_amount": CGST (e.g. 147.25) and SGST (e.g. 147.25) printed at summary.
   - "tax_amount": Total GST amount (e.g. 294.50).
   - "other_amount": Other adjustments, TCS, or round-off printed at footer (e.g., OTHER = -0.32). Preserve negative sign (-0.32).
   - "total_amount": Final Net Payable Invoice Value printed on invoice (e.g. 12986.80 or 6100.57).
   - "total_amount_label": Extract the exact printed label text adjacent to total_amount (e.g., "Invoice Value Net", "Net Amount", "Grand Total", "Total Payable").
   - STRICT RULE FOR TOTAL AMOUNT: Extract "total_amount" ONLY from explicit net payable invoice total labels like "Invoice Value Net", "Net Amount", "Grand Total", "Total Payable", "Net Payable", or "Bill Total". NEVER, UNDER ANY CIRCUMSTANCES, select "Total MRP", "MRP Total", "Previous Balance", "Current Balance", "Account Balance", "Balance Due", or "Amount in words" if it represents account balance or MRP total.
4. PTR vs MRP:
   - P.T.R. (Price to Retailer / Purchase Rate / Rate) is the wholesale price charged to the pharmacy for 1 unit/pack.
   - M.R.P. is the Maximum Retail Price printed on the package.
   - Extract PTR into "ptr", "unit_price", and "purchase_price". Extract MRP into "mrp".
   - DO NOT copy MRP into ptr or purchase_price.
5. GST %:
   - Extract total GST percentage (CGST% + SGST% or IGST%) into "gst_rate" as a float (e.g. 5.0, 12.0, 18.0, 0.0). If missing, return JSON null. DO NOT DEFAULT TO 12.0!
6. QUANTITY & SCHEME / FREE QTY:
   - "quantity": Billed quantity as an integer.
   - "free_qty": Free / scheme quantity (e.g., if 10+2 is written, quantity is 10 and free_qty is 2). Default free_qty to 0.
7. EXPIRY DATE:
   - Convert MM/YY (e.g. "3/28", "03/28") to "2028-03-01". If unreadable, return JSON null.
8. NO SILENT DEFAULTS:
   - If a numeric field is missing or unreadable, return JSON null instead of inventing values or defaulting to 1, 0.0, or 12.0.
9. Return ONLY valid JSON. Do not wrap in markdown backticks.
"""
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
    val = _safe_float_nullable(value)
    return val if val is not None else default


def _safe_int_nullable(value) -> Optional[int]:
    if value in ("", None):
        return None
    try:
        clean_val = re.sub(r"[^\d.-]", "", str(value))
        return int(float(clean_val)) if clean_val else None
    except Exception:
        return None


def _safe_int(value, default: int = 1) -> int:
    val = _safe_int_nullable(value)
    return val if val is not None else default


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
    Ensures every product has proper typed fields without silent fake defaults.
    Flags items needing user review if critical values are missing.
    """
    review_reasons = []
    
    product_name = str(item.get("product_name") or item.get("name") or "").strip()
    if not product_name:
        review_reasons.append("Medicine name missing")
        
    qty = _safe_int_nullable(item.get("quantity"))
    free_qty = _safe_int(item.get("free_qty") or item.get("scheme_qty"), default=0)
    
    if qty is None or qty <= 0:
        review_reasons.append("Quantity missing or unreadable")
        qty_val = None
    else:
        qty_val = qty

    # PTR / Purchase Rate extraction
    raw_ptr = item.get("ptr") or item.get("unit_price") or item.get("purchase_price")
    ptr_val = _safe_float_nullable(raw_ptr)
    
    t_price = _safe_float_nullable(item.get("total_price"))
    mrp_val = _safe_float_nullable(item.get("mrp"))
    disc_val = _safe_float(item.get("discount_percent") or item.get("dis_percent"), default=0.0)

    # Compute PTR if missing but Total Price & Qty exist
    if ptr_val is None and t_price is not None and qty_val is not None and qty_val > 0:
        ptr_val = round(t_price / qty_val, 2)
    elif ptr_val is None and mrp_val is not None and disc_val > 0:
        ptr_val = round(mrp_val * (1.0 - (disc_val / 100.0)), 2)

    if ptr_val is None or ptr_val <= 0:
        review_reasons.append("Purchase price (PTR) missing")

    # Compute Total Price if missing
    if t_price is None and ptr_val is not None and qty_val is not None:
        t_price = round(ptr_val * qty_val, 2)

    # Batch and Expiry
    batch_no = str(item.get("batch_number") or item.get("batch") or "").strip()
    if not batch_no:
        review_reasons.append("Batch number missing")
        
    raw_exp = str(item.get("expiry_date") or item.get("expiry") or "")
    exp_date = _normalize_date(raw_exp)
    if not exp_date:
        review_reasons.append("Expiry date missing or unreadable")

    # GST Rate (DO NOT default to 12.0)
    raw_gst = item.get("gst_rate") or item.get("gst_percent")
    gst_val = _safe_float_nullable(raw_gst)
    if gst_val is None:
        review_reasons.append("GST rate missing")

    hsn = str(item.get("hsn_code") or "").strip()
    brand = str(item.get("brand") or "").strip()
    unit = str(item.get("unit") or "strip").strip()
    page_no = _safe_int(item.get("page_number"), default=1)
    confidence = _safe_float(item.get("confidence"), default=1.0)
    
    needs_review = len(review_reasons) > 0

    return {
        "product_name": product_name,
        "brand": brand,
        "category": str(item.get("category") or "allopathy").strip(),
        "quantity": qty_val,
        "free_qty": free_qty,
        "unit": unit,
        "unit_price": ptr_val,
        "ptr": ptr_val,
        "purchase_price": ptr_val,
        "total_price": t_price,
        "mrp": mrp_val,
        "discount_percent": disc_val,
        "batch_number": batch_no,
        "manufacturing_date": _normalize_date(str(item.get("manufacturing_date") or "")),
        "expiry_date": exp_date,
        "hsn_code": hsn,
        "gst_rate": gst_val,
        "page_number": page_no,
        "confidence": confidence,
        "needs_review": needs_review,
        "review_reasons": review_reasons,
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


def scan_invoice(image_input: Union[str, Path, bytes, List[Union[str, Path, bytes]]], mime_type: str = "image/jpeg") -> dict:
    """
    Scan supplier invoice using Gemini Vision.
    Supports single or multiple image/page inputs belonging to the same invoice.
    Features image optimization, multi-page chunking, schema validation, overlap deduplication, and retry logic.
    """
    start_time = time.time()

    # Normalize image_input to a list of (image_bytes, mime_type)
    image_items = []
    if isinstance(image_input, list):
        input_list = image_input
    else:
        input_list = [image_input]

    for inp in input_list:
        if isinstance(inp, (str, Path)):
            ipath = str(inp)
            optimize_image(ipath)
            ifile = Path(ipath)
            if not ifile.exists():
                logger.error(f"[OCR] File not found: {ipath}")
                continue
            guessed_mime, _ = mimetypes.guess_type(ifile)
            mtype = guessed_mime or ("application/pdf" if ifile.suffix.lower() == ".pdf" else "image/jpeg")
            image_items.append((ifile.read_bytes(), mtype))
        elif isinstance(inp, bytes):
            image_items.append((inp, mime_type))

    if not image_items:
        return {
            "success": False,
            "data": None,
            "error": "No valid image files provided."
        }

    logger.info(f"[OCR:START] Scanning invoice document with {len(image_items)} page image(s)...")

    # Build Gemini prompt contents with all image parts in user-selected page order
    contents = [INVOICE_PROMPT]
    for ibytes, mtype in image_items:
        contents.append(types.Part.from_bytes(data=ibytes, mime_type=mtype))

    last_error = None
    candidate_models = [
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.5-flash",
        "gemini-1.5-flash",
    ]
    if GEMINI_PRIMARY_MODEL and GEMINI_PRIMARY_MODEL not in candidate_models:
        candidate_models.insert(0, GEMINI_PRIMARY_MODEL)

    for target_model in candidate_models:
        try:
            logger.info(f"[OCR:TRY] Attempting invoice OCR ({len(image_items)} pages) with model: {target_model}")
            response = client.models.generate_content(
                model=target_model,
                contents=contents,
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

            # Extract header metadata & financial totals
            raw_inv_date = result.get("invoice_date", "")
            norm_inv_date = _normalize_date(str(raw_inv_date))
            
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

            raw_other = _safe_float(result.get("other_amount") or result.get("roundoff_amount"))
            raw_total = _safe_float(result.get("total_amount") or result.get("grand_total") or result.get("net_amount"))
            raw_total_label = str(result.get("total_amount_label") or "").strip()

            raw_items = result.get("items", [])
            normalized_items = [_normalize_item(it) for it in raw_items if isinstance(it, dict)]

            # Deduplicate overlapping rows across multi-photo scans
            deduped_items = []
            seen_signatures = set()
            for it in normalized_items:
                name_clean = re.sub(r"[^a-z0-9]", "", (it.get("product_name") or "").lower())
                batch_clean = re.sub(r"[^a-z0-9]", "", (it.get("batch_number") or "").lower())
                qty = str(it.get("quantity") or "")
                ptr = f"{it.get('ptr') or 0.0:.2f}"
                
                if name_clean and batch_clean:
                    sig = f"{name_clean}|{batch_clean}|{qty}|{ptr}"
                    if sig in seen_signatures:
                        logger.info(f"[OCR:DEDUP] Dropped overlapping duplicate line item '{it.get('product_name')}' (Batch {it.get('batch_number')})")
                        continue
                    seen_signatures.add(sig)
                elif name_clean and not batch_clean:
                    exp = str(it.get("expiry_date") or "")
                    sig = f"{name_clean}|nobatch|{qty}|{ptr}|{exp}"
                    if sig in seen_signatures:
                        logger.info(f"[OCR:DEDUP] Dropped duplicate line item '{it.get('product_name')}' without batch")
                        continue
                    seen_signatures.add(sig)
                    
                deduped_items.append(it)

            # Reconcile calculations dynamically
            calculated_subtotal = round(sum((it.get("total_price") or 0.0) for it in deduped_items), 2)
            if raw_subtotal == 0.0 and deduped_items:
                raw_subtotal = calculated_subtotal

            effective_discounts = raw_disc if raw_disc > 0 else (raw_scheme + raw_cd)
            calculated_taxable = round(max(0.0, raw_subtotal - effective_discounts), 2)
            if raw_taxable == 0.0 and raw_subtotal > 0:
                raw_taxable = calculated_taxable

            calculated_net_total = round(raw_taxable + raw_tax + raw_other, 2)
            if raw_total == 0.0 and raw_taxable > 0:
                raw_total = calculated_net_total

            # Field-level reconciliation verification
            subtotal_match = abs(raw_subtotal - calculated_subtotal) <= 1.00
            net_total_match = abs(raw_total - calculated_net_total) <= 1.00

            reconciliation = {
                "subtotal_status": "PASS" if subtotal_match else "REVIEW",
                "calculated_subtotal": calculated_subtotal,
                "printed_subtotal": raw_subtotal,
                "subtotal_diff": round(raw_subtotal - calculated_subtotal, 2),

                "discount_status": "PASS",
                "scheme_amount": raw_scheme,
                "cd_amount": raw_cd,
                "total_discount": effective_discounts,

                "taxable_status": "PASS" if abs(raw_taxable - calculated_taxable) <= 1.00 else "REVIEW",
                "calculated_taxable": calculated_taxable,
                "printed_taxable": raw_taxable,

                "gst_status": "PASS",
                "cgst_amount": raw_cgst,
                "sgst_amount": raw_sgst,
                "igst_amount": raw_igst,
                "total_gst": raw_tax,

                "net_total_status": "PASS" if net_total_match else "REVIEW",
                "calculated_net_total": calculated_net_total,
                "printed_net_total": raw_total,
                "net_total_diff": round(raw_total - calculated_net_total, 2),
                "total_amount_label": raw_total_label,

                "overall_status": "PASS" if (subtotal_match and net_total_match) else "REVIEW",
            }

            invoice = {
                "supplier_name": str(result.get("supplier_name") or "").strip(),
                "supplier_gstin": str(result.get("supplier_gstin") or "").strip(),
                "supplier_phone": str(result.get("supplier_phone") or "").strip(),
                "supplier_email": str(result.get("supplier_email") or "").strip(),
                "supplier_address": str(result.get("supplier_address") or "").strip(),
                "invoice_number": str(result.get("invoice_number") or "").strip(),
                "invoice_date": norm_inv_date,
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
                "total_amount_label": raw_total_label,
                "reconciliation": reconciliation,
                "items": deduped_items
            }

            logger.info(
                f"[OCR:SUCCESS] Invoice #{invoice['invoice_number']} | Date: {invoice['invoice_date']} | "
                f"Subtotal: ₹{invoice['subtotal']} | Scheme: -₹{invoice['scheme_amount']} | CD Amt: -₹{invoice['cd_amount']} | "
                f"Taxable: ₹{invoice['taxable_amount']} | GST: ₹{invoice['tax_amount']} | Other: ₹{invoice['other_amount']} | "
                f"Total: ₹{invoice['total_amount']} ({invoice['total_amount_label']}) | Reconciliation: {reconciliation['overall_status']} | Items: {len(deduped_items)}"
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
            logger.warning(f"[OCR_WARNING] Model {target_model} failed: {e}")
            continue

    # All attempts failed
    latency = time.time() - start_time
    log_ai_metrics("/documents/{id}/ocr", "invoice", GEMINI_PRIMARY_MODEL, False, False, latency, error=last_error)
    return {
        "success": False,
        "data": None,
        "error": "Dawaiflow AI was unable to parse this invoice. Please ensure the image is clear or upload an Excel/CSV file."
    }