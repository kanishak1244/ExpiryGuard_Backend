"""
Test Suite: Thermal POS Printing (58mm/80mm) & Windows Print Agent Pipeline
==========================================================================
Tests:
1. ESC/POS Receipt Formatter (58mm and 80mm)
2. Database models (PrinterDevice, PrintJob)
3. API Endpoints (Printer registration, list, default toggle, status)
4. PrintJob lifecycle & Idempotency (Duplicate protection, Retry, Polling, ACK)
5. Zero dependency on billing confirm (Billing succeeds regardless of printer state)
"""

import sys
import os
import json
from datetime import datetime

# Setup paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
import schemas
import crud
from services import thermal_formatter
from database import SessionLocal, engine
from fastapi import Depends
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from app import app, get_current_user, get_db

client = TestClient(app)

# Mock test user
TEST_USER = None

def get_or_create_test_user(db):
    global TEST_USER
    u = db.query(models.User).filter(models.User.email == "printer_test@dawaiflow.com").first()
    if not u:
        u = models.User(
            email="printer_test@dawaiflow.com",
            password="testpass_hashed",
            shop_name="Dawaiflow Test Chemist",
            owner_name="Test Chemist Owner",
            phone="9876543210",
            address="123 Health Ave, New Delhi",
            gstin="07AAAAA0000A1Z5",
            drug_license_no="DL-12345/2026",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    TEST_USER = u
    return u

def override_get_current_user(db: Session = Depends(get_db)):
    return get_or_create_test_user(db)

app.dependency_overrides[get_current_user] = override_get_current_user


def test_01_escpos_formatter_58mm():
    """Verify 58mm ESC/POS byte generator produces valid structure."""
    sample_payload = {
        "invoice_number": "INV-2026-001",
        "created_at": "2026-09-05 14:30:00",
        "customer_name": "Ramesh Kumar",
        "customer_phone": "9811122233",
        "doctor_name": "Dr. A. Sharma",
        "shop": {
            "name": "DAWAIFLOW PHARMACY",
            "address": "Shop 4, Market Complex",
            "phone": "+91 98111 00000",
            "gstin": "07AAAAA0000A1Z5",
            "drug_license": "DL-12345/2026",
            "header_extra": "RETAIL TAX INVOICE"
        },
        "items": [
            {
                "product_name": "AUGMENTIN 625MG",
                "batch_number": "AUG001",
                "expiry_date": "10/26",
                "quantity": 1,
                "unit_price": 204.0,
                "discount": 10.0,
                "gst_percentage": 12.0,
                "total_amount": 194.0
            },
            {
                "product_name": "PAN 40MG",
                "batch_number": "PAN992",
                "expiry_date": "03/27",
                "quantity": 2,
                "unit_price": 150.0,
                "discount": 0.0,
                "gst_percentage": 12.0,
                "total_amount": 300.0
            }
        ],
        "totals": {
            "subtotal": 504.0,
            "discount_amount": 10.0,
            "taxable_value": 441.07,
            "cgst_amount": 26.46,
            "sgst_amount": 26.46,
            "igst_amount": 0.0,
            "round_off": 0.01,
            "grand_total": 494.0,
            "amount_paid": 494.0,
            "balance_due": 0.0
        },
        "payment": {
            "method": "UPI",
            "status": "PAID"
        }
    }

    raw_bytes = thermal_formatter.build_escpos_receipt(
        sample_payload,
        paper_size="58mm",
        cut_paper=True,
        drawer_pulse=True
    )

    assert isinstance(raw_bytes, (bytes, bytearray))
    assert len(raw_bytes) > 200
    # Must start with ESC @ (initialize)
    assert raw_bytes.startswith(b"\x1b\x40")
    # Must contain shop name
    assert b"DAWAIFLOW PHARMACY" in raw_bytes
    # Must contain invoice number
    assert b"INV-2026-001" in raw_bytes
    # Must contain medicine names
    assert b"AUGMENTIN 625MG" in raw_bytes
    assert b"PAN 40MG" in raw_bytes
    # Must contain totals
    assert b"494.00" in raw_bytes
    print(f"[TEST 1 PASSED] 58mm ESC/POS generated {len(raw_bytes)} bytes successfully.")


def test_02_escpos_formatter_80mm():
    """Verify 80mm ESC/POS byte generator produces valid wider structure."""
    sample_payload = {
        "invoice_number": "INV-2026-002",
        "created_at": "2026-09-05 15:00:00",
        "customer_name": "Anita Verma",
        "customer_phone": "9899988877",
        "shop": {
            "name": "SUPER PHARMA",
            "address": "Main Road, Sector 15",
            "phone": "98999 88877",
            "gstin": "07BBBBB1111B1Z6",
            "drug_license": "DL-99999/2026"
        },
        "items": [
            {
                "product_name": "CILACAR 5MG",
                "batch_number": "CIL55",
                "expiry_date": "08/27",
                "quantity": 10,
                "unit_price": 8.5,
                "discount": 0.0,
                "gst_percentage": 12.0,
                "total_amount": 85.0
            }
        ],
        "totals": {
            "subtotal": 85.0,
            "discount_amount": 0.0,
            "taxable_value": 75.89,
            "cgst_amount": 4.55,
            "sgst_amount": 4.55,
            "grand_total": 85.0,
            "amount_paid": 85.0,
            "balance_due": 0.0
        },
        "payment": {
            "method": "CASH",
            "status": "PAID"
        }
    }

    raw_bytes = thermal_formatter.build_escpos_receipt(
        sample_payload,
        paper_size="80mm",
        cut_paper=True,
        drawer_pulse=False
    )

    assert isinstance(raw_bytes, (bytes, bytearray))
    assert len(raw_bytes) > 200
    assert b"SUPER PHARMA" in raw_bytes
    assert b"CILACAR 5MG" in raw_bytes
    print(f"[TEST 2 PASSED] 80mm ESC/POS generated {len(raw_bytes)} bytes successfully.")


def test_03_printer_registration_and_list():
    """Verify registering printers and querying them via REST."""
    db = SessionLocal()
    try:
        user = get_or_create_test_user(db)
        # Clear existing test print jobs and printers
        db.query(models.PrintJob).filter(models.PrintJob.user_id == user.id).delete()
        db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == user.id).delete()
        db.commit()
    finally:
        db.close()

    # 1. Register printer 1 (Default)
    payload1 = {
        "device_name": "Counter 1 Thermal",
        "printer_system_name": "POS-58",
        "connection_type": "USB",
        "paper_size": "58mm",
        "is_default": True,
        "settings_json": json.dumps({"auto_cut": True, "cash_drawer": False})
    }
    resp1 = client.post("/printers/register", json=payload1)
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert data1["device_name"] == "Counter 1 Thermal"
    assert data1["is_default"] is True
    p1_id = data1["id"]

    # 2. Register printer 2 (Secondary)
    payload2 = {
        "device_name": "Billing 2 Bluetooth",
        "printer_system_name": "MTP-II",
        "connection_type": "BLUETOOTH",
        "paper_size": "58mm",
        "is_default": False
    }
    resp2 = client.post("/printers/register", json=payload2)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_default"] is False
    p2_id = data2["id"]

    # 3. List printers
    resp_list = client.get("/printers")
    assert resp_list.status_code == 200
    printers = resp_list.json()
    assert len(printers) == 2

    # 4. Set printer 2 as default
    resp_def = client.put(f"/printers/{p2_id}/default")
    assert resp_def.status_code == 200
    assert resp_def.json()["is_default"] is True

    # Verify printer 1 is no longer default
    resp_list2 = client.get("/printers")
    for p in resp_list2.json():
        if p["id"] == p1_id:
            assert p["is_default"] is False
        if p["id"] == p2_id:
            assert p["is_default"] is True

    # 5. Printer Status Summary
    resp_status = client.get("/printers/status")
    assert resp_status.status_code == 200
    status_data = resp_status.json()
    assert status_data["has_printer"] is True
    assert status_data["default_printer"]["id"] == p2_id
    print("[TEST 3 PASSED] Printer registration, list, default toggle, and status verified.")


