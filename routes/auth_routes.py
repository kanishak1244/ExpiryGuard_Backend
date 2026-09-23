"""
Authentication & Session Management Routes for DawaiFlow / ExpiryGuard.
Handles user registration, login, JWT token issuance, password reset, session verification, and app bootstrap preloading.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from dependencies import (
    get_db,
    get_current_user,
    AuthenticatedUser,
    limiter,
    fast_cache,
    safe_hash_password,
    safe_verify_password,
    SECRET_KEY,
    ALGORITHM,
    ACCESS_TOKEN_EXPIRE_DAYS,
)
import models
import schemas
import crud
import permissions
from jose import jwt

logger = logging.getLogger("expiryguard.routes.auth")

router = APIRouter(tags=["Authentication & Session"])


@router.post("/register")
@limiter.limit("10/minute")
def register_user(
    request: Request,
    user: schemas.UserCreate,
    db: Session = Depends(get_db),
):
    """Register a new pharmacy account."""
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


@router.post("/auth/reset-password")
@limiter.limit("10/minute")
def reset_password(
    request: Request,
    data: schemas.PasswordResetRequest,
    db: Session = Depends(get_db),
):
    """Reset account password by email."""
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
        db.rollback()
        logger.error(f"[Password Reset Error] {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Reset error: {str(e)}")


@router.post("/login")
@limiter.limit("10/minute")
def login(
    request: Request,
    response: Response,
    user: schemas.UserLogin,
    db: Session = Depends(get_db),
):
    """Authenticate pharmacy owner or staff member and issue JWT session token."""
    login_identifier = user.email.strip()

    # 1. Attempt Pharmacy Owner login by email
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


@router.get("/auth/session")
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


@router.get("/app/bootstrap")
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


@router.post("/token")
@limiter.limit("10/minute")
def login_token_alias(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 password form login alias endpoint."""
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


@router.post("/auth/logout")
@router.post("/logout")
def logout(
    response: Response,
    current_user: AuthenticatedUser = Depends(get_current_user),
):
    """Backend logout and session cookie clearing endpoint."""
    response.delete_cookie(key="access_token", path="/", httponly=True)
    if current_user:
        cache_key = f"u:{current_user.id}:s:{current_user.staff_id or 'none'}"
        fast_cache.invalidate_user(current_user.id)
    return {"message": "Logged out successfully"}
