"""
GST Filing Reminders and CA Connect Data Sharing Routes for DawaiFlow / ExpiryGuard.
Handles GSTR-1, GSTR-3B due date calculation, filing logs, and CA Connect export reports.
"""

from datetime import date
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from dependencies import (
    get_db,
    get_current_user,
    require_permission,
    AuthenticatedUser,
)
import models
import schemas
import crud
from services.gst_calculator import calculate_gst_due_dates

router = APIRouter(prefix="/api/gst", tags=["GST Filing & CA Connect"])


class GstSettingsRequest(BaseModel):
    gst_filing_type: str = Field(..., description="monthly or qrmp")
    state_category: Optional[str] = Field("X", description="X or Y")


class MarkFiledRequest(BaseModel):
    return_type: str = Field(..., description="GSTR-1, GSTR-3B, PMT-06")
    period: str = Field(..., description="e.g. 2026-08 or 2026-Q2")
    acknowledgement_no: Optional[str] = None
    notes: Optional[str] = None


@router.get("/status")
def get_gst_status(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns GST configuration, calculated due dates, urgency status, and next due return.
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
        filing_type=current_user.gst_filing_type,
        state_category=current_user.state_category or "X",
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


@router.put("/settings")
def update_gst_settings(
    req: GstSettingsRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Updates pharmacy GST filing frequency (monthly/qrmp) and state category (X/Y).
    """
    f_type = req.gst_filing_type.lower().strip()
    if f_type not in ["monthly", "qrmp"]:
        raise HTTPException(status_code=400, detail="Invalid filing type. Must be 'monthly' or 'qrmp'.")

    s_cat = (req.state_category or "X").upper().strip()
    if s_cat not in ["X", "Y"]:
        s_cat = "X"

    current_user.gst_filing_type = f_type
    current_user.state_category = s_cat
    db.commit()

    return {
        "success": True,
        "message": "GST filing settings updated successfully.",
        "gst_filing_type": current_user.gst_filing_type,
        "state_category": current_user.state_category,
    }


@router.post("/mark-filed")
def mark_return_filed(
    req: MarkFiledRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Logs filing completion for a specific return and period.
    """
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


@router.get("/history")
def get_filing_history(
    current_user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns list of past filing logs for the pharmacy.
    """
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
