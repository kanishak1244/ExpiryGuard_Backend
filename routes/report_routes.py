"""
Analytics, Reports, and Data Export Routes for DawaiFlow / ExpiryGuard.
Handles profit & loss analytics, tax reports, sales/purchase metrics, and CSV exports.
"""

import logging
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
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

logger = logging.getLogger("expiryguard.routes.reports")

router = APIRouter(tags=["Analytics & Reports"])


@router.get("/reports/analytics")
def get_reports_analytics(
    period: Optional[str] = "this_month",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: AuthenticatedUser = Depends(require_permission(permissions.PERM_REPORT_VIEW)),
    db: Session = Depends(get_db),
):
    """Returns comprehensive report analytics (Sales, COGS, Gross Profit, Top Selling, Valuation, Expiry Risk, Trends)."""
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
