"""
Gemini cost reporting (read-only) and phone usage ingestion.

GET  /admin/ai-usage  gated by the AI_USAGE_ADMIN_EMAILS environment variable (comma separated emails).
POST /ai/usage        authenticated phone events (numbers only; shop comes from the token, never the body).
"""
import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from dependencies import get_db, get_current_user, AuthenticatedUser, limiter
import models
from ai import usage_log

logger = logging.getLogger("expiryguard.routes.ai_usage")
router = APIRouter(tags=["AI Usage"])

INVOICE_FEATURES = ("invoice_read", "invoice_second_pass")


def _admin_emails() -> set:
    raw = os.getenv("AI_USAGE_ADMIN_EMAILS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _percentile(values: List[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile (same result as Postgres percentile_cont)."""
    if not values:
        return None
    v = sorted(values)
    k = (len(v) - 1) * pct
    lo = int(k)
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def build_summary(db: Session, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=days)
    rows = db.query(models.AiUsageLog).filter(models.AiUsageLog.created_at >= since).all()

    daily: Dict[tuple, dict] = {}
    monthly: Dict[tuple, dict] = defaultdict(lambda: {"calls": 0, "cost_inr": 0.0})
    feat_costs: Dict[str, List[float]] = defaultdict(list)
    feat_calls: Dict[str, int] = defaultdict(int)
    feat_cache: Dict[str, int] = defaultdict(int)
    bills: Dict[str, float] = defaultdict(float)
    unknown_cost = 0

    for r in rows:
        day = r.created_at.strftime("%Y-%m-%d")
        cost = r.cost_inr
        is_hit = r.outcome == "cache_hit"
        d = daily.setdefault((r.shop_id, day), {"shop_id": r.shop_id, "date": day, "calls": 0, "cache_hits": 0,
                                                 "input_tokens": 0, "output_tokens": 0, "cost_inr": 0.0})
        if is_hit:
            d["cache_hits"] += 1
            feat_cache[r.feature] += 1
            continue
        d["calls"] += 1
        d["input_tokens"] += r.prompt_tokens or 0
        d["output_tokens"] += (r.output_tokens or 0) + (r.thought_tokens or 0)
        d["cost_inr"] += cost or 0.0
        m = monthly[(r.shop_id, r.created_at.strftime("%Y-%m"))]
        m["calls"] += 1
        m["cost_inr"] += cost or 0.0
        feat_calls[r.feature] += 1
        if cost is None:
            unknown_cost += 1  # usage missing: skipped by averages
            continue
        feat_costs[r.feature].append(cost)
        if r.feature in INVOICE_FEATURES and r.bill_id:
            bills[r.bill_id] += cost

    def rnd(x):
        return None if x is None else round(x, 4)

    per_feature = []
    for f in sorted(feat_calls):
        c = feat_costs.get(f, [])
        per_feature.append({
            "feature": f, "calls": feat_calls[f], "cache_hits": feat_cache.get(f, 0),
            "calls_with_cost": len(c),
            "avg_inr_per_call": rnd(sum(c) / len(c)) if c else None,
            "p95_inr_per_call": rnd(_percentile(c, 0.95)),
            "total_inr": rnd(sum(c)),
        })
    qb = feat_costs.get("quick_batch", [])
    day_key = lambda kv: (str(kv[0][0]), kv[0][1])
    return {
        "window_days": days,
        "prices": {"input_usd_per_m": usage_log.PRICE_INPUT_USD_PER_M,
                   "output_usd_per_m": usage_log.PRICE_OUTPUT_USD_PER_M, "usd_inr": usage_log.USD_INR},
        "per_pharmacy_per_day": [dict(v, cost_inr=rnd(v["cost_inr"])) for _, v in sorted(daily.items(), key=day_key)],
        "per_pharmacy_per_month": [{"shop_id": k[0], "month": k[1], "calls": v["calls"], "cost_inr": rnd(v["cost_inr"])}
                                   for k, v in sorted(monthly.items(), key=day_key)],
        "per_feature": per_feature,
        "avg_inr_per_invoice_bill": rnd(sum(bills.values()) / len(bills)) if bills else None,
        "invoice_bills_counted": len(bills),
        "avg_inr_per_quick_batch_request": rnd(sum(qb) / len(qb)) if qb else None,
        "calls_without_usage_numbers": unknown_cost,
    }


@router.get("/admin/ai-usage")
def get_ai_usage(days: int = 30, db: Session = Depends(get_db),
                 current_user: AuthenticatedUser = Depends(get_current_user)):
    allowed = _admin_emails()
    email = (getattr(current_user, "email", None) or "").strip().lower()
    if not allowed or email not in allowed:
        raise HTTPException(status_code=403, detail="Not allowed.")
    return build_summary(db, max(1, min(int(days), 90)))


# ---------------------------------------------------------------------------------------------------------
# Phone events (Quick Batch calls Gemini from the phone, so only the phone knows its token counts)
# ---------------------------------------------------------------------------------------------------------
PHONE_ALLOWED_FEATURES = {"quick_batch"}
PHONE_MAX_EVENTS_PER_REQUEST = 50


class PhoneUsageEvent(BaseModel):
    event_id: str = Field(min_length=8, max_length=40, pattern=r"^[A-Za-z0-9_\-]+$")
    feature: str = Field(max_length=32)
    model: Optional[str] = Field(default=None, max_length=64)
    outcome: str = Field(max_length=16)
    prompt_tokens: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    output_tokens: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    thought_tokens: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    total_tokens: Optional[int] = Field(default=None, ge=0, le=10_000_000)
    strips: Optional[int] = Field(default=None, ge=0, le=1000)
    latency_ms: Optional[int] = Field(default=None, ge=0, le=3_600_000)


class PhoneUsageBatch(BaseModel):
    events: List[PhoneUsageEvent]


@router.post("/ai/usage")
@limiter.limit("30/minute")
def post_phone_usage(request: Request, payload: PhoneUsageBatch,
                     current_user: AuthenticatedUser = Depends(get_current_user)):
    """Records number-only phone events. Shop comes from the token; cost is computed here, never trusted."""
    if len(payload.events) > PHONE_MAX_EVENTS_PER_REQUEST:
        raise HTTPException(status_code=413, detail="Too many events.")
    accepted = 0
    for ev in payload.events:
        if ev.feature not in PHONE_ALLOWED_FEATURES or ev.outcome not in ("success", "error", "timeout"):
            continue
        usage_log.record(
            feature=ev.feature, outcome=ev.outcome, shop_id=current_user.id, model=ev.model, source="phone",
            usage={"prompt_tokens": ev.prompt_tokens, "output_tokens": ev.output_tokens,
                   "thought_tokens": ev.thought_tokens, "total_tokens": ev.total_tokens},
            strips=ev.strips, latency_ms=ev.latency_ms, event_id=ev.event_id,
        )
        accepted += 1
    return {"accepted": accepted}
