"""
cloud_pull.py — Two-way sync, the "pull from Supabase" half
============================================================
NEW INDIAN STEEL Billing System

The existing supabase_sync.py pushes local SQLite changes UP to Supabase.
This module does the reverse: it pulls rows from Supabase DOWN into the
local SQLite cache so two PCs (shop + laptop) stay in sync via the cloud.

How it works
------------
- On startup, pull_all() runs once: fetches every row whose updated_at
  is newer than the last pull marker, upserts into local SQLite, and
  downloads any missing PDFs from Storage.
- A background daemon thread then re-runs pull_all() every PULL_INTERVAL
  seconds (default 15). The Tkinter UI is never blocked.
- Per-table "last pull" timestamps are persisted to disk in a small
  JSON state file so we don't refetch the entire table every poll.

Conflict policy
---------------
Last write wins, decided by updated_at. The push code in supabase_sync
sets updated_at to NOW() on every upsert; the cloud trigger does the
same on every UPDATE. So whichever PC made the most recent edit owns
the row globally.

What can go wrong
-----------------
- Local SQLite uses auto-increment INTEGER ids; cloud stores them as
  TEXT. If both PCs create a NEW invoice at the same time they may both
  pick the same local id (e.g. 5) and clash in cloud. The probability
  is low because the two PCs almost never bill simultaneously, but
  documented as a known limitation.
- Deletes are not synced. If you delete a customer on one PC, the
  other PC will resurrect them on its next pull. Use the cloud DB
  console for permanent deletes.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from logger import get_logger

log = get_logger(__name__)

PULL_INTERVAL = 15          # seconds between polls — catches changes within ~15s
PDF_DOWNLOAD_TIMEOUT = 15   # seconds per PDF
EPOCH = "1970-01-01T00:00:00+00:00"


def _is_cloud_newer(local_ts: str, cloud_ts: str) -> bool:
    """Return True only if cloud timestamp is strictly newer than local.
    Normalises both strings so format differences (T vs space, +00:00 vs +00)
    don't cause the cloud to falsely win."""
    l = (local_ts or "").strip().replace(" ", "T").rstrip("Z")
    c = (cloud_ts or "").strip().replace(" ", "T").rstrip("Z")
    # Strip trailing :00 timezone suffix differences: +00:00 → +00
    for suffix in ("+00:00", "-00:00"):
        if l.endswith(suffix): l = l[:-3]
        if c.endswith(suffix): c = c[:-3]
    return c > l and bool(c)


# ════════════════════════════════════════════════════════════
# CLIENT + STATE
# ════════════════════════════════════════════════════════════

_client = None
_ready  = False


def _get_client():
    """Reuse the same Supabase client supabase_sync uses."""
    global _client, _ready
    if _ready:
        return _client
    if _client is False:
        return None
    try:
        from config import SUPABASE_URL, SUPABASE_KEY
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.info("cloud_pull: SUPABASE_URL/KEY not set — pull disabled.")
            _client = False
            return None
        from supabase import create_client
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _ready  = True
        log.info("cloud_pull: connected to Supabase.")
        return _client
    except Exception as e:
        log.warning("cloud_pull: client init failed (%s) — pull disabled.", e)
        _client = False
        return None


def _state_path() -> Path:
    """Where we remember per-table last-pull timestamps."""
    from config import BASE_DIR
    return Path(BASE_DIR) / "cloud_pull_state.json"


def _load_state() -> dict:
    p = _state_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        log.warning("cloud_pull: state file unreadable (%s) — starting fresh.", e)
        return {}


def _save_state(state: dict) -> None:
    try:
        _state_path().write_text(json.dumps(state, indent=2))
    except Exception as e:
        log.warning("cloud_pull: could not save state: %s", e)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ════════════════════════════════════════════════════════════
# LOCAL UPSERT HELPERS
# ════════════════════════════════════════════════════════════

