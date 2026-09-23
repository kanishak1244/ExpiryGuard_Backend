"""
Multi-User Staff RBAC and Team Management Routes for DawaiFlow / ExpiryGuard.
Handles staff directory CRUD, role assignment, custom permission overrides, and staff login.
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
import permissions

logger = logging.getLogger("expiryguard.routes.staff")

router = APIRouter(tags=["Multi-User Staff & RBAC"])


@router.get("/staff")
def get_staff_members(
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_VIEW")),
    db: Session = Depends(get_db),
):
    """Retrieve list of staff members for the pharmacy."""
    return crud.get_staff_members(db, current_user.id)


@router.post("/staff")
def create_staff_member(
    staff_data: schemas.StaffMemberCreate,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Register a new staff member with assigned role and permissions."""
    created = crud.create_staff_member(db, staff_data, current_user.id)
    fast_cache.invalidate_user(current_user.id)
    return created


@router.get("/staff/{staff_id}")
def get_staff_member(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_VIEW")),
    db: Session = Depends(get_db),
):
    """Get details for a single staff member."""
    staff = crud.get_staff_member_by_id(db, staff_id, current_user.id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return staff


@router.put("/staff/{staff_id}")
def update_staff_member(
    staff_id: int,
    staff_data: schemas.StaffMemberUpdate,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Update staff member role, status, credentials, or permissions."""
    updated = crud.update_staff_member(db, staff_id, staff_data, current_user.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Staff member not found")
    fast_cache.invalidate_user(current_user.id)
    return updated


@router.delete("/staff/{staff_id}")
def delete_staff_member(
    staff_id: int,
    current_user: AuthenticatedUser = Depends(require_permission("STAFF_MANAGE")),
    db: Session = Depends(get_db),
):
    """Deactivate or remove staff member account."""
    success = crud.delete_staff_member(db, staff_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Staff member not found")
    fast_cache.invalidate_user(current_user.id)
    return {"message": "Staff member removed successfully"}
