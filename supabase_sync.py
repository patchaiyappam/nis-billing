"""
supabase_sync.py — Supabase PostgreSQL Cloud Sync
==================================================
NEW INDIAN STEEL Billing System

Syncs customers, invoices, and payments to Supabase PostgreSQL.
Mirrors the existing firebase_sync.py structure so both backends
can coexist and be swapped or run together without conflicts.

Features:
- Auto-sync every N seconds (AUTO_SYNC_INTERVAL from config.py)
- Upsert semantics — safe to run multiple times
- Retry with up to _QUEUE_MAX_RETRIES on the persistent SQLite queue
- Process pending supabase_pdf_upload entries from the retry queue
- Sync status: synced | pending | offline | failed
- Full logging via logger.py — no silent failures

SETUP (one-time):
    pip install supabase
    # Add to config.py:
    SUPABASE_URL = "https://<project-id>.supabase.co"
    SUPABASE_KEY = "<anon-or-service-role-key>"

    # Run migrations.py (or the SQL in README_SUPABASE.md) to create
    # the cloud tables:  customers, invoices, invoice_items, payments,
    # statements, daily_reports  (all with a  pdf_url TEXT  column).
"""

import threading
import time
import json
from logger import get_logger

log = get_logger(__name__)

# ── Sync status constants (same as firebase_sync) ────────
STATUS_SYNCED  = "synced"
STATUS_PENDING = "pending"
STATUS_OFFLINE = "offline"
STATUS_FAILED  = "failed"

_sync_status      = STATUS_OFFLINE
_sync_lock        = threading.Lock()
_auto_sync_timer  = None
_auto_sync_running = False

_QUEUE_MAX_RETRIES = 5
_sync_all_runs = 0   # full-sync counter (throttles bulk product pushes)


def _force_http1():
    """Force httpx (the Supabase client) onto HTTP/1.1. Supabase behind
    Cloudflare breaks on HTTP/2 here (ConnectionTerminated / 'pseudo-header in
    trailer'), which stalls all syncing."""
    try:
        import httpx
        if getattr(httpx.Client, "_nis_http1", False):
            return
        _orig = httpx.Client.__init__
        def _init(self, *a, **kw):
            kw["http2"] = False
            return _orig(self, *a, **kw)
        httpx.Client.__init__ = _init
        httpx.Client._nis_http1 = True
    except Exception:
        pass

# ── Module-level Supabase client ─────────────────────────
_client = None      # Supabase client or None
_ready  = False


def _get_client():
    """
    Return the Supabase client, initializing it lazily.
    Returns None if credentials are absent or the package is missing.
    """
    global _client, _ready

    if _ready:
        return _client

    if _client is False:
        return None

    try:
        from config import SUPABASE_URL, SUPABASE_KEY  # type: ignore[import]
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.info("Supabase Sync: SUPABASE_URL/KEY not set in config.py — disabled.")
            _client = False
            return None

        _force_http1()
        from supabase import create_client  # type: ignore[import]
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _ready  = True
        _set_status(STATUS_SYNCED)
        log.info("Supabase Sync: connected successfully.")
        return _client

    except ImportError:
        log.warning(
            "Supabase Sync: 'supabase' package not installed. "
            "Run:  pip install supabase"
        )
        _client = False
        return None

    except AttributeError:
        log.info(
            "Supabase Sync: SUPABASE_URL / SUPABASE_KEY missing from config.py."
        )
        _client = False
        return None

    except Exception as e:
        log.warning("Supabase Sync setup failed (offline mode): %s", e)
        _client = False
        return None


# ── Status helpers ────────────────────────────────────────

def get_sync_status() -> str:
    """Return current Supabase sync status string."""
    with _sync_lock:
        return _sync_status


def _set_status(status: str) -> None:
    """Thread-safe status update."""
    global _sync_status
    with _sync_lock:
        _sync_status = status


def is_online() -> bool:
    """Return True if Supabase is reachable."""
    return _get_client() is not None


# ══════════════════════════════════════════════════════════
# INDIVIDUAL SYNC HELPERS
# ══════════════════════════════════════════════════════════

def sync_customer(customer: dict) -> bool:
    """
    Upsert a customer record to Supabase PostgreSQL.

    Args:
        customer: dict with keys id, phone, name, total_due, …

    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client:
        _queue_operation("sync_customer", customer)
        return False

    try:
        # Setting updated_at to NOW() ensures the other PC's pull worker
        # picks this row up on its next poll cycle.
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        client.table("customers").upsert(
            {
                "id":              str(customer["id"]),
                "phone":           customer.get("phone", ""),
                "name":            customer.get("name", ""),
                "total_due":       float(customer.get("total_due", 0)),
                "opening_balance": float(customer.get("opening_balance", 0)),
                "address":         customer.get("address", ""),
                "updated_at":      now_iso,
            },
            on_conflict="id"
        ).execute()
        log.debug("Supabase: customer synced — %s", customer.get("phone"))
        _set_status(STATUS_SYNCED)
        return True
    except Exception as e:
        log.warning("Supabase sync_customer failed: %s", e)
        _queue_operation("sync_customer", customer)
        _set_status(STATUS_FAILED)
        return False


def sync_invoice(
    invoice_id: int,
    invoice: dict,
    items: list,
) -> bool:
    """
    Upsert an invoice and its line items to Supabase PostgreSQL.

    Returns True on success, False on failure (auto-queued for retry).
    """
    client = _get_client()
    if not client:
        _queue_operation("sync_invoice", {
            "invoice_id": invoice_id,
            "invoice":    invoice,
            "items":      items,
        })
        return False

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        # Use the device-unique cloud_id as the cloud primary key so two
        # PCs/phone can never overwrite each other's bills.
        cloud_id = str(invoice.get("cloud_id") or invoice_id)
        client.table("invoices").upsert(
            {
                "id":              cloud_id,
                "customer_phone":  invoice.get("customer_phone", ""),
                "customer_name":   invoice.get("customer_name", ""),
                "total":           float(invoice.get("total", 0)),
                "paid":            float(invoice.get("paid", 0)),
                "balance":         float(invoice.get("balance", 0)),
                "type":            invoice.get("type", "invoice"),
                "date":            invoice.get("date", ""),
                "pdf_url":         invoice.get("pdf_url", ""),
                "reference_phone": invoice.get("reference_phone", ""),
                "updated_at":      now_iso,
            },
            on_conflict="id"
        ).execute()

        for item in items:
            client.table("invoice_items").upsert(
                {
                    "invoice_id":   cloud_id,
                    "product_name": item.get("product_name", ""),
                    "qty":          float(item.get("qty", 0)),
                    "price":        float(item.get("price", 0)),
                    "amount":       float(item.get("amount", 0)),
                    "updated_at":   now_iso,
                },
                on_conflict="invoice_id,product_name"
            ).execute()

        log.debug("Supabase: invoice synced — INV-%d", invoice_id)
        _set_status(STATUS_SYNCED)
        return True

    except Exception as e:
        log.warning("Supabase sync_invoice failed: %s", e)
        _queue_operation("sync_invoice", {
            "invoice_id": invoice_id,
            "invoice":    invoice,
            "items":      items,
        })
        _set_status(STATUS_FAILED)
        return False


def sync_payment(payment: dict) -> bool:
    """
    Upsert a payment record to Supabase PostgreSQL.

    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client:
        _queue_operation("sync_payment", payment)
        return False

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        client.table("payments").upsert(
            {
                "id":             str(payment.get("cloud_id") or payment.get("id", "")),
                "customer_phone": payment.get("customer_phone", ""),
                "amount":         float(payment.get("amount", 0)),
                "date":           payment.get("date", ""),
                "note":           payment.get("note", ""),
                "updated_at":     now_iso,
            },
            on_conflict="id"
        ).execute()
        log.debug("Supabase: payment synced — PAY-%s", payment.get("id"))
        _set_status(STATUS_SYNCED)
        return True

    except Exception as e:
        log.warning("Supabase sync_payment failed: %s", e)
        _queue_operation("sync_payment", payment)
        _set_status(STATUS_FAILED)
        return False


def sync_product(product: dict) -> bool:
    """
    Upsert a product record to Supabase PostgreSQL.

    Args:
        product: dict with keys id, name, price, unit, updated_at

    Returns True on success, False on failure.
    """
    client = _get_client()
    if not client:
        _queue_operation("sync_product", product)
        return False

    try:
        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat()
        client.table("products").upsert(
            {
                "id":         str(product["id"]),
                "name":       product.get("name", ""),
                "price":      float(product.get("price", 0)),
                "unit":       product.get("unit", "Nos"),
                # Never fabricate NOW() for a product missing a timestamp — that
                # makes a stale copy look newest and reverts real price edits.
                "updated_at": product.get("updated_at") or "2000-01-01T00:00:00+00:00",
            },
            on_conflict="id"
        ).execute()
        log.debug("Supabase: product synced — %s", product.get("name"))
        _set_status(STATUS_SYNCED)
        return True

    except Exception as e:
        log.warning("Supabase sync_product failed: %s", e)
        _queue_operation("sync_product", product)
        _set_status(STATUS_FAILED)
        return False


# ══════════════════════════════════════════════════════════
# FULL SYNC (called on startup and by auto-sync timer)
# ══════════════════════════════════════════════════════════

def sync_all() -> None:
    """
    Push all local SQLite data to Supabase PostgreSQL.
    Runs in a daemon thread — never blocks the UI.
    """
    if not is_online():
        log.info("Supabase Sync: offline — full sync skipped.")
        _set_status(STATUS_OFFLINE)
        return

    def _worker():
        try:
            from database import (  # type: ignore[import]
                get_all_customers, get_all_invoices,
                get_invoice_items, get_all_payments, get_all_products,
            )
        except ImportError as ie:
            log.error("Supabase sync_all: could not import database.py — %s", ie)
            return

        try:
            import time as _time

            # ── Products ──────────────────────────────────────
            # Push in small batches with a short sleep to avoid
            # hitting Supabase's 100-stream HTTP/2 connection limit.
            # Products rarely change and are the bulk of the traffic — push
            # them only every ~10th cycle to avoid flooding Supabase.
            global _sync_all_runs
            _sync_all_runs += 1
            if _sync_all_runs % 10 == 1:
                products = get_all_products()
                for i, p in enumerate(products):
                    sync_product(dict(p))
                    if i % 20 == 19:
                        _time.sleep(0.5)

            customers = get_all_customers()
            name_by_phone = {c["phone"]: c.get("name", "") for c in customers}
            for i, c in enumerate(customers):
                sync_customer(dict(c))
                if i % 20 == 19:
                    _time.sleep(0.3)

            invoices = get_all_invoices()
            for i, inv in enumerate(invoices):
                inv_d = dict(inv)
                if not inv_d.get("customer_name"):
                    inv_d["customer_name"] = name_by_phone.get(
                        inv_d.get("customer_phone", ""), ""
                    )
                items = get_invoice_items(inv_d["id"])
                sync_invoice(inv_d["id"], inv_d, [dict(i) for i in items])
                if i % 10 == 9:
                    _time.sleep(0.3)

            payments = get_all_payments()
            for i, p in enumerate(payments):
                sync_payment(dict(p))
                if i % 20 == 19:
                    _time.sleep(0.3)

            process_pending_syncs()
            log.info("Supabase full sync complete.")
            _set_status(STATUS_SYNCED)

        except Exception as e:
            log.error("Supabase sync_all error: %s", e, exc_info=True)
            _set_status(STATUS_FAILED)

    t = threading.Thread(target=_worker, daemon=True, name="sb-sync-all")
    t.start()


# ══════════════════════════════════════════════════════════
# PERSISTENT QUEUE HELPERS
# ══════════════════════════════════════════════════════════

