"""
TEST_END_TO_END.py - Safe end-to-end bill test for the NIS billing system.
==========================================================================

What this does
--------------
Exercises the same code path that runs when you click "Generate Bill" in
the GUI, but against a COPY of your real database so nothing real changes.

Specifically it:
  1. Locates your live DB at ~/Documents/NEW_INDIAN_STEEL/billing.db
  2. Copies DB + invoices dir to a sandbox at:
       ~/Documents/NEW_INDIAN_STEEL_TEST/
  3. Monkey-patches config.DB_PATH and config.INVOICES_DIR before any
     other module imports them, so the real files are untouched.
  4. Runs init_database + run_migrations on the sandbox (matches startup).
  5. Picks the first real customer and two real products.
  6. Calls create_invoice_atomic() - the EXACT call the GUI makes - with:
        - 2 line items
        - an old_balance of 500 (exercises the old-balance code path)
        - a partial payment (exercises the running-balance code path)
  7. Generates the PDF, opens it for visual review.
  8. Prints a verification report.

Usage
-----
On your laptop, from the NIS_final folder:

    python TEST_END_TO_END.py

The script does NOT touch your live DB, live invoices, Supabase, or
WhatsApp. Inspect the PDF that opens; if it looks right, the GUI
workflow is fine.
"""
from __future__ import annotations

import os
import shutil
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


# ========================================================================
# 1. Set up a sandbox BEFORE importing config / database / pdf_generator
# ========================================================================

LIVE_BASE   = Path.home() / "Documents" / "NEW_INDIAN_STEEL"
LIVE_DB     = LIVE_BASE / "billing.db"
SANDBOX     = Path.home() / "Documents" / "NEW_INDIAN_STEEL_TEST"
SANDBOX_DB  = SANDBOX / "billing.db"
SANDBOX_INV = SANDBOX / "invoices"

if not LIVE_DB.exists():
    print(f"ERROR: live DB not found at {LIVE_DB}")
    print("       Run the main app once to initialize it, then re-run this test.")
    sys.exit(1)

# Fresh sandbox each run
if SANDBOX.exists():
    shutil.rmtree(SANDBOX)
SANDBOX.mkdir(parents=True, exist_ok=True)
SANDBOX_INV.mkdir(parents=True, exist_ok=True)
shutil.copy2(LIVE_DB, SANDBOX_DB)
# Copy WAL/SHM if present so we read the live state
for ext in ("-wal", "-shm"):
    side = LIVE_DB.with_suffix(LIVE_DB.suffix + ext)
    if side.exists():
        shutil.copy2(side, SANDBOX_DB.with_suffix(SANDBOX_DB.suffix + ext))

print(f"[setup] live DB:    {LIVE_DB}")
print(f"[setup] sandbox DB: {SANDBOX_DB}")

# Patch config BEFORE other modules import it
import config  # noqa: E402
config.DB_PATH      = str(SANDBOX_DB)
config.INVOICES_DIR = str(SANDBOX_INV)
config.BASE_DIR     = str(SANDBOX)
config.BACKUPS_DIR  = str(SANDBOX / "backups")
config.EXPORTS_DIR  = str(SANDBOX / "exports")
config.LOGS_DIR     = str(SANDBOX / "logs")
for d in (config.BACKUPS_DIR, config.EXPORTS_DIR, config.LOGS_DIR):
    os.makedirs(d, exist_ok=True)

# Bypass Supabase + WhatsApp so the test stays local
config.SUPABASE_URL = ""
config.SUPABASE_KEY = ""
config.WA_METHOD    = "wame"


# ========================================================================
# 2. Import the real modules (they now see the sandbox paths)
# ========================================================================
from database import (   # noqa: E402
    init_database,
    get_all_customers, get_all_products,
    get_customer, get_computed_due,
    create_invoice_atomic, get_invoice, get_invoice_items,
)
from migrations import run_migrations   # noqa: E402

# Apply any pending schema migrations on the sandbox DB
# (same thing main.py does at startup)
init_database()
run_migrations()


def banner(msg):
    print()
    print("=" * 72)
    print(msg)
    print("=" * 72)


