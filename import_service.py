import os
import re
import uuid
import datetime
from io import BytesIO
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
from datetime import date, timedelta

# Known header aliases for legacy pharmacy ERP software (Marg ERP, MargBooks, Vyapar, Tally, etc.)
HEADER_ALIASES: Dict[str, List[str]] = {
    "product_name": [
        "product_name", "product name", "product", "item_name", "item name", "item",
        "medicine_name", "medicine name", "medicine", "particulars", "description",
        "drug_name", "drug name", "brand", "brand name", "name", "items"
    ],
    "price": [
        "price", "mrp", "sale_price", "sale price", "selling_price", "selling price",
        "unit_price", "unit price", "rate", "s.rate", "sales rate", "s_rate", "m.r.p"
    ],
    "purchase_price": [
        "purchase_price", "purchase price", "purchase_rate", "purchase rate",
        "p.rate", "p_rate", "cost_price", "cost price", "buying_price", "buying price",
        "cost", "p.price", "buy rate"
    ],
    "hsn_code": [
        "hsn_code", "hsn code", "hsn", "hsn/sac", "sac_code", "sac code", "sac", "hsn_sac"
    ],
    "gst_rate": [
        "gst_rate", "gst rate", "gst", "gst %", "gst_percentage", "tax_rate", "tax rate",
        "tax %", "cgst+sgst", "gst_pct", "tax"
    ],
    "stock_quantity": [
        "stock_quantity", "stock quantity", "stock_qty", "stock qty", "stock", "qty",
        "quantity", "closing_stock", "closing stock", "available_stock", "balance",
        "curr_stock", "current stock", "balance stock"
    ],
    "expiry_date": [
        "expiry_date", "expiry date", "exp_date", "exp date", "expiry", "exp",
        "val_date", "validity", "exp.date", "exp_dt", "expiry_dt"
    ],
    "batch_number": [
        "batch_number", "batch number", "batch_no", "batch no", "batch", "b.no",
        "lot_no", "lot no", "b_no", "batch_id"
    ],
    "tablets_per_strip": [
        "tablets_per_strip", "tablets per strip", "packing", "pack", "units/strip",
        "tabs/strip", "pack_size", "pack size", "strip_size", "strip size"
    ],
    "category": [
        "category", "cat", "group", "product_group", "item_group", "type"
    ]
}

TEMP_CACHE_DIR = os.path.join(os.path.dirname(__file__), "temp_import_cache")
os.makedirs(TEMP_CACHE_DIR, exist_ok=True)

def normalize_header(header: str) -> str:
    """Normalize string for header comparison by lowercasing and stripping special chars."""
    if not isinstance(header, str):
        header = str(header)
    return re.sub(r'[^a-z0-9]', '', header.lower())

def auto_detect_mapping(file_headers: List[str]) -> Tuple[Dict[str, str], List[str]]:
    """
    Auto-detect column mapping by matching uploaded file headers against alias sets.
    Returns (detected_mapping: {field_name: file_header}, unmapped_headers: list)
    """
    detected_mapping: Dict[str, str] = {}
    mapped_file_headers = set()

    # Pre-normalize uploaded headers
    normalized_file_headers = {h: normalize_header(h) for h in file_headers}

    for internal_field, aliases in HEADER_ALIASES.items():
        matched_header = None
        for alias in aliases:
            norm_alias = normalize_header(alias)
            for raw_h, norm_h in normalized_file_headers.items():
                if raw_h in mapped_file_headers:
                    continue
                if norm_h == norm_alias:
                    matched_header = raw_h
                    break
            if matched_header:
                break
        
        # Secondary partial matching if exact match failed
        if not matched_header:
            for alias in aliases:
                norm_alias = normalize_header(alias)
                if len(norm_alias) < 3:
                    continue
                for raw_h, norm_h in normalized_file_headers.items():
                    if raw_h in mapped_file_headers:
                        continue
                    if norm_alias in norm_h or norm_h in norm_alias:
                        matched_header = raw_h
                        break
                if matched_header:
                    break

        if matched_header:
            detected_mapping[internal_field] = matched_header
            mapped_file_headers.add(matched_header)

    unmapped = [h for h in file_headers if h not in mapped_file_headers]
    return detected_mapping, unmapped

