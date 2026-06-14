"""
Dashboard Frame — Daily Business Overview
==========================================
Shows 3 daily metric cards, recent activity tables, and low stock alerts.
All data is queried from the database — no PDF, no charts.

Cards (all clickable):
  Total Bill Amount (blue)  |  Total Received (green)  |  Total Credit (red)

Sections:
  Recent Invoices (5) | Recent Payments (5) | Low Stock table
"""
import tkinter as tk
from tkinter import ttk
from datetime import datetime

from config import COLORS, FONTS
from logger import get_logger
import database as db

log = get_logger(__name__)


def _card(parent, **kw):
    """Create a styled card frame."""
    return tk.Frame(
        parent,
        bg=COLORS["card_bg"],
        highlightbackground=COLORS["card_border"],
        highlightthickness=1,
        **kw,
    )


class DashboardFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self._build_ui()

    # ── Scrollable shell ──────────────────────────────────

    def _build_ui(self):
        canvas = tk.Canvas(self, bg=COLORS["content_bg"], highlightthickness=0)
        sb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=COLORS["content_bg"])
        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        win = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canvas.bind(
            "<Enter>",
            lambda e: canvas.bind_all(
                "<MouseWheel>",
                lambda ev: canvas.yview_scroll(-1 * (ev.delta // 120), "units"),
            ),
        )
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))
        self._build_content()

    # ── Content layout ────────────────────────────────────

    def _build_content(self):
        P = {"padx": 24, "pady": (20, 0)}

        # ── Banner ───────────────────────────────────────
        banner = tk.Frame(self.inner, bg=COLORS["primary"])
        banner.pack(fill="x", **P)
        row = tk.Frame(banner, bg=COLORS["primary"])
        row.pack(fill="x", padx=20, pady=14)
        tk.Label(
            row, text="📊  Business Dashboard",
            font=("Segoe UI", 13, "bold"),
            bg=COLORS["primary"], fg="#FFFFFF",
        ).pack(side="left")
        tk.Label(
            row,
            text=datetime.now().strftime("Today  •  %A, %d %B %Y"),
            font=FONTS["small"], bg=COLORS["primary"], fg="#BFDBFE",
        ).pack(side="right")

        # ── Section heading ───────────────────────────────
        tk.Label(
            self.inner, text="Today's Summary",
            font=FONTS["subheading"], bg=COLORS["content_bg"],
            fg=COLORS["text_muted"],
        ).pack(anchor="w", padx=24, pady=(20, 8))

        # ── 3 Metric cards ────────────────────────────────
        # (key, label, sub-label, default, accent_color, icon, callback)
        CARD_DEFS = [
            ("bill_amt",  "Total Bill Amount",   "Today's invoices",  "₹0",
             COLORS["primary"], "🧾", self._show_invoices_popup),
            ("recv_amt",  "Total Received",       "Today's payments",  "₹0",
             COLORS["success"], "💰", self._show_payments_popup),
            ("credit_amt","Total Credit",         "Pending balances",  "₹0",
             COLORS["danger"],  "⏳", self._show_credit_popup),
        ]

        cards_frame = tk.Frame(self.inner, bg=COLORS["content_bg"])
        cards_frame.pack(fill="x", padx=24)

        self.metric_vars = {}
        for i, (key, label, sub, default, color, icon, callback) in enumerate(CARD_DEFS):
            c = _card(cards_frame)
            c.grid(row=0, column=i, padx=(0, 0 if i == 2 else 16), sticky="nsew")
            cards_frame.columnconfigure(i, weight=1)

            # Accent top bar
            tk.Frame(c, bg=color, height=5).pack(fill="x")

            inner = tk.Frame(c, bg=COLORS["card_bg"])
            inner.pack(fill="both", expand=True, padx=18, pady=14)

            # Icon + sub-label row
            top = tk.Frame(inner, bg=COLORS["card_bg"])
            top.pack(fill="x")
            tk.Label(top, text=icon, font=("Segoe UI", 15),
                     bg=COLORS["card_bg"]).pack(side="left")
            tk.Label(top, text=sub, font=("Segoe UI", 10),
                     bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(side="right")

            # Card title
            tk.Label(inner, text=label, font=FONTS["small_bold"],
                     bg=COLORS["card_bg"], fg=COLORS["text_muted"]
                     ).pack(anchor="w", pady=(4, 0))

            # Big value
            var = tk.StringVar(value=default)
            self.metric_vars[key] = var
            val_lbl = tk.Label(inner, textvariable=var, font=FONTS["metric"],
                               bg=COLORS["card_bg"], fg=color)
            val_lbl.pack(anchor="w", pady=(2, 0))

            # Click hint
            hint = tk.Label(inner, text="Tap to view details →",
                            font=("Segoe UI", 10),
                            bg=COLORS["card_bg"], fg=COLORS["text_muted"])
            hint.pack(anchor="w", pady=(2, 0))

            # Bind click on all child widgets
            cb = callback  # capture in closure
            for w in (c, inner, top, val_lbl, hint):
                w.bind("<Button-1>", lambda e, fn=cb: fn())
                w.configure(cursor="hand2")

        # ── Recent Activity heading ───────────────────────
        tk.Label(
            self.inner, text="Recent Activity",
            font=FONTS["subheading"], bg=COLORS["content_bg"],
            fg=COLORS["text_muted"],
        ).pack(anchor="w", padx=24, pady=(24, 8))

        # ── Two-column: invoices + payments ──────────────
        two_col = tk.Frame(self.inner, bg=COLORS["content_bg"])
        two_col.pack(fill="x", padx=24)
        two_col.columnconfigure(0, weight=1)
        two_col.columnconfigure(1, weight=1)

        # Left — Recent Invoices
        left = _card(two_col)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        tk.Label(left, text="🧾  Recent Invoices", font=FONTS["subheading"],
                 bg=COLORS["card_bg"], fg=COLORS["text_dark"]
                 ).pack(anchor="w", padx=16, pady=(14, 6))

        inv_cols = ("inv_id", "customer", "time", "total", "status")
        self.inv_tree = ttk.Treeview(left, columns=inv_cols, show="headings", height=6)
        for col, hd, w, anch in [
            ("inv_id",   "Invoice",  90,  "center"),
            ("customer", "Customer", 155, "w"),
            ("time",     "Time",     65,  "center"),
            ("total",    "Amount",   100, "e"),
            ("status",   "Status",   75,  "center"),
        ]:
            self.inv_tree.heading(col, text=hd)
            self.inv_tree.column(col, width=w, anchor=anch, stretch=True)

        isb = ttk.Scrollbar(left, orient="vertical", command=self.inv_tree.yview)
        self.inv_tree.configure(yscrollcommand=isb.set)
        self.inv_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 14))
        isb.pack(side="right", fill="y", pady=(0, 14), padx=(0, 8))

        self.inv_tree.tag_configure("paid",    background="#F0FDF4", foreground="#16A34A")
        self.inv_tree.tag_configure("partial", background="#FFFBEB", foreground="#D97706")
        self.inv_tree.tag_configure("unpaid",  background="#FEF2F2", foreground="#DC2626")

        # Right — Recent Payments
        right = _card(two_col)
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="💰  Recent Payments", font=FONTS["subheading"],
                 bg=COLORS["card_bg"], fg=COLORS["text_dark"]
                 ).pack(anchor="w", padx=16, pady=(14, 6))

        pay_cols = ("pay_id", "customer", "time", "amount")
        self.pay_tree = ttk.Treeview(right, columns=pay_cols, show="headings", height=6)
        for col, hd, w, anch in [
            ("pay_id",   "Pay ID",   85,  "center"),
            ("customer", "Customer", 170, "w"),
            ("time",     "Time",     70,  "center"),
            ("amount",   "Amount",   100, "e"),
        ]:
            self.pay_tree.heading(col, text=hd)
            self.pay_tree.column(col, width=w, anchor=anch, stretch=True)

        psb = ttk.Scrollbar(right, orient="vertical", command=self.pay_tree.yview)
        self.pay_tree.configure(yscrollcommand=psb.set)
        self.pay_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=(0, 14))
        psb.pack(side="right", fill="y", pady=(0, 14), padx=(0, 8))

        # ── Reference Pending section ─────────────────────
        tk.Label(
            self.inner, text="🤝  Reference Pending  (referrers with unpaid referred sales)",
            font=FONTS["subheading"], bg=COLORS["content_bg"],
            fg=COLORS["text_muted"],
        ).pack(anchor="w", padx=24, pady=(24, 8))

        ref_card = _card(self.inner)
        ref_card.pack(fill="x", padx=24, pady=(0, 4))
        ref_cols = ("ref_name", "ref_phone", "bills", "pending")
        self.ref_tree = ttk.Treeview(ref_card, columns=ref_cols, show="headings", height=6)
        for col, hd, w, anch in [
            ("ref_name",  "Referrer",   210, "w"),
            ("ref_phone", "Phone",      140, "center"),
            ("bills",     "Bills",       70, "center"),
            ("pending",   "Pending",    120, "e"),
        ]:
            self.ref_tree.heading(col, text=hd)
            self.ref_tree.column(col, width=w, anchor=anch, stretch=True)
        rsb = ttk.Scrollbar(ref_card, orient="vertical", command=self.ref_tree.yview)
        self.ref_tree.configure(yscrollcommand=rsb.set)
        self.ref_tree.pack(side="left", fill="both", expand=True, padx=(12, 0), pady=12)
        rsb.pack(side="right", fill="y", pady=12, padx=(0, 8))

        # ── Low Stock section ─────────────────────────────
        tk.Label(
            self.inner, text="📦  Low Stock Alert",
            font=FONTS["subheading"], bg=COLORS["content_bg"],
            fg=COLORS["text_muted"],
        ).pack(anchor="w", padx=24, pady=(24, 8))

        self.stock_card = _card(self.inner)
        self.stock_card.pack(fill="x", padx=24, pady=(0, 4))
        self.stock_inner = tk.Frame(self.stock_card, bg=COLORS["card_bg"])
        self.stock_inner.pack(fill="both", expand=True, padx=0, pady=0)

        # Bottom spacer
        tk.Frame(self.inner, bg=COLORS["content_bg"], height=24).pack()

    # ── Refresh (called when tab activated) ──────────────

    def refresh(self):
        """Reload all dashboard data from DB — called whenever Dashboard tab is shown."""
        try:
            self._refresh_cards()
            self._refresh_recent_invoices()
            self._refresh_recent_payments()
            self._refresh_reference()
            self._refresh_low_stock()
        except Exception as e:
            log.error("Dashboard refresh error: %s", e, exc_info=True)

    def _refresh_cards(self):
        """Update 3 daily metric cards from fresh DB queries."""
        try:
            summary   = db.get_today_sales_summary()
            bill_amt  = summary.get("total_sales", 0.0)    # sum of invoice totals today
            credit_amt = summary.get("total_balance", 0.0) # sum of today's remaining balances
            recv_amt  = db.get_today_collection_total()      # payments + paid-on-invoice today

            self.metric_vars["bill_amt"].set(f"₹{bill_amt:,.0f}")
            self.metric_vars["recv_amt"].set(f"₹{recv_amt:,.0f}")
            self.metric_vars["credit_amt"].set(f"₹{credit_amt:,.0f}")

            log.debug("Dashboard cards refreshed: bill=%.0f recv=%.0f credit=%.0f",
                      bill_amt, recv_amt, credit_amt)
        except Exception as e:
            log.error("Card refresh error: %s", e, exc_info=True)

    def _refresh_recent_invoices(self):
        """Populate the 5-row recent invoices tree."""
        self.inv_tree.delete(*self.inv_tree.get_children())
        try:
            for inv in db.get_recent_invoices(limit=5):
                bal  = inv.get("balance", 0)
                paid = inv.get("paid", 0)
                if bal <= 0:
                    status, tag = "Paid", "paid"
                elif paid > 0:
                    status, tag = "Partial", "partial"
                else:
                    status, tag = "Unpaid", "unpaid"

                prefix   = "QUO" if inv.get("type") == "quotation" else "INV"
                date_str = inv.get("date", "")
                time_str = date_str[11:16] if len(date_str) > 11 else date_str[:10]

                self.inv_tree.insert("", "end", tags=(tag,), values=(
                    f"{prefix}-{inv['id']}",
                    inv.get("customer_name", "")[:18],
                    time_str,
                    f"₹{inv['total']:,.0f}",
                    status,
                ))
        except Exception as e:
            log.error("Recent invoices refresh error: %s", e, exc_info=True)

    def _refresh_recent_payments(self):
        """Populate the 5-row recent payments tree."""
        self.pay_tree.delete(*self.pay_tree.get_children())
        try:
            for pay in db.get_recent_payments(limit=5):
                date_str = pay.get("date", "")
                time_str = date_str[11:16] if len(date_str) > 11 else date_str[:10]
                self.pay_tree.insert("", "end", values=(
                    f"PAY-{pay['id']}",
                    pay.get("customer_name", "")[:22],
                    time_str,
                    f"₹{pay['amount']:,.0f}",
                ))
        except Exception as e:
            log.error("Recent payments refresh error: %s", e, exc_info=True)

    def _refresh_reference(self):
        """Populate the reference-pending table: referrers + unpaid total."""
        self.ref_tree.delete(*self.ref_tree.get_children())
        try:
            for r in db.get_reference_pending_totals():
                self.ref_tree.insert("", "end", values=(
                    (r.get("ref_name") or "")[:26],
                    r.get("ref_phone", ""),
                    r.get("bills", 0),
                    f"₹{(r.get('pending') or 0):,.0f}",
                ))
        except Exception as e:
            log.error("Reference pending refresh error: %s", e, exc_info=True)

    def _refresh_low_stock(self):
        """Rebuild the low stock product table."""
        for w in self.stock_inner.winfo_children():
            w.destroy()
        try:
            products = db.get_low_stock_products()

            if not products:
                tk.Label(
                    self.stock_inner,
                    text="✅  All products are sufficiently stocked.",
                    font=FONTS["body"], bg=COLORS["card_bg"], fg=COLORS["success"],
                ).pack(anchor="w", padx=16, pady=14)
                return

            # Column header bar
            hdr = tk.Frame(self.stock_inner, bg=COLORS["table_header_bg"])
            hdr.pack(fill="x")
            for text, expand, anchor in [
                ("Product Name",   True,  "w"),
                ("Current Stock",  False, "center"),
                ("Min Stock",      False, "center"),
            ]:
                tk.Label(
                    hdr, text=text, font=FONTS["small_bold"],
                    bg=COLORS["table_header_bg"], fg=COLORS["table_header_fg"],
                    anchor=anchor, width=14 if not expand else None,
                ).pack(side="left", padx=14, pady=7, fill="x" if expand else None,
                       expand=expand)

            # Product rows
            for i, p in enumerate(products):
                is_critical = (p["stock"] == 0)
                row_bg = "#FEF2F2" if is_critical else (
                    COLORS["card_bg"] if i % 2 == 0 else COLORS["table_row_alt"]
                )
                row = tk.Frame(self.stock_inner, bg=row_bg)
                row.pack(fill="x")

                # Product name (expands)
                name_fg = COLORS["danger"] if is_critical else COLORS["text_dark"]
                tk.Label(
                    row, text=p["name"],
                    font=FONTS["body"], bg=row_bg, fg=name_fg, anchor="w",
                ).pack(side="left", padx=14, pady=6, fill="x", expand=True)

                # Stock value
                stock_text  = "OUT OF STOCK" if p["stock"] == 0 else str(p["stock"])
                stock_color = COLORS["danger"] if is_critical else COLORS["warning"]
                tk.Label(
                    row, text=stock_text, font=FONTS["body_bold"],
                    bg=row_bg, fg=stock_color, width=14, anchor="center",
                ).pack(side="left")

                # Min stock
                tk.Label(
                    row, text=str(p["min_stock"]), font=FONTS["body"],
                    bg=row_bg, fg=COLORS["text_muted"], width=14, anchor="center",
                ).pack(side="left")

        except Exception as e:
            log.error("Low stock refresh error: %s", e, exc_info=True)

    # ── Popup helpers ─────────────────────────────────────

    def _make_popup(self, title, header_text, header_color, strip_text, geometry="860x520"):
        """Create a standard popup shell and return (popup, tree_frame)."""
        popup = tk.Toplevel(self)
        popup.title(title)
        popup.geometry(geometry)
        popup.configure(bg=COLORS["content_bg"])
        popup.transient(self)
        popup.grab_set()
        popup.resizable(True, True)

        hdr = tk.Frame(popup, bg=header_color)
        hdr.pack(fill="x")
        tk.Label(hdr, text=header_text, font=FONTS["heading"],
                 bg=header_color, fg="#FFFFFF").pack(side="left", padx=20, pady=14)
        tk.Button(hdr, text="✕ Close", font=FONTS["small"],
                  bg=header_color, fg="#BFDBFE", relief="flat",
                  cursor="hand2", command=popup.destroy).pack(side="right", padx=16)

        tk.Label(popup, text=strip_text, font=FONTS["small"],
                 bg=COLORS["info_light"], fg=header_color, anchor="w"
                 ).pack(fill="x", ipadx=6, ipady=7)

        frame = tk.Frame(popup, bg=COLORS["content_bg"])
        frame.pack(fill="both", expand=True, padx=16, pady=12)
        return popup, frame

    def _build_tree(self, parent, col_defs):
        """Build a Treeview with scrollbar and return the tree widget."""
        tree = ttk.Treeview(parent, columns=[c[0] for c in col_defs], show="headings")
        for col, hd, w, anch in col_defs:
            tree.heading(col, text=hd)
            tree.column(col, width=w, anchor=anch, stretch=True)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        return tree

    # ── Popup 1: Total Bill Amount → Today's Invoices ─────

    def _show_invoices_popup(self):
        """Show today's invoices detail when Total Bill card is clicked."""
        log.info("Opening today's invoices popup.")
        try:
            s = db.get_today_sales_summary()
            strip = (
                f"  Total Billed: ₹{s.get('total_sales', 0):,.2f}   |   "
                f"Invoices: {s.get('invoice_count', 0)}   |   "
                f"Paid on Invoice: ₹{s.get('total_paid', 0):,.2f}   |   "
                f"Balance: ₹{s.get('total_balance', 0):,.2f}"
            )
        except Exception:
            strip = "  Could not load summary."

        _, frame = self._make_popup(
            title="Today's Bill Amount — Invoices",
            header_text="🧾  Today's Total Bill Amount",
            header_color=COLORS["primary"],
            strip_text=strip,
        )

        tree = self._build_tree(frame, [
            ("time",     "Time",     80,  "center"),
            ("customer", "Customer", 240, "w"),
            ("total",    "Total",    120, "e"),
            ("paid",     "Paid",     120, "e"),
            ("balance",  "Balance",  120, "e"),
        ])
        tree.tag_configure("paid",    background="#F0FDF4", foreground="#16A34A")
        tree.tag_configure("partial", background="#FFFBEB", foreground="#D97706")
        tree.tag_configure("unpaid",  background="#FEF2F2", foreground="#DC2626")

        try:
            rows = db.get_today_sales()
            if not rows:
                tree.insert("", "end", values=("—", "No invoices today", "—", "—", "—"))
            else:
                for inv in rows:
                    bal  = inv.get("balance", 0)
                    paid = inv.get("paid", 0)
                    tag  = "paid" if bal <= 0 else ("partial" if paid > 0 else "unpaid")
                    ds   = inv.get("date", "")
                    tree.insert("", "end", tags=(tag,), values=(
                        ds[11:16] if len(ds) > 11 else "—",
                        inv.get("customer_name", "")[:30],
                        f"₹{inv['total']:,.2f}",
                        f"₹{inv['paid']:,.2f}",
                        f"₹{inv['balance']:,.2f}",
                    ))
        except Exception as e:
            log.error("Invoices popup error: %s", e, exc_info=True)
            tree.insert("", "end", values=("", "Error loading data", "", "", ""))

    # ── Popup 2: Total Received → Today's Payments ────────

    def _show_payments_popup(self):
        """Show today's payment entries + paid-on-invoice amounts."""
        log.info("Opening today's payments popup.")
        try:
            total     = db.get_today_collection_total()
            pays      = db.get_today_payments()
            inv_paid  = db.get_today_sales_summary().get("total_paid", 0)
            pay_total = db.get_today_payments_total()
            strip = (
                f"  Total Collected: ₹{total:,.2f}   |   "
                f"Payments: ₹{pay_total:,.2f}   |   "
                f"Paid on Bill: ₹{inv_paid:,.2f}"
            )
        except Exception:
            strip = "  Could not load summary."
            pays  = []
            inv_paid = 0

        _, frame = self._make_popup(
            title="Today's Received Amount — Payments",
            header_text="💰  Today's Total Received",
            header_color=COLORS["success"],
            strip_text=strip,
        )

        tree = self._build_tree(frame, [
            ("pay_id",   "Pay ID",   90,  "center"),
            ("time",     "Time",     80,  "center"),
            ("customer", "Customer", 340, "w"),
            ("type",     "Type",     120, "center"),
            ("amount",   "Amount",   130, "e"),
        ])

        try:
            rows = []
            # Payment entries
            for pay in pays:
                ds = pay.get("date", "")
                rows.append((
                    f"PAY-{pay['id']}",
                    ds[11:16] if len(ds) > 11 else "—",
                    pay.get("customer_name", "")[:38],
                    "Payment",
                    f"₹{pay['amount']:,.2f}",
                ))
            # Paid-on-invoice entries (invoices with paid > 0 today)
            try:
                for inv in db.get_today_invoices():
                    p = inv.get("paid", 0) or 0
                    if p > 0:
                        ds = inv.get("date", "")
                        rows.append((
                            f"INV-{inv['id']}",
                            ds[11:16] if len(ds) > 11 else "—",
                            inv.get("customer_name", "")[:38],
                            "Paid on Bill",
                            f"₹{p:,.2f}",
                        ))
            except Exception:
                pass

            if not rows:
                tree.insert("", "end", values=("—", "—", "No collections today", "—", "—"))
            else:
                for row in rows:
                    tree.insert("", "end", values=row)
        except Exception as e:
            log.error("Payments popup error: %s", e, exc_info=True)
            tree.insert("", "end", values=("", "", "Error loading data", "", ""))

    # ── Popup 3: Total Credit → Pending Customers ─────────

    def _show_credit_popup(self):
        """Show all customers with outstanding balance when Total Credit is clicked."""
        log.info("Opening pending credit customers popup.")
        try:
            pending = db.get_pending_customers_today()
            total   = sum(c["total_due"] for c in pending)
            strip   = (
                f"  Total Pending Credit: ₹{total:,.2f}   |   "
                f"Customers: {len(pending)}"
            )
        except Exception:
            strip   = "  Could not load summary."
            pending = []

        _, frame = self._make_popup(
            title="Total Credit — Pending Customers",
            header_text="⏳  Pending Credit Balances",
            header_color=COLORS["danger"],
            strip_text=strip,
            geometry="760x500",
        )

        tree = self._build_tree(frame, [
            ("no",       "#",           45,  "center"),
            ("customer", "Customer",   320, "w"),
            ("phone",    "Phone",       160, "center"),
            ("due",      "Amount Due",  160, "e"),        ])
        tree.tag_configure("high", background="#FEF2F2", foreground="#DC2626")
        tree.tag_configure("med",  background="#FFFBEB", foreground="#D97706")

        try:
            if not pending:
                tree.insert("", "end", values=("—", "No pending customers", "—", "—"))
            else:
                for i, c in enumerate(pending, 1):
                    due = c.get("total_due", 0) or 0
                    tag = "high" if due >= 10000 else ("med" if due >= 2000 else "")
                    tree.insert("", "end", tags=(tag,), values=(
                        i,
                        c.get("name", "")[:40],
                        c.get("phone", ""),
                        f"₹{due:,.2f}",
                    ))
        except Exception as e:
            log.error("Credit popup error: %s", e, exc_info=True)
            tree.insert("", "end", values=("", "Error loading data", "", ""))

    # ══════════════════════════════════════════════════════
    # POPUP HELPERS
    # ══════════════════════════════════════════════════════

    def _make_popup(self, title, header_text, header_color,
                    strip_text="", geometry="900x540"):
        popup = tk.Toplevel(self)
        popup.title(title)
        popup.geometry(geometry)
        popup.configure(bg=COLORS["content_bg"])
        popup.transient(self.winfo_toplevel())
        popup.grab_set()

        hdr = tk.Frame(popup, bg=header_color, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text=header_text,
                 font=("Segoe UI", 14, "bold"),
                 bg=header_color, fg="#FFFFFF"
                 ).pack(side="left", padx=20)
        tk.Button(hdr, text="✕", font=FONTS["body"],
                  bg=header_color, fg="#FFFFFF",
                  relief="flat", cursor="hand2",
                  command=popup.destroy
                  ).pack(side="right", padx=12)

        if strip_text:
            strip = tk.Frame(popup, bg=COLORS["table_header_bg"])
            strip.pack(fill="x")
            tk.Label(strip, text=strip_text,
                     font=FONTS["small_bold"],
                     bg=COLORS["table_header_bg"],
                     fg=COLORS["text_dark"]
                     ).pack(side="left", padx=12, pady=6)

        frame = tk.Frame(popup, bg=COLORS["content_bg"])
        frame.pack(fill="both", expand=True, padx=12, pady=8)
        return popup, frame

    def _build_tree(self, parent, col_defs):
        cols = [c[0] for c in col_defs]
        tree = ttk.Treeview(parent, columns=cols, show="headings", height=14)
        for col, heading, width, anchor in col_defs:
            tree.heading(col, text=heading)
            tree.column(col, width=width, anchor=anchor)
        sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree
