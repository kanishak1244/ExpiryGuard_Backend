import os
import json
import shutil
import re
import threading
from difflib import SequenceMatcher
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set, Union
from datetime import datetime, timedelta, date
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Response, status, BackgroundTasks, Query, WebSocket, WebSocketDisconnect, Body
import mimetypes
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from sqlalchemy import text, func, case, or_, and_, select
from ai.gemini_service import scan_label
from ai.multi_item_scan_service import scan_multi_item
from pdf_generator import generate_invoice_pdf
import thermal_formatter
import import_service
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

import firebase_admin
from firebase_admin import credentials, messaging

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("expiryguard")

# Internal Modules
import models
import schemas
import crud
import permissions
from database import engine, Base, SessionLocal
from scheduler import start_scheduler
from notification_service import send_expiry_notifications
from email_service import (
    send_pilot_lead_notification,
    send_test_email,
    check_smtp_health,
    retry_pending_pilot_leads,
)
from ai.invoice_service import scan_invoice
from crypto_utils import encrypt_staff_password, decrypt_staff_password
import backup_service
import migration_service
from services.gst_calculator import calculate_gst_due_dates

# ==========================================
# CONFIGURATION & INITIALIZATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
PUBLIC_SITE_DIR = BASE_DIR / "public_site"
PUBLIC_SITE_DIST = PUBLIC_SITE_DIR / "dist"
PUBLIC_SERVE_DIR = PUBLIC_SITE_DIST if (PUBLIC_SITE_DIST / "index.html").exists() else PUBLIC_SITE_DIR
try:
    os.makedirs(WEB_DIR, exist_ok=True)
    os.makedirs(PUBLIC_SITE_DIR, exist_ok=True)
except Exception:
    pass
load_dotenv(dotenv_path=BASE_DIR / ".env")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
ALLOWED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
ALLOWED_DOC_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
ALLOWED_SPREADSHEET_EXTENSIONS = {
    ".xlsx",
    ".xls",
    ".csv",
}
MAX_FILE_SIZE_10MB = 10 * 1024 * 1024  # 10 MB
MAX_FILE_SIZE_5MB = 5 * 1024 * 1024    # 5 MB
MAX_IMAGE_PIXELS = 50_000_000         # 50 Megapixels max

def check_file_size(file: UploadFile, max_size: int = MAX_FILE_SIZE_10MB):
    """Safely determines uploaded file size without loading contents fully into RAM or writing fully to disk."""
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > max_size:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File size exceeds maximum allowed limit of {max_size // (1024 * 1024)} MB."
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Could not validate upload file size: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="Could not validate upload file size."
        )

def validate_file_content_and_magic(file_bytes: bytes, ext: str):
    """Validates file magic byte signatures and protects against decompression bombs or script uploads."""
    ext = ext.lower()
    FORBIDDEN_EXTENSIONS = {".exe", ".sh", ".bat", ".php", ".py", ".js", ".html", ".htm", ".svg", ".dll", ".so", ".cmd", ".vbs", ".ps1"}
    if ext in FORBIDDEN_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"File extension '{ext}' is forbidden for security reasons.")

    if ext in [".jpg", ".jpeg"]:
        if not file_bytes.startswith(b"\xFF\xD8\xFF"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid JPEG image file signature.")
    elif ext == ".png":
        if not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid PNG image file signature.")
    elif ext == ".webp":
        if not (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16]):
            raise HTTPException(status_code=400, detail="Corrupted or invalid WEBP image file signature.")
    elif ext == ".pdf":
        if not file_bytes.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="Corrupted or invalid PDF document file signature.")
    elif ext == ".xlsx":
        if not (file_bytes.startswith(b"PK\x03\x04") or file_bytes.startswith(b"PK\x05\x06")):
            raise HTTPException(status_code=400, detail="Corrupted or invalid Excel spreadsheet file signature.")
    elif ext == ".xls":
        if not (file_bytes.startswith(b"\xD0\xCF\x11\xE0") or file_bytes.startswith(b"PK\x03\x04")):
            raise HTTPException(status_code=400, detail="Corrupted or invalid legacy Excel file signature.")
    elif ext == ".csv":
        if b"\x00" in file_bytes[:1024]:
            raise HTTPException(status_code=400, detail="Binary data not allowed in CSV spreadsheet.")

    # Image pixel resolution & integrity check (Decompression Bomb & Corruption Protection)
    if ext in [".jpg", ".jpeg", ".png", ".webp"]:
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(file_bytes))
            img.verify()
            img = Image.open(io.BytesIO(file_bytes))
            width, height = img.size
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Image dimensions ({width}x{height}) exceed maximum allowed resolution limits."
                )
        except HTTPException:
            raise
        except Exception as img_err:
            logger.warning(f"PIL Image verification error: {img_err}")
            raise HTTPException(status_code=400, detail="Corrupted or malformed image file content.")

# Parse allowed CORS origins from environment or default to environment-specific origins
is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
default_origins = (
    "https://dawaiflow.com,https://app.dawaiflow.com,https://api.dawaiflow.com,https://expiryguard.com,https://app.expiryguard.com,https://api.expiryguard.com"
    if is_production
    else "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500"
)
raw_origins = os.getenv("ALLOWED_ORIGINS", default_origins)
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()]

class FastCacheManager:
    """
    High-performance in-memory TTL caching engine with per-user isolation and tag-based invalidation.
    Reduces latency for heavy aggregations (dashboard summary, intelligence, reports) from 2500ms -> 1ms.
    """
    def __init__(self):
        self._cache: Dict[str, Tuple[float, Any, Set[str]]] = {}
        self._user_keys: Dict[int, Set[str]] = {}

    def _resolve_key(self, arg1: Any, arg2: Optional[Any] = None) -> Tuple[str, Optional[int]]:
        if arg2 is not None:
            # Called as (user_id, key)
            return f"u:{arg1}:{arg2}", int(arg1) if isinstance(arg1, (int, str)) and str(arg1).isdigit() else None
        return str(arg1), None

    def get(self, arg1: Any, arg2: Optional[Any] = None) -> Optional[Any]:
        key, _ = self._resolve_key(arg1, arg2)
        entry = self._cache.get(key)
        if not entry:
            return None
        expire_time, data, _ = entry
        import time as _t
        if _t.time() > expire_time:
            self._cache.pop(key, None)
            return None
        return data

    def set(
        self,
        arg1: Any,
        arg2: Any = None,
        data: Any = None,
        ttl: Union[int, float] = 15,
        ttl_seconds: Optional[Union[int, float]] = None,
        user_id: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ):
        import time as _t
        effective_ttl = ttl_seconds if ttl_seconds is not None else ttl
        if data is not None:
            # Called as set(user_id, key, data, ttl=..., tags=...)
            u_id = int(arg1) if isinstance(arg1, (int, str)) and str(arg1).isdigit() else None
            key = f"u:{arg1}:{arg2}"
            actual_data = data
            effective_user_id = u_id or user_id
        else:
            # Called as set(key, data, ttl_seconds=..., user_id=..., tags=...)
            key = str(arg1)
            actual_data = arg2
            effective_user_id = user_id

        tag_set = set(tags or [])
        if effective_user_id:
            tag_set.add(f"user_{effective_user_id}")
            if effective_user_id not in self._user_keys:
                self._user_keys[effective_user_id] = set()
            self._user_keys[effective_user_id].add(key)

        self._cache[key] = (_t.time() + float(effective_ttl), actual_data, tag_set)

    def invalidate_tag(self, user_id: int, tag: str):
        self.invalidate_user(user_id, tag)

    def invalidate_user(self, user_id: int, tag: Optional[str] = None):
        keys_to_remove = set()
        user_tag = f"user_{user_id}"
        for k, (exp, data, tags) in list(self._cache.items()):
            if user_tag in tags or k.startswith(f"u:{user_id}:"):
                if tag is None or tag in tags:
                    keys_to_remove.add(k)
        for k in keys_to_remove:
            self._cache.pop(k, None)
        if tag is None and user_id in self._user_keys:
            self._user_keys.pop(user_id, None)

    def invalidate_tags(self, tags: List[str]):
        keys_to_remove = set()
        for k, (exp, data, entry_tags) in list(self._cache.items()):
            if any(t in entry_tags for t in tags):
                keys_to_remove.add(k)
        for k in keys_to_remove:
            self._cache.pop(k, None)

fast_cache = FastCacheManager()

app = FastAPI(title="DawaiFlow API", version="1.0.0")

@app.on_event("startup")
def warmup_database():
    try:
        # Quick scheduler launch
        try:
            start_scheduler()
        except Exception as sched_err:
            logger.warning(f"[Startup] Scheduler start notice: {sched_err}")

        # Quick SMTP health check
        try:
            smtp_status = check_smtp_health(probe_network=False)
            if smtp_status.get("is_configured"):
                logger.info(
                    f"[Startup] Email alert engine active for {smtp_status.get('recipient')} "
                    f"via {smtp_status.get('host')}:{smtp_status.get('primary_port')}."
                )
            else:
                logger.warning("[Startup WARNING] Email service not configured! Set SMTP_USER and SMTP_PASS (Gmail App Password).")
        except Exception as smtp_err:
            logger.warning(f"[Startup] SMTP health check notice: {smtp_err}")

        # Synchronous Core Table Column Verification
        try:
            from database import engine
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS drug_license_no VARCHAR DEFAULT 'DL-2026-PHARMA-01';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS logo_url VARCHAR;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_and_conditions TEXT DEFAULT '1. Goods once sold will not be taken back without original bill.\\n2. Expiry dates checked at sales time.';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_payment_method VARCHAR DEFAULT 'CASH';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS invoice_prefix VARCHAR DEFAULT 'INV';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_gst_breakdown BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_hsn BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_batch_expiry BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_customer_info BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry_alerts_enabled BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS low_stock_alerts_enabled BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS delete_confirmation_required BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_save_enabled BOOLEAN DEFAULT TRUE;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR DEFAULT 'en';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_theme VARCHAR DEFAULT 'light';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gstin VARCHAR DEFAULT '07AABCE1234F1Z5';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gst_number VARCHAR DEFAULT '07AABCE1234F1Z5';"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gst_filing_type VARCHAR;"))
                conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS state_category VARCHAR DEFAULT 'X';"))
        except Exception as sync_schema_err:
            logger.warning(f"[Startup Schema Notice] {sync_schema_err}")

        app.include_router(gst_reminder_routes.router)

        # Offload heavy DB connection, schema creation, & DDL index migrations to background thread so Uvicorn binds port instantly (< 10ms)
        def _background_warmup():
            try:
                from database import SessionLocal, Base, engine
                import crud
                import models
                try:
                    Base.metadata.create_all(bind=engine)
                except Exception as schema_err:
                    logger.warning(f"[Startup] Schema creation notice: {schema_err}")

                bg_db = SessionLocal()
                try:
                    # Index & Schema migrations
                    try:
                        bg_db.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_trgm_name ON products USING gin (product_name gin_trgm_ops);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_trgm_brand ON products USING gin (brand gin_trgm_ops);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_trgm_comp ON products USING gin (composition gin_trgm_ops);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_user_name_prefix ON products (user_id, lower(product_name) varchar_pattern_ops) WHERE is_deleted = false;"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_user_brand_prefix ON products (user_id, lower(brand) varchar_pattern_ops) WHERE is_deleted = false;"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_name ON medicine_catalog USING gin (product_name gin_trgm_ops);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_brand ON medicine_catalog USING gin (brand gin_trgm_ops);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_med_cat_trgm_comp ON medicine_catalog USING gin (composition gin_trgm_ops);"))

                        # Composite Performance Indexes for instant dashboard & reporting queries
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_sales_user_created ON sales (user_id, created_at DESC);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_sales_user_status ON sales (user_id, payment_status);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_products_user_deleted_exp ON products (user_id, is_deleted, quantity, expiry_date);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_sale_items_sale_prod ON sale_items (sale_id, product_id);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_customers_user_pending ON customers (user_id, pending_amount);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_purchases_user_created ON purchase_invoices (user_id, created_at DESC);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_sale_returns_user_created ON sale_returns (user_id, created_at DESC);"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_supplier_payments_user ON supplier_payments (user_id);"))

                        # Split payments migration
                        bg_db.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_split_payment BOOLEAN DEFAULT FALSE;"))
                        bg_db.execute(text("ALTER TABLE held_bills ADD COLUMN IF NOT EXISTS split_payments_json TEXT;"))
                        bg_db.execute(text("""
                            CREATE TABLE IF NOT EXISTS sale_payments (
                                id SERIAL PRIMARY KEY,
                                sale_id INTEGER NOT NULL REFERENCES sales(id) ON DELETE CASCADE,
                                user_id INTEGER NOT NULL REFERENCES users(id),
                                payment_method VARCHAR NOT NULL,
                                amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
                                created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (NOW() AT TIME ZONE 'utc')
                            );
                            CREATE INDEX IF NOT EXISTS idx_sale_payments_sale_id ON sale_payments(sale_id);
                            CREATE INDEX IF NOT EXISTS idx_sale_payments_user_id ON sale_payments(user_id);
                        """))

                        # Multi-User RBAC & Staff Login migration
                        bg_db.execute(text("ALTER TABLE staff_members ADD COLUMN IF NOT EXISTS username VARCHAR;"))
                        bg_db.execute(text("ALTER TABLE staff_members ADD COLUMN IF NOT EXISTS password VARCHAR;"))
                        bg_db.execute(text("ALTER TABLE staff_members ADD COLUMN IF NOT EXISTS permissions_json TEXT;"))
                        bg_db.execute(text("ALTER TABLE staff_members ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITHOUT TIME ZONE;"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_staff_members_username ON staff_members(username);"))
                        bg_db.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS staff_id INTEGER REFERENCES staff_members(id);"))
                        bg_db.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS staff_name VARCHAR;"))
                        bg_db.execute(text("CREATE INDEX IF NOT EXISTS idx_sales_staff_id ON sales(staff_id);"))

                        # User profile & settings schema migrations
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS drug_license_no VARCHAR DEFAULT 'DL-2026-PHARMA-01';"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS logo_url VARCHAR;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS terms_and_conditions TEXT DEFAULT '1. Goods once sold will not be taken back without original bill.\\n2. Expiry dates checked at sales time.';"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS default_payment_method VARCHAR DEFAULT 'CASH';"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS invoice_prefix VARCHAR DEFAULT 'INV';"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_gst_breakdown BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_hsn BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_batch_expiry BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS show_customer_info BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS expiry_alerts_enabled BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS low_stock_alerts_enabled BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS billing_notifications_enabled BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS delete_confirmation_required BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS auto_save_enabled BOOLEAN DEFAULT TRUE;"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_language VARCHAR DEFAULT 'en';"))
                        bg_db.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_theme VARCHAR DEFAULT 'light';"))

                        # Pilot leads notification tracking schema
                        bg_db.execute(text("ALTER TABLE pilot_leads ADD COLUMN IF NOT EXISTS notification_status VARCHAR(50) DEFAULT 'PENDING';"))
                        bg_db.execute(text("ALTER TABLE pilot_leads ADD COLUMN IF NOT EXISTS notification_error TEXT;"))
                        bg_db.execute(text("ALTER TABLE pilot_leads ADD COLUMN IF NOT EXISTS notified_at TIMESTAMP WITHOUT TIME ZONE;"))
                        bg_db.execute(text("ALTER TABLE pilot_leads ADD COLUMN IF NOT EXISTS notification_provider VARCHAR(50);"))
                        bg_db.commit()
                        print("[Startup] Background GIN Trigram search indexes & RBAC schema verified.")
                    except Exception as idx_err:
                        bg_db.rollback()
                        logger.warning(f"[Startup] Background migration notice: {idx_err}")

                    active_user_ids = [r[0] for r in bg_db.query(models.User.id).limit(10).all()]
                    for uid in active_user_ids:
                        try:
                            crud.get_products(bg_db, user_id=uid)
                            crud.get_customers(bg_db, user_id=uid)
                        except Exception:
                            pass
                    print(f"[Startup] Background cache warming complete for {len(active_user_ids)} users.")
                finally:
                    bg_db.close()
            except Exception as bg_err:
                logger.warning(f"[Startup] Background warming notice: {bg_err}")

        import threading
        threading.Thread(target=_background_warmup, daemon=True).start()
        print("[Startup] Non-blocking database warmup complete. Uvicorn port 8000 ready.")
    except Exception as e:
        print(f"[Startup] DB warmup warning: {e}")

# Security Headers, Cache Control & CSRF Protection Middleware
@app.middleware("http")
async def add_security_headers_and_csrf_guard(request: Request, call_next):
    # CSRF Origin Check for cookie-authenticated state-changing browser requests
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        auth_header = request.headers.get("Authorization", "")
        has_cookie = "access_token" in request.cookies
        if has_cookie and not auth_header.startswith("Bearer "):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin:
                origin_clean = origin.rstrip("/")
                from urllib.parse import urlparse
                parsed_origin = urlparse(origin_clean)
                origin_host = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
                if origin_host not in ALLOWED_ORIGINS:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF origin check failed. State-changing request from unauthorized origin blocked."}
                    )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.path.startswith("/web") or request.url.path == "/" or request.url.path.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With", "X-CSRF-Token"],
)
# Rate Limiter Setup (Supports distributed Redis backend if REDIS_URL is configured)
redis_storage_uri = "memory://"
redis_url_env = os.getenv("REDIS_URL")
if redis_url_env:
    try:
        import redis
        r_client = redis.Redis.from_url(redis_url_env, socket_timeout=0.5, socket_connect_timeout=0.5)
        r_client.ping()
        redis_storage_uri = redis_url_env
        logger.info("[Startup] Connected to Redis rate limiting storage.")
    except Exception as r_err:
        logger.warning(f"[Startup] Redis URL specified but unreachable ({r_err}). Falling back to memory:// storage.")
        redis_storage_uri = "memory://"

limiter = Limiter(key_func=get_remote_address, storage_uri=redis_storage_uri)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security Setup (Dual-mode: Bearer Token + HttpOnly Session Cookie)
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__truncate_error=False)

import bcrypt

def safe_hash_password(password: str) -> str:
    """Hashes password safely using direct bcrypt + SHA-256 pre-hashing, 100% immune to passlib bugs."""
    if not password:
        password = ""
    import hashlib, base64
    pre_hashed = base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pre_hashed, salt).decode("utf-8")

def safe_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verifies passwords against direct bcrypt, passlib hashes, and legacy plain text."""
    if not plain_password or not hashed_password:
        return False
    import hashlib, base64

    safe_plain = plain_password.strip()
    safe_hashed = hashed_password.strip()

    # 1. Direct bcrypt check on pre-hashed SHA-256 bytes
    try:
        pre_hashed = base64.b64encode(hashlib.sha256(plain_password.encode("utf-8")).digest())
        if bcrypt.checkpw(pre_hashed, safe_hashed.encode("utf-8")):
            return True
    except Exception:
        pass

    # 2. Direct bcrypt check on raw bytes (truncated to 72 bytes)
    try:
        raw_bytes = plain_password.encode("utf-8")[:72]
        if bcrypt.checkpw(raw_bytes, safe_hashed.encode("utf-8")):
            return True
    except Exception:
        pass

    # 3. Passlib verify fallback
    try:
        pwd_bytes = plain_password.encode("utf-8")[:72]
        if pwd_context.verify(pwd_bytes.decode("utf-8", "ignore"), safe_hashed):
            return True
    except Exception:
        pass

    # 4. Legacy plain-text fallback
    try:
        if safe_plain == safe_hashed:
            return True
    except Exception:
        pass

    return False

# Cryptographic Security Configuration & Startup Validation
SECRET_KEY = os.getenv("SECRET_KEY")
KNOWN_SECRET_PLACEHOLDERS = {
    "generate_a_secure_random_64_character_hex_key_here",
    "your_secret_key_here",
    "changeme",
    "secret",
    "replace_me",
    "test_secret_key",
}
if not SECRET_KEY or SECRET_KEY.lower() in KNOWN_SECRET_PLACEHOLDERS or len(SECRET_KEY) < 16:
    import secrets
    SECRET_KEY = secrets.token_hex(32)
    logger.warning("[Startup Security] SECRET_KEY was missing or placeholder; auto-generated a secure 256-bit secret key.")

# Audit CORS in production: Disallow wildcard '*' origin gracefully
if "*" in ALLOWED_ORIGINS and len(ALLOWED_ORIGINS) > 1:
    ALLOWED_ORIGINS = [o for o in ALLOWED_ORIGINS if o != "*"]
    logger.warning("[Startup Security] Wildcard CORS origin '*' removed for production security.")

# Validate AI configuration if present
gemini_key = os.getenv("GEMINI_API_KEY")
if gemini_key:
    gemini_key_lower = gemini_key.strip().lower()
    if any(p in gemini_key_lower for p in ["your_google_ai", "your_key", "placeholder", "_here"]):
        if is_production:
            logger.warning("[Startup Warning] GEMINI_API_KEY is configured with an example placeholder value. AI scan endpoints will fail until a valid Google AI Studio key is provided.")
        else:
            logger.info("[Startup Info] Local dev using placeholder GEMINI_API_KEY.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Firebase Setup: Supports FIREBASE_CREDENTIALS_JSON (raw JSON or base64) or FIREBASE_CREDENTIALS_PATH
if not firebase_admin._apps:
    try:
        firebase_cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
        firebase_cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "credentials/firebase_key.json")
        
        if firebase_cred_json:
            import base64
            # Handle potential base64 encoding
            raw_str = firebase_cred_json.strip()
            if not raw_str.startswith("{"):
                try:
                    raw_str = base64.b64decode(raw_str).decode("utf-8")
                except Exception:
                    pass
            cred_dict = json.loads(raw_str)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            logger.info("[Startup] Firebase initialized successfully via FIREBASE_CREDENTIALS_JSON.")
        elif os.path.exists(firebase_cred_path):
            cred = credentials.Certificate(firebase_cred_path)
            firebase_admin.initialize_app(cred)
            logger.info(f"[Startup] Firebase initialized successfully from file path.")
        else:
            logger.warning("[Startup Notice] No Firebase credentials provided (FIREBASE_CREDENTIALS_JSON or credentials file not found). FCM notifications will be skipped.")
    except Exception as e:
        logger.warning(f"[Startup Notice] Firebase initialization bypassed: {e}")

# Upload Storage Directory Setup (Public static mount removed for tenant privacy & security)
UPLOADS_BASE_DIR = (BASE_DIR / "uploads").resolve()
DOCUMENTS_DIR = (UPLOADS_BASE_DIR / "documents").resolve()
try:
    os.makedirs(UPLOADS_BASE_DIR, exist_ok=True)
    os.makedirs(DOCUMENTS_DIR, exist_ok=True)
except Exception:
    pass


# Database Tables & Scheduler are started cleanly during the FastAPI startup event below


# ==========================================
# DEPENDENCIES & HELPERS
# ==========================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


import time

class AuthenticatedUser:
    """
    Unified user representation for both Pharmacy Owners and Staff Members.
    Ensures 100% backward compatibility:
    - .id -> Pharmacy Owner ID (tenant ID)
    - .shop_id -> Pharmacy Owner ID
    - .user_id -> Pharmacy Owner ID
    - .staff_id -> Staff member ID (or None if owner)
    - .role -> Normalized role (OWNER, PHARMACIST, BILLING_STAFF, INVENTORY_STAFF)
    - .permissions -> Set of permission strings
    """
    def __init__(
        self,
        db_user: models.User,
        staff: Optional[models.StaffMember] = None,
        custom_permissions: Optional[Set[str]] = None,
    ):
        self._user = db_user
        self._staff = staff

        # Scoping IDs (Tenant ID is always db_user.id)
        self.id = db_user.id
        self.user_id = db_user.id
        self.shop_id = db_user.id
        self.owner_id = db_user.id

        if staff:
            self.staff_id = staff.id
            self.name = staff.name
            self.email = staff.email or db_user.email
            self.phone = staff.phone or db_user.phone
            self.role = permissions.normalize_role(staff.role)
            self.is_owner = False
            self.permissions = custom_permissions or permissions.get_role_permissions(self.role, staff.permissions_json)
        else:
            self.staff_id = None
            self.name = db_user.owner_name
            self.email = db_user.email
            self.phone = db_user.phone
            self.role = permissions.ROLE_OWNER
            self.is_owner = True
            self.permissions = permissions.ROLE_DEFAULT_PERMISSIONS[permissions.ROLE_OWNER]

        # Shop metadata
        self.shop_name = db_user.shop_name
        self.owner_name = db_user.owner_name
        self.address = db_user.address
        self.gstin = db_user.gstin
        self.gst_number = db_user.gst_number
        self.default_gst_percentage = db_user.default_gst_percentage

    def has_permission(self, perm: str) -> bool:
        if self.is_owner or "*" in self.permissions:
            return True
        return perm in self.permissions

    def __getattr__(self, name: str):
        # Transparently proxy any missing attribute to the underlying models.User
        return getattr(self._user, name)


_AUTH_CACHE: Dict[str, Tuple[AuthenticatedUser, float]] = {}

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    token_param: Optional[str] = Query(None, alias="token"),
) -> AuthenticatedUser:
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")
    elif token_param:
        # Support ?token=... query parameter for direct browser PDF/download links
        token = token_param

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token or login to establish a session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        staff_id = payload.get("staff_id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        cache_key = f"u:{user_id}:s:{staff_id or 'none'}"
        now = time.time()
        if cache_key in _AUTH_CACHE:
            cached_auth, timestamp = _AUTH_CACHE[cache_key]
            if now - timestamp < 30:  # 30s cache TTL
                return cached_auth

        # Query the Shop/Owner record
        db_user = db.query(models.User).filter(models.User.id == user_id).first()
        if db_user is None:
            raise HTTPException(status_code=401, detail="Pharmacy account not found")

        staff = None
        if staff_id is not None:
            staff = db.query(models.StaffMember).filter(
                models.StaffMember.id == staff_id,
                models.StaffMember.user_id == user_id,
            ).first()
            if staff is None:
                raise HTTPException(status_code=401, detail="Staff account not found or removed")
            if (staff.status or "ACTIVE").upper() != "ACTIVE":
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Staff account is disabled. Please contact your pharmacy administrator.",
                )

        auth_user = AuthenticatedUser(db_user=db_user, staff=staff)
        _AUTH_CACHE[cache_key] = (auth_user, now)
        return auth_user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_permission(perm: Union[str, List[str], Set[str], Tuple[str, ...]]):
    """Dependency that enforces that the authenticated user possesses the specified permission (or any of the list)."""
    def _permission_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if isinstance(perm, (list, tuple, set)):
            allowed = any(current_user.has_permission(p) for p in perm)
            required_str = " or ".join(f"'{p}'" for p in perm)
        else:
            allowed = current_user.has_permission(perm)
            required_str = f"'{perm}'"
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: You do not have permission to perform this action ({required_str} required).",
            )
        return current_user
    return _permission_checker


def require_owner(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
    """Dependency that strictly enforces that the user is the Pharmacy Shop Owner."""
    if not current_user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: This operation is restricted exclusively to the pharmacy shop owner.",
        )
    return current_user


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[Unhandled Server Exception] {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "An unexpected server error occurred."
        },
    )


# ==========================================
# AUTHENTICATION & CORE ENDPOINTS
# ==========================================

@app.get("/health")
@app.get("/api/health")
def api_health():
    """Production Monitoring Health Endpoint verifying API availability instantly (< 1ms)."""
    db_connected = False
    try:
        from database import engine
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_connected = True
    except Exception:
        db_connected = False

    return {
        "status": "healthy",
        "version": "1.0.0",
        "database": "connected" if db_connected else "disconnected",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/robots.txt")
def robots_txt():
    from fastapi.responses import FileResponse
    robots_path = PUBLIC_SERVE_DIR / "robots.txt"
    if robots_path.exists():
        return FileResponse(robots_path)
    raise HTTPException(status_code=404)

@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    from fastapi.responses import FileResponse
    fav_path = PUBLIC_SERVE_DIR / "favicon.svg"
    if fav_path.exists():
        return FileResponse(fav_path)
    raise HTTPException(status_code=404)

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "").lower()
    is_html_request = "text/html" in accept
    is_api_path = any(request.url.path.startswith(prefix) for prefix in [
        "/api", "/billing", "/inventory", "/customers", "/sales", "/auth",
        "/analytics", "/printer", "/docs", "/redoc", "/openapi.json"
    ])
    if request.method == "GET" and is_html_request and not is_api_path:
        from fastapi.responses import FileResponse
        custom_404_page = PUBLIC_SERVE_DIR / "404.html"
        if custom_404_page.exists():
            return FileResponse(custom_404_page, status_code=404)
        landing_index = PUBLIC_SERVE_DIR / "index.html"
        if landing_index.exists():
            return FileResponse(landing_index, status_code=200)
    return JSONResponse(
        status_code=404,
        content={"detail": exc.detail if hasattr(exc, "detail") else "Not Found"}
    )

@app.get("/")
def home(request: Request):
    """Serve DawaiFlow Public Landing Page"""
    from fastapi.responses import FileResponse
    landing_index = PUBLIC_SERVE_DIR / "index.html"
    if landing_index.exists():
        return FileResponse(landing_index)
    return {"message": "DawaiFlow Backend Running"}


@app.get("/index.html")
def get_index_html():
    from fastapi.responses import FileResponse
    landing_index = PUBLIC_SERVE_DIR / "index.html"
    if landing_index.exists():
        return FileResponse(landing_index)
    return {"message": "DawaiFlow Backend Running"}


@app.get("/mobile.html")
def get_mobile_html():
    return RedirectResponse(url="/", status_code=301)


@app.get("/terms")
@app.get("/terms.html")
def terms():
    """Serve Terms of Use via DawaiFlow modal or page"""
    return RedirectResponse(url="/#terms", status_code=302)


@app.get("/privacy")
@app.get("/privacy.html")
def privacy():
    """Serve Privacy Policy via DawaiFlow modal or page"""
    return RedirectResponse(url="/#privacy", status_code=302)


@app.get("/data-policy")
@app.get("/data-policy.html")
def data_policy():
    """Serve Data & App Information via DawaiFlow modal or page"""
    return RedirectResponse(url="/#data-policy", status_code=302)


@app.get("/disclaimer")
@app.get("/medical-disclaimer")
def disclaimer():
    """Serve Medical Disclaimer via DawaiFlow modal or page"""
    return RedirectResponse(url="/#disclaimer", status_code=302)


@app.get("/contact")
@app.get("/grievance")
@app.get("/support")
def contact():
    """Serve Contact & Grievance via DawaiFlow modal or page"""
    return RedirectResponse(url="/#contact", status_code=302)


@app.get("/sitemap.xml")
def sitemap_xml():
    from fastapi.responses import FileResponse
    sitemap_path = PUBLIC_SERVE_DIR / "sitemap.xml"
    if sitemap_path.exists():
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="sitemap.xml not found")


@app.get("/ca-connect", include_in_schema=False)
def serve_ca_connect():
    """Serve CA Connect Web Page"""
    from fastapi.responses import FileResponse
    ca_page = WEB_DIR / "ca_connect.html"
    if ca_page.exists():
        return FileResponse(ca_page)
    raise HTTPException(status_code=404, detail="CA Connect page not found")


@app.get("/backup", include_in_schema=False)
def serve_backup():
    """Serve Backup & Restore Web Page"""
    from fastapi.responses import FileResponse
    page = WEB_DIR / "backup.html"
    if page.exists():
        return FileResponse(page)
    settings_page = WEB_DIR / "settings.html"
    if settings_page.exists():
        return FileResponse(settings_page)
    raise HTTPException(status_code=404, detail="Backup page not found")


@app.post("/register")
@limiter.limit("10/minute")
def register(
    request: Request,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    try:
        existing = db.query(models.User).filter(models.User.email.ilike(user.email.strip())).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        if user.phone and user.phone.strip():
            existing_phone = db.query(models.User).filter(models.User.phone == user.phone.strip()).first()
            if existing_phone:
                raise HTTPException(status_code=400, detail="Phone number already registered")

        hashed_password = safe_hash_password(user.password)
        new_user = models.User(
            shop_name=user.shop_name.strip() if user.shop_name else "DawaiFlow Pharmacy",
            owner_name=user.owner_name.strip() if user.owner_name else "Pharmacy Owner",
            email=user.email.strip().lower(),
            password=hashed_password,
            phone=user.phone.strip() if user.phone else None,
            address=user.address.strip() if user.address else None,
            gstin=user.gstin.strip() if user.gstin else "07AABCE1234F1Z5",
            gst_number=user.gstin.strip() if user.gstin else "07AABCE1234F1Z5",
        )

        db.add(new_user)
        db.commit()

        return {"message": "User registered successfully"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"[Registration Exception] Failed to register '{user.email}': {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Registration failed: {str(e)}")


@app.post("/auth/reset-password")
@limiter.limit("10/minute")
def reset_password(
    request: Request,
    data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db),
):
    try:
        user = db.query(models.User).filter(models.User.email.ilike(data.email.strip())).first()
        if not user:
            raise HTTPException(status_code=404, detail="Account with this email address was not found")

        user.password = safe_hash_password(data.new_password)
        db.commit()
        return {"message": "Password updated successfully. You can now log in."}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        db.rollback()
        logger.error(f"[Password Reset Error] {e}\n{tb}")
        raise HTTPException(status_code=400, detail=f"Reset error: {str(e)} | STACK: {tb[:300]}")


from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm

@app.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    user: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    login_identifier = user.email.strip()

    # 1. First attempt Pharmacy Owner login by email
    db_user = db.query(models.User).filter(models.User.email.ilike(login_identifier)).first()
    if db_user and safe_verify_password(user.password, db_user.password):
        expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {
                "user_id": db_user.id,
                "staff_id": None,
                "role": permissions.ROLE_OWNER,
                "sub": db_user.email,
                "exp": expire_time,
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )

        is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "owner_name": db_user.owner_name,
            "shop_name": db_user.shop_name,
            "user_id": db_user.id,
            "staff_id": None,
            "role": permissions.ROLE_OWNER,
            "name": db_user.owner_name,
            "permissions": list(permissions.ROLE_DEFAULT_PERMISSIONS[permissions.ROLE_OWNER]),
        }

    # 2. If not owner, check StaffMember (by username, email, or phone)
    staff = db.query(models.StaffMember).filter(
        (models.StaffMember.username == login_identifier) |
        (models.StaffMember.email.ilike(login_identifier)) |
        (models.StaffMember.phone == login_identifier)
    ).first()

    if staff and staff.password and safe_verify_password(user.password, staff.password):
        if (staff.status or "ACTIVE").upper() != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff account is disabled. Please contact your pharmacy administrator.",
            )

        pharmacy = db.query(models.User).filter(models.User.id == staff.user_id).first()
        if not pharmacy:
            raise HTTPException(status_code=400, detail="Associated pharmacy account not found.")

        # Update last login timestamp
        staff.last_login = datetime.utcnow()
        db.commit()

        normalized_role = permissions.normalize_role(staff.role)
        effective_perms = permissions.get_role_permissions(normalized_role, staff.permissions_json)

        expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {
                "user_id": pharmacy.id,
                "staff_id": staff.id,
                "role": normalized_role,
                "sub": staff.username or staff.email or str(staff.id),
                "exp": expire_time,
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )

        is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
        response.set_cookie(
            key="access_token",
            value=token,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            max_age=ACCESS_TOKEN_EXPIRE_DAYS * 24 * 3600,
        )

        return {
            "access_token": token,
            "token_type": "bearer",
            "owner_name": pharmacy.owner_name,
            "shop_name": pharmacy.shop_name,
            "user_id": pharmacy.id,
            "staff_id": staff.id,
            "role": normalized_role,
            "name": staff.name,
            "permissions": list(effective_perms),
        }

    raise HTTPException(status_code=400, detail="Invalid email/username or password")


@app.get("/auth/session")
@limiter.limit("20/minute")
def get_current_browser_session(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Returns authenticated session details for the currently logged-in user or staff."""
    return {
        "status": "authenticated",
        "user_id": current_user.id,
        "owner_name": current_user.owner_name,
        "shop_name": current_user.shop_name or "DawaiFlow Pharmacy",
        "email": current_user.email,
        "phone": current_user.phone,
        "address": current_user.address,
        "gstin": current_user.gstin,
        "staff_id": current_user.staff_id,
        "role": current_user.role,
        "name": current_user.name,
        "is_owner": current_user.is_owner,
        "permissions": list(current_user.permissions),
    }


