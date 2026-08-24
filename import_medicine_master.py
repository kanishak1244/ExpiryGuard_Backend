import sys
import os
import argparse
import pandas as pd
from datetime import datetime, date, timedelta

# Append current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine, Base
import models

DEFAULT_CSV_PATH = r"C:\Users\vashi\OneDrive\Desktop\expiry date detection (mannual)\indian_medicine_data.csv"

def parse_pack_size(label: str) -> int:
    """Parses tablets per strip from pack_size_label (e.g. 'strip of 10 tablets' -> 10)"""
    if not label or pd.isna(label):
        return 10
    import re
    match = re.search(r'(\d+)\s*(tablet|capsule|strip|pill)', str(label).lower())
    if match:
        try:
            return int(match.group(1))
        except ValueError:
            pass
    return 10

def import_medicine_master(csv_path: str = DEFAULT_CSV_PATH, target_user_id: int = 1, is_test_run: bool = True, batch_size: int = 5000):
    print("=" * 60)
    print(f"--- EXPIRYGUARD MEDICINE MASTER IMPORT ---")
    print(f"Source CSV Path: {csv_path}")
    print(f"Target User ID: #{target_user_id}")
    print(f"Mode: {'TEST RUN (50 rows only)' if is_test_run else 'FULL IMPORT'}")
    print("=" * 60)

    if not os.path.exists(csv_path):
        print(f"[ERROR] File not found: {csv_path}")
        return

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        # Check target user
        user = db.query(models.User).filter(models.User.id == target_user_id).first()
        if not user:
            print(f"[WARNING] User #{target_user_id} not found! Fetching first available user...")
            user = db.query(models.User).first()
            if not user:
                print("[ERROR] No user accounts exist in database! Register a user first.")
                return
            target_user_id = user.id

        print(f"[OK] Importing for Shop: '{user.shop_name}' (Owner: {user.owner_name}, User ID: #{target_user_id})")

        nrows = 50 if is_test_run else None
        print(f"[INFO] Reading CSV file into memory...")
        df = pd.read_csv(csv_path, nrows=nrows)
        print(f"[OK] Loaded {len(df)} rows from CSV.")

        # Inspection report
        print("\n--- DATA CLEANING & COLUMN MAPPING ---")
        clean_cols = [str(c).encode('ascii', 'ignore').decode('ascii') for c in df.columns]
        print("Raw Columns:", clean_cols)

        # Filter out discontinued or invalid
        if 'Is_discontinued' in df.columns:
            df = df[df['Is_discontinued'] == False]

        df = df.dropna(subset=['name'])
        df = df[df['name'].str.strip() != '']

        print(f"[OK] Valid non-discontinued rows to insert: {len(df)}")

        # Fetch existing product names to avoid exact duplicate inserts
        existing_names = set(
            c[0].lower() for c in db.query(models.MedicineCatalog.product_name).all()
        )
        print(f"[OK] Existing catalog items in DB: {len(existing_names)}")

        new_catalog_items = []
        inserted_count = 0
        skipped_count = 0

        for idx, row in df.iterrows():
            prod_name = str(row['name']).strip()
            if prod_name.lower() in existing_names:
                skipped_count += 1
                continue

            price_raw = row.get('price(₹)') or row.get('price') or 0.0
            try:
                unit_price = float(price_raw)
            except (ValueError, TypeError):
                unit_price = 0.0

            brand_raw = str(row.get('manufacturer_name') or row.get('brand') or 'Generic').strip()
            category_raw = str(row.get('type') or row.get('category') or 'allopathy').strip()
            pack_label = str(row.get('pack_size_label') or '').strip()

            comp1 = str(row.get('short_composition1') or '').strip()
            comp2 = str(row.get('short_composition2') or '').strip()
            comp_combined = f"{comp1} {comp2}".strip() or None

            tablets_strip = parse_pack_size(pack_label)

            cat_item = models.MedicineCatalog(
                product_name=prod_name,
                brand=brand_raw,
                category=category_raw,
                hsn_code="3004",
                gst_rate=12.0,
                default_price=unit_price,
                tablets_per_strip=tablets_strip,
                pack_size_label=pack_label if pack_label else None,
                composition=comp_combined,
                verified=False
            )

            new_catalog_items.append(cat_item)
            existing_names.add(prod_name.lower())

            if len(new_catalog_items) >= batch_size:
                db.bulk_save_objects(new_catalog_items)
                db.commit()
                inserted_count += len(new_catalog_items)
                print(f"   [BULK COMMIT] Inserted {inserted_count} catalog items...")
                new_catalog_items.clear()

        if new_catalog_items:
            db.bulk_save_objects(new_catalog_items)
            db.commit()
            inserted_count += len(new_catalog_items)

        print("\n" + "=" * 60)
        print(f"[SUCCESS] IMPORT COMPLETE!")
        print(f"   Successfully Inserted: {inserted_count} medicines")
        print(f"   Duplicates Skipped:   {skipped_count}")
        print("=" * 60)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Import failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ExpiryGuard Medicine Master Data Import Script")
    parser.add_argument("--file", type=str, default=DEFAULT_CSV_PATH, help="Path to medicine CSV file")
    parser.add_argument("--user-id", type=int, default=1, help="Target user ID")
    parser.add_argument("--full", action="store_true", help="Run full import (all 250k rows)")
    args = parser.parse_args()

    is_test = not args.full
    import_medicine_master(csv_path=args.file, target_user_id=args.user_id, is_test_run=is_test)
