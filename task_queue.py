"""
task_queue.py — Background Task Queue Processor
================================================
NEW INDIAN STEEL Billing System

Processes background tasks stored in the SQLite background_tasks table.
Runs in a single persistent daemon thread so the Tkinter UI never freezes.

Task types handled:
  print_pdf     — print PDF to default printer
  upload_pdf    — upload PDF to Supabase Storage
  whatsapp_send — open WhatsApp Web with invoice message
  cloud_sync    — sync customer + invoice to Supabase PostgreSQL

Design:
  - One worker thread polls for pending tasks every POLL_INTERVAL seconds
  - Exponential retry delay: 2^retry_count seconds (max 5 min)
  - Duplicate execution prevented: tasks set to 'processing' before work starts
  - All errors caught, logged, and stored in error_message column
  - Thread-safe DB access via database.py primitives
  - Graceful shutdown via stop()

Usage (called from main.py once on startup):
    from task_queue import start_task_worker
    start_task_worker()
"""

import json
import threading
import time
import sys
import os
import subprocess

from logger import get_logger

log = get_logger(__name__)

# ── Configuration ─────────────────────────────────────────
POLL_INTERVAL   = 3      # seconds between task queue polls — push tasks within ~3s of creation
MAX_RETRIES     = 5      # tasks with retry_count >= this are abandoned
MAX_RETRY_DELAY = 300    # cap exponential backoff at 5 minutes

# ── Worker thread state ───────────────────────────────────
_worker_thread   = None
_running         = False
_running_lock    = threading.Lock()


# ══════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════

def add_task(task_type: str, task_data: dict) -> int:
    """
    Add a task to the background queue.

    Args:
        task_type : 'print_pdf' | 'upload_pdf' | 'whatsapp_send' | 'cloud_sync'
        task_data : dict of parameters required by the task handler

    Returns:
        task_id (int) — the new database row ID, or -1 on failure.
    """
    from database import add_background_task  # type: ignore[import]
    payload = json.dumps(task_data, default=str)
    task_id = add_background_task(task_type, payload)
    log.info("Task added: type=%s id=%d data_keys=%s",
             task_type, task_id, list(task_data.keys()))
    return task_id


def start_task_worker() -> None:
    """
    Start the background worker daemon thread.
    Safe to call multiple times — only one thread ever runs.
    """
    global _worker_thread, _running

    with _running_lock:
        if _running and _worker_thread and _worker_thread.is_alive():
            log.debug("Task worker already running — skipping start.")
            return
        _running = True

    _worker_thread = threading.Thread(
        target=_worker_loop,
        daemon=True,
        name="task-queue-worker",
    )
    _worker_thread.start()
    log.info("Background task worker started (poll every %ds).", POLL_INTERVAL)


def stop() -> None:
    """Signal the worker thread to stop after its current poll cycle."""
    global _running
    with _running_lock:
        _running = False
    log.info("Background task worker stop requested.")


def process_tasks() -> None:
    """
    Process all currently pending/retry tasks once (synchronous).
    Can be called manually for testing or immediate flush.
    """
    from database import get_pending_tasks  # type: ignore[import]
    tasks = get_pending_tasks(max_retries=MAX_RETRIES)
    if not tasks:
        log.debug("process_tasks: queue empty.")
        return
    log.info("process_tasks: processing %d task(s).", len(tasks))
    for task in tasks:
        _execute_task(task)


def retry_failed_tasks() -> None:
    """
    Re-queue tasks that are in 'failed' status but still under MAX_RETRIES.
    Useful to call manually after fixing a connectivity issue.
    """
    from database import _execute_read, mark_task_retry  # type: ignore[import]
    rows = _execute_read(
        "SELECT * FROM background_tasks "
        "WHERE status='failed' AND retry_count < ? ORDER BY created_at ASC",
        (MAX_RETRIES,)
    )
    tasks = [dict(r) for r in rows]
    for task in tasks:
        mark_task_retry(task["id"], "manually re-queued")
        log.info("Task re-queued: id=%d type=%s", task["id"], task["task_type"])
    log.info("retry_failed_tasks: %d task(s) re-queued.", len(tasks))


# ══════════════════════════════════════════════════════════
# WORKER LOOP
# ══════════════════════════════════════════════════════════

def _worker_loop() -> None:
    """Main polling loop — runs until stop() is called."""
    log.info("Task worker loop started.")
    while True:
        with _running_lock:
            if not _running:
                break
        try:
            process_tasks()
        except Exception as e:
            log.error("Task worker loop error: %s", e, exc_info=True)
        time.sleep(POLL_INTERVAL)
    log.info("Task worker loop exited.")


# ══════════════════════════════════════════════════════════
# TASK EXECUTOR
# ══════════════════════════════════════════════════════════

def _execute_task(task: dict) -> None:
    """
    Execute a single task row.  Marks it processing before starting,
    then completed/retry after finishing.  Never raises.
    """
    task_id   = task["id"]
    task_type = task["task_type"]
    retry_cnt = task.get("retry_count", 0)

    # ── Exponential backoff ──────────────────────────────
    # Don't retry a task until enough time has passed since last attempt.
    if retry_cnt > 0 and task.get("last_attempt"):
        delay = min(2 ** retry_cnt, MAX_RETRY_DELAY)
        try:
            from datetime import datetime
            last = datetime.strptime(task["last_attempt"], "%Y-%m-%d %H:%M:%S")
            elapsed = (datetime.now() - last).total_seconds()
            if elapsed < delay:
                log.debug(
                    "Task %d: backoff %.0fs remaining (retry #%d).",
                    task_id, delay - elapsed, retry_cnt
                )
                return
        except Exception:
            pass  # Can't parse timestamp — proceed

    from database import (   # type: ignore[import]
        mark_task_processing, mark_task_completed, mark_task_retry
    )

    mark_task_processing(task_id)
    log.info("Task executing: id=%d type=%s retry=%d", task_id, task_type, retry_cnt)

    try:
        data = json.loads(task.get("task_data_json") or "{}")
    except json.JSONDecodeError:
        data = {}

    try:
        if task_type == "print_pdf":
            _handle_print_pdf(data)
        elif task_type == "upload_pdf":
            _handle_upload_pdf(data)
        elif task_type == "whatsapp_send":
            _handle_whatsapp_send(data)
        elif task_type == "cloud_sync":
            _handle_cloud_sync(data)
        else:
            log.warning("Unknown task type: %s — marking completed to drain.", task_type)

        mark_task_completed(task_id)
        log.info("Task completed: id=%d type=%s", task_id, task_type)

    except Exception as e:
        err_msg = str(e)
        log.warning(
            "Task failed: id=%d type=%s error=%s (retry #%d)",
            task_id, task_type, err_msg, retry_cnt
        )
        mark_task_retry(task_id, err_msg)


# ══════════════════════════════════════════════════════════
# TASK HANDLERS
# ══════════════════════════════════════════════════════════

def _handle_print_pdf(data: dict) -> None:
    """
    print_pdf task handler.
    data = {"pdf_path": "/abs/path/to/invoice.pdf"}
    """
    pdf_path = data.get("pdf_path", "")
    if not pdf_path or not os.path.exists(pdf_path):
        log.warning("print_pdf: file not found — %s", pdf_path)
        return  # Don't retry if file is missing

    if sys.platform == "win32":
        os.startfile(pdf_path, "print")
        log.info("print_pdf: sent to printer — %s", os.path.basename(pdf_path))
    elif sys.platform == "darwin":
        subprocess.run(["lpr", pdf_path], check=True)
        log.info("print_pdf: printed via lpr (macOS).")
    else:
        subprocess.run(["lpr", pdf_path], check=True)
        log.info("print_pdf: printed via lpr (Linux).")


def _handle_upload_pdf(data: dict) -> None:
    """
    upload_pdf task handler.
    data = {"pdf_path": ..., "invoice_id": ..., "doc_type": "invoice"}

    On success: saves public URL back to local SQLite invoices row.
    On failure: raises so task_queue retries with backoff.
    """
    from supabase_storage import upload_pdf, is_storage_available  # type: ignore[import]

    pdf_path   = data.get("pdf_path", "")
    invoice_id = data.get("invoice_id")
    doc_type   = data.get("doc_type", "invoice")

    if not pdf_path or not os.path.exists(pdf_path):
        log.warning("upload_pdf: PDF missing — %s — skipping.", pdf_path)
        return  # File gone — no point retrying

    if not is_storage_available():
        raise RuntimeError("Supabase Storage not available — will retry later.")

    url, err = upload_pdf(pdf_path, doc_type=doc_type, doc_id=invoice_id)
    if not url:
        raise RuntimeError(f"Upload failed: {err}")

    # Persist URL to local SQLite
    if invoice_id:
        from database import save_invoice_pdf_url  # type: ignore[import]
        save_invoice_pdf_url(int(invoice_id), url)

    log.info("upload_pdf: success — INV-%s → %s", invoice_id, url)


