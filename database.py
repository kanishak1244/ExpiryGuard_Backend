import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL or DATABASE_URL.startswith("<") or "your_supabase" in DATABASE_URL.lower():
    print("[Startup Warning] DATABASE_URL missing or placeholder; defaulting to local SQLite database.")
    DATABASE_URL = f"sqlite:///{(BASE_DIR / 'dawaiflow.db').resolve()}"
else:
    # Sanitize common input mistakes (accidental quotes, whitespace, or KEY= prefix)
    DATABASE_URL = DATABASE_URL.strip().strip("'\"")
    if DATABASE_URL.startswith("DATABASE_URL="):
        DATABASE_URL = DATABASE_URL[len("DATABASE_URL="):].strip().strip("'\"")

# Auto-normalize standard postgresql scheme
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+psycopg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# Supabase Pooler optimization:
# If connecting through Supabase pooler (pooler.supabase.com),
# switch port 5432 (Session mode, max 15 clients) to 6543 (Transaction mode, unlimited clients),
# and use NullPool + pool_pre_ping=True to prevent EMAXCONNSESSION errors.
is_supabase_pooler = "pooler.supabase.com" in DATABASE_URL

if is_supabase_pooler:
    if ":5432" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace(":5432", ":6543")
    
    engine = create_engine(
        DATABASE_URL,
        pool_size=15,
        max_overflow=10,
        pool_recycle=1800,
        pool_use_lifo=True,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None, "connect_timeout": 10},
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_use_lifo=True,
        pool_recycle=1800,
        connect_args={"connect_timeout": 10},
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False, # Keep in-memory attributes on commit to avoid re-fetch round-trips
    bind=engine
)

Base = declarative_base()

def ensure_return_columns():
    """
    Idempotent schema migration ensuring sales and sale_items relations have return tracking columns.
    """
    from sqlalchemy import text
    try:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_returned_amount DOUBLE PRECISION DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS returned_quantity INTEGER DEFAULT 0;"))
    except Exception as e:
        print(f"[!] Schema migration note: {e}")

# Column migration helper - call on demand if needed
# ensure_return_columns()