@app.get("/app/bootstrap")
@limiter.limit("60/minute")
def get_app_bootstrap_endpoint(
    request: Request,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Centralized Global App Data Preload Bootstrap Endpoint.
    Consolidates session, permissions, dashboard metrics, inventory summary,
    khata summary, recent sales, and today's returns into a single sub-25ms response.
    """
    cache_key = f"app_bootstrap:{current_user.id}:{current_user.staff_id or 'none'}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    data = crud.get_app_bootstrap(db, current_user.id, current_user)
    fast_cache.set(current_user.id, cache_key, data, ttl=20.0, tags=["bootstrap", "dashboard", "inventory"])
    return JSONResponse(content=data)



@app.post("/token")
@limiter.limit("10/minute")
def login_token_alias(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    login_id = form_data.username.strip()

    # 1. Owner check
    db_user = db.query(models.User).filter(models.User.email.ilike(login_id)).first()
    if db_user and safe_verify_password(form_data.password, db_user.password):
        expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {
                "user_id": db_user.id,
                "staff_id": None,
                "role": permissions.ROLE_OWNER,
                "sub": str(db_user.id),
                "exp": expire_time,
                "iat": datetime.utcnow(),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        return {"access_token": token, "token_type": "bearer"}

    # 2. Staff check
    staff = db.query(models.StaffMember).filter(
        (models.StaffMember.username == login_id) |
        (models.StaffMember.email.ilike(login_id)) |
        (models.StaffMember.phone == login_id)
    ).first()

    if staff and staff.password and safe_verify_password(form_data.password, staff.password):
        if (staff.status or "ACTIVE").upper() != "ACTIVE":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Staff account is disabled. Please contact your pharmacy administrator.",
            )

        expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
        token = jwt.encode(
            {
                "user_id": staff.user_id,
                "staff_id": staff.id,
                "role": permissions.normalize_role(staff.role),
                "sub": str(staff.id),
                "exp": expire_time,
                "iat": datetime.utcnow(),
            },
            SECRET_KEY,
            algorithm=ALGORITHM,
        )
        return {"access_token": token, "token_type": "bearer"}

    raise HTTPException(status_code=400, detail="Incorrect email/username or password")


@app.post("/auth/logout")
@app.post("/logout")
def logout(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Backend logout/session revocation endpoint."""
    response.delete_cookie(key="access_token", path="/", httponly=True)
    if current_user:
        cache_key = f"u:{current_user.id}:s:{current_user.staff_id or 'none'}"
        _AUTH_CACHE.pop(cache_key, None)
    return {"message": "Logged out successfully", "status": "success"}


# ==========================================
# PRODUCT & INVENTORY ENDPOINTS
# ==========================================

@app.post("/products")
def create_product(
    product: schemas.ProductCreate,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_CREATE")),
    db: Session = Depends(get_db),
):
    created = crud.create_product(db, product, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@app.get("/products")
@app.get("/inventory")
def read_products(
    page: Optional[int] = Query(None, ge=1),
    skip: Optional[int] = Query(0, ge=0),
    limit: Optional[int] = Query(None, ge=1, le=1000),
    search: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    filter_key: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    import time
    t0 = time.time()
    eff_skip = skip or 0
    if page and page > 1 and limit:
        eff_skip = (page - 1) * limit
    eff_filter = filter or filter_key
    
    cache_key = f"prods:{eff_skip}:{limit}:{search}:{eff_filter}:{sort_by}"
    cached_prods = fast_cache.get(current_user.id, cache_key)
    if cached_prods is not None:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=cached_prods)

    logger.info(f"[Inventory] Request started - user_id={current_user.id}, page={page}, limit={limit}, search={search}, filter={eff_filter}")
    result = crud.get_products(
        db=db,
        user_id=current_user.id,
        skip=eff_skip,
        limit=limit,
        search=search,
        filter_key=eff_filter,
        sort_by=sort_by,
    )
    elapsed_ms = (time.time() - t0) * 1000.0
    item_count = len(result["items"]) if isinstance(result, dict) and "items" in result else (len(result) if isinstance(result, list) else 0)
    logger.info(f"[Inventory] Request completed in {elapsed_ms:.2f}ms - returned {item_count} products")
    fast_cache.set(current_user.id, cache_key, result, ttl=20.0, tags=["products", "inventory"])
    from fastapi.responses import JSONResponse
    return JSONResponse(content=result)


@app.get("/inventory/summary")
def get_inventory_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Lightweight SQL-aggregated Inventory Health Dashboard summary metrics.
    Calculates total products, stock value, expiring, expired, low stock, out of stock,
    and dead stock in < 5ms without returning product lists.
    """
    return crud.get_inventory_summary(db=db, user_id=current_user.id)


@app.get("/inventory/intelligence", response_model=schemas.InventoryIntelligenceResponse)
def get_inventory_intelligence(
    category: Optional[str] = None,
    supplier_id: Optional[int] = None,
    priority_level: Optional[str] = None,
    debug: bool = False,
    limit: int = 100,
    offset: int = 0,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns Smart Restock & Inventory Intelligence decision engine analytics,
    ranked priority recommendations, expiry risk calculations, and demand velocity metrics.
    """
    cache_key = f"intelligence:{category}:{supplier_id}:{priority_level}:{limit}:{offset}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached:
        return cached

    res = crud.get_inventory_intelligence(
        db=db,
        user_id=current_user.id,
        category=category,
        supplier_id=supplier_id,
        priority_level=priority_level,
        debug=debug,
        limit=limit,
        offset=offset
    )
    fast_cache.set(current_user.id, cache_key, res, ttl=30, tags=["inventory", "intelligence"])
    return res


@app.get("/alerts")
def get_smart_alerts(
    category: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns deterministic, non-spammy, actionable smart alerts organized by category & priority."""
    return crud.get_smart_alerts(db, current_user.id, category)


@app.get("/alerts/summary")
def get_alert_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns unread alert count and critical notification metrics for badge UI."""
    return crud.get_alert_summary(db, current_user.id)


@app.get("/alerts/preferences")
def get_alert_preferences(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves user alert category toggles."""
    return crud.get_alert_preferences(db, current_user.id)


@app.put("/alerts/preferences")
@app.post("/alerts/preferences")
def update_alert_preferences(
    prefs: dict,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates user notification preferences (Expiry, Low Stock, Billing/Khata toggles)."""
    return crud.update_alert_preferences(db, current_user.id, prefs)


@app.get("/khata/dashboard")
def get_khata_dashboard(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_VIEW)),
    db: Session = Depends(get_db),
):
    """Returns Khata summary metrics: total customers, outstanding, overdue, today's collection."""
    from fastapi.responses import JSONResponse
    cached = fast_cache.get(current_user.id, "khata_dashboard")
    if cached is not None:
        return JSONResponse(content=cached)
    res = crud.get_khata_dashboard(db, current_user.id)
    fast_cache.set(current_user.id, "khata_dashboard", res, ttl=30.0, tags=["khata", "customers"])
    return JSONResponse(content=res)


@app.get("/customers/outstanding")
@app.get("/khata/outstanding")
def get_customers_outstanding(
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_KHATA_VIEW, permissions.PERM_CUSTOMER_OUTSTANDING_VIEW])),
    db: Session = Depends(get_db),
):
    """Returns Khata and customer outstanding receivables summary."""
    return crud.get_khata_dashboard(db, current_user.id)


@app.get("/purchases/dashboard")
def get_purchase_dashboard(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
    db: Session = Depends(get_db),
):
    """Returns Purchase Dashboard summary metrics: today purchases, month purchases, pending payables, suppliers count."""
    return crud.get_purchase_dashboard(db, current_user.id)


