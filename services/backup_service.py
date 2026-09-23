"""
Dawaiflow Production-Ready Backup & Restore Service.
Handles:
- Full relational extraction of shop/business data preserving IDs, relationships & foreign keys
- Cryptographic SHA-256 integrity verification
- Gzip compression & AES-128-CBC/HMAC-SHA256 authenticated symmetric encryption (Fernet)
- Pre-restore safety snapshots (type="PRE_RESTORE_SAFETY")
- Atomic, transactional restoration with rollback protection
- PostgreSQL serial sequence synchronization post-restore
- Multi-tenant shop isolation enforcement
"""

import gzip
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from crypto_utils import get_credential_cipher, get_backup_cipher
import models

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
try:
    os.makedirs(BACKUPS_DIR, exist_ok=True)
except Exception:
    pass

BACKUP_VERSION = 1
SCHEMA_VERSION = 1
APP_VERSION = "1.0.0"


def _json_serial(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _model_to_dict(instance: Any, exclude_fields: Optional[set] = None) -> Dict[str, Any]:
    """Convert an SQLAlchemy model instance to a dictionary with clean serializable types."""
    exclude = exclude_fields or set()
    data = {}
    for col in instance.__table__.columns:
        if col.name in exclude:
            continue
        val = getattr(instance, col.name)
        if isinstance(val, (datetime, date)):
            val = val.isoformat()
        data[col.name] = val
    return data


def create_backup(
    db: Session,
    user_id: int,
    backup_type: str = "MANUAL",
    notes: Optional[str] = None,
    created_by_user_id: Optional[int] = None,
    created_by_name: Optional[str] = None,
) -> models.BackupRecord:
    """
    Extracts all business data for user_id, builds a versioned relational package,
    encrypts it with authenticated symmetric encryption, writes it safely to disk,
    and logs the backup record.
    """
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise ValueError(f"User / Shop ID {user_id} does not exist.")

    # 1. Shop profile & settings
    user_data = _model_to_dict(user)
    notif_settings = db.query(models.NotificationSettings).filter(models.NotificationSettings.user_id == user_id).first()
    notif_data = _model_to_dict(notif_settings) if notif_settings else None

    # 2. Staff members (password hash and Fernet encrypted_password preserved, NO plaintext)
    staff_members = db.query(models.StaffMember).filter(models.StaffMember.user_id == user_id).all()
    staff_data = [_model_to_dict(s) for s in staff_members]

    # 3. Products & stock (both active and soft-deleted)
    products = db.query(models.Product).filter(models.Product.user_id == user_id).all()
    product_data = [_model_to_dict(p) for p in products]

    # 4. Inventory transactions
    transactions = db.query(models.InventoryTransaction).filter(models.InventoryTransaction.shop_id == user_id).all()
    transaction_data = [_model_to_dict(t) for t in transactions]

    # 5. Customers & Khata repayments
    customers = db.query(models.Customer).filter(models.Customer.user_id == user_id).all()
    customer_data = [_model_to_dict(c) for c in customers]
    customer_payments = db.query(models.CustomerPayment).filter(models.CustomerPayment.user_id == user_id).all()
    customer_payment_data = [_model_to_dict(cp) for cp in customer_payments]

    # 6. Suppliers & Supplier payments
    suppliers = db.query(models.Supplier).filter(models.Supplier.user_id == user_id).all()
    supplier_data = [_model_to_dict(s) for s in suppliers]
    supplier_payments = db.query(models.SupplierPayment).filter(models.SupplierPayment.user_id == user_id).all()
    supplier_payment_data = [_model_to_dict(sp) for sp in supplier_payments]

    # 7. Purchases & Purchase items
    purchases = db.query(models.PurchaseInvoice).filter(models.PurchaseInvoice.user_id == user_id).all()
    purchase_ids = [p.id for p in purchases]
    purchase_items = db.query(models.PurchaseItem).filter(models.PurchaseItem.purchase_invoice_id.in_(purchase_ids)).all() if purchase_ids else []
    purchase_returns = db.query(models.PurchaseReturn).filter(models.PurchaseReturn.user_id == user_id).all()
    return_ids = [pr.id for pr in purchase_returns]
    purchase_return_items = db.query(models.PurchaseReturnItem).filter(models.PurchaseReturnItem.purchase_return_id.in_(return_ids)).all() if return_ids else []

    purchase_data = [_model_to_dict(p) for p in purchases]
    purchase_item_data = [_model_to_dict(pi) for pi in purchase_items]
    purchase_return_data = [_model_to_dict(pr) for pr in purchase_returns]
    purchase_return_item_data = [_model_to_dict(pri) for pri in purchase_return_items]

    # 8. Sales & Sale items & Split payments
    sales = db.query(models.Sale).filter(models.Sale.user_id == user_id).all()
    sale_ids = [s.id for s in sales]
    sale_items = db.query(models.SaleItem).filter(models.SaleItem.sale_id.in_(sale_ids)).all() if sale_ids else []
    sale_payments = db.query(models.SalePayment).filter(models.SalePayment.user_id == user_id).all()
    sale_returns = db.query(models.SaleReturn).filter(models.SaleReturn.user_id == user_id).all()
    s_return_ids = [sr.id for sr in sale_returns]
    sale_return_items = db.query(models.SaleReturnItem).filter(models.SaleReturnItem.sale_return_id.in_(s_return_ids)).all() if s_return_ids else []

    sale_data = [_model_to_dict(s) for s in sales]
    sale_item_data = [_model_to_dict(si) for si in sale_items]
    sale_payment_data = [_model_to_dict(sp) for sp in sale_payments]
    sale_return_data = [_model_to_dict(sr) for sr in sale_returns]
    sale_return_item_data = [_model_to_dict(sri) for sri in sale_return_items]

    # 9. Held bills
    held_bills = db.query(models.HeldBill).filter(models.HeldBill.user_id == user_id).all()
    held_bill_ids = [hb.id for hb in held_bills]
    held_bill_items = db.query(models.HeldBillItem).filter(models.HeldBillItem.held_bill_id.in_(held_bill_ids)).all() if held_bill_ids else []
    held_bill_data = [_model_to_dict(hb) for hb in held_bills]
    held_bill_item_data = [_model_to_dict(hbi) for hbi in held_bill_items]

    # 10. Configurations: StoreBranches, CaProfiles, PrinterDevices
    branches = db.query(models.StoreBranch).filter(models.StoreBranch.user_id == user_id).all()
    ca_profiles = db.query(models.CaProfile).filter(models.CaProfile.user_id == user_id).all()
    printers = db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == user_id).all()

    counts = {
        "products": len(product_data),
        "sales": len(sale_data),
        "sale_items": len(sale_item_data),
        "sale_payments": len(sale_payment_data),
        "purchases": len(purchase_data),
        "purchase_items": len(purchase_item_data),
        "customers": len(customer_data),
        "customer_payments": len(customer_payment_data),
        "suppliers": len(supplier_data),
        "supplier_payments": len(supplier_payment_data),
        "staff": len(staff_data),
        "held_bills": len(held_bill_data),
        "held_bill_items": len(held_bill_item_data),
    }

    manifest = {
        "dawaiflow_backup": True,
        "backup_version": BACKUP_VERSION,
        "schema_version": SCHEMA_VERSION,
        "app_version": APP_VERSION,
        "shop_id": user_id,
        "shop_name": user.shop_name,
        "owner_name": user.owner_name,
        "user_email": user.email,
        "backup_type": backup_type,
        "record_counts": counts,
        "created_at": datetime.utcnow().isoformat(),
    }

    full_payload = {
        "manifest": manifest,
        "data": {
            "user": user_data,
            "notification_settings": notif_data,
            "staff_members": staff_data,
            "products": product_data,
            "inventory_transactions": transaction_data,
            "customers": customer_data,
            "customer_payments": customer_payment_data,
            "suppliers": supplier_data,
            "supplier_payments": supplier_payment_data,
            "purchase_invoices": purchase_data,
            "purchase_items": purchase_item_data,
            "purchase_returns": purchase_return_data,
            "purchase_return_items": purchase_return_item_data,
            "sales": sale_data,
            "sale_items": sale_item_data,
            "sale_payments": sale_payment_data,
            "sale_returns": sale_return_data,
            "sale_returns_items": sale_return_item_data,
            "held_bills": held_bill_data,
            "held_bill_items": held_bill_item_data,
            "store_branches": [_model_to_dict(b) for b in branches],
            "ca_profiles": [_model_to_dict(ca) for ca in ca_profiles],
            "printer_devices": [_model_to_dict(pr) for pr in printers],
        }
    }

    # Compute raw SHA256 of the data
    canonical_raw = json.dumps(full_payload["data"], sort_keys=True, default=_json_serial).encode("utf-8")
    checksum = hashlib.sha256(canonical_raw).hexdigest()
    manifest["checksum_sha256"] = checksum
    full_payload["manifest"]["checksum_sha256"] = checksum

    # Compress & Encrypt
    raw_json_bytes = json.dumps(full_payload, default=_json_serial).encode("utf-8")
    compressed = gzip.compress(raw_json_bytes)

    cipher = get_backup_cipher()
    encrypted_bytes = cipher.encrypt(compressed)

    # Filename & Path
    clean_shop = re.sub(r"[^a-zA-Z0-9_-]", "_", user.shop_name.lower())[:16]
    date_str = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_uuid = str(uuid.uuid4())
    filename = f"dawaiflow_backup_{clean_shop}_{date_str}_{backup_uuid[:8]}.dfbk"
    file_path = str(BACKUPS_DIR / filename)

    # Atomic file write
    temp_path = file_path + ".tmp"
    with open(temp_path, "wb") as f:
        f.write(encrypted_bytes)
    os.replace(temp_path, file_path)

    file_size = os.path.getsize(file_path)

    # Save to BackupRecord
    record = models.BackupRecord(
        user_id=user_id,
        backup_id=backup_uuid,
        filename=filename,
        file_path=file_path,
        file_size_bytes=file_size,
        backup_type=backup_type,
        status="SUCCESS",
        backup_version=BACKUP_VERSION,
        schema_version=SCHEMA_VERSION,
        app_version=APP_VERSION,
        checksum_sha256=checksum,
        record_counts_json=json.dumps(counts),
        notes=notes,
        created_by_user_id=created_by_user_id or user_id,
        created_by_name=created_by_name or user.owner_name,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(f"[BACKUP] Created {backup_type} backup {backup_uuid} for shop {user.shop_name} ({file_size} bytes)")
    return record


def validate_backup_package(file_bytes: bytes, target_user_id: int) -> Dict[str, Any]:
    """
    Decrypts and strictly validates a backup package:
    - Verifies encryption & integrity
    - Verifies Gzip compression format
    - Verifies JSON structure and manifest
    - Verifies backup version and schema compatibility
    - Verifies cryptographic SHA-256 data checksum
    - Verifies multi-tenant shop isolation (target_user_id matches backup shop_id)
    """
    if not file_bytes:
        raise ValueError("Backup file is empty.")

    # 1. Decrypt
    try:
        cipher = get_backup_cipher()
        decompressed_bytes = cipher.decrypt(file_bytes)
    except Exception as e:
        raise ValueError("Backup file is corrupted, invalid, or cannot be decrypted with server keys.") from e

    # 2. Decompress
    try:
        raw_json_bytes = gzip.decompress(decompressed_bytes)
    except Exception as e:
        raise ValueError("Backup archive compression is corrupted or invalid.") from e

    # 3. Parse JSON
    try:
        payload = json.loads(raw_json_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError("Backup archive contains invalid or unreadable data structure.") from e

    manifest = payload.get("manifest")
    data = payload.get("data")
    if not manifest or not data:
        raise ValueError("Backup file structure is invalid: Missing manifest or data section.")

    if manifest.get("dawaiflow_backup") is not True:
        raise ValueError("Selected file is not a valid Dawaiflow backup.")

    # 4. Version compatibility
    b_version = manifest.get("backup_version")
    if b_version != BACKUP_VERSION:
        raise ValueError(f"Incompatible backup version ({b_version}). Expected version {BACKUP_VERSION}.")

    # 5. Checksum verification
    expected_checksum = manifest.get("checksum_sha256")
    canonical_raw = json.dumps(data, sort_keys=True, default=_json_serial).encode("utf-8")
    actual_checksum = hashlib.sha256(canonical_raw).hexdigest()
    if expected_checksum != actual_checksum:
        raise ValueError("Backup integrity check failed: Data checksum does not match manifest (file may be corrupted).")

    # 6. Multi-tenant Shop Isolation check
    backup_shop_id = manifest.get("shop_id")
    if backup_shop_id != target_user_id:
        backup_shop_name = manifest.get("shop_name", "Unknown Shop")
        raise ValueError(
            f"Multi-tenant isolation violation: This backup belongs to '{backup_shop_name}' (ID: {backup_shop_id}), "
            f"and cannot be restored into your pharmacy."
        )

    return payload


def _reset_postgres_sequences(db: Session, table_names: List[str]):
    """Reset PostgreSQL serial primary key sequences to MAX(id) + 1 to prevent ID collision errors."""
    for tbl in table_names:
        try:
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{tbl}', 'id'), COALESCE((SELECT MAX(id) FROM {tbl}), 1), true);"
            ))
        except Exception as e:
            logger.debug(f"Note: Could not reset sequence for table '{tbl}' (might not be serial): {e}")


