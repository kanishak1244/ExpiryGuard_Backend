import sys
import os
from sqlalchemy import text

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import engine

def migrate_suppliers_documents():
    print("=" * 75)
    print("--- EXPIRYGUARD: SUPPLIERS & DOCUMENTS SQL MIGRATION ---")
    print("=" * 75)

    sql_cmds = [
        # Create Suppliers table
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            name VARCHAR NOT NULL,
            contact_person VARCHAR,
            phone VARCHAR,
            email VARCHAR,
            address TEXT,
            gstin VARCHAR,
            state VARCHAR DEFAULT 'Delhi',
            payment_terms VARCHAR DEFAULT 'Net 30',
            notes TEXT,
            status VARCHAR NOT NULL DEFAULT 'Active',
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_suppliers_user_id ON suppliers(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);",

        # Create Documents table
        """
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id),
            supplier_id INTEGER REFERENCES suppliers(id),
            sale_id INTEGER REFERENCES sales(id),
            title VARCHAR NOT NULL,
            doc_type VARCHAR NOT NULL DEFAULT 'purchase_invoice',
            file_path VARCHAR NOT NULL,
            file_type VARCHAR NOT NULL,
            file_size INTEGER DEFAULT 0,
            invoice_number VARCHAR,
            invoice_date DATE,
            total_amount FLOAT DEFAULT 0.0,
            item_count INTEGER DEFAULT 0,
            ocr_raw_json TEXT,
            ocr_status VARCHAR NOT NULL DEFAULT 'Processing',
            notes TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc'),
            updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
        );
        """,
        "CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);",
        "CREATE INDEX IF NOT EXISTS idx_documents_supplier_id ON documents(supplier_id);",

        # Update Products & InventoryTransactions for traceability
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id);",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id);",
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS invoice_number VARCHAR;",
        "CREATE INDEX IF NOT EXISTS idx_products_supplier_id ON products(supplier_id);",
        "CREATE INDEX IF NOT EXISTS idx_products_document_id ON products(document_id);",

        "ALTER TABLE inventory_transactions ADD COLUMN IF NOT EXISTS supplier_id INTEGER REFERENCES suppliers(id);",
        "ALTER TABLE inventory_transactions ADD COLUMN IF NOT EXISTS document_id INTEGER REFERENCES documents(id);",
        "ALTER TABLE inventory_transactions ADD COLUMN IF NOT EXISTS invoice_number VARCHAR;"
    ]

    with engine.connect() as conn:
        for cmd in sql_cmds:
            conn.execute(text(cmd))
        conn.commit()

    print("[OK] Suppliers, Documents, and Traceability schema verified in PostgreSQL.")

if __name__ == "__main__":
    migrate_suppliers_documents()