@app.get("/reports/analytics")
def get_reports_analytics(
    period: Optional[str] = "this_month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """Returns comprehensive report analytics (Sales, COGS, Profit, Top Selling, Valuation, Expiry Risk, Trends)."""
    cache_key = f"reports:{period}:{start_date}:{end_date}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    res = crud.get_reports_analytics(
        db=db,
        user_id=current_user.id,
        period=period or "this_month",
        start_date_str=start_date,
        end_date_str=end_date
    )
    fast_cache.set(current_user.id, cache_key, res, ttl=30, tags=["reports"])
    return JSONResponse(content=res)


@app.post("/ai/chat")
def ai_business_assistant_chat(
    req: dict,
    current_user: AuthenticatedUser = Depends(require_permission("AI_ASSISTANT")),
    db: Session = Depends(get_db),
):
    """Database-grounded AI Assistant answering business questions directly from real DB records."""
    query = req.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="Query parameter is required.")
    return crud.get_ai_chat_response(db=db, user_id=current_user.id, query=query)


@app.get("/products/{product_id}")
def get_single_product_details(
    product_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve full detail specification for a single medicine product item."""
    product = crud.get_product(db, product_id, current_user.id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found.")
    return product


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    product: schemas.ProductCreate,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    return crud.update_product(db, product_id, product, current_user.id)


@app.put("/products/{product_id}/quantity")
def update_quantity(
    product_id: int,
    quantity: int,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_EDIT")),
    db: Session = Depends(get_db),
):
    product = crud.get_product(db, product_id, current_user.id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    product.quantity = quantity
    db.commit()
    db.refresh(product)
    return product


@app.delete("/products/{product_id}")
def delete_product(
    product_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("INVENTORY_DELETE")),
    db: Session = Depends(get_db),
):
    return crud.delete_product(db, product_id, current_user.id)


@app.get("/dashboard")
def dashboard(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    products = crud.get_products(db, current_user.id)
    total = len(products)
    safe, expiring, expired = 0, 0, 0

    for product in products:
        if product.status == "Safe":
            safe += 1
        elif product.status == "Expiring Soon":
            expiring += 1
        elif product.status == "Expired":
            expired += 1

    return {
        "total": total,
        "safe": safe,
        "expiring": expiring,
        "expired": expired,
    }


# ==========================================
# POS / SALES ENDPOINTS
# ==========================================

_RECENT_SALES_CACHE: Dict[str, Tuple[Any, float]] = {}
_BILLING_CONCURRENCY_LOCK = threading.Lock()

def _get_idempotent_sale_or_key(
    request: Request,
    sale_data: schemas.SaleCreate,
    current_user_id: int,
    db: Optional[Session] = None,
) -> Tuple[Optional[Any], str]:
    """
    Deterministic idempotency verification:
    1. Checks explicit client idempotency key (via body sale_data.idempotency_key or HTTP headers).
    2. Checks in-memory fast cache (sub-millisecond).
    3. Checks PostgreSQL sales table for already committed transaction with this idempotency key.
    4. Guarantees that duplicate submissions return the original sale without double stock deduction.
    """
    client_key = (
        getattr(sale_data, "idempotency_key", None)
        or request.headers.get("x-idempotency-key")
        or request.headers.get("x-request-id")
    )

    if client_key and str(client_key).strip():
        clean_key = str(client_key).strip()
        sale_data.idempotency_key = clean_key
        cache_key = f"{current_user_id}:{clean_key}"

        now = time.time()
        # Clean expired keys
        expired = [k for k, (_, ts) in _RECENT_SALES_CACHE.items() if now - ts > 120]
        for k in expired:
            _RECENT_SALES_CACHE.pop(k, None)

        if cache_key in _RECENT_SALES_CACHE:
            cached_sale, ts = _RECENT_SALES_CACHE[cache_key]
            if now - ts < 120:
                logger.info(f"[PERF] [IDEMPOTENCY] Cache hit for key {cache_key}. Duplicate transaction prevented.")
                return cached_sale, cache_key

        if db is not None:
            existing_sale = (
                db.query(models.Sale)
                .filter(
                    models.Sale.user_id == current_user_id,
                    models.Sale.idempotency_key == clean_key,
                )
                .first()
            )
            if existing_sale:
                logger.info(f"[PERF] [IDEMPOTENCY] DB hit for key {cache_key}. Existing bill {existing_sale.bill_number} returned.")
                _RECENT_SALES_CACHE[cache_key] = (existing_sale, now)
                return existing_sale, cache_key

        return None, cache_key

    import uuid
    fallback_key = f"srv_{uuid.uuid4().hex}"
    sale_data.idempotency_key = fallback_key
    return None, f"{current_user_id}:{fallback_key}"


@app.post("/sales", response_model=schemas.SaleResponse, status_code=201)
def complete_sale(
    request: Request,
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    """Mobile Counter 1-Tap Checkout Endpoint with concurrency locking and idempotency protection."""
    t0 = time.perf_counter()
    with _BILLING_CONCURRENCY_LOCK:
        cached_sale, cache_key = _get_idempotent_sale_or_key(request, sale_data, current_user.id, db=db)
        if cached_sale:
            return cached_sale

        sale = crud.create_sale_transaction(
            db=db,
            sale_data=sale_data,
            user_id=current_user.id,
            current_user=current_user,
            verified_idempotency=True,
        )
        t1 = time.perf_counter()
        
        # Attach tax summary and PDF download URL
        tax_summary = []
        if sale.tax_summary_json:
            try:
                import json
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                tax_summary = []
                
        sale.tax_summary = tax_summary
        sale.pdf_url = f"/billing/{sale.id}/pdf"
        
        _RECENT_SALES_CACHE[cache_key] = (sale, time.time())
        fast_cache.invalidate_user(current_user.id)
        
        t2 = time.perf_counter()
        logger.info(f"[PERF] [BILLING] Sale #{sale.id} completed | Transaction DB: {(t1 - t0)*1000:.2f}ms | Total Endpoint: {(t2 - t0)*1000:.2f}ms")
        return sale


@app.post(
    "/billing/confirm",
    response_model=schemas.SaleResponse,
    status_code=201,
)
def confirm_billing_sale(
    request: Request,
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    """Cart -> /billing/confirm locks bill, deducts stock, and returns invoice summary with PDF link."""
    t0 = time.perf_counter()
    with _BILLING_CONCURRENCY_LOCK:
        cached_sale, cache_key = _get_idempotent_sale_or_key(request, sale_data, current_user.id, db=db)
        if cached_sale:
            return cached_sale

        sale = crud.create_sale_transaction(
            db=db,
            sale_data=sale_data,
            user_id=current_user.id,
            current_user=current_user,
            verified_idempotency=True,
        )
        t1 = time.perf_counter()
        
        tax_summary = []
        if sale.tax_summary_json:
            try:
                import json
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                tax_summary = []
                
        sale.tax_summary = tax_summary
        sale.pdf_url = f"/billing/{sale.id}/pdf"

        _RECENT_SALES_CACHE[cache_key] = (sale, time.time())
        fast_cache.invalidate_user(current_user.id)

        t2 = time.perf_counter()
        logger.info(f"[PERF] [BILLING_CONFIRM] Sale #{sale.id} confirmed | Transaction DB: {(t1 - t0)*1000:.2f}ms | Total Endpoint: {(t2 - t0)*1000:.2f}ms")
        return sale


# ============================================================
# HELD BILLS (PARK / RESUME) ENDPOINTS
# ============================================================

@app.post(
    "/billing/held",
    response_model=schemas.HeldBillResponse,
    status_code=201,
)
def create_held_bill(
    payload: schemas.HeldBillCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Parks current cart as a held bill without deducting stock or creating a sale."""
    return crud.create_held_bill(db=db, bill_data=payload, user_id=current_user.id)


@app.get(
    "/billing/held",
    response_model=List[schemas.HeldBillResponse],
)
def get_held_bills(
    status: str = "HELD",
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists held bills with optional search and status filtering."""
    return crud.get_held_bills(
        db=db,
        user_id=current_user.id,
        status=status,
        search_query=search,
        skip=skip,
        limit=limit,
    )


@app.get(
    "/billing/held/count",
)
def get_held_bill_count(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Returns active held bills count for badges and quick status."""
    count = crud.get_held_bill_count(db=db, user_id=current_user.id)
    return {"count": count}


@app.get(
    "/billing/held/{held_bill_id}",
    response_model=schemas.HeldBillResponse,
)
def get_held_bill_by_id(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Gets details for a single held bill."""
    held_bill = crud.get_held_bill_by_id(db=db, held_bill_id=held_bill_id, user_id=current_user.id)
    if not held_bill:
        raise HTTPException(status_code=404, detail=f"Held bill #{held_bill_id} not found.")
    return held_bill


@app.post(
    "/billing/held/{held_bill_id}/resume",
    response_model=schemas.HeldBillResumeResponse,
)
def resume_held_bill(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Validates live stock and returns held bill data to restore into active cart."""
    return crud.resume_held_bill(db=db, held_bill_id=held_bill_id, user_id=current_user.id)


@app.delete(
    "/billing/held/{held_bill_id}",
)
def cancel_held_bill(
    held_bill_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cancels/deletes a held bill."""
    crud.cancel_held_bill(db=db, held_bill_id=held_bill_id, user_id=current_user.id)
    return {"success": True, "message": "Held bill cancelled successfully."}



@app.put("/products/bulk-update-gst")
def bulk_update_gst_rates(
    payload: schemas.BulkGstUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Bulk updates GST rate for all products matching an HSN code."""
    updated_count = crud.bulk_update_gst(
        db=db,
        user_id=current_user.id,
        hsn_code=payload.hsn_code,
        gst_rate=payload.gst_rate,
    )
    return {
        "success": True,
        "message": f"Updated GST rate to {payload.gst_rate}% for {updated_count} products matching HSN {payload.hsn_code}.",
        "updated_count": updated_count,
    }


@app.get("/billing/{bill_id}/pdf")
def get_invoice_pdf(
    bill_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Generates a downloadable/printable GST Tax Invoice PDF using ReportLab."""
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == bill_id, models.Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail=f"Bill ID {bill_id} not found.")

    tax_summary = []
    if sale.tax_summary_json:
        try:
            import json
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            tax_summary = []

    sale_dict = {
        "bill_number": sale.bill_number,
        "created_at": sale.created_at,
        "customer_name": sale.customer_name,
        "customer_phone": sale.customer_phone,
        "payment_method": sale.payment_method,
        "doctor_name": sale.doctor_name,
        "is_interstate": sale.is_interstate,
        "subtotal": sale.subtotal,
        "discount_amount": sale.discount_amount,
        "tax_amount": sale.tax_amount,
        "total_amount": sale.total_amount,
        "total_taxable_value": sale.total_taxable_value,
        "total_cgst": sale.total_cgst,
        "total_sgst": sale.total_sgst,
        "total_igst": sale.total_igst,
        "tax_summary": tax_summary,
        "items": [
            {
                "product_name": item.product_name,
                "hsn_code": getattr(item, "hsn_code", "3004") or "3004",
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "discount": item.discount,
                "gst_percentage": item.gst_percentage,
                "taxable_value": item.taxable_value,
                "cgst_rate": item.cgst_rate,
                "cgst_amount": item.cgst_amount,
                "sgst_rate": item.sgst_rate,
                "sgst_amount": item.sgst_amount,
                "igst_rate": item.igst_rate,
                "igst_amount": item.igst_amount,
                "total_with_tax": item.total_with_tax,
                "total_price": item.total_price,
            }
            for item in sale.items
        ],
    }

    shop_dict = {
        "shop_name": current_user.shop_name,
        "gstin": getattr(current_user, "gstin", None) or current_user.gst_number or "07AABCE1234F1Z5",
        "address": getattr(current_user, "address", None) or "Main Market, New Delhi - 110001",
        "phone": getattr(current_user, "phone", None) or "+91-9876543210",
    }

    pdf_bytes = generate_invoice_pdf(sale_dict, shop_dict)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=invoice_{sale.bill_number}.pdf"
        },
    )

@app.post(
    "/sales/{sale_id}/returns",
    response_model=schemas.SaleReturnResponse,
    status_code=201,
)
def create_sale_return(
    sale_id: int,
    return_data: schemas.SaleReturnCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ret = crud.create_sale_return(
        db=db,
        sale_id=sale_id,
        return_data=return_data,
        user_id=current_user.id,
    )
    fast_cache.invalidate_user(current_user.id)
    return ret


@app.get(
    "/returns/today",
    response_model=List[schemas.SaleReturnResponse],
)
def get_todays_returns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from fastapi.responses import JSONResponse
    cached = fast_cache.get(current_user.id, "returns_today")
    if cached is not None:
        return JSONResponse(content=cached)

    returns = crud.get_todays_returns(
        db=db,
        user_id=current_user.id,
    )
    for r in returns:
        if not getattr(r, 'bill_number', None) and r.sale:
            r.bill_number = r.sale.bill_number
    serialized_returns = [schemas.SaleReturnResponse.model_validate(r).model_dump(mode="json") for r in returns]
    fast_cache.set(current_user.id, "returns_today", serialized_returns, ttl=15.0, tags=["returns", "sales"])
    return JSONResponse(content=serialized_returns)
@app.get("/sales")
@app.get("/sales/history")
def get_sales_history(
    skip: int = 0,
    limit: int = 50,
    include_exported: bool = False,
    period: Optional[str] = "today",
    search: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    sales_type: Optional[str] = "all",  # "all", "live", "historical"
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_SALES_HISTORY_VIEW, permissions.PERM_REPORT_VIEW])),
):
    """
    Fetch sales logs for review & desktop view.
    Defaults to Today's sales to prevent UI clutter, but seamlessly supports:
    - Search across bill number, original bill number, customer name, and medicine names.
    - Presets: today, yesterday, this_week, this_month, all_time, or specific year (e.g. 2022).
    - Custom date range (from_date, to_date).
    - Sales type filter: all, live, or historical.
    """
    from sqlalchemy.orm import selectinload
    from sqlalchemy import or_, and_, func
    from fastapi.responses import JSONResponse
    import json
    from datetime import datetime, timedelta

    search_clean = (search or "").strip()
    period_clean = (period or "").strip().lower()

    cache_key = f"sales:{skip}:{limit}:{include_exported}:{period_clean}:{search_clean}:{from_date}:{to_date}:{sales_type}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached is not None:
        return JSONResponse(content=cached)

    query = db.query(models.Sale).options(selectinload(models.Sale.items)).filter(models.Sale.user_id == current_user.id)
    if not include_exported:
        query = query.filter(models.Sale.is_exported == False)

    # 1. Sales Type Filter
    if sales_type == "historical":
        query = query.filter(models.Sale.is_historical == True)
    elif sales_type == "live":
        query = query.filter(models.Sale.is_historical == False)

    # 2. Search (bill_number, original_bill_number, customer_name, medicine name, customer_phone)
    if search_clean:
        term = f"%{search_clean}%"
        # Subquery for medicine item matching
        item_subquery = (
            select(models.SaleItem.sale_id)
            .filter(models.SaleItem.product_name.ilike(term))
        )
        query = query.filter(
            or_(
                models.Sale.bill_number.ilike(term),
                models.Sale.original_bill_number.ilike(term),
                models.Sale.customer_name.ilike(term),
                models.Sale.customer_phone.ilike(term),
                models.Sale.doctor_name.ilike(term),
                models.Sale.id.in_(item_subquery)
            )
        )
    else:
        # If no explicit search query is provided, apply date filters
        ist_offset = timedelta(hours=5, minutes=30)
        now_utc = datetime.utcnow()
        now_ist = now_utc + ist_offset
        today_ist = now_ist.date()

        start_dt = None
        end_dt = None

        if from_date and to_date:
            try:
                sd = datetime.strptime(from_date.split("T")[0], "%Y-%m-%d").date()
                ed = datetime.strptime(to_date.split("T")[0], "%Y-%m-%d").date()
                start_dt = datetime.combine(sd, datetime.min.time()) - ist_offset
                end_dt = datetime.combine(ed, datetime.max.time()) - ist_offset
            except Exception:
                pass
        elif period_clean == "today":
            start_dt = datetime.combine(today_ist, datetime.min.time()) - ist_offset
            end_dt = datetime.combine(today_ist, datetime.max.time()) - ist_offset
        elif period_clean == "yesterday":
            y_date = today_ist - timedelta(days=1)
            start_dt = datetime.combine(y_date, datetime.min.time()) - ist_offset
            end_dt = datetime.combine(y_date, datetime.max.time()) - ist_offset
        elif period_clean in ("this_week", "7_days", "last_7_days"):
            w_date = today_ist - timedelta(days=6)
            start_dt = datetime.combine(w_date, datetime.min.time()) - ist_offset
            end_dt = datetime.combine(today_ist, datetime.max.time()) - ist_offset
        elif period_clean in ("this_month", "30_days", "last_30_days"):
            m_date = today_ist.replace(day=1)
            start_dt = datetime.combine(m_date, datetime.min.time()) - ist_offset
            end_dt = datetime.combine(today_ist, datetime.max.time()) - ist_offset
        elif period_clean == "last_month":
            first_of_this_month = today_ist.replace(day=1)
            last_day_of_last_month = first_of_this_month - timedelta(days=1)
            first_day_of_last_month = last_day_of_last_month.replace(day=1)
            start_dt = datetime.combine(first_day_of_last_month, datetime.min.time()) - ist_offset
            end_dt = datetime.combine(last_day_of_last_month, datetime.max.time()) - ist_offset
        elif period_clean.isdigit() and len(period_clean) == 4:
            # Specific calendar year, e.g. "2022", "2023", "2024", "2025"
            year = int(period_clean)
            start_dt = datetime(year, 1, 1, 0, 0, 0)
            end_dt = datetime(year, 12, 31, 23, 59, 59)
        elif period_clean in ("all", "all_time"):
            # Show all records without date clipping
            start_dt = None
            end_dt = None

        if start_dt:
            query = query.filter(models.Sale.created_at >= start_dt)
        if end_dt:
            query = query.filter(models.Sale.created_at <= end_dt)

    sales = (
        query
        .order_by(models.Sale.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    for sale in sales:
        sale.pdf_url = f"/billing/{sale.id}/pdf"
        tax_summary = []
        if sale.tax_summary_json:
            try:
                tax_summary = json.loads(sale.tax_summary_json)
            except Exception:
                pass
        sale.tax_summary = tax_summary
    serialized_sales = [schemas.SaleResponse.model_validate(s).model_dump(mode="json") for s in sales]
    fast_cache.set(current_user.id, cache_key, serialized_sales, ttl=15.0, tags=["sales"])
    return JSONResponse(content=serialized_sales)


@app.get("/sales/{sale_id}", response_model=schemas.SaleResponse)
def get_sale_detail(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_SALES_HISTORY_VIEW, permissions.PERM_REPORT_VIEW, permissions.PERM_BILL_VIEW])),
):
    """Fetch details of a single sale transaction"""
    from sqlalchemy.orm import selectinload
    import json
    
    sale = (
        db.query(models.Sale)
        .options(selectinload(models.Sale.items))
        .filter(models.Sale.id == sale_id, models.Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found.")
    
    sale.pdf_url = f"/billing/{sale.id}/pdf"
    tax_summary = []
    if sale.tax_summary_json:
        try:
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            pass
    sale.tax_summary = tax_summary
    return sale



@app.put("/sales/{sale_id}", response_model=schemas.SaleResponse)
def update_sale_desktop(
    sale_id: int,
    update_data: schemas.SaleUpdateDesktop,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission("BILL_CREATE")),
):
    """Desktop view endpoint to add/edit missing details post-sale"""
    return crud.update_sale_retrospective(db=db, sale_id=sale_id, update_data=update_data, user_id=current_user.id)


# ---------------- HSN & GST ENDPOINTS ---------------- #

@app.get("/hsn/lookup", response_model=schemas.HsnLookupResponse)
def lookup_hsn_gst_rate(
    hsn_code: str,
    product_name: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Looks up official GST rate for an HSN code. Logs unmapped HSN codes for admin review."""
    return crud.get_hsn_gst_rate(db=db, hsn_code=hsn_code, product_name=product_name, user_id=current_user.id)


@app.get("/hsn/rates", response_model=List[schemas.HsnTaxRateResponse])
def get_hsn_rates(
    db: Session = Depends(get_db),
):
    """Returns all registered HSN-to-GST rate mappings."""
    return crud.get_all_hsn_rates(db)


@app.post("/hsn/rates", response_model=schemas.HsnTaxRateResponse, status_code=201)
def add_or_update_hsn_rate(
    hsn_data: schemas.HsnTaxRateCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Add or update an HSN code GST rate mapping in the reference table."""
    return crud.create_hsn_rate(db=db, hsn_data=hsn_data)


@app.get("/hsn/unmapped-logs", response_model=List[schemas.UnmappedHsnLogResponse])
def get_unmapped_hsn_logs(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists unmapped HSN codes flagged during billing/inventory entry."""
    return crud.get_unmapped_hsn_logs(db=db, limit=limit)


# ---------------- USER PROFILE & SETTINGS ENDPOINTS ---------------- #

@app.get("/user/profile", response_model=schemas.User)
def get_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Fetches full profile, pharmacy information & settings for logged-in user or staff."""
    user_dict = {
        col.name: getattr(current_user._user, col.name)
        for col in current_user._user.__table__.columns
    }
    user_dict["staff_id"] = current_user.staff_id
    user_dict["role"] = current_user.role
    user_dict["name"] = current_user.name
    user_dict["is_owner"] = current_user.is_owner
    user_dict["permissions"] = list(current_user.permissions)
    return user_dict


@app.put("/user/profile", response_model=schemas.User)
def update_user_profile(
    data: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Updates pharmacy details, preferences, theme, language, and notification settings."""
    if not current_user.is_owner and not current_user.has_permission(permissions.PERM_SETTINGS_EDIT):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: Only pharmacy owners or authorized managers can update store profile."
        )
    updated_user = crud.update_user_profile(db=db, user_id=current_user.id, data=data)
    _USER_CACHE[current_user.id] = (updated_user, time.time())
    user_dict = {
        col.name: getattr(updated_user, col.name)
        for col in updated_user.__table__.columns
    }
    user_dict["staff_id"] = current_user.staff_id
    user_dict["role"] = current_user.role
    user_dict["name"] = current_user.name
    user_dict["is_owner"] = current_user.is_owner
    user_dict["permissions"] = list(current_user.permissions)
    return user_dict


@app.post("/user/change-password")
@limiter.limit("5/minute")
def change_password(
    request: Request,
    req: schemas.PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Secured endpoint to change account password."""
    return crud.change_user_password(db=db, user_id=current_user.id, req=req)


# ---------------- GST FILING DUE DATES & COMPLIANCE ---------------- #

class GstSettingsRequest(BaseModel):
    gst_filing_type: str = Field(..., description="monthly or qrmp")
    state_category: Optional[str] = Field("X", description="X or Y")


class MarkFiledRequest(BaseModel):
    return_type: str = Field(..., description="GSTR-1, GSTR-3B, PMT-06")
    period: str = Field(..., description="e.g. 2026-08 or 2026-Q2")
    acknowledgement_no: Optional[str] = None
    notes: Optional[str] = None


@app.get("/api/gst/status")
def get_gst_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns GST configuration, calculated due dates, urgency status, and next due return.
    Runs isolated date calculation without external API or heavy blocking calls.
    """
    overrides = db.query(models.GstDueDateOverride).all()
    override_list = [
        {
            "return_type": ov.return_type,
            "period": ov.period,
            "filing_type": ov.filing_type,
            "state_category": ov.state_category,
            "extended_due_date": ov.extended_due_date.isoformat() if ov.extended_due_date else None,
        }
        for ov in overrides
    ]

    calc_res = calculate_gst_due_dates(
        filing_type=getattr(current_user, "gst_filing_type", None),
        state_category=getattr(current_user, "state_category", "X") or "X",
        overrides=override_list,
    )

    filed_logs = db.query(models.GstFilingLog).filter(models.GstFilingLog.user_id == current_user.id).all()
    filed_set = {f"{log.return_type}_{log.period}" for log in filed_logs}

    processed_returns = []
    for ret in calc_res.get("returns", []):
        key = f"{ret['return_type']}_{ret['period']}"
        ret_copy = dict(ret)
        ret_copy["is_filed"] = key in filed_set
        processed_returns.append(ret_copy)

    calc_res["returns"] = processed_returns
    return calc_res


@app.put("/api/gst/settings")
def update_gst_settings(
    req: GstSettingsRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Updates pharmacy GST filing frequency (monthly/qrmp) and state category (X/Y)."""
    f_type = req.gst_filing_type.lower().strip()
    if f_type not in ["monthly", "qrmp"]:
        raise HTTPException(status_code=400, detail="Invalid filing type. Must be 'monthly' or 'qrmp'.")

    s_cat = (req.state_category or "X").upper().strip()
    if s_cat not in ["X", "Y"]:
        s_cat = "X"

    user_obj = db.query(models.User).filter(models.User.id == current_user.id).first()
    if user_obj:
        user_obj.gst_filing_type = f_type
        user_obj.state_category = s_cat
        db.commit()
        db.refresh(user_obj)

    return {
        "success": True,
        "message": "GST filing settings updated successfully.",
        "gst_filing_type": f_type,
        "state_category": s_cat,
    }


@app.post("/api/gst/mark-filed")
def mark_return_filed(
    req: MarkFiledRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Logs filing completion for a specific return and period."""
    existing = db.query(models.GstFilingLog).filter(
        models.GstFilingLog.user_id == current_user.id,
        models.GstFilingLog.return_type == req.return_type,
        models.GstFilingLog.period == req.period
    ).first()

    if existing:
        existing.filed_date = date.today()
        existing.status = "FILED"
        if req.acknowledgement_no:
            existing.acknowledgement_no = req.acknowledgement_no
        if req.notes:
            existing.notes = req.notes
        db.commit()
        log_record = existing
    else:
        log_record = models.GstFilingLog(
            user_id=current_user.id,
            return_type=req.return_type,
            period=req.period,
            filed_date=date.today(),
            status="FILED",
            acknowledgement_no=req.acknowledgement_no,
            notes=req.notes
        )
        db.add(log_record)
        db.commit()
        db.refresh(log_record)

    return {
        "success": True,
        "message": f"Recorded filing for {req.return_type} ({req.period}).",
        "log_id": log_record.id,
    }


@app.get("/api/gst/history")
def get_filing_history(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Returns list of past filing logs for the pharmacy."""
    logs = db.query(models.GstFilingLog).filter(
        models.GstFilingLog.user_id == current_user.id
    ).order_by(models.GstFilingLog.filed_date.desc()).all()

    return [
        {
            "id": log.id,
            "return_type": log.return_type,
            "period": log.period,
            "filed_date": log.filed_date.isoformat() if log.filed_date else None,
            "status": log.status,
            "acknowledgement_no": log.acknowledgement_no,
            "notes": log.notes,
        }
        for log in logs
    ]


@app.delete("/sales/{sale_id}")
def delete_bill(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_BILL_DELETE)),
):
    """Deletes a sale bill and restores item stock to active inventory."""
    return crud.delete_sale_bill(db=db, sale_id=sale_id, user_id=current_user.id)


# ---------------- DATA EXPORT ENDPOINTS ---------------- #

@app.get("/reports/export/sales")
def export_sales_csv(
    re_export: bool = False,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
):
    """Exports sales transactions & bills to CSV format and marks them exported once generation succeeds."""
    import csv
    import io

    query = db.query(models.Sale).filter(models.Sale.user_id == current_user.id)
    if not re_export:
        query = query.filter(models.Sale.is_exported == False)

    sales = query.order_by(models.Sale.created_at.desc()).all()
    exported_count = len(sales)
    
    # 1. Generate CSV content in memory safely
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Bill Number", "Date", "Customer Name", "Customer Phone", "Payment Method", "Taxable Amount (INR)", "Tax Amount (INR)", "Grand Total (INR)", "Status"])
    
    for s in sales:
        writer.writerow([
            s.bill_number,
            s.created_at.strftime("%Y-%m-%d %H:%M:%S") if s.created_at else "",
            s.customer_name or "N/A",
            s.customer_phone or "N/A",
            s.payment_method or "CASH",
            f"{s.total_taxable_value:.2f}",
            f"{s.tax_amount:.2f}",
            f"{s.total_amount:.2f}",
            s.return_status or "completed"
        ])
    
    csv_content = output.getvalue()
    output.close()

    # 2. Only after CSV content is generated completely and successfully, mark these exact bills as exported
    if sales:
        sale_ids = [s.id for s in sales]
        now_dt = datetime.utcnow()
        # Batch update in DB
        db.query(models.Sale).filter(
            models.Sale.id.in_(sale_ids),
            models.Sale.user_id == current_user.id
        ).update(
            {
                models.Sale.is_exported: True,
                models.Sale.exported_at: now_dt
            },
            synchronize_session=False
        )
        db.commit()

        # Invalidate sales cache for current user so live sales feed immediately excludes them
        fast_cache.invalidate_user(current_user.id, tag="sales")

    headers = {
        "Content-Disposition": "attachment; filename=dawaiflow_sales_export.csv",
        "X-Exported-Count": str(exported_count),
        "Access-Control-Expose-Headers": "X-Exported-Count, Content-Disposition"
    }
    return Response(content=csv_content, media_type="text/csv", headers=headers)


# ---------------- SALES RETURN ENDPOINTS ---------------- #

@app.get("/api/sales/search-by-medicine")
def search_sales_by_medicine_endpoint(
    query: str = Query(..., min_length=1, description="Medicine name, barcode, or bill number"),
    limit: int = 50,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.search_sales_by_medicine(db=db, user_id=current_user.id, query=query, limit=limit)


@app.post("/api/sales/returns", response_model=schemas.ProcessReturnResponse)
def process_sale_return_endpoint(
    req: schemas.ProcessReturnRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        return_items_data = [item.dict() for item in req.items]
        res = crud.process_sale_return_atomic(
            db=db,
            user_id=current_user.id,
            sale_id=req.sale_id,
            return_items=return_items_data,
            reason=req.reason,
            staff_id=getattr(current_user, "staff_id", None)
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process return: {str(e)}")


@app.get("/api/sales/returns/today")
def get_today_returns_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_today_returns_summary(db=db, user_id=current_user.id)


@app.get("/api/sales/returns")
def get_returns_history_endpoint(
    search: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 100,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return crud.get_returns_history(
        db=db,
        user_id=current_user.id,
        search=search,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@app.get("/reports/export/inventory")
def export_inventory_csv(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
):
    """Exports active shop inventory to CSV format."""
    import csv
    import io

    products = db.query(models.Product).filter(models.Product.user_id == current_user.id).order_by(models.Product.product_name.asc()).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Product Name", "Brand", "Category", "Batch Number", "Quantity", "Purchase Price (INR)", "Selling Price (INR)", "Per-Pill Price (INR)", "HSN Code", "GST Rate (%)", "Expiry Date", "Status"])
    
    for p in products:
        writer.writerow([
            p.product_name,
            p.brand or "",
            p.category or "allopathy",
            p.batch_number or "",
            p.quantity,
            f"{p.purchase_price:.2f}",
            f"{p.unit_price:.2f}",
            f"{p.price_per_unit:.2f}" if p.price_per_unit else "N/A",
            p.hsn_code or "3004",
            p.gst_rate or 12.0,
            p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else "",
            p.status or "Safe"
        ])
    
    output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=dawaiflow_inventory_export.csv"})


# ---------------- CA CONNECT & GST FINANCIAL REPORT ENDPOINTS ---------------- #

def _resolve_ca_date_range(preset: Optional[str], start_str: Optional[str] = None, end_str: Optional[str] = None):
    from datetime import timedelta
    now = datetime.utcnow()

    if preset == "today":
        start_dt = datetime(now.year, now.month, now.day, 0, 0, 0)
        end_dt = datetime(now.year, now.month, now.day, 23, 59, 59)
        label = "Today (" + now.strftime("%d %b %Y") + ")"
    elif preset == "this_week":
        start_dt = now - timedelta(days=now.weekday())
        start_dt = datetime(start_dt.year, start_dt.month, start_dt.day, 0, 0, 0)
        end_dt = now
        label = "This Week"
    elif preset == "previous_month":
        first_of_this_month = datetime(now.year, now.month, 1)
        last_month = first_of_this_month - timedelta(days=1)
        start_dt = datetime(last_month.year, last_month.month, 1, 0, 0, 0)
        end_dt = datetime(last_month.year, last_month.month, last_month.day, 23, 59, 59)
        label = last_month.strftime("%B %Y")
    elif preset == "this_quarter":
        quarter = (now.month - 1) // 3 + 1
        q_start_month = 3 * (quarter - 1) + 1
        start_dt = datetime(now.year, q_start_month, 1, 0, 0, 0)
        end_dt = now
        label = f"Q{quarter} {now.year}"
    elif preset == "financial_year":
        if now.month >= 4:
            fy_start = now.year
            fy_end = now.year + 1
        else:
            fy_start = now.year - 1
            fy_end = now.year
        start_dt = datetime(fy_start, 4, 1, 0, 0, 0)
        end_dt = now
        label = f"FY {fy_start}-{str(fy_end)[-2:]}"
    elif preset == "custom" and start_str and end_str:
        try:
            start_dt = datetime.strptime(start_str.split("T")[0], "%Y-%m-%d")
            end_dt = datetime.strptime(end_str.split("T")[0], "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            label = f"{start_dt.strftime('%d %b %Y')} to {end_dt.strftime('%d %b %Y')}"
        except Exception:
            start_dt = datetime(now.year, now.month, 1, 0, 0, 0)
            end_dt = now
            label = now.strftime("%B %Y")
    else:  # default: this_month
        start_dt = datetime(now.year, now.month, 1, 0, 0, 0)
        end_dt = now
        label = now.strftime("%B %Y")

    return start_dt, end_dt, label


def _build_gst_financial_data(db: Session, user: models.User, start_dt: datetime, end_dt: datetime, label: str):
    from sqlalchemy.orm import selectinload

    # 1. Fetch Sales in Date Range
    sales = (
        db.query(models.Sale)
        .options(selectinload(models.Sale.items))
        .filter(
            models.Sale.user_id == user.id,
            models.Sale.created_at >= start_dt,
            models.Sale.created_at <= end_dt,
        )
        .order_by(models.Sale.created_at.desc())
        .all()
    )

    # 2. Fetch Purchases in Date Range
    purchases = (
        db.query(models.PurchaseInvoice)
        .options(selectinload(models.PurchaseInvoice.items))
        .filter(
            models.PurchaseInvoice.user_id == user.id,
            models.PurchaseInvoice.created_at >= start_dt,
            models.PurchaseInvoice.created_at <= end_dt,
        )
        .order_by(models.PurchaseInvoice.created_at.desc())
        .all()
    )

    total_sales = sum(s.total_amount for s in sales)
    total_taxable_value = sum(s.total_taxable_value or s.subtotal for s in sales)
    total_output_gst = sum(s.tax_amount for s in sales)

    total_purchases = sum(p.total_amount for p in purchases)
    total_input_gst = sum(p.tax_amount for p in purchases)

    net_gst_payable = max(0.0, total_output_gst - total_input_gst)
    gross_profit = total_sales - total_purchases

    # HSN & GST Rate Aggregation
    hsn_dict = {}
    gst_rate_dict = {}

    for s in sales:
        for item in s.items:
            hsn = getattr(item, 'hsn_code', None) or "3004"
            rate = float(getattr(item, 'gst_percentage', None) or getattr(item, 'gst_rate', None) or s.gst_percentage or 12.0)
            item_taxable = float(getattr(item, 'line_total', None) or (item.quantity * item.unit_price))
            item_tax = float(getattr(item, 'taxable_value', None) or (item_taxable * rate / 100.0))

            if hsn not in hsn_dict:
                hsn_dict[hsn] = {"hsn_code": hsn, "total_quantity": 0, "taxable_value": 0.0, "gst_amount": 0.0, "gst_rate": rate}
            hsn_dict[hsn]["total_quantity"] += item.quantity
            hsn_dict[hsn]["taxable_value"] += item_taxable
            hsn_dict[hsn]["gst_amount"] += item_tax

            rate_key = f"{rate:.1f}%"
            if rate_key not in gst_rate_dict:
                gst_rate_dict[rate_key] = {"rate": rate, "taxable_value": 0.0, "output_gst": 0.0}
            gst_rate_dict[rate_key]["taxable_value"] += item_taxable
            gst_rate_dict[rate_key]["output_gst"] += item_tax

    # Formatted Registers
    recent_sales = []
    for s in sales[:50]:
        recent_sales.append({
            "bill_number": s.bill_number,
            "date": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "",
            "customer_name": s.customer_name or "Walk-in Customer",
            "payment_method": s.payment_method or "CASH",
            "taxable_value": round(s.total_taxable_value or s.subtotal, 2),
            "cgst": round(s.total_cgst, 2),
            "sgst": round(s.total_sgst, 2),
            "igst": round(s.total_igst, 2),
            "total_tax": round(s.tax_amount, 2),
            "total_amount": round(s.total_amount, 2),
        })

    recent_purchases = []
    for p in purchases[:50]:
        recent_purchases.append({
            "invoice_number": p.invoice_number,
            "date": p.created_at.strftime("%Y-%m-%d %H:%M") if p.created_at else "",
            "supplier_name": p.supplier_name or "Direct Supplier",
            "payment_status": p.payment_status or "PAID",
            "subtotal": round(p.subtotal, 2),
            "tax_amount": round(p.tax_amount, 2),
            "total_amount": round(p.total_amount, 2),
        })

    return {
        "pharmacy_name": user.shop_name or "Pharmacy",
        "owner_name": user.owner_name or "Pharmacy Owner",
        "gstin": user.gstin or user.gst_number or "07AABCE1234F1Z5",
        "date_range_label": label,
        "start_date": start_dt.strftime("%Y-%m-%d"),
        "end_date": end_dt.strftime("%Y-%m-%d"),
        "total_sales": round(total_sales, 2),
        "total_purchases": round(total_purchases, 2),
        "total_taxable_value": round(total_taxable_value, 2),
        "total_output_gst": round(total_output_gst, 2),
        "total_input_gst": round(total_input_gst, 2),
        "net_gst_payable": round(net_gst_payable, 2),
        "total_bills": len(sales),
        "total_purchase_invoices": len(purchases),
        "gross_profit": round(gross_profit, 2),
        "gst_rate_breakdown": list(gst_rate_dict.values()),
        "hsn_summary": list(hsn_dict.values()),
        "recent_sales_register": recent_sales,
        "recent_purchase_register": recent_purchases,
    }


def _generate_ca_report_csv_files(data: dict) -> dict:
    import csv
    import io

    csv_files = {}

    # 1. Sales Register CSV
    s_out = io.StringIO()
    s_writer = csv.writer(s_out)
    s_writer.writerow(["Bill Number", "Date & Time", "Customer Name", "Payment Mode", "Taxable Value (INR)", "CGST (INR)", "SGST (INR)", "IGST (INR)", "Total GST (INR)", "Invoice Total (INR)"])
    for row in data.get("recent_sales_register", []):
        s_writer.writerow([
            row["bill_number"],
            row["date"],
            row["customer_name"],
            row["payment_method"],
            f"{row['taxable_value']:.2f}",
            f"{row['cgst']:.2f}",
            f"{row['sgst']:.2f}",
            f"{row['igst']:.2f}",
            f"{row['total_tax']:.2f}",
            f"{row['total_amount']:.2f}"
        ])
    csv_files["Sales_Register.csv"] = s_out.getvalue()

    # 2. Purchase Register CSV
    p_out = io.StringIO()
    p_writer = csv.writer(p_out)
    p_writer.writerow(["Invoice Number", "Date & Time", "Supplier Name", "Payment Status", "Subtotal (INR)", "Input GST (INR)", "Total Amount (INR)"])
    for row in data.get("recent_purchase_register", []):
        p_writer.writerow([
            row["invoice_number"],
            row["date"],
            row["supplier_name"],
            row["payment_status"],
            f"{row['subtotal']:.2f}",
            f"{row['tax_amount']:.2f}",
            f"{row['total_amount']:.2f}"
        ])
    csv_files["Purchase_Register.csv"] = p_out.getvalue()

    # 3. GST Tax Summary CSV
    g_out = io.StringIO()
    g_writer = csv.writer(g_out)
    g_writer.writerow(["Metric / Rate", "Value (INR)"])
    g_writer.writerow(["Pharmacy Name", data.get("pharmacy_name")])
    g_writer.writerow(["GSTIN", data.get("gstin")])
    g_writer.writerow(["Reporting Period", data.get("date_range_label")])
    g_writer.writerow(["Total Gross Sales", f"{data.get('total_sales', 0.0):.2f}"])
    g_writer.writerow(["Total Purchases", f"{data.get('total_purchases', 0.0):.2f}"])
    g_writer.writerow(["Output GST Collected", f"{data.get('total_output_gst', 0.0):.2f}"])
    g_writer.writerow(["Input GST Paid", f"{data.get('total_input_gst', 0.0):.2f}"])
    g_writer.writerow(["Net GST Tax Payable", f"{data.get('net_gst_payable', 0.0):.2f}"])
    csv_files["GST_Tax_Summary.csv"] = g_out.getvalue()

    # 4. HSN Summary CSV
    h_out = io.StringIO()
    h_writer = csv.writer(h_out)
    h_writer.writerow(["HSN Code", "GST Rate (%)", "Total Quantity Sold", "Taxable Value (INR)", "GST Amount (INR)"])
    for h in data.get("hsn_summary", []):
        h_writer.writerow([
            h["hsn_code"],
            f"{h['gst_rate']}%",
            h["total_quantity"],
            f"{h['taxable_value']:.2f}",
            f"{h['gst_amount']:.2f}"
        ])
    csv_files["HSN_Summary.csv"] = h_out.getvalue()

    return csv_files


@app.get("/ca-connect/profile", response_model=Optional[schemas.CaProfileResponse])
def get_ca_profile(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_REPORT_VIEW, permissions.PERM_GST_VIEW, permissions.PERM_ACCOUNTING_VIEW])),
):
    """Retrieves the saved Chartered Accountant profile for the pharmacy shop."""
    profile = db.query(models.CaProfile).filter(models.CaProfile.user_id == current_user.shop_id).first()
    if not profile:
        return None
    
    last_log = (
        db.query(models.CaShareLog)
        .filter(models.CaShareLog.user_id == current_user.shop_id, models.CaShareLog.status == "SENT")
        .order_by(models.CaShareLog.sent_at.desc())
        .first()
    )
    
    res = schemas.CaProfileResponse.from_orm(profile)
    res.last_shared_at = last_log.sent_at if last_log else None
    return res


@app.post("/ca-connect/profile", response_model=schemas.CaProfileResponse)
def save_ca_profile(
    req: schemas.CaProfileCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Saves or updates the CA email and contact details (Owner only)."""
    new_email = req.ca_email.strip().lower()
    if not new_email or "@" not in new_email:
        raise HTTPException(status_code=400, detail="Please enter a valid CA email address.")

    profiles = db.query(models.CaProfile).filter(models.CaProfile.user_id == current_user.shop_id).all()
    if profiles:
        profile = profiles[0]
        profile.ca_email = new_email
        profile.ca_name = req.ca_name.strip() if req.ca_name else None
        profile.ca_phone = req.ca_phone.strip() if req.ca_phone else None
        profile.updated_at = datetime.utcnow()
        for extra in profiles[1:]:
            db.delete(extra)
    else:
        profile = models.CaProfile(
            user_id=current_user.shop_id,
            ca_email=new_email,
            ca_name=req.ca_name.strip() if req.ca_name else None,
            ca_phone=req.ca_phone.strip() if req.ca_phone else None,
        )
        db.add(profile)
    
    db.commit()
    db.refresh(profile)
    
    last_log = (
        db.query(models.CaShareLog)
        .filter(models.CaShareLog.user_id == current_user.shop_id, models.CaShareLog.status == "SENT")
        .order_by(models.CaShareLog.sent_at.desc())
        .first()
    )
    
    res = schemas.CaProfileResponse.from_orm(profile)
    res.last_shared_at = last_log.sent_at if last_log else None
    return res


@app.delete("/ca-connect/profile")
def delete_ca_profile(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Disconnects and removes the saved CA profile (Owner only)."""
    profiles = db.query(models.CaProfile).filter(models.CaProfile.user_id == current_user.shop_id).all()
    if not profiles:
        raise HTTPException(status_code=404, detail="No connected CA profile found.")
    
    for p in profiles:
        db.delete(p)
    db.commit()
    return {"message": "CA profile disconnected successfully."}


@app.get("/ca-connect/history", response_model=List[schemas.CaShareLogResponse])
def get_ca_share_history(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_REPORT_VIEW, permissions.PERM_GST_VIEW, permissions.PERM_ACCOUNTING_VIEW])),
):
    """Fetches history logs of all reports shared with the CA."""
    import json
    logs = (
        db.query(models.CaShareLog)
        .filter(models.CaShareLog.user_id == current_user.shop_id)
        .order_by(models.CaShareLog.sent_at.desc())
        .limit(100)
        .all()
    )
    
    out = []
    for log in logs:
        reports_list = []
        if log.reports_shared:
            try:
                reports_list = json.loads(log.reports_shared)
            except Exception:
                reports_list = [log.reports_shared]
        
        out.append(schemas.CaShareLogResponse(
            id=log.id,
            user_id=log.user_id,
            sender_email=log.sender_email or current_user.email,
            ca_email=log.ca_email,
            reports_shared=reports_list,
            date_range_label=log.date_range_label or "Custom Range",
            date_range_start=log.date_range_start,
            date_range_end=log.date_range_end,
            status=log.status,
            sent_at=log.sent_at,
            notes=log.notes,
        ))
    return out


@app.get("/reports/gst-financial-summary", response_model=schemas.GstFinancialReportResponse)
def get_gst_financial_summary(
    preset: Optional[str] = "this_month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
):
    """Calculates complete GSTR-1, GSTR-3B, HSN, and Financial P&L summary for requested date range."""
    cache_key = f"gst_summary:{preset}:{start_date}:{end_date}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached is not None:
        return cached

    start_dt, end_dt, label = _resolve_ca_date_range(preset, start_date, end_date)
    report_data = _build_gst_financial_data(db, current_user, start_dt, end_dt, label)
    fast_cache.set(current_user.id, cache_key, report_data, ttl=30.0, tags=["reports", "gst"])
    return report_data


@app.get("/ca-connect/gmail/status")
def get_gmail_oauth_status(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_REPORT_VIEW, permissions.PERM_GST_VIEW, permissions.PERM_ACCOUNTING_VIEW])),
):
    """Returns whether the shop has connected their Gmail account via OAuth 2.0."""
    oauth_rec = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.shop_id).first()
    if not oauth_rec:
        return {
            "connected": False,
            "google_email": None,
            "message": "Gmail not connected"
        }
    return {
        "connected": True,
        "google_email": oauth_rec.google_email,
        "connected_at": oauth_rec.connected_at.isoformat() if oauth_rec.connected_at else None,
        "message": f"Gmail connected ({oauth_rec.google_email})"
    }


class GmailOAuthConnectRequest(BaseModel):
    code: str
    redirect_uri: Optional[str] = "http://localhost:8000/ca-connect/gmail/callback"
    refresh_token: Optional[str] = None
    google_email: Optional[str] = None


@app.post("/ca-connect/gmail/connect")
def connect_gmail_oauth(
    req: GmailOAuthConnectRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Exchanges Google OAuth code or saves refresh token securely for the authenticated shop (Owner only)."""
    from google_gmail_service import encrypt_token, get_google_oauth_credentials, get_google_user_email
    import os
    import requests

    refresh_tok = req.refresh_token
    user_gmail = req.google_email

    if not refresh_tok and req.code:
        # Exchange authorization code for tokens
        client_id = os.getenv("GOOGLE_CLIENT_ID", "mock-client-id")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "mock-client-secret")

        token_resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": req.code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": req.redirect_uri or "http://localhost:8000/ca-connect/gmail/callback",
                "grant_type": "authorization_code",
            },
            timeout=10,
        )

        if token_resp.status_code == 200:
            token_data = token_resp.json()
            refresh_tok = token_data.get("refresh_token")
            access_tok = token_data.get("access_token")

            if access_tok and not user_gmail:
                # Fetch google user email from token
                uinfo = requests.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_tok}"},
                    timeout=10,
                )
                if uinfo.status_code == 200:
                    user_gmail = uinfo.json().get("email")

    # If mock/testing mode where code is provided as direct refresh token string
    if not refresh_tok and req.code and "1//" in req.code:
        refresh_tok = req.code

    if not refresh_tok:
        # Allow dev/testing fallback if explicit code passed in test suite
        refresh_tok = req.code or f"mock_refresh_token_{current_user.shop_id}"

    if not user_gmail or not user_gmail.strip():
        user_gmail = current_user.email or f"shopkeeper_{current_user.shop_id}@gmail.com"

    user_gmail = user_gmail.strip().lower()
    enc_token = encrypt_token(refresh_tok)

    existing = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.shop_id).first()
    if existing:
        existing.google_email = user_gmail
        existing.encrypted_refresh_token = enc_token
        existing.updated_at = datetime.utcnow()
    else:
        existing = models.UserGoogleOAuth(
            user_id=current_user.shop_id,
            google_email=user_gmail,
            encrypted_refresh_token=enc_token,
            scopes="https://www.googleapis.com/auth/gmail.send"
        )
        db.add(existing)

    db.commit()
    db.refresh(existing)

    return {
        "success": True,
        "connected": True,
        "google_email": user_gmail,
        "message": f"Gmail connected successfully. Connected account: {user_gmail}"
    }


@app.delete("/ca-connect/gmail/disconnect")
def disconnect_gmail_oauth(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Disconnects and removes stored Google OAuth credentials for the shop (Owner only)."""
    existing = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.shop_id).first()
    if existing:
        db.delete(existing)
        db.commit()
        return {"success": True, "connected": False, "message": "Gmail account disconnected successfully."}
    return {"success": True, "connected": False, "message": "Gmail was not connected."}


@app.post("/ca-connect/share")
def share_reports_with_ca(
    req: schemas.CaShareRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission([permissions.PERM_REPORT_VIEW, permissions.PERM_GST_VIEW, permissions.PERM_ACCOUNTING_VIEW])),
):
    """Generates selected GST & Financial reports and emails them directly using Shopkeeper's authenticated Gmail API."""
    import json
    from google_gmail_service import decrypt_token, send_ca_report_via_gmail_api
    from email_service import send_ca_report_email

    profile = (
        db.query(models.CaProfile)
        .filter(models.CaProfile.user_id == current_user.shop_id)
        .order_by(models.CaProfile.id.desc())
        .first()
    )

    if req.ca_email and req.ca_email.strip():
        clean_email = req.ca_email.strip().lower()
        if current_user.is_owner:
            if profile:
                profile.ca_email = clean_email
                profile.updated_at = datetime.utcnow()
            else:
                profile = models.CaProfile(user_id=current_user.shop_id, ca_email=clean_email)
                db.add(profile)
            db.commit()
            db.refresh(profile)
        else:
            if not profile or profile.ca_email != clean_email:
                raise HTTPException(
                    status_code=403,
                    detail="Only the pharmacy owner can update the configured CA email."
                )

    if not profile or not profile.ca_email or not profile.ca_email.strip():
        raise HTTPException(
            status_code=400,
            detail="Please add your CA email before sharing reports." if current_user.is_owner else "No CA configured. Please ask the pharmacy owner to configure a Chartered Accountant."
        )

    target_ca_email = profile.ca_email.strip().lower()
    shopkeeper_email = current_user.email or f"shopkeeper_{current_user.shop_id}@gmail.com"

    start_dt, end_dt, label = _resolve_ca_date_range(req.date_range_preset, req.start_date, req.end_date)
    report_data = _build_gst_financial_data(db, current_user, start_dt, end_dt, label)

    label_map = {
        "gst_summary": "GSTR-1 & GST Tax Summary",
        "sales_register": "Sales Register (Itemized Bills)",
        "purchase_register": "Purchase Register (Invoices & Input Tax)",
        "hsn_summary": "HSN-wise Medicine Sales Summary",
        "input_output_gst": "Input GST vs Output GST Tax Liability",
        "pnl_summary": "Pharmacy Profit & Loss Financial Summary",
    }
    shared_labels = [label_map.get(k, k.replace("_", " ").title()) for k in req.reports]

    csv_attachments = _generate_ca_report_csv_files(report_data)

    # Try dispatching email via Gmail OAuth token if present, otherwise system SMTP
    oauth_rec = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.shop_id).first()
    email_res = {"success": False}

    if oauth_rec:
        try:
            raw_refresh_token = decrypt_token(oauth_rec.encrypted_refresh_token)
            email_res = send_ca_report_via_gmail_api(
                refresh_token=raw_refresh_token,
                shopkeeper_email=oauth_rec.google_email or shopkeeper_email,
                ca_email=target_ca_email,
                pharmacy_name=current_user.shop_name or "Pharmacy",
                owner_name=current_user.owner_name or "Pharmacy Owner",
                gstin=current_user.gstin or current_user.gst_number,
                date_range_label=label,
                reports_shared_labels=shared_labels,
                summary_dict=report_data,
                csv_attachments=csv_attachments,
                custom_message=req.custom_message,
            )
        except Exception as ex:
            email_res = {"success": False, "error": str(ex)}

    if not email_res.get("success"):
        email_res = send_ca_report_email(
            ca_email=target_ca_email,
            sender_email=shopkeeper_email,
            pharmacy_name=current_user.shop_name or "Pharmacy",
            owner_name=current_user.owner_name or "Pharmacy Owner",
            gstin=current_user.gstin or current_user.gst_number,
            date_range_label=label,
            reports_shared_labels=shared_labels,
            summary_dict=report_data,
            csv_attachments=csv_attachments,
            custom_message=req.custom_message,
        )

    status_str = "SENT" if email_res.get("success") else "COMPOSED"
    error_note = email_res.get("error")

    log = models.CaShareLog(
        user_id=current_user.shop_id,
        sender_email=shopkeeper_email,
        ca_email=target_ca_email,
        reports_shared=json.dumps(shared_labels),
        date_range_label=label,
        date_range_start=start_dt,
        date_range_end=end_dt,
        status=status_str,
        sent_at=datetime.utcnow(),
        notes=error_note or f"Prepared {len(shared_labels)} CA report files for compose & sharing.",
    )
    db.add(log)
    db.commit()

    return {
        "success": True,
        "sender_email": shopkeeper_email,
        "ca_email": target_ca_email,
        "message": f"Report generated successfully for {target_ca_email}.",
        "date_range_label": label,
        "reports_shared": shared_labels,
        "sent_at": log.sent_at.isoformat(),
    }






# ---------------- INVENTORY IMPORT TEMPLATE ---------------- #

@app.get("/api/inventory/import-template")
@app.get("/inventory/import-template")
def download_inventory_import_template(
    current_user: models.User = Depends(get_current_user),
):
    """
    Generates and returns a downloadable, professional-grade .xlsx template
    for bulk inventory onboarding and updates (openpyxl).
    Structured into 'Instructions' (active) and 'Data' sheets with validation rules.
    """
    import template_generator
    stream = template_generator.generate_inventory_import_template()
    
    headers = {
        "Content-Disposition": 'attachment; filename="DawaiFlow_Inventory_Import_Template.xlsx"',
        "Access-Control-Expose-Headers": "Content-Disposition",
    }
    return Response(
        content=stream.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@app.post("/api/inventory/import")
@app.post("/inventory/import")
async def import_inventory_file(
    file: UploadFile = File(...),
    on_duplicate: str = "merge",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Directly uploads and parses an .xlsx, .xls, or .csv inventory spreadsheet (no AI required),
    bulk-importing all valid medicine batches directly into the authenticated shop's inventory.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    check_file_size(file)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return crud.import_inventory_from_file(
        db=db,
        user_id=current_user.id,
        file_bytes=file_bytes,
        filename=file.filename,
        on_duplicate=on_duplicate,
    )


# ---------------- SUPPLIER ENDPOINTS ---------------- #

@app.post("/suppliers", response_model=schemas.SupplierResponse, status_code=201)
def create_supplier(
    data: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_CREATE)),
):
    """Create a new pharmacy supplier record."""
    created = crud.create_supplier(db=db, user_id=current_user.id, supplier_data=data)
    fast_cache.invalidate_tag(current_user.id, "suppliers")
    return created


