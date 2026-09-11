print(">>> notification_service.py LOADED <<<")

# Override standard print locally for Windows encoding compatibility (prevent UnicodeEncodeError crashes)
_print = print
def print(*args, **kwargs):
    try:
        _print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [
            str(arg).encode('ascii', errors='replace').decode('ascii')
            for arg in args
        ]
        _print(*safe_args, **kwargs)
    except Exception:
        pass

from datetime import datetime
import traceback

from database import SessionLocal
import models

from firebase_admin import messaging


# ======================================
# Refresh Product Status
# ======================================
from datetime import datetime, date


def refresh_product(product):
    expiry = product.expiry_date

    # Handle both string and date objects
    if isinstance(expiry, str):
        try:
            expiry = datetime.strptime(expiry, "%Y-%m-%d").date()
        except ValueError:
            return

    elif isinstance(expiry, datetime):
        expiry = expiry.date()

    elif not isinstance(expiry, date):
        return

    today = datetime.now().date()

    days = (expiry - today).days

    product.days_remaining = days

    if days < 0:
        product.status = "Expired"
    elif days <= 30:
        product.status = "Expiring Soon"
    else:
        product.status = "Safe"
# ======================================
# Reminder Frequency Logic
# ======================================
def should_send_reminder(product, settings):

    today = datetime.now().date().isoformat()

    # Prevent multiple notifications on the same day
    if product.last_notification_date == today:
        return False

    frequency = (settings.reminder_frequency or "once").lower()

    # -----------------------------
    # Once
    # -----------------------------
    if frequency == "once":

        if product.notified_expiring:
            return False

        product.notified_expiring = True
        product.last_notification_date = today
        return True

    # -----------------------------
    # Daily
    # -----------------------------
    elif frequency == "daily":

        product.last_notification_date = today
        return True

    # -----------------------------
    # Every 2 Days
    # -----------------------------
    elif frequency == "every_2_days":

        if product.days_remaining >= 0 and product.days_remaining % 2 == 0:
            product.last_notification_date = today
            return True

        return False

    # -----------------------------
    # Weekly
    # -----------------------------
    elif frequency == "weekly":

        if product.days_remaining >= 0 and product.days_remaining % 7 == 0:
            product.last_notification_date = today
            return True

        return False

    return False
# ======================================
# Send Notifications
# ======================================
# ======================================
# EXPIRY REVIEW DIGEST ENGINE
# ======================================

from sqlalchemy.orm import joinedload

def calculate_expiry_digest_buckets(user_id: int, db, include_items: bool = True):
    """
    Calculates 5 dynamic non-overlapping expiry buckets for user inventory:
    1. expired: days <= 0
    2. 1m: 1 <= days <= 30
    3. 3m: 31 <= days <= 90
    4. 6m: 91 <= days <= 180
    5. 9m: 181 <= days <= 270
    Excludes products > 270 days (~9 months) and soft-deleted items.
    High performance: uses joinedload to eliminate N+1 SQL queries.
    """
    today = datetime.utcnow().date()
    
    if include_items:
        products = db.query(models.Product).options(
            joinedload(models.Product.supplier)
        ).filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False
        ).all()
    else:
        # Fast query for summary counts only (no joinedload needed)
        products = db.query(models.Product).filter(
            models.Product.user_id == user_id,
            models.Product.is_deleted == False
        ).all()

    buckets = {
        "expired": {"count": 0, "stock_value": 0.0, "items": []},
        "1m": {"count": 0, "stock_value": 0.0, "items": []},
        "3m": {"count": 0, "stock_value": 0.0, "items": []},
        "6m": {"count": 0, "stock_value": 0.0, "items": []},
        "9m": {"count": 0, "stock_value": 0.0, "items": []},
    }

    for p in products:
        if not p.expiry_date:
            continue

        exp_date = p.expiry_date
        if isinstance(exp_date, str):
            try:
                exp_date = datetime.strptime(exp_date, "%Y-%m-%d").date()
            except ValueError:
                continue

        days = (exp_date - today).days
        val = float(p.quantity * (p.purchase_price if p.purchase_price > 0 else p.unit_price))

        bucket_key = None
        if days <= 0:
            bucket_key = "expired"
        elif 1 <= days <= 30:
            bucket_key = "1m"
        elif 31 <= days <= 90:
            bucket_key = "3m"
        elif 91 <= days <= 180:
            bucket_key = "6m"
        elif 181 <= days <= 270:
            bucket_key = "9m"

        if bucket_key:
            buckets[bucket_key]["count"] += 1
            buckets[bucket_key]["stock_value"] += val
            if include_items:
                supplier_name = p.supplier.name if p.supplier else "N/A"
                buckets[bucket_key]["items"].append({
                    "id": p.id,
                    "product_name": p.product_name,
                    "batch_number": p.batch_number or "DEFAULT-B1",
                    "expiry_date": exp_date.strftime("%Y-%m-%d"),
                    "days_remaining": days,
                    "quantity": p.quantity,
                    "purchase_price": p.purchase_price,
                    "unit_price": p.unit_price,
                    "estimated_stock_value": round(val, 2),
                    "supplier_name": supplier_name,
                    "status": "EXPIRED" if days <= 0 else ("CRITICAL" if days <= 30 else "WARNING"),
                })

    total_at_risk_count = sum(b["count"] for b in buckets.values())
    total_at_risk_value = sum(b["stock_value"] for b in buckets.values())

    # Build concise FCM Notification Message
    title = "📋 Expiry Review Digest"
    lines = []
    if buckets["expired"]["count"] > 0:
        lines.append(f"🔴 {buckets['expired']['count']} expired")
    if buckets["1m"]["count"] > 0:
        lines.append(f"🟠 {buckets['1m']['count']} expiring within 1 month")
    if buckets["3m"]["count"] > 0:
        lines.append(f"🟡 {buckets['3m']['count']} expiring within 3 months")
    if buckets["6m"]["count"] > 0:
        lines.append(f"🟢 {buckets['6m']['count']} expiring within 6 months")
    if buckets["9m"]["count"] > 0:
        lines.append(f"🔵 {buckets['9m']['count']} expiring within 9 months")

    if lines:
        body = "Time for your medicine expiry review.\n" + "\n".join(lines) + "\nTap to review inventory in ExpiryGuard."
    else:
        body = "All inventory medicines are healthy. No items expiring within 9 months."

    return {
        "buckets": buckets,
        "total_at_risk_count": total_at_risk_count,
        "total_at_risk_value": round(total_at_risk_value, 2),
        "notification_title": title,
        "notification_body": body,
        "has_items": total_at_risk_count > 0,
    }


