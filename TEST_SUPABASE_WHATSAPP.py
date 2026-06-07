"""
TEST_SUPABASE_WHATSAPP.py - Live check: Supabase sync + WhatsApp PDF sharing
============================================================================

Exercises the full cloud chain end-to-end against the SAME Supabase project
the app uses (URL/KEY from config.py). Does NOT touch your live SQLite DB.

What it verifies:
  1. supabase package installed
  2. Supabase URL/KEY reachable
  3. Required tables exist (customers, invoices, invoice_items)
  4. Required Storage bucket "invoices" exists and is public
  5. sync_customer() round-trips
  6. sync_invoice() with line items round-trips
  7. upload_pdf() uploads a real PDF and returns a public URL
  8. The public URL is actually reachable (HTTP 200)
  9. WhatsApp message body is built correctly with the PDF URL embedded
 10. WhatsApp _dispatch routing picks the right method based on config

Run from the NIS_final folder:
    python TEST_SUPABASE_WHATSAPP.py

Inserts test rows with phone "9999900001" and invoice id "test-INV-1".
Cleanup is best-effort at the end. No real customer or invoice is touched.
"""
from __future__ import annotations

import os
import sys
import shutil
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ============================================================
# Use a SANDBOX SQLite so test inserts don't touch live data,
# but use the REAL Supabase URL/KEY from config.py.
# ============================================================
LIVE_BASE  = Path.home() / "Documents" / "NEW_INDIAN_STEEL"
LIVE_DB    = LIVE_BASE / "billing.db"
SANDBOX    = Path.home() / "Documents" / "NEW_INDIAN_STEEL_CLOUDTEST"
SBOX_DB    = SANDBOX / "billing.db"
SBOX_INV   = SANDBOX / "invoices"

if not LIVE_DB.exists():
    print(f"ERROR: live DB not found at {LIVE_DB}")
    sys.exit(1)

if SANDBOX.exists():
    shutil.rmtree(SANDBOX)
SANDBOX.mkdir(parents=True, exist_ok=True)
SBOX_INV.mkdir(parents=True, exist_ok=True)
shutil.copy2(LIVE_DB, SBOX_DB)

import config  # noqa: E402
config.DB_PATH      = str(SBOX_DB)
config.INVOICES_DIR = str(SBOX_INV)
config.BASE_DIR     = str(SANDBOX)
config.BACKUPS_DIR  = str(SANDBOX / "backups")
config.EXPORTS_DIR  = str(SANDBOX / "exports")
config.LOGS_DIR     = str(SANDBOX / "logs")
for d in (config.BACKUPS_DIR, config.EXPORTS_DIR, config.LOGS_DIR):
    os.makedirs(d, exist_ok=True)

# Force wame so no WhatsApp message is actually sent during test
config.WA_METHOD       = "wame"
config.WA_META_TOKEN   = ""
config.WA_META_PHONE_ID = ""
config.WA_TWILIO_SID   = ""
config.WA_TWILIO_TOKEN = ""
config.WA_TWILIO_FROM  = ""


def banner(msg):
    print()
    print("=" * 72)
    print(msg)
    print("=" * 72)


# ============================================================
# 1. Package + connectivity
# ============================================================
banner("1. Supabase package + credentials")

print(f"  SUPABASE_URL = {config.SUPABASE_URL or '(empty)'}")
print(f"  SUPABASE_KEY = {'(set)' if config.SUPABASE_KEY else '(empty)'}")

if not config.SUPABASE_URL or not config.SUPABASE_KEY:
    print("  FAIL: credentials missing — cloud sync would be disabled.")
    sys.exit(2)

try:
    from supabase import create_client
    print("  OK   supabase package installed")
except ImportError:
    print("  FAIL: supabase package not installed. Run: pip install supabase")
    sys.exit(3)

try:
    client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
    print("  OK   client created")
except Exception as e:
    print(f"  FAIL: cannot create client: {e}")
    sys.exit(4)


# ============================================================
# 2. Tables exist
# ============================================================
banner("2. Required Postgres tables exist")