def _upsert_customer(row: dict) -> None:
    """Insert or update a single customer row from cloud."""
    from database import get_conn, _write_lock
    phone = row.get("phone")
    if not phone:
        return
    name            = row.get("name") or ""
    address         = row.get("address") or ""
    total_due       = float(row.get("total_due") or 0)
    opening_balance = float(row.get("opening_balance") or 0)
    updated_at      = row.get("updated_at") or _now_iso()

    with _write_lock:
        conn = get_conn()
        try:
            existing = conn.execute(
                "SELECT updated_at FROM customers WHERE phone=?", (phone,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO customers "
                    "(name, phone, address, total_due, opening_balance, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (name, phone, address, total_due, opening_balance, updated_at),
                )
            else:
                # Last write wins: only update if cloud is newer
                if _is_cloud_newer(existing["updated_at"], updated_at):
                    conn.execute(
                        "UPDATE customers SET name=?, address=?, total_due=?, "
                        "opening_balance=?, updated_at=? WHERE phone=?",
                        (name, address, total_due, opening_balance, updated_at, phone),
                    )
            conn.commit()
        finally:
            conn.close()


def _has_column(conn, table: str, column: str) -> bool:
    """Check if a column exists in a local SQLite table."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _upsert_invoice(row: dict) -> None:
    """Insert or update a single invoice row from cloud."""
    from database import get_conn, _write_lock
    try:
        invoice_id = int(row.get("id"))
    except (TypeError, ValueError):
        return
    updated_at      = row.get("updated_at") or _now_iso()
    customer_phone  = row.get("customer_phone") or ""
    date            = row.get("date") or ""
    total           = float(row.get("total") or 0)
    paid            = float(row.get("paid") or 0)
    balance         = float(row.get("balance") or 0)
    inv_type        = row.get("type") or "invoice"
    pdf_url         = row.get("pdf_url") or ""
    reference_phone = row.get("reference_phone") or ""

    with _write_lock:
        conn = get_conn()
        try:
            has_ua  = _has_column(conn, "invoices", "updated_at")
            has_ref = _has_column(conn, "invoices", "reference_phone")

            if has_ua:
                existing = conn.execute(
                    "SELECT updated_at FROM invoices WHERE id=?", (invoice_id,)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM invoices WHERE id=?", (invoice_id,)
                ).fetchone()

            def _ref_cols():
                return (", reference_phone" if has_ref else "")
            def _ref_vals():
                return ((reference_phone,) if has_ref else ())

            if existing is None:
                if has_ua:
                    conn.execute(
                        "INSERT INTO invoices (id, customer_phone, date, total, paid, "
                        f"balance, type, pdf_url, updated_at{_ref_cols()}) "
                        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?{', ?' if has_ref else ''})",
                        (invoice_id, customer_phone, date, total, paid,
                         balance, inv_type, pdf_url, updated_at) + _ref_vals(),
                    )
                else:
                    conn.execute(
                        "INSERT INTO invoices (id, customer_phone, date, total, paid, "
                        f"balance, type, pdf_url{_ref_cols()}) "
                        f"VALUES (?, ?, ?, ?, ?, ?, ?, ?{', ?' if has_ref else ''})",
                        (invoice_id, customer_phone, date, total, paid,
                         balance, inv_type, pdf_url) + _ref_vals(),
                    )
            else:
                local_ua = existing["updated_at"] if has_ua else ""
                if (local_ua or "") < updated_at:
                    if has_ua:
                        conn.execute(
                            "UPDATE invoices SET customer_phone=?, date=?, total=?, "
                            f"paid=?, balance=?, type=?, pdf_url=?, updated_at=?"
                            f"{', reference_phone=?' if has_ref else ''} WHERE id=?",
                            (customer_phone, date, total, paid, balance,
                             inv_type, pdf_url, updated_at) + _ref_vals() + (invoice_id,),
                        )
                    else:
                        conn.execute(
                            "UPDATE invoices SET customer_phone=?, date=?, total=?, "
                            f"paid=?, balance=?, type=?, pdf_url=?"
                            f"{', reference_phone=?' if has_ref else ''} WHERE id=?",
                            (customer_phone, date, total, paid, balance,
                             inv_type, pdf_url) + _ref_vals() + (invoice_id,),
                        )
            conn.commit()
        finally:
            conn.close()


def _upsert_invoice_item(row: dict) -> None:
    """Insert or update a single invoice_item row from cloud.
    Uses product_name as the stable key (Supabase key), stores it locally
    so items survive even when product_id can't be resolved.
    """
    from database import get_conn, _write_lock
    try:
        invoice_id = int(row.get("invoice_id"))
    except (TypeError, ValueError):
        return
    product_name = row.get("product_name") or ""
    qty    = float(row.get("qty") or 0)
    price  = float(row.get("price") or 0)
    amount = float(row.get("amount") or 0)
    updated_at = row.get("updated_at") or _now_iso()

    if not product_name:
        return  # nothing to store without a name

    with _write_lock:
        conn = get_conn()
        try:
            has_ua    = _has_column(conn, "invoice_items", "updated_at")
            has_pname = _has_column(conn, "invoice_items", "product_name")

            # Resolve product_id (case-insensitive); 0 if not found — OK
            pid_row = conn.execute(
                "SELECT id FROM products WHERE LOWER(name)=LOWER(?)", (product_name,)
            ).fetchone()
            product_id = pid_row["id"] if pid_row else 0

            # Look up by product_name (stable) if column exists, else by product_id
            if has_pname:
                existing = conn.execute(
                    "SELECT id, updated_at FROM invoice_items "
                    "WHERE invoice_id=? AND LOWER(product_name)=LOWER(?)",
                    (invoice_id, product_name),
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id, updated_at FROM invoice_items "
                    "WHERE invoice_id=? AND product_id=?",
                    (invoice_id, product_id),
                ).fetchone()

            if existing is None:
                if has_pname and has_ua:
                    conn.execute(
                        "INSERT INTO invoice_items "
                        "(invoice_id, product_id, product_name, qty, price, amount, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (invoice_id, product_id, product_name, qty, price, amount, updated_at),
                    )
                elif has_pname:
                    conn.execute(
                        "INSERT INTO invoice_items "
                        "(invoice_id, product_id, product_name, qty, price, amount) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (invoice_id, product_id, product_name, qty, price, amount),
                    )
                else:
                    conn.execute(
                        "INSERT INTO invoice_items "
                        "(invoice_id, product_id, qty, price, amount) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (invoice_id, product_id, qty, price, amount),
                    )
            else:
                local_ua = (existing["updated_at"] if has_ua else "") or ""
                if local_ua < updated_at:
                    if has_pname and has_ua:
                        conn.execute(
                            "UPDATE invoice_items SET product_id=?, product_name=?, "
                            "qty=?, price=?, amount=?, updated_at=? WHERE id=?",
                            (product_id, product_name, qty, price, amount,
                             updated_at, existing["id"]),
                        )
                    elif has_ua:
                        conn.execute(
                            "UPDATE invoice_items SET qty=?, price=?, amount=?, "
                            "updated_at=? WHERE id=?",
                            (qty, price, amount, updated_at, existing["id"]),
                        )
                    else:
                        conn.execute(
                            "UPDATE invoice_items SET qty=?, price=?, amount=? WHERE id=?",
                            (qty, price, amount, existing["id"]),
                        )
            conn.commit()
        finally:
            conn.close()


def _upsert_payment(row: dict) -> None:
    from database import get_conn, _write_lock
    try:
        pay_id = int(row.get("id"))
    except (TypeError, ValueError):
        return
    updated_at = row.get("updated_at") or _now_iso()
    phone  = row.get("customer_phone") or ""
    amount = float(row.get("amount") or 0)
    date   = row.get("date") or ""

    with _write_lock:
        conn = get_conn()
        try:
            has_ua = _has_column(conn, "payments", "updated_at")
            if has_ua:
                existing = conn.execute(
                    "SELECT updated_at FROM payments WHERE id=?", (pay_id,)
                ).fetchone()
            else:
                existing = conn.execute(
                    "SELECT id FROM payments WHERE id=?", (pay_id,)
                ).fetchone()

            if existing is None:
                if has_ua:
                    conn.execute(
                        "INSERT INTO payments (id, customer_phone, amount, date, updated_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (pay_id, phone, amount, date, updated_at),
                    )
                else:
                    conn.execute(
                        "INSERT INTO payments (id, customer_phone, amount, date) "
                        "VALUES (?, ?, ?, ?)",
                        (pay_id, phone, amount, date),
                    )
            else:
                local_ua = existing["updated_at"] if has_ua else ""
                if (local_ua or "") < updated_at:
                    if has_ua:
                        conn.execute(
                            "UPDATE payments SET customer_phone=?, amount=?, date=?, "
                            "updated_at=? WHERE id=?",
                            (phone, amount, date, updated_at, pay_id),
                        )
                    else:
                        conn.execute(
                            "UPDATE payments SET customer_phone=?, amount=?, date=? "
                            "WHERE id=?",
                            (phone, amount, date, pay_id),
                        )
            conn.commit()
        finally:
            conn.close()


# ════════════════════════════════════════════════════════════
# TABLE PULL FUNCTIONS
# ════════════════════════════════════════════════════════════

def _pull_table(table: str, upsert_fn, state: dict) -> int:
    """Pull rows from `table` updated since the saved marker.

    Returns count of rows upserted locally."""
    client = _get_client()
    if not client:
        return 0
    last = state.get(table, EPOCH)
    try:
        # Supabase REST: WHERE updated_at > last, ORDER BY updated_at ASC
        res = (client.table(table)
                     .select("*")
                     .gt("updated_at", last)
                     .order("updated_at", desc=False)
                     .limit(500)
                     .execute())
    except Exception as e:
        log.warning("cloud_pull: select from %s failed: %s", table, e)
        return 0
    rows = res.data or []
    if not rows:
        return 0
    newest = last
    for r in rows:
        try:
            upsert_fn(r)
            if r.get("updated_at") and r["updated_at"] > newest:
                newest = r["updated_at"]
        except Exception as e:
            log.warning("cloud_pull: upsert %s row failed: %s", table, e)
    state[table] = newest
    log.info("cloud_pull: %s pulled %d row(s); marker -> %s",
             table, len(rows), newest)
    return len(rows)


def pull_customers(state: dict) -> int:
    return _pull_table("customers", _upsert_customer, state)


def pull_invoices(state: dict) -> int:
    return _pull_table("invoices", _upsert_invoice, state)


def pull_invoice_items(state: dict) -> int:
    return _pull_table("invoice_items", _upsert_invoice_item, state)


def pull_payments(state: dict) -> int:
    return _pull_table("payments", _upsert_payment, state)


def _upsert_product(row: dict) -> None:
    """Insert or update a single product row from cloud."""
    from database import get_conn, _write_lock
    try:
        product_id = int(row.get("id"))
    except (TypeError, ValueError):
        return
    name       = row.get("name") or ""
    price      = float(row.get("price") or 0)
    unit       = row.get("unit") or "Nos"
    updated_at = row.get("updated_at") or _now_iso()

    with _write_lock:
        conn = get_conn()
        try:
            existing = conn.execute(
                "SELECT updated_at FROM products WHERE id=?", (product_id,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO products (id, name, price, unit, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (product_id, name, price, unit, updated_at),
                )
            else:
                if _is_cloud_newer(existing["updated_at"], updated_at):
                    conn.execute(
                        "UPDATE products SET name=?, price=?, unit=?, updated_at=? "
                        "WHERE id=?",
                        (name, price, unit, updated_at, product_id),
                    )
            conn.commit()
        finally:
            conn.close()


def pull_products(state: dict) -> int:
    return _pull_table("products", _upsert_product, state)


# ════════════════════════════════════════════════════════════
# PDF DOWNLOAD
# ════════════════════════════════════════════════════════════

def download_missing_pdfs() -> int:
    """Download any invoice PDF whose URL is in cloud but the local file
    is missing from INVOICES_DIR. Returns count of files downloaded."""
    from config import INVOICES_DIR
    from database import _execute_read
    rows = _execute_read(
        "SELECT id, pdf_url FROM invoices WHERE pdf_url IS NOT NULL AND pdf_url <> ''"
    )
    count = 0
    for row in rows:
        url = row["pdf_url"]
        # Use the URL's basename as the local filename
        basename = os.path.basename(url.split("?", 1)[0])
        if not basename or not basename.lower().endswith(".pdf"):
            continue
        local = os.path.join(INVOICES_DIR, basename)
        if os.path.exists(local):
            continue
        try:
            os.makedirs(INVOICES_DIR, exist_ok=True)
            req = urllib.request.Request(url, headers={"User-Agent": "NIS/1.0"})
            with urllib.request.urlopen(req, timeout=PDF_DOWNLOAD_TIMEOUT) as r, \
                 open(local, "wb") as out:
                out.write(r.read())
            count += 1
            log.info("cloud_pull: downloaded %s", basename)
        except Exception as e:
            log.warning("cloud_pull: PDF download failed for INV-%s (%s): %s",
                        row["id"], url, e)
    if count:
        log.info("cloud_pull: %d PDF(s) downloaded.", count)
    return count


# ════════════════════════════════════════════════════════════
# TOP-LEVEL pull_all + recompute
# ════════════════════════════════════════════════════════════

def _recompute_all_customer_dues() -> None:
    """After pulling invoices and payments, customer.total_due may be
    out of sync. Recompute from source-of-truth: opening_balance +
    sum(invoice balances) - sum(payments). Skipped silently if any
    expected column is missing on older schemas."""
    from database import get_conn, _write_lock
    with _write_lock:
        conn = get_conn()
        try:
            conn.execute("""
                UPDATE customers
                   SET total_due = COALESCE(opening_balance, 0)
                       + COALESCE((SELECT SUM(balance) FROM invoices
                                    WHERE customer_phone = customers.phone
                                      AND LOWER(type)='invoice'), 0)
                       - COALESCE((SELECT SUM(amount) FROM payments
                                    WHERE customer_phone = customers.phone), 0)
            """)
            conn.commit()
        except Exception as e:
            log.debug("recompute customer dues skipped: %s", e)
        finally:
            conn.close()


def pull_all() -> dict:
    """Run one full pull cycle. Safe to call from any thread."""
    if not _get_client():
        return {"products": 0, "customers": 0, "invoices": 0,
                "invoice_items": 0, "payments": 0, "pdfs": 0}

    state = _load_state()
    counts = {
        "products":      pull_products(state),
        "customers":     pull_customers(state),
        "invoices":      pull_invoices(state),
        "invoice_items": pull_invoice_items(state),
        "payments":      pull_payments(state),
        "pdfs":          download_missing_pdfs(),
    }
    _save_state(state)

    if counts["invoices"] or counts["payments"]:
        _recompute_all_customer_dues()

    total = sum(counts.values())
    if total:
        log.info("cloud_pull: pull_all done — %s", counts)
    return counts


# ════════════════════════════════════════════════════════════
# BACKGROUND WORKER
# ════════════════════════════════════════════════════════════

_worker_thread = None
_running = False
_running_lock = threading.Lock()


def start_pull_worker(interval: int = PULL_INTERVAL,
                      initial_delay: int = 0) -> None:
    """Start a daemon thread that pulls every `interval` seconds.
    `initial_delay` postpones the very first pull so a startup push can
    finish first — prevents cloud from overwriting freshly-edited local data.
    Safe to call multiple times; only one worker ever runs."""
    global _worker_thread, _running
    with _running_lock:
        if _running and _worker_thread and _worker_thread.is_alive():
            return
        _running = True

    def _loop():
        log.info("cloud_pull worker started (interval=%ds, initial_delay=%ds).",
                 interval, initial_delay)
        if initial_delay > 0:
            time.sleep(initial_delay)
        try:
            pull_all()
        except Exception as e:
            log.error("cloud_pull initial pull error: %s", e, exc_info=True)
        while True:
            with _running_lock:
                if not _running:
                    break
            time.sleep(interval)
            try:
                pull_all()
            except Exception as e:
                log.error("cloud_pull loop error: %s", e, exc_info=True)
        log.info("cloud_pull worker exited.")

    _worker_thread = threading.Thread(target=_loop, daemon=True,
                                       name="cloud-pull-worker")
    _worker_thread.start()


def stop_pull_worker() -> None:
    global _running
    with _running_lock:
        _running = False