def _handle_whatsapp_send(data: dict) -> None:
    """
    whatsapp_send task handler.
    data = {phone, customer_name, invoice_id, total, paid,
            balance, old_balance, bill_type, pdf_url}

    Uses the whatsapp._dispatch chain (Meta API -> Twilio -> wa.me)
    so the PDF URL is automatically included for API methods and
    pre-filled in the wa.me link as a final fallback.

    Looks up the latest pdf_url from SQLite at execution time, so a
    whatsapp_send task queued before the upload_pdf task finishes
    still ends up including the URL once it's available.
    """
    from whatsapp import (   # type: ignore[import]
        _normalize_phone, _build_bill_message, _dispatch,
    )

    invoice_id = data.get("invoice_id")
    pdf_url    = data.get("pdf_url", "")
    pdf_path   = data.get("pdf_path", "")

    # If the queued task didn't have a URL yet, check whether the
    # upload_pdf task has since populated invoices.pdf_url.
    if not pdf_url and invoice_id:
        try:
            from database import get_invoice  # type: ignore[import]
            inv = get_invoice(int(invoice_id))
            if inv and inv.get("pdf_url"):
                pdf_url = inv["pdf_url"]
        except Exception as e:
            log.debug("whatsapp_send: could not look up pdf_url: %s", e)

    phone_e164 = _normalize_phone(str(data.get("phone", "")))
    message    = _build_bill_message(
        customer_name = data.get("customer_name", "Customer"),
        invoice_id    = int(invoice_id or 0),
        total         = float(data.get("total", 0)),
        paid          = float(data.get("paid", 0)),
        balance       = float(data.get("balance", 0)),
        old_balance   = float(data.get("old_balance", 0)),
        bill_type     = data.get("bill_type", "invoice"),
        pdf_url       = pdf_url,
        ref_name      = data.get("reference_name", ""),
        ref_phone     = data.get("reference_phone", ""),
        payment_type  = data.get("payment_type", ""),
    )

    _dispatch(phone_e164, message, pdf_path=pdf_path, pdf_url=pdf_url)

    log.info("whatsapp_send: dispatched to +%s for INV-%s (pdf_url=%s)",
             phone_e164, invoice_id, "yes" if pdf_url else "no")


def _handle_cloud_sync(data: dict) -> None:
    """
    cloud_sync task handler.
    data = {"phone": ..., "invoice_id": ..., "payment_id": ..., "product_id": ...}

    Syncs the customer, invoice (if given), payment (if given), and product
    (if given) to Supabase PostgreSQL.
    Raises on failure so task_queue retries with backoff.
    """
    from supabase_sync import (  # type: ignore[import]
        sync_customer, sync_invoice, sync_payment, sync_product, is_online,
    )
    from database import (  # type: ignore[import]
        get_customer, get_invoice, get_invoice_items, get_payment, get_product,
    )

    if not is_online():
        raise RuntimeError("Supabase not reachable — will retry later.")

    phone      = data.get("phone", "")
    invoice_id = data.get("invoice_id")
    payment_id = data.get("payment_id")
    product_id = data.get("product_id")

    # ── Sync customer ─────────────────────────────────────
    if phone:
        cust = get_customer(phone)
        if cust:
            ok = sync_customer(dict(cust))
            if not ok:
                raise RuntimeError("sync_customer failed.")

    # ── Sync invoice + items ──────────────────────────────
    if invoice_id:
        inv   = get_invoice(int(invoice_id))
        items = get_invoice_items(int(invoice_id))
        if inv:
            inv_dict = dict(inv)
            # Local SQLite invoices table only stores customer_phone, not
            # customer_name. Enrich the dict here so the Supabase invoices
            # row gets a meaningful customer_name column.
            if not inv_dict.get("customer_name") and inv_dict.get("customer_phone"):
                c = get_customer(inv_dict["customer_phone"])
                if c:
                    inv_dict["customer_name"] = c.get("name", "")
            ok = sync_invoice(int(invoice_id), inv_dict,
                              [dict(i) for i in items])
            if not ok:
                raise RuntimeError("sync_invoice failed.")

    # ── Sync payment ──────────────────────────────────────
    if payment_id:
        pay = get_payment(int(payment_id))
        if pay:
            ok = sync_payment(dict(pay))
            if not ok:
                raise RuntimeError("sync_payment failed.")

    # ── Sync product ──────────────────────────────────────
    if product_id:
        prod = get_product(int(product_id))
        if prod:
            ok = sync_product(dict(prod))
            if not ok:
                raise RuntimeError("sync_product failed.")

    log.info("cloud_sync: done — phone=%s INV-%s PAY-%s PROD-%s",
             phone, invoice_id, payment_id, product_id)
