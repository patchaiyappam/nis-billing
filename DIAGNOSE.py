"""Run this to diagnose invoice_items issue."""
import sqlite3, os

DB = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL", "billing.db")
OUT = os.path.join(os.path.expanduser("~"), "Desktop", "DIAGNOSE.txt")

con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row
lines = []

lines.append("=== invoice_items columns ===")
cols = [r[1] for r in con.execute("PRAGMA table_info(invoice_items)")]
lines.append(str(cols))

lines.append("\n=== schema_version (applied migrations) ===")
try:
    for r in con.execute("SELECT * FROM schema_version ORDER BY version"):
        lines.append(str(dict(r)))
except Exception as e:
    lines.append(f"Error: {e}")

lines.append("\n=== invoice_items for INV-20 (raw) ===")
try:
    for r in con.execute("SELECT * FROM invoice_items WHERE invoice_id=20"):
        lines.append(str(dict(r)))
except Exception as e:
    lines.append(f"Error: {e}")

lines.append("\n=== ALL invoice_items (last 20) ===")
try:
    for r in con.execute("SELECT * FROM invoice_items ORDER BY id DESC LIMIT 20"):
        lines.append(str(dict(r)))
except Exception as e:
    lines.append(f"Error: {e}")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Saved to {OUT}")
input("Press Enter to close...")
