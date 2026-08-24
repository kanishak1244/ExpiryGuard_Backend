import sys
import os
from sqlalchemy import text, func

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
import models
import crud

def inspect_hsn_coverage():
    print("=" * 75)
    print("--- EXPIRYGUARD: HSN CODE COVERAGE & TAX RATE AUDIT ---")
    print("=" * 75)

    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Audit MedicineCatalog (Reference Dataset)
        total_catalog = db.query(models.MedicineCatalog).count()
        missing_catalog_hsn = db.query(models.MedicineCatalog).filter(
            (models.MedicineCatalog.hsn_code.is_(None)) | 
            (models.MedicineCatalog.hsn_code == "") |
            (models.MedicineCatalog.hsn_code == "3004")  # default fallback
        ).count()

        distinct_catalog_hsn = (
            db.query(models.MedicineCatalog.hsn_code, func.count(models.MedicineCatalog.id))
            .group_by(models.MedicineCatalog.hsn_code)
            .order_by(func.count(models.MedicineCatalog.id).desc())
            .limit(10)
            .all()
        )

        print("\n1. MEDICINE REFERENCE CATALOG AUDIT (medicine_catalog):")
        print(f"   • Total Catalog Medicines:                  {total_catalog:,}")
        print(f"   • Standard Allopathy HSN 3004 / Default:   {missing_catalog_hsn:,} ({missing_catalog_hsn/total_catalog*100:.1f}%)")
        print("\n   Top HSN Distribution in Catalog:")
        for hsn, cnt in distinct_catalog_hsn:
            print(f"     - HSN '{hsn or 'BLANK'}': {cnt:,} items ({cnt/total_catalog*100:.1f}%)")

        # 2. Audit Products (Active Shop Inventory)
        total_products = db.query(models.Product).count()
        missing_prod_hsn = db.query(models.Product).filter(
            (models.Product.hsn_code.is_(None)) | 
            (models.Product.hsn_code == "")
        ).count()

        distinct_prod_hsn = (
            db.query(models.Product.hsn_code, func.count(models.Product.id))
            .group_by(models.Product.hsn_code)
            .all()
        )

        print("\n2. ACTIVE SHOP INVENTORY AUDIT (products):")
        print(f"   • Total Active Stock Items:                 {total_products:,}")
        print(f"   • Missing HSN Code Count:                   {missing_prod_hsn:,}")
        print("   Active Stock HSN Distribution:")
        for hsn, cnt in distinct_prod_hsn:
            print(f"     - HSN '{hsn or 'BLANK'}': {cnt:,} items")

        # 3. Reference HSN Tax Table Audit
        crud.seed_default_hsn_rates(db)
        hsn_rates = db.query(models.HsnTaxRate).all()
        print("\n3. REGISTERED HSN TAX RATE LOOKUP MAPPINGS (hsn_tax_rates):")
        print(f"{'HSN CODE':<10} | {'GST RATE':<10} | {'LIFE SAVING':<12} | {'CATEGORY':<15} | {'DESCRIPTION'}")
        print("-" * 80)
        for hr in hsn_rates:
            ls_str = "YES (Nil 0%)" if hr.is_life_saving else "No"
            print(f"{hr.hsn_code:<10} | {hr.gst_rate:<9.1f}% | {ls_str:<12} | {hr.category:<15} | {hr.description[:35]}")

        print("\n" + "=" * 75)
        print("RECOMMENDED BULK HSN POPULATION & COMPLIANCE STRATEGY:")
        print("=" * 75)
        print("""
1. AUTOMATIC BASELINE RULE (HSN 3004 @ 5% GST):
   - Over 95% of retail pharmacy items in India fall under HSN 3004 (Medicaments) or 3003.
   - Setting HSN 3004 (5% GST) as the smart default covers almost all prescription allopathic medicines.

2. CATEGORY-BASED AUTOMATIC PATTERN MATCHING:
   - Supplements / Protein / Nutraceuticals -> HSN 2106 (18% GST)
   - Cosmetics / Medicated Soaps / Shampoos  -> HSN 3304 (18% GST)
   - Bandages / Gauzes / Surgical Dressings -> HSN 3005 (12% GST)
   - Vaccines / Life-Saving Immunologicals  -> HSN 3002 (0% Nil GST)

3. PILOT PHARMACY SCAN-TIME AUTO-LEARNING:
   - When a shopkeeper scans a supplier invoice during restocking, Gemini AI automatically extracts
     the supplier's HSN code printed on the invoice (e.g. 3004, 3005, 2106).
   - ExpiryGuard saves that verified HSN code back into the product catalog, automatically populating
     the missing entries organically as pilot pharmacies use the app!
        """)

    except Exception as e:
        print(f"[ERROR] Audit failed: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    inspect_hsn_coverage()
