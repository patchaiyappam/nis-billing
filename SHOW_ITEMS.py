"""Shows invoice_items for recent invoices in a popup window."""
import sqlite3, os, tkinter as tk
from tkinter import scrolledtext

DB = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL", "billing.db")
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

lines = []

# Columns in invoice_items
cols = [r[1] for r in con.execute("PRAGMA table_info(invoice_items)")]
lines.append(f"invoice_items columns: {cols}\n")

# Recent invoice_items
rows = con.execute("SELECT * FROM invoice_items ORDER BY id DESC LIMIT 30").fetchall()
lines.append(f"Total invoice_items rows: {con.execute('SELECT COUNT(*) FROM invoice_items').fetchone()[0]}\n")
lines.append("Recent invoice_items:")
for r in rows:
    lines.append(f"  {dict(r)}")

# Check specific invoices
lines.append("\nPer-invoice item counts:")
for inv in con.execute("SELECT id, total FROM invoices ORDER BY id DESC LIMIT 10").fetchall():
    count = con.execute("SELECT COUNT(*) FROM invoice_items WHERE invoice_id=?", (inv['id'],)).fetchone()[0]
    lines.append(f"  INV-{inv['id']} (₹{inv['total']:.0f}): {count} items")

# Show in popup
root = tk.Tk()
root.title("Invoice Items Diagnostic")
root.geometry("800x500")
st = scrolledtext.ScrolledText(root, font=("Consolas", 10))
st.pack(fill="both", expand=True)
st.insert("end", "\n".join(lines))
st.config(state="disabled")
tk.Button(root, text="Close", command=root.destroy, pady=8).pack()
root.mainloop()
