"""Database Migration System - NEW INDIAN STEEL Billing System."""
import sqlite3
import threading
from logger import get_logger
from config import DB_PATH

log = get_logger(__name__)
_migration_lock = threading.Lock()


MIGRATIONS = [
    (1, "Add type column to invoices if missing", [
        "ALTER TABLE invoices ADD COLUMN type TEXT DEFAULT 'invoice'"
    ]),
    (2, "Create pending_syncs table", [
        """CREATE TABLE IF NOT EXISTS pending_syncs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            operation   TEXT    NOT NULL,
            payload     TEXT    NOT NULL,
            retry_count INTEGER DEFAULT 0,
            created_at  TEXT    NOT NULL,
            last_tried  TEXT
        )"""
    ]),
    (3, "Ensure schema_version table exists", [
        """CREATE TABLE IF NOT EXISTS schema_version (
            version     INTEGER PRIMARY KEY,
            description TEXT    NOT NULL,
            applied_at  TEXT    NOT NULL
        )"""
    ]),
    (4, "Add firebase_url column to invoices", [
        "ALTER TABLE invoices ADD COLUMN firebase_url TEXT"
    ]),
    (5, "Add firebase_url column to payments", [
        "ALTER TABLE payments ADD COLUMN firebase_url TEXT"
    ]),
    (6, "Add stock columns to products", [
        "ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0",
        "ALTER TABLE products ADD COLUMN min_stock INTEGER DEFAULT 0",
    ]),
    (7, "Add opening_balance and address to customers", [
        "ALTER TABLE customers ADD COLUMN opening_balance REAL DEFAULT 0.0",
        "ALTER TABLE customers ADD COLUMN address TEXT DEFAULT ''",
    ]),
    (8, "Add updated_at columns for two-way sync", [
        "ALTER TABLE customers     ADD COLUMN updated_at TEXT",
        "ALTER TABLE invoices      ADD COLUMN updated_at TEXT",
        "ALTER TABLE invoice_items ADD COLUMN updated_at TEXT",
        "ALTER TABLE payments      ADD COLUMN updated_at TEXT",
    ]),
    (9, "Add pdf_url to invoices", [
        "ALTER TABLE invoices ADD COLUMN pdf_url TEXT DEFAULT ''",
    ]),
    (10, "Add unit column to products (Kg/Nos)", [
        "ALTER TABLE products ADD COLUMN unit TEXT DEFAULT 'Nos'",
    ]),
    (11, "Add updated_at to products for two-way sync", [
        "ALTER TABLE products ADD COLUMN updated_at TEXT",
    ]),
    (12, "Add reference_phone to invoices for referral tracking", [
        "ALTER TABLE invoices ADD COLUMN reference_phone TEXT DEFAULT ''",
    ]),
    (13, "Ensure updated_at exists on all sync tables (repair migration)", [
        "ALTER TABLE customers     ADD COLUMN updated_at TEXT",
        "ALTER TABLE invoices      ADD COLUMN updated_at TEXT",
        "ALTER TABLE invoice_items ADD COLUMN updated_at TEXT",
        "ALTER TABLE payments      ADD COLUMN updated_at TEXT",
        "ALTER TABLE products      ADD COLUMN updated_at TEXT",
    ]),
    (14, "Add product_name to invoice_items so items survive cloud sync", [
        "ALTER TABLE invoice_items ADD COLUMN product_name TEXT DEFAULT ''",
    ]),
    (15, "Ensure unit and updated_at exist on products (repair)", [
        "ALTER TABLE products ADD COLUMN unit       TEXT DEFAULT 'Nos'",
        "ALTER TABLE products ADD COLUMN updated_at TEXT",
    ]),
    (16, "Add payment_type to invoices (Cash/UPI/Credit/Cheque)", [
        "ALTER TABLE invoices ADD COLUMN payment_type TEXT DEFAULT 'Cash'",
    ]),
    (17, "Add cloud_id to invoices & payments for collision-free sync", [
        "ALTER TABLE invoices ADD COLUMN cloud_id TEXT",
        "ALTER TABLE payments ADD COLUMN cloud_id TEXT",
        "UPDATE invoices SET cloud_id = CAST(id AS TEXT) "
        "WHERE cloud_id IS NULL OR cloud_id = ''",
        "UPDATE payments SET cloud_id = CAST(id AS TEXT) "
        "WHERE cloud_id IS NULL OR cloud_id = ''",
    ]),
    (18, "Backfill NULL product updated_at so price edits aren't reverted", [
        "UPDATE products SET updated_at = '2000-01-01T00:00:00+00:00' "
        "WHERE updated_at IS NULL OR updated_at = ''",
    ]),
]


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _ensure_version_table(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        description TEXT NOT NULL,
        applied_at TEXT NOT NULL)""")
    conn.commit()


def _get_applied_versions(conn):
    rows = conn.execute("SELECT version FROM schema_version").fetchall()
    return {row["version"] for row in rows}


def _column_exists(conn, table, column):
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _record_migration(conn, version, description):
    from datetime import datetime
    conn.execute(
        "INSERT OR IGNORE INTO schema_version (version, description, applied_at) VALUES (?, ?, ?)",
        (version, description, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))


def apply_migration(conn, version, description, sql_statements):
    try:
        for sql in sql_statements:
            s = sql.strip()
            if s.upper().startswith("ALTER TABLE") and "ADD COLUMN" in s.upper():
                parts = s.split()
                try:
                    tbl = parts[2]
                    ac = [p.upper() for p in parts].index("COLUMN")
                    col = parts[ac + 1]
                    if _column_exists(conn, tbl, col):
                        continue
                except (ValueError, IndexError):
                    pass
            conn.execute(s)
        _record_migration(conn, version, description)
        conn.commit()
        log.info("Migration v%d applied: %s", version, description)
        return True
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        log.error("Migration v%d FAILED: %s | %s", version, description, e)
        return False


def run_migrations():
    with _migration_lock:
        try:
            conn = _get_conn()
        except Exception as e:
            log.error("Migration: cannot open DB: %s", e)
            return
        try:
            _ensure_version_table(conn)
            applied = _get_applied_versions(conn)
            pending = [(v, d, s) for v, d, s in MIGRATIONS if v not in applied]
            if not pending:
                log.info("Schema up to date.")
                return
            log.info("Running %d pending migration(s).", len(pending))
            for v, d, s in sorted(pending, key=lambda x: x[0]):
                log.info("Applying v%d: %s", v, d)
                if not apply_migration(conn, v, d, s):
                    log.error("Migration halted at v%d.", v)
                    break
            log.info("Migration run complete.")
        except Exception as e:
            log.error("Migration error: %s", e)
        finally:
            try:
                conn.close()
            except Exception:
                pass
