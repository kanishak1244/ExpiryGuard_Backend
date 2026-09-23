"""
User Profile and Shop Configuration Settings Routes for DawaiFlow / ExpiryGuard.
Handles pharmacy profile updates, invoice customization defaults, and push notification toggles.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from dependencies import (
    get_db,
    get_current_user,
    require_permission,
    AuthenticatedUser,
    fast_cache,
    limiter,
)
import models
import schemas
import crud

logger = logging.getLogger("expiryguard.routes.settings")

router = APIRouter(tags=["Profile & Settings"])


@router.get("/users/me")
@router.get("/settings")
def get_user_profile(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve active pharmacy owner profile and shop settings."""
    user = db.query(models.User).filter(models.User.id == current_user.id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.put("/users/me")
@router.put("/settings")
def update_user_profile(
    settings_data: schemas.UserSettingsUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("SETTINGS_EDIT")),
    db: Session = Depends(get_db),
):
    """Update pharmacy profile, drug license number, logo, and invoice printing settings."""
    updated = crud.update_user_settings(db, current_user.id, settings_data)
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.get("/notification-settings")
def get_notification_settings(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get push notification preference settings."""
    return crud.get_notification_settings(db, current_user.id)


@router.put("/notification-settings")
def update_notification_settings(
    data: schemas.NotificationSettingsCreate,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update push notification preference settings."""
    crud.update_notification_settings(db, current_user.id, data)
    return {"message": "Notification preferences updated"}


@router.post("/fcm-token")
def register_fcm_token(
    data: dict,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register mobile device FCM push token."""
    token = data.get("fcm_token") or data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="fcm_token is required")
    crud.register_fcm_token(db, current_user.id, token)
    return {"message": "FCM token registered"}
