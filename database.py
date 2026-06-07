"""
SQLite Database — Thread-safe CRUD with concurrency protection.
================================================================
All write operations are serialized through a threading.Lock to prevent
"database is locked" errors from concurrent UI / sync / backup threads.

Read operations use check_same_thread=False and WAL journal mode for
safe concurrent reads without blocking.
"""
import sqlite3
import threading
import time
from datetime import datetime
from config import DB_PATH
from logger import get_logger

log = get_logger(__name__)

# ── Global write lock — serializes all DB mutations ──────
_write_lock = threading.Lock()

# ── Maximum retries on SQLITE_BUSY ───────────────────────
_MAX_RETRIES = 3
_RETRY_DELAY = 0.2  # seconds


def get_conn():
    """Get a database connection with Row factory and WAL mode.
    Uses check_same_thread=False for safe cross-thread reads."""
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _execute_read(sql, params=()):
    """Execute a read query with retry on busy. Returns list of Row."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            conn = get_conn()
            try:
                rows = conn.execute(sql, params).fetchall()
                return rows
            finally:
                conn.close()
        except sqlite3.OperationalError as e:
            if "locked" in str(e) and attempt < _MAX_RETRIES:
                log.warning("DB read locked (attempt %d/%d), retrying...",
                            attempt, _MAX_RETRIES)
                time.sleep(_RETRY_DELAY * attempt)
            else:
                log.error("DB read failed: %s", e, exc_info=True)
                raise


def _execute_read_one(sql, params=()):
    """Execute a read query returning a single Row or None."""
    rows = _execute_read(sql, params)
    return rows[0] if rows else None


def _execute_write(func):
    """Decorator: acquire write lock, create connection, call func(conn),
    commit on success, rollback on failure. Retries on busy."""
    def wrapper(*args, **kwargs):
        with _write_lock:
            for attempt in range(1, _MAX_RETRIES + 1):
                conn = get_conn()
                try:
                    result = func(conn, *args, **kwargs)
                    conn.commit()
                    return result
                except sqlite3.OperationalError as e:
                    conn.rollback()
                    if "locked" in str(e) and attempt < _MAX_RETRIES:
                        log.warning("DB write locked (attempt %d/%d), retrying...",
                                    attempt, _MAX_RETRIES)
                        time.sleep(_RETRY_DELAY * attempt)
                    else:
                        log.error("DB write failed: %s", e, exc_info=True)
                        raise
                except Exception as e:
                    conn.rollback()
                    log.error("DB write error: %s", e, exc_info=True)
                    raise
                finally:
                    conn.close()
    return wrapper


# ══════════════════════════════════════════════════════════
# DATABASE INITIALIZATION
# ══════════════════════════════════════════════════════════

def init_database():
    """Create all tables and insert sample products."""
    with _write_lock:
        conn = get_conn()
        try:
            c = conn.cursor()

            c.execute('''CREATE TABLE IF NOT EXISTS customers (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT    NOT NULL,
                phone TEXT    UNIQUE NOT NULL,
                total_due REAL DEFAULT 0.0
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS products (
                id    INTEGER PRIMARY KEY AUTOINCREMENT,
                name  TEXT    NOT NULL,
                price REAL    NOT NULL
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS invoices (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_phone TEXT NOT NULL,
                date           TEXT NOT NULL,
                total          REAL NOT NULL,
                paid           REAL DEFAULT 0.0,
                balance        REAL NOT NULL,
                synced         INTEGER DEFAULT 0,
                type           TEXT DEFAULT 'invoice',
                FOREIGN KEY (customer_phone) REFERENCES customers(phone)
            )''')
            # Safe ALTER TABLE — only if column doesn't exist
            existing_cols = [row[1] for row in c.execute("PRAGMA table_info(invoices)")]
            if "type" not in existing_cols:
                c.execute("ALTER TABLE invoices ADD COLUMN type TEXT DEFAULT 'invoice'")

            c.execute('''CREATE TABLE IF NOT EXISTS invoice_items (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                qty        INTEGER NOT NULL,
                price      REAL    NOT NULL,
                amount     REAL    NOT NULL,
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS payments (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_phone TEXT NOT NULL,
                amount         REAL NOT NULL,
                date           TEXT NOT NULL,
                synced         INTEGER DEFAULT 0,
                FOREIGN KEY (customer_phone) REFERENCES customers(phone)
            )''')

            c.execute('''CREATE TABLE IF NOT EXISTS pending_syncs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                operation   TEXT    NOT NULL,
                payload     TEXT    NOT NULL,
                retry_count INTEGER DEFAULT 0,
                created_at  TEXT    NOT NULL,
                last_tried  TEXT
            )''')

            # Insert sample products if table is empty
            if c.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
                samples = [
                    ("TMT Bar 8mm (per kg)", 65.00),
                    ("TMT Bar 10mm (per kg)", 64.00),
                    ("TMT Bar 12mm (per kg)", 63.00),
                    ("MS Angle 25x25 (per kg)", 58.00),
                    ("MS Angle 50x50 (per kg)", 57.00),
                    ("MS Channel (per kg)", 60.00),
                    ("GI Pipe 1 inch (per pc)", 350.00),
                    ("GI Pipe 1.5 inch (per pc)", 520.00),
                    ("GI Sheet 22G (per pc)", 480.00),
                    ("Binding Wire (per kg)", 75.00),
                    ("MS Flat Bar (per kg)", 55.00),
                    ("MS Round Bar (per kg)", 58.00),
                ]
                c.executemany("INSERT INTO products (name, price) VALUES (?, ?)", samples)

            conn.commit()
            log.info("Database initialized successfully.")
        except Exception as e:
            conn.rollback()
            log.critical("Database initialization failed: %s", e, exc_info=True)
            raise
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════
# CUSTOMER OPERATIONS
# ══════════════════════════════════════════════════════════

def get_customer(phone):
    """Get customer by phone number. Returns dict or None."""
    row = _execute_read_one("SELECT * FROM customers WHERE phone = ?", (phone,))
    return dict(row) if row else None


def get_customer_by_id(customer_id: int):
    """Get customer by integer ID. Returns dict or None."""
    row = _execute_read_one("SELECT * FROM customers WHERE id = ?", (int(customer_id),))
    return dict(row) if row else None


def find_customer(query: str):
    """
    Flexible customer lookup — accepts:
      - 10-digit phone number  → exact phone match
      - short integer string   → match by customer ID
      - anything else          → name LIKE search (returns first match)
    Returns a customer dict or None.
    """
    q = query.strip()
    if not q:
        return None
    # Customer ID: short number (1-6 digits, not starting with 6/7/8/9 at length 10)
    if q.isdigit() and len(q) <= 6:
        return get_customer_by_id(int(q))
    # Phone number: exactly 10 digits
    if q.isdigit() and len(q) == 10:
        return get_customer(q)
    # Name search: first match
    row = _execute_read_one(
        "SELECT * FROM customers WHERE LOWER(name) LIKE LOWER(?) ORDER BY name LIMIT 1",
        (f"%{q}%",))
    return dict(row) if row else None


@_execute_write
def create_customer(conn, name, phone, address="", opening_balance=0.0):
    """
    Create a new customer with optional address and opening balance.
    Sets total_due = opening_balance so the running due starts correctly.
    """
    ob = max(0.0, float(opening_balance))   # Never allow negative
    conn.execute(
        "INSERT INTO customers (name, phone, address, opening_balance, total_due) "
        "VALUES (?, ?, ?, ?, ?)",
        (name.strip(), phone.strip(), address.strip(), ob, ob)
    )
    log.info("Customer created: %s (%s) opening_balance=%.2f", name, phone, ob)


@_execute_write
def update_customer(conn, phone, name, address="", opening_balance=0.0):
    """
    Edit an existing customer's name, address, and opening balance.
    When opening_balance changes, total_due is recomputed as:
        opening_balance + SUM(invoice balances) - SUM(payments)
    so the running due stays accurate.
    """
    ob = max(0.0, float(opening_balance))   # Never allow negative
    conn.execute(
        "UPDATE customers SET name=?, address=?, opening_balance=? WHERE phone=?",
        (name.strip(), address.strip(), ob, phone)
    )
    # Recompute total_due from source-of-truth records
    inv_bal = conn.execute(
        "SELECT COALESCE(SUM(balance), 0) FROM invoices "
        "WHERE customer_phone=? AND LOWER(type)='invoice'", (phone,)
    ).fetchone()[0]
    pay_total = conn.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE customer_phone=?", (phone,)
    ).fetchone()[0]
    new_due = ob + inv_bal - pay_total
    conn.execute(
        "UPDATE customers SET total_due=? WHERE phone=?", (new_due, phone)
    )
    log.info("Customer updated: phone=%s name=%s opening_balance=%.2f new_due=%.2f",
             phone, name, ob, new_due)


def get_or_create_customer(name, phone, address="", opening_balance=0.0):
    """Get existing customer or create new one. Returns customer dict."""
    c = get_customer(phone)
    if c:
        return c
    create_customer(name, phone, address, opening_balance)
    return get_customer(phone)


# Special fixed phone for walk-in / cash customers (no account tracking)
WALKIN_PHONE = "0000000000"

def get_or_create_walkin_customer():
    """
    Return the internal Walk-in / Cash Customer record.
    Created automatically on first use. Balance is never shown to anyone.
    Phone is '0000000000' — excluded from customer lists.
    """
    c = get_customer(WALKIN_PHONE)
    if not c:
        try:
            create_customer("Walk-in Customer", WALKIN_PHONE, "", 0.0)
        except Exception:
            pass
        c = get_customer(WALKIN_PHONE)
    return c


@_execute_write
def update_customer_due(conn, phone, amount_change):
    """Add (positive) or subtract (negative) from customer total_due."""
    conn.execute("UPDATE customers SET total_due = total_due + ? WHERE phone = ?",
                 (amount_change, phone))


def get_computed_due(phone):
    """
    Compute current due from source of truth:
        opening_balance + SUM(invoice balances) - SUM(payments)
    Returns float.
    """
    row = _execute_read_one(
        "SELECT opening_balance FROM customers WHERE phone=?", (phone,)
    )
    if not row:
        return 0.0
    ob = row["opening_balance"] or 0.0

    inv_bal = _execute_read_one(
        "SELECT COALESCE(SUM(balance), 0) AS s FROM invoices "
        "WHERE customer_phone=? AND LOWER(type)='invoice'", (phone,)
    )
    pay_total = _execute_read_one(
        "SELECT COALESCE(SUM(amount), 0) AS s FROM payments WHERE customer_phone=?",
        (phone,)
    )
    result = ob + (inv_bal["s"] if inv_bal else 0.0) - (pay_total["s"] if pay_total else 0.0)
    return round(result, 2)


def get_all_customers():
    """Return all customers ordered by name. Excludes the Walk-in internal account."""
    rows = _execute_read(
        "SELECT * FROM customers WHERE phone != ? ORDER BY name",
        (WALKIN_PHONE,))
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════
# PRODUCT OPERATIONS
# ══════════════════════════════════════════════════════════

def get_product(product_id):
    """Get product by ID. Returns dict or None."""
    row = _execute_read_one("SELECT * FROM products WHERE id = ?", (product_id,))
    return dict(row) if row else None


def get_all_products():
    rows = _execute_read("SELECT * FROM products ORDER BY id")
    return [dict(r) for r in rows]


def search_products(query):
    """Search products by name using LIKE. Returns list of dicts
    sorted by relevance: exact prefix matches first, then contains."""
    if not query or not query.strip():
        return get_all_products()
    q = query.strip()
    # Fetch all matches — prefix matches come first via ORDER BY
    rows = _execute_read(
        """SELECT *, 
               CASE WHEN LOWER(name) LIKE LOWER(? || '%') THEN 0 ELSE 1 END AS rank
           FROM products 
           WHERE LOWER(name) LIKE LOWER(?)
           ORDER BY rank, name
           LIMIT 20""",
        (q, f"%{q}%"))
    return [dict(r) for r in rows]


@_execute_write
def add_product(conn, name, price, unit="Nos"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO products (name, price, unit, updated_at) VALUES (?, ?, ?, ?)",
        (name, price, unit, now))
    log.info("Product added: %s @ %.2f (%s)", name, price, unit)


@_execute_write
def update_product(conn, product_id, name, price, unit="Nos"):
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE products SET name = ?, price = ?, unit = ?, updated_at = ? WHERE id = ?",
        (name, price, unit, now, product_id))
    log.info("Product #%s updated: %s @ %.2f (%s)",
             product_id, name, price, unit)


@_execute_write
def delete_product(conn, product_id):
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    log.info("Product #%s deleted.", product_id)


# ══════════════════════════════════════════════════════════
# DELETE OPERATIONS (invoice / payment / customer)
# All push the delete to Supabase so cloud_pull won't resurrect them.
# ══════════════════════════════════════════════════════════

def _cloud_delete(table: str, key_col: str, key_val) -> None:
    """Best-effort delete on Supabase. Silent on failure."""
    try:
        from supabase_sync import _get_client  # type: ignore[import]
        client = _get_client()
        if client:
            client.table(table).delete().eq(key_col, str(key_val)).execute()
            log.debug("Cloud delete %s where %s=%s", table, key_col, key_val)
    except Exception as e:
        log.warning("Cloud delete failed (%s): %s", table, e)


def delete_invoice(invoice_id: int) -> bool:
    """Delete an invoice + its items, reverse the customer balance change.

    Cascades to Supabase so the pull worker won't resurrect it.
    Returns True on success.
    """
    with _write_lock:
        conn = get_conn()
        try:
            inv = conn.execute(
                "SELECT customer_phone, balance, type FROM invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            if not inv:
                log.warning("delete_invoice: INV-%s not found.", invoice_id)
                return False
            phone   = inv["customer_phone"]
            balance = float(inv["balance"] or 0)
            kind    = (inv["type"] or "invoice").lower()

            conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (invoice_id,))
            conn.execute("DELETE FROM invoices      WHERE id=?",         (invoice_id,))

            # Reverse the customer's running due for actual invoices only
            if kind == "invoice":
                conn.execute(
                    "UPDATE customers SET total_due = total_due - ? WHERE phone=?",
                    (balance, phone),
                )
            conn.commit()
            log.info("Invoice INV-%d deleted (phone=%s, reversed=%.2f).",
                     invoice_id, phone, balance)
        except Exception as e:
            conn.rollback()
            log.error("delete_invoice failed: %s", e, exc_info=True)
            return False
        finally:
            conn.close()

    # Push delete to cloud so pull doesn't resurrect
    _cloud_delete("invoice_items", "invoice_id", invoice_id)
    _cloud_delete("invoices",      "id",         invoice_id)
    return True


def confirm_draft_invoice(invoice_id: int) -> tuple:
    """
    Convert a draft invoice into a real invoice.

    - Changes type from 'draft' → 'invoice'
    - Adds the invoice balance to the customer's running due
    - Stamps updated_at so cloud sync picks it up

    Returns (True, message) on success, (False, error) on failure.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    with _write_lock:
        conn = get_conn()
        try:
            inv = conn.execute(
                "SELECT customer_phone, balance, type FROM invoices WHERE id=?",
                (invoice_id,),
            ).fetchone()
            if not inv:
                return False, f"Invoice #{invoice_id} not found."
            kind = (inv["type"] or "").lower()
            if kind != "draft":
                return False, f"Invoice #{invoice_id} is already a '{kind}', not a draft."
            phone   = inv["customer_phone"]
            balance = float(inv["balance"] or 0)

            conn.execute(
                "UPDATE invoices SET type='invoice', updated_at=? WHERE id=?",
                (now, invoice_id),
            )
            conn.execute(
                "UPDATE customers SET total_due = total_due + ? WHERE phone=?",
                (balance, phone),
            )
            conn.commit()
            log.info("Draft INV-%d confirmed as invoice (phone=%s, balance=%.2f).",
                     invoice_id, phone, balance)
            return True, f"Invoice #{invoice_id} confirmed. ₹{balance:,.2f} added to customer balance."
        except Exception as e:
            conn.rollback()
            log.error("confirm_draft_invoice failed: %s", e, exc_info=True)
            return False, str(e)
        finally:
            conn.close()