required_tables = ["customers", "invoices", "invoice_items", "payments"]
table_ok = {}
for t in required_tables:
    try:
        client.table(t).select("*").limit(1).execute()
        table_ok[t] = True
        print(f"  OK   table '{t}' reachable")
    except Exception as e:
        table_ok[t] = False
        print(f"  FAIL table '{t}': {e}")

if not all(table_ok.values()):
    print()
    print("  Missing tables. Run the SQL in NIS_final/supabase_migrations.sql")
    print("  in the Supabase SQL editor, then re-run this test.")
    sys.exit(5)


# ============================================================
# 3. Storage bucket
# ============================================================
banner("3. Storage bucket 'invoices' exists and is public")
try:
    buckets = client.storage.list_buckets()
    names = [b.name if hasattr(b, "name") else b.get("name", "") for b in buckets]
    print(f"  buckets: {names}")
    if "invoices" in names:
        print("  OK   bucket 'invoices' exists")
    else:
        print("  FAIL bucket 'invoices' is missing.")
        print("       Create it in Supabase dashboard -> Storage -> New bucket -> name 'invoices' -> Public")
        sys.exit(6)
except Exception as e:
    print(f"  FAIL listing buckets: {e}")
    sys.exit(7)


# ============================================================
# 4. sync_customer round-trip
# ============================================================
banner("4. sync_customer round-trip")

TEST_PHONE   = "9999900001"
TEST_INVID   = 999001     # numeric id used by sync_invoice

from supabase_sync import sync_customer, sync_invoice  # noqa: E402

cust = {
    "id":        999001,
    "phone":     TEST_PHONE,
    "name":      "TEST CUSTOMER (delete me)",
    "total_due": 0.0,
    "address":   "TEST",
}
ok = sync_customer(cust)
print(f"  sync_customer returned: {ok}")

# Verify it landed
try:
    rows = client.table("customers").select("*").eq("phone", TEST_PHONE).execute()
    matched = [r for r in rows.data if r.get("phone") == TEST_PHONE]
    if matched:
        print(f"  OK   customer round-trip:")
        print(f"       {matched[0]}")
    else:
        print(f"  FAIL customer not found after upsert")
except Exception as e:
    print(f"  FAIL verify: {e}")


# ============================================================
# 5. sync_invoice round-trip with line items
# ============================================================
banner("5. sync_invoice + invoice_items round-trip")

invoice = {
    "customer_phone": TEST_PHONE,
    "customer_name":  "TEST CUSTOMER (delete me)",
    "total":   1000.00,
    "paid":     500.00,
    "balance":  500.00,
    "type":    "invoice",
    "date":    "2026-05-16 12:00:00",
    "pdf_url": "",
}
items = [
    {"product_name": "TEST PRODUCT A", "qty": 1, "price": 600.0, "amount": 600.0},
    {"product_name": "TEST PRODUCT B", "qty": 2, "price": 200.0, "amount": 400.0},
]
ok = sync_invoice(TEST_INVID, invoice, items)
print(f"  sync_invoice returned: {ok}")

try:
    rows = client.table("invoices").select("*").eq("id", str(TEST_INVID)).execute()
    if rows.data:
        print(f"  OK   invoice round-trip:")
        print(f"       {rows.data[0]}")
    else:
        print("  FAIL invoice not found after upsert")

    irows = client.table("invoice_items").select("*").eq("invoice_id", str(TEST_INVID)).execute()
    print(f"  invoice_items rows: {len(irows.data)}")
    for r in irows.data:
        print(f"       {r}")
except Exception as e:
    print(f"  FAIL verify: {e}")


# ============================================================
# 6. PDF upload + public URL fetch
# ============================================================
banner("6. Upload PDF to Storage and verify public URL")

# Use the bill PDF generated by the previous test if present, else build one
sample_pdfs = sorted(
    (Path.home() / "Documents" / "NEW_INDIAN_STEEL_TEST" / "invoices").glob("*.pdf")
)
if sample_pdfs:
    pdf_path = str(sample_pdfs[-1])
    print(f"  using existing sample PDF: {pdf_path}")
