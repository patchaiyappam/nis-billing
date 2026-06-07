"""
Firebase Cloud Sync Module — Stabilized + Persistent Queue
===========================================================
Syncs customers, invoices, and payments to Firebase Firestore.
Only runs when internet is available and firebase_credentials.json exists.

Features:
- Auto-sync every N seconds (configurable)
- Retry with exponential backoff (max 3 attempts)
- Sync status tracking: SYNCED, PENDING, OFFLINE, FAILED
- Persistent queue: failed syncs stored in DB, retried on reconnect
- Full logging — no silent failures
- Thread-safe status updates

SETUP INSTRUCTIONS:
1. Go to https://console.firebase.google.com/
2. Create a new project (e.g., "new-indian-steel-billing")
3. Go to Project Settings > Service Accounts
4. Click "Generate new private key" - downloads a JSON file
5. Rename it to "firebase_credentials.json"
6. Place it in: Documents/NEW_INDIAN_STEEL/
7. In Firestore Database, click "Create database" (start in test mode)
"""
import threading
import time
import json
from config import FIREBASE_CRED_PATH, FIREBASE_ENABLED, AUTO_SYNC_INTERVAL
from logger import get_logger

log = get_logger(__name__)

# ── Sync status constants ─────────────────────────────────
STATUS_SYNCED  = "synced"
STATUS_PENDING = "pending"
STATUS_OFFLINE = "offline"
STATUS_FAILED  = "failed"

_sync_status = STATUS_OFFLINE
_sync_lock = threading.Lock()
_auto_sync_timer = None
_auto_sync_running = False

# ── Maximum retry attempts for the persistent queue ───────
_QUEUE_MAX_RETRIES = 5

# ── Firebase initialization ──────────────────────────────
firestore_client = None
if FIREBASE_ENABLED:
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            cred = credentials.Certificate(FIREBASE_CRED_PATH)
            firebase_admin.initialize_app(cred)

        firestore_client = firestore.client()
        _sync_status = STATUS_SYNCED
        log.info("Firebase connected successfully!")
    except Exception as e:
        log.warning("Firebase setup failed (running offline): %s", e)
        firestore_client = None
        _sync_status = STATUS_OFFLINE
else:
    log.info("Firebase credentials not found — running in offline mode.")


# ── Status helpers ────────────────────────────────────────

def get_sync_status():
    """Return current sync status string."""
    with _sync_lock:
        return _sync_status


def _set_status(status):
    """Thread-safe status update."""
    global _sync_status
    with _sync_lock:
        _sync_status = status


def is_online():
    """Check if Firebase is available."""
    return firestore_client is not None


# ── Retry helper ──────────────────────────────────────────

def _retry(func, *args, max_retries=3, label="operation"):
    """
    Run func(*args) with exponential backoff retry.
    Returns True on success, False on final failure.
    """
    for attempt in range(1, max_retries + 1):
        try:
            func(*args)
            return True
        except Exception as e:
            wait = 2 ** attempt  # 2s, 4s, 8s
            if attempt < max_retries:
                log.warning("Sync %s attempt %d/%d failed: %s — retrying in %ds",
                            label, attempt, max_retries, e, wait)
                time.sleep(wait)
            else:
                log.error("Sync %s failed after %d attempts: %s",
                          label, max_retries, e, exc_info=True)
                return False


# ── Sync functions (internal, no retry) ──────────────────

def _sync_customer_impl(customer_dict):
    """Sync a single customer to Firebase (no retry wrapper)."""
    phone = customer_dict["phone"]
    firestore_client.collection("customers").document(phone).set(customer_dict)
    log.debug("Synced customer %s", phone)


def _sync_invoice_impl(invoice_id, invoice_dict, items_list):
    """Sync invoice and its items to Firebase (no retry wrapper)."""
    doc_ref = firestore_client.collection("invoices").document(str(invoice_id))
    invoice_dict["items"] = items_list
    doc_ref.set(invoice_dict)
    from database import mark_invoice_synced
    mark_invoice_synced(invoice_id)
    log.debug("Synced invoice %s", invoice_id)


def _sync_payment_impl(payment_id, payment_dict):
    """Sync payment to Firebase (no retry wrapper)."""
    firestore_client.collection("payments").document(str(payment_id)).set(payment_dict)
    from database import mark_payment_synced
    mark_payment_synced(payment_id)
    log.debug("Synced payment %s", payment_id)


# ── Queue helper ──────────────────────────────────────────

def _queue_on_failure(operation, payload_dict):
    """
    Persist a failed sync operation to the DB queue so it can be
    retried automatically on the next app startup or sync cycle.
    """
    try:
        from database import queue_sync_operation
        queue_sync_operation(operation, json.dumps(payload_dict, default=str))
        log.info("Queued for later retry: op=%s", operation)
    except Exception as e:
        log.error("Failed to queue operation '%s': %s", operation, e, exc_info=True)