def delete_payment(payment_id: int) -> bool:
    """Delete a payment and add the amount back to the customer's due."""
    with _write_lock:
        conn = get_conn()
        try:
            pay = conn.execute(
                "SELECT customer_phone, amount FROM payments WHERE id=?",
                (payment_id,),
            ).fetchone()
            if not pay:
                log.warning("delete_payment: PAY-%s not found.", payment_id)
                return False
            phone  = pay["customer_phone"]
            amount = float(pay["amount"] or 0)

            conn.execute("DELETE FROM payments WHERE id=?", (payment_id,))
            conn.execute(
                "UPDATE customers SET total_due = total_due + ? WHERE phone=?",
                (amount, phone),
            )
            conn.commit()
            log.info("Payment PAY-%d deleted (phone=%s, restored=%.2f).",
                     payment_id, phone, amount)
        except Exception as e:
            conn.rollback()
            log.error("delete_payment failed: %s", e, exc_info=True)
            return False
        finally:
            conn.close()

    _cloud_delete("payments", "id", payment_id)
    return True


def delete_customer(phone: str) -> tuple:
    """Delete a customer. Refuses if they have any invoices or payments.

    Returns (ok: bool, message: str).
    """
    with _write_lock:
        conn = get_conn()
        try:
            inv_n = conn.execute(
                "SELECT COUNT(*) AS n FROM invoices WHERE customer_phone=?",
                (phone,),
            ).fetchone()["n"]
            pay_n = conn.execute(
                "SELECT COUNT(*) AS n FROM payments WHERE customer_phone=?",
                (phone,),
            ).fetchone()["n"]
            if inv_n or pay_n:
                msg = (f"Cannot delete: customer has {inv_n} invoice(s) and "
                       f"{pay_n} payment(s). Delete those first.")
                log.info("delete_customer refused for %s: %s", phone, msg)
                return False, msg

            cust = conn.execute(
                "SELECT id FROM customers WHERE phone=?", (phone,)
            ).fetchone()
            if not cust:
                return False, f"Customer {phone} not found."

            conn.execute("DELETE FROM customers WHERE phone=?", (phone,))
            conn.commit()
            log.info("Customer %s deleted.", phone)
        except Exception as e:
            conn.rollback()
            log.error("delete_customer failed: %s", e, exc_info=True)
            return False, str(e)
        finally:
            conn.close()

    _cloud_delete("customers", "phone", phone)
    return True, "Deleted."