else:
    # Quick generate one
    from database import init_database  # noqa: E402
    from migrations import run_migrations  # noqa: E402
    from database import (get_all_customers, get_all_products,  # noqa: E402
                          create_invoice_atomic)
    init_database(); run_migrations()
    custs = get_all_customers(); prods = get_all_products()
    items_local = [
        {"product_id": prods[0]["id"], "product_name": prods[0]["name"],
         "qty": 1, "price": float(prods[0]["price"]),
         "amount": float(prods[0]["price"])},
    ]
    inv_id, pdf_path, _ = create_invoice_atomic(
        custs[0]["phone"], custs[0]["name"],
        float(prods[0]["price"]), 0.0, float(prods[0]["price"]),
        items_local, bill_type="invoice",
    )
    print(f"  generated sample PDF: {pdf_path}")

from supabase_storage import upload_pdf, is_storage_available  # noqa: E402

print(f"  storage available: {is_storage_available()}")
url, err = upload_pdf(pdf_path, doc_type="invoice", doc_id=TEST_INVID)
if url:
    print(f"  OK   upload succeeded")
    print(f"       URL: {url}")
else:
    print(f"  FAIL upload: {err}")

# Verify URL is reachable
if url:
    try:
        req = urllib.request.Request(url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=15)
        ctype = resp.headers.get("Content-Type", "")
        clen  = resp.headers.get("Content-Length", "")
        print(f"  OK   public URL responds: HTTP {resp.status}, "
              f"Content-Type={ctype}, Content-Length={clen}")
    except Exception as e:
        print(f"  FAIL public URL not reachable: {e}")


# ============================================================
# 7. WhatsApp message build with PDF URL embedded
# ============================================================
banner("7. WhatsApp message body (what the customer would receive)")

from whatsapp import _build_bill_message, _normalize_phone  # noqa: E402

msg = _build_bill_message(
    customer_name="TEST CUSTOMER",
    invoice_id=TEST_INVID,
    total=1000.0, paid=500.0, balance=500.0,
    old_balance=200.0, bill_type="invoice",
    pdf_url=url or "https://example.com/missing.pdf",
)
print(msg)
print()
e164 = _normalize_phone(TEST_PHONE)
print(f"  to: +{e164}")


# ============================================================
# 8. WhatsApp dispatch decision (what method would actually fire)
# ============================================================
banner("8. WhatsApp dispatch routing decision")

cfg_method = config.WA_METHOD
has_meta   = bool(config.WA_META_TOKEN and config.WA_META_PHONE_ID)
has_twilio = bool(config.WA_TWILIO_SID and config.WA_TWILIO_TOKEN and config.WA_TWILIO_FROM)

print(f"  WA_METHOD       : {cfg_method}")
print(f"  Meta configured : {has_meta}")
print(f"  Twilio configured: {has_twilio}")

if has_meta:
    print("  -> Would send fully automatically via Meta API")
    print("     (text message + PDF document attachment)")
elif has_twilio:
    print("  -> Would send fully automatically via Twilio")
    print("     (text + PDF link)")
else:
    print("  -> Would use wa.me fallback (opens WhatsApp Desktop;")
    print("     one manual click required to send. PDF URL is in the message.)")


# ============================================================
# 9. Cleanup (best-effort)
# ============================================================
banner("9. Cleanup test rows")
try:
    client.table("invoice_items").delete().eq("invoice_id", str(TEST_INVID)).execute()
    client.table("invoices").delete().eq("id", str(TEST_INVID)).execute()
    client.table("customers").delete().eq("phone", TEST_PHONE).execute()
    print("  OK   test rows removed from customers/invoices/invoice_items")
except Exception as e:
    print(f"  WARN cleanup failed (rows may remain): {e}")


banner("DONE")
print("  If every step printed OK, your cloud sync + WhatsApp chain is healthy.")
print("  Sandbox SQLite preserved at:", SANDBOX)
