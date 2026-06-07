"""
Pending List Frame — NEW INDIAN STEEL
======================================
Shows all customers with a pending (non-zero) balance.
Features:
  - Live search by name / phone / ID
  - Sorted by due amount (highest first) by default
  - Click column header to re-sort
  - Double-click row → opens CustomerDetailPopup
  - Summary bar: total customers pending, total amount due
  - Refresh button
"""
import tkinter as tk
from tkinter import ttk, messagebox

from config import COLORS, FONTS
from logger import get_logger
import database as db

log = get_logger(__name__)


def _card(parent, **kw):
    return tk.Frame(parent, bg=COLORS["card_bg"],
                    highlightbackground=COLORS["card_border"],
                    highlightthickness=1, **kw)


class PendingFrame(tk.Frame):
    """Customer-wise pending dues list."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self._sort_col  = "due"
        self._sort_asc  = False   # highest due first by default
        self._all_rows  = []      # cached full list
        self._date_from = tk.StringVar()
        self._date_to   = tk.StringVar()
        self._build_ui()

    # ── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────
        toolbar = tk.Frame(self, bg=COLORS["primary"])
        toolbar.pack(fill="x")

        tk.Label(toolbar, text="⏳  Customer Pending List",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["primary"], fg="#FFFFFF"
                 ).pack(side="left", padx=20, pady=14)

        # Refresh button
        tk.Button(toolbar, text="🔄 Refresh",
                  font=FONTS["button"], bg=COLORS["info"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self.refresh
                  ).pack(side="right", padx=(0, 12), pady=10)

        # Search box
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filter())
        se = tk.Entry(toolbar, textvariable=self.search_var,
                      font=FONTS["input"], width=26,
                      bg="white", fg="#1A1A2E", relief="flat",
                      highlightbackground="#CBD5E1", highlightthickness=1)
        se.pack(side="right", ipady=5, padx=(0, 6), pady=10)
        tk.Label(toolbar, text="🔍 Search name / phone / ID",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#BFDBFE"
                 ).pack(side="right")

        # Date filter row
        date_row = tk.Frame(self, bg=COLORS["primary"])
        date_row.pack(fill="x")

        tk.Label(date_row, text="📅 Last Bill Date — From:",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#BFDBFE"
                 ).pack(side="left", padx=(20, 4), pady=6)
        from_e = tk.Entry(date_row, textvariable=self._date_from,
                          font=FONTS["input"], width=12,
                          bg="white", fg="#1A1A2E", relief="flat",
                          highlightbackground="#CBD5E1", highlightthickness=1)
        from_e.pack(side="left", ipady=4, pady=6)
        tk.Label(date_row, text="YYYY-MM-DD",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#7FB3D0"
                 ).pack(side="left", padx=(2, 16))

        tk.Label(date_row, text="To:",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#BFDBFE"
                 ).pack(side="left", padx=(0, 4))
        to_e = tk.Entry(date_row, textvariable=self._date_to,
                        font=FONTS["input"], width=12,
                        bg="white", fg="#1A1A2E", relief="flat",
                        highlightbackground="#CBD5E1", highlightthickness=1)
        to_e.pack(side="left", ipady=4, pady=6)
        tk.Label(date_row, text="YYYY-MM-DD",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#7FB3D0"
                 ).pack(side="left", padx=(2, 8))

        tk.Button(date_row, text="Apply",
                  font=FONTS["small"], bg=COLORS["info"], fg="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._apply_filter
                  ).pack(side="left", pady=6)
        tk.Button(date_row, text="Clear",
                  font=FONTS["small"], bg="#64748B", fg="white",
                  relief="flat", padx=10, pady=4, cursor="hand2",
                  command=self._clear_date_filter
                  ).pack(side="left", padx=(4, 0), pady=6)

        # ── Summary bar ───────────────────────────────────────
        self.summary_bar = tk.Frame(self, bg="#FFF7ED",
                                    highlightbackground="#FED7AA",
                                    highlightthickness=1)
        self.summary_bar.pack(fill="x", padx=20, pady=(12, 0))

        self.lbl_count = tk.Label(self.summary_bar, text="",
                                   font=FONTS["body_bold"],
                                   bg="#FFF7ED", fg=COLORS["warning"])
        self.lbl_count.pack(side="left", padx=20, pady=8)

        self.lbl_total = tk.Label(self.summary_bar, text="",
                                   font=("Segoe UI", 14, "bold"),
                                   bg="#FFF7ED", fg=COLORS["danger"])
        self.lbl_total.pack(side="right", padx=20, pady=8)

        tk.Label(self.summary_bar, text="Total Outstanding →",
                 font=FONTS["small"], bg="#FFF7ED",
                 fg=COLORS["text_muted"]).pack(side="right")

        # ── List card ─────────────────────────────────────────
        list_card = _card(self)
        list_card.pack(fill="both", expand=True, padx=20, pady=(8, 0))
        tk.Frame(list_card, bg=COLORS["danger"], height=3).pack(fill="x")

        hdr = tk.Frame(list_card, bg=COLORS["card_bg"])
        hdr.pack(fill="x", padx=16, pady=(10, 4))
        self.count_lbl = tk.Label(hdr, text="",
                                   font=FONTS["subheading"],
                                   bg=COLORS["card_bg"], fg="#1A1A2E")
        self.count_lbl.pack(side="left")
        tk.Label(hdr, text="Double-click to view customer details",
                 font=FONTS["small"], bg=COLORS["card_bg"],
                 fg=COLORS["text_muted"]).pack(side="right")

        # Treeview
        cols = ("sno", "id", "name", "phone", "due", "last_bill")
        self.tree = ttk.Treeview(list_card, columns=cols,
                                  show="headings", height=20)

        # Column definitions
        col_defs = [
            ("sno",       "S.No",        55,  "center"),
            ("id",        "ID",          55,  "center"),
            ("name",      "Customer Name", 220, "w"),
            ("phone",     "Phone",       120, "center"),
            ("due",       "Due Amount ₹", 120, "e"),
            ("last_bill", "Last Bill",   110, "center"),
        ]
        for col, hd, w, anch in col_defs:
            self.tree.heading(col, text=hd,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=w, anchor=anch)

        # Row tags
        self.tree.tag_configure("high",   background="#FEF2F2", foreground="#DC2626")
        self.tree.tag_configure("medium", background="#FFFBEB", foreground="#D97706")
        self.tree.tag_configure("low",    background="#F0FDF4", foreground="#16A34A")

        sb = ttk.Scrollbar(list_card, orient="vertical",
                           command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True,
                       padx=(16, 0), pady=(0, 12))
        sb.pack(side="right", fill="y", pady=(0, 12), padx=(0, 6))

        self.tree.bind("<Double-1>", lambda e: self._open_detail())
        self.tree.bind("<Return>",   lambda e: self._open_detail())

        # ── Bottom action bar ─────────────────────────────────
        act = tk.Frame(self, bg=COLORS["content_bg"])
        act.pack(fill="x", padx=20, pady=(6, 12))

        tk.Button(act, text="👤  View Customer",
                  font=FONTS["button"], bg=COLORS["primary"], fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self._open_detail
                  ).pack(side="left", padx=(0, 8))

        tk.Button(act, text="🔴  NIL Balance  (zero out selected customer)",
                  font=FONTS["button"], bg="#7B241C", fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self._nil_balance
                  ).pack(side="left", padx=(0, 8))

        # Load data
        self._load_data()

    # ── Data ──────────────────────────────────────────────────

    def refresh(self):
        """Called when tab is shown or Refresh clicked."""
        self._load_data()

    def _load_data(self):
        """Fetch all customers with pending due and cache them."""
        try:
            rows = db.get_pending_customers_today()   # [{name, phone, total_due}]
            # Enrich with ID
            enriched = []
            for r in rows:
                cust = db.get_customer(r["phone"])
                enriched.append({
                    "id":             cust["id"] if cust else 0,
                    "name":           r["name"],
                    "phone":          r["phone"],
                    "due":            float(r["total_due"]),
                    "last_bill_date": r.get("last_bill_date") or "",
                })
            self._all_rows = enriched
        except Exception as e:
            log.error("PendingFrame load error: %s", e)
            self._all_rows = []
        self._apply_filter()

    def _clear_date_filter(self):
        self._date_from.set("")
        self._date_to.set("")
        self._apply_filter()

    def _apply_filter(self):
        """Filter cached rows by search query and date range, then re-render."""
        q      = self.search_var.get().strip().lower()
        d_from = self._date_from.get().strip()
        d_to   = self._date_to.get().strip()
        rows   = self._all_rows
        if q:
            rows = [r for r in rows if
                    q in r["name"].lower() or
                    q in r["phone"] or
                    q in str(r["id"])]
        if d_from:
            rows = [r for r in rows if (r.get("last_bill_date") or "") >= d_from]
        if d_to:
            rows = [r for r in rows if (r.get("last_bill_date") or "") <= d_to + "Z"]

        # Sort
        reverse = not self._sort_asc
        if self._sort_col == "due":
            rows = sorted(rows, key=lambda r: r["due"], reverse=reverse)
        elif self._sort_col == "name":
            rows = sorted(rows, key=lambda r: r["name"].lower(), reverse=reverse)
        elif self._sort_col == "id":
            rows = sorted(rows, key=lambda r: r["id"], reverse=reverse)
        elif self._sort_col == "phone":
            rows = sorted(rows, key=lambda r: r["phone"], reverse=reverse)
        elif self._sort_col == "last_bill":
            rows = sorted(rows, key=lambda r: r.get("last_bill_date") or "", reverse=reverse)
        # sno: keep original order

        self._render(rows)

    def _render(self, rows):
        self.tree.delete(*self.tree.get_children())

        total_due = sum(r["due"] for r in rows)
        count = len(rows)

        self.count_lbl.config(text=f"{count} Customer(s) with pending dues")
        self.lbl_count.config(text=f"⚠  {count} customers pending")
        self.lbl_total.config(text=f"₹{total_due:,.2f}")

        # Update column header arrows
        for col in ("sno", "id", "name", "phone", "due", "last_bill"):
            label = {"sno": "S.No", "id": "ID", "name": "Customer Name",
                     "phone": "Phone", "due": "Due Amount ₹",
                     "last_bill": "Last Bill"}[col]
            if col == self._sort_col:
                arrow = " ▲" if self._sort_asc else " ▼"
                self.tree.heading(col, text=label + arrow)
            else:
                self.tree.heading(col, text=label)

        for i, r in enumerate(rows, 1):
            due = r["due"]
            if due >= 10000:
                tag = "high"
            elif due >= 2000:
                tag = "medium"
            else:
                tag = "low"

            lb = r.get("last_bill_date") or ""
            lb_str = lb[:10] if lb else "—"
            self.tree.insert("", "end",
                iid=r["phone"],
                tags=(tag,),
                values=(
                    i,
                    r["id"],
                    r["name"],
                    r["phone"],
                    f"₹{due:,.2f}",
                    lb_str,
                ))

    def _sort_by(self, col):
        if self._sort_col == col:
            self._sort_asc = not self._sort_asc
        else:
            self._sort_col = col
            self._sort_asc = (col != "due")   # due defaults descending
        self._apply_filter()

    # ── Actions ───────────────────────────────────────────────

    def _open_detail(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Click a customer row first.")
            return
        phone = sel[0]   # iid is phone
        from ui.history_frame import CustomerDetailPopup
        CustomerDetailPopup(self, phone)

    def _nil_balance(self):
        """Zero out the selected customer's outstanding balance."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("NIL Balance", "Select a customer row first.")
            return
        phone = sel[0]
        c = db.get_customer(phone)
        if not c:
            messagebox.showerror("NIL Balance", "Customer not found.")
            return
        due = c.get("total_due", 0) or 0
        if due <= 0:
            messagebox.showinfo("NIL Balance",
                f"{c['name']} already has ₹0.00 balance.")
            return
        if not messagebox.askyesno(
            "NIL Balance — Confirm",
            f"Customer  : {c['name']}\n"
            f"Current Due : ₹{due:,.2f}\n\n"
            f"This will set the balance to ₹0.00 immediately.\n"
            f"A write-off record is saved for audit.\n\n"
            f"Proceed?",
            icon="warning"
        ):
            return
        try:
            payment_id, wiped = db.nil_customer_balance(phone)
            try:
                from task_queue import add_task
                if payment_id:
                    add_task("cloud_sync", {"phone": phone, "payment_id": payment_id})
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("NIL Balance Failed", str(e))
            return
        messagebox.showinfo("NIL Balance Done",
            f"✅ ₹{wiped:,.2f} wiped for {c['name']}.\n"
            f"Balance is now ₹0.00.")
        self._load_data()   # refresh list — customer should disappear
