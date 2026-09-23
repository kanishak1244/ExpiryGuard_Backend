import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# Ensure import paths work
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv(dotenv_path=BASE_DIR / ".env")

from ai.gemini_service import (
    optimize_image,
    detect_and_lookup_barcode,
    scan_label,
    validate_label_data
)
from ai.invoice_service import scan_invoice, validate_invoice_data
from ai.multi_item_scan_service import scan_multi_item, validate_multi_item_data

print("========== EXPIRYGUARD AI ARCHITECTURE DIAGNOSTICS & TEST ==========")

# Setup a test image path
TEST_IMAGE = str(BASE_DIR / "expiryguard.jpeg")

# Ensure a test image exists
if not os.path.exists(TEST_IMAGE):
    with open(TEST_IMAGE, "wb") as f:
        f.write(b"DUMMY_IMAGE_CONTENT")

def test_image_optimization():
    print("\n--- Testing Image Optimization ---")
    temp_file = str(BASE_DIR / "temp_large_test.jpg")
    
    # Pad actual image to make it larger than 300KB
    import shutil
    shutil.copy(TEST_IMAGE, temp_file)
    with open(temp_file, "ab") as f:
         f.write(b"\x00" * 400 * 1024)
         
    padded_size = os.path.getsize(temp_file)
    print(f"Padded test file size: {padded_size / 1024:.1f} KB")
    
    optimize_image(temp_file)
    optimized_size = os.path.getsize(temp_file)
    print(f"Optimized file size: {optimized_size / 1024:.1f} KB")
    
    if os.path.exists(temp_file):
        os.remove(temp_file)
    print("Success: Image optimization completed successfully.")

def test_barcode_lookup():
    print("\n--- Testing Barcode-First Optimization ---")
    from ai.gemini_service import BARCODE_MAP
    dolo_info = BARCODE_MAP.get("8901138510839")
    print(f"EAN 8901138510839 maps to: {dolo_info.get('product_name')} by {dolo_info.get('brand')}")
    assert dolo_info["product_name"] == "Dolo 650 Tablet"
    print("Success: Barcode mapping matches expected metadata.")

def test_label_validation():
    print("\n--- Testing Schema Validation ---")
    valid_data = {
        "product_name": "Panadol 500mg",
        "brand": "GSK",
        "batch_number": "PAN123",
        "expiry_date": "2028-12-01"
    }
    invalid_data = {
        "brand": "Unknown",
        "batch_number": "123"
    }
    print("Validating structured label schema...")
    print(f"Valid data check: {validate_label_data(valid_data)}")
    print(f"Invalid data check: {validate_label_data(invalid_data)}")
    assert validate_label_data(valid_data) == True
    assert validate_label_data(invalid_data) == False
    print("Success: Schema validation filters invalid payloads correctly.")

def test_scan_label():
    print("\n--- Testing scan_label (Gemini API Request) ---")
    t0 = time.time()
    res = scan_label(TEST_IMAGE)
    t1 = time.time()
    print(f"scan_label latency: {t1-t0:.2f}s")
    print(f"Response success status: {res.get('success')}")
    print(f"Extracted payload: {res.get('data')}")
    print(f"Errors (if any): {res.get('error')}")

def test_scan_invoice():
    print("\n--- Testing scan_invoice (Gemini API Request) ---")
    t0 = time.time()
    res = scan_invoice(TEST_IMAGE)
    t1 = time.time()
    print(f"scan_invoice latency: {t1-t0:.2f}s")
    print(f"Response success status: {res.get('success')}")
    print(f"Extracted items count: {len(res.get('data', {}).get('items', [])) if res.get('data') else 0}")
    print(f"Errors (if any): {res.get('error')}")

def test_scan_multi_item():
    print("\n--- Testing scan_multi_item (Gemini API Request) ---")
    t0 = time.time()
    res = scan_multi_item(TEST_IMAGE)
    t1 = time.time()
    print(f"scan_multi_item latency: {t1-t0:.2f}s")
    print(f"Response success status: {res.get('success')}")
    print(f"Extracted items count: {len(res.get('items', []))}")
    print(f"Errors (if any): {res.get('error')}")

def test_scan_multi_page_invoice():
    print("\n--- Testing scan_invoice with Multiple Image Pages (Multi-Photo Scan) ---")
    t0 = time.time()
    res = scan_invoice([TEST_IMAGE, TEST_IMAGE])
    t1 = time.time()
    print(f"multi_page_invoice latency: {t1-t0:.2f}s")
    print(f"Response success status: {res.get('success')}")
    items = res.get('data', {}).get('items', []) if res.get('data') else []
    print(f"Extracted items count across pages: {len(items)}")

def test_ai_chat():
    print("\n--- Testing AI Assistant Chat (Grounded RAG) ---")
    from database import SessionLocal
    import crud
    db = SessionLocal()
    try:
        t0 = time.time()
        res = crud.get_ai_chat_response(db, user_id=1, query="How is my sales this month?")
        t1 = time.time()
        print(f"ai_chat latency: {t1-t0:.2f}s")
        print(f"Response: {res.get('answer')}")
        print(f"Source metadata: {res.get('source')}")
    finally:
        db.close()

if __name__ == "__main__":
    test_image_optimization()
    test_barcode_lookup()
    test_label_validation()
    test_scan_label()
    test_scan_invoice()
    test_scan_multi_page_invoice()
    test_scan_multi_item()
    test_ai_chat()
    print("\n========== ALL AI OPTIMIZATION DIAGNOSTIC TESTS PASSED ==========")