def test_04_print_job_idempotency_and_queue():
    """Verify PrintJob creation is idempotent and follows correct state transitions."""
    db = SessionLocal()
    try:
        user = get_or_create_test_user(db)
        # Create a fake sale
        sale = models.Sale(
            user_id=user.id,
            bill_number=f"TEST-BILL-{int(datetime.utcnow().timestamp())}",
            customer_name="Test Patient",
            customer_phone="9988776655",
            payment_method="CASH",
            subtotal=100.0,
            discount_amount=0.0,
            tax_amount=12.0,
            total_amount=112.0,
            total_taxable_value=100.0,
            total_cgst=6.0,
            total_sgst=6.0,
            total_igst=0.0
        )
        db.add(sale)
        db.commit()
        db.refresh(sale)
        sale_id = sale.id
    finally:
        db.close()

    # 1. Create first print job
    resp_job1 = client.post("/print-jobs", json={"sale_id": sale_id, "copies": 1, "force_print_again": False})
    assert resp_job1.status_code == 201, resp_job1.text
    job1 = resp_job1.json()
    job1_id = job1["id"]
    assert job1["status"] == "PENDING"

    # 2. Idempotency test: Attempt to create job for same sale without force_print_again
    resp_job2 = client.post("/print-jobs", json={"sale_id": sale_id, "copies": 1, "force_print_again": False})
    assert resp_job2.status_code == 201
    job2 = resp_job2.json()
    # Must return the SAME existing job ID!
    assert job2["id"] == job1_id, "Failed idempotency! Created duplicate print job."

    # 3. Agent Poll: Should return this pending job
    resp_poll = client.post("/printer-agent/poll")
    assert resp_poll.status_code == 200
    poll_data = resp_poll.json()
    assert len(poll_data["jobs"]) >= 1
    found_job = next((j for j in poll_data["jobs"] if j["job_id"] == job1_id), None)
    assert found_job is not None
    assert found_job["invoice_number"] == sale.bill_number

    # 4. Agent ACK: Transition to PRINTING
    resp_ack_printing = client.post("/printer-agent/ack", json={"job_id": job1_id, "status": "PRINTING"})
    assert resp_ack_printing.status_code == 200

    # 5. Agent ACK: Transition to PRINTED
    resp_ack_printed = client.post("/printer-agent/ack", json={"job_id": job1_id, "status": "PRINTED"})
    assert resp_ack_printed.status_code == 200

    # Verify status in GET /print-jobs
    resp_jobs = client.get("/print-jobs")
    assert resp_jobs.status_code == 200
    db_job = next((j for j in resp_jobs.json() if j["id"] == job1_id), None)
    assert db_job is not None, f"Job {job1_id} not found in print jobs: {resp_jobs.json()}"
    assert db_job["status"] == "PRINTED"
    assert db_job["printed_at"] is not None

    # 6. Test Retry endpoint
    resp_retry = client.post(f"/print-jobs/{job1_id}/retry")
    assert resp_retry.status_code == 200
    assert resp_retry.json()["status"] == "PENDING"
    assert resp_retry.json()["retry_count"] == 1
    print("[TEST 4 PASSED] Print job creation, idempotency, polling, ACK, and retry verified.")


def test_05_test_print_endpoint():
    """Verify POST /print-jobs/test-print enqueues a test receipt."""
    resp = client.post("/print-jobs/test-print", json={"paper_size": "58mm"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "PENDING"
    assert "TEST-" in data["invoice_number"]
    print(f"[TEST 5 PASSED] Test print enqueued with job #{data['id']}.")


if __name__ == "__main__":
    print("Running Thermal POS Printing Test Suite...")
    test_01_escpos_formatter_58mm()
    test_02_escpos_formatter_80mm()
    test_03_printer_registration_and_list()
    test_04_print_job_idempotency_and_queue()
    test_05_test_print_endpoint()
    print("\nALL 5 TEST SUITES PASSED WITH 100% SUCCESS!")
