"""
Firebase Storage PDF Upload — NEW INDIAN STEEL Billing System
=============================================================
Uploads invoice, statement, and daily report PDFs to Firebase Storage
and saves public download URLs back to Firestore.

Features:
- Upload PDFs to a Firebase Storage bucket
- Retrieve public download URLs
- Save URL to Firestore document
- Offline fallback: queues upload for later retry
- Thread-safe background uploads
- Full logging — no silent failures

SETUP INSTRUCTIONS:
1. In Firebase Console → Storage → Get Started (create a bucket)
2. Ensure firebase_credentials.json is in Documents/NEW_INDIAN_STEEL/
3. In Firebase Console → Storage → Rules, allow authenticated writes
4. Install: pip install firebase-admin
   (already required for Firestore sync)

Usage:
    from firebase_storage import upload_pdf_background
    upload_pdf_background("invoice", invoice_id, "/path/to/file.pdf")
"""
import os
import threading
from logger import get_logger
from config import FIREBASE_CRED_PATH, FIREBASE_ENABLED

log = get_logger(__name__)

# ── Firebase Storage bucket name ────────────────────────────
# Set this to your Firebase Storage bucket URL, e.g.:
#   "your-project-id.appspot.com"
# If empty, upload is disabled even when Firebase is available.
STORAGE_BUCKET = ""   # <-- fill in your bucket name

# ── Maximum upload retries ───────────────────────────────────
_MAX_UPLOAD_RETRIES = 3


# ── Firebase Admin SDK initialization ────────────────────────
_storage_bucket = None
_firestore_client = None

if FIREBASE_ENABLED and STORAGE_BUCKET:
    try:
        import firebase_admin
        from firebase_admin import credentials, storage, firestore

        # Re-use the already-initialized app from firebase_sync.py if present
        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_admin.initialize_app(cred, {
                "storageBucket": STORAGE_BUCKET
            })
        else:
            # App already initialized — update bucket if not set
            try:
                _storage_bucket = storage.bucket(STORAGE_BUCKET)
            except Exception:
                pass

        _storage_bucket    = storage.bucket()
        _firestore_client  = firestore.client()
        log.info("Firebase Storage initialized. Bucket: %s", STORAGE_BUCKET)

    except Exception as e:
        log.warning("Firebase Storage setup failed (uploads disabled): %s", e)
        _storage_bucket   = None
        _firestore_client = None
else:
    if not FIREBASE_ENABLED:
        log.info("Firebase Storage: credentials not found — uploads disabled.")
    elif not STORAGE_BUCKET:
        log.info("Firebase Storage: STORAGE_BUCKET not configured — uploads disabled.")


# ══════════════════════════════════════════════════════════════
# PUBLIC HELPERS
# ══════════════════════════════════════════════════════════════

def is_storage_available():
    """Return True if Firebase Storage is configured and initialized."""
    return _storage_bucket is not None


def get_public_url(blob):
    """
    Return the public HTTPS download URL for a Firebase Storage blob.
    Uses make_public() to grant public read access, then returns the URL.
    Returns None on failure.
    """
    try:
        blob.make_public()
        url = blob.public_url
        log.debug("Public URL obtained: %s", url)
        return url
    except Exception as e:
        log.warning("Could not make blob public: %s — trying signed URL", e)
        try:
            import datetime as dt
            url = blob.generate_signed_url(
                expiration=dt.timedelta(days=7),
                method="GET"
            )
            return url
        except Exception as e2:
            log.error("Signed URL generation failed: %s", e2, exc_info=True)
            return None


# ══════════════════════════════════════════════════════════════
# UPLOAD
# ══════════════════════════════════════════════════════════════

def upload_pdf(filepath, doc_type="invoice", doc_id=None):
    """
    Upload a PDF file to Firebase Storage and save the URL to Firestore.

    Args:
        filepath  (str)  : Local path to the PDF file.
        doc_type  (str)  : "invoice" | "statement" | "daily_report"
        doc_id    (str)  : Firestore document ID to attach the URL to.
                           If None, URL is logged only (not saved to Firestore).

    Returns:
        (url: str | None, error: str | None)
        - On success: (download_url, None)
        - On failure: (None, error_message)
    """
    if not is_storage_available():
        msg = "Firebase Storage not available — skipping upload."
        log.info(msg)
        return None, msg

    if not os.path.exists(filepath):
        msg = f"PDF file not found: {filepath}"
        log.error(msg)
        return None, msg

    filename = os.path.basename(filepath)
    # Organise files by type in the bucket
    blob_path = f"pdfs/{doc_type}/{filename}"

    last_error = None
    for attempt in range(1, _MAX_UPLOAD_RETRIES + 1):
        try:
            blob = _storage_bucket.blob(blob_path)
            blob.upload_from_filename(filepath, content_type="application/pdf")
            log.info("PDF uploaded to Firebase Storage: %s (attempt %d)", blob_path, attempt)

            url = get_public_url(blob)
            if not url:
                log.warning("Upload succeeded but URL retrieval failed for %s", blob_path)
                return None, "URL retrieval failed after upload."

            # Save URL back to Firestore
            if _firestore_client and doc_id:
                _save_url_to_firestore(doc_type, str(doc_id), url, filename)

            log.info("PDF upload complete: %s → %s", filename, url)
            return url, None

        except Exception as e:
            last_error = e
            log.warning("PDF upload attempt %d/%d failed: %s", attempt, _MAX_UPLOAD_RETRIES, e)

    log.error("PDF upload failed after %d attempts: %s", _MAX_UPLOAD_RETRIES, last_error,
              exc_info=True)
    return None, str(last_error)


