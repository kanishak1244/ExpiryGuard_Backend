import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine

def migrate_user_settings():
    print("=" * 70)
    print("--- EXPIRYGUARD: USER SETTINGS & PHARMACY PROFILE SQL MIGRATION ---")
    print("=" * 70)

    sql_cmds = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS drug_license_no VARCHAR DEFAULT 'DL-2026-PHARMA-01';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS logo_url VARCHAR;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_and_conditions TEXT DEFAULT '1. Goods once sold will not be taken back without original bill.\n2. Expiry dates checked at sales time.';",
        
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS default_payment_method VARCHAR DEFAULT 'CASH';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS invoice_prefix VARCHAR DEFAULT 'INV';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_gst_breakdown BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_hsn BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_batch_expiry BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS show_customer_info BOOLEAN DEFAULT TRUE;",

        "ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry_alerts_enabled BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS low_stock_alerts_enabled BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_notifications_enabled BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS delete_confirmation_required BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_save_enabled BOOLEAN DEFAULT TRUE;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR DEFAULT 'en';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_theme VARCHAR DEFAULT 'light';"
    ]

    with engine.connect() as conn:
        for cmd in sql_cmds:
            conn.execute(text(cmd))
        conn.commit()

    print("[OK] User settings and pharmacy profile columns verified in PostgreSQL.")

if __name__ == "__main__":
    migrate_user_settings()
