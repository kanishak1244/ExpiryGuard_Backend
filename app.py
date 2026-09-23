"""
DawaiFlow API - Production FastAPI Application Assembly Point.
Configures CORS, rate limiting, security headers, static asset mounts,
background database warmup, exception handling, and mounts all domain APIRouters.
"""

import os
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

from fastapi import FastAPI, Depends, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

# Internal Shared Context & Database
from dependencies import get_db, limiter, fast_cache
from database import engine, Base, SessionLocal
import models
import schemas
import crud
from scheduler import start_scheduler
from email_service import check_smtp_health

# Domain Routers
from routes import (
    auth_routes,
    product_routes,
    sale_routes,
    purchase_routes,
    customer_routes,
    ai_routes,
    report_routes,
    staff_routes,
    setting_routes,
    document_routes,
    gst_routes,
)

# Logging Setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("expiryguard")

# Base Directory Setup
BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
PUBLIC_SITE_DIR = BASE_DIR / "public_site"
PUBLIC_SITE_DIST = PUBLIC_SITE_DIR / "dist"
PUBLIC_SERVE_DIR = PUBLIC_SITE_DIST if (PUBLIC_SITE_DIST / "index.html").exists() else PUBLIC_SITE_DIR

os.makedirs(WEB_DIR, exist_ok=True)
os.makedirs(PUBLIC_SITE_DIR, exist_ok=True)
load_dotenv(dotenv_path=BASE_DIR / ".env")

# CORS Security Setup
is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"
default_origins = (
    "https://dawaiflow.com,https://app.dawaiflow.com,https://api.dawaiflow.com,https://expiryguard.com,https://app.expiryguard.com,https://api.expiryguard.com"
    if is_production
    else "http://localhost:8000,http://127.0.0.1:8000,http://localhost:3000,http://127.0.0.1:3000,http://localhost:5500,http://127.0.0.1:5500"
)
raw_origins = os.getenv("ALLOWED_ORIGINS", default_origins)
ALLOWED_ORIGINS = [o.strip().rstrip("/") for o in raw_origins.split(",") if o.strip()]
if "*" in ALLOWED_ORIGINS and len(ALLOWED_ORIGINS) > 1:
    ALLOWED_ORIGINS = [o for o in ALLOWED_ORIGINS if o != "*"]

# Initialize FastAPI App
app = FastAPI(
    title="DawaiFlow API",
    description="Production API for DawaiFlow AI Pharmacy Management System",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "Accept", "Origin", "X-Requested-With", "X-CSRF-Token"],
)


# Security Headers & CSRF Protection Middleware
@app.middleware("http")
async def add_security_headers_and_csrf_guard(request: Request, call_next):
    if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
        auth_header = request.headers.get("Authorization", "")
        has_cookie = "access_token" in request.cookies
        if has_cookie and not auth_header.startswith("Bearer "):
            origin = request.headers.get("origin") or request.headers.get("referer")
            if origin:
                from urllib.parse import urlparse
                parsed_origin = urlparse(origin.rstrip("/"))
                origin_host = f"{parsed_origin.scheme}://{parsed_origin.netloc}"
                if origin_host not in ALLOWED_ORIGINS:
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "CSRF origin check failed. State-changing request blocked."}
                    )

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response