def _save_url_to_firestore(doc_type, doc_id, url, filename):
    """Save the Firebase Storage URL to the corresponding Firestore document."""
    try:
        collection_map = {
            "invoice":      "invoices",
            "statement":    "statements",
            "daily_report": "daily_reports",
        }
        collection = collection_map.get(doc_type, "pdfs")
        _firestore_client.collection(collection).document(doc_id).set(
            {"firebase_url": url, "pdf_filename": filename},
            merge=True  # don't overwrite existing fields
        )
        log.debug("Firestore URL saved: %s/%s → %s", collection, doc_id, url)
    except Exception as e:
        log.warning("Could not save PDF URL to Firestore: %s", e)


def queue_upload_if_offline(filepath, doc_type="invoice", doc_id=None):
    """
    If Firebase Storage is offline/unavailable, queue the upload
    in the persistent sync queue (pending_syncs table) for later retry.

    If storage IS available, uploads immediately in a background thread.
    """
    if is_storage_available():
        # Upload immediately in background — don't block caller
        upload_pdf_background(filepath, doc_type, doc_id)
        return

    # Queue for later
    try:
        import json
        from database import queue_sync_operation
        payload = json.dumps({
            "filepath": filepath,
            "doc_type": doc_type,
            "doc_id":   str(doc_id) if doc_id else None,
        })
        queue_sync_operation("pdf_upload", payload)
        log.info("PDF upload queued (offline): %s", os.path.basename(filepath))
    except Exception as e:
        log.error("Failed to queue PDF upload: %s", e, exc_info=True)


# ══════════════════════════════════════════════════════════════
# BACKGROUND UPLOAD (non-blocking)
# ══════════════════════════════════════════════════════════════

def upload_pdf_background(filepath, doc_type="invoice", doc_id=None):
    """
    Upload a PDF in a daemon thread so the UI is never blocked.
    Falls back to queue_upload_if_offline() if storage is unavailable.
    """
    if not is_storage_available():
        queue_upload_if_offline(filepath, doc_type, doc_id)
        return

    def _worker():
        url, err = upload_pdf(filepath, doc_type, doc_id)
        if err and not url:
            # If upload fails, queue for retry via persistent sync queue
            try:
                import json
                from database import queue_sync_operation
                payload = json.dumps({
                    "filepath": filepath,
                    "doc_type": doc_type,
                    "doc_id":   str(doc_id) if doc_id else None,
                })
                queue_sync_operation("pdf_upload", payload)
                log.info("Failed PDF upload queued for retry: %s", os.path.basename(filepath))
            except Exception as qe:
                log.error("Could not queue failed PDF upload: %s", qe)

    t = threading.Thread(target=_worker, daemon=True,
                         name=f"pdf-upload-{os.path.basename(filepath)}")
    t.start()
    log.debug("Background PDF upload started: %s", os.path.basename(filepath))


# ══════════════════════════════════════════════════════════════
# PROCESS QUEUED PDF UPLOADS (called by process_pending_syncs)
# ══════════════════════════════════════════════════════════════

def process_queued_pdf_upload(payload_dict):
    """
    Process a single queued pdf_upload operation from the sync queue.
    Called by firebase_sync.process_pending_syncs().

    Returns True on success, False on failure.
    """
    filepath  = payload_dict.get("filepath")
    doc_type  = payload_dict.get("doc_type", "invoice")
    doc_id    = payload_dict.get("doc_id")

    if not filepath or not os.path.exists(filepath):
        log.warning("Queued PDF upload skipped — file missing: %s", filepath)
        return False  # Don't retry missing files

    url, err = upload_pdf(filepath, doc_type, doc_id)
    return url is not None
