import sys
import os
import re
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
import models

def parse_pack_size_label(label: str):
    """
    Parses human pack_size_label text into (units_per_pack, is_countable, needs_review).
    Handles tablets, capsules, strips, bottles (ml), tubes (gm), etc.
    """
    if not label or not isinstance(label, str) or label.strip().lower() in ['nan', 'none', '']:
        return None, False, True

    clean = label.strip().lower()

    # 1. Non-countable items (Liquids, Syrups, Drops, Creams, Ointments, Injections, Powders)
    non_countable_keywords = ['ml', 'gm', 'gram', 'kg', 'ltr', 'liter', 'syrup', 'suspension', 'ointment', 'gel', 'cream', 'drops', 'lotion', 'solution', 'elixir']
    is_liquid_or_cream = any(kw in clean for kw in non_countable_keywords)
    has_pill_kw = any(p in clean for p in ['tablet', 'tab', 'capsule', 'cap', 'strip', 'softgel', 'pill'])

    if is_liquid_or_cream and not has_pill_kw:
        return None, False, False

    # 2. Extract numeric unit count for countable items (tablets, capsules, strips)
    patterns = [
        r'(?:strip|box|pack|blister|vial|bottle)\s+of\s+(\d+)\b',
        r'(\d+)\s*(?:tablet|tablets|tab|capsule|capsules|cap|softgel|softgels|pill|pills|n)\b',
        r'(?:strip|box|pack|blister)\s*\(?\s*(\d+)\s*\)?',
        r'^(\d+)\s*(?:s|tabs|caps)?$',
    ]

    for pat in patterns:
        match = re.search(pat, clean)
        if match:
            try:
                count = int(match.group(1))
                if 1 <= count <= 1000:
                    return count, True, False
            except ValueError:
                pass

    nums = re.findall(r'\b(\d+)\b', clean)
    if nums:
        try:
            val = int(nums[0])
            if 1 <= val <= 200:
                return val, True, False
        except ValueError:
            pass

    return None, True, True

def run_pack_size_migration():
    print("=" * 70)
    print("--- EXPIRYGUARD: PARSE PACK SIZE & AUTO-CALCULATE PER-UNIT PRICE ---")
    print("=" * 70)

    # 1. Add SQL columns
    print("\n[STEP 1/3] Adding database columns for per-unit pricing...")
    sql_cols = [
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS units_per_pack INTEGER;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS price_per_unit FLOAT;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS is_countable BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE medicine_catalog ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;",

        "ALTER TABLE products ADD COLUMN IF NOT EXISTS units_per_pack INTEGER;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS price_per_unit FLOAT;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_countable BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS needs_review BOOLEAN DEFAULT FALSE;"
    ]

    with engine.connect() as conn:
        for query in sql_cols:
            conn.execute(text(query))
        conn.commit()
    print("[OK] Columns verified.")

    db = SessionLocal()
    try:
        # 2. Parse & Calculate for MedicineCatalog using yield_per
        print("\n[STEP 2/3] Processing 'medicine_catalog' table (chunked commits)...")
        
        count = 0
        parsed_countable = 0
        parsed_non_countable = 0
        flagged_review = 0

        for cat in db.query(models.MedicineCatalog).yield_per(5000):
            units, is_count, review = parse_pack_size_label(cat.pack_size_label)
            cat.units_per_pack = units or cat.tablets_per_strip or (10 if is_count else None)
            cat.is_countable = is_count
            cat.needs_review = review

            if is_count and cat.units_per_pack and cat.units_per_pack > 0:
                cat.price_per_unit = round((cat.default_price or 0.0) / cat.units_per_pack, 2)
                cat.tablets_per_strip = cat.units_per_pack
                parsed_countable += 1
            else:
                cat.price_per_unit = None
                if not is_count:
                    parsed_non_countable += 1
                if review:
                    flagged_review += 1

            count += 1
            if count % 10000 == 0:
                db.commit()
                print(f"   [CHUNK COMMIT] Processed {count} catalog items...")

        db.commit()
        print(f"[OK] MedicineCatalog updated ({count} total items):")
        print(f"   • Countable medicines (tablets/capsules): {parsed_countable}")
        print(f"   • Non-countable (syrups/ointments/ml):     {parsed_non_countable}")
        print(f"   • Flagged for review:                       {flagged_review}")

        # 3. Parse & Calculate for Products (Live Inventory)
        print("\n[STEP 3/3] Processing active 'products' live inventory table...")
        products = db.query(models.Product).all()
        for prod in products:
            units, is_count, review = parse_pack_size_label(prod.pack_size_label)
            prod.units_per_pack = units or prod.tablets_per_strip or (10 if is_count else None)
            prod.is_countable = is_count
            prod.needs_review = review

            if is_count and prod.units_per_pack and prod.units_per_pack > 0:
                prod.price_per_unit = round((prod.unit_price or 0.0) / prod.units_per_pack, 2)
                prod.loose_tablet_price = prod.price_per_unit
                prod.tablets_per_strip = prod.units_per_pack

        db.commit()
        print(f"[OK] Active inventory updated ({len(products)} products).")

        print("\n" + "=" * 70)
        print("SUCCESS: PER-UNIT PRICING & PACK SIZE MIGRATION COMPLETE!")
        print("=" * 70)

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Migration failed: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    run_pack_size_migration()