def main():
    banner("STEP A - Pick a real customer and two real products")

    customers = get_all_customers()
    products  = get_all_products()
    if len(customers) < 1:
        print("ERROR: no customers in DB. Import customers first.")
        return 2
    if len(products) < 2:
        print("ERROR: need at least 2 products in DB for the test.")
        return 2

    cust = customers[0]
    p1, p2 = products[0], products[1]

    print(f"  Customer : {cust['name']}  ({cust['phone']})")
    print(f"  Existing due (computed): {get_computed_due(cust['phone']):.2f}")
    print(f"  Product 1: #{p1['id']} {p1['name']} @ {p1['price']}")
    print(f"  Product 2: #{p2['id']} {p2['name']} @ {p2['price']}")

    banner("STEP B - Build the line items (qty 2 of each)")

    items = [
        {"product_id": p1["id"], "product_name": p1["name"],
         "qty": 2, "price": float(p1["price"]),
         "amount": 2 * float(p1["price"])},
        {"product_id": p2["id"], "product_name": p2["name"],
         "qty": 2, "price": float(p2["price"]),
         "amount": 2 * float(p2["price"])},
    ]
    subtotal     = sum(i["amount"] for i in items)
    discount_pct = 5.0
    discount_amt = round(subtotal * discount_pct / 100.0, 2)
    transport    = 100.0
    grand_total  = round(subtotal - discount_amt + transport, 2)
    paid         = round(grand_total / 2, 2)
    invoice_bal  = round(grand_total - paid, 2)
    old_balance  = 500.00
    net_balance  = round(old_balance + invoice_bal, 2)

    print(f"  Subtotal       : {subtotal:.2f}")
    print(f"  Discount (5%)  : {discount_amt:.2f}")
    print(f"  Transport      : {transport:.2f}")
    print(f"  Grand total    : {grand_total:.2f}")
    print(f"  Paid now       : {paid:.2f}")
    print(f"  Invoice balance: {invoice_bal:.2f}")
    print(f"  Old balance    : {old_balance:.2f}  (test value)")
    print(f"  Net balance    : {net_balance:.2f}")

    banner("STEP C - Call create_invoice_atomic (same call the GUI makes)")

    due_before = get_computed_due(cust["phone"])
    print(f"  Customer due BEFORE save: {due_before:.2f}")

    invoice_id, pdf_path, error = create_invoice_atomic(
        cust["phone"], cust["name"],
        grand_total, paid, invoice_bal,
        items,
        bill_type    = "invoice",
        transport    = transport,
        discount_pct = discount_pct,
        discount_amt = discount_amt,
        old_balance  = old_balance,
        net_balance  = net_balance,
    )

    if invoice_id is None:
        print(f"  FAIL: invoice not saved - {error}")
        return 3
    print(f"  OK   invoice_id = {invoice_id}")
    if error:
        print(f"  WARN: post-save warning - {error}")
    print(f"  PDF  {pdf_path}")

    banner("STEP D - Verify DB rows match what we sent")

    inv = get_invoice(invoice_id)
    print(f"  invoices row     : {dict(inv)}")
    saved_items = get_invoice_items(invoice_id)
    for it in saved_items:
        print(f"  invoice_items    : {dict(it)}")

    ok = True
    if abs(inv["total"] - grand_total) > 0.01:
        print(f"  FAIL total mismatch: {inv['total']} vs {grand_total}")
        ok = False
    if abs(inv["paid"] - paid) > 0.01:
        print(f"  FAIL paid mismatch: {inv['paid']} vs {paid}")
        ok = False
    if abs(inv["balance"] - invoice_bal) > 0.01:
        print(f"  FAIL balance mismatch: {inv['balance']} vs {invoice_bal}")
        ok = False
    if len(saved_items) != len(items):
        print(f"  FAIL item-count mismatch: {len(saved_items)} vs {len(items)}")
        ok = False

    due_after = get_computed_due(cust["phone"])
    print(f"  Customer due AFTER save : {due_after:.2f}")
    expected_due = round(due_before + invoice_bal, 2)
    if abs(due_after - expected_due) > 0.01:
        print(f"  FAIL due delta: expected {expected_due:.2f}, got {due_after:.2f}")
        ok = False
    else:
        print(f"  OK   due increased by exactly {invoice_bal:.2f}")

    banner("STEP E - Open the PDF for visual review")
    if pdf_path and os.path.exists(pdf_path):
        print(f"  Opening: {pdf_path}")
        try:
            if sys.platform == "win32":
                os.startfile(pdf_path)
            elif sys.platform == "darwin":
                import subprocess; subprocess.run(["open", pdf_path])
            else:
                import subprocess; subprocess.run(["xdg-open", pdf_path])
        except Exception as e:
            print(f"  Could not auto-open ({e}). Open it manually.")
    else:
        print("  FAIL: PDF path missing or file not generated.")
        ok = False

    banner("VISUAL CHECKLIST - confirm in the PDF that opens")
    print("  [ ] Header says 'ESTIMATE' (not 'INVOICE' or 'TAX INVOICE')")
    print("  [ ] Logo + 'NEW INDIAN STEEL' shown")
    print("  [ ] Customer name and phone correct")
    print("  [ ] Both line items present with correct qty, price, amount")
    print("  [ ] Subtotal, 5% discount, transport, grand total all correct")
    print("  [ ] Old Balance row shows 500.00")
    print(f"  [ ] Net Balance row shows {net_balance:.2f}")
    print("  [ ] Summary block is RIGHT-ALIGNED with no grey shading")
    print("  [ ] No tax/GSTIN columns")

    banner("RESULT")
    if ok:
        print("  PASS - end-to-end workflow is healthy.")
        print(f"  Sandbox preserved at: {SANDBOX}")
        print("  (Delete that folder anytime; your live DB is untouched.)")
        return 0
    else:
        print("  FAIL - see messages above.")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        print("\nUNHANDLED EXCEPTION:")
        traceback.print_exc()
        sys.exit(99)
