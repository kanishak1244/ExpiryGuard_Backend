import os
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from sqlalchemy.pool import NullPool

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required. Please set it in Railway variables.")

# Sanitize common input mistakes (accidental quotes, whitespace, or KEY= prefix)
DATABASE_URL = DATABASE_URL.strip().strip("'\"")
if DATABASE_URL.startswith("DATABASE_URL="):
    DATABASE_URL = DATABASE_URL[len("DATABASE_URL="):].strip().strip("'\"")

if DATABASE_URL.startswith("<") or "your_supabase" in DATABASE_URL.lower():
    raise RuntimeError("DATABASE_URL contains an example placeholder (<your_supabase_postgresql_connection_string>). Please paste your real Supabase connection string.")

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
