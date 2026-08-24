from apscheduler.schedulers.background import BackgroundScheduler
from notification_service import send_expiry_notifications
from database import SessionLocal
import crud

scheduler = BackgroundScheduler()


def purge_expired_inventory_job():
    """Daily scheduled job to permanently purge soft-deleted items older than 60 days."""
    db = SessionLocal()
    try:
        purged = crud.purge_expired_soft_deleted_inventory(db)
        if purged > 0:
            print(f"[SCHEDULER] Purged {purged} soft-deleted inventory records older than 60 days.")
    except Exception as e:
        print(f"[SCHEDULER ERROR] Failed to purge 60-day old soft-deleted inventory: {e}")
    finally:
        db.close()


def start_scheduler():
    scheduler.add_job(
        send_expiry_notifications,
        trigger="interval",
        minutes=15,
        id="expiry_notifications",
        replace_existing=True,
    )

    scheduler.add_job(
        purge_expired_inventory_job,
        trigger="interval",
        hours=24,
        id="purge_soft_deleted_inventory_60d",
        replace_existing=True,
    )

    scheduler.start()

    print("[SCHEDULER] Notification & Soft-Delete Purge Scheduler Started")