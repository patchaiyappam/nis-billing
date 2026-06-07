"""
PURGE_QUEUES.py - Emergency queue cleanup
==========================================

Use this when the app keeps re-syncing deleted data. It happens when
old entries are stuck in the pending_syncs or background_tasks tables
(usually because the app was running while a wipe script was executed,
so SQLite's WAL recovered the old entries on next startup).

What it does:
  1. Forces a WAL checkpoint on billing.db
  2. Truncates pending_syncs and background_tasks
  3. Resets the autoincrement counter
  4. Reports how many rows were purged

IMPORTANT: close the billing app completely BEFORE running this.
If the app is open, you'll see a "database is locked" error.

Usage:
    python PURGE_QUEUES.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

db_path = Path.home() / "Documents" / "NEW_INDIAN_STEEL" / "billing.db"
if not db_path.exists():
    print(f"ERROR: DB not found at {db_path}")
    sys.exit(1)

print(f"Opening {db_path}")
conn = sqlite3.connect(str(db_path), timeout=5)
try:
    # Force checkpoint so anything in -wal is merged in
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    def safe_count(tbl: str) -> int:
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        except sqlite3.OperationalError:
            return -1

    def safe_delete(tbl: str) -> int:
        n = safe_count(tbl)
        if n < 0:
            print(f"  {tbl}: table does not exist (skipping)")
            return 0
        conn.execute(f"DELETE FROM {tbl}")
        print(f"  {tbl}: purged {n} row(s)")
        return n

    print("\nBEFORE:")
    print(f"  pending_syncs    : {safe_count('pending_syncs')}")
    print(f"  background_tasks : {safe_count('background_tasks')}")
    print(f"  invoices         : {safe_count('invoices')}")
    print(f"  invoice_items    : {safe_count('invoice_items')}")

    print("\nPURGING:")
    safe_delete("pending_syncs")
    safe_delete("background_tasks")
    # Reset autoincrement counters
    try:
        conn.execute("DELETE FROM sqlite_sequence WHERE name IN "
                     "('pending_syncs','background_tasks')")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    # Checkpoint again to flush
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")

    print("\nAFTER:")
    print(f"  pending_syncs    : {safe_count('pending_syncs')}")
    print(f"  background_tasks : {safe_count('background_tasks')}")

    print()
    print("Done. Now open the app again. The fresh 79 customers will")
    print("re-sync to Supabase on startup with no old entries blocking.")

except sqlite3.OperationalError as e:
    if "locked" in str(e):
        print("\nERROR: database is locked.")
        print("       The billing app is still running. Close it first")
        print("       (X out of the window) and run this script again.")
    else:
        print(f"\nERROR: {e}")
    sys.exit(2)
finally:
    conn.close()
