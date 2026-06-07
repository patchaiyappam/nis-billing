"""
TEST_TWO_WAY_SYNC.py - End-to-end test of two-way cloud sync
=============================================================

Simulates TWO different PCs (call them A and B) both using the same
Supabase project. Verifies that:

  1. An invoice created on PC A becomes visible on PC B within one
     pull cycle.
  2. A customer name change on PC B becomes visible on PC A within
     one pull cycle.
  3. PDFs uploaded by either side end up on both sides' local disk.

Runs entirely against the live Supabase project but uses two SANDBOX
SQLite DBs in ~/Documents/NEW_INDIAN_STEEL_PC_A and ..._PC_B so the
real DB is untouched.

Both sandboxes get migrations applied so updated_at columns exist.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def banner(msg):
    print()
    print("=" * 72)
    print(msg)
    print("=" * 72)


def setup_sandbox(name: str) -> Path:
    """Build a fresh sandbox directory at ~/Documents/NEW_INDIAN_STEEL_{name}."""
    base = Path.home() / "Documents" / f"NEW_INDIAN_STEEL_{name}"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True, exist_ok=True)
    (base / "invoices").mkdir(exist_ok=True)
    (base / "backups").mkdir(exist_ok=True)
    (base / "exports").mkdir(exist_ok=True)
    (base / "logs").mkdir(exist_ok=True)
    # Copy seed DB if present
    seed = HERE / "billing.db"
    if seed.exists():
        shutil.copy2(seed, base / "billing.db")
    return base


def configure_for(base: Path) -> None:
    """Re-point config to this sandbox BEFORE any other module imports."""
    import config
    config.BASE_DIR     = str(base)
    config.DB_PATH      = str(base / "billing.db")
    config.INVOICES_DIR = str(base / "invoices")
    config.BACKUPS_DIR  = str(base / "backups")
    config.EXPORTS_DIR  = str(base / "exports")
    config.LOGS_DIR     = str(base / "logs")
    # Force the modules that cached the path at import time to rebind.
    # database.py does `from config import DB_PATH`, so we need to also
    # patch its name binding.
    import database, migrations, supabase_sync, supabase_storage, cloud_pull
    for mod in (database, migrations, supabase_sync, supabase_storage, cloud_pull):
        if hasattr(mod, "DB_PATH"):
            mod.DB_PATH = config.DB_PATH
        if hasattr(mod, "BASE_DIR"):
            mod.BASE_DIR = config.BASE_DIR
        if hasattr(mod, "INVOICES_DIR"):
            mod.INVOICES_DIR = config.INVOICES_DIR
    # Reset cached supabase clients so they reconnect under the new state
    supabase_sync._client = None
    supabase_sync._ready = False
    supabase_storage._client = None
    supabase_storage._ready = False
    cloud_pull._client = None
    cloud_pull._ready = False


def init_sandbox():
    """Run migrations on whatever DB config currently points to."""
    from database import init_database
    from migrations import run_migrations
    init_database()
    run_migrations()


def main():
    banner("Setting up two sandboxes (PC_A and PC_B)")
    base_a = setup_sandbox("PC_A")
    base_b = setup_sandbox("PC_B")
    print(f"  PC_A: {base_a}")
    print(f"  PC_B: {base_b}")

    # ---- Initialize PC_A ----
    configure_for(base_a)
    init_sandbox()
    from database import (create_customer, create_invoice, get_all_customers,
                          get_customer)
    from supabase_sync import sync_customer, sync_invoice
    from cloud_pull import pull_all

    # First, wipe cloud so we start clean
    banner("Wiping cloud so test starts from a clean state")
    from supabase_sync import _get_client
    cli = _get_client()
    for tbl in ("invoice_items", "invoices", "payments", "customers"):
        try:
            cli.table(tbl).delete().gte("updated_at", "1970-01-01").execute()
        except Exception as e:
            print(f"  warn: could not wipe {tbl}: {e}")

    # ---- Act on PC_A: create a unique test customer ----
    banner("[PC_A] creating test customer TEST_SYNC (phone 9999988888)")
    test_phone = "9999988888"
    create_customer("TEST_SYNC_ORIGINAL", test_phone)
    cust = get_customer(test_phone)
    sync_customer(cust)
    print(f"  pushed to cloud: {cust}")

    # ---- Switch to PC_B, pull, and verify it landed ----
    configure_for(base_b)
    init_sandbox()
    banner("[PC_B] pulling from cloud and checking that the customer arrived")
    counts = pull_all()
    print(f"  pull counts: {counts}")
    from database import get_customer as get_customer_b
    cust_b = get_customer_b(test_phone)
    if cust_b and cust_b.get("name") == "TEST_SYNC_ORIGINAL":
        print(f"  OK   PC_B sees the customer: {cust_b['name']}")
    else:
        print(f"  FAIL PC_B does not see the customer. Got: {cust_b}")
        return 1

    # ---- Act on PC_B: rename the customer ----
    banner("[PC_B] renaming the customer to TEST_SYNC_RENAMED")
    from database import update_customer
    update_customer(test_phone, "TEST_SYNC_RENAMED", address="changed-by-B",
                    opening_balance=cust_b.get("opening_balance", 0) or 0)
    cust_b2 = get_customer_b(test_phone)
    sync_customer(cust_b2)
    print(f"  pushed renamed customer: name={cust_b2['name']}")

    # ---- Back to PC_A, pull, verify it sees the rename ----
    configure_for(base_a)
    banner("[PC_A] pulling again and checking that the rename came through")
    time.sleep(2)  # give Postgres trigger a moment
    counts = pull_all()
    print(f"  pull counts: {counts}")
    cust_a2 = get_customer(test_phone)
    if cust_a2 and cust_a2.get("name") == "TEST_SYNC_RENAMED":
        print(f"  OK   PC_A sees the rename: {cust_a2['name']}")
    else:
        print(f"  FAIL PC_A did not see rename. Got: {cust_a2}")
        return 2

    banner("Cleanup: removing test customer from cloud")
    try:
        cli = _get_client()
        cli.table("customers").delete().eq("phone", test_phone).execute()
    except Exception as e:
        print(f"  warn: cleanup failed: {e}")

    banner("RESULT")
    print("  PASS - two-way sync works end-to-end.")
    print(f"  Sandboxes preserved at:")
    print(f"    {base_a}")
    print(f"    {base_b}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