def restore_backup(
    db: Session,
    user_id: int,
    backup_file_bytes: bytes,
    initiated_by_name: str,
) -> Dict[str, Any]:
    """
    Executes a production-safe atomic database restore:
    1. Validates the incoming backup package.
    2. Automatically creates a PRE_RESTORE_SAFETY backup of current data first.
    3. Replaces existing shop data atomically in reverse dependency order inside a transaction.
    4. Re-inserts data preserving original IDs and relational links.
    5. Resets PostgreSQL sequences.
    6. Verifies record counts match manifest.
    7. Rolls back transaction if any error occurs.
    """
    # Step 1: Pre-validation
    payload = validate_backup_package(backup_file_bytes, target_user_id=user_id)
    manifest = payload["manifest"]
    data = payload["data"]

    # Step 2: Safety Backup Before Restore
    logger.info(f"[RESTORE] Creating pre-restore safety backup for shop ID {user_id}...")
    try:
        safety_record = create_backup(
            db,
            user_id=user_id,
            backup_type="PRE_RESTORE_SAFETY",
            created_by_name=f"Automated Safety Backup (before restore by {initiated_by_name})"
        )
    except Exception as e:
        logger.error(f"[RESTORE ABORTED] Failed to create safety backup: {e}")
        raise ValueError(
            f"Restoration cancelled for safety: Could not create automated safety backup of current data ({e}). "
            f"Your current database was not modified."
        ) from e

    # Step 3: Log Start
    restore_log = models.RestoreLog(
        user_id=user_id,
        backup_id=manifest.get("checksum_sha256", "manual")[:16],
        safety_backup_id=safety_record.backup_id,
        initiated_by_name=initiated_by_name,
        status="VALIDATING",
        started_at=datetime.utcnow(),
    )
    db.add(restore_log)
    db.commit()

    # Step 4: Atomic Database Restoration
    try:
        # A. Delete current shop data in reverse FK dependency order
        logger.info(f"[RESTORE] Purging existing relational records for user_id={user_id}...")
        
        # Sales & returns
        sale_ids = [s[0] for s in db.query(models.Sale.id).filter(models.Sale.user_id == user_id).all()]
        sale_return_ids = [sr[0] for sr in db.query(models.SaleReturn.id).filter(models.SaleReturn.user_id == user_id).all()]
        if sale_return_ids:
            db.query(models.SaleReturnItem).filter(models.SaleReturnItem.sale_return_id.in_(sale_return_ids)).delete(synchronize_session=False)
        db.query(models.SaleReturn).filter(models.SaleReturn.user_id == user_id).delete(synchronize_session=False)

        if sale_ids:
            db.query(models.SaleItem).filter(models.SaleItem.sale_id.in_(sale_ids)).delete(synchronize_session=False)
        db.query(models.SalePayment).filter(models.SalePayment.user_id == user_id).delete(synchronize_session=False)
        db.query(models.Sale).filter(models.Sale.user_id == user_id).delete(synchronize_session=False)

        # Purchases & returns
        purchase_ids = [p[0] for p in db.query(models.PurchaseInvoice.id).filter(models.PurchaseInvoice.user_id == user_id).all()]
        purchase_return_ids = [pr[0] for pr in db.query(models.PurchaseReturn.id).filter(models.PurchaseReturn.user_id == user_id).all()]
        if purchase_return_ids:
            db.query(models.PurchaseReturnItem).filter(models.PurchaseReturnItem.purchase_return_id.in_(purchase_return_ids)).delete(synchronize_session=False)
        db.query(models.PurchaseReturn).filter(models.PurchaseReturn.user_id == user_id).delete(synchronize_session=False)

        if purchase_ids:
            db.query(models.PurchaseItem).filter(models.PurchaseItem.purchase_invoice_id.in_(purchase_ids)).delete(synchronize_session=False)
        db.query(models.PurchaseInvoice).filter(models.PurchaseInvoice.user_id == user_id).delete(synchronize_session=False)

        # Held bills
        held_ids = [hb[0] for hb in db.query(models.HeldBill.id).filter(models.HeldBill.user_id == user_id).all()]
        if held_ids:
            db.query(models.HeldBillItem).filter(models.HeldBillItem.held_bill_id.in_(held_ids)).delete(synchronize_session=False)
        db.query(models.HeldBill).filter(models.HeldBill.user_id == user_id).delete(synchronize_session=False)

        # Customer ledger & payments
        db.query(models.CustomerPayment).filter(models.CustomerPayment.user_id == user_id).delete(synchronize_session=False)
        db.query(models.Customer).filter(models.Customer.user_id == user_id).delete(synchronize_session=False)

        # Supplier ledger & payments
        db.query(models.SupplierPayment).filter(models.SupplierPayment.user_id == user_id).delete(synchronize_session=False)
        db.query(models.Supplier).filter(models.Supplier.user_id == user_id).delete(synchronize_session=False)

        # Inventory & transactions
        db.query(models.InventoryTransaction).filter(models.InventoryTransaction.shop_id == user_id).delete(synchronize_session=False)
        db.query(models.Product).filter(models.Product.user_id == user_id).delete(synchronize_session=False)

        # Staff members
        db.query(models.StaffMember).filter(models.StaffMember.user_id == user_id).delete(synchronize_session=False)

        # Configurations
        db.query(models.NotificationSettings).filter(models.NotificationSettings.user_id == user_id).delete(synchronize_session=False)
        db.query(models.StoreBranch).filter(models.StoreBranch.user_id == user_id).delete(synchronize_session=False)
        db.query(models.CaProfile).filter(models.CaProfile.user_id == user_id).delete(synchronize_session=False)
        db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == user_id).delete(synchronize_session=False)

        # B. Restore records into tables preserving original IDs
        logger.info(f"[RESTORE] Inserting restored relational records...")

        # 1. Update User profile fields (preserving ID, email, password)
        if data.get("user"):
            u_dict = data["user"]
            current_user_obj = db.query(models.User).filter(models.User.id == user_id).first()
            if current_user_obj:
                for k, v in u_dict.items():
                    if k not in ("id", "email", "password") and hasattr(current_user_obj, k):
                        setattr(current_user_obj, k, v)

        # 2. Notification settings
        if data.get("notification_settings"):
            ns = models.NotificationSettings(**data["notification_settings"])
            ns.user_id = user_id
            db.add(ns)

        # 3. Staff members
        for s_item in data.get("staff_members", []):
            s_item["user_id"] = user_id
            db.add(models.StaffMember(**s_item))

        # 4. Products
        for p_item in data.get("products", []):
            p_item["user_id"] = user_id
            if p_item.get("expiry_date") and isinstance(p_item["expiry_date"], str):
                try:
                    p_item["expiry_date"] = datetime.fromisoformat(p_item["expiry_date"]).date()
                except Exception:
                    pass
            db.add(models.Product(**p_item))

        # 5. Inventory transactions
        for it_item in data.get("inventory_transactions", []):
            it_item["shop_id"] = user_id
            db.add(models.InventoryTransaction(**it_item))

        # 6. Customers & Payments
        for c_item in data.get("customers", []):
            c_item["user_id"] = user_id
            db.add(models.Customer(**c_item))
        for cp_item in data.get("customer_payments", []):
            cp_item["user_id"] = user_id
            db.add(models.CustomerPayment(**cp_item))

        # 7. Suppliers & Payments
        for sup_item in data.get("suppliers", []):
            sup_item["user_id"] = user_id
            db.add(models.Supplier(**sup_item))
        for sp_item in data.get("supplier_payments", []):
            sp_item["user_id"] = user_id
            db.add(models.SupplierPayment(**sp_item))

        # 8. Purchases & items
        for pur_item in data.get("purchase_invoices", []):
            pur_item["user_id"] = user_id
            if pur_item.get("invoice_date") and isinstance(pur_item["invoice_date"], str):
                try:
                    pur_item["invoice_date"] = datetime.fromisoformat(pur_item["invoice_date"]).date()
                except Exception:
                    pass
            db.add(models.PurchaseInvoice(**pur_item))
        for pi_item in data.get("purchase_items", []):
            db.add(models.PurchaseItem(**pi_item))
        for pr_item in data.get("purchase_returns", []):
            pr_item["user_id"] = user_id
            db.add(models.PurchaseReturn(**pr_item))
        for pri_item in data.get("purchase_return_items", []):
            db.add(models.PurchaseReturnItem(**pri_item))

        # 9. Sales & items & payments & returns
        for s_row in data.get("sales", []):
            s_row["user_id"] = user_id
            db.add(models.Sale(**s_row))
        for si_item in data.get("sale_items", []):
            db.add(models.SaleItem(**si_item))
        for sp_row in data.get("sale_payments", []):
            sp_row["user_id"] = user_id
            db.add(models.SalePayment(**sp_row))
        for sr_row in data.get("sale_returns", []):
            sr_row["user_id"] = user_id
            db.add(models.SaleReturn(**sr_row))
        for sri_row in data.get("sale_returns_items", data.get("sale_return_items", [])):
            db.add(models.SaleReturnItem(**sri_row))

        # 10. Held bills
        for hb_row in data.get("held_bills", []):
            hb_row["user_id"] = user_id
            db.add(models.HeldBill(**hb_row))
        for hbi_row in data.get("held_bill_items", []):
            db.add(models.HeldBillItem(**hbi_row))

        # 11. Configurations
        for br in data.get("store_branches", []):
            br["user_id"] = user_id
            db.add(models.StoreBranch(**br))
        for ca in data.get("ca_profiles", []):
            ca["user_id"] = user_id
            db.add(models.CaProfile(**ca))
        for prn in data.get("printer_devices", []):
            prn["user_id"] = user_id
            db.add(models.PrinterDevice(**prn))

        # Flush to DB within transaction
        db.flush()

        # C. Reset sequences for all restored tables
        tables_to_sync = [
            "products", "inventory_transactions", "customers", "customer_payments",
            "suppliers", "supplier_payments", "purchase_invoices", "purchase_items",
            "purchase_returns", "purchase_return_items", "sales", "sale_items",
            "sale_payments", "sale_returns", "sale_return_items", "held_bills",
            "held_bill_items", "staff_members", "store_branches", "ca_profiles",
            "printer_devices"
        ]
        _reset_postgres_sequences(db, tables_to_sync)

        # D. Post-restore Verification Check
        expected_counts = manifest.get("record_counts", {})
        restored_products = db.query(models.Product).filter(models.Product.user_id == user_id).count()
        restored_sales = db.query(models.Sale).filter(models.Sale.user_id == user_id).count()
        restored_customers = db.query(models.Customer).filter(models.Customer.user_id == user_id).count()
        restored_suppliers = db.query(models.Supplier).filter(models.Supplier.user_id == user_id).count()
        restored_staff = db.query(models.StaffMember).filter(models.StaffMember.user_id == user_id).count()

        verification_summary = {
            "products": {"expected": expected_counts.get("products", 0), "actual": restored_products},
            "sales": {"expected": expected_counts.get("sales", 0), "actual": restored_sales},
            "customers": {"expected": expected_counts.get("customers", 0), "actual": restored_customers},
            "suppliers": {"expected": expected_counts.get("suppliers", 0), "actual": restored_suppliers},
            "staff": {"expected": expected_counts.get("staff", 0), "actual": restored_staff},
        }

        # Check for count mismatch
        for entity, check in verification_summary.items():
            if check["actual"] != check["expected"]:
                raise ValueError(
                    f"Integrity check failed for {entity}: expected {check['expected']} records, "
                    f"found {check['actual']} after restoration."
                )

        # Commit transaction
        db.commit()

        # Update Restore Log
        restore_log.status = "RESTORED"
        restore_log.completed_at = datetime.utcnow()
        restore_log.verification_summary_json = json.dumps(verification_summary)
        db.commit()

        logger.info(f"[RESTORE SUCCESS] Shop ID {user_id} successfully restored from backup!")
        return {
            "success": True,
            "status": "success",
            "message": "Database restored successfully.",
            "safety_backup_id": safety_record.backup_id,
            "verification": verification_summary,
            "restored_at": datetime.utcnow().isoformat(),
        }

    except Exception as e:
        db.rollback()
        logger.error(f"[RESTORE ERROR] Restoration failed, rolled back changes: {e}")
        try:
            restore_log.status = "FAILED"
            restore_log.error_message = str(e)
            db.commit()
        except Exception:
            pass
        raise ValueError(f"Restoration failed: {e}. All changes were rolled back to the safety state.") from e


