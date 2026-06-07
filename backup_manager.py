"""
Backup & Restore Manager — NEW INDIAN STEEL Billing System
===========================================================
Handles automatic and manual database backups with timestamped
filenames, restore with confirmation, and cleanup of old backups.

Phase 3 additions:
- safe_restore_backup(): stops sync, creates safety backup, restores,
  then calls a restart callback — prevents restore while DB is active.
"""
import os
import shutil
import glob
import threading
from datetime import datetime, timedelta

from config import DB_PATH, BACKUPS_DIR
from logger import get_logger

log = get_logger(__name__)

# ── Restore guard: prevents concurrent restores ───────────
_restore_lock = threading.Lock()
_restore_in_progress = False


# ══════════════════════════════════════════════════════════
# BACKUP
# ══════════════════════════════════════════════════════════

def create_backup(tag="manual"):
    """
    Create a timestamped backup of the database.
    tag: descriptive label ('manual', 'startup', 'daily', 'shutdown', 'pre_restore')
    Returns the backup filepath on success, None on failure.
    """
    if not os.path.exists(DB_PATH):
        log.warning("Cannot backup — database file not found: %s", DB_PATH)
        return None

    os.makedirs(BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}_{tag}.db"
    dest = os.path.join(BACKUPS_DIR, filename)

    # Prevent overwrite (extremely unlikely with seconds precision)
    if os.path.exists(dest):
        log.warning("Backup file already exists, skipping: %s", dest)
        return dest

    try:
        shutil.copy2(DB_PATH, dest)
        size_kb = os.path.getsize(dest) / 1024
        log.info("Backup created: %s (%.1f KB)", filename, size_kb)
        return dest
    except Exception as e:
        log.error("Backup failed: %s", e, exc_info=True)
        return None


def auto_backup_on_startup():
    """
    Run a daily startup backup. Skips if a backup was already
    created today (any tag). Returns backup path or None.
    """
    today = datetime.now().strftime("%Y%m%d")
    existing = glob.glob(os.path.join(BACKUPS_DIR, f"backup_{today}_*.db"))
    if existing:
        log.info("Daily backup already exists for %s — skipping.", today)
        return existing[0]

    log.info("Creating daily startup backup...")
    return create_backup(tag="startup")


# ══════════════════════════════════════════════════════════
# RESTORE — Basic (used internally)
# ══════════════════════════════════════════════════════════

def restore_backup(backup_path):
    """
    Replace the current database with a backup file.
    Creates a safety backup of the current DB before restoring.
    Returns (success: bool, message: str).

    NOTE: Prefer safe_restore_backup() for UI-triggered restores.
    This function does NOT stop sync or check for active operations.
    """
    if not os.path.exists(backup_path):
        msg = f"Backup file not found: {backup_path}"
        log.error(msg)
        return False, msg

    # Safety: backup current DB before overwriting
    safety = create_backup(tag="pre_restore")
    if safety:
        log.info("Safety backup before restore: %s", safety)
    else:
        log.warning("Could not create safety backup before restore — proceeding anyway.")

    try:
        shutil.copy2(backup_path, DB_PATH)
        log.info("Database restored from: %s", os.path.basename(backup_path))
        return True, f"Restored from: {os.path.basename(backup_path)}"
    except Exception as e:
        msg = f"Restore failed: {e}"
        log.error(msg, exc_info=True)
        return False, msg


# ══════════════════════════════════════════════════════════
# SAFE RESTORE FLOW (Phase 3)
# ══════════════════════════════════════════════════════════

