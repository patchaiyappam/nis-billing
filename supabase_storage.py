"""
supabase_storage.py — PDF Upload to Supabase Storage
======================================================
NEW INDIAN STEEL Billing System

Uploads invoice PDFs to Supabase Storage bucket "invoices/" and
returns permanent public download URLs.

Mirrors the existing firebase_storage.py pattern so the rest of
the codebase can treat both backends identically.

Features:
- Upload PDFs to Supabase Storage  (bucket: invoices, folder: invoices/)
- Generate permanent public download URL (no expiry)
- Persist PDF URL back to Supabase PostgreSQL invoices table
- Offline fallback: queue upload in SQLite pending_syncs for retry
- Retry logic (configurable _MAX_UPLOAD_RETRIES)
- Background daemon-thread upload — Tkinter UI never freezes
- Optional on_success(url) callback for chained WhatsApp send
- Full logging via logger.py — no silent failures

SETUP (one-time):
    pip install supabase
    # Add to config.py:
    SUPABASE_URL = "https://<project-id>.supabase.co"
    SUPABASE_KEY = "<anon-or-service-role-key>"
    # In Supabase Console → Storage → create bucket "invoices" (public)

Usage:
    from supabase_storage import upload_pdf_background
    upload_pdf_background(pdf_path, doc_type="invoice",
                          doc_id=invoice_id, on_success=my_callback)
"""

import os
import threading
from logger import get_logger

log = get_logger(__name__)

# ── Bucket / folder config ────────────────────────────────
STORAGE_BUCKET = "invoices"          # bucket name in Supabase Console
STORAGE_FOLDER = "invoices"          # logical folder path inside the bucket

# ── Retry config ─────────────────────────────────────────
_MAX_UPLOAD_RETRIES = 3

# ── Module-level client cache ─────────────────────────────
_client = None          # Supabase client instance, or False if init failed
_ready  = False         # True once successfully initialized


def _get_client():
    """
    Return the Supabase client, initializing it lazily on first call.
    Returns None if credentials are missing or the supabase package is absent.
    """
    global _client, _ready

    if _ready:
        return _client                   # already initialized OK

    if _client is False:                 # sentinel: previously failed, don't retry
        return None

    try:
        from config import SUPABASE_URL, SUPABASE_KEY  # type: ignore[import]
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.info("Supabase Storage: SUPABASE_URL/KEY not set in config.py — disabled.")
            _client = False
            return None

        from supabase import create_client  # type: ignore[import]
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _ready  = True
        log.info("Supabase Storage initialized. Bucket: %s", STORAGE_BUCKET)
        return _client

    except ImportError:
        log.warning(
            "Supabase Storage: 'supabase' package not installed. "
            "Run:  pip install supabase"
        )
        _client = False
        return None

    except AttributeError:
        # config.py exists but doesn't have SUPABASE_URL / SUPABASE_KEY yet
        log.info(
            "Supabase Storage: SUPABASE_URL / SUPABASE_KEY missing from config.py. "
            "Add them and restart the app."
        )
        _client = False
        return None

    except Exception as e:
        log.warning("Supabase Storage setup failed (uploads disabled): %s", e)
        _client = False
        return None


# ══════════════════════════════════════════════════════════
# PUBLIC HELPERS
# ══════════════════════════════════════════════════════════

def is_storage_available() -> bool:
    """Return True if Supabase Storage is configured and reachable."""
    return _get_client() is not None


def get_public_url(blob_path: str) -> str | None:
    """
    Return the permanent public URL for an object already uploaded to
    Supabase Storage.  Uses the bucket's public-read policy (no expiry).

    Args:
        blob_path: Path inside the bucket, e.g. "invoices/INV-5_20260511.pdf"

    Returns:
        Public URL string, or None on failure.
    """
    client = _get_client()
    if not client:
        return None
    try:
        url = client.storage.from_(STORAGE_BUCKET).get_public_url(blob_path)
        log.debug("Public URL: %s", url)
        return url
    except Exception as e:
        log.error("Could not get public URL for %s: %s", blob_path, e, exc_info=True)
        return None


# ══════════════════════════════════════════════════════════
# CORE UPLOAD (synchronous — call from a worker thread)
# ══════════════════════════════════════════════════════════

def upload_pdf(
    filepath: str,
    doc_type: str = "invoice",
    doc_id: "int | str | None" = None,
) -> "tuple[str | None, str | None]":
    """
    Upload a PDF file to Supabase Storage with retry logic.

    Args:
        filepath : Absolute local path to the PDF file.
        doc_type : "invoice" | "statement" | "daily_report"
        doc_id   : Invoice ID used to update the cloud DB record.

    Returns:
        (url, None)   — on success; url is the permanent public download link.
        (None, error) — on failure; error is a human-readable string.
    """
    client = _get_client()
    if not client:
        msg = "Supabase Storage not available — skipping upload."
        log.info(msg)
        return None, msg

    if not os.path.exists(filepath):
        msg = f"PDF file not found: {filepath}"
        log.error(msg)
        return None, msg

    filename  = os.path.basename(filepath)
    blob_path = f"{STORAGE_FOLDER}/{filename}"   # e.g. invoices/INV-5_20260511_173045.pdf
    last_err  = None

    for attempt in range(1, _MAX_UPLOAD_RETRIES + 1):
        try:
            with open(filepath, "rb") as fh:
                pdf_bytes = fh.read()

            # upsert=True prevents duplicate-key errors on re-upload
            client.storage.from_(STORAGE_BUCKET).upload(
                path=blob_path,
                file=pdf_bytes,
                file_options={
                    "content-type": "application/pdf",
                    "upsert":       "true",
                },
            )
            log.info(
                "PDF uploaded to Supabase Storage: %s (attempt %d/%d)",
                blob_path, attempt, _MAX_UPLOAD_RETRIES
            )

            url = get_public_url(blob_path)
            if not url:
                log.warning("Upload succeeded but URL retrieval failed: %s", blob_path)
                return None, "URL retrieval failed after successful upload."

            # Persist URL to Supabase PostgreSQL
            if doc_id is not None:
                _save_url_to_cloud(doc_type, doc_id, url, filename)

            log.info("Supabase upload complete: %s → %s", filename, url)
            return url, None

        except Exception as exc:
            last_err = exc
            log.warning(
                "Supabase PDF upload attempt %d/%d failed: %s",
                attempt, _MAX_UPLOAD_RETRIES, exc
            )

    log.error(
        "Supabase PDF upload failed after %d attempts. Last error: %s",
        _MAX_UPLOAD_RETRIES, last_err, exc_info=True
    )
    return None, str(last_err)