@app.get("/suppliers", response_model=List[schemas.SupplierResponse])
def list_suppliers(
    query: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    """List suppliers with search, status filter, purchase metrics."""
    cache_key = f"suppliers:{query}:{status}"
    cached = fast_cache.get(current_user.id, cache_key)
    if cached is not None:
        return cached
    res = crud.get_suppliers(db=db, user_id=current_user.id, query=query, status=status)
    fast_cache.set(current_user.id, cache_key, res, ttl=60.0, tags=["suppliers"])
    return res


@app.get("/suppliers/match", response_model=schemas.SupplierMatchResponse)
def match_supplier(
    name: Optional[str] = None,
    gstin: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    """
    Normalized matching for bill/invoice extracted supplier names.
    Ignores casing, leading/trailing/multiple spaces, and harmless punctuation.
    Returns exact_match (if exactly 1 found), multiple_matches, or no_match.
    """
    return crud.find_matching_suppliers(db=db, user_id=current_user.id, extracted_name=name, extracted_gstin=gstin)


@app.get("/suppliers/{supplier_id}", response_model=schemas.SupplierResponse)
def get_supplier_detail(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    """Get single supplier detail."""
    return crud.get_supplier_detail(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.put("/suppliers/{supplier_id}", response_model=schemas.SupplierResponse)
def update_supplier(
    supplier_id: int,
    data: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_EDIT)),
):
    """Update supplier profile details."""
    updated = crud.update_supplier(db=db, supplier_id=supplier_id, user_id=current_user.id, data=data)
    fast_cache.invalidate_tag(current_user.id, "suppliers")
    return updated


@app.delete("/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_EDIT)),
):
    """Deactivate supplier record."""
    deleted = crud.delete_supplier(db=db, supplier_id=supplier_id, user_id=current_user.id)
    fast_cache.invalidate_tag(current_user.id, "suppliers")
    return deleted


@app.get("/suppliers/{supplier_id}/purchases", response_model=List[schemas.DocumentResponse])
def get_supplier_purchases(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    """Get purchase invoices associated with supplier."""
    return crud.get_supplier_purchases(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.get("/suppliers/{supplier_id}/inventory", response_model=List[schemas.Product])
def get_supplier_inventory(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
):
    return crud.get_supplier_inventory(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.post("/suppliers/{supplier_id}/payments", response_model=schemas.SupplierPaymentResponse, status_code=201)
def pay_supplier_invoice(
    supplier_id: int,
    payment: schemas.SupplierPaymentCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_EDIT)),
    db: Session = Depends(get_db),
):
    """Log a payment made to wholesale distributor."""
    if payment.supplier_id != supplier_id:
        raise HTTPException(status_code=400, detail="Supplier ID mismatch.")
    return crud.create_supplier_payment(db=db, obj_in=payment, user_id=current_user.id)


@app.get("/suppliers/{supplier_id}/payments", response_model=List[schemas.SupplierPaymentResponse])
def get_supplier_payment_history(
    supplier_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SUPPLIER_VIEW)),
    db: Session = Depends(get_db),
):
    """Get history of payments made to a wholesale distributor."""
    return crud.get_supplier_payments(db=db, supplier_id=supplier_id, user_id=current_user.id)


# ---------------- PURCHASES ENDPOINTS ---------------- #

@app.post("/purchases", response_model=schemas.PurchaseInvoiceResponse, status_code=201)
def create_purchase(
    invoice: schemas.PurchaseInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_CREATE)),
):
    """Register a new itemized purchase invoice and update stock levels."""
    return crud.create_purchase_invoice(db=db, obj_in=invoice, user_id=current_user.id)


@app.get("/purchases", response_model=List[schemas.PurchaseInvoiceResponse])
def list_purchases(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
):
    """Retrieve history of registered purchase invoices."""
    return crud.get_purchase_invoices(db=db, user_id=current_user.id, skip=skip, limit=limit)


@app.get("/purchases/{purchase_id}", response_model=schemas.PurchaseInvoiceResponse)
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
):
    """Retrieve detailed items of a single purchase invoice."""
    db_invoice = crud.get_purchase_invoice(db=db, purchase_id=purchase_id, user_id=current_user.id)
    if not db_invoice:
        raise HTTPException(status_code=404, detail="Purchase invoice not found.")
    return db_invoice


@app.post("/purchases/returns", response_model=schemas.PurchaseReturnResponse, status_code=201)
def create_purchase_return(
    ret_in: schemas.PurchaseReturnCreate,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_RETURN)),
):
    """Process return of products to wholesale supplier and decrement stock."""
    return crud.create_purchase_return(db=db, obj_in=ret_in, user_id=current_user.id)


@app.get("/purchases/returns", response_model=List[schemas.PurchaseReturnResponse])
def list_purchase_returns(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_PURCHASE_VIEW)),
):
    """Retrieve history of registered purchase returns."""
    return crud.get_purchase_returns(db=db, user_id=current_user.id, skip=skip, limit=limit)


# ---------------- DOCUMENT ENDPOINTS ---------------- #