def read_file_to_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Reads uploaded bytes into a pandas DataFrame supporting .csv, .tsv, .xlsx, .xls."""
    ext = os.path.splitext(filename.lower())[1]
    if ext in ['.xlsx', '.xls']:
        df = pd.read_excel(BytesIO(file_bytes))
    elif ext in ['.tsv']:
        df = pd.read_csv(BytesIO(file_bytes), sep='\t')
    else:
        # Default to CSV with fallback encodings for Marg ERP exports (utf-8, latin-1, cp1252)
        try:
            df = pd.read_csv(BytesIO(file_bytes), encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(BytesIO(file_bytes), encoding='latin-1')

    # Drop completely empty rows
    df = df.dropna(how='all')
    # Strip string column names
    df.columns = [str(col).strip() for col in df.columns]
    return df

def parse_date_flexible(val: Any) -> Tuple[Optional[date], Optional[str]]:
    """
    Parses various date strings (ISO, DD/MM/YYYY, MM/YY, MM/YYYY, Excel serials).
    Returns (parsed_date: date | None, warning_message: str | None).
    """
    if pd.isna(val) or val is None or str(val).strip() in ['', 'nan', 'NaT', 'None']:
        # Default expiry: 1 year from today if missing
        default_exp = date.today() + timedelta(days=365)
        return default_exp, "Expiry date missing; defaulted to 1 year from today."

    val_str = str(val).strip()

    # Handle pandas / python datetime objects directly
    if isinstance(val, (datetime.datetime, datetime.date, pd.Timestamp)):
        if isinstance(val, pd.Timestamp):
            return val.date(), None
        if isinstance(val, datetime.datetime):
            return val.date(), None
        return val, None

    # Handle numeric Excel serial dates (e.g. 45657)
    if val_str.isdigit() and len(val_str) in [4, 5]:
        try:
            excel_base = datetime.date(1899, 12, 30)
            parsed = excel_base + timedelta(days=int(val_str))
            return parsed, None
        except Exception:
            pass

    # Common Indian Pharma date formats
    date_formats = [
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
        "%m/%Y", "%m-%Y", "%b-%Y", "%b %Y", "%B %Y",
        "%m/%y", "%m-%y", "%b-%y", "%y-%m-%d"
    ]

    for fmt in date_formats:
        try:
            dt = datetime.datetime.strptime(val_str, fmt).date()
            # If format was MM/YYYY or MM/YY, pick the end of month
            if fmt in ["%m/%Y", "%m-%Y", "%b-%Y", "%b %Y", "%B %Y", "%m/%y", "%m-%y", "%b-%y"]:
                # Jump to next month 1st day then minus 1 day
                year = dt.year
                month = dt.month
                if month == 12:
                    dt = datetime.date(year, 12, 31)
                else:
                    next_month = datetime.date(year, month + 1, 1)
                    dt = next_month - timedelta(days=1)
            return dt, None
        except ValueError:
            continue

    # Fallback default
    default_exp = date.today() + timedelta(days=365)
    return default_exp, f"Could not parse expiry date '{val_str}'; defaulted to 1 year from today."

def validate_and_normalize_row(
    row: pd.Series,
    mapping: Dict[str, str],
    row_index: int
) -> Tuple[Optional[Dict[str, Any]], List[str], Optional[str]]:
    """
    Validates a single row against mapping.
    Returns (cleaned_dict, warnings_list, error_reason).
    """
    warnings: List[str] = []

    # 1. Product Name (REQUIRED)
    name_col = mapping.get("product_name")
    if not name_col or name_col not in row or pd.isna(row[name_col]):
        return None, [], f"Row {row_index}: Missing required field 'product_name'."
    
    product_name = str(row[name_col]).strip()
    if not product_name or product_name.lower() == 'nan':
        return None, [], f"Row {row_index}: Empty product name."

    # 2. Selling Price / MRP (REQUIRED)
    price_col = mapping.get("price")
    price_val = None
    if price_col and price_col in row and not pd.isna(row[price_col]):
        try:
            # Strip currency symbols if present (e.g. "Rs 150", "₹150.00")
            cleaned_price = re.sub(r'[^0-9.]', '', str(row[price_col]))
            price_val = float(cleaned_price)
        except Exception:
            pass

    if price_val is None or price_val <= 0:
        return None, [], f"Row {row_index}: Invalid or missing price for product '{product_name}'."

    # 3. Purchase Price (OPTIONAL, default to 80% of selling price)
    purchase_col = mapping.get("purchase_price")
    purchase_price = 0.0
    if purchase_col and purchase_col in row and not pd.isna(row[purchase_col]):
        try:
            purchase_price = float(re.sub(r'[^0-9.]', '', str(row[purchase_col])))
        except Exception:
            purchase_price = round(price_val * 0.8, 2)
            warnings.append(f"Invalid purchase price for '{product_name}'; calculated as 80% of selling price (₹{purchase_price}).")
    else:
        purchase_price = round(price_val * 0.8, 2)
        warnings.append(f"Missing purchase price for '{product_name}'; calculated as ₹{purchase_price}.")

    # 4. HSN Code (OPTIONAL, default "3004")
    hsn_col = mapping.get("hsn_code")
    hsn_code = "3004"
    if hsn_col and hsn_col in row and not pd.isna(row[hsn_col]):
        raw_hsn = re.sub(r'[^0-9]', '', str(row[hsn_col]))
        if raw_hsn:
            hsn_code = raw_hsn
    else:
        warnings.append(f"Missing HSN code for '{product_name}'; defaulted to '3004'.")

    # 5. GST Rate (OPTIONAL, default 12.0)
    gst_col = mapping.get("gst_rate")
    gst_rate = 12.0
    if gst_col and gst_col in row and not pd.isna(row[gst_col]):
        try:
            raw_gst = float(re.sub(r'[^0-9.]', '', str(row[gst_col])))
            if 0 <= raw_gst <= 28:
                gst_rate = raw_gst
        except Exception:
            warnings.append(f"Invalid GST rate for '{product_name}'; defaulted to 12.0%.")

    # 6. Stock Quantity (OPTIONAL, default 0)
    stock_col = mapping.get("stock_quantity")
    stock_qty = 0
    if stock_col and stock_col in row and not pd.isna(row[stock_col]):
        try:
            stock_qty = int(float(str(row[stock_col]).strip()))
            if stock_qty < 0:
                stock_qty = 0
        except Exception:
            warnings.append(f"Invalid stock quantity for '{product_name}'; set to 0.")

    # 7. Expiry Date (OPTIONAL, default 1 year ahead)
    exp_col = mapping.get("expiry_date")
    exp_val = row.get(exp_col) if exp_col else None
    expiry_date_obj, date_warn = parse_date_flexible(exp_val)
    if date_warn:
        warnings.append(f"For '{product_name}': {date_warn}")

    # 8. Batch Number (OPTIONAL)
    batch_col = mapping.get("batch_number")
    batch_number = None
    if batch_col and batch_col in row and not pd.isna(row[batch_col]):
        b_str = str(row[batch_col]).strip()
        if b_str and b_str.lower() != 'nan':
            batch_number = b_str

    # 9. Tablets Per Strip (OPTIONAL, default 10)
    tab_col = mapping.get("tablets_per_strip")
    tablets_per_strip = 10
    if tab_col and tab_col in row and not pd.isna(row[tab_col]):
        try:
            t_val = int(float(str(row[tab_col]).strip()))
            if t_val > 0:
                tablets_per_strip = t_val
        except Exception:
            pass

    # 10. Category (OPTIONAL, default "General")
    cat_col = mapping.get("category")
    category = "General"
    if cat_col and cat_col in row and not pd.isna(row[cat_col]):
        c_str = str(row[cat_col]).strip()
        if c_str and c_str.lower() != 'nan':
            category = c_str

    cleaned_data = {
        "product_name": product_name,
        "unit_price": price_val,
        "price": price_val,
        "purchase_price": purchase_price,
        "hsn_code": hsn_code,
        "gst_rate": gst_rate,
        "gst_percentage": gst_rate,
        "quantity": stock_qty,
        "expiry_date": expiry_date_obj,
        "batch_number": batch_number,
        "tablets_per_strip": tablets_per_strip,
        "category": category,
        "days_remaining": (expiry_date_obj - date.today()).days if expiry_date_obj else 365,
        "status": "Safe" if (expiry_date_obj and (expiry_date_obj - date.today()).days > 30) else "Expiring Soon"
    }

    return cleaned_data, warnings, None

def is_valid_preview_id(preview_id: str) -> bool:
    """Validate that preview_id is a valid UUID string to prevent path traversal."""
    try:
        uuid.UUID(str(preview_id))
        return True
    except (ValueError, TypeError, AttributeError):
        return False

def save_temp_dataframe(df: pd.DataFrame) -> str:
    """Saves dataframe to temporary cache file and returns preview_id."""
    preview_id = str(uuid.uuid4())
    cache_path = os.path.join(TEMP_CACHE_DIR, f"{preview_id}.json")
    df.to_json(cache_path, orient="records", date_format="iso")
    return preview_id

def load_temp_dataframe(preview_id: str) -> Optional[pd.DataFrame]:
    """Loads dataframe from temporary cache file with traversal protection."""
    if not is_valid_preview_id(preview_id):
        return None
    cache_path = os.path.join(TEMP_CACHE_DIR, f"{preview_id}.json")
    if os.path.exists(cache_path):
        return pd.read_json(cache_path)
    return None

def cleanup_temp_cache(preview_id: str):
    """Deletes temporary cache file after import completion with traversal protection."""
    if not is_valid_preview_id(preview_id):
        return
    cache_path = os.path.join(TEMP_CACHE_DIR, f"{preview_id}.json")
    if os.path.exists(cache_path):
        try:
            os.remove(cache_path)
        except Exception:
            pass
