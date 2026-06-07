"""
sync_now.py — One-time full sync of all local data to Supabase.
Run this from your shop PC to push all existing invoices/customers to cloud.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import sqlite3
import json

try:
    from supabase import create_client
    SUPABASE_OK = True
except ImportError:
    print("ERROR: supabase package not installed.")
    print("Run:  pip install supabase")
    sys.exit(1)

from config import SUPABASE_URL, SUPABASE_KEY, DB_PATH

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL or SUPABASE_KEY not set in config.py")
    sys.exit(1)

print("Connecting to Supabase...")
try:
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("Connected OK.\n")
except Exception as e:
    print(f"Connection failed: {e}")
    sys.exit(1)

# Use local DB path
db_path = DB_PATH
if not os.path.exists(db_path):
    # Try local billing.db
    db_path = os.path.join(os.path.dirname(__file__), "billing.db")

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
print(f"Database: {db_path}\n")

errors = 0

def sync_table(label, table, rows, conflict_col="id"):
    global errors
    if not rows:
        print(f"  {label}: nothing to sync")
        return
    try:
        sb.table(table).upsert(rows, on_conflict=conflict_col).execute()
        print(f"  ✓ {label}: {len(rows)} records synced")
    except Exception as e:
        print(f"  ✗ {label} FAILED: {e}")
        errors += 1

print("=" * 48)
print("  Syncing all data to Supabase...")
print("=" * 48)

# Customers
customers = [dict(r) for r in conn.execute("SELECT * FROM customers")]
sync_table("Customers", "customers",
    [{"phone": c["phone"], "name": c["name"],
      "total_due": c.get("total_due", 0)} for c in customers],
    conflict_col="phone")

# Invoices
invoices = [dict(r) for r in conn.execute("SELECT * FROM invoices")]
sync_table("Invoices", "invoices", [
    {"id": i["id"],
     "customer_phone": i.get("customer_phone",""),
     "customer_name":  i.get("customer_name",""),
     "total":   i.get("total",0),
     "paid":    i.get("paid",0),
     "balance": i.get("balance",0),
     "date":    str(i.get("date","")),
     "type":    i.get("type","invoice"),
     "pdf_url": i.get("pdf_url","") or ""}
    for i in invoices])

# Invoice items
items = [dict(r) for r in conn.execute(
    "SELECT ii.*, p.name as pname FROM invoice_items ii "
    "LEFT JOIN products p ON ii.product_id=p.id")]
sync_table("Invoice items", "invoice_items", [
    {"id":           item["id"],
     "invoice_id":   item["invoice_id"],
     "product_id":   item.get("product_id"),
     "product_name": item.get("pname") or "",
     "qty":    item.get("qty",0),
     "price":  item.get("price",0),
     "amount": item.get("amount",0)}
    for item in items])

# Payments
payments = [dict(r) for r in conn.execute("SELECT * FROM payments")]
sync_table("Payments", "payments", [
    {"id":             p["id"],
     "customer_phone": p.get("customer_phone",""),
     "customer_name":  p.get("customer_name",""),
     "amount": p.get("amount",0),
     "date":   str(p.get("date",""))}
    for p in payments])

conn.close()
print()
print("=" * 48)
if errors == 0:
    print("  ALL DATA SYNCED SUCCESSFULLY ✓")
    print()
    print("  Go to supabase.com → Table Editor")
    print("  to see all your customers and invoices.")
else:
    print(f"  SYNC DONE WITH {errors} ERROR(S)")
    print("  Check internet connection and try again.")
print("=" * 48)