# ══════════════════════════════════════════════════════════
# INVOICE OPERATIONS — ATOMIC TRANSACTION
# ══════════════════════════════════════════════════════════

def create_invoice(customer_phone, total, paid, balance, items,
                   type="invoice", reference_phone="", payment_type="Cash"):
    """
    Create invoice with items in a single atomic transaction.
    items = list of dicts:
      [{"product_id": 1, "qty": 10, "price": 550.0, "amount": 5500.0}, ...]
    reference_phone: phone of the customer who referred this sale (optional).
    Returns the invoice ID.
    """
    with _write_lock:
        conn = get_conn()
        try:
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ref  = reference_phone.strip() if reference_phone else ""
            ptype = (payment_type or "Cash").strip()

            # Check if payment_type column exists (migration 16)
            inv_cols = [r[1] for r in conn.execute("PRAGMA table_info(invoices)")]
            if "payment_type" in inv_cols:
                c.execute("""INSERT INTO invoices
                                 (customer_phone, date, total, paid, balance, type,
                                  reference_phone, payment_type)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                          (customer_phone, now, total, paid, balance, type, ref, ptype))
            else:
                c.execute("""INSERT INTO invoices
                                 (customer_phone, date, total, paid, balance, type, reference_phone)
                             VALUES (?, ?, ?, ?, ?, ?, ?)""",
                          (customer_phone, now, total, paid, balance, type, ref))
            invoice_id = c.lastrowid

            # Check if product_name column exists (migration 14)
            has_pname = any(
                row[1] == "product_name"
                for row in conn.execute("PRAGMA table_info(invoice_items)")
            )
            for item in items:
                pname = item.get("product_name", "") or ""
                pid   = item.get("product_id", 0) or 0
                if has_pname:
                    c.execute("""INSERT INTO invoice_items
                                 (invoice_id, product_id, product_name, qty, price, amount)
                                 VALUES (?, ?, ?, ?, ?, ?)""",
                              (invoice_id, pid, pname,
                               item["qty"], item["price"], item["amount"]))
                else:
                    c.execute("""INSERT INTO invoice_items
                                 (invoice_id, product_id, qty, price, amount)
                                 VALUES (?, ?, ?, ?, ?)""",
                              (invoice_id, pid,
                               item["qty"], item["price"], item["amount"]))
            log.info("Saved %d item(s) for invoice #%d (has_pname=%s)",
                     len(items), invoice_id, has_pname)

            # Update customer total due ONLY if type == "invoice"
            if type.lower() == "invoice":
                c.execute("UPDATE customers SET total_due = total_due + ? WHERE phone = ?",
                          (balance, customer_phone))

            conn.commit()
            log.info("Invoice #%d created: phone=%s, total=%.2f, ref=%s, type=%s",
                     invoice_id, customer_phone, total, ref or "—", type)
            return invoice_id
        except Exception as e:
            conn.rollback()
            log.error("Invoice creation failed (rolled back): %s", e, exc_info=True)
            raise
        finally:
            conn.close()


def create_invoice_atomic(customer_phone, customer_name, total, paid, balance,
                          items, bill_type="invoice",
                          transport=0.0, discount_pct=0.0, discount_amt=0.0,
                          old_balance=0.0, net_balance=0.0,
                          reference_phone="", payment_type="Cash"):
    """
    Atomic invoice flow: save to DB → generate PDF.
    reference_phone: phone of the customer who referred this sale (optional).

    Returns (invoice_id, pdf_path, error_message).
    - On full success: (id, path, None)
    - On DB failure: (None, None, error_string)
    - On PDF failure: (id, None, error_string)
    """
    from pdf_generator import generate_invoice_pdf, REPORTLAB_AVAILABLE

    # Step 1: Ensure customer exists
    customer = get_or_create_customer(customer_name, customer_phone)
    if not customer:
        return None, None, "Failed to create/find customer."

    # Step 2: Create invoice (atomic DB transaction)
    try:
        invoice_id = create_invoice(
            customer_phone, total, paid, max(0, balance),
            items, type=bill_type, reference_phone=reference_phone,
            payment_type=payment_type)
    except Exception as e:
        return None, None, f"Failed to save invoice: {e}"

    # Step 3: Generate PDF (non-fatal — invoice is already saved)
    pdf_path = None
    pdf_error = None
    if REPORTLAB_AVAILABLE:
        try:
            pdf_path = generate_invoice_pdf(
                invoice_id, customer_name, customer_phone, items,
                total, paid, max(0, balance), type=bill_type,
                transport=transport, discount_pct=discount_pct,
                discount_amt=discount_amt, old_balance=old_balance,
                net_balance=net_balance, payment_type=payment_type)
            if not pdf_path:
                pdf_error = "PDF generation returned None."
        except Exception as e:
            pdf_error = f"PDF generation failed: {e}"
            log.error("PDF failed for invoice #%d: %s", invoice_id, e, exc_info=True)

    if pdf_error:
        return invoice_id, None, pdf_error
    return invoice_id, pdf_path, None


def get_invoice(invoice_id):
    row = _execute_read_one("SELECT * FROM invoices WHERE id = ?", (invoice_id,))
    return dict(row) if row else None


def get_invoice_items(invoice_id):
    """Return items for an invoice — simple query, no JOIN failures."""
    conn = get_conn()
    try:
        # Step 1: get raw items
        rows = conn.execute(
            "SELECT * FROM invoice_items WHERE invoice_id=? ORDER BY id",
            (invoice_id,)
        ).fetchall()

        cols = [r[1] for r in conn.execute("PRAGMA table_info(invoice_items)")]
        has_pname = "product_name" in cols
        has_ua    = "updated_at"   in cols

        # Check if products table has 'unit' column (migration 10 / 15)
        prod_cols   = [r[1] for r in conn.execute("PRAGMA table_info(products)")]
        has_unit    = "unit" in prod_cols

        result = []
        for row in rows:
            d = dict(row)
            pid   = d.get("product_id", 0) or 0
            pname = d.get("product_name", "") if has_pname else ""
            unit  = "Nos"

            # Look up product name and unit (guarded against missing columns)
            if pid and (not pname):
                if has_unit:
                    p = conn.execute(
                        "SELECT name, unit FROM products WHERE id=?", (pid,)
                    ).fetchone()
                    if p:
                        pname = p["name"] or pname
                        unit  = p["unit"] or "Nos"
                else:
                    p = conn.execute(
                        "SELECT name FROM products WHERE id=?", (pid,)
                    ).fetchone()
                    if p:
                        pname = p["name"] or pname
            elif pid:
                if has_unit:
                    p = conn.execute(
                        "SELECT unit FROM products WHERE id=?", (pid,)
                    ).fetchone()
                    if p:
                        unit = p["unit"] or "Nos"

            result.append({
                "id":           d.get("id"),
                "invoice_id":   d.get("invoice_id"),
                "product_id":   pid,
                "product_name": pname or "—",
                "qty":          d.get("qty", 0),
                "price":        d.get("price", 0),
                "amount":       d.get("amount", 0),
                "unit":         unit,
            })

        log.debug("get_invoice_items #%d → %d rows", invoice_id, len(result))
        return result
    except Exception as e:
        log.error("get_invoice_items failed for #%d: %s", invoice_id, e)
        return []
    finally:
        conn.close()


def get_invoices_by_reference(reference_phone: str) -> list:
    """Return all invoices that were referred by this customer phone.
    Joins customer name for display."""
    rows = _execute_read("""
        SELECT i.*,
               COALESCE(c.name, i.customer_phone) AS customer_name
        FROM invoices i
        LEFT JOIN customers c ON c.phone = i.customer_phone
        WHERE i.reference_phone = ?
        ORDER BY i.date DESC
    """, (reference_phone.strip(),))
    return [dict(r) for r in rows]


def get_invoices_by_phone(phone):
    rows = _execute_read(
        "SELECT * FROM invoices WHERE customer_phone = ? ORDER BY date DESC",
        (phone,))
    return [dict(r) for r in rows]


def get_unsynced_invoices():
    rows = _execute_read("SELECT * FROM invoices WHERE synced = 0")
    return [dict(r) for r in rows]


@_execute_write
def mark_invoice_synced(conn, invoice_id):
    conn.execute("UPDATE invoices SET synced = 1 WHERE id = ?", (invoice_id,))


# ══════════════════════════════════════════════════════════
# PAYMENT OPERATIONS
# ══════════════════════════════════════════════════════════

def create_payment(customer_phone, amount):
    """Record a payment and reduce customer total_due. Returns payment ID.
    DB-level guard prevents total_due going negative."""
    with _write_lock:
        conn = get_conn()
        try:
            c = conn.cursor()

            # Overpayment guard
            row = c.execute("SELECT total_due FROM customers WHERE phone = ?",
                            (customer_phone,)).fetchone()
            if row is None:
                raise ValueError(f"Customer with phone {customer_phone} not found.")
            current_due = row["total_due"]
            if amount > current_due:
                raise ValueError(
                    f"Payment Rs.{amount:,.2f} exceeds total due Rs.{current_due:,.2f}.")

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute("INSERT INTO payments (customer_phone, amount, date) VALUES (?, ?, ?)",
                      (customer_phone, amount, now))
            payment_id = c.lastrowid

            # Reduce customer total_due (clamped to 0)
            c.execute(
                "UPDATE customers SET total_due = MAX(0, total_due - ?) WHERE phone = ?",
                (amount, customer_phone))

            conn.commit()
            log.info("Payment #%d recorded: %s paid Rs.%.2f", payment_id, customer_phone, amount)
            return payment_id
        except Exception as e:
            conn.rollback()
            log.error("Payment creation failed: %s", e, exc_info=True)
            raise
        finally:
            conn.close()


def nil_customer_balance(customer_phone: str):
    """
    Zero out a customer's entire outstanding balance in one atomic operation.

    Steps:
      1. Read current total_due.
      2. If already 0, return (0, "Already zero").
      3. Insert a payment record for the full due amount
         (date prefixed with [NIL] so it's identifiable in history).
      4. Set total_due = 0 directly (belt-and-suspenders).
      5. Mark the payment as unsynced so cloud picks it up.

    Returns (payment_id, wiped_amount) on success, raises on failure.
    """
    with _write_lock:
        conn = get_conn()
        try:
            c = conn.cursor()
            row = c.execute(
                "SELECT total_due FROM customers WHERE phone = ?",
                (customer_phone,)).fetchone()
            if row is None:
                raise ValueError(f"Customer {customer_phone} not found.")
            current_due = float(row["total_due"])
            if current_due <= 0:
                return None, 0.0   # nothing to nil

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            note_date = f"[NIL] {now}"
            c.execute(
                "INSERT INTO payments (customer_phone, amount, date) VALUES (?, ?, ?)",
                (customer_phone, current_due, note_date))
            payment_id = c.lastrowid
            c.execute(
                "UPDATE customers SET total_due = 0 WHERE phone = ?",
                (customer_phone,))
            conn.commit()
            log.info(
                "NIL balance: customer %s, wiped ₹%.2f, payment_id=%d",
                customer_phone, current_due, payment_id)
            return payment_id, current_due
        except Exception as e:
            conn.rollback()
            log.error("nil_customer_balance failed: %s", e, exc_info=True)
            raise
        finally:
            conn.close()


def get_payments_by_phone(phone):
    rows = _execute_read(
        "SELECT * FROM payments WHERE customer_phone = ? ORDER BY date DESC",
        (phone,))
    return [dict(r) for r in rows]


def get_payment(payment_id: int):
    """Return a single payment row by id, or None if not found."""
    row = _execute_read_one(
        "SELECT * FROM payments WHERE id = ?", (payment_id,))
    return dict(row) if row else None


def get_unsynced_payments():
    rows = _execute_read("SELECT * FROM payments WHERE synced = 0")
    return [dict(r) for r in rows]


@_execute_write
def mark_payment_synced(conn, payment_id):
    conn.execute("UPDATE payments SET synced = 1 WHERE id = ?", (payment_id,))


# ══════════════════════════════════════════════════════════
# DAILY REPORT QUERIES
# ══════════════════════════════════════════════════════════

def _today_prefix():
    """Return today's date string for SQL LIKE matching (YYYY-MM-DD%)."""
    return datetime.now().strftime("%Y-%m-%d") + "%"


def get_today_sales_summary():
    """Returns dict: {total_sales, total_paid, total_balance, invoice_count}."""
    row = _execute_read_one("""
        SELECT COALESCE(SUM(total), 0)   AS total_sales,
               COALESCE(SUM(paid), 0)    AS total_paid,
               COALESCE(SUM(balance), 0) AS total_balance,
               COUNT(*)                  AS invoice_count
        FROM invoices
        WHERE date LIKE ? AND LOWER(type) = 'invoice'
    """, (_today_prefix(),))
    return dict(row) if row else {
        "total_sales": 0, "total_paid": 0, "total_balance": 0, "invoice_count": 0}


def get_today_invoice_count():
    """Return number of invoices created today."""
    row = _execute_read_one("""
        SELECT COUNT(*) AS count FROM invoices WHERE date LIKE ? AND LOWER(type) = 'invoice'
    """, (_today_prefix(),))
    return row["count"] if row else 0


def get_today_invoices():
    """Return all invoices created today with customer name."""
    rows = _execute_read("""
        SELECT i.*, c.name AS customer_name
        FROM invoices i
        LEFT JOIN customers c ON i.customer_phone = c.phone
        WHERE i.date LIKE ?
        ORDER BY i.date DESC
    """, (_today_prefix(),))
    return [dict(r) for r in rows]


def get_today_payments():
    """Return all payments recorded today with customer name."""
    rows = _execute_read("""
        SELECT p.*, c.name AS customer_name
        FROM payments p
        LEFT JOIN customers c ON p.customer_phone = c.phone
        WHERE p.date LIKE ?
        ORDER BY p.date DESC
    """, (_today_prefix(),))
    return [dict(r) for r in rows]


def get_today_payments_total():
    """Return total payment amount collected today (payments table only)."""
    row = _execute_read_one("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments WHERE date LIKE ?
    """, (_today_prefix(),))
    return row["total"] if row else 0


def get_today_collection_total():
    """Return total cash collected today: payments table + invoices.paid (Paid Now at billing)."""
    pay_row = _execute_read_one("""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM payments WHERE date LIKE ?
    """, (_today_prefix(),))
    inv_row = _execute_read_one("""
        SELECT COALESCE(SUM(paid), 0) AS total
        FROM invoices WHERE date LIKE ? AND LOWER(type) = 'invoice'
    """, (_today_prefix(),))
    pay_total = (pay_row["total"] if pay_row else 0)
    inv_total = (inv_row["total"] if inv_row else 0)
    return pay_total + inv_total


def get_top_products_today(limit=10):
    """Return top-selling products today by total quantity."""
    rows = _execute_read("""
        SELECT p.name, SUM(ii.qty) AS total_qty,
               SUM(ii.amount) AS total_amount
        FROM invoice_items ii
        JOIN invoices inv ON ii.invoice_id = inv.id
        JOIN products p   ON ii.product_id = p.id
        WHERE inv.date LIKE ? AND LOWER(inv.type) = 'invoice'
        GROUP BY p.id
        ORDER BY total_qty DESC
        LIMIT ?
    """, (_today_prefix(), limit))
    return [dict(r) for r in rows]


# get_pending_customers_today — defined below (line ~1122) near dashboard queries.


# ══════════════════════════════════════════════════════════════
# PERSISTENT FIREBASE SYNC QUEUE
# ══════════════════════════════════════════════════════════════

def queue_sync_operation(operation, payload):
    """
    Add a failed/offline operation to the persistent sync queue.

    Args:
        operation (str): e.g. 'sync_invoice', 'sync_payment', 'pdf_upload'
        payload   (str): JSON-encoded data needed to retry the operation.

    Returns the new queue item ID, or None on failure.
    """
    with _write_lock:
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                "INSERT INTO pending_syncs (operation, payload, retry_count, created_at) "
                "VALUES (?, ?, 0, ?)",
                (operation, payload, now)
            )
            conn.commit()
            item_id = cur.lastrowid
            log.debug("Sync queued: op=%s id=%d", operation, item_id)
            return item_id
        except Exception as e:
            conn.rollback()
            log.error("Failed to queue sync operation '%s': %s", operation, e, exc_info=True)
            return None
        finally:
            conn.close()


def get_pending_syncs(max_retries=5):
    """
    Return all pending sync queue items that have not exceeded max_retries.
    Returns list of dicts with keys: id, operation, payload, retry_count, created_at.
    """
    rows = _execute_read(
        "SELECT * FROM pending_syncs WHERE retry_count < ? ORDER BY created_at ASC",
        (max_retries,)
    )
    return [dict(r) for r in rows]


@_execute_write
def increment_sync_retry(conn, item_id):
    """Increment the retry counter and update last_tried timestamp."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE pending_syncs SET retry_count = retry_count + 1, last_tried = ? WHERE id = ?",
        (now, item_id)
    )
    log.debug("Sync retry count incremented: id=%d", item_id)


@_execute_write
def remove_sync_item(conn, item_id):
    """Remove a successfully processed item from the sync queue."""
    conn.execute("DELETE FROM pending_syncs WHERE id = ?", (item_id,))
    log.debug("Sync queue item removed: id=%d", item_id)


# ══════════════════════════════════════════════════════════════
# DASHBOARD QUERIES
# ══════════════════════════════════════════════════════════════

def get_today_sales():
    """Return list of today's invoices with customer name for the popup table."""
    rows = _execute_read("""
        SELECT i.id, i.date, i.total, i.paid, i.balance, i.type,
               COALESCE(c.name, i.customer_phone) AS customer_name
        FROM invoices i
        LEFT JOIN customers c ON i.customer_phone = c.phone
        WHERE i.date LIKE ? AND LOWER(i.type) = 'invoice'
        ORDER BY i.date DESC
    """, (_today_prefix(),))
    return [dict(r) for r in rows]


def get_today_pending():
    """Return total balance outstanding from today's invoices."""
    row = _execute_read_one("""
        SELECT COALESCE(SUM(balance), 0) AS total_pending
        FROM invoices
        WHERE date LIKE ? AND LOWER(type) = 'invoice' AND balance > 0
    """, (_today_prefix(),))
    return row["total_pending"] if row else 0.0


def get_recent_invoices(limit=5):
    """Return last N invoices with customer name, newest first."""
    rows = _execute_read("""
        SELECT i.id, i.date, i.total, i.paid, i.balance, i.type,
               COALESCE(c.name, i.customer_phone) AS customer_name
        FROM invoices i
        LEFT JOIN customers c ON i.customer_phone = c.phone
        ORDER BY i.date DESC
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in rows]


def get_recent_payments(limit=5):
    """Return last N payments with customer name, newest first."""
    rows = _execute_read("""
        SELECT p.id, p.date, p.amount,
               COALESCE(c.name, p.customer_phone) AS customer_name
        FROM payments p
        LEFT JOIN customers c ON p.customer_phone = c.phone
        ORDER BY p.date DESC
        LIMIT ?
    """, (limit,))
    return [dict(r) for r in rows]


def get_low_stock_products():
    """Return products where stock <= min_stock (only when min_stock > 0)."""
    rows = _execute_read("""
        SELECT id, name, stock, min_stock
        FROM products
        WHERE min_stock > 0 AND stock <= min_stock
        ORDER BY stock ASC
    """)
    return [dict(r) for r in rows]


def get_last_bill():
    """Return the single most recent invoice with customer name."""
    row = _execute_read_one("""
        SELECT i.id, i.total, i.date,
               COALESCE(c.name, i.customer_phone) AS customer_name
        FROM invoices i
        LEFT JOIN customers c ON i.customer_phone = c.phone
        WHERE LOWER(i.type) = 'invoice'
        ORDER BY i.date DESC
        LIMIT 1
    """)
    return dict(row) if row else None


def get_last_payment():
    """Return the single most recent payment with customer name."""
    row = _execute_read_one("""
        SELECT p.id, p.amount, p.date,
               COALESCE(c.name, p.customer_phone) AS customer_name
        FROM payments p
        LEFT JOIN customers c ON p.customer_phone = c.phone
        ORDER BY p.date DESC
        LIMIT 1
    """)
    return dict(row) if row else None


def get_pending_customers_today():
    """
    Return all customers with a non-zero total_due balance,
    including last_bill_date from the invoices table.
    """
    rows = _execute_read("""
        SELECT c.name, c.phone, c.total_due,
               MAX(i.date) AS last_bill_date
        FROM customers c
        LEFT JOIN invoices i ON i.customer_phone = c.phone
                             AND LOWER(i.type) = 'invoice'
        WHERE c.total_due > 0
        GROUP BY c.phone
        ORDER BY c.total_due DESC
    """)
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
# BACKGROUND TASKS TABLE  (new — for task_queue.py)
# ══════════════════════════════════════════════════════════════

def init_background_tasks_table():
    """
    Create the background_tasks table if it doesn't exist.
    Called once from main.py after init_database().
    """
    with _write_lock:
        conn = get_conn()
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS background_tasks (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_type     TEXT    NOT NULL,
                    task_data_json TEXT   NOT NULL DEFAULT '{}',
                    status        TEXT    NOT NULL DEFAULT 'pending',
                    retry_count   INTEGER NOT NULL DEFAULT 0,
                    created_at    TEXT    NOT NULL,
                    last_attempt  TEXT,
                    error_message TEXT
                )
            """)
            # Add pdf_url to invoices if missing (safe migration)
            cols = [r[1] for r in conn.execute("PRAGMA table_info(invoices)")]
            if "pdf_url" not in cols:
                conn.execute("ALTER TABLE invoices ADD COLUMN pdf_url TEXT DEFAULT ''")
                log.info("DB migration: added pdf_url column to invoices.")
            conn.commit()
            log.info("background_tasks table ready.")
        except Exception as e:
            conn.rollback()
            log.error("init_background_tasks_table failed: %s", e, exc_info=True)
        finally:
            conn.close()


def add_background_task(task_type: str, task_data_json: str) -> int:
    """
    Insert a new background task.  Returns the new task ID.
    task_type: 'print_pdf' | 'upload_pdf' | 'whatsapp_send' | 'cloud_sync'
    task_data_json: JSON string of parameters for the task handler.
    """
    with _write_lock:
        conn = get_conn()
        try:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.execute(
                "INSERT INTO background_tasks "
                "(task_type, task_data_json, status, retry_count, created_at) "
                "VALUES (?, ?, 'pending', 0, ?)",
                (task_type, task_data_json, now)
            )
            conn.commit()
            task_id = cur.lastrowid
            log.debug("Task queued: type=%s id=%d", task_type, task_id)
            return task_id
        except Exception as e:
            conn.rollback()
            log.error("add_background_task failed: %s", e, exc_info=True)
            return -1
        finally:
            conn.close()


def get_pending_tasks(task_type: str = None, max_retries: int = 5) -> list:
    """Return pending/retry tasks, optionally filtered by type."""
    if task_type:
        rows = _execute_read(
            "SELECT * FROM background_tasks "
            "WHERE status IN ('pending','retry') AND retry_count < ? AND task_type = ? "
            "ORDER BY created_at ASC",
            (max_retries, task_type)
        )
    else:
        rows = _execute_read(
            "SELECT * FROM background_tasks "
            "WHERE status IN ('pending','retry') AND retry_count < ? "
            "ORDER BY created_at ASC",
            (max_retries,)
        )
    return [dict(r) for r in rows]


@_execute_write
def mark_task_processing(conn, task_id: int):
    """Mark task as currently being processed."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE background_tasks SET status='processing', last_attempt=? WHERE id=?",
        (now, task_id)
    )


@_execute_write
def mark_task_completed(conn, task_id: int):
    """Mark a task as successfully completed."""
    conn.execute(
        "UPDATE background_tasks SET status='completed' WHERE id=?",
        (task_id,)
    )
    log.debug("Task completed: id=%d", task_id)


@_execute_write
def mark_task_failed(conn, task_id: int, error_message: str = ""):
    """Mark a task as failed and increment retry count."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE background_tasks "
        "SET status='failed', retry_count=retry_count+1, "
        "last_attempt=?, error_message=? WHERE id=?",
        (now, error_message[:500], task_id)
    )
    log.debug("Task failed: id=%d error=%s", task_id, error_message[:100])


@_execute_write
def mark_task_retry(conn, task_id: int, error_message: str = ""):
    """Put a failed task back in the retry queue."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn.execute(
        "UPDATE background_tasks "
        "SET status='retry', retry_count=retry_count+1, "
        "last_attempt=?, error_message=? WHERE id=?",
        (now, error_message[:500], task_id)
    )


def get_task_status(task_id: int) -> dict:
    """Return full task row as dict, or empty dict if not found."""
    row = _execute_read_one(
        "SELECT * FROM background_tasks WHERE id=?", (task_id,)
    )
    return dict(row) if row else {}


# ── Sync queue aliases expected by supabase_sync.py ──────

def mark_sync_complete(item_id: int):
    """Remove a completed pending_syncs entry (alias used by supabase_sync)."""
    remove_sync_item(item_id)


# ── Full-table reads expected by supabase_sync.sync_all ──

def get_all_invoices() -> list:
    rows = _execute_read("SELECT * FROM invoices ORDER BY id DESC")
    return [dict(r) for r in rows]


def get_all_payments() -> list:
    rows = _execute_read("SELECT * FROM payments ORDER BY id DESC")
    return [dict(r) for r in rows]


@_execute_write
def save_invoice_pdf_url(conn, invoice_id: int, pdf_url: str):
    """Store the Supabase Storage public URL on the invoice row."""
    conn.execute(
        "UPDATE invoices SET pdf_url = ? WHERE id = ?",
        (pdf_url, invoice_id)
    )
    log.debug("Saved pdf_url for invoice #%d", invoice_id)


def _migrate_reference_fields():
    """Add reference_phone / customer_name / pdf_url / updated_at to invoices if missing."""
    try:
        conn = get_conn()
        cols = [row[1] for row in conn.execute("PRAGMA table_info(invoices)")]
        for col, defval in [
            ("reference_phone", "''"),
            ("customer_name",   "''"),
            ("pdf_url",         "''"),
            ("updated_at",      "''"),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE invoices ADD COLUMN {col} TEXT DEFAULT {defval}")
                log.info("DB migration: added %s to invoices.", col)
        cust_cols = [row[1] for row in conn.execute("PRAGMA table_info(customers)")]
        for col in ("reference_name", "reference_phone"):
            if col not in cust_cols:
                conn.execute(f"ALTER TABLE customers ADD COLUMN {col} TEXT DEFAULT ''")
                log.info("DB migration: added %s to customers.", col)
        conn.commit()
    except Exception as e:
        log.error("Reference fields migration failed: %s", e)
    finally:
        conn.close()


# Run migration on import
try:
    _migrate_reference_fields()
except Exception:
    pass