# ── Public sync functions (with retry + queue fallback) ──

def sync_customer(customer_dict):
    """Sync a single customer to Firebase with retry. Queues on failure."""
    if not is_online():
        _set_status(STATUS_OFFLINE)
        _queue_on_failure("sync_customer", customer_dict)
        return
    _set_status(STATUS_PENDING)
    ok = _retry(_sync_customer_impl, customer_dict,
                label=f"customer:{customer_dict.get('phone','?')}")
    if ok:
        _set_status(STATUS_SYNCED)
    else:
        _set_status(STATUS_FAILED)
        _queue_on_failure("sync_customer", customer_dict)


def sync_invoice(invoice_id, invoice_dict, items_list):
    """Sync invoice and its items to Firebase with retry. Queues on failure."""
    if not is_online():
        _set_status(STATUS_OFFLINE)
        _queue_on_failure("sync_invoice", {
            "invoice_id": invoice_id,
            "invoice":    invoice_dict,
            "items":      items_list,
        })
        return
    _set_status(STATUS_PENDING)
    ok = _retry(_sync_invoice_impl, invoice_id, invoice_dict, items_list,
                label=f"invoice:{invoice_id}")
    if ok:
        _set_status(STATUS_SYNCED)
    else:
        _set_status(STATUS_FAILED)
        _queue_on_failure("sync_invoice", {
            "invoice_id": invoice_id,
            "invoice":    invoice_dict,
            "items":      items_list,
        })


def sync_payment(payment_id, payment_dict):
    """Sync payment to Firebase with retry. Queues on failure."""
    if not is_online():
        _set_status(STATUS_OFFLINE)
        _queue_on_failure("sync_payment", {
            "payment_id": payment_id,
            "payment":    payment_dict,
        })
        return
    _set_status(STATUS_PENDING)
    ok = _retry(_sync_payment_impl, payment_id, payment_dict,
                label=f"payment:{payment_id}")
    if ok:
        _set_status(STATUS_SYNCED)
    else:
        _set_status(STATUS_FAILED)
        _queue_on_failure("sync_payment", {
            "payment_id": payment_id,
            "payment":    payment_dict,
        })


# ── Full sync ────────────────────────────────────────────

def sync_all_pending():
    """
    Sync all unsynced records to Firebase with retry on each.
    Also processes the persistent retry queue of previously failed syncs.
    """
    if not is_online():
        log.info("Firebase not available, skipping sync.")
        _set_status(STATUS_OFFLINE)
        return

    _set_status(STATUS_PENDING)
    log.info("Starting full sync...")

    from database import (get_unsynced_invoices, get_unsynced_payments,
                          get_invoice_items, get_all_customers)

    had_failure = False

    # Sync all customers
    customers = get_all_customers()
    for cust in customers:
        ok = _retry(_sync_customer_impl, cust,
                    label=f"customer:{cust['phone']}")
        if not ok:
            had_failure = True

    # Sync unsynced invoices
    unsynced_inv = get_unsynced_invoices()
    for inv in unsynced_inv:
        items = get_invoice_items(inv["id"])
        ok = _retry(_sync_invoice_impl, inv["id"], dict(inv),
                    [dict(i) for i in items],
                    label=f"invoice:{inv['id']}")
        if not ok:
            had_failure = True

    # Sync unsynced payments
    unsynced_pay = get_unsynced_payments()
    for pay in unsynced_pay:
        ok = _retry(_sync_payment_impl, pay["id"], dict(pay),
                    label=f"payment:{pay['id']}")
        if not ok:
            had_failure = True

    # ── Process the persistent queue ─────────────────────
    queue_had_failure = _process_persistent_queue()
    if queue_had_failure:
        had_failure = True

    if had_failure:
        _set_status(STATUS_FAILED)
        log.warning("Full sync completed with some failures.")
    else:
        _set_status(STATUS_SYNCED)
        log.info("Full sync completed — %d customers, %d invoices, %d payments.",
                 len(customers), len(unsynced_inv), len(unsynced_pay))


# ══════════════════════════════════════════════════════════
# PERSISTENT SYNC QUEUE PROCESSING
# ══════════════════════════════════════════════════════════

