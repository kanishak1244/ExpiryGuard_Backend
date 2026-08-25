import os
import json
import shutil
import re
from difflib import SequenceMatcher
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Response, status, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from passlib.context import CryptContext
from jose import jwt, JWTError
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from ai.gemini_service import scan_label
from ai.multi_item_scan_service import scan_multi_item
from pdf_generator import generate_invoice_pdf
import import_service
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler

import firebase_admin
from firebase_admin import credentials, messaging

# Internal Modules
import models
import schemas
import crud
from database import engine, Base, SessionLocal
from scheduler import start_scheduler
from notification_service import send_expiry_notifications
from email_service import send_pilot_lead_notification, send_test_email
from ai.gemini_service import scan_label
from ai.invoice_service import scan_invoice

# ==========================================
# CONFIGURATION & INITIALIZATION
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
PUBLIC_SITE_DIR = BASE_DIR / "public_site"
os.makedirs(WEB_DIR, exist_ok=True)
os.makedirs(PUBLIC_SITE_DIR, exist_ok=True)
load_dotenv(dotenv_path=BASE_DIR / ".env")

ALLOWED_IMAGE_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}
ALLOWED_DOC_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

def check_file_size(file: UploadFile, max_size: int = MAX_FILE_SIZE):
    """Safely determines uploaded file size without loading contents fully into RAM or writing fully to disk."""
    try:
        file.file.seek(0, 2)
        size = file.file.tell()
        file.file.seek(0)
        if size > max_size:
            raise HTTPException(
                status_code=400,
                detail=f"File size must not exceed {max_size // (1024 * 1024)} MB."
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Could not validate upload file size: {str(e)}"
        )

# Parse allowed CORS origins from environment or default to local origins
raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500")
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]

app = FastAPI(title="ExpiryGuard API", version="1.0.0")

@app.on_event("startup")
def warmup_database():
    try:
        from database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        print("[Startup] Database connection pool pre-warmed.")
    except Exception as e:
        print(f"[Startup] DB warmup warning: {e}")

# Security Headers & Cache Prevention Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
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
    allow_headers=["*"],
)
# Rate Limiter Setup (Supports distributed Redis backend if REDIS_URL is configured)
redis_storage_uri = os.getenv("REDIS_URL") or "memory://"
limiter = Limiter(key_func=get_remote_address, storage_uri=redis_storage_uri)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Security Setup (Dual-mode: Bearer Token + HttpOnly Session Cookie)
security = HTTPBearer(auto_error=False)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY is missing. Add it to the .env file.")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

# Firebase Setup
cred = credentials.Certificate("credentials/firebase_key.json")
firebase_admin.initialize_app(cred)

# Static Files Mount
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


def run_gst_migrations(db_engine):
    try:
        with db_engine.connect() as conn:
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS hsn_code VARCHAR DEFAULT '3004';"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS gst_rate FLOAT DEFAULT 12.0;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS gstin VARCHAR DEFAULT '07AABCE1234F1Z5';"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS address VARCHAR;"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS is_interstate BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_taxable_value FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_cgst FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_sgst FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS total_igst FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sales ADD COLUMN IF NOT EXISTS tax_summary_json TEXT;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS discount FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS total_price FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS batch_number VARCHAR;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS unit_type VARCHAR DEFAULT 'strip';"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS tablets_per_strip INTEGER;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS gst_percentage FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS gst_amount FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS hsn_code VARCHAR DEFAULT '3004';"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS taxable_value FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS cgst_rate FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS cgst_amount FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS sgst_rate FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS sgst_amount FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS igst_rate FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS igst_amount FLOAT DEFAULT 0.0;"))
            conn.execute(text("ALTER TABLE sale_items ADD COLUMN IF NOT EXISTS total_with_tax FLOAT DEFAULT 0.0;"))
            # Soft Delete Migration
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN DEFAULT FALSE;"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;"))
            conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS deleted_by INTEGER;"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_products_is_deleted ON products(is_deleted);"))
            conn.commit()
    except Exception as e:
        print(f"[MIGRATION WARNING] Schema migration note: {e}")


# Database Tables & Scheduler
Base.metadata.create_all(bind=engine)
run_gst_migrations(engine)
start_scheduler()


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

_USER_CACHE: Dict[int, Tuple[models.User, float]] = {}

def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
):
    token = None
    if credentials and credentials.credentials:
        token = credentials.credentials
    elif request.cookies.get("access_token"):
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a Bearer token or login to establish a session.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")

        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")

        now = time.time()
        # Fast in-memory user cache with 60s TTL to eliminate redundant auth queries
        if user_id in _USER_CACHE:
            cached_user, timestamp = _USER_CACHE[user_id]
            if now - timestamp < 60:
                try:
                    return db.merge(cached_user, load=False)
                except Exception:
                    pass

        user = db.query(models.User).filter(models.User.id == user_id).first()
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        _USER_CACHE[user_id] = (user, now)
        return user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
    detail_msg = "An unexpected server error occurred." if is_prod else str(exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "success": False,
            "message": "Internal Server Error",
            "detail": detail_msg,
        },
    )


