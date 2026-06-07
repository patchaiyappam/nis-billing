"""
NEW INDIAN STEEL - Billing & Credit Management System
=====================================================
Entry point. Initializes logging, runs startup backup,
initializes the database, and launches the Tkinter UI.

Run this file to start the application:
    python main.py
"""
import sys
import os

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from logger import get_logger
from config import AUTO_BACKUP_ENABLED
from database import init_database, init_background_tasks_table
from backup_manager import auto_backup_on_startup, cleanup_old_backups
from migrations import run_migrations

log = get_logger("main")


def main():
    log.info("=" * 50)
    log.info("  NEW INDIAN STEEL - Billing System  STARTING")
    log.info("=" * 50)

    # ── Startup backup ────────────────────────────────
    if AUTO_BACKUP_ENABLED:
        try:
            auto_backup_on_startup()
            cleanup_old_backups(keep_days=30)
        except Exception as e:
            log.error("Startup backup failed: %s", e, exc_info=True)

    # ── Database init ─────────────────────────────────
    log.info("Initializing database...")
    try:
        init_database()
        log.info("Database ready.")
    except Exception as e:
        log.critical("Database initialization failed: %s", e, exc_info=True)
        sys.exit(1)

    # ── Schema migrations ─────────────────────────────────
    log.info("Running database migrations...")
    try:
        run_migrations()
    except Exception as e:
        log.error("Migration error (non-fatal): %s", e, exc_info=True)

    # ── Background tasks table ────────────────────────────
    try:
        init_background_tasks_table()
        log.info("Background tasks table ready.")
    except Exception as e:
        log.error("Background tasks init failed (non-fatal): %s", e, exc_info=True)

    # ── Start background task worker ─────────────────────
    try:
        from task_queue import start_task_worker
        start_task_worker()
        log.info("Background task worker started.")
    except Exception as e:
        log.error("Task worker start failed (non-fatal): %s", e, exc_info=True)

    # ── Start Supabase auto-sync ──────────────────────────
    try:
        from supabase_sync import start_auto_sync
        start_auto_sync()
        log.info("Supabase auto-sync started.")
    except Exception as e:
        log.info("Supabase auto-sync not started (offline or not configured): %s", e)

    # ── Push local changes FIRST, then start pull worker ────
    # This ensures any edits made locally (even after a crash) are
    # pushed to cloud BEFORE the pull can overwrite them.
    try:
        from supabase_sync import sync_all as _push_all, is_online as _online
        if _online():
            import threading
            threading.Thread(target=_push_all, daemon=True).start()
            log.info("Startup push launched.")
    except Exception as e:
        log.info("Startup push skipped: %s", e)

    # ── Start cloud pull worker (two-way sync) ───────────
    # Pulls changes made on the other PC every 15s and downloads any
    # new PDFs from Storage. Safe to fail — app still works offline.
    # Delay first pull by 10s to let the startup push complete first.
    try:
        from cloud_pull import start_pull_worker
        start_pull_worker(initial_delay=10)
        log.info("Cloud pull worker started.")
    except Exception as e:
        log.info("Cloud pull worker not started: %s", e)

    # ── Launch UI — shop mode or admin mode ──────────────
    log.info("Starting application...")
    try:
        from config import USER_MODE
        if USER_MODE == "admin":
            log.info("Launching ADMIN mode (full access).")
            from ui.app import BillingApp
            app = BillingApp()
        else:
            log.info("Launching SHOP mode (dad / simple UI).")
            from ui.shop_app import ShopApp
            app = ShopApp()
        app.mainloop()
    except Exception as e:
        log.critical("Application crashed: %s", e, exc_info=True)
        raise
    finally:
        log.info("Application closed.")


if __name__ == "__main__":
    main()