def send_expiry_digest_notifications(force_send: bool = False):
    """
    Sends twice-weekly Expiry Review Digest push notifications to registered users.
    Checks user's configured digest_days (e.g. Tuesday, Friday) and digest_time.
    """
    print("\n========== Expiry Review Digest Service ==========")
    db = SessionLocal()

    try:
        now = datetime.now()
        current_weekday = now.strftime("%A") # e.g. "Tuesday"
        users = db.query(models.User).all()

        for user in users:
            settings = db.query(models.NotificationSettings).filter(
                models.NotificationSettings.user_id == user.id
            ).first()

            if not settings:
                settings = models.NotificationSettings(
                    user_id=user.id,
                    digest_enabled=True,
                    digest_days="Tuesday,Friday",
                    digest_time="09:00"
                )
                db.add(settings)
                db.commit()
                db.refresh(settings)

            if not force_send:
                if not settings.enabled or not getattr(settings, 'digest_enabled', True):
                    print(f"Digest notifications disabled for user {user.id}")
                    continue

                allowed_days = [d.strip() for d in (settings.digest_days or "Tuesday,Friday").split(",")]
                if current_weekday not in allowed_days:
                    print(f"Today ({current_weekday}) is not in configured digest days {allowed_days} for user {user.id}")
                    continue

            digest_data = calculate_expiry_digest_buckets(user.id, db)
            if not digest_data["has_items"]:
                print(f"No expiring or expired products found for user {user.id}. Skipping digest push.")
                continue

            device = db.query(models.DeviceToken).filter(
                models.DeviceToken.user_id == user.id
            ).order_by(models.DeviceToken.id.desc()).first()

            if not device or not device.token:
                print(f"No FCM device token registered for user {user.id}")
                continue

            print(f"Sending Expiry Digest to user {user.id} ({device.token[:15]}...):")
            print(digest_data["notification_body"])

            message = messaging.Message(
                notification=messaging.Notification(
                    title=digest_data["notification_title"],
                    body=digest_data["notification_body"],
                ),
                data={
                    "click_action": "FLUTTER_NOTIFICATION_CLICK",
                    "screen": "SmartExpiry",
                    "module": "Smart Expiry",
                },
                token=device.token,
            )

            try:
                resp = messaging.send(message)
                print(f"✅ Expiry Digest Sent to user {user.id}! FCM ID: {resp}")
            except Exception as e:
                print(f"❌ FCM Error sending digest to user {user.id}: {e}")

    finally:
        db.close()


def send_expiry_notifications():
    """Backwards compatible alias calling send_expiry_digest_notifications()."""
    send_expiry_digest_notifications(force_send=False)