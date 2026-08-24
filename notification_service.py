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
from turtle import title

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
def send_expiry_notifications():
    print("\n========== Notification Service ==========")

    db = SessionLocal()

    try:
        products = db.query(models.Product).all()

        print(f"Found {len(products)} products")

        current = datetime.now()
        current_minutes = current.hour * 60 + current.minute

        for product in products:

            # Refresh status and remaining days
            refresh_product(product)

            print("--------------------------------")
            print("Product:", product.product_name)
            print("Days Remaining:", product.days_remaining)

            settings = (
                db.query(models.NotificationSettings)
                .filter(
                    models.NotificationSettings.user_id == product.user_id
                )
                .first()
            )
            print("Settings:", settings)

            if settings is None or not settings.enabled:
                continue

            # ----------------------------------
            # Notification Time (±5 min)
            # ----------------------------------
            try:
                hour, minute = map(
                    int,
                    settings.notification_time.split(":")
                )

                setting_minutes = hour * 60 + minute

                #if abs(current_minutes - setting_minutes) > 5:
                    #continue

            except Exception:
                continue

            device = (
                db.query(models.DeviceToken)
                .filter(models.DeviceToken.user_id == product.user_id)
                .order_by(models.DeviceToken.id.desc())
                .first()
            )
            print("Device:", device)

            if device is None:
                continue

            title = None
            body = None

            # ===============================
            # Expired Notification
            # ===============================
            if product.days_remaining < 0:

                if getattr(product, 'notified_expired', False):
                    continue

                title = "❌ Product Expired"
                body = (
                    f"{product.product_name} has expired."
                )

                if hasattr(product, 'notified_expired'):
                    product.notified_expired = True

            # ===============================
            # Reminder Notification
            # ===============================
            elif (
                product.days_remaining
                <= settings.notify_before_days
            ):

                if should_send_reminder(
                    product,
                    settings,
                ):

                    title = "⚠️ Product Expiring Soon"

                    body = (
                        f"{product.product_name} expires in "
                        f"{product.days_remaining} day(s)."
                    )

            print("Title:", title)

            if title is None:
                continue

            print("Sending to token:")
            print(device.token)
           
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                token=device.token,
            )

            try:
                response = messaging.send(message)

                print(
                    f"✅ Sent: {product.product_name}"
                )

                print(response)

            except Exception as e:
                print("========== FCM ERROR ==========")
                traceback.print_exc()
                print("===============================")

        db.commit()

    finally:
        db.close()