def safe_restore_backup(backup_path, stop_sync_fn=None, restart_fn=None):
    """
    Safe restore sequence:
      1. Acquire exclusive restore lock (prevents concurrent restores)
      2. Stop auto-sync to prevent mid-sync corruption
      3. Create a 'pre_restore' safety backup of current DB
      4. Copy selected backup over the active DB file
      5. Call restart_fn (app restart callback) if provided

    Args:
        backup_path  (str)      : Full path to the backup file to restore.
        stop_sync_fn (callable) : Called to halt the Firebase auto-sync timer.
                                  Pass firebase_sync.stop_auto_sync here.
        restart_fn   (callable) : Called after successful restore to restart
                                  the application. If None, caller must restart.

    Returns:
        (success: bool, message: str)
    """
    global _restore_in_progress

    # ── Guard: only one restore at a time ─────────────────
    if not _restore_lock.acquire(blocking=False):
        msg = "A restore operation is already in progress. Please wait."
        log.warning(msg)
        return False, msg

    _restore_in_progress = True
    log.info("=== SAFE RESTORE STARTED ===")

    try:
        # ── Step 1: Validate backup file ──────────────────
        if not os.path.exists(backup_path):
            msg = f"Backup file not found: {backup_path}"
            log.error(msg)
            return False, msg

        # ── Step 2: Stop auto-sync ─────────────────────────
        if stop_sync_fn and callable(stop_sync_fn):
            try:
                stop_sync_fn()
                log.info("Auto-sync stopped before restore.")
            except Exception as e:
                log.warning("Could not stop auto-sync: %s", e)

        # ── Step 3: Safety backup of current DB ───────────
        log.info("Creating pre-restore safety backup...")
        safety_path = create_backup(tag="pre_restore")
        if safety_path:
            log.info("Safety backup created: %s", os.path.basename(safety_path))
        else:
            log.warning("Safety backup failed — proceeding with restore (risk accepted).")

        # ── Step 4: Restore selected backup ───────────────
        try:
            shutil.copy2(backup_path, DB_PATH)
            log.info("Database restored successfully from: %s",
                     os.path.basename(backup_path))
        except Exception as e:
            msg = f"Restore copy failed: {e}"
            log.error(msg, exc_info=True)
            return False, msg

        # ── Step 5: Trigger restart ────────────────────────
        if restart_fn and callable(restart_fn):
            log.info("Triggering application restart...")
            try:
                restart_fn()
            except Exception as e:
                log.error("Restart callback failed: %s", e, exc_info=True)

        log.info("=== SAFE RESTORE COMPLETE ===")
        return True, f"Restored from: {os.path.basename(backup_path)}"

    except Exception as e:
        msg = f"Unexpected restore error: {e}"
        log.error(msg, exc_info=True)
        return False, msg

    finally:
        _restore_in_progress = False
        _restore_lock.release()


def is_restore_in_progress():
    """Return True if a restore operation is currently running."""
    return _restore_in_progress


# ══════════════════════════════════════════════════════════
# LIST / CLEANUP
# ══════════════════════════════════════════════════════════

def list_backups():
    """
    List all available backup files, newest first.
    Returns list of dicts: {path, filename, size_kb, date_str}
    """
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    files = glob.glob(os.path.join(BACKUPS_DIR, "backup_*.db"))
    backups = []
    for f in sorted(files, reverse=True):
        try:
            stat = os.stat(f)
            backups.append({
                "path":     f,
                "filename": os.path.basename(f),
                "size_kb":  round(stat.st_size / 1024, 1),
                "date_str": datetime.fromtimestamp(stat.st_mtime).strftime(
                    "%d %b %Y  %I:%M %p"),
            })
        except Exception:
            continue
    return backups


def cleanup_old_backups(keep_days=30):
    """
    Remove backup files older than `keep_days`.
    Returns number of files removed.
    """
    cutoff = datetime.now() - timedelta(days=keep_days)
    removed = 0
    for f in glob.glob(os.path.join(BACKUPS_DIR, "backup_*.db")):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(f))
            if mtime < cutoff:
                os.remove(f)
                log.info("Removed old backup: %s", os.path.basename(f))
                removed += 1
        except Exception as e:
            log.warning("Could not remove %s: %s", f, e)
    if removed:
        log.info("Cleaned up %d old backup(s).", removed)
    return removed
