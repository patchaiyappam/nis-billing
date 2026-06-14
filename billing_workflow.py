"""
billing_workflow.py — Automated Billing Workflow Orchestrator
=============================================================
NEW INDIAN STEEL Billing System

Orchestrates the complete 10-step automated billing workflow
triggered when the user clicks "Generate Bill".

Steps (in order):
  1.  Save invoice in SQLite database          ← MUST succeed; aborts on failure
  2.  Generate invoice PDF                     ← failure logged, workflow continues
  3.  Print PDF automatically (default printer)
  4.  Upload PDF to Supabase Storage           ← background thread
  5.  Get public PDF URL from Supabase
  6.  Open WhatsApp automatically
  7.  Open customer chat automatically
  8.  Fill invoice summary in WhatsApp
  9.  Include Supabase PDF URL in message
  10. Send WhatsApp message automatically

Design principles:
  - Step 1 (DB save) ALWAYS runs synchronously and must succeed.
  - Steps 2-3 run synchronously in the calling thread.
  - Steps 4-10 run in a background daemon thread (non-blocking).
  - Any post-save failure is logged only; it never cancels the invoice.
  - Tkinter UI is never frozen.
  - Uses logger.py throughout.

Usage (replace existing code in billing_frame._generate_bill):
    from billing_workflow import run_billing_workflow

    invoice_id, pdf_path, error = run_billing_workflow(
        phone, name, grand, paid, max(0, net_balance),
        self.items,
        bill_type    = bill_type,
        transport    = transport,
        discount_pct = disc_pct,
        discount_amt = disc_amt,
        old_balance  = old_bal,
        net_balance  = net_balance,
    )

    if invoice_id is None:
        messagebox.showerror("Error", f"Failed to save invoice:\n{error}")
        return

    # Show success dialog immediately (upload + WhatsApp happen in background)
    messagebox.showinfo("Bill Saved!", ...)
"""

import os
import sys
import subprocess
import threading
from logger import get_logger

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════
# STEP HELPERS
# ══════════════════════════════════════════════════════════

def _step_save_invoice(
    phone, name, total, paid, balance, items,
    bill_type, transport, discount_pct, discount_amt,
    old_balance, net_balance, reference_phone="", payment_type="Cash"
):
    """
    STEP 1 — Save invoice to SQLite (atomic, thread-safe).
    Returns (invoice_id, pdf_path, error).
    """
    try:
        from database import create_invoice_atomic  # type: ignore[import]
        invoice_id, pdf_path, error = create_invoice_atomic(
            phone, name, total, paid, balance,
            items,
            bill_type       = bill_type,
            transport       = transport,
            discount_pct    = discount_pct,
            discount_amt    = discount_amt,
            old_balance     = old_balance,
            net_balance     = net_balance,
            reference_phone = reference_phone,
            payment_type    = payment_type,
        )
        if invoice_id:
            log.info(
                "STEP 1 ✓ Invoice #%d saved — total=₹%.2f paid=₹%.2f",
                invoice_id, total, paid
            )
        else:
            log.error("STEP 1 ✗ Invoice save failed: %s", error)
        return invoice_id, pdf_path, error

    except Exception as e:
        log.error("STEP 1 ✗ create_invoice_atomic raised: %s", e, exc_info=True)
        return None, None, str(e)


def _step_print_pdf(pdf_path: str) -> None:
    """
    STEP 3 — Print the PDF using the system default printer.
    Uses os.startfile(path, 'print') on Windows.
    Failure is logged and warned but never stops the workflow.
    """
    if not pdf_path or not os.path.exists(pdf_path):
        log.warning("STEP 3 ✗ Print skipped — PDF not found: %s", pdf_path)
        return
    try:
        if sys.platform == "win32":
            os.startfile(pdf_path, "print")
            log.info("STEP 3 ✓ PDF sent to default printer: %s", os.path.basename(pdf_path))
        elif sys.platform == "darwin":
            subprocess.run(["lpr", pdf_path], check=True)
            log.info("STEP 3 ✓ PDF printed (macOS lpr): %s", os.path.basename(pdf_path))
        else:
            subprocess.run(["lpr", pdf_path], check=True)
            log.info("STEP 3 ✓ PDF printed (Linux lpr): %s", os.path.basename(pdf_path))
    except Exception as e:
        log.warning("STEP 3 ✗ Print failed (non-fatal): %s", e)


def _step_open_pdf(pdf_path: str) -> None:
    """
    STEP 2b — Open the PDF for visual confirmation (existing behaviour).
    """
    if not pdf_path or not os.path.exists(pdf_path):
        return
    try:
        if sys.platform == "win32":
            os.startfile(pdf_path)
        elif sys.platform == "darwin":
            subprocess.run(["open", pdf_path])
        else:
            subprocess.run(["xdg-open", pdf_path])
    except Exception as e:
        log.debug("Open PDF skipped: %s", e)


def _whatsapp_auto_send_ok() -> bool:
    """Auto-send WhatsApp only when it won't disrupt billing: needs
    WA_AUTO_SEND=True AND a silent method (Meta/Twilio). "wame" steals focus."""
    try:
        from config import WA_AUTO_SEND, WA_METHOD  # type: ignore[import]
        return bool(WA_AUTO_SEND) and str(WA_METHOD).lower() in ("meta", "twilio")
    except Exception:
        return False


def _step_upload_and_whatsapp(
    pdf_path: str,
    invoice_id: int,
    phone: str,
    name: str,
    total: float,
    paid: float,
    balance: float,
    old_balance: float,
    bill_type: str,
    reference_name: str = "",
    reference_phone: str = "",
    payment_type: str = "Cash",
) -> None:
    """
    STEPS 4-10 — Runs entirely in a background thread.
    Queues upload_pdf, cloud_sync, and whatsapp_send as durable tasks
    so they survive app restarts if they fail.
    """
    from task_queue import add_task  # type: ignore[import]

    # ── STEP 4/5: Queue PDF upload ────────────────────────
    if pdf_path and os.path.exists(pdf_path):
        add_task("upload_pdf", {
            "pdf_path":   pdf_path,
            "invoice_id": invoice_id,
            "doc_type":   "invoice",
        })
        log.info("STEP 4: upload_pdf task queued for INV-%d", invoice_id)
    else:
        log.warning("STEP 4: PDF missing — upload skipped: %s", pdf_path)

    # ── STEPS 6-10: Queue WhatsApp send (only if non-disruptive) ──
    if _whatsapp_auto_send_ok():
        add_task("whatsapp_send", {
            "phone":          phone,
            "customer_name":  name,
            "invoice_id":     invoice_id,
            "total":          total,
            "paid":           paid,
            "balance":        balance,
            "old_balance":    old_balance,
            "bill_type":      bill_type,
            "pdf_url":        "",             # will be filled after upload completes
            "pdf_path":       pdf_path or "", # for local image sending
            "reference_name": reference_name or "",
            "reference_phone":reference_phone or "",
            "payment_type":   payment_type or "Cash",
        })
        log.info("STEPS 6-10: whatsapp_send task queued for INV-%d", invoice_id)
    else:
        log.info("WhatsApp auto-send disabled — billing left undisturbed (INV-%d).", invoice_id)

    # ── Supabase DB sync ─────────────────────────────────
    add_task("cloud_sync", {
        "phone":      phone,
        "invoice_id": invoice_id,
    })
    log.info("Cloud sync task queued for INV-%d", invoice_id)


def _save_pdf_url_to_sqlite(invoice_id: int, pdf_url: str) -> None:
    """
    Persist the Supabase PDF URL back to the local SQLite invoices table
    so it is available offline and in reports.
    """
    try:
        from database import get_conn, _write_lock  # type: ignore[import]
        import threading as _threading

        with _write_lock:
            conn = get_conn()
            try:
                conn.execute(
                    "UPDATE invoices SET pdf_url = ? WHERE id = ?",
                    (pdf_url, invoice_id)
                )
                conn.commit()
                log.debug("PDF URL saved to SQLite invoices: INV-%d", invoice_id)
            except Exception as db_err:
                conn.rollback()
                log.warning("Could not save PDF URL to SQLite: %s", db_err)
            finally:
                conn.close()
    except ImportError:
        log.debug("_save_pdf_url_to_sqlite: database not importable in this context.")
    except Exception as e:
        log.warning("_save_pdf_url_to_sqlite error: %s", e)


def _queue_upload_for_retry(pdf_path: str, invoice_id: int) -> None:
    """
    Queue a failed / skipped Supabase upload in SQLite pending_syncs.
    """
    try:
        import json
        from database import queue_sync_operation  # type: ignore[import]
        payload = json.dumps({
            "filepath": pdf_path,
            "doc_type": "invoice",
            "doc_id":   str(invoice_id),
            "backend":  "supabase",
        })
        queue_sync_operation("supabase_pdf_upload", payload)
        log.info("PDF queued for Supabase retry: %s", os.path.basename(pdf_path))
    except Exception as e:
        log.error("Could not queue PDF for retry: %s", e)


