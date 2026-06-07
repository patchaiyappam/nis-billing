import sqlite3, os

db = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL", "billing.db")
out = os.path.join(os.path.expanduser("~"), "Desktop", "NIS_CHECK.txt")

con = sqlite3.connect(db)
con.row_factory = sqlite3.Row
lines = []

lines.append("=== invoice_items columns ===")
cols = [r[1] for r in con.execute("PRAGMA table_info(invoice_items)")]
lines.append(str(cols))
lines.append("")

lines.append("=== invoice_items (last 30 rows) ===")
for r in con.execute("SELECT * FROM invoice_items ORDER BY id DESC LIMIT 30").fetchall():
    lines.append(str(dict(r)))
lines.append("")

lines.append("=== Total invoice_items count ===")
count = con.execute("SELECT COUNT(*) FROM invoice_items").fetchone()[0]
lines.append(str(count))

with open(out, "w") as f:
    f.write("\n".join(lines))

print("Saved to Desktop/NIS_CHECK.txt")
input("Press Enter to close...")