def _save_url_to_cloud(
    doc_type: str,
    doc_id: "int | str",
    url: str,
    filename: str,
) -> None:
    """
    Upsert the Supabase Storage download URL back to the PostgreSQL table
    that corresponds to doc_type.  Never overwrites other columns.
    """
    client = _get_client()
    if not client:
        return

    table_map = {
        "invoice":      "invoices",
        "statement":    "statements",
        "daily_report": "daily_reports",
    }
    table = table_map.get(doc_type, "invoices")

    try:
        client.table(table).update(
            {"pdf_url": url, "pdf_filename": filename}
        ).eq("id", str(doc_id)).execute()
        log.debug("Cloud DB URL saved: %s#%s → %s", table, doc_id, url)
    except Exception as e:
        log.warning("Could not save PDF URL to Supabase DB: %s", e)


# ══════════════════════════════════════════════════════════
# OFFLINE QUEUE
# ══════════════════════════════════════════════════════════

def queue_upload_if_offline(
    filepath: str,
    doc_type: str = "invoice",
    doc_id: "int | str | None" = None,
) -> None:
    """
    If Supabase Storage is offline / unconfigured, persist the pending
    upload in the SQLite  pending_syncs  table so it is retried later.

    If storage IS available, kicks off an immediate background upload.
    """
    if is_storage_available():
        upload_pdf_background(filepath, doc_type, doc_id)
        return

    try:
        import json
        from database import queue_sync_operation  # type: ignore[import]
        payload = json.dumps({
            "filepath": filepath,
            "doc_type": doc_type,
            "doc_id":   str(doc_id) if doc_id is not None else None,
            "backend":  "supabase",
        })
        queue_sync_operation("supabase_pdf_upload", payload)
        log.info(
            "PDF upload queued for later (Supabase offline): %s",
            os.path.basename(filepath)
        )
    except Exception as e:
        log.error("Failed to queue Supabase PDF upload: %s", e, exc_info=True)


# ══════════════════════════════════════════════════════════
# BACKGROUND UPLOAD — keeps Tkinter UI fully responsive
# ══════════════════════════════════════════════════════════

def upload_pdf_background(
    filepath: str,
    doc_type: str = "invoice",
    doc_id: "int | str | None" = None,
    on_success=None,
) -> None:
    """
    Upload a PDF in a background daemon thread.

    The Tkinter main thread is never blocked. On success the optional
    on_success(url) callback is fired from the worker thread — use
    root.after() inside it if you need to update the UI.

    Args:
        filepath   : Local PDF path.
        doc_type   : "invoice" | "statement" | "daily_report"
        doc_id     : DB document ID for cloud URL persistence.
        on_success : Optional callable(url: str).  Called after a
                     successful upload.  Use this to chain the WhatsApp
                     send with the real Supabase PDF URL.
    """
    if not is_storage_available():
        queue_upload_if_offline(filepath, doc_type, doc_id)
        return

    def _worker():
        url, err = upload_pdf(filepath, doc_type, doc_id)

        if err and not url:
            # Re-queue for later retry
            try:
                import json
                from database import queue_sync_operation  # type: ignore[import]
                payload = json.dumps({
                    "filepath": filepath,
                    "doc_type": doc_type,
                    "doc_id":   str(doc_id) if doc_id is not None else None,
                    "backend":  "supabase",
                })
                queue_sync_operation("supabase_pdf_upload", payload)
                log.info(
                    "Failed Supabase upload queued for retry: %s",
                    os.path.basename(filepath)
                )
            except Exception as qe:
                log.error("Could not queue failed Supabase PDF upload: %s", qe)
            return

        # Upload succeeded
        if on_success and url:
            try:
                on_success(url)
            except Exception as cb_err:
                log.warning("on_success callback error: %s", cb_err)

    t = threading.Thread(
        target=_worker,
        daemon=True,
        name=f"sb-upload-{os.path.basename(filepath)}",
    )
    t.start()
    log.debug("Background Supabase PDF upload started: %s", os.path.basename(filepath))


# ══════════════════════════════════════════════════════════
# PROCESS QUEUED UPLOADS (called by supabase_sync.process_pending_syncs)
# ══════════════════════════════════════════════════════════

def process_queued_pdf_upload(payload_dict: dict) -> bool:
    """
    Retry a single  supabase_pdf_upload  entry from pending_syncs.

    Returns True on success (entry can be deleted), False to keep for
    another retry later.
    """
    filepath = payload_dict.get("filepath")
    doc_type = payload_dict.get("doc_type", "invoice")
    doc_id   = payload_dict.get("doc_id")

    if not filepath or not os.path.exists(filepath):
        log.warning(
            "Queued Supabase PDF skipped — local file missing: %s", filepath
        )
        return False          # keep in queue; file may appear later

    url, _ = upload_pdf(filepath, doc_type, doc_id)
    return url is not None
