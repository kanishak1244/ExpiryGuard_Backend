import sys
import os
import json
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine, Base
import models

def migrate_catalog_split_fast():
    print("=" * 70)
    print("--- EXPIRYGUARD: FAST MEDICINE CATALOG SEPARATION & INVENTORY RESET ---")
    print("=" * 70)

    # Step 1: Ensure medicine_catalog table exists
    print("\n[STEP 1/3] Ensuring 'medicine_catalog' table exists in PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    print("[OK] 'medicine_catalog' table verified.")

    with engine.connect() as conn:
        # Step 2: Insert master entries directly into medicine_catalog via high-speed SQL
        print("\n[STEP 2/3] Transferring master items from 'products' into 'medicine_catalog'...")
        sql_transfer = text("""
            INSERT INTO medicine_catalog (product_name, brand, category, hsn_code, gst_rate, default_price, tablets_per_strip, pack_size_label, composition, verified)
            SELECT DISTINCT ON (LOWER(product_name)) 
                product_name, brand, category, hsn_code, gst_rate, unit_price, tablets_per_strip, pack_size_label, composition, verified
            FROM products 
            WHERE batch_number LIKE 'MASTER-LOT-%'
            ON CONFLICT DO NOTHING;
        """)
        res_transfer = conn.execute(sql_transfer)
        conn.commit()
        print(f"[OK] Transferred master items into 'medicine_catalog'.")

        # Step 3: Remove master entries from products live inventory table
        print("\n[STEP 3/3] Clearing master entries out of 'products' live stock table...")
        sql_delete = text("DELETE FROM products WHERE batch_number LIKE 'MASTER-LOT-%';")
        res_delete = conn.execute(sql_delete)
        conn.commit()
        print(f"[OK] Removed {res_delete.rowcount} master items from active inventory.")

        # Verification counts
        cat_count = conn.execute(text("SELECT COUNT(*) FROM medicine_catalog;")).scalar()
        prod_count = conn.execute(text("SELECT COUNT(*) FROM products;")).scalar()

        print("\n" + "=" * 70)
        print("SUCCESS: MIGRATION & SEPARATION COMPLETE!")
        print(f"   • Reference Catalog Items ('medicine_catalog'): {cat_count}")
        print(f"   • Actual Shop Inventory Stock ('products'):         {prod_count}")
        print("=" * 70)

if __name__ == "__main__":
    migrate_catalog_split_fast()