def _process_persistent_queue():
    """
    Process all items in the pending_syncs table (DB).
    Called automatically at the end of every sync_all_pending() run.
    Thread-safe — uses the same DB write lock.

    Returns True if any item still failed after dispatch.
    """
    if not is_online():
        return False

    try:
        from database import (get_pending_syncs, remove_sync_item,
                               increment_sync_retry)
    except ImportError:
        log.warning("database.py queue functions not available — skipping queue.")
        return False

    items = get_pending_syncs(max_retries=_QUEUE_MAX_RETRIES)
    if not items:
        log.debug("Persistent sync queue is empty.")
        return False

    log.info("Processing %d item(s) from persistent sync queue...", len(items))
    had_failure = False

    for item in items:
        item_id   = item["id"]
        operation = item["operation"]
        retry_cnt = item["retry_count"]

        # Deserialize payload
        try:
            payload = json.loads(item["payload"])
        except (json.JSONDecodeError, TypeError) as e:
            log.error("Queue item %d has invalid payload — removing: %s", item_id, e)
            remove_sync_item(item_id)
            continue

        log.debug("Processing queue item %d: op=%s retry=%d", item_id, operation, retry_cnt)
        success = _dispatch_queue_item(operation, payload)

        if success:
            remove_sync_item(item_id)
            log.info("Queue item %d cleared (op=%s).", item_id, operation)
        else:
            increment_sync_retry(item_id)
            new_count = retry_cnt + 1
            log.warning("Queue item %d retry %d/%d failed (op=%s).",
                        item_id, new_count, _QUEUE_MAX_RETRIES, operation)
            had_failure = True

    return had_failure


def _dispatch_queue_item(operation, payload):
    """
    Route a persistent queue item to the correct sync handler.
    Returns True on success, False on failure.
    """
    try:
        if operation == "sync_customer":
            return _retry(_sync_customer_impl, payload,
                          label=f"queue:customer:{payload.get('phone','?')}")

        elif operation == "sync_invoice":
            inv_id   = payload.get("invoice_id")
            inv_dict = payload.get("invoice", {})
            items    = payload.get("items", [])
            return _retry(_sync_invoice_impl, inv_id, inv_dict, items,
                          label=f"queue:invoice:{inv_id}")

        elif operation == "sync_payment":
            pay_id   = payload.get("payment_id")
            pay_dict = payload.get("payment", {})
            return _retry(_sync_payment_impl, pay_id, pay_dict,
                          label=f"queue:payment:{pay_id}")

        elif operation == "pdf_upload":
            try:
                from firebase_storage import process_queued_pdf_upload
                return process_queued_pdf_upload(payload)
            except Exception as e:
                log.error("pdf_upload dispatch error: %s", e, exc_info=True)
                return False

        else:
            # Unknown operation — remove so it doesn't loop forever
            log.warning("Unknown queue operation '%s' — discarding item.", operation)
            return True

    except Exception as e:
        log.error("Queue dispatch failed for op='%s': %s", operation, e, exc_info=True)
        return False


def process_pending_syncs():
    """
    Public API — process the persistent sync queue now.
    Safe to call from any thread. Does not block the UI.
    """
    if not is_online():
        log.info("process_pending_syncs: offline, skipping.")
        return
    _process_persistent_queue()


# ── Background helpers ────────────────────────────────────

def _sync_in_background(func, *args):
    """Run sync function in a background daemon thread."""
    thread = threading.Thread(target=func, args=args, daemon=True)
    thread.start()


def background_sync_all():
    """Run full sync in background thread (non-blocking)."""
    _sync_in_background(sync_all_pending)


# ── Auto-sync timer ──────────────────────────────────────

def start_auto_sync(interval=None):
    """
    Start recurring auto-sync every `interval` seconds.
    Uses AUTO_SYNC_INTERVAL from config if not specified.
    Each tick also processes the persistent queue.
    """
    global _auto_sync_running, _auto_sync_timer
    if _auto_sync_running:
        return  # already running

    interval = interval or AUTO_SYNC_INTERVAL
    _auto_sync_running = True
    log.info("Auto-sync started (every %ds)", interval)

    def _tick():
        global _auto_sync_timer
        if not _auto_sync_running:
            return
        try:
            sync_all_pending()
        except Exception as e:
            log.error("Auto-sync tick failed: %s", e, exc_info=True)
        # Schedule next tick
        _auto_sync_timer = threading.Timer(interval, _tick)
        _auto_sync_timer.daemon = True
        _auto_sync_timer.start()

    # Start first tick after interval (not immediately, to let startup settle)
    _auto_sync_timer = threading.Timer(interval, _tick)
    _auto_sync_timer.daemon = True
    _auto_sync_timer.start()


def stop_auto_sync():
    """Stop the recurring auto-sync timer."""
    global _auto_sync_running, _auto_sync_timer
    _auto_sync_running = False
    if _auto_sync_timer:
        _auto_sync_timer.cancel()
        _auto_sync_timer = None
    log.info("Auto-sync stopped.")