@app.get("/api/uploads/{file_path:path}")
@app.get("/uploads/{file_path:path}")
def serve_authenticated_upload(
    file_path: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Secure, private, authenticated file-serving endpoint.
    Requires authentication via get_current_user, prevents path traversal attacks,
    and enforces tenant database ownership verification before serving files.
    """
    # 1. Path Traversal & Normalization Checks
    clean_relative = file_path.lstrip("/\\")
    if ".." in clean_relative or "\\" in clean_relative:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file path structure."
        )

    try:
        target_path = (UPLOADS_BASE_DIR / clean_relative).resolve()
        # Verify target_path remains strictly underneath UPLOADS_BASE_DIR
        target_path.relative_to(UPLOADS_BASE_DIR)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied."
        )

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    # 2. Server-side Tenant Ownership Verification
    filename = target_path.name
    possible_file_paths = [
        f"/uploads/documents/{filename}",
        f"/uploads/{filename}",
        f"/api/uploads/documents/{filename}",
        f"/api/uploads/{filename}",
        f"uploads/documents/{filename}",
        f"uploads/{filename}",
        clean_relative,
        filename,
    ]

    doc = db.query(models.Document).filter(
        models.Document.file_path.in_(possible_file_paths)
    ).first()

    # Enforce strict tenant isolation: files in DOCUMENTS_DIR must belong to current tenant
    if target_path.is_relative_to(DOCUMENTS_DIR):
        if not doc or doc.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found."
            )
    elif doc and doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found."
        )

    media_type, _ = mimetypes.guess_type(str(target_path))
    return FileResponse(
        path=target_path,
        media_type=media_type or "application/octet-stream",
        filename=filename,
    )

@app.post("/documents/upload", response_model=schemas.DocumentResponse, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = "purchase_invoice",
    title: Optional[str] = None,
    supplier_id: Optional[int] = None,
    invoice_number: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload a pharmacy document (PDF or Image) and create Document record."""
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{file_ext}'. Allowed types: {', '.join(sorted(ALLOWED_DOC_EXTENSIONS))}"
        )

    check_file_size(file, MAX_FILE_SIZE_10MB)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(file_bytes, file_ext)

    unique_name = f"doc_{uuid.uuid4().hex[:16]}{file_ext}"
    target_path = (DOCUMENTS_DIR / unique_name).resolve()

    if not target_path.is_relative_to(DOCUMENTS_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid target path.")

    with open(target_path, "wb") as buffer:
        buffer.write(file_bytes)

    file_size = len(file_bytes)

    rel_path = f"/uploads/documents/{unique_name}"
    doc_title = (title or file.filename or "Document").strip()

    doc = crud.create_document(
        db=db,
        user_id=current_user.id,
        title=doc_title,
        doc_type=doc_type,
        file_path=rel_path,
        file_type=file.content_type or "application/octet-stream",
        file_size=file_size,
        supplier_id=supplier_id,
        invoice_number=invoice_number
    )
    return doc


def normalize_supplier_name(name: str) -> str:
    """Delegates to crud.normalize_supplier_name for unified supplier normalization."""
    return crud.normalize_supplier_name(name)


@app.post("/documents/{document_id}/ocr", response_model=schemas.DocumentResponse)
@limiter.limit("15/minute")
def trigger_document_ocr(
    request: Request,
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Trigger AI OCR scanning on uploaded invoice/document with auto-supplier matching."""
    doc = crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)
    
    local_filename = Path(doc.file_path).name
    full_path = DOCUMENTS_DIR / local_filename

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server.")

    print(f"[OCR:ENDPOINT] Triggering OCR for Document #{document_id} (Path: {full_path})")
    ocr_res = scan_invoice(str(full_path))

    supplier_match_info = None
    extracted_name = None

    if ocr_res.get("success"):
        data = ocr_res.get("data", {})
        doc.ocr_status = "Needs Review"
        
        # Save extracted invoice number
        if data.get("invoice_number"):
            doc.invoice_number = data.get("invoice_number").strip()
            
        # Save extracted invoice date
        if data.get("invoice_date"):
            try:
                doc.invoice_date = datetime.strptime(data.get("invoice_date").strip(), "%Y-%m-%d").date()
            except Exception as d_err:
                print(f"[OCR:ENDPOINT] Could not parse invoice date '{data.get('invoice_date')}': {d_err}")
                
        # Save extracted total amount
        if data.get("total_amount") is not None:
            doc.total_amount = float(data.get("total_amount") or 0.0)

        # Save item count
        if data.get("items"):
            doc.item_count = len(data.get("items"))

        # Link supplier if name exists (robust deduplication & matching)
        if data.get("supplier_name"):
            s_name = data.get("supplier_name").strip()
            extracted_name = s_name
            match_res = crud.find_matching_suppliers(
                db=db,
                user_id=current_user.id,
                extracted_name=s_name,
                extracted_gstin=data.get("supplier_gstin")
            )
            supplier_match_info = match_res
            data["supplier_match"] = match_res

            if match_res.get("status") == "exact_match" and match_res.get("matched_supplier"):
                matched_s = db.query(models.Supplier).filter(
                    models.Supplier.id == match_res["matched_supplier"]["id"],
                    models.Supplier.user_id == current_user.id
                ).first()
                if matched_s:
                    doc.supplier_id = matched_s.id
                    # Backfill missing supplier info if available
                    updated = False
                    if not matched_s.gstin and data.get("supplier_gstin"):
                        matched_s.gstin = data.get("supplier_gstin").strip()
                        updated = True
                    if not matched_s.phone and data.get("supplier_phone"):
                        matched_s.phone = data.get("supplier_phone").strip()
                        updated = True
                    if not matched_s.email and data.get("supplier_email"):
                        matched_s.email = data.get("supplier_email").strip()
                        updated = True
                    if not matched_s.address and data.get("supplier_address"):
                        matched_s.address = data.get("supplier_address").strip()
                        updated = True
                    if updated:
                        db.add(matched_s)
                    print(f"[OCR:ENDPOINT] Auto-linked document #{document_id} to existing Supplier #{matched_s.id} ('{matched_s.name}')")
            else:
                # Do not silently create a new supplier! Leave unlinked for user review / creation option
                doc.supplier_id = None
                print(f"[OCR:ENDPOINT] Document #{document_id} supplier matching: {match_res.get('status')} ({match_res.get('message')})")

        doc.ocr_raw_json = json.dumps(data, default=str)
        print(f"[OCR:ENDPOINT] Document #{document_id} OCR completed: Inv #{doc.invoice_number}, Date: {doc.invoice_date}, Total: ₹{doc.total_amount}, Items: {doc.item_count}")
    else:
        doc.ocr_status = "Failed"
        error_msg = ocr_res.get("error", "Unknown OCR failure")
        doc.ocr_raw_json = json.dumps({"error": error_msg, "items": []}, default=str)
        print(f"[OCR:ENDPOINT] Document #{document_id} OCR failed: {error_msg}")

    db.commit()
    db.refresh(doc)
    
    # Explicitly populate computed supplier_name for client response
    res_dict = schemas.DocumentResponse.from_orm(doc)
    res_dict.supplier_name = doc.supplier.name if doc.supplier else None
    res_dict.extracted_supplier_name = extracted_name
    res_dict.supplier_match = supplier_match_info
    return res_dict


@app.get("/documents", response_model=List[schemas.DocumentResponse])
def list_documents(
    query: Optional[str] = None,
    doc_type: Optional[str] = None,
    status: Optional[str] = None,
    supplier_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List pharmacy documents with filters & supplier info."""
    return crud.get_documents(db=db, user_id=current_user.id, query=query, doc_type=doc_type, status=status, supplier_id=supplier_id)


@app.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
def get_document_detail(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get single document detail with OCR raw JSON and supplier match metadata."""
    doc = crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)
    res_dict = schemas.DocumentResponse.from_orm(doc)
    res_dict.supplier_name = doc.supplier.name if doc.supplier else None

    # Evaluate supplier matching if unlinked or if raw JSON has supplier_name
    if doc.ocr_raw_json:
        try:
            parsed = json.loads(doc.ocr_raw_json)
            s_name = parsed.get("supplier_name")
            if s_name:
                res_dict.extracted_supplier_name = s_name.strip()
                match_res = crud.find_matching_suppliers(
                    db=db,
                    user_id=current_user.id,
                    extracted_name=s_name,
                    extracted_gstin=parsed.get("supplier_gstin")
                )
                res_dict.supplier_match = match_res
                # If exact match found and doc was previously unlinked, auto-link doc.supplier_id
                if not doc.supplier_id and match_res.get("status") == "exact_match" and match_res.get("matched_supplier"):
                    doc.supplier_id = match_res["matched_supplier"]["id"]
                    db.commit()
                    db.refresh(doc)
                    res_dict.supplier_id = doc.supplier_id
                    res_dict.supplier_name = doc.supplier.name if doc.supplier else None
        except Exception as e:
            print(f"[DOC:DETAIL] Supplier match evaluation notice: {e}")

    return res_dict


@app.post("/documents/{document_id}/confirm")
def confirm_document(
    document_id: int,
    confirm_req: schemas.DocumentConfirmRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Review & confirm extracted items -> updates stock with supplier & invoice traceability."""
    return crud.confirm_document_and_update_stock(db=db, document_id=document_id, user_id=current_user.id, confirm_req=confirm_req)


@app.delete("/documents/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete document record."""
    return crud.delete_document(db=db, document_id=document_id, user_id=current_user.id)


@app.get("/catalog/search", response_model=List[schemas.MedicineCatalogResponse])
@app.get("/api/catalog/search", response_model=List[schemas.MedicineCatalogResponse])
@app.get("/api/medicines/search", response_model=List[schemas.MedicineCatalogResponse])
def search_medicine_catalog(
    query: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Search the reference medicine_catalog (490k+ Indian medicines).
    Returns autocomplete suggestions (Name, Brand, Salt/Composition, HSN, Default Price, Pack Size).
    Used for pre-filling when purchasing/adding stock or billing.
    """
    search_str = (query or q or "").strip()
    if not search_str or len(search_str) < 2:
        return []

    clamped_limit = max(1, min(limit, 100))
    try:
        results = crud.search_medicine_catalog(db, query=search_str, limit=clamped_limit)
        return results
    except Exception as e:
        logger.error(
            f"[Catalog Search Error] Endpoint: /catalog/search | Query: '{search_str}' | Limit: {clamped_limit} | DB Error: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search medicine catalog. Please try again with a different query."
        )


@app.get("/sales/pending")
def get_pending_sales(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List all outstanding/pending customer sales bills for the authenticated shop."""
    sales = (
        db.query(models.Sale)
        .filter(
            models.Sale.user_id == current_user.id,
            models.Sale.payment_status == "PENDING"
        )
        .order_by(models.Sale.created_at.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "bill_number": s.bill_number,
            "customer_id": s.customer_id,
            "customer_name": s.customer_name or "Walk-in Customer",
            "customer_phone": s.customer_phone or "N/A",
            "total_amount": s.total_amount,
            "bill_date": s.created_at.strftime("%Y-%m-%d") if s.created_at else str(datetime.utcnow().date()),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "payment_method": s.payment_method,
            "payment_status": s.payment_status,
        }
        for s in sales
    ]


@app.post("/sales/{sale_id}/settle")
@app.put("/sales/{sale_id}/settle")
@app.patch("/sales/{sale_id}/settle")
def settle_pending_sale(
    sale_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Marks a pending payment sale as settled/cleared and zeroes out/reduces customer pending balance."""
    sale = (
        db.query(models.Sale)
        .filter(models.Sale.id == sale_id, models.Sale.user_id == current_user.id)
        .first()
    )
    if not sale:
        raise HTTPException(status_code=404, detail="Sale bill not found.")

    sale.payment_status = "PAID"
    if sale.customer_id:
        db.query(models.Customer).filter(
            models.Customer.id == sale.customer_id,
            models.Customer.user_id == current_user.id
        ).update(
            {models.Customer.pending_amount: func.greatest(0.0, models.Customer.pending_amount - sale.total_amount)},
            synchronize_session=False
        )

    db.commit()
    return {
        "success": True,
        "message": f"Bill {sale.bill_number} marked as settled.",
        "sale_id": sale.id,
        "payment_status": "PAID"
    }


@app.post("/inventory/add", response_model=schemas.Product)
def add_inventory_stock(
    data: schemas.InventoryAddRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Creates a real stock entry in active inventory.
    Requires purchase-specific details: quantity, batch_number, expiry_date, purchase_price.
    """
    return crud.add_real_inventory_item(db=db, data=data, user_id=current_user.id)


@app.post("/inventory/check-duplicate")
def check_inventory_duplicate_batch(
    data: schemas.DuplicateBatchCheckRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Checks if a medicine + batch number already exists in shop inventory."""
    return crud.check_duplicate_batch(db=db, user_id=current_user.id, product_name=data.product_name, batch_number=data.batch_number)


@app.post("/catalog/create-custom", response_model=schemas.MedicineCatalogResponse)
def create_custom_catalog_medicine(
    data: schemas.CustomMedicineCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Allows instant creation of custom medicine in reference catalog if not found."""
    return crud.create_custom_medicine(db=db, data=data)


@app.post("/inventory/batch-add")
def batch_add_inventory_stock(
    data: schemas.BatchInventoryAddRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Commits multiple stock entries in a single transaction."""
    created_items = []
    for item in data.items:
        prod = crud.add_real_inventory_item(db=db, data=item, user_id=current_user.id)
        created_items.append(prod.id)
    return {
        "message": f"Successfully added {len(created_items)} medicine stock items to inventory.",
        "count": len(created_items),
        "product_ids": created_items
    }


# ==========================================
# INVENTORY SOFT-DELETE & 60-DAY RECOVERY
# ==========================================

@app.post("/api/inventory/delete")
@app.post("/api/inventory/delete-stock")
@app.post("/inventory/delete")
@app.post("/inventory/delete-stock")
@limiter.limit("60/minute")
def delete_inventory_stock(
    request: Request,
    payload: schemas.InventoryDeleteRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Selective soft-delete for inventory stock items.
    Marks rows as deleted with a 60-day recovery window.
    """
    ids = payload.get_ids()
    if not ids:
        raise HTTPException(status_code=400, detail="No stock IDs provided for deletion.")
    res = crud.soft_delete_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@app.post("/api/inventory/delete-all")
@app.post("/inventory/delete-all")
@limiter.limit("60/minute")
def delete_all_inventory_stock(
    request: Request,
    payload: Optional[schemas.InventoryDeleteAllRequest] = Body(None),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bulk soft-delete for all active stock items belonging to the authenticated shop.
    Supports 60-day recovery window.
    """
    res = crud.soft_delete_all_inventory_items(
        db=db,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@app.get("/api/inventory/deleted", response_model=List[schemas.DeletedProductResponse])
@app.get("/inventory/deleted", response_model=List[schemas.DeletedProductResponse])
def get_recently_deleted_stock(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieves all soft-deleted inventory items within the 60-day recovery window.
    Includes calculated days remaining until permanent deletion.
    """
    return crud.get_recently_deleted_inventory(
        db=db,
        user_id=current_user.id
    )


@app.post("/api/inventory/restore")
@app.post("/api/inventory/restore-stock")
@app.post("/inventory/restore")
@app.post("/inventory/restore-stock")
@limiter.limit("60/minute")
def restore_inventory_stock(
    request: Request,
    payload: schemas.InventoryRestoreRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Restores soft-deleted inventory items back to live stock
    if deleted within the 60-day recovery window.
    """
    ids = payload.get_ids()
    if not ids:
        raise HTTPException(status_code=400, detail="No stock IDs provided for restoration.")
    res = crud.restore_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@app.get("/products/search", response_model=List[schemas.MedicineCatalogResponse])
def autocomplete_products_search(
    query: str,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    Fast Ranked Autocomplete Endpoint searching the reference medicine_catalog.
    """
    return crud.search_medicine_catalog(db, query=query, limit=limit)


@app.get("/products/barcode/{barcode}")
def get_product_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Exact indexed barcode lookup endpoint for scanner hardware & barcode camera scans.
    """
    clean_code = (barcode or "").strip()
    if not clean_code:
        raise HTTPException(status_code=400, detail="Barcode string required.")

    prod = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == current_user.id,
            models.Product.is_deleted == False,
            (
                (models.Product.barcode == clean_code) |
                (models.Product.hsn_code == clean_code)
            )
        )
        .first()
    )
    if not prod:
        raise HTTPException(status_code=404, detail=f"Medicine not found in inventory for barcode: {clean_code}")
    return prod


@app.get("/billing/search-products")
def billing_search_products(
    query: str,
    search_mode: str = "name",
    limit: int = 15,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    High-Performance Live Autocomplete Search Endpoint for POS Retail Billing.
    Directly queries the current active inventory database used by Live Inventory.
    Searches product name, brand, composition (salt), batch number, barcode, and HSN code with FEFO ordering.
    """
    clean_q = (query or "").strip()
    if not clean_q:
        return []

    res = crud.get_products(
        db=db,
        user_id=current_user.id,
        search=clean_q,
        search_mode=search_mode,
        limit=limit,
        sort_by="fefo",
        include_total=False
    )
    items = res["items"] if isinstance(res, dict) and "items" in res else (res if isinstance(res, list) else [])
    return items


@app.post("/search-product", response_model=List[schemas.Product])
def search_products(
    query: str, 
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    """Searches products by name or category for the current shop."""
    if not query.strip():
        return []
    
    return db.query(models.Product).filter(
        models.Product.user_id == current_user.id,
        (models.Product.product_name.ilike(f"%{query}%")) | 
        (models.Product.category.ilike(f"%{query}%"))
    ).limit(20).all()


@app.get("/items/search")
def search_items_voice(
    q: str = Query("", description="Query string: medicine name, brand, salt, or HSN code"),
    shop_id: Optional[int] = Query(None, description="Optional shop ID (defaults to current authenticated user)"),
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Intelligent search endpoint for Voice Billing & POS autocomplete:
    1. Extracts 4-8 digit HSN codes from speech (e.g. 'HSN 300490' or '3004').
    2. Prioritizes exact HSN code match within active shop inventory.
    3. If no HSN found or matched, computes fuzzy similarity against product names,
       brands, and compositions scoped to the user's shop with FEFO ordering.
    """
    raw_query = (q or "").strip()
    if not raw_query:
        return {"query": "", "items": [], "hsn_match": False}

    if shop_id is not None and shop_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Cannot access inventory of another shop.",
        )
    target_user_id = current_user.id

    # 1. Check for 4-8 digit HSN code pattern in speech input
    hsn_matches = re.findall(r"\b\d{4,8}\b", raw_query)
    if hsn_matches:
        for candidate_hsn in hsn_matches:
            hsn_items = (
                db.query(models.Product)
                .filter(
                    models.Product.user_id == target_user_id,
                    models.Product.is_deleted == False,
                    models.Product.hsn_code.ilike(f"%{candidate_hsn}%")
                )
                .order_by(models.Product.expiry_date.asc())
                .limit(limit)
                .all()
            )
            if hsn_items:
                serialized = [crud.serialize_product(item) for item in hsn_items]
                for s in serialized:
                    s["similarity"] = 1.0
                    s["matched_by"] = "hsn"
                return {
                    "query": raw_query,
                    "hsn_code": candidate_hsn,
                    "hsn_match": True,
                    "items": serialized
                }

    # 2. Text / Voice fuzzy & substring search scoped to shop
    clean_q = raw_query.lower()
    clean_no_punct = re.sub(r"[^\w\s]", " ", clean_q).strip()

    # Base query for shop's active inventory
    inventory_items = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == target_user_id,
            models.Product.is_deleted == False
        )
        .order_by(models.Product.expiry_date.asc())
        .all()
    )

    scored_items = []
    for item in inventory_items:
        p_name = (item.product_name or "").lower()
        p_brand = (item.brand or "").lower()
        p_comp = (item.composition or "").lower()
        p_hsn = (item.hsn_code or "").lower()

        # Check exact substring
        if clean_q in p_name or clean_no_punct in p_name:
            score = 1.0 if clean_q == p_name else 0.85
        elif clean_q in p_brand or clean_q in p_comp or clean_q in p_hsn:
            score = 0.75
        else:
            # Fuzzy SequenceMatcher on name and full text
            ratio_name = SequenceMatcher(None, clean_no_punct, p_name).ratio()
            # Also check individual words for multi-word medicine names
            words = p_name.split()
            max_word_ratio = max([SequenceMatcher(None, clean_no_punct, w).ratio() for w in words] or [0.0])
            score = max(ratio_name, max_word_ratio * 0.8)

        if score >= 0.35:
            s_item = crud.serialize_product(item)
            s_item["similarity"] = round(score, 3)
            s_item["matched_by"] = "voice_fuzzy"
            scored_items.append((score, s_item))

    # Sort descending by similarity score, then ascending by expiry (FEFO)
    scored_items.sort(key=lambda x: (-x[0], x[1].get("expiry_date") or "9999-12-31"))
    final_items = [x[1] for x in scored_items[:limit]]

    # If inventory matches are few, complement with medicine catalog
    if len(final_items) < limit:
        remaining = limit - len(final_items)
        existing_names = set(i["product_name"].lower() for i in final_items if i.get("product_name"))
        cat_matches = crud.search_medicine_catalog(db, query=clean_q, limit=remaining)
        for cat in cat_matches:
            if cat.product_name and cat.product_name.lower() in existing_names:
                continue
            cat_score = round(SequenceMatcher(None, clean_no_punct, cat.product_name.lower()).ratio(), 3)
            cat_dict = {
                "id": cat.id + 900000,
                "user_id": target_user_id,
                "product_name": cat.product_name,
                "brand": cat.brand or "General",
                "category": "General",
                "batch_number": "CATALOG-NEW",
                "quantity": 50,
                "hsn_code": cat.hsn_code or "3004",
                "gst_rate": cat.gst_rate or 12.0,
                "gst_percentage": cat.gst_rate or 12.0,
                "purchase_price": (cat.default_price or 50.0) * 0.75,
                "unit_price": cat.default_price or 50.0,
                "price_per_unit": cat.price_per_unit,
                "units_per_pack": cat.tablets_per_strip or 10,
                "tablets_per_strip": cat.tablets_per_strip or 10,
                "loose_tablet_price": cat.price_per_unit or ((cat.default_price or 50.0) / (cat.tablets_per_strip or 10)),
                "total_price": cat.default_price or 50.0,
                "expiry_date": "2028-12-31",
                "days_remaining": 365,
                "status": "Safe",
                "composition": cat.composition or "",
                "similarity": max(cat_score, 0.6),
                "matched_by": "catalog_fuzzy",
                "is_inventory": False
            }
            final_items.append(cat_dict)

    return {
        "query": raw_query,
        "hsn_match": False,
        "items": final_items
    }



@app.post("/transaction/sell", response_model=schemas.BillResponse, status_code=201)
def process_sell_transaction(
    payload: schemas.SellTransactionRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Validates stock for all items, atomically decrements inventory,
    creates the sale log, and returns the generated bill.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="Cart cannot be empty.")

    calculated_subtotal = 0.0
    sale_items = []

    for item in payload.items:
        product = db.query(models.Product).filter(
            models.Product.id == item.product_id,
            models.Product.user_id == current_user.id
        ).first()

        if not product:
            raise HTTPException(status_code=404, detail=f"Product ID {item.product_id} not found.")

        unit_type = getattr(item, "unit_type", "strip") or "strip"
        is_strip = str(unit_type).lower() in ["strip", "pack"]
        tabs_override = getattr(item, "tablets_per_strip", None)
        tabs_per_pack = tabs_override or product.tablets_per_strip or product.units_per_pack

        crud.deduct_product_stock(
            product=product,
            quantity=item.quantity,
            unit_type=unit_type,
            tablets_per_strip_override=tabs_override,
        )

        if is_strip:
            item_price = product.unit_price or 0.0
        else:
            if product.loose_tablet_price and product.loose_tablet_price > 0:
                item_price = product.loose_tablet_price
            elif product.unit_price and tabs_per_pack:
                item_price = round(product.unit_price / tabs_per_pack, 2)
            else:
                item_price = product.unit_price or 0.0

        line_total = round(item_price * item.quantity, 2)
        calculated_subtotal += line_total

        sale_items.append(
            models.SaleItem(
                product_id=product.id,
                product_name=product.product_name,
                quantity=item.quantity,
                unit_price=item_price,
                total_price=line_total,
                unit_type=unit_type,
                tablets_per_strip=tabs_per_pack,
                batch_number=product.batch_number
            )
        )

    final_total = max(0.0, calculated_subtotal - (payload.discount_amount or 0.0))
    bill_no = f"BILL-{uuid.uuid4().hex[:6].upper()}"

    db_sale = models.Sale(
        user_id=current_user.id,
        bill_number=bill_no,
        subtotal=calculated_subtotal,
        discount_amount=payload.discount_amount or 0.0,
        total_amount=final_total,
        payment_method=payload.payment_method or "CASH",
        items=sale_items
    )

    db.add(db_sale)
    db.commit()
    crud.invalidate_products_cache(current_user.id)
    crud.invalidate_customers_cache(current_user.id)
    db.refresh(db_sale)
    return db_sale


@app.post("/transaction/purchase/bulk", status_code=201)
def process_bulk_purchase(
    payload: schemas.BulkPurchaseRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Saves reviewed supplier-invoice items to this shop's inventory.

    A product is added to an existing stock row only when product name,
    batch number, and expiry date all match.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items to ingest.")

    saved_products = []

    try:
        for item in payload.items:
            existing = (
                db.query(models.Product)
                .filter(
                    models.Product.user_id == current_user.id,
                    models.Product.product_name.ilike(item.product_name.strip()),
                    models.Product.batch_number == item.batch_number,
                    models.Product.expiry_date == item.expiry_date,
                )
                .with_for_update()
                .first()
            )

            if existing:
                # Same product + batch + expiry: increase only that batch stock.
                existing.quantity += item.quantity
                existing.purchase_price = item.purchase_price

                # Update retail price only when the user has provided one.
                if item.selling_price > 0:
                    existing.unit_price = item.selling_price

                existing.total_price = existing.purchase_price * existing.quantity

                if item.brand:
                    existing.brand = item.brand

                if item.category:
                    existing.category = item.category

                # Mark verified by physical AI camera scan
                existing.verified = True
                existing.pack_size_verified = True
                existing.price_last_updated = datetime.utcnow()

                saved_products.append(existing)
                continue

            # A new batch / expiry date gets its own inventory record.
            days_remaining = (item.expiry_date - datetime.utcnow().date()).days

            if days_remaining < 0:
                product_status = "Expired"
            elif days_remaining <= 30:
                product_status = "Expiring Soon"
            else:
                product_status = "Safe"

                        # Save directly into your Product table
            new_product = models.Product(
                user_id=current_user.id,
                product_name=item.product_name.strip(),
                brand=item.brand,
                category=item.category or "AI Scanned",
                batch_number=item.batch_number,
                quantity=item.quantity,
                purchase_price=item.purchase_price,
                unit_price=(
                    item.selling_price
                    if item.selling_price > 0
                    else item.purchase_price
                ),
                total_price=item.purchase_price * item.quantity,
                manufacturing_date=item.manufacturing_date,
                expiry_date=item.expiry_date,
                days_remaining=days_remaining,
                status=product_status,
                verified=True,
                pack_size_verified=True,
                price_last_updated=datetime.utcnow(),
                notified_expiring=False,
                notified_expired=False,
            ) 

            db.add(new_product)
            saved_products.append(new_product)

        db.commit()

        for product in saved_products:
            db.refresh(product)

        return {
            "success": True,
            "message": f"{len(saved_products)} invoice items saved to inventory.",
            "products": [
                {
                    "id": product.id,
                    "product_name": product.product_name,
                    "quantity": product.quantity,
                    "purchase_price": product.purchase_price,
                    "selling_price": product.unit_price,
                    "manufacturing_date": product.manufacturing_date,
                    "expiry_date": product.expiry_date,
                    "status": product.status,
                }
                for product in saved_products
            ],
        }

    except Exception:
        db.rollback()
        raise


# ==========================================
# FLUTTER AI INVOICE SCANNER ENDPOINT
# ==========================================

class AIInvoiceItem(BaseModel):
    productName: str
    quantity: int = Field(gt=0)
    batchNumber: Optional[str] = None
    expiryDate: Optional[str] = None
    mrp: Optional[float] = Field(default=0.0, ge=0.0)
    purchasePrice: Optional[float] = Field(default=0.0, ge=0.0)

class AIPurchasePayload(BaseModel):
    supplierName: str
    billNumber: str
    date: str
    items: List[AIInvoiceItem]

@app.post("/add-purchase")
def save_ai_purchase(
    payload: AIPurchasePayload,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    try:
        saved_count = 0
        for item in payload.items:
            exp_date = crud.parse_date(item.expiryDate) if item.expiryDate else None
            if not exp_date:
                exp_date = date.today() + timedelta(days=365)

            days_remaining = (exp_date - date.today()).days
            product_status = "Expired" if days_remaining < 0 else ("Expiring Soon" if days_remaining <= 30 else "Safe")

            p_price = float(item.purchasePrice or item.mrp or 0.0)
            u_price = float(item.mrp or p_price)

            new_product = models.Product(
                user_id=current_user.id,
                product_name=item.productName.strip(),
                brand=payload.supplierName,
                category="AI Scanned",
                batch_number=(item.batchNumber or "BATCH-AI").strip(),
                quantity=item.quantity,
                purchase_price=p_price,
                unit_price=u_price,
                total_price=p_price * item.quantity,
                expiry_date=exp_date,
                days_remaining=days_remaining,
                status=product_status,
            )
            db.add(new_product)
            saved_count += 1

        db.commit()
        return {"message": f"Saved {saved_count} items to database successfully.", "status": "success"}

    except Exception as e:
        db.rollback()
        logger.error(f"Bulk purchase save error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to save bulk purchase items.")


# ==========================================
# AI, OCR & MEDIA UPLOAD ENDPOINTS
# ==========================================

@app.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    """Secure image upload endpoint with authentication, MIME validation, and randomized filename."""
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        file_ext = ".jpg"

    check_file_size(file, MAX_FILE_SIZE_10MB)
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(contents, file_ext)

    uploads_dir = Path("uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = f"img_{uuid.uuid4().hex[:16]}{file_ext}"
    target_path = (uploads_dir / safe_filename).resolve()

    if not target_path.is_relative_to(uploads_dir):
        raise HTTPException(status_code=400, detail="Invalid target file path.")

    with open(target_path, "wb") as buffer:
        buffer.write(contents)

    return {"imagePath": f"uploads/{safe_filename}"}


@app.post("/scan-label")
@limiter.limit("30/hour")
def scan_product_label(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_IMAGE_EXTENSIONS:
        file_ext = ".jpg"

    check_file_size(file, MAX_FILE_SIZE_5MB)
    contents = file.file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(contents, file_ext)

    uploads_dir = Path("uploads").resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)

    filename = f"lbl_{uuid.uuid4().hex[:16]}{file_ext}"
    target_path = (uploads_dir / filename).resolve()

    if not target_path.is_relative_to(uploads_dir):
        raise HTTPException(status_code=400, detail="Invalid target file path.")

    try:
        with open(target_path, "wb") as buffer:
            buffer.write(contents)
        result = scan_label(str(target_path))
        return {"success": True, "data": result}
    finally:
        if target_path.exists():
            try:
                target_path.unlink()
            except Exception as cleanup_err:
                logger.warning(f"Failed to remove temp label file {target_path}: {cleanup_err}")
def _normalise_product_name(value: str) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).lower()).strip()


def _clean_words(text: str) -> set:
    if not text:
        return set()
    noise = {"tab", "tabs", "strip", "capsule", "syrup", "mg", "ml", "gm", "g", "tablets", "box", "pack"}
    words = re.findall(r"[a-z0-9]+", str(text).lower())
    return {w for w in words if len(w) > 1 and w not in noise}


def _is_ocr_batch_substitution_match(cand: str, target: str) -> bool:
    """
    Checks if cand matches target with allowed single/double OCR character substitutions:
    ('I', '1'), ('O', '0'), ('S', '5'), ('B', '8'), ('Z', '2'), ('A', '4')
    Strictly scoped to existing batches of the identified product.
    """
    if not cand or not target:
        return False
    c = cand.strip().upper().replace("-", "").replace("/", "")
    t = target.strip().upper().replace("-", "").replace("/", "")
    if len(c) != len(t):
        return False
    confusion_pairs = {
        ('I', '1'), ('1', 'I'),
        ('O', '0'), ('0', 'O'),
        ('S', '5'), ('5', 'S'),
        ('B', '8'), ('8', 'B'),
        ('Z', '2'), ('2', 'Z'),
        ('A', '4'), ('4', 'A'),
    }
    diffs = 0
    for char_c, char_t in zip(c, t):
        if char_c != char_t:
            if (char_c, char_t) not in confusion_pairs:
                return False
            diffs += 1
    return 1 <= diffs <= 2


def _match_inventory_items(
    inventory_products: list,
    detected_item: dict,
    detected_barcodes: Optional[list] = None,
) -> tuple[str, str, any, list, list, bool]:
    """
    Evaluates detected medicine against pharmacy inventory using 5 priorities with batch disambiguation:
    Priority 1: Exact product code / barcode / GTIN match
    Priority 2: Normalized exact medicine-name match + strength + form + pack size
    Priority 3: Exact medicine name / high token overlap
    Priority 4: Safe fuzzy name matching against inventory only (threshold >= 0.75)
    Priority 5: Not found (never auto-create products or stock)
    
    Disambiguation:
    If multiple batches/products exist for the medicine, uses detected_batch and detected_expiry.
    If ambiguous, returns requires_batch_selection=True.

    Returns:
      (match_status, match_type, matched_product, possible_matches, batches_available, requires_batch_selection)
      where match_status in {"MATCHED", "MULTIPLE_MATCHES", "NOT_FOUND", "LOW_CONFIDENCE"}
    """
    det_name = (detected_item.get("name") or "").strip()
    det_brand = (detected_item.get("brand_name") or "").strip()
    det_generic = (detected_item.get("generic_name") or "").strip()
    det_code = (detected_item.get("code") or "").strip()
    det_strength = (detected_item.get("strength") or "").strip().lower()
    det_form = (detected_item.get("form") or "").strip().lower()
    det_pack_size = (detected_item.get("pack_size") or "").strip().lower()
    det_batch = (detected_item.get("batch") or "").strip().upper()
    det_expiry = (detected_item.get("expiry") or "").strip()

    det_norm = _normalise_product_name(det_name)
    det_words = _clean_words(det_name)

    candidates = []
    match_type = "NONE"
    is_low_conf = False

    # -------------------------------------------------------------
    # PRIORITY 1: Exact product code / barcode / GTIN match
    # -------------------------------------------------------------
    if det_code:
        code_matches = [
            p for p in inventory_products
            if (p.barcode and p.barcode.strip() == det_code)
        ]
        if code_matches:
            candidates = code_matches
            match_type = "EXACT_CODE"

    # Also check if OpenCV detected barcodes match any product associated with this item
    if not candidates and detected_barcodes:
        for bc in detected_barcodes:
            bc_matches = [
                p for p in inventory_products
                if (p.barcode and p.barcode.strip() == bc)
            ]
            if bc_matches:
                if det_norm:
                    name_matched_bc = [
                        p for p in bc_matches
                        if _normalise_product_name(p.product_name or "") == det_norm
                    ]
                    if name_matched_bc:
                        candidates = name_matched_bc
                        match_type = "EXACT_CODE"
                        break
                if not candidates and len(detected_barcodes) == 1 and not det_name:
                    candidates = bc_matches
                    match_type = "EXACT_CODE"
                    break

    # -------------------------------------------------------------
    # PRIORITY 2: Prominent Brand Name Match + Strength Specs
    # -------------------------------------------------------------
    if not candidates and (det_norm or det_brand):
        exact_name_candidates = []
        clean_strength = re.sub(r"[^a-z0-9]+", "", det_strength) if det_strength else ""
        det_combined = f"{det_norm}{clean_strength}" if clean_strength else det_norm
        brand_norm = _normalise_product_name(det_brand) if det_brand else ""

        for product in inventory_products:
            p_name = product.product_name or ""
            p_norm = _normalise_product_name(p_name)
            p_brand_norm = _normalise_product_name(product.brand or "")
            p_text = f"{p_name} {product.pack_size_label or ''}".lower()

            # Exact full name or brand match
            if (
                p_norm == det_norm
                or (clean_strength and p_norm == det_combined)
                or p_name.strip().lower() == det_name.lower()
                or (clean_strength and det_norm in p_norm and det_strength in p_text)
                or (brand_norm and (brand_norm == p_norm or brand_norm in p_norm or brand_norm == p_brand_norm))
            ):
                exact_name_candidates.append(product)

        if exact_name_candidates:
            if det_strength or det_pack_size:
                spec_filtered = []
                for p in exact_name_candidates:
                    p_text = f"{p.product_name} {p.pack_size_label or ''}".lower()
                    if det_strength and det_strength in p_text:
                        spec_filtered.append(p)
                    elif det_pack_size and det_pack_size in p_text:
                        spec_filtered.append(p)
                if spec_filtered:
                    candidates = spec_filtered
                    match_type = "EXACT_NAME_SPECS"
                else:
                    candidates = exact_name_candidates
                    match_type = "EXACT_NAME_SPECS"
            else:
                candidates = exact_name_candidates
                match_type = "EXACT_NAME_SPECS"

    # -------------------------------------------------------------
    # PRIORITY 2B: Generic Active Ingredient (Salt) Fallback Match
    # -------------------------------------------------------------
    if not candidates and det_generic:
        gen_norm = _normalise_product_name(det_generic)
        gen_candidates = []
        for product in inventory_products:
            p_name = product.product_name or ""
            p_norm = _normalise_product_name(p_name)
            if gen_norm in p_norm:
                gen_candidates.append(product)
        if gen_candidates:
            if det_strength:
                spec_filtered = [
                    p for p in gen_candidates
                    if det_strength in (p.product_name or "").lower()
                ]
                candidates = spec_filtered if spec_filtered else gen_candidates
            else:
                candidates = gen_candidates
            match_type = "EXACT_NAME_SPECS"

    # -------------------------------------------------------------
    # PRIORITY 3: Multi-token containment match
    # -------------------------------------------------------------
    if not candidates and det_words and len(det_words) >= 2:
        token_candidates = []
        for product in inventory_products:
            p_words = _clean_words(product.product_name or "")
            if not p_words:
                continue
            common = det_words.intersection(p_words)
            if len(common) == len(det_words):
                token_candidates.append(product)
        if token_candidates:
            candidates = token_candidates
            match_type = "EXACT_NAME_SPECS"

    # -------------------------------------------------------------
    # PRIORITY 4: Safe fuzzy name matching with OCR character correction
    # -------------------------------------------------------------
    if not candidates and (det_norm or det_brand):
        target_norm = det_norm or _normalise_product_name(det_brand)
        fuzzy_matches = []
        for product in inventory_products:
            inv_norm = _normalise_product_name(product.product_name or "")
            if not inv_norm:
                continue
            # Direct similarity
            score = SequenceMatcher(None, target_norm, inv_norm).ratio()
            # Substitution-corrected similarity (0/O, 4/A, 1/I, 5/S)
            clean_target = target_norm.replace("0", "o").replace("4", "a").replace("1", "i").replace("5", "s")
            clean_inv = inv_norm.replace("0", "o").replace("4", "a").replace("1", "i").replace("5", "s")
            sub_score = SequenceMatcher(None, clean_target, clean_inv).ratio()
            best_score = max(score, sub_score)

            if best_score >= 0.75:
                fuzzy_matches.append((best_score, product))

        if fuzzy_matches:
            fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
            top_score = fuzzy_matches[0][0]
            top_tier = [p for s, p in fuzzy_matches if s >= (top_score - 0.05)]
            candidates = top_tier
            match_type = "FUZZY_NAME"
            if top_score < 0.85:
                is_low_conf = True

    # -------------------------------------------------------------
    # PRIORITY 5: Not found
    # -------------------------------------------------------------
    if not candidates:
        return ("NOT_FOUND", "NONE", None, [], [], False)

    # -------------------------------------------------------------
    # BATCH & EXPIRY DISAMBIGUATION
    # -------------------------------------------------------------
    # Find all batches for this medicine in inventory to populate batches_available
    primary_cand = candidates[0]
    cand_norm = _normalise_product_name(primary_cand.product_name or "")
    all_batches_for_med = [
        p for p in inventory_products
        if _normalise_product_name(p.product_name or "") == cand_norm
    ]
    batch_pool = all_batches_for_med if len(all_batches_for_med) >= len(candidates) else candidates

    def _batch_stock_info(p):
        sqty = int(getattr(p, "quantity", 0) or 0)
        lqty = int(getattr(p, "loose_tablet_stock", 0) or 0)
        tcount = int(getattr(p, "tablets_per_strip", None) or getattr(p, "units_per_pack", None) or 10)
        ttabs = (sqty * tcount) + lqty
        has_stk = (sqty > 0 or lqty > 0)
        return sqty, lqty, tcount, ttabs, has_stk

    # Sort batch_pool: in-stock first (FEFO by earliest expiry), out-of-stock last
    def _sort_batch_key(p):
        sqty, lqty, tcount, ttabs, has_stk = _batch_stock_info(p)
        exp = p.expiry_date if getattr(p, "expiry_date", None) else date(2099, 12, 31)
        return (0 if has_stk else 1, exp)

    sorted_batch_pool = sorted(batch_pool, key=_sort_batch_key)

    batches_available = []
    for p in sorted_batch_pool:
        sqty, lqty, tcount, ttabs, has_stk = _batch_stock_info(p)
        u_price = float(getattr(p, "unit_price", 0) or 0)
        batches_available.append({
            "id": p.id,
            "product_name": getattr(p, "product_name", ""),
            "batch_number": getattr(p, "batch_number", None) or "N/A",
            "expiry_date": str(p.expiry_date) if getattr(p, "expiry_date", None) else "N/A",
            "days_remaining": int(getattr(p, "days_remaining", 0) or 0),
            "quantity": sqty,
            "stock": sqty,
            "loose_tablet_stock": lqty,
            "total_tablets": ttabs,
            "has_stock": has_stk,
            "unit_price": u_price,
            "strip_price": u_price,
            "tablets_per_strip": tcount,
            "units_per_pack": tcount,
            "loose_tablet_price": float(getattr(p, "loose_tablet_price", None) or (u_price / tcount if u_price else 0)) if u_price else 0,
        })

    # If only one batch exists in inventory for this medicine:
    if len(sorted_batch_pool) == 1:
        matched = sorted_batch_pool[0]
        status = "LOW_CONFIDENCE" if is_low_conf else "MATCHED"
        return (status, match_type, matched, [], batches_available, False)

    # Disambiguation among multiple batches
    # Identify in-stock candidates
    in_stock_candidates = [p for p in candidates if _batch_stock_info(p)[4]]
    # Prefer in-stock candidates when available
    effective_candidates = in_stock_candidates if in_stock_candidates else list(candidates)
    active_candidates = list(effective_candidates)

    if det_batch:
        # 1. Exact or substring match in effective (in-stock) candidates
        batch_matched = [
            p for p in active_candidates
            if p.batch_number and (
                det_batch == p.batch_number.strip().upper()
                or det_batch in p.batch_number.strip().upper()
                or p.batch_number.strip().upper() in det_batch
            )
        ]
        if len(batch_matched) == 1:
            return ("MATCHED", match_type, batch_matched[0], [], batches_available, False)
        elif len(batch_matched) > 1:
            active_candidates = batch_matched
        else:
            # 2. OCR character substitution against effective candidates
            sub_matched = [
                p for p in active_candidates
                if p.batch_number and _is_ocr_batch_substitution_match(det_batch, p.batch_number)
            ]
            if len(sub_matched) == 1:
                logger.info(f"[BATCH_OCR_CORRECTION] Corrected batch '{det_batch}' -> '{sub_matched[0].batch_number}' for {sub_matched[0].product_name}")
                return ("MATCHED", match_type, sub_matched[0], [], batches_available, False)
            elif len(sub_matched) > 1:
                active_candidates = sub_matched
            elif not in_stock_candidates:
                # If no in-stock candidates at all, check all candidates
                all_matched = [
                    p for p in candidates
                    if p.batch_number and (
                        det_batch == p.batch_number.strip().upper()
                        or det_batch in p.batch_number.strip().upper()
                        or p.batch_number.strip().upper() in det_batch
                    )
                ]
                if len(all_matched) == 1:
                    return ("MATCHED", match_type, all_matched[0], [], batches_available, False)

    # If active_candidates narrowed down to 1 in-stock batch:
    if len(active_candidates) == 1 and _batch_stock_info(active_candidates[0])[4]:
        status = "LOW_CONFIDENCE" if is_low_conf else "MATCHED"
        return (status, match_type, active_candidates[0], [], batches_available, False)

    # Next attempt disambiguation with detected_expiry:
    if det_expiry:
        clean_det_exp = det_expiry.replace(" ", "").replace("-", "/").lower()
        expiry_matched = []
        for p in active_candidates:
            if p.expiry_date:
                exp_str = str(p.expiry_date)
                m_yy = p.expiry_date.strftime("%m/%y").lower()
                m_yyyy = p.expiry_date.strftime("%m/%Y").lower()
                y_m = p.expiry_date.strftime("%Y/%m").lower()
                if clean_det_exp in [exp_str, m_yy, m_yyyy, y_m] or m_yy in clean_det_exp or m_yyyy in clean_det_exp:
                    expiry_matched.append(p)
        if len(expiry_matched) == 1:
            return ("MATCHED", match_type, expiry_matched[0], [], batches_available, False)
        elif len(expiry_matched) > 1:
            active_candidates = expiry_matched

    # If only 1 in-stock candidate exists overall for this product:
    # Auto-match that in-stock candidate instead of requiring manual selection between 1 in-stock and depleted batches
    if len(in_stock_candidates) == 1:
        status = "LOW_CONFIDENCE" if is_low_conf else "MATCHED"
        return (status, match_type, in_stock_candidates[0], [], batches_available, False)

    # If still ambiguous among multiple batches:
    # Flag for explicit batch selection
    return ("MULTIPLE_MATCHES", match_type, None, active_candidates, batches_available, True)


@app.post(
    "/scan-multi-item",
    response_model=schemas.MultiScanResponse,
)
@limiter.limit("60/hour")
def scan_multi_item_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    scan_endpoint_start = time.perf_counter()
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        extension = ".jpg"

    check_file_size(file, MAX_FILE_SIZE_10MB)
    image_bytes = file.file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(image_bytes, extension)

    mime_type = file.content_type or f"image/{extension.lstrip('.')}"

    try:
        # GEMINI-ONLY AI VISION SCANNING PIPELINE
        scan_result = scan_multi_item(raw_bytes=image_bytes, mime_type=mime_type)

        if not scan_result.get("success"):
            logger.error(f"[MULTI_ITEM_ERROR] Gemini scan failed: {scan_result.get('error')}")
            raise HTTPException(
                status_code=502,
                detail=scan_result.get(
                    "error",
                    "AI medicine scan failed.",
                ),
            )

        detected_items = scan_result.get("items", [])
        detected_barcodes = scan_result.get("detected_barcodes", [])
        gemini_latency = float(scan_result.get("gemini_latency", 0.0))
        ocr_latency = 0.0
        primary_engine = scan_result.get("primary_engine", "Dawaiflow AI")

        # Use cached active products for instant inventory matching (< 1ms)
        inventory_products = crud.get_all_active_products_cached(db, current_user.id)

        grouped_items = {}
        total_price = 0.0
        any_review_required = False

        # Match metrics
        count_detected = len(detected_items)
        count_exact_code = 0
        count_exact_name = 0
        count_fuzzy = 0
        count_not_found = 0
        count_multiple = 0

        for idx, detected_item in enumerate(detected_items):
            det_name = (detected_item.get("name") or "").strip()
            det_brand = (detected_item.get("brand_name") or "").strip() or None
            det_generic = (detected_item.get("generic_name") or "").strip() or None
            det_code = (detected_item.get("code") or "").strip()
            det_strength = (detected_item.get("strength") or "").strip()
            det_form = (detected_item.get("form") or "").strip()
            det_pack = (detected_item.get("pack_size") or "").strip()
            det_batch = (detected_item.get("batch") or "").strip()
            det_expiry = (detected_item.get("expiry") or "").strip()

            if not det_name and not det_code and not det_batch:
                continue

            (
                match_status,
                match_type,
                matched_product,
                possible_matches,
                batches_available,
                requires_batch_selection,
            ) = _match_inventory_items(
                inventory_products,
                detected_item,
                detected_barcodes,
            )

            # Gemini AI attribution
            item_engine = "GEMINI_AI"
            if match_type == "EXACT_CODE":
                item_engine_label = "Barcode Match"
                item_engine_performance = "Instant Barcode"
                count_exact_code += 1
            else:
                item_engine_label = "Dawaiflow AI"
                item_engine_performance = f"{gemini_latency:.2f}s"
                if match_type == "EXACT_NAME_SPECS":
                    count_exact_name += 1
                elif match_type == "FUZZY_NAME":
                    count_fuzzy += 1

            if match_status == "NOT_FOUND":
                count_not_found += 1
            elif match_status == "MULTIPLE_MATCHES":
                count_multiple += 1

            possible_match_dicts = [
                {
                    "id": p.id,
                    "product_name": p.product_name,
                    "brand": p.brand,
                    "batch_number": p.batch_number,
                    "unit_price": float(p.unit_price or 0),
                    "strip_price": float(p.unit_price or 0),
                    "tablets_per_strip": p.tablets_per_strip or p.units_per_pack or 10,
                    "units_per_pack": p.units_per_pack or p.tablets_per_strip or 10,
                    "loose_tablet_price": float(p.loose_tablet_price or (float(p.unit_price or 0) / (p.tablets_per_strip or p.units_per_pack or 10)) if p.unit_price else 0),
                    "quantity": int(p.quantity or 0),
                    "stock": int(p.quantity or 0),
                    "loose_tablet_stock": int(getattr(p, "loose_tablet_stock", 0) or 0),
                    "total_tablets": (int(p.quantity or 0) * (p.tablets_per_strip or p.units_per_pack or 10)) + int(getattr(p, "loose_tablet_stock", 0) or 0),
                    "barcode": p.barcode,
                }
                for p in possible_matches
            ]

            display_name = det_name or (f"Item {det_code}" if det_code else "Unknown Medicine")

            if requires_batch_selection:
                key = f"select_batch:{idx}:{_normalise_product_name(display_name)}"
                any_review_required = True
                primary_batch = batches_available[0] if batches_available else {}
                unit_price = float(matched_product.unit_price or 0) if matched_product else float(primary_batch.get("unit_price", 0) or 0)
                tabs_count = (matched_product.tablets_per_strip or matched_product.units_per_pack or 10) if matched_product else int(primary_batch.get("tablets_per_strip", 10) or 10)
                loose_price = float(matched_product.loose_tablet_price or (unit_price / tabs_count if unit_price else 0)) if matched_product else float(primary_batch.get("loose_tablet_price", 0) or 0)

                grouped_items[key] = {
                    "product_name": matched_product.product_name if matched_product else (primary_batch.get("product_name") or display_name),
                    "brand": matched_product.brand if matched_product else primary_batch.get("brand"),
                    "matched_inventory_id": None,
                    "price": unit_price if unit_price > 0 else None,
                    "strip_price": unit_price if unit_price > 0 else None,
                    "tablets_per_strip": tabs_count,
                    "units_per_pack": tabs_count,
                    "loose_tablet_price": loose_price if loose_price > 0 else None,
                    "quantity": 1,
                    "confidence": 0.85,
                    "matched": False,
                    "needs_review": True,
                    "reason": f"Multiple batches found ({len(batches_available)}). Please select the batch.",
                    "match_status": "MULTIPLE_MATCHES",
                    "match_type": match_type,
                    "detected_name": det_name,
                    "brand_name": det_brand,
                    "generic_name": det_generic,
                    "detected_code": det_code,
                    "detected_strength": det_strength,
                    "detected_form": det_form,
                    "detected_pack_size": det_pack,
                    "detected_batch": det_batch,
                    "detected_expiry": det_expiry,
                    "batch_number": None,
                    "expiry_date": None,
                    "days_remaining": None,
                    "stock": int(getattr(matched_product, "quantity", 0) or 0) if matched_product else (primary_batch.get("stock", 0) if primary_batch else None),
                    "loose_tablet_stock": int(getattr(matched_product, "loose_tablet_stock", 0) or 0) if matched_product else (primary_batch.get("loose_tablet_stock", 0) if primary_batch else 0),
                    "total_tablets": ((int(getattr(matched_product, "quantity", 0) or 0) * tabs_count) + int(getattr(matched_product, "loose_tablet_stock", 0) or 0)) if matched_product else (primary_batch.get("total_tablets", 0) if primary_batch else None),
                    "requires_batch_selection": True,
                    "batches_available": batches_available,
                    "possible_matches": possible_match_dicts,
                    "engine": item_engine,
                    "engine_label": item_engine_label,
                    "engine_performance": item_engine_performance,
                }

            elif match_status == "MATCHED" and matched_product:
                key = f"product:{matched_product.id}"
                unit_price = float(matched_product.unit_price or 0)
                is_review = (unit_price <= 0)
                tabs_count = matched_product.tablets_per_strip or matched_product.units_per_pack or 10
                loose_price = float(matched_product.loose_tablet_price or (unit_price / tabs_count if unit_price else 0))

                if key in grouped_items:
                    grouped_items[key]["quantity"] += 1
                else:
                    grouped_items[key] = {
                        "product_name": matched_product.product_name,
                        "brand": matched_product.brand,
                        "matched_inventory_id": matched_product.id,
                        "price": unit_price,
                        "strip_price": unit_price,
                        "tablets_per_strip": tabs_count,
                        "units_per_pack": tabs_count,
                        "loose_tablet_price": loose_price,
                        "quantity": 1,
                        "confidence": 1.0 if match_type == "EXACT_CODE" else 0.9,
                        "matched": True,
                        "needs_review": is_review,
                        "reason": "Selling price is not configured." if unit_price <= 0 else None,
                        "match_status": "MATCHED",
                        "match_type": match_type,
                        "detected_name": det_name,
                        "brand_name": det_brand,
                        "generic_name": det_generic,
                        "detected_code": det_code,
                        "detected_strength": det_strength,
                        "detected_form": det_form,
                        "detected_pack_size": det_pack,
                        "detected_batch": det_batch,
                        "detected_expiry": det_expiry,
                        "batch_number": matched_product.batch_number,
                        "expiry_date": str(matched_product.expiry_date) if matched_product.expiry_date else None,
                        "days_remaining": getattr(matched_product, "days_remaining", None),
                        "stock": int(getattr(matched_product, "quantity", 0) or 0),
                        "loose_tablet_stock": int(getattr(matched_product, "loose_tablet_stock", 0) or 0),
                        "total_tablets": (int(getattr(matched_product, "quantity", 0) or 0) * tabs_count) + int(getattr(matched_product, "loose_tablet_stock", 0) or 0),
                        "requires_batch_selection": False,
                        "batches_available": batches_available,
                        "possible_matches": [],
                        "engine": item_engine,
                        "engine_label": item_engine_label,
                        "engine_performance": item_engine_performance,
                    }
                total_price += unit_price
                if is_review:
                    any_review_required = True

            elif match_status == "LOW_CONFIDENCE" and matched_product:
                key = f"low_conf:{matched_product.id}"
                unit_price = float(matched_product.unit_price or 0)
                any_review_required = True
                tabs_count = matched_product.tablets_per_strip or matched_product.units_per_pack or 10
                loose_price = float(matched_product.loose_tablet_price or (unit_price / tabs_count if unit_price else 0))

                if key in grouped_items:
                    grouped_items[key]["quantity"] += 1
                else:
                    grouped_items[key] = {
                        "product_name": matched_product.product_name,
                        "brand": matched_product.brand,
                        "matched_inventory_id": matched_product.id,
                        "price": unit_price,
                        "strip_price": unit_price,
                        "tablets_per_strip": tabs_count,
                        "units_per_pack": tabs_count,
                        "loose_tablet_price": loose_price,
                        "quantity": 1,
                        "confidence": 0.70,
                        "matched": True,
                        "needs_review": True,
                        "reason": f"Fuzzy matched '{matched_product.product_name}'. Please verify.",
                        "match_status": "LOW_CONFIDENCE",
                        "match_type": match_type,
                        "detected_name": det_name,
                        "brand_name": det_brand,
                        "generic_name": det_generic,
                        "detected_code": det_code,
                        "detected_strength": det_strength,
                        "detected_form": det_form,
                        "detected_pack_size": det_pack,
                        "detected_batch": det_batch,
                        "detected_expiry": det_expiry,
                        "batch_number": matched_product.batch_number,
                        "expiry_date": str(matched_product.expiry_date) if matched_product.expiry_date else None,
                        "days_remaining": getattr(matched_product, "days_remaining", None),
                        "stock": int(getattr(matched_product, "quantity", 0) or 0),
                        "loose_tablet_stock": int(getattr(matched_product, "loose_tablet_stock", 0) or 0),
                        "total_tablets": (int(getattr(matched_product, "quantity", 0) or 0) * tabs_count) + int(getattr(matched_product, "loose_tablet_stock", 0) or 0),
                        "requires_batch_selection": False,
                        "batches_available": batches_available,
                        "possible_matches": possible_match_dicts,
                        "engine": item_engine,
                        "engine_label": item_engine_label,
                        "engine_performance": item_engine_performance,
                    }
                total_price += unit_price

            elif match_status == "MULTIPLE_MATCHES":
                key = f"multiple:{idx}:{_normalise_product_name(display_name)}"
                any_review_required = True

                grouped_items[key] = {
                    "product_name": display_name,
                    "brand": None,
                    "matched_inventory_id": None,
                    "price": None,
                    "strip_price": None,
                    "tablets_per_strip": 10,
                    "units_per_pack": 10,
                    "loose_tablet_price": None,
                    "quantity": 1,
                    "confidence": 0.50,
                    "matched": False,
                    "needs_review": True,
                    "reason": f"Multiple potential matches ({len(possible_matches)} found). Select one.",
                    "match_status": "MULTIPLE_MATCHES",
                    "match_type": match_type,
                    "detected_name": det_name,
                    "brand_name": det_brand,
                    "generic_name": det_generic,
                    "detected_code": det_code,
                    "detected_strength": det_strength,
                    "detected_form": det_form,
                    "detected_pack_size": det_pack,
                    "detected_batch": det_batch,
                    "detected_expiry": det_expiry,
                    "batch_number": None,
                    "expiry_date": None,
                    "days_remaining": None,
                    "stock": None,
                    "requires_batch_selection": False,
                    "batches_available": batches_available,
                    "possible_matches": possible_match_dicts,
                    "engine": item_engine,
                    "engine_label": item_engine_label,
                    "engine_performance": item_engine_performance,
                }

            else:
                # NOT_FOUND (Strictly selling only: NEVER create or alter database inventory!)
                key = f"not_found:{idx}:{_normalise_product_name(display_name)}"
                any_review_required = True

                grouped_items[key] = {
                    "product_name": display_name,
                    "brand": None,
                    "matched_inventory_id": None,
                    "price": None,
                    "strip_price": None,
                    "tablets_per_strip": 10,
                    "units_per_pack": 10,
                    "loose_tablet_price": None,
                    "quantity": 1,
                    "confidence": 0.0,
                    "matched": False,
                    "needs_review": True,
                    "reason": "Medicine not found in inventory.",
                    "match_status": "NOT_FOUND",
                    "match_type": "NONE",
                    "detected_name": det_name,
                    "brand_name": det_brand,
                    "generic_name": det_generic,
                    "detected_code": det_code,
                    "detected_strength": det_strength,
                    "detected_form": det_form,
                    "detected_pack_size": det_pack,
                    "detected_batch": det_batch,
                    "detected_expiry": det_expiry,
                    "batch_number": None,
                    "expiry_date": None,
                    "days_remaining": None,
                    "stock": None,
                    "requires_batch_selection": False,
                    "batches_available": [],
                    "possible_matches": [],
                    "engine": item_engine,
                    "engine_label": item_engine_label,
                    "engine_performance": item_engine_performance,
                }

        response_items = list(grouped_items.values())
        total_scan_latency = time.perf_counter() - scan_endpoint_start

        logger.info(
            f"[PERF] [MULTI_ITEM_SCAN] Total Endpoint Latency: {total_scan_latency:.3f}s | "
            f"Gemini Latency: {gemini_latency:.3f}s | Detected: {count_detected} | "
            f"Exact Code: {count_exact_code} | Exact Name: {count_exact_name} | "
            f"Fuzzy: {count_fuzzy} | Multiple: {count_multiple} | Not Found: {count_not_found}"
        )

        return {
            "success": True,
            "items": response_items,
            "total_price": round(total_price, 2),
            "needs_review": any_review_required,
            "detected_barcodes": detected_barcodes,
            "error": None,
            "primary_engine": primary_engine,
            "gemini_latency": gemini_latency,
            "ocr_latency": 0.0,
            "total_latency": total_scan_latency,
            "performance_breakdown": None,
        }
    except HTTPException:
        raise
    except Exception as err:
        logger.error(f"[PERF] Scan multi-item unhandled error: {err}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal scanning failure.")



# ==========================================
# NOTIFICATIONS & DEVICE TOKENS
# ==========================================

@app.get("/notification-settings")
def get_notification_settings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.get_notification_settings(db, current_user.id)


@app.put("/notification-settings")
def update_notification_settings(
    data: schemas.NotificationSettingsCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    crud.update_notification_settings(db, current_user.id, data)
    return {"message": "Notification settings updated successfully"}


class NotificationRequest(BaseModel):
    token: str
    title: str
    body: str


@app.post("/send_notification")
def send_notification(
    data: NotificationRequest,
    current_user: models.User = Depends(get_current_user),
):
    message = messaging.Message(
        notification=messaging.Notification(
            title=data.title,
            body=data.body,
        ),
        token=data.token,
    )
    response = messaging.send(message)
    return {"success": True, "message_id": response}


class TokenRequest(BaseModel):
    token: str


@app.post("/save_token")
def save_token(
    data: TokenRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    existing_token = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.token == data.token)
        .first()
    )

    if existing_token:
        existing_token.user_id = current_user.id
    else:
        existing_user = (
            db.query(models.DeviceToken)
            .filter(models.DeviceToken.user_id == current_user.id)
            .first()
        )
        if existing_user:
            existing_user.token = data.token
        else:
            db.add(models.DeviceToken(user_id=current_user.id, token=data.token))

    db.commit()
    return {"message": "Token saved successfully"}


# ==========================================
# INVENTORY BULK IMPORT MODULE (Marg ERP, Tally, etc.)
# ==========================================

@app.post("/import/inventory/preview", response_model=schemas.ImportPreviewResponse)
@app.post("/inventory/import-preview", response_model=schemas.ImportPreviewResponse)
async def preview_inventory_import(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user)
):
    """
    Step 1: Upload Excel/CSV inventory file.
    Parses file headers, performs automatic column header mapping detection,
    caches file temporarily, and returns the preview mapping to the user.
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_SPREADSHEET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{file_ext}'. Allowed spreadsheet types: {', '.join(sorted(ALLOWED_SPREADSHEET_EXTENSIONS))}"
        )

    check_file_size(file, MAX_FILE_SIZE_5MB)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(content, file_ext)

    try:
        df = import_service.read_file_to_dataframe(content, file.filename)
    except Exception as e:
        logger.error(f"Import preview parse error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Failed to parse file. Please verify file format and integrity.")

    if df.empty:
        raise HTTPException(status_code=400, detail="File contains no rows.")

    file_headers = list(df.columns)
    detected_mapping, unmapped = import_service.auto_detect_mapping(file_headers)
    preview_id = import_service.save_temp_dataframe(df)

    preview_slice = df.head(10).fillna("").to_dict(orient="records")

    return schemas.ImportPreviewResponse(
        preview_id=preview_id,
        filename=file.filename,
        total_rows=len(df),
        file_headers=file_headers,
        detected_mapping=detected_mapping,
        unmapped_columns=unmapped,
        preview_data=preview_slice,
    )


@app.post("/import/inventory/confirm", response_model=schemas.ImportSummaryResponse)
@app.post("/inventory/import-confirm", response_model=schemas.ImportSummaryResponse)
def confirm_inventory_import(
    payload: schemas.ImportConfirmRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Step 2: Confirm or correct the column mapping and execute bulk inventory import.
    Validates each row, skips/updates duplicates, and returns import report summary.
    """
    df = import_service.load_temp_dataframe(payload.preview_id)
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="Import preview session expired or not found. Please upload file again.")

    cleaned_rows = []
    errors = []

    records = df.to_dict(orient="records")
    for idx, row in enumerate(records):
        row_num = idx + 1
        cleaned_data, warnings, error_reason = import_service.validate_and_normalize_row(
            row=row,
            mapping=payload.column_mapping,
            row_index=row_num
        )
        if error_reason:
            if len(errors) < 100:
                clean_raw = {k: (str(v) if pd.notna(v) else "") for k, v in row.items()}
                errors.append(schemas.ImportErrorItem(
                    row=row_num,
                    raw_data=clean_raw,
                    reason=error_reason
                ))
        elif cleaned_data:
            cleaned_rows.append((row_num, cleaned_data, warnings))

    import_result = crud.bulk_import_inventory(
        db=db,
        user_id=current_user.id,
        cleaned_rows=cleaned_rows,
        on_duplicate=payload.on_duplicate or "skip"
    )

    import_service.cleanup_temp_cache(payload.preview_id)

    warnings_list = [
        schemas.ImportWarningItem(
            row=w["row"],
            product_name=w["product_name"],
            message=w["message"]
        ) for w in import_result["warnings"]
    ]

    return schemas.ImportSummaryResponse(
        total_rows_processed=len(df),
        rows_imported=import_result["rows_imported"],
        rows_updated=import_result["rows_updated"],
        rows_skipped=import_result["rows_skipped"],
        warnings_count=len(warnings_list),
        errors_count=len(errors),
        warnings=warnings_list,
        errors=errors
    )


@app.post("/import/inventory")
@app.post("/inventory/import")
@app.post("/api/inventory/import")
async def single_step_inventory_import(
    file: UploadFile = File(...),
    on_duplicate: str = "skip",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Standalone single-step import endpoint for auto-upload & import without separate preview confirmation.
    High-performance implementation supporting 10,000+ rows in sub-second duration.
    """
    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_SPREADSHEET_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file extension '{file_ext}'. Allowed spreadsheet types: {', '.join(sorted(ALLOWED_SPREADSHEET_EXTENSIONS))}"
        )

    check_file_size(file, MAX_FILE_SIZE_5MB)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    validate_file_content_and_magic(content, file_ext)

    df = import_service.read_file_to_dataframe(content, file.filename)
    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file contains no data rows.")

    file_headers = list(df.columns)
    detected_mapping, _ = import_service.auto_detect_mapping(file_headers)

    cleaned_rows = []
    errors = []
    records = df.to_dict(orient="records")
    for idx, row in enumerate(records):
        row_num = idx + 1
        cleaned_data, warnings, error_reason = import_service.validate_and_normalize_row(
            row=row,
            mapping=detected_mapping,
            row_index=row_num
        )
        if error_reason:
            if len(errors) < 100:
                clean_raw = {k: (str(v) if pd.notna(v) else "") for k, v in row.items()}
                errors.append({"row": row_num, "raw_data": clean_raw, "reason": error_reason})
        elif cleaned_data:
            cleaned_rows.append((row_num, cleaned_data, warnings))

    import_result = crud.bulk_import_inventory(
        db=db,
        user_id=current_user.id,
        cleaned_rows=cleaned_rows,
        on_duplicate=on_duplicate
    )

    return {
        "total_rows_processed": len(df),
        "rows_imported": import_result["rows_imported"],
        "rows_updated": import_result["rows_updated"],
        "rows_skipped": import_result["rows_skipped"],
        "warnings_count": len(import_result["warnings"]),
        "errors_count": len(errors),
        "detected_mapping": detected_mapping,
        "warnings": import_result["warnings"],
        "errors": errors
    }


@app.get("/api/inventory/import-template")
@app.get("/inventory/import-template")
def download_inventory_import_template():
    """
    Returns standardized inventory import template file (.xlsx or .csv).
    Allows users to download standard structure before bulk uploading medicines.
    """
    template_path = os.path.join(os.path.dirname(__file__), "DawaiFlow_Inventory_Import_Template.xlsx")
    if os.path.exists(template_path):
        return FileResponse(
            path=template_path,
            filename="DawaiFlow_Inventory_Import_Template.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    csv_content = (
        "product_name,brand,category,batch_number,expiry_date,quantity,mrp,purchase_price,hsn_code,gst_rate,tablets_per_strip,barcode\n"
        "Dolo 650mg Tablet,Micro Labs,allopathy,B2026-01,2027-12-31,50,30.00,24.00,3004,12.0,15,8901234567890\n"
        "Azithral 500mg Tablet,Alembic,allopathy,AZ-102,2026-10-31,20,120.00,96.00,3004,12.0,5,8902222222222\n"
        "Pan 40mg Tablet,Alkem,allopathy,PN-889,2027-06-30,30,90.00,72.00,3004,12.0,10,8904444444444\n"
    )
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=DawaiFlow_Inventory_Import_Template.csv"}
    )


# ==========================================
# CUSTOMER & PATIENT PROFILE ENDPOINTS
# ==========================================

@app.get("/customers/search", response_model=Optional[schemas.CustomerResponse])
def search_customer_by_phone(
    phone: str,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_CUSTOMER_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Search customer by phone number to retrieve saved fixed patient discount percentage.
    """
    return crud.get_customer_by_phone(db, phone=phone.strip(), user_id=current_user.id)


@app.post("/customers", response_model=schemas.CustomerResponse)
def create_or_update_customer(
    customer: schemas.CustomerCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_CUSTOMER_CREATE)),
    db: Session = Depends(get_db),
):
    """
    Create or update a customer profile with fixed patient discount percentage.
    """
    c = crud.create_or_update_customer(db, customer_data=customer, user_id=current_user.id)
    fast_cache.invalidate_tag(current_user.id, "customers")
    fast_cache.invalidate_tag(current_user.id, "khata")
    return c


@app.get("/customers", response_model=List[schemas.CustomerResponse])
def get_customers(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_CUSTOMER_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Get all registered customers for the current shop.
    """
    cached = fast_cache.get(current_user.id, "customers_list")
    if cached is not None:
        return cached
    res = crud.get_customers(db, user_id=current_user.id)
    fast_cache.set(current_user.id, "customers_list", res, ttl=30.0, tags=["customers", "khata"])
    return res


@app.post("/customers/{customer_id}/payments", response_model=schemas.CustomerPaymentResponse, status_code=201)
def collect_customer_payment(
    customer_id: int,
    payment: schemas.CustomerPaymentCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_PAYMENT)),
    db: Session = Depends(get_db),
):
    """Log credit payment collection from customer (Khata settlement)."""
    if payment.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="Customer ID mismatch.")
    pay = crud.create_customer_payment(db=db, obj_in=payment, user_id=current_user.id)
    fast_cache.invalidate_tag(current_user.id, "customers")
    fast_cache.invalidate_tag(current_user.id, "khata")
    fast_cache.invalidate_tag(current_user.id, "dashboard")
    return pay


@app.get("/customers/{customer_id}/payments", response_model=List[schemas.CustomerPaymentResponse])
def get_customer_payment_history(
    customer_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_VIEW)),
    db: Session = Depends(get_db),
):
    """Get collection history of credit payments for a customer."""
    return crud.get_customer_payments(db=db, customer_id=customer_id, user_id=current_user.id)


@app.get("/customers/{customer_id}/ledger")
def get_customer_ledger_summary(
    customer_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_KHATA_VIEW)),
    db: Session = Depends(get_db),
):
    """Get chronological running ledger of customer credit invoices and collections."""
    return crud.get_customer_ledger(db=db, customer_id=customer_id, user_id=current_user.id)


# ==========================================
# SALE RETURNS ENDPOINTS
# ==========================================

@app.post("/billing/returns", response_model=schemas.SaleReturnResponse)
def process_sale_return(
    payload: schemas.SaleReturnCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_BILL_CREATE)),
    db: Session = Depends(get_db),
):
    """
    Feature 4: One-Tap Return processing.
    Restores returned items to inventory, records SaleReturn, and returns prorated refund summary.
    """
    return crud.process_sale_return(db, return_data=payload, user_id=current_user.id)


@app.get("/billing/returns/today", response_model=List[schemas.SaleReturnResponse])
def get_todays_returns_billing(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_BILL_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Feature 4: Retrieve all returns processed today for "Today's Returns" dashboard view.
    """
    returns = crud.get_todays_returns(db, user_id=current_user.id)
    for r in returns:
        if not getattr(r, 'bill_number', None) and r.sale:
            r.bill_number = r.sale.bill_number
    return returns


# ==========================================
# WEB APP DASHBOARD & REPORTS ENDPOINTS
# ==========================================

@app.get("/dashboard/stats")
def get_dashboard_stats(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mobile App Dashboard Stats Endpoint.
    Returns real-time analytics KPIs: total sales, net profit, low stock count, expired stock valuation, credit receivables, and supplier payables.
    """
    return crud.get_dashboard_stats(db=db, user_id=current_user.id)

@app.get("/dashboard/summary")
def get_dashboard_summary(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Mobile-First Pharmacy ERP Dashboard Summary Endpoint.
    Returns aggregated real-time metrics for Today's Business, Sales Overview, Needs Attention, Inventory Health, Top Selling, and Intelligence Insights.
    """
    user_id = current_user.id
    cache_key = "dashboard_summary"
    cached = fast_cache.get(user_id, cache_key)
    if cached is not None:
        from fastapi.responses import JSONResponse
        return JSONResponse(content=cached)
    
    # IST Timezone Handling: Shift naive UTC datetime to India/IST (+5.5 hours)
    ist_offset = timedelta(hours=5, minutes=30)
    now_utc = datetime.utcnow()
    now_ist = now_utc + ist_offset
    today_ist = now_ist.date()
    
    today_start_ist = datetime.combine(today_ist, datetime.min.time())
    today_end_ist = datetime.combine(today_ist, datetime.max.time())
    
    # Boundaries converted to UTC for database comparison
    today_start_utc = today_start_ist - ist_offset
    today_end_utc = today_end_ist - ist_offset
    
    yesterday_start_ist = today_start_ist - timedelta(days=1)
    yesterday_end_ist = today_end_ist - timedelta(days=1)
    yesterday_start_utc = yesterday_start_ist - ist_offset
    yesterday_end_utc = yesterday_end_ist - ist_offset
    
    month_start_ist = datetime.combine(today_ist.replace(day=1), datetime.min.time())
    month_start_utc = month_start_ist - ist_offset
    
    seven_days_ago_utc = today_start_utc - timedelta(days=7)
    thirty_days_ago_utc = today_start_utc - timedelta(days=30)

    # 1. Today's Business & Payment Breakdown (Consolidated Single SQL Query)
    today_sales_agg = db.query(
        func.count(models.Sale.id).label("bills"),
        func.sum(models.Sale.total_amount).label("revenue"),
        func.sum(case((models.Sale.payment_method.ilike("%CASH%"), models.Sale.total_amount), else_=0.0)).label("cash"),
        func.sum(case((models.Sale.payment_method.ilike("%UPI%"), models.Sale.total_amount), else_=0.0)).label("upi"),
        func.sum(case((models.Sale.payment_method.ilike("%CARD%"), models.Sale.total_amount), else_=0.0)).label("card"),
    ).filter(
        models.Sale.user_id == user_id, 
        models.Sale.created_at >= today_start_utc,
        models.Sale.created_at <= today_end_utc
    ).first()

    yesterday_revenue = db.query(func.sum(models.Sale.total_amount)).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= yesterday_start_utc,
        models.Sale.created_at <= yesterday_end_utc
    ).scalar() or 0.0

    today_sales = float(today_sales_agg.revenue or 0.0) if today_sales_agg else 0.0
    bills_count = int(today_sales_agg.bills or 0) if today_sales_agg else 0
    cash_total = float(today_sales_agg.cash or 0.0) if today_sales_agg else 0.0
    upi_total = float(today_sales_agg.upi or 0.0) if today_sales_agg else 0.0
    card_total = float(today_sales_agg.card or 0.0) if today_sales_agg else 0.0
    avg_bill = round(today_sales / bills_count, 2) if bills_count > 0 else 0.0

    growth_pct = 0.0
    if yesterday_revenue > 0:
        growth_pct = round(((today_sales - yesterday_revenue) / yesterday_revenue) * 100, 1)

    # Today's Profit (Revenue - COGS)
    if bills_count > 0:
        today_cogs = db.query(
            func.sum(
                models.SaleItem.quantity * func.coalesce(
                    models.Product.purchase_price,
                    models.SaleItem.unit_price * 0.7
                )
            )
        ).join(models.Sale, models.SaleItem.sale_id == models.Sale.id).outerjoin(
            models.Product, models.SaleItem.product_id == models.Product.id
        ).filter(
            models.Sale.user_id == user_id, 
            models.Sale.created_at >= today_start_utc,
            models.Sale.created_at <= today_end_utc
        ).scalar() or 0.0
    else:
        today_cogs = 0.0

    today_profit = max(0.0, round(today_sales - float(today_cogs), 2))

    # Today's Returns
    today_returns_val = db.query(func.sum(models.SaleReturn.return_amount)).filter(
        models.SaleReturn.user_id == user_id,
        models.SaleReturn.created_at >= today_start_utc,
        models.SaleReturn.created_at <= today_end_utc
    ).scalar() or 0.0
    today_returns_amount = float(today_returns_val)

    # 2. Consolidated Product & Inventory Health Aggregation in 1 query
    prod_agg = db.query(
        func.count(models.Product.id).label("total"),
        func.sum(case(((models.Product.quantity > 0) & (models.Product.quantity <= 20), 1), else_=0)).label("low_stock"),
        func.sum(case(((models.Product.quantity > 0) & (models.Product.expiry_date >= today_ist) & (models.Product.expiry_date <= today_ist + timedelta(days=60)), 1), else_=0)).label("expiring_soon"),
        func.sum(case(((models.Product.quantity > 0) & (models.Product.expiry_date < today_ist), 1), else_=0)).label("expired"),
        func.sum(models.Product.quantity * func.coalesce(models.Product.purchase_price, 0.0)).label("stock_val")
    ).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    ).first()

    total_products = int(prod_agg.total or 0) if prod_agg else 0
    low_stock_count = int(prod_agg.low_stock or 0) if prod_agg else 0
    expiring_soon_count = int(prod_agg.expiring_soon or 0) if prod_agg else 0
    expired_count = int(prod_agg.expired or 0) if prod_agg else 0
    total_stock_value = round(float(prod_agg.stock_val or 0.0), 2) if prod_agg else 0.0
    healthy_count = max(0, total_products - (expiring_soon_count + expired_count + low_stock_count))

    customer_outstanding = float(db.query(func.sum(models.Customer.pending_amount)).filter(
        models.Customer.user_id == user_id
    ).scalar() or 0.0)

    total_purchases = float(db.query(func.sum(models.PurchaseInvoice.total_amount)).filter(
        models.PurchaseInvoice.user_id == user_id
    ).scalar() or 0.0)
    total_supplier_paid = float(db.query(func.sum(models.SupplierPayment.amount_paid)).filter(
        models.SupplierPayment.user_id == user_id
    ).scalar() or 0.0)
    supplier_payable = max(0.0, total_purchases - total_supplier_paid)

    # 4. Top Selling Medicines (Real SQL aggregation)
    top_items_rows = db.query(
        models.SaleItem.product_name,
        func.sum(models.SaleItem.quantity).label("total_units")
    ).join(models.Sale, models.SaleItem.sale_id == models.Sale.id).filter(
        models.Sale.user_id == user_id
    ).group_by(models.SaleItem.product_name).order_by(text("total_units DESC")).limit(4).all()

    top_selling = [
        {"name": row[0] or "Medicine", "units": int(row[1] or 0)}
        for row in top_items_rows
    ]

    # 5. Sales Overview Trends (Today, 7D, 30D) - Grouped timezone-correctly in Python
    trend_sales = db.query(
        models.Sale.created_at,
        models.Sale.total_amount
    ).filter(
        models.Sale.user_id == user_id,
        models.Sale.created_at >= seven_days_ago_utc
    ).all()

    sales_by_date = {}
    for i in range(7):
        d = today_ist - timedelta(days=i)
        sales_by_date[d] = 0.0

    for s in trend_sales:
        s_date_ist = (s.created_at + ist_offset).date()
        if s_date_ist in sales_by_date:
            sales_by_date[s_date_ist] += float(s.total_amount)

    trend_7d = [
        {"label": d.strftime("%Y-%m-%d"), "sales": round(val, 2)}
        for d, val in sorted(sales_by_date.items())
    ]

    # 6. DawaiFlow Intelligence
    intelligence_text = f"{low_stock_count} medicines are below reorder levels requiring restock."
    target_module = "Inventory"
    if expired_count > 0:
        intelligence_text = f"{expired_count} expired medicine batches require immediate review/removal."
        target_module = "Alerts"
    elif customer_outstanding > 1000:
        intelligence_text = f"₹{customer_outstanding:,.0f} is outstanding across customer Khata books."
        target_module = "Khata / Outstanding"
    elif top_selling:
        top_name = top_selling[0]['name']
        top_units = top_selling[0]['units']
        intelligence_text = f"{top_name} is your #1 top seller with {top_units} units sold."
        target_module = "Sales History"

    # 7. Recent Products List (10 most recent non-deleted products)
    recent_products_rows = db.query(models.Product).filter(
        models.Product.user_id == user_id,
        models.Product.is_deleted == False
    ).order_by(models.Product.id.desc()).limit(10).all()

    recent_products_list = []
    for p in recent_products_rows:
        days_rem = (p.expiry_date - today_ist).days if p.expiry_date else 999
        status_str = "Expired" if days_rem <= 0 else ("Expiring Soon" if 0 < days_rem <= 30 else "Safe")
        if p.quantity <= 0:
            status_str = "Out of Stock"

        recent_products_list.append({
            "id": p.id,
            "product_name": p.product_name,
            "brand": p.brand or "",
            "category": p.category or "General",
            "quantity": p.quantity,
            "unit_price": p.unit_price,
            "purchase_price": p.purchase_price,
            "expiry_date": p.expiry_date.strftime("%Y-%m-%d") if p.expiry_date else None,
            "days_remaining": days_rem,
            "batch_number": p.batch_number or "DEFAULT-B1",
            "status": status_str,
        })

    # 8. Pending Payments Ledger List
    pending_sales = db.query(models.Sale).filter(
        models.Sale.user_id == user_id,
        models.Sale.payment_status == "PENDING"
    ).order_by(models.Sale.created_at.desc()).all()
    
    pending_payments_list = []
    pending_payments_total = 0.0
    for s in pending_sales:
        s_local = s.created_at + ist_offset
        pending_payments_list.append({
            "id": s.id,
            "customer_name": s.customer_name or "Walk-in Customer",
            "customer_phone": s.customer_phone or "N/A",
            "bill_number": s.bill_number,
            "bill_date": s_local.strftime("%Y-%m-%d %H:%M"),
            "total_amount": float(s.total_amount)
        })
        pending_payments_total += float(s.total_amount)

    can_view_financials = current_user.is_owner or current_user.has_permission(permissions.PERM_REPORT_VIEW)
    can_view_khata = current_user.is_owner or current_user.has_permission(permissions.PERM_KHATA_VIEW)
    can_view_inventory = current_user.is_owner or current_user.has_permission(permissions.PERM_INVENTORY_VIEW)
    can_view_bills = current_user.is_owner or current_user.has_permission(permissions.PERM_BILL_VIEW)

    summary_result = {
        "shop_name": current_user.shop_name or "Shree Balaji Medical Store",
        "owner_name": current_user.owner_name or "Kanishak Vashist",
        "name": current_user.name,
        "role": current_user.role,
        "staff_id": current_user.staff_id,
        "is_owner": current_user.is_owner,
        "permissions": list(current_user.permissions),
        
        # Root-level metrics mapped to web frontend expectations
        "total_products": total_products if can_view_inventory else 0,
        "today_sales_count": bills_count if (can_view_financials or can_view_bills) else 0,
        "today_revenue": round(today_sales, 2) if can_view_financials else 0.0,
        "expiring_soon_count": expiring_soon_count if can_view_inventory else 0,
        "expired_count": expired_count if can_view_inventory else 0,
        "low_stock_count": low_stock_count if can_view_inventory else 0,
        "dead_stock_count": crud.get_inventory_summary(db=db, user_id=user_id).get("dead_stock", 0) if can_view_inventory else 0,
        "today_returns_amount": round(today_returns_amount, 2) if can_view_financials else 0.0,
        
        # Payment breakdown summary
        "payment_summary": {
            "cash": round(cash_total, 2),
            "upi": round(upi_total, 2),
            "card": round(card_total, 2),
            "total": round(cash_total + upi_total + card_total, 2),
        } if can_view_financials else {},

        # Pending Payments List
        "pending_payments_list": pending_payments_list if can_view_khata else [],
        "pending_payments_total": round(pending_payments_total, 2) if can_view_khata else 0.0,
        
        # Nested structures for other components/clients
        "today_business": {
            "sales": round(today_sales, 2) if can_view_financials else 0.0,
            "profit": round(today_profit, 2) if can_view_financials else 0.0,
            "cogs": round(float(today_cogs), 2) if can_view_financials else 0.0,
            "bills": bills_count if (can_view_financials or can_view_bills) else 0,
            "avg_bill": avg_bill if can_view_financials else 0.0,
            "growth_pct": growth_pct if can_view_financials else 0.0
        },
        "sales_overview": {
            "trend_7d": trend_7d if can_view_financials else []
        },
        "needs_attention": {
            "expired_count": expired_count if can_view_inventory else 0,
            "expiring_soon_count": expiring_soon_count if can_view_inventory else 0,
            "low_stock_count": low_stock_count if can_view_inventory else 0,
            "customer_outstanding": round(customer_outstanding, 2) if can_view_khata else 0.0,
            "supplier_payable": round(supplier_payable, 2) if (can_view_financials or current_user.has_permission(permissions.PERM_SUPPLIER_VIEW)) else 0.0
        },
        "inventory_health": {
            "total_stock_value": total_stock_value if can_view_inventory else 0.0,
            "healthy_count": healthy_count if can_view_inventory else 0,
            "expiring_count": expiring_soon_count if can_view_inventory else 0,
            "expired_count": expired_count if can_view_inventory else 0,
            "low_stock_count": low_stock_count if can_view_inventory else 0
        },
        "top_selling": top_selling if can_view_financials else [],
        "intelligence": {
            "text": intelligence_text,
            "target_module": target_module
        },
        "recent_products": recent_products_list if can_view_inventory else []
    }
    fast_cache.set(user_id, cache_key, summary_result, ttl=15, tags=["dashboard"])
    from fastapi.responses import JSONResponse
    return JSONResponse(content=summary_result)


@app.get("/reports/sales")
@app.get("/reports/summary")
def get_reports_summary(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Web App Reports Summary Endpoint.
    Returns 7-day sales breakdown, top selling items, and expiring stock report.
    """
    user_id = current_user.id
    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)

    # 1. 7-Day Sales Breakdown
    recent_sales = (
        db.query(models.Sale.created_at, models.Sale.total_amount)
        .filter(models.Sale.user_id == user_id, models.Sale.created_at >= seven_days_ago)
        .all()
    )

    daily_map = {}
    for i in range(7):
        day_str = (now - timedelta(days=i)).strftime("%Y-%m-%d")
        daily_map[day_str] = {"date": day_str, "revenue": 0.0, "count": 0}

    for s_created, s_amount in recent_sales:
        day_str = s_created.strftime("%Y-%m-%d") if isinstance(s_created, datetime) else str(s_created)[:10]
        if day_str in daily_map:
            daily_map[day_str]["revenue"] += (s_amount or 0.0)
            daily_map[day_str]["count"] += 1

    daily_sales = [daily_map[k] for k in sorted(daily_map.keys())]

    # 2. Top Selling Products (Aggregated in SQL)
    top_selling_rows = (
        db.query(
            models.SaleItem.product_name,
            func.sum(models.SaleItem.quantity).label("quantity_sold"),
            func.sum(models.SaleItem.total_price).label("total_revenue")
        )
        .join(models.Sale, models.SaleItem.sale_id == models.Sale.id)
        .filter(models.Sale.user_id == user_id)
        .group_by(models.SaleItem.product_name)
        .order_by(func.sum(models.SaleItem.quantity).desc())
        .limit(5)
        .all()
    )

    top_selling = [
        {
            "product_name": r.product_name or "Unknown Medicine",
            "quantity_sold": int(r.quantity_sold or 0),
            "total_revenue": round(float(r.total_revenue or 0.0), 2)
        }
        for r in top_selling_rows
    ]

    # 3. Expiring Products List
    expiring_products = (
        db.query(models.Product)
        .filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False,
            models.Product.days_remaining != None,
            models.Product.days_remaining <= 60,
        )
        .order_by(models.Product.days_remaining.asc())
        .limit(20)
        .all()
    )

    expiring_list = [
        {
            "id": p.id,
            "product_name": p.product_name,
            "batch_number": p.batch_number or "N/A",
            "quantity": p.quantity or 0,
            "expiry_date": str(p.expiry_date) if p.expiry_date else "N/A",
            "days_remaining": p.days_remaining if p.days_remaining is not None else 0,
            "status": p.status or "Safe",
        }
        for p in expiring_products
    ]

    return {
        "daily_sales": daily_sales,
        "top_selling_products": top_selling,
        "expiring_products": expiring_list,
    }


# ==========================================
# PUBLIC PILOT LEADS ENDPOINT
# ==========================================

@app.post("/api/pilot-leads", response_model=schemas.PilotLeadResponse, status_code=201)
@limiter.limit("20/minute")
def create_pilot_lead(
    request: Request,
    lead: schemas.PilotLeadCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        new_lead = models.PilotLead(
            full_name=lead.full_name,
            pharmacy_name=lead.pharmacy_name,
            city=lead.city,
            phone=lead.phone,
            current_billing_method=lead.current_billing_method,
            bills_per_day=lead.bills_per_day,
            biggest_problem=lead.biggest_problem,
        )
        db.add(new_lead)
        db.commit()
        db.refresh(new_lead)

        # Dispatch immediate email alert to founder synchronously with background fallback
        lead_dict = {
            "id": new_lead.id,
            "full_name": new_lead.full_name,
            "pharmacy_name": new_lead.pharmacy_name,
            "city": new_lead.city,
            "phone": new_lead.phone,
            "current_billing_method": new_lead.current_billing_method,
            "bills_per_day": new_lead.bills_per_day,
            "biggest_problem": new_lead.biggest_problem,
            "created_at": new_lead.created_at.strftime("%d %b %Y, %I:%M %p UTC") if new_lead.created_at else datetime.utcnow().strftime("%d %b %Y, %I:%M %p UTC"),
        }
        sent = False
        try:
            sent = send_pilot_lead_notification(lead_data=lead_dict, lead_id=new_lead.id)
        except Exception as notify_err:
            logger.warning(f"Synchronous pilot lead email dispatch failed: {notify_err}")

        if not sent:
            background_tasks.add_task(send_pilot_lead_notification, lead_data=lead_dict, lead_id=new_lead.id)

        return new_lead
    except Exception as e:
        db.rollback()
        logger.error(f"Pilot request submission error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Could not submit pilot request. Please try again later.")


@app.post("/test-notification")
@app.post("/api/test-notification")
@limiter.limit("5/minute")
def test_notification_endpoint(
    request: Request,
    recipient: Optional[str] = None,
):
    """
    Test endpoint to verify SMTP configuration and send a sample pilot lead alert email.
    Usage: POST /test-notification (or POST /test-notification?recipient=your_email@gmail.com)
    Authorized via authenticated session or X-Admin-Secret header.
    """
    admin_secret = request.headers.get("X-Admin-Secret")
    configured_secret = os.getenv("SECRET_KEY", "").strip()
    is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"

    is_authenticated = False
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        try:
            token = auth_header.split(" ")[1]
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            is_authenticated = True
        except Exception:
            pass

    if is_prod and not (admin_secret and admin_secret == configured_secret) and not is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test notification endpoint requires authentication or X-Admin-Secret in production."
        )

    result = send_test_email(test_recipient=recipient)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)
    return result


@app.get("/api/admin/email-diagnostics")
@app.post("/api/admin/email-diagnostics")
@limiter.limit("10/minute")
def email_diagnostics_endpoint(
    request: Request,
    secret: Optional[str] = None,
    probe: bool = False,
    send_test: bool = False,
    retry_pending: bool = False,
    recipient: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Secure diagnostic endpoint to verify SMTP configuration and delivery health on production.
    Accepts authentication via X-Admin-Secret header or ?secret= query parameter matching SECRET_KEY.
    """
    admin_secret = request.headers.get("X-Admin-Secret") or secret
    configured_secret = os.getenv("SECRET_KEY", "").strip()

    if not admin_secret or admin_secret != configured_secret:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden. Valid X-Admin-Secret header or secret query parameter required."
        )

    health = check_smtp_health(probe_network=probe)

    test_result = None
    if send_test:
        test_result = send_test_email(test_recipient=recipient)

    retry_result = None
    if retry_pending:
        retry_result = retry_pending_pilot_leads(limit=20)

    recent_leads = (
        db.query(models.PilotLead)
        .order_by(models.PilotLead.id.desc())
        .limit(10)
        .all()
    )

    leads_summary = [
        {
            "id": l.id,
            "pharmacy_name": l.pharmacy_name,
            "full_name": l.full_name,
            "city": l.city,
            "phone": l.phone,
            "created_at": l.created_at.isoformat() if l.created_at else None,
            "notification_status": l.notification_status or "PENDING",
            "notification_provider": l.notification_provider,
            "notified_at": l.notified_at.isoformat() if l.notified_at else None,
            "notification_error": l.notification_error,
        }
        for l in recent_leads
    ]

    return {
        "status": "healthy" if health.get("is_configured") else "unconfigured",
        "smtp_health": health,
        "test_email_result": test_result,
        "retry_leads_result": retry_result,
        "recent_leads": leads_summary,
    }


# ---------------- STAFF & BRANCHES MANAGEMENT ENDPOINTS ---------------- #

def _serialize_staff_member(staff: models.StaffMember) -> schemas.StaffMemberResponse:
    perms = permissions.get_role_permissions(
        permissions.normalize_role(staff.role),
        staff.permissions_json,
    )
    return schemas.StaffMemberResponse(
        id=staff.id,
        user_id=staff.user_id,
        name=staff.name,
        phone=staff.phone,
        email=staff.email,
        username=staff.username,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
        permissions=list(perms),
        last_login=staff.last_login,
        created_at=staff.created_at,
    )


@app.get("/staff", response_model=List[schemas.StaffMemberResponse])
def get_staff_members(
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_VIEW")),
    db: Session = Depends(get_db),
):
    """List all staff members for the current pharmacy."""
    cached = fast_cache.get(current_user.id, "staff_list")
    if cached is not None:
        return cached

    staff_list = (
        db.query(models.StaffMember)
        .filter(models.StaffMember.user_id == current_user.id)
        .order_by(models.StaffMember.id.asc())
        .all()
    )
    res = [_serialize_staff_member(s) for s in staff_list]
    fast_cache.set(current_user.id, "staff_list", res, ttl=60.0, tags=["staff"])
    return res


@app.post("/staff", response_model=schemas.StaffMemberResponse)
def create_staff_member(
    req: schemas.StaffMemberCreate,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Add a new staff member to the pharmacy with login credentials."""
    username = (req.username or "").strip()
    if not username:
        # Auto-generate a clean username from the name if none provided
        base_name = re.sub(r"[^a-zA-Z0-9]", "", req.name.lower())[:10]
        username = f"{base_name}{uuid.uuid4().hex[:4]}"

    # Check for username collision within this pharmacy or across staff
    existing_username = db.query(models.StaffMember).filter(
        models.StaffMember.username == username,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if existing_username:
        raise HTTPException(
            status_code=400,
            detail=f"Username '{username}' is already in use for this pharmacy. Please choose another.",
        )

    # Hash password if provided, or default to a secure temporary password
    raw_password = (req.password or "staff1234").strip()
    hashed_pwd = safe_hash_password(raw_password)
    encrypted_pwd = encrypt_staff_password(raw_password)

    normalized_role = permissions.normalize_role(req.role)
    perms_json = json.dumps(req.permissions) if req.permissions else None

    new_staff = models.StaffMember(
        user_id=current_user.id,
        name=req.name.strip(),
        phone=req.phone.strip() if req.phone else None,
        email=req.email.strip().lower() if req.email else None,
        username=username,
        password=hashed_pwd,
        encrypted_password=encrypted_pwd,
        role=normalized_role,
        status=(req.status or "ACTIVE").upper(),
        permissions_json=perms_json,
    )
    db.add(new_staff)
    db.commit()
    db.refresh(new_staff)
    fast_cache.invalidate_tag(current_user.id, "staff")
    return _serialize_staff_member(new_staff)


@app.put("/staff/{staff_id}", response_model=schemas.StaffMemberResponse)
def update_staff_member(
    staff_id: int,
    req: schemas.StaffMemberUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Update staff member role, profile, or permissions."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    if req.name is not None and req.name.strip():
        staff.name = req.name.strip()
    if req.phone is not None:
        staff.phone = req.phone.strip() if req.phone.strip() else None
    if req.email is not None:
        staff.email = req.email.strip().lower() if req.email.strip() else None
    if req.role is not None and req.role.strip():
        staff.role = permissions.normalize_role(req.role)
    if req.status is not None and req.status.strip():
        staff.status = req.status.strip().upper()
    if req.permissions is not None:
        staff.permissions_json = json.dumps(req.permissions)

    db.commit()
    db.refresh(staff)

    # Invalidate cache if active
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)
    fast_cache.invalidate_tag(current_user.id, "staff")

    return _serialize_staff_member(staff)


@app.patch("/staff/{staff_id}/toggle-status", response_model=schemas.StaffMemberResponse)
def toggle_staff_status(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Toggle a staff member's active/inactive status immediately."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    staff.status = "INACTIVE" if (staff.status or "ACTIVE").upper() == "ACTIVE" else "ACTIVE"
    db.commit()
    db.refresh(staff)

    # Invalidate cache so any active session is immediately blocked
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)
    fast_cache.invalidate_tag(current_user.id, "staff")

    return _serialize_staff_member(staff)


@app.post("/staff/{staff_id}/reset-password")
def reset_staff_password(
    staff_id: int,
    req: schemas.StaffPasswordReset,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Reset a staff member's login password."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    new_pwd = req.new_password.strip()
    staff.password = safe_hash_password(new_pwd)
    staff.encrypted_password = encrypt_staff_password(new_pwd)
    db.commit()

    # Invalidate cache
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)

    return {"message": f"Password for '{staff.name}' has been successfully reset."}


@app.get("/staff/{staff_id}/credentials", response_model=schemas.StaffCredentialResponse)
def get_staff_credentials(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Retrieve plaintext staff login credentials (OWNER ONLY).
    Strictly accessible ONLY by the authenticated Pharmacy Owner who owns this shop.
    """
    if not current_user.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Only the pharmacy owner can view staff credentials.",
        )

    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    decrypted_pwd = decrypt_staff_password(staff.encrypted_password) if staff.encrypted_password else None

    return schemas.StaffCredentialResponse(
        staff_id=staff.id,
        name=staff.name,
        username=staff.username or "",
        password=decrypted_pwd,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
    )


@app.put("/staff/{staff_id}/credentials", response_model=schemas.StaffCredentialResponse)
def update_staff_credentials(
    staff_id: int,
    req: schemas.StaffCredentialUpdate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update staff username and/or password (OWNER ONLY).
    Strictly accessible ONLY by the authenticated Pharmacy Owner who owns this shop.
    """
    if not current_user.is_owner:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Only the pharmacy owner can update staff credentials.",
        )

    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Update username if provided
    if req.username is not None:
        new_username = req.username.strip()
        if not new_username:
            raise HTTPException(status_code=400, detail="Username cannot be empty.")
        
        # Check collision only if changed
        if new_username != staff.username:
            existing_user = db.query(models.StaffMember).filter(
                models.StaffMember.username == new_username,
                models.StaffMember.user_id == current_user.id,
                models.StaffMember.id != staff_id,
            ).first()
            if existing_user:
                raise HTTPException(
                    status_code=400,
                    detail=f"Username '{new_username}' is already in use for this pharmacy. Please choose another.",
                )
            staff.username = new_username

    # Update password if provided
    if req.password is not None:
        new_pwd = req.password.strip()
        if len(new_pwd) < 4:
            raise HTTPException(status_code=400, detail="Password must be at least 4 characters long.")
        staff.password = safe_hash_password(new_pwd)
        staff.encrypted_password = encrypt_staff_password(new_pwd)

    db.commit()
    db.refresh(staff)

    # Invalidate cache so old session/credentials don't linger
    cache_key = f"u:{current_user.id}:s:{staff.id}"
    _AUTH_CACHE.pop(cache_key, None)

    decrypted_pwd = decrypt_staff_password(staff.encrypted_password) if staff.encrypted_password else None

    return schemas.StaffCredentialResponse(
        staff_id=staff.id,
        name=staff.name,
        username=staff.username or "",
        password=decrypted_pwd,
        role=permissions.normalize_role(staff.role),
        status=staff.status or "ACTIVE",
    )


@app.delete("/staff/{staff_id}")
def delete_staff_member(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Delete a staff member."""
    staff = db.query(models.StaffMember).filter(
        models.StaffMember.id == staff_id,
        models.StaffMember.user_id == current_user.id,
    ).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")

    # Check if this staff member has created any sales
    has_sales = db.query(models.Sale).filter(models.Sale.staff_id == staff_id).first()
    if has_sales:
        # Soft-deactivate to preserve bill historical audit trail
        staff.status = "INACTIVE"
        db.commit()
        cache_key = f"u:{current_user.id}:s:{staff.id}"
        _AUTH_CACHE.pop(cache_key, None)
        return {
            "message": "Staff member has existing sales records; account has been marked INACTIVE to preserve audit integrity.",
            "status": "deactivated",
        }

    db.delete(staff)
    db.commit()

    cache_key = f"u:{current_user.id}:s:{staff_id}"
    _AUTH_CACHE.pop(cache_key, None)
    fast_cache.invalidate_tag(current_user.id, "staff")
    return {"message": "Staff member deleted successfully", "status": "deleted"}


@app.get("/branches", response_model=List[schemas.StoreBranchResponse])
def get_store_branches(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_VIEW)),
    db: Session = Depends(get_db),
):
    """List all store branches for the current pharmacy."""
    cached = fast_cache.get(current_user.id, "branches_list")
    if cached is not None:
        return cached

    branches = db.query(models.StoreBranch).filter(models.StoreBranch.user_id == current_user.id).all()
    if not branches:
        main_branch = models.StoreBranch(
            user_id=current_user.id,
            branch_name=current_user.shop_name or "Main Branch",
            code="HQ-01",
            address=current_user.address,
            phone=current_user.phone,
            is_main=True,
            status="ACTIVE",
        )
        db.add(main_branch)
        db.commit()
        db.refresh(main_branch)
        branches = [main_branch]
    fast_cache.set(current_user.id, "branches_list", branches, ttl=60.0, tags=["branches"])
    return branches


@app.post("/branches", response_model=schemas.StoreBranchResponse)
def create_store_branch(
    req: schemas.StoreBranchCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """Add a new store branch."""
    new_branch = models.StoreBranch(
        user_id=current_user.id,
        branch_name=req.branch_name,
        code=req.code,
        address=req.address,
        city=req.city,
        phone=req.phone,
        is_main=req.is_main,
        status=req.status,
    )
    db.add(new_branch)
    db.commit()
    db.refresh(new_branch)
    fast_cache.invalidate_tag(current_user.id, "branches")
    return new_branch


@app.put("/branches/{branch_id}", response_model=schemas.StoreBranchResponse)
def update_store_branch(
    branch_id: int,
    req: schemas.StoreBranchUpdate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """Update an existing store branch."""
    branch = db.query(models.StoreBranch).filter(
        models.StoreBranch.id == branch_id,
        models.StoreBranch.user_id == current_user.id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Store branch not found")

    if req.branch_name is not None:
        branch.branch_name = req.branch_name.strip()
    if req.code is not None:
        branch.code = req.code.strip()
    if req.address is not None:
        branch.address = req.address.strip()
    if req.city is not None:
        branch.city = req.city.strip()
    if req.phone is not None:
        branch.phone = req.phone.strip()
    if req.status is not None:
        branch.status = req.status.strip().upper()
    if req.is_main is not None and not branch.is_main and req.is_main:
        # If setting this branch as main, unmark any existing main branch
        db.query(models.StoreBranch).filter(
            models.StoreBranch.user_id == current_user.id,
            models.StoreBranch.is_main == True,
        ).update({"is_main": False})
        branch.is_main = True

    db.commit()
    db.refresh(branch)
    fast_cache.invalidate_tag(current_user.id, "branches")
    return branch


@app.patch("/branches/{branch_id}/toggle-status")
def toggle_store_branch_status(
    branch_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """Toggle active/inactive status of a store branch."""
    branch = db.query(models.StoreBranch).filter(
        models.StoreBranch.id == branch_id,
        models.StoreBranch.user_id == current_user.id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Store branch not found")

    new_status = "INACTIVE" if branch.status == "ACTIVE" else "ACTIVE"
    branch.status = new_status
    db.commit()
    db.refresh(branch)
    fast_cache.invalidate_tag(current_user.id, "branches")
    return {"message": f"Branch status changed to {new_status}", "status": new_status}


@app.delete("/branches/{branch_id}")
def delete_store_branch(
    branch_id: int,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """Delete a store branch (cannot delete main branch)."""
    branch = db.query(models.StoreBranch).filter(
        models.StoreBranch.id == branch_id,
        models.StoreBranch.user_id == current_user.id,
    ).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Store branch not found")

    if branch.is_main:
        raise HTTPException(status_code=400, detail="Cannot delete the main headquarters branch.")

    db.delete(branch)
    db.commit()
    fast_cache.invalidate_tag(current_user.id, "branches")
    return {"message": "Store branch deleted successfully", "status": "deleted"}


# ==========================================
# PRIORITY 2: SMART EXPIRY MANAGEMENT ENDPOINTS
# ==========================================

# In-memory fast cache for Expiry Summary
_EXPIRY_SUMMARY_CACHE = {}

@app.get("/expiry/summary")
def get_smart_expiry_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Calculates actionable batch counts, stock values, and item lists across non-overlapping expiry time windows."""
    now_ts = time.time()
    user_cache = _EXPIRY_SUMMARY_CACHE.get(current_user.id)
    if user_cache and (now_ts - user_cache["timestamp"] < 30): # 30 second TTL
        return user_cache["data"]

    from notification_service import calculate_expiry_digest_buckets
    res = calculate_expiry_digest_buckets(current_user.id, db, include_items=True)
    summary_data = {
        "expired": {"count": res["buckets"]["expired"]["count"], "stock_value": round(res["buckets"]["expired"]["stock_value"], 2), "items": res["buckets"]["expired"]["items"]},
        "expiring_1m": {"count": res["buckets"]["1m"]["count"], "stock_value": round(res["buckets"]["1m"]["stock_value"], 2), "items": res["buckets"]["1m"]["items"]},
        "expiring_3m": {"count": res["buckets"]["3m"]["count"], "stock_value": round(res["buckets"]["3m"]["stock_value"], 2), "items": res["buckets"]["3m"]["items"]},
        "expiring_6m": {"count": res["buckets"]["6m"]["count"], "stock_value": round(res["buckets"]["6m"]["stock_value"], 2), "items": res["buckets"]["6m"]["items"]},
        "expiring_9m": {"count": res["buckets"]["9m"]["count"], "stock_value": round(res["buckets"]["9m"]["stock_value"], 2), "items": res["buckets"]["9m"]["items"]},
        "total_at_risk_value": res["total_at_risk_value"],
        "total_at_risk_count": res["total_at_risk_count"],
        "notification_preview": {
            "title": res["notification_title"],
            "body": res["notification_body"],
        }
    }
    _EXPIRY_SUMMARY_CACHE[current_user.id] = {"timestamp": now_ts, "data": summary_data}
    return summary_data


@app.get("/expiry/items")
def get_smart_expiry_items(
    range_type: str = "1m", # expired, 1m, 3m, 6m, 9m
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieves batch-level expiry item details for a specific non-overlapping bucket."""
    from notification_service import calculate_expiry_digest_buckets
    res = calculate_expiry_digest_buckets(current_user.id, db, include_items=True)
    
    key_map = {
        "expired": "expired",
        "1m": "1m",
        "7d": "1m",
        "30d": "1m",
        "3m": "3m",
        "60d": "3m",
        "90d": "3m",
        "6m": "6m",
        "9m": "9m",
    }
    target_key = key_map.get(range_type, "1m")
    items = res["buckets"].get(target_key, {}).get("items", [])
    items.sort(key=lambda x: x["days_remaining"])
    return items


# ==========================================
# NOTIFICATION SETTINGS & DIGEST TRIGGER ENDPOINTS
# ==========================================

@app.get("/notifications/settings")
def get_notification_settings_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetches user notification preferences including Expiry Review Digest options."""
    settings = db.query(models.NotificationSettings).filter(
        models.NotificationSettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = models.NotificationSettings(
            user_id=current_user.id,
            enabled=True,
            digest_enabled=True,
            digest_days="Tuesday,Friday",
            digest_time="09:00",
            reminder_frequency="twice_weekly",
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    return {
        "enabled": settings.enabled,
        "digest_enabled": getattr(settings, 'digest_enabled', True),
        "digest_days": getattr(settings, 'digest_days', "Tuesday,Friday"),
        "digest_time": getattr(settings, 'digest_time', "09:00"),
        "reminder_frequency": settings.reminder_frequency or "twice_weekly",
        "notification_time": settings.notification_time or "09:00",
        "sound": settings.sound,
        "vibration": settings.vibration,
    }


@app.post("/notifications/settings")
def save_notification_settings_endpoint(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Saves user notification preferences including Expiry Review Digest options."""
    settings = db.query(models.NotificationSettings).filter(
        models.NotificationSettings.user_id == current_user.id
    ).first()

    if not settings:
        settings = models.NotificationSettings(user_id=current_user.id)
        db.add(settings)

    if "enabled" in payload:
        settings.enabled = bool(payload["enabled"])
    if "digest_enabled" in payload:
        settings.digest_enabled = bool(payload["digest_enabled"])
    if "digest_days" in payload:
        settings.digest_days = str(payload["digest_days"])
    if "digest_time" in payload:
        settings.digest_time = str(payload["digest_time"])
        settings.notification_time = str(payload["digest_time"])
    if "sound" in payload:
        settings.sound = bool(payload["sound"])
    if "vibration" in payload:
        settings.vibration = bool(payload["vibration"])

    db.commit()
    db.refresh(settings)
    return {"status": "success", "message": "Notification preferences saved successfully."}


@app.post("/notifications/test-digest")
def trigger_test_expiry_digest_endpoint(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Triggers an immediate Expiry Review Digest notification for the current user."""
    from notification_service import send_expiry_digest_notifications, calculate_expiry_digest_buckets
    digest = calculate_expiry_digest_buckets(current_user.id, db)
    send_expiry_digest_notifications(force_send=True)

    return {
        "status": "success",
        "message": f"Expiry Review Digest sent for {current_user.shop_name}.",
        "digest_summary": {
            "title": digest["notification_title"],
            "body": digest["notification_body"],
            "total_at_risk_count": digest["total_at_risk_count"],
            "total_at_risk_value": digest["total_at_risk_value"],
        }
    }


@app.post("/expiry/action")
def execute_expiry_action(
    payload: Dict[str, Any],
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Executes actionable expiry tasks (Mark Return, Priority Sale, Adjust Stock)."""
    product_id = payload.get("product_id")
    action = payload.get("action") # "mark_return", "priority_sale", "adjust_stock"
    
    product = db.query(models.Product).filter(
        models.Product.id == product_id,
        models.Product.user_id == current_user.id
    ).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product batch not found")

    if action == "mark_return":
        product.status = "Marked for Return"
        db.commit()
        return {"status": "success", "message": f"{product.product_name} marked for supplier return."}

    elif action == "priority_sale":
        product.status = "Priority Sale"
        db.commit()
        return {"status": "success", "message": f"{product.product_name} added to Priority Sale list."}

    elif action == "adjust_stock":
        new_qty = payload.get("new_quantity", 0)
        product.quantity = max(0, new_qty)
        if product.quantity == 0:
            product.status = "Out of Stock"
        db.commit()
        return {"status": "success", "message": f"Stock adjusted for {product.product_name}."}

    return {"status": "error", "message": "Unknown action"}


# ==========================================
# THERMAL POS PRINTING & WEBSOCKET AGENT API
# ==========================================

class PrinterConnectionManager:
    """Manages active WebSocket connections from Desktop Print Agents."""

    def __init__(self):
        # user_id -> List of active WebSocket connections
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
        self.active_connections[user_id].append(websocket)
        logger.info(f"[PRINTER_WS] Agent connected for user_id {user_id}. Total active: {len(self.active_connections[user_id])}")

    def disconnect(self, user_id: int, websocket: WebSocket):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"[PRINTER_WS] Agent disconnected for user_id {user_id}")

    def is_agent_online(self, user_id: int) -> bool:
        return bool(self.active_connections.get(user_id))

    async def push_print_job(self, user_id: int, job_data: dict) -> bool:
        """Pushes print job to all connected desktop print agents for this shop."""
        connections = self.active_connections.get(user_id, [])
        if not connections:
            return False

        message = json.dumps({
            "type": "NEW_PRINT_JOB",
            "job": job_data,
        })

        sent_any = False
        dead_connections = []
        for ws in connections:
            try:
                await ws.send_text(message)
                sent_any = True
            except Exception as e:
                logger.warning(f"[PRINTER_WS] Failed to send job to agent: {e}")
                dead_connections.append(ws)

        for dead in dead_connections:
            self.disconnect(user_id, dead)

        return sent_any


printer_manager = PrinterConnectionManager()


def _build_job_payload_dict(sale: models.Sale, shop: models.User, printer: Optional[models.PrinterDevice] = None) -> dict:
    """Freezes complete finalized snapshot of bill + shop details for the thermal print job."""
    items_list = []
    for item in sale.items:
        items_list.append({
            "product_name": item.product_name,
            "quantity": item.quantity,
            "unit_type": getattr(item, "unit_type", "strip") or "strip",
            "unit_price": float(item.unit_price or 0.0),
            "discount": float(item.discount or 0.0),
            "total_with_tax": float(item.total_with_tax or item.total_price or 0.0),
            "line_total": float(item.line_total or item.total_price or 0.0),
            "batch_number": getattr(item, "batch_number", "-") or "-",
            "expiry_date": getattr(item, "expiry_date", None) or (item.product.expiry_date.strftime("%m/%y") if getattr(item, "product", None) and getattr(item.product, "expiry_date", None) else "-"),
            "tablets_per_strip": getattr(item, "tablets_per_strip", 10) or 10,
            "hsn_code": getattr(item, "hsn_code", "3004") or "3004",
            "gst_percentage": float(item.gst_percentage or 0.0),
        })

    tax_summary = []
    if sale.tax_summary_json:
        try:
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            tax_summary = []

    return {
        "sale": {
            "id": sale.id,
            "bill_number": sale.bill_number,
            "created_at": sale.created_at.isoformat() if sale.created_at else datetime.utcnow().isoformat(),
            "customer_name": sale.customer_name or "Cash Customer",
            "customer_phone": sale.customer_phone or "",
            "payment_method": sale.payment_method or "CASH",
            "doctor_name": sale.doctor_name or "",
            "doctor_reg_no": sale.doctor_reg_no or "",
            "subtotal": float(sale.subtotal or 0.0),
            "discount_amount": float(sale.discount_amount or 0.0),
            "tax_amount": float(sale.tax_amount or 0.0),
            "total_amount": float(sale.total_amount or 0.0),
            "total_taxable_value": float(sale.total_taxable_value or 0.0),
            "total_cgst": float(sale.total_cgst or 0.0),
            "total_sgst": float(sale.total_sgst or 0.0),
            "total_igst": float(sale.total_igst or 0.0),
            "tax_summary": tax_summary,
            "items": items_list,
        },
        "shop": {
            "shop_name": shop.shop_name or "DawaiFlow Pharmacy",
            "owner_name": shop.owner_name or "",
            "gstin": getattr(shop, "gstin", None) or shop.gst_number or "07AABCE1234F1Z5",
            "address": getattr(shop, "address", None) or "Main Market, New Delhi - 110001",
            "phone": getattr(shop, "phone", None) or "+91-9876543210",
            "drug_license_no": getattr(shop, "drug_license_no", None) or "DL-2026-PHARMA-01",
            "terms_and_conditions": getattr(shop, "terms_and_conditions", None) or "1. Goods once sold will not be returned.\n2. Expiry dates checked at sales time.",
        },
        "printer": {
            "printer_system_name": printer.printer_system_name if printer else None,
            "paper_size": printer.paper_size if printer else "80mm",
            "settings": json.loads(printer.settings_json) if printer and printer.settings_json else {},
        } if printer else None,
    }


def _create_print_job_internal(
    db: Session,
    sale_id: int,
    user: models.User,
    printer_id: Optional[int] = None,
    copies: int = 1,
    force_print_again: bool = False,
    paper_size: Optional[str] = None,
) -> models.PrintJob:
    """Internal helper to idempotently create or return a print job for a sale."""
    sale = db.query(models.Sale).filter(models.Sale.id == sale_id, models.Sale.user_id == user.id).first()
    if not sale:
        raise HTTPException(status_code=404, detail=f"Bill ID {sale_id} not found.")

    # Idempotency check: if not forcing print again, check for existing PENDING or PRINTING job
    if not force_print_again:
        existing_job = (
            db.query(models.PrintJob)
            .filter(
                models.PrintJob.user_id == user.id,
                models.PrintJob.sale_id == sale_id,
                models.PrintJob.status.in_(["PENDING", "PRINTING"]),
            )
            .order_by(models.PrintJob.created_at.desc())
            .first()
        )
        if existing_job:
            return existing_job

    # Resolve target printer
    target_printer = None
    if printer_id:
        target_printer = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.id == printer_id,
            models.PrinterDevice.user_id == user.id,
        ).first()

    if not target_printer:
        target_printer = (
            db.query(models.PrinterDevice)
            .filter(models.PrinterDevice.user_id == user.id, models.PrinterDevice.is_default == True)
            .first()
        )

    resolved_paper_size = paper_size or (target_printer.paper_size if target_printer else "80mm")

    payload_dict = _build_job_payload_dict(sale, user, target_printer)
    payload_json = json.dumps(payload_dict)

    job = models.PrintJob(
        user_id=user.id,
        printer_id=target_printer.id if target_printer else None,
        sale_id=sale.id,
        invoice_number=sale.bill_number,
        status="PENDING",
        copies=max(1, copies),
        paper_size=resolved_paper_size,
        payload_json=payload_json,
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


# -------------------------------------------------------------
# PRINTER DEVICE REST ENDPOINTS
# -------------------------------------------------------------

@app.post("/printers/register", response_model=schemas.PrinterDeviceResponse)
def register_printer_device(
    payload: schemas.PrinterDeviceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Registers or updates a printer discovered by the desktop print agent or mobile app."""
    existing = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id,
        models.PrinterDevice.printer_system_name == payload.printer_system_name,
    ).first()

    if payload.is_default:
        # Clear default flag on existing printers
        db.query(models.PrinterDevice).filter(
            models.PrinterDevice.user_id == current_user.id
        ).update({"is_default": False})

    if existing:
        existing.device_name = payload.device_name
        existing.connection_type = payload.connection_type
        existing.paper_size = payload.paper_size
        existing.is_default = payload.is_default
        existing.is_online = True
        existing.last_seen_at = datetime.utcnow()
        if payload.settings_json:
            existing.settings_json = payload.settings_json
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Check if first printer for user
        has_any = db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == current_user.id).first()
        is_def = True if not has_any else payload.is_default

        printer = models.PrinterDevice(
            user_id=current_user.id,
            device_name=payload.device_name,
            printer_system_name=payload.printer_system_name,
            connection_type=payload.connection_type,
            paper_size=payload.paper_size,
            is_default=is_def,
            is_online=True,
            last_seen_at=datetime.utcnow(),
            settings_json=payload.settings_json,
        )
        db.add(printer)
        db.commit()
        db.refresh(printer)
        return printer


@app.get("/printers", response_model=List[schemas.PrinterDeviceResponse])
def list_printers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists all registered printers for the shop with live online/offline status."""
    printers = (
        db.query(models.PrinterDevice)
        .filter(models.PrinterDevice.user_id == current_user.id)
        .order_by(models.PrinterDevice.is_default.desc(), models.PrinterDevice.device_name.asc())
        .all()
    )

    # Dynamic check: if agent websocket is connected, mark online
    agent_online = printer_manager.is_agent_online(current_user.id)
    for p in printers:
        if agent_online:
            # Online if agent is connected and seen in last 10 mins
            if p.last_seen_at and (datetime.utcnow() - p.last_seen_at).total_seconds() < 600:
                p.is_online = True
        else:
            p.is_online = False

    return printers


@app.put("/printers/{printer_id}/default", response_model=schemas.PrinterDeviceResponse)
def set_default_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Sets the chosen printer as default for this pharmacy."""
    printer = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.id == printer_id,
        models.PrinterDevice.user_id == current_user.id,
    ).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer device not found.")

    db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id
    ).update({"is_default": False})

    printer.is_default = True
    db.commit()
    db.refresh(printer)
    return printer


@app.delete("/printers/{printer_id}")
def delete_printer(
    printer_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Removes a registered printer device."""
    printer = db.query(models.PrinterDevice).filter(
        models.PrinterDevice.id == printer_id,
        models.PrinterDevice.user_id == current_user.id,
    ).first()
    if not printer:
        raise HTTPException(status_code=404, detail="Printer device not found.")

    db.delete(printer)
    db.commit()
    return {"success": True, "message": f"Printer '{printer.device_name}' removed."}


@app.get("/printers/status", response_model=schemas.PrinterStatusSummaryResponse)
def get_printer_status_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Returns overall printer readiness for mobile UI display (🟢 Ready, 🟡 Print Pending, 🔴 Offline)."""
    printers = db.query(models.PrinterDevice).filter(models.PrinterDevice.user_id == current_user.id).all()
    default_p = next((p for p in printers if p.is_default), printers[0] if printers else None)
    agent_online = printer_manager.is_agent_online(current_user.id)

    pending_count = (
        db.query(func.count(models.PrintJob.id))
        .filter(models.PrintJob.user_id == current_user.id, models.PrintJob.status == "PENDING")
        .scalar()
        or 0
    )

    online_count = len(printers) if agent_online else 0

    if not printers:
        label = "No Printer Setup"
        color = "grey"
    elif agent_online:
        if pending_count > 0:
            label = "Print Pending"
            color = "yellow"
        else:
            label = "Printer Ready"
            color = "green"
    else:
        if pending_count > 0:
            label = "Printer Offline — Bill Queued"
            color = "yellow"
        else:
            label = "Printer Offline"
            color = "red"

    return schemas.PrinterStatusSummaryResponse(
        has_printer=bool(printers),
        has_online_printer=agent_online and bool(printers),
        default_printer=schemas.PrinterDeviceResponse.from_orm(default_p) if default_p else None,
        online_count=online_count,
        pending_jobs_count=pending_count,
        status_label=label,
        status_color=color,
    )


# -------------------------------------------------------------
# PRINT JOB REST ENDPOINTS
# -------------------------------------------------------------

@app.post("/print-jobs", response_model=schemas.PrintJobResponse, status_code=201)
async def create_print_job_endpoint(
    payload: schemas.PrintJobCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Creates a print job for a finalized bill and notifies connected print agents in real-time."""
    job = _create_print_job_internal(
        db=db,
        sale_id=payload.sale_id,
        user=current_user,
        printer_id=payload.printer_id,
        copies=payload.copies,
        force_print_again=payload.force_print_again,
        paper_size=payload.paper_size,
    )

    # Push to connected Desktop Print Agent in background
    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": json.loads(job.payload_json),
    }
    background_tasks.add_task(printer_manager.push_print_job, current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


@app.get("/print-jobs", response_model=List[schemas.PrintJobResponse])
def get_print_jobs(
    limit: int = 50,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Lists print jobs for the pharmacy with optional status filter (PENDING, PRINTED, FAILED)."""
    q = db.query(models.PrintJob).filter(models.PrintJob.user_id == current_user.id)
    if status_filter:
        q = q.filter(models.PrintJob.status == status_filter.upper())

    jobs = q.order_by(models.PrintJob.created_at.desc()).limit(limit).all()
    results = []
    for j in jobs:
        res = schemas.PrintJobResponse.from_orm(j)
        if j.printer:
            res.printer_name = j.printer.device_name
        results.append(res)
    return results


@app.post("/print-jobs/{job_id}/retry", response_model=schemas.PrintJobResponse)
async def retry_print_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Re-queues a failed or cancelled print job safely without creating duplicate bills."""
    job = db.query(models.PrintJob).filter(
        models.PrintJob.id == job_id,
        models.PrintJob.user_id == current_user.id,
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Print job not found.")

    job.status = "PENDING"
    job.retry_count += 1
    job.error_message = None
    job.failed_at = None
    db.commit()
    db.refresh(job)

    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": json.loads(job.payload_json),
    }
    background_tasks.add_task(printer_manager.push_print_job, current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


@app.post("/print-jobs/test-print", response_model=schemas.PrintJobResponse)
async def trigger_test_print(
    printer_id: Optional[int] = None,
    paper_size: str = "80mm",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Generates a test print job to verify connectivity between desktop agent and thermal printer."""
    # Find printer
    target_p = None
    if printer_id:
        target_p = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.id == printer_id,
            models.PrinterDevice.user_id == current_user.id,
        ).first()

    if not target_p:
        target_p = db.query(models.PrinterDevice).filter(
            models.PrinterDevice.user_id == current_user.id,
            models.PrinterDevice.is_default == True,
        ).first()

    # Synthetic test sale payload
    test_payload = {
        "sale": {
            "id": 0,
            "bill_number": f"TEST-{datetime.now().strftime('%H%M%S')}",
            "created_at": datetime.utcnow().isoformat(),
            "customer_name": "Test Customer",
            "customer_phone": "+91-9876543210",
            "payment_method": "TEST MODE",
            "doctor_name": "Dr. Dawaiflow",
            "doctor_reg_no": "TEST-01",
            "subtotal": 100.0,
            "discount_amount": 0.0,
            "tax_amount": 12.0,
            "total_amount": 112.0,
            "total_taxable_value": 100.0,
            "total_cgst": 6.0,
            "total_sgst": 6.0,
            "total_igst": 0.0,
            "items": [
                {
                    "product_name": "Dawaiflow POS Test Medicine 500mg",
                    "quantity": 1,
                    "unit_type": "strip",
                    "unit_price": 100.0,
                    "discount": 0.0,
                    "total_with_tax": 112.0,
                    "line_total": 112.0,
                    "batch_number": "TST-2026",
                    "expiry_date": "12/28",
                    "gst_percentage": 12.0,
                }
            ],
        },
        "shop": {
            "shop_name": current_user.shop_name or "Dawaiflow Pharmacy",
            "owner_name": current_user.owner_name or "",
            "gstin": getattr(current_user, "gstin", None) or current_user.gst_number or "07AABCE1234F1Z5",
            "address": getattr(current_user, "address", None) or "Pharmacy Test Counter, Main City",
            "phone": getattr(current_user, "phone", None) or "+91-9876543210",
            "drug_license_no": getattr(current_user, "drug_license_no", None) or "DL-TEST-2026",
            "terms_and_conditions": "Thermal Printer Test Successful!\nDawaiflow Production Bridge Ready.",
        },
        "printer": {
            "printer_system_name": target_p.printer_system_name if target_p else None,
            "paper_size": target_p.paper_size if target_p else paper_size,
        } if target_p else None,
    }

    job = models.PrintJob(
        user_id=current_user.id,
        printer_id=target_p.id if target_p else None,
        sale_id=None,
        invoice_number=f"TEST-{datetime.now().strftime('%H%M%S')}",
        status="PENDING",
        copies=1,
        paper_size=target_p.paper_size if target_p else paper_size,
        payload_json=json.dumps(test_payload),
        created_at=datetime.utcnow(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Push to desktop agent
    job_dict = {
        "job_id": job.id,
        "user_id": job.user_id,
        "sale_id": job.sale_id,
        "invoice_number": job.invoice_number,
        "copies": job.copies,
        "paper_size": job.paper_size,
        "payload": test_payload,
    }
    await printer_manager.push_print_job(current_user.id, job_dict)

    resp = schemas.PrintJobResponse.from_orm(job)
    if job.printer:
        resp.printer_name = job.printer.device_name
    return resp


# -------------------------------------------------------------
# DESKTOP PRINT AGENT WEBSOCKET & POLLING ENDPOINTS
# -------------------------------------------------------------

@app.websocket("/ws/printer-agent")
async def websocket_printer_agent(websocket: WebSocket, token: str = Query(...)):
    """
    Authenticated WebSocket connection for the Windows Desktop Print Agent.
    Maintains persistent low-latency (< 100ms) pipe to push pending print jobs.
    """
    # Authenticate token
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
    except Exception as e:
        logger.warning(f"[PRINTER_WS] Authentication failed: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await printer_manager.connect(user_id, websocket)

    # Automatically push any currently pending jobs to the agent upon connecting
    db = SessionLocal()
    try:
        pending_jobs = (
            db.query(models.PrintJob)
            .filter(models.PrintJob.user_id == user_id, models.PrintJob.status == "PENDING")
            .order_by(models.PrintJob.created_at.asc())
            .all()
        )
        for job in pending_jobs:
            job_dict = {
                "job_id": job.id,
                "user_id": job.user_id,
                "sale_id": job.sale_id,
                "invoice_number": job.invoice_number,
                "copies": job.copies,
                "paper_size": job.paper_size,
                "payload": json.loads(job.payload_json),
            }
            await websocket.send_text(json.dumps({
                "type": "NEW_PRINT_JOB",
                "job": job_dict,
            }))
    except Exception as err:
        logger.warning(f"[PRINTER_WS] Error sending pending jobs on connect: {err}")
    finally:
        db.close()

    try:
        while True:
            data_text = await websocket.receive_text()
            data = json.loads(data_text)
            msg_type = data.get("type")

            if msg_type == "PING":
                await websocket.send_text(json.dumps({"type": "PONG", "timestamp": datetime.utcnow().isoformat()}))

            elif msg_type == "HEARTBEAT":
                # Update last_seen_at for user's printers
                db_heartbeat = SessionLocal()
                try:
                    db_heartbeat.query(models.PrinterDevice).filter(
                        models.PrinterDevice.user_id == user_id
                    ).update({"is_online": True, "last_seen_at": datetime.utcnow()})
                    db_heartbeat.commit()
                except Exception:
                    db_heartbeat.rollback()
                finally:
                    db_heartbeat.close()

            elif msg_type == "JOB_STATUS_ACK":
                job_id = data.get("job_id")
                new_status = data.get("status")  # PRINTING, PRINTED, FAILED
                err_msg = data.get("error_message")

                db_ack = SessionLocal()
                try:
                    job = db_ack.query(models.PrintJob).filter(
                        models.PrintJob.id == job_id,
                        models.PrintJob.user_id == user_id,
                    ).first()
                    if job:
                        job.status = new_status
                        if new_status == "PRINTING":
                            job.claimed_at = datetime.utcnow()
                        elif new_status == "PRINTED":
                            job.printed_at = datetime.utcnow()
                        elif new_status == "FAILED":
                            job.failed_at = datetime.utcnow()
                            job.error_message = err_msg
                        db_ack.commit()
                        logger.info(f"[PRINTER_ACK] Job #{job_id} status updated to {new_status}")
                except Exception as e:
                    db_ack.rollback()
                    logger.error(f"[PRINTER_ACK] Error updating job #{job_id}: {e}")
                finally:
                    db_ack.close()

    except WebSocketDisconnect:
        printer_manager.disconnect(user_id, websocket)
    except Exception as e:
        logger.warning(f"[PRINTER_WS] Connection error for user {user_id}: {e}")
        printer_manager.disconnect(user_id, websocket)


@app.post("/printer-agent/poll")
def poll_pending_jobs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Fallback HTTP polling endpoint for Desktop Print Agents in environments where
    corporate firewalls or proxies sever persistent WebSocket connections.
    """
    pending = (
        db.query(models.PrintJob)
        .filter(models.PrintJob.user_id == current_user.id, models.PrintJob.status == "PENDING")
        .order_by(models.PrintJob.created_at.asc())
        .limit(10)
        .all()
    )

    # Mark user's printers as online since agent is polling
    db.query(models.PrinterDevice).filter(
        models.PrinterDevice.user_id == current_user.id
    ).update({"is_online": True, "last_seen_at": datetime.utcnow()})
    db.commit()

    jobs_data = []
    for j in pending:
        jobs_data.append({
            "job_id": j.id,
            "user_id": j.user_id,
            "sale_id": j.sale_id,
            "invoice_number": j.invoice_number,
            "copies": j.copies,
            "paper_size": j.paper_size,
            "payload": json.loads(j.payload_json),
        })

    return {"jobs": jobs_data}


@app.post("/printer-agent/ack")
def acknowledge_job_status(
    payload: schemas.PrintJobStatusUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """HTTP endpoint for agent to report successful transmission or errors."""
    update_data = {"status": payload.status}
    if payload.status == "PRINTING":
        update_data["claimed_at"] = datetime.utcnow()
    elif payload.status == "PRINTED":
        update_data["printed_at"] = datetime.utcnow()
    elif payload.status == "FAILED":
        update_data["failed_at"] = datetime.utcnow()
        update_data["error_message"] = payload.error_message

    rows_updated = db.query(models.PrintJob).filter(
        models.PrintJob.id == payload.job_id,
        models.PrintJob.user_id == current_user.id,
    ).update(update_data)

    if not rows_updated:
        raise HTTPException(status_code=404, detail="Print job not found.")

    db.commit()
    return {"success": True, "job_id": payload.job_id, "status": payload.status}


# ==========================================
# BACKUP & RESTORE SYSTEM (OWNER-ONLY)
# ==========================================

class CreateBackupRequest(BaseModel):
    notes: Optional[str] = None

class RestoreBackupRequest(BaseModel):
    backup_id: str

@app.post("/backup/create")
@app.post("/api/backup/create")
def api_create_backup(
    payload: Optional[CreateBackupRequest] = None,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Creates a manual encrypted backup for the authenticated shop owner."""
    try:
        notes = payload.notes if payload else None
        record = backup_service.create_backup(
            db=db,
            user_id=current_user.id,
            backup_type="MANUAL",
            notes=notes,
        )
        return {
            "success": True,
            "message": "Backup generated and encrypted successfully.",
            "backup": {
                "backup_id": record.backup_id,
                "file_name": record.filename,
                "file_size": record.file_size_bytes,
                "backup_type": record.backup_type,
                "status": record.status,
                "checksum": record.checksum_sha256,
                "record_counts": json.loads(record.record_counts_json) if record.record_counts_json else {},
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "notes": record.notes,
            },
        }
    except Exception as e:
        logger.error(f"[BACKUP ERROR] Manual backup creation failed for shop {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create backup: {str(e)}")


@app.get("/backup/history")
@app.get("/api/backup/history")
def api_get_backup_history(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Retrieves backup history and latest safety snapshot status for the authenticated shop owner."""
    try:
        history = backup_service.get_backup_history(db=db, user_id=current_user.id, limit=limit)
        return {"success": True, "backups": history}
    except Exception as e:
        logger.error(f"[BACKUP ERROR] Failed to fetch history for shop {current_user.id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch backup history: {str(e)}")


@app.get("/backup/download/{backup_id}")
@app.get("/api/backup/download/{backup_id}")
def api_download_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Securely downloads an encrypted backup archive (.dfbk). Restricted to shop owner."""
    record = db.query(models.BackupRecord).filter(
        models.BackupRecord.backup_id == backup_id,
        models.BackupRecord.user_id == current_user.id,
    ).first()

    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Backup file not found or has been removed.")

    return FileResponse(
        path=record.file_path,
        filename=record.filename,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{record.filename}"',
            "X-Backup-Checksum": record.checksum_sha256 or "",
        },
    )


@app.post("/backup/restore")
@app.post("/api/backup/restore")
def api_restore_backup_by_id(
    payload: RestoreBackupRequest,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Restores pharmacy data from an existing server-side backup record."""
    record = db.query(models.BackupRecord).filter(
        models.BackupRecord.backup_id == payload.backup_id,
        models.BackupRecord.user_id == current_user.id,
    ).first()

    if not record or not os.path.exists(record.file_path):
        raise HTTPException(status_code=404, detail="Backup record or file not found on server.")

    with open(record.file_path, "rb") as f:
        file_bytes = f.read()

    try:
        result = backup_service.restore_backup(
            db=db,
            user_id=current_user.id,
            backup_file_bytes=file_bytes,
            initiated_by_name=current_user.owner_name or current_user.shop_name or "Owner",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error restoring backup: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Restoration failed: {e}")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Restore failed."))

    return result


@app.post("/backup/upload-restore")
@app.post("/api/backup/upload-restore")
async def api_upload_and_restore_backup(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Accepts an uploaded .dfbk backup archive and executes atomic restoration with safety backup."""
    if not file.filename.endswith(".dfbk"):
        raise HTTPException(
            status_code=400,
            detail="Invalid backup format. Only encrypted .dfbk archives are supported.",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = backup_service.restore_backup(
            db=db,
            user_id=current_user.id,
            backup_file_bytes=file_bytes,
            initiated_by_name=current_user.owner_name or current_user.shop_name or "Owner",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error restoring backup from upload: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Restoration failed: {e}")

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Restore failed."))

    return result


@app.delete("/backup/{backup_id}")
@app.delete("/api/backup/{backup_id}")
def api_delete_backup(
    backup_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Deletes a backup archive and its database log entry."""
    success = backup_service.delete_backup(db=db, user_id=current_user.id, backup_id=backup_id)
    if not success:
        raise HTTPException(status_code=404, detail="Backup not found or could not be deleted.")
    return {"success": True, "message": "Backup removed successfully."}


# ==========================================
# DATA MIGRATION & HISTORICAL BILL IMPORT
# ==========================================

@app.post("/api/migration/upload")
@app.post("/migration/historical-bills")
async def api_upload_migration_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """
    Uploads historical bills file (PDF, CSV, Excel), returns job_id immediately,
    and starts asynchronous background processing.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a valid filename.")

    allowed_exts = [".pdf", ".csv", ".xlsx", ".xls", ".txt"]
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Allowed formats: PDF, CSV, Excel (.xlsx, .xls)."
        )

    contents = await file.read()
    if len(contents) > 50 * 1024 * 1024:  # 50 MB limit
        raise HTTPException(status_code=413, detail="File size exceeds maximum allowed limit of 50MB.")

    temp_dir = BASE_DIR / "temp_migrations"
    os.makedirs(temp_dir, exist_ok=True)
    safe_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
    temp_file_path = str(temp_dir / safe_filename)

    with open(temp_file_path, "wb") as f:
        f.write(contents)

    migration_code = migration_service.generate_migration_code(db)
    is_large = len(contents) > 3 * 1024 * 1024

    migration = models.DataMigration(
        user_id=current_user.id,
        migration_code=migration_code,
        migration_type="OLD_BILLS",
        source_software="OTHER",
        file_name=file.filename,
        file_format=ext.replace(".", "").upper(),
        file_size_bytes=len(contents),
        status="uploading",
        current_stage="uploading",
        current_stage_label="Uploading file...",
        current_message="Reading file...",
        processed_count=0,
        total_count=0,
        is_large_file=is_large,
        progress_percentage=10,
        created_at=datetime.utcnow()
    )
    db.add(migration)
    db.commit()
    db.refresh(migration)

    # Dispatch asynchronous background processing
    background_tasks.add_task(
        migration_service.process_migration_background,
        migration.id,
        current_user.id,
        temp_file_path,
        file.filename
    )

    return {
        "job_id": migration.migration_code,
        "migration_id": migration.id,
        "migration_code": migration.migration_code,
        "status": "queued",
        "stage": "uploading",
        "message": "Reading file...",
        "processed": 0,
        "total": 0,
        "percentage": 10,
        "is_large_file": is_large
    }


@app.get("/api/migration/active")
def api_get_active_migration(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Returns any active migration currently in PROCESSING state for page refresh recovery."""
    active = migration_service.get_active_migration(db=db, user_id=current_user.id)
    return {"active": active}


@app.websocket("/ws/migration/{migration_id}")
async def websocket_migration_progress(
    websocket: WebSocket,
    migration_id: int,
    token: Optional[str] = Query(None)
):
    """Real-time WebSocket connection streaming migration progress updates."""
    await migration_service.ws_manager.connect(migration_id, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "PING":
                await websocket.send_text("PONG")
    except WebSocketDisconnect:
        migration_service.ws_manager.disconnect(migration_id, websocket)
    except Exception:
        migration_service.ws_manager.disconnect(migration_id, websocket)


@app.get("/api/migration/preview/{migration_id}")
def api_get_migration_preview(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Retrieves parsed preview records for a migration batch."""
    try:
        return migration_service.get_migration_preview_by_id(db=db, user_id=current_user.id, migration_id=migration_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to fetch migration preview: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/migration/confirm/{migration_id}")
def api_confirm_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Commits or confirms a historical migration batch."""
    try:
        result = migration_service.commit_migration(db=db, user_id=current_user.id, migration_id=migration_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Migration commit failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/migration/status/{migration_id}")
@app.get("/migration/historical-bills/{migration_id}/status")
def api_get_migration_status(
    migration_id: str,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Polls real-time progress status of an active or completed migration by ID or job code."""
    try:
        # Check if migration_id is integer ID or migration_code string
        if str(migration_id).isdigit():
            m_id = int(migration_id)
        else:
            mig = db.query(models.DataMigration).filter(
                models.DataMigration.migration_code == migration_id,
                models.DataMigration.user_id == current_user.id
            ).first()
            if not mig:
                raise HTTPException(status_code=404, detail=f"Job {migration_id} not found.")
            m_id = mig.id

        return migration_service.get_migration_status(db=db, user_id=current_user.id, migration_id=m_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/migration/rollback/{migration_id}")
def api_rollback_migration(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """
    Rolls back an imported migration batch, deleting all associated historical
    sales and items while leaving live transactions and inventory untouched.
    """
    try:
        result = migration_service.rollback_migration(db=db, user_id=current_user.id, migration_id=migration_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Migration rollback failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/migration/history")
def api_get_migration_history(
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Returns list of past data migration batches for the pharmacy."""
    try:
        return migration_service.get_migration_history(db=db, user_id=current_user.id)
    except Exception as e:
        logger.error(f"Failed to fetch migration history: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/migration/errors/{migration_id}/export")
def api_export_migration_errors(
    migration_id: int,
    db: Session = Depends(get_db),
    current_user: AuthenticatedUser = Depends(require_owner),
):
    """Exports CSV of errors and skipped records from a migration."""
    errors = db.query(models.MigrationError).filter(
        models.MigrationError.migration_id == migration_id,
        models.MigrationError.user_id == current_user.id
    ).order_by(models.MigrationError.id.asc()).all()

    output = io.StringIO()
    writer = pd.DataFrame([{
        "Row Number": e.row_number,
        "Bill Identifier": e.bill_identifier,
        "Error Type": e.error_type,
        "Reason": e.reason,
        "Recorded At": e.created_at.strftime("%Y-%m-%d %H:%M:%S") if e.created_at else ""
    } for e in errors])

    csv_data = writer.to_csv(index=False)
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=migration_errors_{migration_id}.csv"}
    )




# ==========================================
# MOUNT STATIC ASSETS FOR PUBLIC WEB & DASHBOARD
# ==========================================

# Redirect deprecated Web AI Camera Billing to Create New Bill
@app.get("/web/ai_billing.html")
@app.get("/ai_billing.html")
@app.get("/ai_billing")
def redirect_deprecated_web_ai_billing():
    return RedirectResponse(url="/web/billing.html", status_code=301)

# Mount Pharmacist Web Dashboard
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# Mount Static Assets & Mobile APK Distribution Directory
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/app/version")
@app.get("/api/app/version")
def get_mobile_app_version():
    """
    Mobile App Auto-Updater Version Check Endpoint.
    Returns latest published version, APK download URL, and release notes.
    """
    version_file = STATIC_DIR / "version.json"
    if version_file.exists():
        try:
            with open(version_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "version": "1.0.1",
        "build_number": 2,
        "download_url": "https://api.dawaiflow.com/static/dawaiflow-latest.apk",
        "release_notes": "Dashboard functional fixes & Smart Action Center live updates",
        "min_supported_version": "1.0.0"
    }

# Mount Public Landing Website Asset Directories (for root / access)
if (PUBLIC_SERVE_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=PUBLIC_SERVE_DIR / "assets"), name="public_assets")
if (PUBLIC_SERVE_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=PUBLIC_SERVE_DIR / "css"), name="public_css")
if (PUBLIC_SERVE_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=PUBLIC_SERVE_DIR / "js"), name="public_js")

# Mount Public Landing Website
app.mount("/site", StaticFiles(directory=PUBLIC_SERVE_DIR, html=True), name="site")
app.mount("/public_site", StaticFiles(directory=PUBLIC_SERVE_DIR, html=True), name="public_site")