# ==========================================
# AUTHENTICATION & CORE ENDPOINTS
# ==========================================

@app.get("/api/health")
def api_health():
    return {"message": "ExpiryGuard Backend Running"}

@app.get("/robots.txt")
def robots_txt():
    from fastapi.responses import FileResponse
    robots_path = PUBLIC_SITE_DIR / "robots.txt"
    if robots_path.exists():
        return FileResponse(robots_path)
    raise HTTPException(status_code=404)

@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    from fastapi.responses import FileResponse
    fav_path = PUBLIC_SITE_DIR / "favicon.svg"
    if fav_path.exists():
        return FileResponse(fav_path)
    raise HTTPException(status_code=404)

@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    if not request.url.path.startswith("/api"):
        from fastapi.responses import FileResponse
        custom_404_page = PUBLIC_SITE_DIR / "404.html"
        if custom_404_page.exists():
            return FileResponse(custom_404_page, status_code=404)
    return JSONResponse(
        status_code=404,
        content={"detail": exc.detail}
    )

@app.get("/")
def home():
    """Serve ExpiryGuard Public SaaS Landing Page"""
    from fastapi.responses import FileResponse
    landing_index = PUBLIC_SITE_DIR / "index.html"
    if landing_index.exists():
        return FileResponse(landing_index)
    return {"message": "ExpiryGuard Backend Running"}


