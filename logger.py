"""
Centralized Logging — NEW INDIAN STEEL Billing System
=====================================================
Provides rotating file + console logging for all modules.
Usage:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Something happened")
    log.error("Something broke", exc_info=True)
"""
import os
import logging
from logging.handlers import RotatingFileHandler
from config import LOGS_DIR

# ── Ensure logs directory exists ──────────────────────────
os.makedirs(LOGS_DIR, exist_ok=True)

LOG_FILE = os.path.join(LOGS_DIR, "app.log")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# ── Module-level flag to prevent duplicate root setup ─────
_root_configured = False


def _setup_root_logger():
    """Configure the root logger once with file + console handlers."""
    global _root_configured
    if _root_configured:
        return
    _root_configured = True

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # ── Rotating file handler (5 MB max, keep 5 backups) ──
    try:
        file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        root.addHandler(file_handler)
    except Exception as e:
        # If file logging fails, still allow console logging
        print(f"[LOGGER] Could not create file handler: {e}")

    # ── Console handler (INFO and above) ──────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger. Call this at the top of each module:
        log = get_logger(__name__)

    The root logger is configured on first call.
    """
    _setup_root_logger()
    return logging.getLogger(name)