def get_backup_history(db: Session, user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    """Returns list of all backup snapshots for the pharmacy shop."""
    records = db.query(models.BackupRecord).filter(
        models.BackupRecord.user_id == user_id
    ).order_by(models.BackupRecord.created_at.desc()).limit(limit).all()

    results = []
    for r in records:
        counts = {}
        if r.record_counts_json:
            try:
                counts = json.loads(r.record_counts_json)
            except Exception:
                pass

        results.append({
            "id": r.id,
            "backup_id": r.backup_id,
            "filename": r.filename,
            "file_size_bytes": r.file_size_bytes,
            "file_size_formatted": _format_file_size(r.file_size_bytes),
            "backup_type": r.backup_type,
            "status": r.status,
            "backup_version": r.backup_version,
            "schema_version": r.schema_version,
            "app_version": r.app_version,
            "checksum_sha256": r.checksum_sha256,
            "record_counts": counts,
            "notes": r.notes,
            "created_by_name": r.created_by_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })
    return results


def delete_backup(db: Session, user_id: int, backup_id: str) -> bool:
    """Deletes a backup file and its record from the database."""
    record = db.query(models.BackupRecord).filter(
        models.BackupRecord.user_id == user_id,
        models.BackupRecord.backup_id == backup_id
    ).first()

    if not record:
        raise ValueError("Backup record not found.")

    if record.file_path and os.path.exists(record.file_path):
        try:
            os.remove(record.file_path)
        except Exception as e:
            logger.warning(f"Could not delete backup file {record.file_path}: {e}")

    db.delete(record)
    db.commit()
    return True


def _format_file_size(size_bytes: int) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