@app.post("/register")
@limiter.limit("60/minute")
def register(
    request: Request,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    existing = db.query(models.User).filter(models.User.email.ilike(user.email.strip())).first()
    if existing:
        return {"message": "Email already registered"}

    hashed_password = pwd_context.hash(user.password)
    new_user = models.User(
        shop_name=user.shop_name,
        owner_name=user.owner_name,
        email=user.email.strip().lower(),
        password=hashed_password,
    )

    db.add(new_user)
    db.commit()

    return {"message": "User registered successfully"}


from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordRequestForm

@app.post("/login")
@limiter.limit("60/minute")
def login(
    request: Request,
    response: Response,
    user: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    db_user = db.query(models.User).filter(models.User.email.ilike(user.email.strip())).first()

    if not db_user or not pwd_context.verify(user.password, db_user.password):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(
        {"user_id": db_user.id, "exp": expire_time},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    # Set secure HttpOnly session cookie for web browser clients
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
    }


@app.post("/logout")
def logout(response: Response):
    """Clears authentication session cookie."""
    response.delete_cookie(key="access_token")
    return {"message": "Logged out successfully"}


@app.get("/auth/session")
def get_or_create_browser_session(
    response: Response,
    db: Session = Depends(get_db),
):
    """Provides a valid session token for browser dashboard clients."""
    is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if is_prod:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Session auto-login is disabled in the production environment."
        )

    shop = db.query(models.User).order_by(models.User.id.asc()).first()
    if not shop:
        raise HTTPException(status_code=404, detail="No active shop found in system.")

    expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(
        {"user_id": shop.id, "exp": expire_time},
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
        "user_id": shop.id,
        "shop_name": shop.shop_name or "ExpiryGuard Pharmacy",
        "email": shop.email,
    }


@app.post("/token")
def login_token_alias(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    db_user = db.query(models.User).filter(models.User.email.ilike(form_data.username.strip())).first()
    if not db_user or not pwd_context.verify(form_data.password, db_user.password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")

    expire_time = datetime.utcnow() + timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS)
    token = jwt.encode(
        {"user_id": db_user.id, "exp": expire_time},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    return {"access_token": token, "token_type": "bearer"}


# ==========================================
# PRODUCT & INVENTORY ENDPOINTS
# ==========================================

@app.post("/products")
def create_product(
    product: schemas.ProductCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.create_product(db, product, current_user.id)


@app.get("/products")
@app.get("/inventory")
def read_products(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.get_products(db, current_user.id)


@app.put("/products/{product_id}")
def update_product(
    product_id: int,
    product: schemas.ProductCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return crud.update_product(db, product_id, product, current_user.id)


@app.put("/products/{product_id}/quantity")
def update_quantity(
    product_id: int,
    quantity: int,
    current_user: models.User = Depends(get_current_user),
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
    current_user: models.User = Depends(get_current_user),
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

@app.post("/sales", response_model=schemas.SaleResponse, status_code=201)
def complete_sale(
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mobile Counter 1-Tap Checkout Endpoint"""
    t0 = time.perf_counter()
    sale = crud.create_sale_transaction(
        db=db,
        sale_data=sale_data,
        user_id=current_user.id,
        current_user=current_user,
    )
    t1 = time.perf_counter()
    print(f"[SERVER TIMING] crud.create_sale_transaction: {(t1 - t0)*1000:.2f}ms")
    
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
    t2 = time.perf_counter()
    print(f"[SERVER TIMING] Total handler before return: {(t2 - t0)*1000:.2f}ms")
    return sale


@app.post(
    "/billing/confirm",
    response_model=schemas.SaleResponse,
    status_code=201,
)
def confirm_billing_sale(
    sale_data: schemas.SaleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Cart -> /billing/confirm locks bill, deducts stock, and returns invoice summary with PDF link."""
    sale = crud.create_sale_transaction(
        db=db,
        sale_data=sale_data,
        user_id=current_user.id,
        current_user=current_user,
    )
    
    tax_summary = []
    if sale.tax_summary_json:
        try:
            import json
            tax_summary = json.loads(sale.tax_summary_json)
        except Exception:
            tax_summary = []
            
    sale.tax_summary = tax_summary
    sale.pdf_url = f"/billing/{sale.id}/pdf"
    return sale


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
    return crud.create_sale_return(
        db=db,
        sale_id=sale_id,
        return_data=return_data,
        user_id=current_user.id,
    )


@app.get(
    "/returns/today",
    response_model=List[schemas.SaleReturnResponse],
)
def get_todays_returns(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    returns = crud.get_todays_returns(
        db=db,
        user_id=current_user.id,
    )
    for r in returns:
        if not getattr(r, 'bill_number', None) and r.sale:
            r.bill_number = r.sale.bill_number
    return returns
@app.get("/sales", response_model=List[schemas.SaleResponse])
def get_sales_history(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Fetch sales logs for review & desktop view"""
    return (
        db.query(models.Sale)
        .filter(models.Sale.user_id == current_user.id)
        .order_by(models.Sale.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


@app.put("/sales/{sale_id}", response_model=schemas.SaleResponse)
def update_sale_desktop(
    sale_id: int,
    update_data: schemas.SaleUpdateDesktop,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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
    current_user: models.User = Depends(get_current_user),
):
    """Fetches full profile, pharmacy information & settings for logged-in user."""
    return current_user


@app.put("/user/profile", response_model=schemas.User)
def update_user_profile(
    data: schemas.UserProfileUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Updates pharmacy details, preferences, theme, language, and notification settings."""
    return crud.update_user_profile(db=db, user_id=current_user.id, data=data)


@app.post("/user/change-password")
def change_password(
    req: schemas.PasswordChangeRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Secured endpoint to change account password."""
    return crud.change_user_password(db=db, user_id=current_user.id, req=req)


@app.delete("/sales/{sale_id}")
def delete_bill(
    sale_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Deletes a sale bill and restores item stock to active inventory."""
    return crud.delete_sale_bill(db=db, sale_id=sale_id, user_id=current_user.id)


# ---------------- DATA EXPORT ENDPOINTS ---------------- #

@app.get("/reports/export/sales")
def export_sales_csv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Exports all sales transactions & bills to CSV format."""
    import csv
    import io

    sales = db.query(models.Sale).filter(models.Sale.user_id == current_user.id).order_by(models.Sale.created_at.desc()).all()
    
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
    
    output.seek(0)
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=expiryguard_sales_export.csv"})


@app.get("/reports/export/inventory")
def export_inventory_csv(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=expiryguard_inventory_export.csv"})


# ---------------- RESTOCK SUGGESTIONS ENDPOINTS ---------------- #

@app.get("/inventory/restock-suggestions", response_model=schemas.RestockSuggestionsResponse)
@app.get("/restock/suggestions", response_model=schemas.RestockSuggestionsResponse)
def get_inventory_restock_suggestions(
    reason_filter: Optional[str] = None,
    sort_by: Optional[str] = "demand",
    search: Optional[str] = None,
    multiplier: Optional[float] = 3.0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Intelligent demand-aware restock recommendations list:
    Computes Out of Stock, Expired, and Low Stock relative to 30-day sales velocity.
    """
    return crud.get_restock_suggestions(
        db=db,
        user_id=current_user.id,
        multiplier=multiplier or 3.0,
        reason_filter=reason_filter,
        sort_by=sort_by or "demand",
        search=search,
    )


@app.get("/inventory/restock-suggestions/export-csv")
def export_restock_suggestions_csv(
    reason_filter: Optional[str] = None,
    sort_by: Optional[str] = "demand",
    search: Optional[str] = None,
    multiplier: Optional[float] = 3.0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Exports demand-calculated restock purchase suggestions as CSV."""
    import csv
    import io

    res = crud.get_restock_suggestions(
        db=db,
        user_id=current_user.id,
        multiplier=multiplier or 3.0,
        reason_filter=reason_filter,
        sort_by=sort_by or "demand",
        search=search,
    )
    items = res.get("suggestions", [])

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Medicine Name",
        "Brand / Manufacturer",
        "Salt / Composition",
        "Reason / Status",
        "Urgency Level",
        "Sellable Stock (Packs)",
        "Expired Stock (Packs)",
        "30-Day Sales",
        "Avg Weekly Sales",
        "Days of Stock Left",
        "Suggested Reorder Qty (Packs)",
        "Estimated Pack MRP (INR)",
        "Estimated Reorder Cost (INR)"
    ])

    for it in items:
        days_str = f"{it['days_of_stock_remaining']} days" if it.get("days_of_stock_remaining") is not None else "N/A (No Recent Sales)"
        if it.get("sellable_stock") == 0:
            days_str = "0 days (Stockout)"

        writer.writerow([
            it.get("product_name"),
            it.get("brand") or "Generic",
            it.get("composition") or "",
            it.get("reason_label") or it.get("reason"),
            it.get("urgency_level") or "Normal",
            it.get("sellable_stock", 0),
            it.get("expired_stock", 0),
            it.get("sales_30d", 0.0),
            it.get("avg_weekly_sales", 0.0),
            days_str,
            it.get("suggested_reorder_qty", 10),
            f"{it.get('unit_price', 0.0):.2f}",
            f"{it.get('estimated_reorder_cost', 0.0):.2f}"
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=expiryguard_restock_suggestions.csv"}
    )


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
        "Content-Disposition": 'attachment; filename="ExpiryGuard_Inventory_Import_Template.xlsx"',
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
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Directly uploads and parses an .xlsx, .xls, or .csv inventory spreadsheet (no Gemini AI required),
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
    )


# ---------------- SUPPLIER ENDPOINTS ---------------- #

@app.post("/suppliers", response_model=schemas.SupplierResponse, status_code=201)
def create_supplier(
    data: schemas.SupplierCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a new pharmacy supplier record."""
    return crud.create_supplier(db=db, user_id=current_user.id, supplier_data=data)


@app.get("/suppliers", response_model=List[schemas.SupplierResponse])
def list_suppliers(
    query: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List suppliers with search, status filter, purchase metrics."""
    return crud.get_suppliers(db=db, user_id=current_user.id, query=query, status=status)


@app.get("/suppliers/{supplier_id}", response_model=schemas.SupplierResponse)
def get_supplier_detail(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get single supplier detail."""
    return crud.get_supplier_detail(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.put("/suppliers/{supplier_id}", response_model=schemas.SupplierResponse)
def update_supplier(
    supplier_id: int,
    data: schemas.SupplierUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Update supplier profile details."""
    return crud.update_supplier(db=db, supplier_id=supplier_id, user_id=current_user.id, data=data)


@app.delete("/suppliers/{supplier_id}")
def delete_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Deactivate supplier record."""
    return crud.delete_supplier(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.get("/suppliers/{supplier_id}/purchases", response_model=List[schemas.DocumentResponse])
def get_supplier_purchases(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get purchase invoices associated with supplier."""
    return crud.get_supplier_purchases(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.get("/suppliers/{supplier_id}/inventory", response_model=List[schemas.Product])
def get_supplier_inventory(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return crud.get_supplier_inventory(db=db, supplier_id=supplier_id, user_id=current_user.id)


@app.post("/suppliers/{supplier_id}/payments", response_model=schemas.SupplierPaymentResponse, status_code=201)
def pay_supplier_invoice(
    supplier_id: int,
    payment: schemas.SupplierPaymentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log a payment made to wholesale distributor."""
    if payment.supplier_id != supplier_id:
        raise HTTPException(status_code=400, detail="Supplier ID mismatch.")
    return crud.create_supplier_payment(db=db, obj_in=payment, user_id=current_user.id)


@app.get("/suppliers/{supplier_id}/payments", response_model=List[schemas.SupplierPaymentResponse])
def get_supplier_payment_history(
    supplier_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get history of payments made to a wholesale distributor."""
    return crud.get_supplier_payments(db=db, supplier_id=supplier_id, user_id=current_user.id)


# ---------------- PURCHASES ENDPOINTS ---------------- #

@app.post("/purchases", response_model=schemas.PurchaseInvoiceResponse, status_code=201)
def create_purchase(
    invoice: schemas.PurchaseInvoiceCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Register a new itemized purchase invoice and update stock levels."""
    return crud.create_purchase_invoice(db=db, obj_in=invoice, user_id=current_user.id)


@app.get("/purchases", response_model=List[schemas.PurchaseInvoiceResponse])
def list_purchases(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Retrieve history of registered purchase invoices."""
    return crud.get_purchase_invoices(db=db, user_id=current_user.id, skip=skip, limit=limit)


@app.get("/purchases/{purchase_id}", response_model=schemas.PurchaseInvoiceResponse)
def get_purchase(
    purchase_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
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
    current_user: models.User = Depends(get_current_user),
):
    """Process return of products to wholesale supplier and decrement stock."""
    return crud.create_purchase_return(db=db, obj_in=ret_in, user_id=current_user.id)


@app.get("/purchases/returns", response_model=List[schemas.PurchaseReturnResponse])
def list_purchase_returns(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Retrieve history of registered purchase returns."""
    return crud.get_purchase_returns(db=db, user_id=current_user.id, skip=skip, limit=limit)


# ---------------- DOCUMENT ENDPOINTS ---------------- #

DOCUMENTS_DIR = BASE_DIR / "uploads" / "documents"
os.makedirs(DOCUMENTS_DIR, exist_ok=True)
app.mount("/uploads/documents", StaticFiles(directory=DOCUMENTS_DIR), name="documents_files")

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

    check_file_size(file)

    unique_name = f"doc_{uuid.uuid4().hex[:12]}{file_ext}"
    target_path = DOCUMENTS_DIR / unique_name

    with open(target_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_size = target_path.stat().st_size
    if file_size > MAX_FILE_SIZE:
        if target_path.exists():
            target_path.unlink()
        raise HTTPException(status_code=400, detail="File size must not exceed 10 MB.")

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


@app.post("/documents/{document_id}/ocr", response_model=schemas.DocumentResponse)
def trigger_document_ocr(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Trigger AI OCR scanning on uploaded invoice/document."""
    doc = crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)
    
    local_filename = Path(doc.file_path).name
    full_path = DOCUMENTS_DIR / local_filename

    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server.")

    print(f"[OCR:ENDPOINT] Triggering OCR for Document #{document_id} (Path: {full_path})")
    ocr_res = scan_invoice(str(full_path))

    if ocr_res.get("success"):
        data = ocr_res.get("data", {})
        doc.ocr_raw_json = json.dumps(data)
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

        # Link supplier if matching name exists
        if data.get("supplier_name") and not doc.supplier_id:
            s_name = data.get("supplier_name").strip()
            existing_s = db.query(models.Supplier).filter(
                models.Supplier.user_id == current_user.id,
                func.lower(models.Supplier.name) == s_name.lower()
            ).first()
            if existing_s:
                doc.supplier_id = existing_s.id
                print(f"[OCR:ENDPOINT] Auto-linked document #{document_id} to existing Supplier #{existing_s.id} ('{existing_s.name}')")

        print(f"[OCR:ENDPOINT] Document #{document_id} OCR completed: Inv #{doc.invoice_number}, Date: {doc.invoice_date}, Total: ₹{doc.total_amount}, Items: {doc.item_count}")
    else:
        doc.ocr_status = "Failed"
        error_msg = ocr_res.get("error", "Unknown OCR failure")
        doc.ocr_raw_json = json.dumps({"error": error_msg, "items": []})
        print(f"[OCR:ENDPOINT] Document #{document_id} OCR failed: {error_msg}")

    db.commit()
    db.refresh(doc)
    return doc


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
    """Get single document detail with OCR raw JSON."""
    return crud.get_document_detail(db=db, document_id=document_id, user_id=current_user.id)


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
def search_medicine_catalog(
    query: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Search the reference medicine_catalog (240k+ Indian medicines).
    Returns autocomplete suggestions (Name, Brand, Salt/Composition, HSN, Default Price, Pack Size).
    Used for pre-filling when purchasing/adding stock or billing.
    """
    search_str = (query or q or "").strip()
    return crud.search_medicine_catalog(db, query=search_str, limit=limit)


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
        db.query(models.Customer).filter(models.Customer.id == sale.customer_id).update(
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
    return crud.soft_delete_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )


@app.post("/inventory/delete-all")
@limiter.limit("60/minute")
def delete_all_inventory_stock(
    request: Request,
    payload: schemas.InventoryDeleteAllRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Bulk soft-delete for all active stock items belonging to the authenticated shop.
    Requires explicit confirmation flag in request body (confirm: true).
    """
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Explicit confirmation flag (confirm: true) is required to delete all stock."
        )

    return crud.soft_delete_all_inventory_items(
        db=db,
        user_id=current_user.id
    )


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
    return crud.restore_inventory_items(
        db=db,
        stock_ids=ids,
        user_id=current_user.id
    )


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


@app.get("/billing/search-products", response_model=List[schemas.Product])
def billing_search_products(
    query: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Searches shop inventory ranked by FEFO (earliest expiry first)."""
    clean_q = query.strip()
    if not clean_q:
        return []
    return (
        db.query(models.Product)
        .filter(
            models.Product.user_id == current_user.id,
            models.Product.is_deleted == False,
            models.Product.product_name.ilike(f"%{clean_q}%")
        )
        .order_by(models.Product.expiry_date.asc())
        .limit(20)
        .all()
    )


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

        if product.quantity < item.quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient stock for '{product.product_name}'. Stock: {product.quantity}, Requested: {item.quantity}"
            )

        product.quantity -= item.quantity
        line_total = product.unit_price * item.quantity
        calculated_subtotal += line_total

        sale_items.append(
            models.SaleItem(
                product_id=product.id,
                product_name=product.product_name,
                quantity=item.quantity,
                unit_price=product.unit_price,
                total_price=line_total,
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
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# AI, OCR & MEDIA UPLOAD ENDPOINTS
# ==========================================

@app.post("/upload-image")
def upload_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    """Secure image upload endpoint with authentication, MIME validation, and randomized filename."""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, PNG, and WEBP images are allowed.",
        )

    file_ext = Path(file.filename or "").suffix.lower()
    if file_ext not in ALLOWED_DOC_EXTENSIONS:
        file_ext = ".jpg"

    check_file_size(file)
    contents = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File size must not exceed 10 MB.")

    os.makedirs("uploads", exist_ok=True)
    safe_filename = f"img_{uuid.uuid4().hex[:16]}{file_ext}"
    file_path = os.path.join("uploads", safe_filename)

    with open(file_path, "wb") as buffer:
        buffer.write(contents)

    return {"imagePath": f"uploads/{safe_filename}"}


@app.post("/scan-label")
@limiter.limit("30/hour")
def scan_product_label(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, PNG and WEBP images are allowed.",
        )

    check_file_size(file)
    contents = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size must not exceed 10 MB.",
        )

    file.file.seek(0)
    os.makedirs("uploads", exist_ok=True)

    extension = os.path.splitext(file.filename)[1].lower()
    filename = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join("uploads", filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = scan_label(file_path)
        return {"success": True, "data": result}
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
def _normalise_product_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower()).strip()


def _clean_words(text: str) -> set:
    noise = {"tab", "tabs", "strip", "capsule", "syrup", "mg", "ml", "gm", "g", "tablets", "box", "pack"}
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {w for w in words if len(w) > 1 and w not in noise}

def _find_inventory_product(products, detected_name: str):
    if not detected_name or not detected_name.strip():
        return None

    det_raw = detected_name.strip().lower()
    det_norm = _normalise_product_name(detected_name)
    det_words = _clean_words(detected_name)

    if not det_norm:
        return None

    # 1. Exact raw & normalized match
    for product in products:
        p_raw = (product.product_name or "").strip().lower()
        if p_raw == det_raw or _normalise_product_name(product.product_name) == det_norm:
            return product

    # 2. Token overlap match (e.g. "Pudina Pani" matches "pudina pani")
    if det_words:
        best_token_prod = None
        max_overlap = 0
        for product in products:
            p_words = _clean_words(product.product_name or "")
            if not p_words:
                continue
            common = det_words.intersection(p_words)
            overlap_count = len(common)
            # If all words in detected name are found in inventory name
            if len(common) == len(det_words) and len(det_words) >= 1:
                return product
            if overlap_count > max_overlap:
                max_overlap = overlap_count
                best_token_prod = product
        if max_overlap >= 2:
            return best_token_prod

    # 3. Containment match
    for product in products:
        inv_norm = _normalise_product_name(product.product_name or "")
        if len(det_norm) >= 4 and (det_norm in inv_norm or inv_norm in det_norm):
            return product

    # 4. Fuzzy ratio match (threshold 0.65)
    best_product = None
    best_score = 0.0

    for product in products:
        inv_norm = _normalise_product_name(product.product_name or "")
        score = SequenceMatcher(None, det_norm, inv_norm).ratio()
        if score > best_score:
            best_score = score
            best_product = product

    if best_score >= 0.65:
        return best_product

    return None
@app.post(
    "/scan-multi-item",
    response_model=schemas.MultiScanResponse,
)
@limiter.limit("20/hour")
def scan_multi_item_endpoint(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, PNG and WEBP images are allowed.",
        )

    check_file_size(file)
    image_bytes = file.file.read()

    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size must not exceed 10 MB.",
        )

    extension = os.path.splitext(file.filename or ".jpg")[1].lower()

    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".jpg"

    os.makedirs("uploads", exist_ok=True)

    temporary_filename = f"{uuid.uuid4()}{extension}"
    temporary_path = os.path.join(
        "uploads",
        temporary_filename,
    )

    try:
        with open(temporary_path, "wb") as output_file:
            output_file.write(image_bytes)

        ai_result = scan_multi_item(temporary_path)

        if not ai_result.get("success"):
            raise HTTPException(
                status_code=502,
                detail=ai_result.get(
                    "error",
                    "Multi-item AI scan failed.",
                ),
            )

        detected_items = ai_result.get("items", [])

        inventory_products = (
            db.query(models.Product)
            .filter(
                models.Product.user_id == current_user.id
            )
            .all()
        )

        grouped_items = {}
        total_price = 0.0
        any_review_required = False

        for detected_item in detected_items:
            product_name = (
                detected_item.get("product_name") or ""
            ).strip()

            if not product_name:
                continue

            detected_quantity = max(
                int(detected_item.get("quantity") or 1),
                1,
            )

            matched_product = _find_inventory_product(
                inventory_products,
                product_name,
            )

            if matched_product is None:
                key = f"unknown:{_normalise_product_name(product_name)}"

                if key in grouped_items:
                    grouped_items[key]["quantity"] += detected_quantity
                else:
                    grouped_items[key] = {
                        "product_name": product_name,
                        "brand": detected_item.get("brand"),
                        "matched_inventory_id": None,
                        "price": None,
                        "quantity": detected_quantity,
                        "confidence": float(
                            detected_item.get("confidence") or 0
                        ),
                        "matched": False,
                        "needs_review": True,
                        "reason": (
                            "No matching product was found "
                            "in this shop's inventory."
                        ),
                    }

                any_review_required = True
                continue

            key = f"product:{matched_product.id}"
            inventory_price = float(
                matched_product.unit_price or 0
            )

            if key in grouped_items:
                grouped_items[key]["quantity"] += detected_quantity
            else:
                grouped_items[key] = {
                    "product_name": matched_product.product_name,
                    "brand": matched_product.brand,
                    "matched_inventory_id": matched_product.id,
                    "price": inventory_price,
                    "quantity": detected_quantity,
                    "confidence": float(
                        detected_item.get("confidence") or 0
                    ),
                    "matched": True,
                    "needs_review": (
                        bool(detected_item.get("needs_review"))
                        or inventory_price <= 0
                    ),
                    "reason": (
                        "Selling price is not configured."
                        if inventory_price <= 0
                        else None
                    ),
                }

            total_price += inventory_price * detected_quantity

            if (
                bool(detected_item.get("needs_review"))
                or inventory_price <= 0
            ):
                any_review_required = True

        response_items = list(grouped_items.values())

        any_review_required = (
            any_review_required
            or any(
                item["needs_review"]
                for item in response_items
            )
        )

        return {
            "success": True,
            "items": response_items,
            "total_price": round(total_price, 2),
            "needs_review": any_review_required,
            "error": None,
        }

    finally:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)

@app.post("/scan-invoice", response_model=schemas.InvoiceScanResponse)
@limiter.limit("20/hour")
def scan_supplier_invoice(
    request: Request,
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Only JPG, JPEG, PNG and WEBP images are allowed.",
        )

    check_file_size(file)
    contents = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File size must not exceed 10 MB.",
        )

    file.file.seek(0)
    os.makedirs("uploads", exist_ok=True)

    _, extension = os.path.splitext(file.filename or ".jpg")
    filename = f"{uuid.uuid4()}{extension}"
    file_path = os.path.join("uploads", filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = scan_invoice(file_path)
        return result
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


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
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    check_file_size(file)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        df = import_service.read_file_to_dataframe(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

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

    for idx, row in df.iterrows():
        row_num = idx + 1
        cleaned_data, warnings, error_reason = import_service.validate_and_normalize_row(
            row=row,
            mapping=payload.column_mapping,
            row_index=row_num
        )
        if error_reason:
            errors.append(schemas.ImportErrorItem(
                row=row_num,
                raw_data=row.fillna("").to_dict(),
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
async def single_step_inventory_import(
    file: UploadFile = File(...),
    on_duplicate: str = "skip",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    """
    Standalone single-step import endpoint for auto-upload & import without separate preview confirmation.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    check_file_size(file)
    content = await file.read()
    df = import_service.read_file_to_dataframe(content, file.filename)
    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    file_headers = list(df.columns)
    detected_mapping, _ = import_service.auto_detect_mapping(file_headers)

    cleaned_rows = []
    errors = []
    for idx, row in df.iterrows():
        row_num = idx + 1
        cleaned_data, warnings, error_reason = import_service.validate_and_normalize_row(
            row=row,
            mapping=detected_mapping,
            row_index=row_num
        )
        if error_reason:
            errors.append({"row": row_num, "raw_data": row.fillna("").to_dict(), "reason": error_reason})
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


# ==========================================
# CUSTOMER & PATIENT PROFILE ENDPOINTS
# ==========================================

@app.get("/customers/search", response_model=Optional[schemas.CustomerResponse])
def search_customer_by_phone(
    phone: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Search customer by phone number to retrieve saved fixed patient discount percentage.
    """
    return crud.get_customer_by_phone(db, phone=phone.strip(), user_id=current_user.id)


@app.post("/customers", response_model=schemas.CustomerResponse)
def create_or_update_customer(
    customer: schemas.CustomerCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create or update a customer profile with fixed patient discount percentage.
    """
    return crud.create_or_update_customer(db, customer_data=customer, user_id=current_user.id)


@app.get("/customers", response_model=List[schemas.CustomerResponse])
def get_customers(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get all registered customers for the current shop.
    """
    return crud.get_customers(db, user_id=current_user.id)


@app.post("/customers/{customer_id}/payments", response_model=schemas.CustomerPaymentResponse, status_code=201)
def collect_customer_payment(
    customer_id: int,
    payment: schemas.CustomerPaymentCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Log credit payment collection from customer (Khata settlement)."""
    if payment.customer_id != customer_id:
        raise HTTPException(status_code=400, detail="Customer ID mismatch.")
    return crud.create_customer_payment(db=db, obj_in=payment, user_id=current_user.id)


@app.get("/customers/{customer_id}/payments", response_model=List[schemas.CustomerPaymentResponse])
def get_customer_payment_history(
    customer_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get collection history of credit payments for a customer."""
    return crud.get_customer_payments(db=db, customer_id=customer_id, user_id=current_user.id)


@app.get("/customers/{customer_id}/ledger")
def get_customer_ledger_summary(
    customer_id: int,
    current_user: models.User = Depends(get_current_user),
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
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Feature 4: One-Tap Return processing.
    Restores returned items to inventory, records SaleReturn, and returns prorated refund summary.
    """
    return crud.process_sale_return(db, return_data=payload, user_id=current_user.id)


@app.get("/billing/returns/today", response_model=List[schemas.SaleReturnResponse])
def get_todays_returns_billing(
    current_user: models.User = Depends(get_current_user),
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

@app.get("/dashboard/summary")
def get_dashboard_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Web App Dashboard KPI Summary Endpoint.
    Returns real-time metrics: product count, today's sales count, today's revenue, expiring count, expired count.
    """
    user_id = current_user.id
    today_start = datetime.combine(datetime.utcnow().date(), datetime.min.time())

    # Products summary - query only necessary columns
    prod_rows = db.query(models.Product.quantity, models.Product.days_remaining).filter(models.Product.user_id == user_id, models.Product.is_deleted == False).all()
    total_products = len(prod_rows)
    low_stock_count = sum(1 for q, _ in prod_rows if (q or 0) <= 10)
    expiring_soon_count = sum(1 for _, d in prod_rows if d is not None and 0 < d <= 60)
    expired_count = sum(1 for _, d in prod_rows if d is not None and d <= 0)

    # Today's sales summary
    sales_agg = (
        db.query(
            func.count(models.Sale.id).label("count"),
            func.sum(models.Sale.total_amount).label("revenue")
        )
        .filter(
            models.Sale.user_id == user_id,
            models.Sale.created_at >= today_start,
        )
        .first()
    )
    today_sales_count = int(sales_agg.count or 0) if sales_agg else 0
    today_revenue = round(float(sales_agg.revenue or 0.0), 2) if sales_agg else 0.0

    # Today's returns summary
    today_returns = crud.get_todays_returns(db, user_id=user_id)
    today_returns_count = len(today_returns)
    today_returns_amount = round(sum(r.return_amount for r in today_returns), 2)

    # Pending sales summary
    pending_sales = (
        db.query(models.Sale)
        .filter(
            models.Sale.user_id == user_id,
            models.Sale.payment_status == "PENDING",
        )
        .order_by(models.Sale.created_at.desc())
        .limit(50)
        .all()
    )
    pending_payments_count = len(pending_sales)
    pending_payments_total = round(sum(s.total_amount for s in pending_sales), 2)
    pending_payments_list = [
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
        for s in pending_sales
    ]

    return {
        "shop_name": current_user.shop_name,
        "owner_name": current_user.owner_name,
        "total_products": total_products,
        "low_stock_count": low_stock_count,
        "expiring_soon_count": expiring_soon_count,
        "expired_count": expired_count,
        "today_sales_count": today_sales_count,
        "today_revenue": today_revenue,
        "today_returns_count": today_returns_count,
        "today_returns_amount": today_returns_amount,
        "pending_payments_count": pending_payments_count,
        "pending_payments_total": pending_payments_total,
        "pending_payments_list": pending_payments_list,
    }


@app.get("/reports/summary")
def get_reports_summary(
    current_user: models.User = Depends(get_current_user),
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

        # Dispatch immediate email alert to founder in background (non-blocking)
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
        background_tasks.add_task(send_pilot_lead_notification, lead_data=lead_dict)

        return new_lead
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Could not submit pilot request: {str(e)}")


@app.post("/test-notification")
@app.post("/api/test-notification")
@limiter.limit("2/minute")
def test_notification_endpoint(
    request: Request,
    recipient: Optional[str] = None,
    current_user: models.User = Depends(get_current_user),
):
    """
    Test endpoint to verify SMTP configuration and send a sample pilot lead alert email.
    Usage: POST /test-notification (or POST /test-notification?recipient=your_email@gmail.com)
    """
    is_prod = os.getenv("ENVIRONMENT", "development").lower() == "production"
    if is_prod:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test notification endpoint is disabled in the production environment."
        )

    result = send_test_email(test_recipient=recipient)
    if not result.get("success"):
        return JSONResponse(status_code=400, content=result)
    return result


# ==========================================
# STATIC FILE MOUNTING FOR WEB APP & PUBLIC SITE
# ==========================================

# Mount Pharmacist Web Dashboard
app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")

# Mount Public Landing Website Asset Directories (for root / access)
if (PUBLIC_SITE_DIR / "css").exists():
    app.mount("/css", StaticFiles(directory=PUBLIC_SITE_DIR / "css"), name="public_css")
if (PUBLIC_SITE_DIR / "js").exists():
    app.mount("/js", StaticFiles(directory=PUBLIC_SITE_DIR / "js"), name="public_js")
if (PUBLIC_SITE_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=PUBLIC_SITE_DIR / "assets"), name="public_assets")

# Mount Public Landing Website
app.mount("/site", StaticFiles(directory=PUBLIC_SITE_DIR, html=True), name="site")
app.mount("/public_site", StaticFiles(directory=PUBLIC_SITE_DIR, html=True), name="public_site")