def _sync_to_supabase(phone: str, invoice_id: int) -> None:
    """
    Sync customer and invoice records to Supabase PostgreSQL.
    Runs inside the background thread — failures are logged only.
    """
    try:
        from supabase_sync import sync_customer, sync_invoice  # type: ignore[import]
        from database import (                                  # type: ignore[import]
            get_customer, get_invoice, get_invoice_items
        )

        cust = get_customer(phone)
        if cust:
            sync_customer(dict(cust))

        inv   = get_invoice(invoice_id)
        items = get_invoice_items(invoice_id)
        if inv:
            sync_invoice(invoice_id, dict(inv), [dict(i) for i in items])

        log.debug("Supabase sync done for INV-%d", invoice_id)
    except Exception as e:
        log.warning("Supabase sync after invoice failed (non-fatal): %s", e)


# ══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════

def run_billing_workflow(
    phone: str,
    name: str,
    total: float,
    paid: float,
    balance: float,
    items: list,
    bill_type: str = "invoice",
    transport: float = 0.0,
    discount_pct: float = 0.0,
    discount_amt: float = 0.0,
    old_balance: float = 0.0,
    net_balance: float = 0.0,
    reference_phone: str = "",
    reference_name: str = "",
    payment_type: str = "Cash",
    skip_print: bool = False,
) -> tuple:
    """
    Execute the full 10-step automated billing workflow.

    STEP 1 (DB save) runs synchronously and is the only step that can
    abort the workflow (returns invoice_id=None on failure).

    STEPS 2-3 (PDF open + print) run synchronously so the file is
    printed before the UI dialog appears.

    STEPS 4-10 (Supabase upload + WhatsApp) run in a background daemon
    thread — the Tkinter UI returns immediately.

    Args:
        phone        : Customer phone number (10-digit Indian)
        name         : Customer name
        total        : Grand total (after discount + transport)
        paid         : Amount paid now
        balance      : Remaining balance (this invoice only)
        items        : List of item dicts [{product_name, qty, price, amount}, …]
        bill_type    : "invoice" or "quotation"
        transport    : Freight / transport charge
        discount_pct : Discount percentage
        discount_amt : Discount amount (calculated)
        old_balance  : Previous unpaid balance from customer record
        net_balance  : old_balance + balance (overall due after this payment)

    Returns:
        (invoice_id, pdf_path, error)
        - invoice_id is None only if Step 1 failed.
        - pdf_path may be None if PDF generation failed.
        - error is a string description of any Step 1 failure.
    """
    # ── STEP 1: Save invoice (MUST succeed) ──────────────
    invoice_id, pdf_path, error = _step_save_invoice(
        phone, name, total, paid, balance, items,
        bill_type, transport, discount_pct, discount_amt,
        old_balance, net_balance, reference_phone, payment_type
    )

    if invoice_id is None:
        # Hard failure — return immediately so UI can show error
        return None, None, error

    # ── STEP 2: Open PDF for review ──────────────────────
    if not skip_print and pdf_path and os.path.exists(pdf_path):
        _step_open_pdf(pdf_path)
        log.info("STEP 2 ✓ PDF opened: %s", os.path.basename(pdf_path))
    elif skip_print:
        log.info("STEP 2 skipped — already printed via preview.")
    else:
        log.warning("STEP 2 ✗ PDF not generated or missing.")

    # ── STEP 3: Queue print (background, non-blocking) ──
    if not skip_print and pdf_path and os.path.exists(pdf_path):
        try:
            from task_queue import add_task  # type: ignore[import]
            add_task("print_pdf", {"pdf_path": pdf_path})
            log.info("STEP 3: print_pdf task queued: %s", os.path.basename(pdf_path))
        except Exception as e:
            log.warning("STEP 3: Could not queue print task: %s", e)
    elif skip_print:
        log.info("STEP 3 skipped — already printed via preview.")

    # ── STEPS 4-10: Background thread ───────────────────
    bg = threading.Thread(
        target=_step_upload_and_whatsapp,
        args=(
            pdf_path, invoice_id,
            phone, name, total, paid, balance,
            old_balance, bill_type,
            reference_name, reference_phone, payment_type,
        ),
        daemon=True,
        name=f"billing-workflow-{invoice_id}",
    )
    bg.start()
    log.info(
        "Billing workflow background thread started for INV-%d.", invoice_id
    )

    return invoice_id, pdf_path, error