def _queue_operation(operation: str, data: dict) -> None:
    """
    Persist a failed sync operation in SQLite pending_syncs for retry.
    """
    try:
        from database import queue_sync_operation  # type: ignore[import]
        payload = json.dumps(data, default=str)
        queue_sync_operation(f"supabase_{operation}", payload)
        log.info("Supabase op queued for retry: %s", operation)
    except Exception as e:
        log.error("Could not queue Supabase operation '%s': %s", operation, e)


def process_pending_syncs(max_retries: int = _QUEUE_MAX_RETRIES) -> None:
    """
    Retry all pending  supabase_*  operations stored in SQLite.
    Called by sync_all() and can be called manually.
    """
    if not is_online():
        return

    try:
        from database import (  # type: ignore[import]
            get_pending_syncs, mark_sync_complete, increment_sync_retry,
        )
    except ImportError as ie:
        log.error("process_pending_syncs: cannot import database.py — %s", ie)
        return

    pending = get_pending_syncs(max_retries)
    if not pending:
        return

    log.info("Supabase: processing %d pending sync item(s).", len(pending))

    for item in pending:
        op      = item["operation"]
        item_id = item["id"]

        if not op.startswith("supabase_"):
            continue           # belongs to firebase_sync, not us

        try:
            data = json.loads(item["payload"])
        except Exception:
            mark_sync_complete(item_id)
            continue

        success = False
        try:
            if op == "supabase_sync_customer":
                success = sync_customer(data)
            elif op == "supabase_sync_invoice":
                success = sync_invoice(
                    data["invoice_id"], data["invoice"], data.get("items", [])
                )
            elif op == "supabase_sync_payment":
                success = sync_payment(data)
            elif op == "supabase_sync_product":
                success = sync_product(data)
            elif op == "supabase_pdf_upload":
                from supabase_storage import process_queued_pdf_upload  # type: ignore[import]
                success = process_queued_pdf_upload(data)
            else:
                log.warning("Unknown supabase queue op: %s — skipping.", op)
                mark_sync_complete(item_id)
                continue

        except Exception as exc:
            log.error("Error processing queued op %s: %s", op, exc, exc_info=True)

        if success:
            mark_sync_complete(item_id)
            log.info("Supabase retry succeeded: %s (id=%d)", op, item_id)
        else:
            increment_sync_retry(item_id)
            log.warning("Supabase retry failed: %s (id=%d)", op, item_id)


# ══════════════════════════════════════════════════════════
# AUTO-SYNC TIMER (background, matches firebase_sync pattern)
# ══════════════════════════════════════════════════════════

def start_auto_sync() -> None:
    """
    Start a repeating background timer that calls sync_all() every
    AUTO_SYNC_INTERVAL seconds (defined in config.py).
    Safe to call multiple times — only one timer runs at a time.
    """
    global _auto_sync_running, _auto_sync_timer

    if _auto_sync_running:
        return

    try:
        from config import AUTO_SYNC_INTERVAL  # type: ignore[import]
        interval = AUTO_SYNC_INTERVAL
    except Exception:
        interval = 60

    _auto_sync_running = True
    log.info("Supabase auto-sync started (interval=%ds).", interval)

    def _tick():
        global _auto_sync_timer
        if not _auto_sync_running:
            return
        sync_all()
        _auto_sync_timer = threading.Timer(interval, _tick)
        _auto_sync_timer.daemon = True
        _auto_sync_timer.start()

    _auto_sync_timer = threading.Timer(interval, _tick)
    _auto_sync_timer.daemon = True
    _auto_sync_timer.start()


def stop_auto_sync() -> None:
    """Stop the repeating auto-sync timer."""
    global _auto_sync_running, _auto_sync_timer
    _auto_sync_running = False
    if _auto_sync_timer:
        _auto_sync_timer.cancel()
        _auto_sync_timer = None
    log.info("Supabase auto-sync stopped.")
