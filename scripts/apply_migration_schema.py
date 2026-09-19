"""
Schema migration script for Data Migration & Import Old Bills.
Safely adds tables and columns without touching live data.
"""
import sys
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from database import engine
from sqlalchemy import text


def run_migration():
    print("Applying schema updates for Data Migration system...")
    with engine.begin() as conn:
        # 1. Create data_migrations table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS data_migrations (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                migration_code VARCHAR(50) UNIQUE NOT NULL,
                migration_type VARCHAR(50) NOT NULL DEFAULT 'OLD_BILLS',
                source_software VARCHAR(50) DEFAULT 'OTHER',
                file_name VARCHAR(255) NOT NULL,
                file_format VARCHAR(20) NOT NULL,
                file_size_bytes INTEGER DEFAULT 0,
                status VARCHAR(50) NOT NULL DEFAULT 'PREVIEW',
                total_records_detected INTEGER DEFAULT 0,
                total_records_parsed INTEGER DEFAULT 0,
                total_records_imported INTEGER DEFAULT 0,
                total_duplicates_skipped INTEGER DEFAULT 0,
                total_errors INTEGER DEFAULT 0,
                total_amount_imported DOUBLE PRECISION DEFAULT 0.0,
                progress_percentage INTEGER DEFAULT 0,
                preview_data_json TEXT,
                summary_notes TEXT,
                error_message TEXT,
                created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT (NOW() AT TIME ZONE 'utc'),
                completed_at TIMESTAMP WITHOUT TIME ZONE,
                rolled_back_at TIMESTAMP WITHOUT TIME ZONE
            );
            CREATE INDEX IF NOT EXISTS ix_data_migrations_id ON data_migrations(id);
            CREATE INDEX IF NOT EXISTS ix_data_migrations_user_id ON data_migrations(user_id);
            CREATE INDEX IF NOT EXISTS ix_data_migrations_code ON data_migrations(migration_code);
            CREATE INDEX IF NOT EXISTS ix_data_migrations_status ON data_migrations(status);
        """))
        print("[OK] data_migrations table verified")

        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='current_stage') THEN
                    ALTER TABLE data_migrations ADD COLUMN current_stage VARCHAR(50) NOT NULL DEFAULT 'uploading';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='current_stage_label') THEN
                    ALTER TABLE data_migrations ADD COLUMN current_stage_label VARCHAR(100) NOT NULL DEFAULT 'Uploading document';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='current_message') THEN
                    ALTER TABLE data_migrations ADD COLUMN current_message VARCHAR(255) NOT NULL DEFAULT 'DAWAI FLOW AI is preparing your document...';
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='processed_count') THEN
                    ALTER TABLE data_migrations ADD COLUMN processed_count INTEGER NOT NULL DEFAULT 0;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='total_count') THEN
                    ALTER TABLE data_migrations ADD COLUMN total_count INTEGER NOT NULL DEFAULT 0;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='data_migrations' AND column_name='is_large_file') THEN
                    ALTER TABLE data_migrations ADD COLUMN is_large_file BOOLEAN NOT NULL DEFAULT FALSE;
                END IF;
            END $$;
        """))
        print("[OK] data_migrations stage tracking columns verified")

        # 2. Create migration_errors table if not exists
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS migration_errors (
                id SERIAL PRIMARY KEY,
                migration_id INTEGER NOT NULL REFERENCES data_migrations(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id),
                row_number INTEGER,
                bill_identifier VARCHAR(100),
                error_type VARCHAR(50) DEFAULT 'PARSE_ERROR',
                raw_record_json TEXT,
                reason TEXT NOT NULL,
                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
            );
            CREATE INDEX IF NOT EXISTS ix_migration_errors_id ON migration_errors(id);
            CREATE INDEX IF NOT EXISTS ix_migration_errors_migration_id ON migration_errors(migration_id);
            CREATE INDEX IF NOT EXISTS ix_migration_errors_user_id ON migration_errors(user_id);
        """))
        print("[OK] migration_errors table verified")

        # 3. Add columns to sales table if not present
        conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sales' AND column_name='is_historical') THEN
                    ALTER TABLE sales ADD COLUMN is_historical BOOLEAN NOT NULL DEFAULT FALSE;
                    CREATE INDEX IF NOT EXISTS ix_sales_is_historical ON sales(is_historical);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sales' AND column_name='transaction_source') THEN
                    ALTER TABLE sales ADD COLUMN transaction_source VARCHAR(50) NOT NULL DEFAULT 'LIVE_BILLING';
                    CREATE INDEX IF NOT EXISTS ix_sales_transaction_source ON sales(transaction_source);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sales' AND column_name='migration_id') THEN
                    ALTER TABLE sales ADD COLUMN migration_id INTEGER REFERENCES data_migrations(id) ON DELETE SET NULL;
                    CREATE INDEX IF NOT EXISTS ix_sales_migration_id ON sales(migration_id);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sales' AND column_name='original_bill_number') THEN
                    ALTER TABLE sales ADD COLUMN original_bill_number VARCHAR(100);
                    CREATE INDEX IF NOT EXISTS ix_sales_original_bill_number ON sales(original_bill_number);
                END IF;
            END $$;
        """))
        print("[OK] sales table historical columns verified")

        # 4. Alter sale_items table: make product_id nullable and add migration columns
        conn.execute(text("""
            DO $$
            BEGIN
                -- Make product_id nullable for historic items that cannot match catalog
                ALTER TABLE sale_items ALTER COLUMN product_id DROP NOT NULL;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sale_items' AND column_name='is_historical') THEN
                    ALTER TABLE sale_items ADD COLUMN is_historical BOOLEAN NOT NULL DEFAULT FALSE;
                    CREATE INDEX IF NOT EXISTS ix_sale_items_is_historical ON sale_items(is_historical);
                END IF;

                IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='sale_items' AND column_name='migration_id') THEN
                    ALTER TABLE sale_items ADD COLUMN migration_id INTEGER REFERENCES data_migrations(id) ON DELETE SET NULL;
                    CREATE INDEX IF NOT EXISTS ix_sale_items_migration_id ON sale_items(migration_id);
                END IF;
            END $$;
        """))
        print("[OK] sale_items table columns verified and product_id made nullable")

    print("Migration schema applied successfully!")


if __name__ == "__main__":
    run_migration()
