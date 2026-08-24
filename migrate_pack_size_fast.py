import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine

def run_fast_pack_size_migration():
    print("=" * 70)
    print("--- EXPIRYGUARD: HIGH-SPEED SQL PER-UNIT PRICING MIGRATION ---")
    print("=" * 70)

    sql_commands = [
        # 1. Add SQL columns if not present
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS units_per_pack INTEGER;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS price_per_unit FLOAT;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS is_countable BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;",

        "ALTER TABLE products ADD COLUMN IF NOT EXISTS units_per_pack INTEGER;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_per_unit FLOAT;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_countable BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;",

        # 2. Update MedicineCatalog countable vs non-countable
        """
        UPDATE medicine_catalog 
        SET units_per_pack = COALESCE(tablets_per_strip, 10),
            is_countable = TRUE
        WHERE pack_size_label ILIKE '%tablet%' 
           OR pack_size_label ILIKE '%capsule%' 
           OR pack_size_label ILIKE '%strip%'
           OR pack_size_label ILIKE '%pill%';
        """,
        """
        UPDATE medicine_catalog 
        SET is_countable = FALSE,
            units_per_pack = NULL,
            price_per_unit = NULL
        WHERE pack_size_label ILIKE '%ml%' 
           OR pack_size_label ILIKE '%gm%' 
           OR pack_size_label ILIKE '%syrup%' 
           OR pack_size_label ILIKE '%ointment%' 
           OR pack_size_label ILIKE '%gel%' 
           OR pack_size_label ILIKE '%cream%'
           OR pack_size_label ILIKE '%drops%'
           OR pack_size_label ILIKE '%solution%';
        """,
        """
        UPDATE medicine_catalog 
        SET price_per_unit = ROUND((default_price / NULLIF(units_per_pack, 0))::numeric, 2)
        WHERE is_countable = TRUE AND units_per_pack > 0 AND default_price > 0;
        """,

        # 3. Update Products live inventory table
        """
        UPDATE products 
        SET units_per_pack = COALESCE(tablets_per_strip, 10),
            is_countable = TRUE
        WHERE pack_size_label ILIKE '%tablet%' 
           OR pack_size_label ILIKE '%capsule%' 
           OR pack_size_label ILIKE '%strip%'
           OR pack_size_label ILIKE '%pill%';
        """,
        """
        UPDATE products 
        SET is_countable = FALSE,
            units_per_pack = NULL,
            price_per_unit = NULL
        WHERE pack_size_label ILIKE '%ml%' 
           OR pack_size_label ILIKE '%gm%' 
           OR pack_size_label ILIKE '%syrup%' 
           OR pack_size_label ILIKE '%ointment%' 
           OR pack_size_label ILIKE '%gel%' 
           OR pack_size_label ILIKE '%cream%';
        """,
        """
        UPDATE products 
        SET price_per_unit = ROUND((unit_price / NULLIF(units_per_pack, 0))::numeric, 2),
            loose_tablet_price = ROUND((unit_price / NULLIF(units_per_pack, 0))::numeric, 2)
        WHERE is_countable = TRUE AND units_per_pack > 0 AND unit_price > 0;
        """
    ]

    with engine.connect() as conn:
        for idx, cmd in enumerate(sql_commands, 1):
            conn.execute(text(cmd))
            conn.commit()
            print(f"[OK] Executed SQL step #{idx}")

        cat_countable = conn.execute(text("SELECT COUNT(*) FROM medicine_catalog WHERE is_countable = TRUE;")).scalar()
        cat_non_countable = conn.execute(text("SELECT COUNT(*) FROM medicine_catalog WHERE is_countable = FALSE;")).scalar()
        prod_count = conn.execute(text("SELECT COUNT(*) FROM products;")).scalar()

        print("\n" + "=" * 70)
        print("SUCCESS: HIGH-SPEED PER-UNIT PRICING MIGRATION COMPLETE!")
        print(f"   • Countable Catalog Medicines (Tablets/Capsules): {cat_countable}")
        print(f"   • Non-Countable Catalog Items (Liquids/Creams):    {cat_non_countable}")
        print(f"   • Live Shop Inventory Items Updated:              {prod_count}")
        print("=" * 70)

if __name__ == "__main__":
    run_fast_pack_size_migration()
