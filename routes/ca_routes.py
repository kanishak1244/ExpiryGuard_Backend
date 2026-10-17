"""
CA Connect & Chartered Accountant Compliance Routes for DawaiFlow.
Handles CA profile management, GST financial summaries, report sharing, and audit logging.
"""

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

router = APIRouter(tags=["CA Connect & Compliance Hub"])


@router.get("/ca/profile")
@router.get("/ca-connect/profile")
def get_ca_profile_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns configured Chartered Accountant profile details for the pharmacy.
    """
    prof = crud.get_ca_profile(db, current_user.id)
    return prof or {}


@router.post("/ca-connect/profile")
def save_ca_profile_endpoint(
    req: schemas.CaProfileCreate,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """
    Creates or updates Chartered Accountant contact details.
    """
    res = crud.save_ca_profile(
        db=db,
        user_id=current_user.id,
        ca_email=req.ca_email,
        ca_name=req.ca_name,
        ca_phone=req.ca_phone
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@router.delete("/ca-connect/profile")
def delete_ca_profile_endpoint(
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_SETTINGS_EDIT)),
    db: Session = Depends(get_db),
):
    """
    Disconnects Chartered Accountant contact details.
    """
    success = crud.delete_ca_profile(db, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="No CA profile configured to delete.")
    fast_cache.invalidate_user(current_user.id)
    return {"success": True, "message": "CA profile disconnected successfully."}


@router.get("/ca/share-history")
@router.get("/ca-connect/history")
def get_ca_share_history_endpoint(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Returns audit log of all report dispatches to the Chartered Accountant.
    """
    return crud.get_ca_share_history(db, current_user.id, limit=limit)


@router.post("/ca-connect/share")
@limiter.limit("20/hour")
def share_reports_with_ca_endpoint(
    request: Request,
    req: schemas.CaShareRequest,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Compiles and emails selected financial & GST reports to the Chartered Accountant.
    """
    res = crud.share_reports_with_ca(
        db=db,
        user_id=current_user.id,
        reports=req.reports,
        preset=req.date_range_preset or "this_month",
        start_date=req.start_date,
        end_date=req.end_date,
        target_ca_email=req.ca_email,
        custom_message=req.custom_message
    )
    fast_cache.invalidate_user(current_user.id)
    return res


@router.get("/ca/financial-summary")
@router.get("/reports/gst-financial-summary")
def get_gst_financial_summary_endpoint(
    preset: Optional[str] = Query(default="current_month"),
    start_date: Optional[str] = Query(default=None),
    end_date: Optional[str] = Query(default=None),
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """
    Calculates sales, purchases, output GST, input GST, net payable, and HSN tax summary.
    """
    return crud.get_gst_financial_summary(
        db=db,
        user_id=current_user.id,
        preset=preset or "current_month",
        start_date_str=start_date,
        end_date_str=end_date
    )


@router.get("/ca-connect/gmail/status")
def get_gmail_status_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns OAuth connection status for direct Gmail dispatch.
    """
    oauth = db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.id).first()
    if oauth and oauth.google_email:
        return {
            "connected": True,
            "google_email": oauth.google_email,
            "connected_at": oauth.created_at.isoformat() if oauth.created_at else None
        }
    return {
        "connected": False,
        "google_email": None
    }


@router.delete("/ca-connect/gmail/disconnect")
def disconnect_gmail_endpoint(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Disconnects Gmail OAuth token for CA dispatch.
    """
    db.query(models.UserGoogleOAuth).filter(models.UserGoogleOAuth.user_id == current_user.id).delete()
    db.commit()
    return {"success": True, "message": "Gmail account disconnected."}