# Application Startup Warmup
@app.on_event("startup")
def warmup_database():
    try:
        try:
            start_scheduler()
        except Exception as sched_err:
            logger.warning(f"[Startup] Scheduler start notice: {sched_err}")

        try:
            smtp_status = check_smtp_health(probe_network=False)
            if smtp_status.get("is_configured"):
                logger.info(f"[Startup] Email alert engine active for {smtp_status.get('recipient')}.")
        except Exception as smtp_err:
            logger.warning(f"[Startup] SMTP health check notice: {smtp_err}")

        def _background_warmup():
            try:
                Base.metadata.create_all(bind=engine)
                bg_db = SessionLocal()
                try:
                    active_user_ids = [r[0] for r in bg_db.query(models.User.id).limit(10).all()]
                    for uid in active_user_ids:
                        try:
                            crud.get_products(bg_db, user_id=uid)
                        except Exception:
                            pass
                    logger.info(f"[Startup] Background cache warming complete for {len(active_user_ids)} active users.")
                finally:
                    bg_db.close()
            except Exception as bg_err:
                logger.warning(f"[Startup] Background warming notice: {bg_err}")

        import threading
        threading.Thread(target=_background_warmup, daemon=True).start()
        logger.info("[Startup] Application server ready on port 8000.")
    except Exception as e:
        logger.warning(f"[Startup] DB warmup warning: {e}")


# Mount Static Files Directories
if PUBLIC_SITE_DIST.exists():
    app.mount("/assets", StaticFiles(directory=PUBLIC_SITE_DIST / "assets"), name="public_site_assets")

if WEB_DIR.exists():
    app.mount("/web", StaticFiles(directory=WEB_DIR, html=True), name="web")


# Register Domain APIRouters
app.include_router(auth_routes.router)
app.include_router(product_routes.router)
app.include_router(sale_routes.router)
app.include_router(purchase_routes.router)
app.include_router(customer_routes.router)
app.include_router(ai_routes.router)
app.include_router(report_routes.router)
app.include_router(staff_routes.router)
app.include_router(setting_routes.router)
app.include_router(document_routes.router)
app.include_router(gst_routes.router)


# Global Health & Static Route Handlers
@app.get("/health")
@app.get("/api/health")
def api_health():
    """Production Monitoring Health Endpoint."""
    db_connected = False
    try:
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
    robots_path = PUBLIC_SERVE_DIR / "robots.txt"
    if robots_path.exists():
        return FileResponse(robots_path)
    raise HTTPException(status_code=404)


@app.get("/favicon.ico")
@app.get("/favicon.svg")
def favicon():
    fav_path = PUBLIC_SERVE_DIR / "favicon.svg"
    if fav_path.exists():
        return FileResponse(fav_path)
    raise HTTPException(status_code=404)


@app.get("/")
def home():
    """Serve DawaiFlow Public Landing Page or SPA."""
    landing_index = PUBLIC_SERVE_DIR / "index.html"
    if landing_index.exists():
        return FileResponse(landing_index)
    return {"message": "DawaiFlow Backend API Running"}


@app.get("/terms")
@app.get("/terms.html")
def terms():
    return RedirectResponse(url="/#terms", status_code=302)


@app.get("/privacy")
@app.get("/privacy.html")
def privacy():
    return RedirectResponse(url="/#privacy", status_code=302)


@app.get("/data-policy")
@app.get("/data-policy.html")
def data_policy():
    return RedirectResponse(url="/#data-policy", status_code=302)


@app.get("/disclaimer")
@app.get("/medical-disclaimer")
def disclaimer():
    return RedirectResponse(url="/#disclaimer", status_code=302)


@app.get("/contact")
@app.get("/grievance")
@app.get("/support")
def contact():
    return RedirectResponse(url="/#contact", status_code=302)


@app.get("/sitemap.xml")
def sitemap_xml():
    sitemap_path = PUBLIC_SERVE_DIR / "sitemap.xml"
    if sitemap_path.exists():
        return FileResponse(sitemap_path, media_type="application/xml")
    raise HTTPException(status_code=404, detail="sitemap.xml not found")


# Global Exception Handlers
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc: HTTPException):
    accept = request.headers.get("accept", "").lower()
    is_html_request = "text/html" in accept
    is_api_path = any(request.url.path.startswith(prefix) for prefix in [
        "/api", "/billing", "/inventory", "/customers", "/sales", "/auth",
        "/analytics", "/printer", "/docs", "/redoc", "/openapi.json"
    ])
    if request.method == "GET" and is_html_request and not is_api_path:
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


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"[Unhandled Server Exception] {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."}
    )