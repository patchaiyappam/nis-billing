"""
Billing Frame — Dark theme, large fonts, product search, atomic invoicing
"""
import tkinter as tk
from tkinter import ttk, messagebox
import os, sys, subprocess

from config import COLORS, FONTS
from logger import get_logger
from database import (
    get_customer, get_product, get_invoice, get_invoice_items,
    search_products, create_invoice_atomic, find_customer, get_all_customers,
)
from whatsapp import send_bill_message
from billing_workflow import run_billing_workflow  # automated 10-step workflow

log = get_logger(__name__)


def _open_file(path):
    try:
        if sys.platform == "win32":    os.startfile(path)
        elif sys.platform == "darwin": subprocess.run(["open", path])
        else:                          subprocess.run(["xdg-open", path])
    except Exception: pass

def _print_file(path):
    try:
        if sys.platform == "win32":    os.startfile(path, "print")
        else:                          subprocess.run(["lpr", path])
    except Exception: pass


def _card(parent, accent=None):
    f = tk.Frame(parent, bg=COLORS["card_bg"],
                 highlightbackground=COLORS["card_border"],
                 highlightthickness=1)
    if accent:
        tk.Frame(f, bg=accent, height=4).pack(fill="x")
    return f

def _lbl(parent, text, font=None, color="text_medium", **kw):
    return tk.Label(parent, text=text,
                    font=font or FONTS["body"],
                    bg=parent.cget("bg"),
                    fg=COLORS[color], **kw)

def _entry(parent, var, width=16, state="normal", **kw):
    return tk.Entry(parent, textvariable=var,
                    font=FONTS["input"], width=width,
                    bg=COLORS["input_bg"],
                    fg="#1A1A2E",
                    insertbackground="#1B3A6B",
                    disabledbackground=COLORS["card_bg"],
                    disabledforeground="#AAAAAA",
                    readonlybackground=COLORS["card_bg"],
                    relief="flat",
                    highlightbackground=COLORS["input_border"],
                    highlightcolor=COLORS["primary"],
                    highlightthickness=2,
                    state=state, **kw)

def _btn(parent, text, bg, fg="#fff", cmd=None, pady=10, padx=18):
    b = tk.Button(parent, text=text, font=FONTS["button"],
                  bg=COLORS[bg], fg=fg, relief="flat",
                  activebackground=COLORS.get(bg+"_hover", COLORS[bg]),
                  activeforeground=fg,
                  cursor="hand2", padx=padx, pady=pady,
                  command=cmd)
    return b

def _section(parent, title, accent):
    f = _card(parent, accent=accent)
    f.pack(fill="x", padx=20, pady=(0, 10))
    inner = tk.Frame(f, bg=COLORS["card_bg"])
    inner.pack(fill="x", padx=18, pady=14)
    _lbl(inner, title, FONTS["subheading"], "text_dark").pack(anchor="w", pady=(0, 10))
    return inner


class BillingFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self.items = []
        self.current_customer = None
        self._build_ui()

    def _build_ui(self):
        canvas = tk.Canvas(self, bg=COLORS["content_bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self.container = tk.Frame(canvas, bg=COLORS["content_bg"])
        win = canvas.create_window((0, 0), window=self.container, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(win, width=e.width))
        self.container.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def _scroll(e): canvas.yview_scroll(int(-1*(e.delta/120)), "units")
        canvas.bind("<Enter>",  lambda e: canvas.bind_all("<MouseWheel>", _scroll))
        canvas.bind("<Leave>",  lambda e: canvas.unbind_all("<MouseWheel>"))

        tk.Frame(self.container, bg=COLORS["content_bg"], height=16).pack()

        self._build_customer_section()
        self._build_item_section()
        self._build_items_table()
        self._build_summary_section()

        tk.Frame(self.container, bg=COLORS["content_bg"], height=24).pack()

    # ── SECTION 1: Customer ───────────────────────────────
    def _build_customer_section(self):
        inner = _section(self.container, "👤  Customer Details", COLORS["primary"])

        # ── Row 1: Three search boxes side by side ────────
        search_row = tk.Frame(inner, bg=COLORS["card_bg"])
        search_row.pack(fill="x", pady=(0, 4))

        # Shared suggestion state
        self._cust_sugg_data   = []
        self._cust_selecting   = False
        self._active_sugg_frame = None

        def _make_search_box(parent, label, var, width, field):
            """Build one labelled search entry + its own dropdown listbox."""
            frame = tk.Frame(parent, bg=COLORS["card_bg"])
            _lbl(frame, label, color="text_muted").pack(anchor="w")
            entry = _entry(frame, var, width=width)
            entry.pack(anchor="w", pady=(4, 0))

            lb_frame = tk.Frame(frame, bg=COLORS["card_bg"])
            lb = tk.Listbox(lb_frame, font=FONTS["body"], height=6,
                            bg=COLORS["input_bg"], fg="#1A1A2E",
                            selectbackground=COLORS["primary"],
                            selectforeground="#FFFFFF",
                            relief="flat", highlightthickness=1,
                            highlightbackground=COLORS["input_border"],
                            width=width + 5)
            lb.pack(fill="x")

            def on_type(*_):
                if self._cust_selecting:
                    return
                q = var.get().strip()
                if not q:
                    lb_frame.pack_forget()
                    lb.delete(0, tk.END)
                    return
                try:
                    all_c = get_all_customers()
                except Exception:
                    return
                q_low = q.lower()
                if field == "id":
                    matches = [c for c in all_c if str(c.get("id","")).startswith(q)]
                elif field == "name":
                    matches = [c for c in all_c if q_low in (c.get("name") or "").lower()]
                else:  # phone
                    matches = [c for c in all_c if q in (c.get("phone") or "")]
                matches = matches[:8]
                self._cust_sugg_data = matches
                lb.delete(0, tk.END)
                for c in matches:
                    due = c.get("total_due", 0) or 0
                    lb.insert(tk.END,
                        f"  [{c['id']}]  {c['name'][:20]}  {c['phone']}  Due:₹{due:,.0f}")
                if matches:
                    if self._active_sugg_frame and self._active_sugg_frame is not lb_frame:
                        self._active_sugg_frame.pack_forget()
                    lb_frame.pack(fill="x", pady=(0, 4))
                    lb.selection_set(0)
                    self._active_sugg_frame = lb_frame
                else:
                    lb_frame.pack_forget()

            def on_select(e=None):
                sel = lb.curselection()
                if not sel or not self._cust_sugg_data:
                    return
                c = self._cust_sugg_data[sel[0]]
                self._cust_selecting = True
                # Fill all three search vars
                self._id_search_var.set(str(c.get("id","")))
                self._name_search_var.set(c["name"])
                self._phone_search_var.set(c["phone"])
                self._cust_selecting = False
                lb_frame.pack_forget()
                lb.delete(0, tk.END)
                self._active_sugg_frame = None
                self._load_customer(c)
                self._recalculate()
                # ── Auto-advance to Reference field ──────────
                self.after(50, self._focus_ref)

            def nav_down(e):
                cur = lb.curselection()
                idx = (cur[0] + 1) if cur else 0
                if idx < lb.size():
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(idx); lb.see(idx)

            def nav_up(e):
                cur = lb.curselection()
                idx = (cur[0] - 1) if cur else 0
                if idx >= 0:
                    lb.selection_clear(0, tk.END)
                    lb.selection_set(idx); lb.see(idx)

            var.trace_add("write", on_type)
            entry.bind("<Return>",  on_select)
            entry.bind("<Down>",    nav_down)
            entry.bind("<Up>",      nav_up)
            entry.bind("<Escape>",  lambda e: lb_frame.pack_forget())
            lb.bind("<Double-1>",   on_select)
            lb.bind("<Return>",     on_select)
            return frame

        self._id_search_var    = tk.StringVar()
        self._name_search_var  = tk.StringVar()
        self._phone_search_var = tk.StringVar()
        # phone_var used by billing logic — keep it pointing to phone
        self.phone_var = self._phone_search_var

        id_box   = _make_search_box(search_row, "🔢 Customer ID",   self._id_search_var,   10, "id")
        name_box = _make_search_box(search_row, "👤 Customer Name", self._name_search_var, 22, "name")
        phone_box= _make_search_box(search_row, "📞 Phone Number",  self._phone_search_var,16, "phone")
        id_box.pack(side="left", padx=(0, 16))
        name_box.pack(side="left", padx=(0, 16))
        phone_box.pack(side="left", padx=(0, 16))

        # ── New Customer quick-add button ─────────────────
        add_cust_frame = tk.Frame(search_row, bg=COLORS["card_bg"])
        add_cust_frame.pack(side="left", anchor="s", pady=(0, 4))
        _lbl(add_cust_frame, " ", color="text_muted").pack(anchor="w")   # spacer label
        _btn(add_cust_frame, "➕  New Customer", "success",
             cmd=self._quick_add_customer).pack(anchor="w", pady=(4, 0))

        # ── Walk-in / Cash Sale button ─────────────────────
        walkin_frame = tk.Frame(search_row, bg=COLORS["card_bg"])
        walkin_frame.pack(side="left", anchor="s", padx=(10, 0), pady=(0, 4))
        _lbl(walkin_frame, " ", color="text_muted").pack(anchor="w")
        _btn(walkin_frame, "🚶  Walk-in Sale", "warning",
             cmd=self._set_walkin_customer).pack(anchor="w", pady=(4, 0))

        # ── Row 2: Resolved name display + Bill Type ──────
        row2 = tk.Frame(inner, bg=COLORS["card_bg"])
        row2.pack(fill="x", pady=(8, 0))

        nf = tk.Frame(row2, bg=COLORS["card_bg"])
        nf.pack(side="left")
        _lbl(nf, "Customer Name (auto-filled)", color="text_muted").pack(anchor="w")
        self.name_var = tk.StringVar()
        self.name_entry = _entry(nf, self.name_var, width=24)
        self.name_entry.pack(pady=4)

        # Bill type
        tf = tk.Frame(row2, bg=COLORS["card_bg"])
        tf.pack(side="left", padx=(32, 0))
        _lbl(tf, "Bill Type", color="text_muted").pack(anchor="w")
        self.type_var = tk.StringVar(value="invoice")
        rb = tk.Frame(tf, bg=COLORS["card_bg"])
        rb.pack(pady=4)
        for txt, val in [("Invoice","invoice"),("Quotation","quotation")]:
            tk.Radiobutton(rb, text=txt, variable=self.type_var, value=val,
                           font=FONTS["body"], bg=COLORS["card_bg"],
                           fg=COLORS["text_medium"],
                           selectcolor=COLORS["card_bg"],
                           activebackground=COLORS["card_bg"],
                           command=self._on_type_change
                           ).pack(side="left", padx=8)

        # ── Reference row — live-search dropdown ──────────
        ref_row = tk.Frame(inner, bg=COLORS["card_bg"])
        ref_row.pack(fill="x", pady=(6, 0))

        rf = tk.Frame(ref_row, bg=COLORS["card_bg"])
        rf.pack(side="left", fill="x")

        _lbl(rf, "Referred By (optional) — type Name / Phone / ID",
             color="text_muted").pack(anchor="w")
        ref_inp = tk.Frame(rf, bg=COLORS["card_bg"])
        ref_inp.pack(anchor="w", pady=4)

        self.ref_search_var = tk.StringVar()   # what user types
        self.ref_phone_var  = tk.StringVar()   # resolved phone (stored in invoice)
        self.ref_name_var   = tk.StringVar()   # resolved name

        self._ref_entry = _entry(ref_inp, self.ref_search_var, width=26)
        self._ref_entry.pack(side="left")

        _btn(ref_inp, "✕ Clear", "divider", cmd=self._clear_reference
             ).pack(side="left", padx=(6, 0))

        # Live-search dropdown listbox
        ref_lb_frame = tk.Frame(rf, bg=COLORS["card_bg"])
        self._ref_lb = tk.Listbox(
            ref_lb_frame, font=FONTS["body"], height=5,
            bg=COLORS["input_bg"], fg="#1A1A2E",
            selectbackground=COLORS["primary"],
            selectforeground="#FFFFFF",
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS["input_border"],
            width=44)
        self._ref_lb.pack(fill="x")
        self._ref_sugg_data = []

        def _ref_on_type(*_):
            if self._cust_selecting:
                return
            q = self.ref_search_var.get().strip()
            if not q:
                ref_lb_frame.pack_forget()
                self._ref_lb.delete(0, tk.END)
                return
            try:
                all_c = get_all_customers()
            except Exception:
                return
            q_low = q.lower()
            matches = [c for c in all_c if
                       q_low in (c.get("name") or "").lower() or
                       q in (c.get("phone") or "") or
                       str(c.get("id", "")).startswith(q)][:6]
            self._ref_sugg_data = matches
            self._ref_lb.delete(0, tk.END)
            for c in matches:
                due = c.get("total_due", 0) or 0
                self._ref_lb.insert(
                    tk.END,
                    f"  [{c['id']}]  {c['name'][:20]}  {c['phone']}  Due:₹{due:,.0f}")
            if matches:
                ref_lb_frame.pack(fill="x", pady=(0, 4))
                self._ref_lb.selection_set(0)
            else:
                ref_lb_frame.pack_forget()

        def _ref_select(e=None):
            sel = self._ref_lb.curselection()
            if not sel or not self._ref_sugg_data:
                return
            c = self._ref_sugg_data[sel[0]]
            self.ref_search_var.set(c["name"])
            self.ref_phone_var.set(c["phone"])
            self.ref_name_var.set(c["name"])
            ref_lb_frame.pack_forget()
            self._ref_lb.delete(0, tk.END)
            self.ref_status.config(
                text=f"✓  Referred by: [{c.get('id','')}] {c['name']}  ({c['phone']})",
                fg=COLORS["success"])
            self.after(50, self._focus_product_search)

        def _ref_nav_down(e):
            cur = self._ref_lb.curselection()
            idx = (cur[0] + 1) if cur else 0
            if idx < self._ref_lb.size():
                self._ref_lb.selection_clear(0, tk.END)
                self._ref_lb.selection_set(idx); self._ref_lb.see(idx)

        def _ref_nav_up(e):
            cur = self._ref_lb.curselection()
            idx = (cur[0] - 1) if cur else 0
            if idx >= 0:
                self._ref_lb.selection_clear(0, tk.END)
                self._ref_lb.selection_set(idx); self._ref_lb.see(idx)

        self.ref_search_var.trace_add("write", _ref_on_type)
        self._ref_entry.bind("<Return>",
            lambda e: _ref_select() or self._focus_product_search())
        self._ref_entry.bind("<Down>",   _ref_nav_down)
        self._ref_entry.bind("<Up>",     _ref_nav_up)
        self._ref_entry.bind("<Escape>", lambda e: ref_lb_frame.pack_forget())
        self._ref_lb.bind("<Double-1>",  _ref_select)
        self._ref_lb.bind("<Return>",    _ref_select)

        # Status label showing resolved reference name
        self.ref_status = tk.Label(rf, text="No reference selected",
                                   font=FONTS["small"],
                                   bg=COLORS["card_bg"], fg=COLORS["text_muted"])
        self.ref_status.pack(anchor="w")

        # Status bar
        self.cust_status = tk.Label(inner, text="",
                                    font=FONTS["body_bold"],
                                    bg=COLORS["card_bg"], fg=COLORS["text_muted"])
        self.cust_status.pack(anchor="w", pady=(6,0))

    # ── SECTION 2: Add Item + Product Search ─────────────
    def _build_item_section(self):
        inner = _section(self.container, "📦  Add Item", COLORS["success"])

        # Row 0: Product search
        search_row = tk.Frame(inner, bg=COLORS["card_bg"])
        search_row.pack(fill="x", pady=(0, 8))
        _lbl(search_row, "🔍 Search Product by Name:", color="text_medium").pack(side="left")
        self.search_var = tk.StringVar()
        self._search_entry = _entry(search_row, self.search_var, width=32)
        self._search_entry.pack(side="left", padx=(8, 0))
        self.search_var.trace_add("write", self._on_search_typed)
        self._search_entry.bind("<Down>", self._search_nav_down)
        self._search_entry.bind("<Up>", self._search_nav_up)
        self._search_entry.bind("<Return>", self._search_select)
        self._search_entry.bind("<Escape>", lambda e: self._hide_suggestions())

        # Suggestion listbox (hidden by default)
        self._suggestion_frame = tk.Frame(inner, bg=COLORS["card_bg"])
        self._suggestion_lb = tk.Listbox(
            self._suggestion_frame, font=FONTS["body"], height=6,
            bg=COLORS["input_bg"], fg="#1A1A2E",
            selectbackground=COLORS["primary"], selectforeground="#FFFFFF",
            relief="flat", highlightthickness=1,
            highlightbackground=COLORS["input_border"])
        self._suggestion_lb.pack(fill="x")
        self._suggestion_lb.bind("<Double-1>", self._search_select)
        self._suggestion_lb.bind("<Return>", self._search_select)
        self._suggestion_data = []  # matching product dicts

        row = tk.Frame(inner, bg=COLORS["card_bg"])
        row.pack(fill="x")

        # Product ID
        idf = tk.Frame(row, bg=COLORS["card_bg"])
        idf.pack(side="left")
        _lbl(idf, "Product ID", color="text_muted").pack(anchor="w")
        self.pid_var = tk.StringVar()
        pe = _entry(idf, self.pid_var, width=6)
        pe.pack(side="left", pady=6)
        pe.bind("<Return>", lambda e: self._fetch_product())
        _btn(idf, "🔍", "primary", cmd=self._fetch_product, padx=10
             ).pack(side="left", padx=(4,0), pady=6)

        # Product name
        pnf = tk.Frame(row, bg=COLORS["card_bg"])
        pnf.pack(side="left", padx=(18,0))
        _lbl(pnf, "Product Name", color="text_muted").pack(anchor="w")
        self.pname_var = tk.StringVar()
        _entry(pnf, self.pname_var, width=24, state="readonly").pack(pady=6)

        # Price — EDITABLE
        prf = tk.Frame(row, bg=COLORS["card_bg"])
        prf.pack(side="left", padx=(18,0))
        _lbl(prf, "Price (₹)  ✏ Editable", color="warning").pack(anchor="w")
        self.pprice_var = tk.StringVar()
        self._price_entry = _entry(prf, self.pprice_var, width=10)
        self._price_entry.pack(pady=6)
        self._price_entry.bind("<Return>", lambda e: self._price_enter())
        self.pprice_var.trace_add("write", self._update_item_amount_preview)

        # Qty
        qf = tk.Frame(row, bg=COLORS["card_bg"])
        qf.pack(side="left", padx=(18,0))
        _lbl(qf, "Quantity", color="text_muted").pack(anchor="w")
        self.qty_var = tk.StringVar(value="0")
        self._qty_entry = _entry(qf, self.qty_var, width=8)
        self._qty_entry.pack(side="left", pady=6)
        self._qty_entry.bind("<Return>", lambda e: self._add_item())
        self.qty_var.trace_add("write", self._update_item_amount_preview)

        # Preview amount
        self.preview_var = tk.StringVar(value="Amount: ₹0.00")
        tk.Label(qf, textvariable=self.preview_var,
                 font=FONTS["small_bold"], bg=COLORS["card_bg"],
                 fg=COLORS["warning"]).pack(side="left", padx=(10,0), pady=6)

        _btn(inner, "➕  Add Item to Bill", "success",
             cmd=self._add_item).pack(anchor="w", pady=(8,0))

    # ── Product Search Helpers ────────────────────────────
    def _on_search_typed(self, *_):
        query = self.search_var.get().strip()
        if len(query) < 1:
            self._hide_suggestions()
            return
        try:
            results = search_products(query)
        except Exception as e:
            log.error("Product search failed: %s", e)
            return
        self._suggestion_data = results
        self._suggestion_lb.delete(0, tk.END)
        for p in results:
            self._suggestion_lb.insert(tk.END, f"  [{p['id']}]  {p['name']}  —  ₹{p['price']:,.2f}")
        if results:
            self._suggestion_frame.pack(fill="x", pady=(0, 6))
            self._suggestion_lb.selection_set(0)
        else:
            self._hide_suggestions()

    def _hide_suggestions(self):
        self._suggestion_frame.pack_forget()
        self._suggestion_lb.delete(0, tk.END)
        self._suggestion_data = []

    def _search_nav_down(self, e):
        if not self._suggestion_data:
            return
        cur = self._suggestion_lb.curselection()
        idx = (cur[0] + 1) if cur else 0
        if idx < len(self._suggestion_data):
            self._suggestion_lb.selection_clear(0, tk.END)
            self._suggestion_lb.selection_set(idx)
            self._suggestion_lb.see(idx)

    def _search_nav_up(self, e):
        if not self._suggestion_data:
            return
        cur = self._suggestion_lb.curselection()
        idx = (cur[0] - 1) if cur else 0
        if idx >= 0:
            self._suggestion_lb.selection_clear(0, tk.END)
            self._suggestion_lb.selection_set(idx)
            self._suggestion_lb.see(idx)

    def _search_select(self, e=None):
        sel = self._suggestion_lb.curselection()
        if not sel or not self._suggestion_data:
            return
        p = self._suggestion_data[sel[0]]
        self.pid_var.set(str(p["id"]))
        self.pname_var.set(p["name"])
        self.pprice_var.set(f"{p['price']:.2f}")
        self.search_var.set("")
        self._hide_suggestions()
        log.debug("Product selected via search: #%d %s", p["id"], p["name"])
        # ── Auto-advance to Price field ───────────────────
        self.after(30, self._focus_price)

    # ── SECTION 3: Items Table ────────────────────────────
    def _build_items_table(self):
        f = _card(self.container)
        f.pack(fill="x", padx=20, pady=(0,10))
        inner = tk.Frame(f, bg=COLORS["card_bg"])
        inner.pack(fill="both", expand=True)

        cols = ("no","product","qty","price","amount")
        self.tree = ttk.Treeview(inner, columns=cols, show="headings", height=7)

        style = ttk.Style()
        style.configure("Treeview",
            font=FONTS["body"], rowheight=36,
            background=COLORS["card_bg"],
            fieldbackground=COLORS["card_bg"],
            foreground=COLORS["text_dark"],
            borderwidth=0)
        style.configure("Treeview.Heading",
            font=FONTS["small_bold"],
            background=COLORS["table_header_bg"],
            foreground=COLORS["table_header_fg"],
            relief="flat")
        style.map("Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", "#FFFFFF")])

        for col, hd, w, anc in [
            ("no","#",50,"center"),("product","Product",320,"w"),
            ("qty","Qty",80,"center"),("price","Price ₹",130,"e"),
            ("amount","Amount ₹",150,"e")]:
            self.tree.heading(col, text=hd)
            self.tree.column(col, width=w, anchor=anc)

        sb = ttk.Scrollbar(inner, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(12,0), pady=10)
        sb.pack(side="right", fill="y", pady=10, padx=(0,8))

        rm_row = tk.Frame(self.container, bg=COLORS["content_bg"])
        rm_row.pack(fill="x", padx=20, pady=(0,4))
        _btn(rm_row, "🗑  Remove Selected Item", "danger",
             cmd=self._remove_item).pack(side="right")

    # ── SECTION 4: Summary ────────────────────────────────
    def _build_summary_section(self):
        f = _card(self.container, accent=COLORS["warning"])
        f.pack(fill="x", padx=20, pady=(0,10))
        inner = tk.Frame(f, bg=COLORS["card_bg"])
        inner.pack(fill="x", padx=18, pady=16)

        _lbl(inner, "📋  Bill Summary", FONTS["subheading"], "text_dark").pack(anchor="w", pady=(0,14))

        # ── Row: Current Bill Amount ──
        r1 = tk.Frame(inner, bg=COLORS["card_bg"])
        r1.pack(fill="x", pady=4)
        _lbl(r1, "Current Bill Amount:", FONTS["body_bold"], "text_muted").pack(side="left")
        self.subtotal_var = tk.StringVar(value="₹  0.00")
        tk.Label(r1, textvariable=self.subtotal_var,
                 font=("Segoe UI", 15, "bold"),
                 bg=COLORS["card_bg"], fg=COLORS["text_dark"]).pack(side="right")

        # ── Row: Transport Charges ──
        r2 = tk.Frame(inner, bg=COLORS["card_bg"])
        r2.pack(fill="x", pady=4)
        _lbl(r2, "Transport Charges (₹):", FONTS["body"], "text_muted").pack(side="left")
        self.transport_var = tk.StringVar(value="0")
        te = _entry(r2, self.transport_var, width=12)
        te.pack(side="right", padx=(0,4))
        self.transport_var.trace_add("write", self._recalculate)

        # ── Row: Discount ──
        r3 = tk.Frame(inner, bg=COLORS["card_bg"])
        r3.pack(fill="x", pady=4)
        _lbl(r3, "Discount % (optional):", FONTS["body"], "text_muted").pack(side="left")
        self.discount_var = tk.StringVar(value="")
        de = _entry(r3, self.discount_var, width=8)
        de.pack(side="right", padx=(0,4))
        tk.Label(r3, text="%", font=FONTS["body_bold"],
                 bg=COLORS["card_bg"], fg=COLORS["warning"]).pack(side="right")
        self.discount_var.trace_add("write", self._recalculate)
        self.discount_amt_var = tk.StringVar(value="")
        self.discount_lbl = tk.Label(r3, textvariable=self.discount_amt_var,
                                     font=FONTS["small"], bg=COLORS["card_bg"],
                                     fg=COLORS["success"])
        self.discount_lbl.pack(side="right", padx=(0,12))

        # ── Divider ──
        tk.Frame(inner, bg=COLORS["divider"], height=2).pack(fill="x", pady=10)

        # ── Row: Grand Total ──
        r4 = tk.Frame(inner, bg=COLORS["card_bg"])
        r4.pack(fill="x", pady=4)
        _lbl(r4, "GRAND TOTAL:", FONTS["subheading"], "primary").pack(side="left")
        self.grand_total_var = tk.StringVar(value="₹  0.00")
        tk.Label(r4, textvariable=self.grand_total_var,
                 font=("Segoe UI", 22, "bold"),
                 bg=COLORS["card_bg"], fg=COLORS["primary"]).pack(side="right")

        # ── Row: Old Balance (editable for manual override) ──
        r5 = tk.Frame(inner, bg=COLORS["card_bg"])
        r5.pack(fill="x", pady=4)
        _lbl(r5, "Old Balance (previous due ₹):",
             FONTS["body"], "text_muted").pack(side="left")
        _lbl(r5, "(auto-filled when you search a customer — you can edit it)",
             FONTS["small"], "text_muted").pack(side="left", padx=(8,0))
        self.old_balance_var = tk.StringVar(value="0")
        self.old_balance_entry = _entry(r5, self.old_balance_var, width=14)
        self.old_balance_entry.pack(side="right", padx=(0,4))
        self.old_balance_var.trace_add("write", self._recalculate)

        # ── Divider ──
        tk.Frame(inner, bg=COLORS["divider"], height=2).pack(fill="x", pady=10)

        # ── Row: Payment Type ──
        r_pt = tk.Frame(inner, bg=COLORS["card_bg"])
        r_pt.pack(fill="x", pady=4)
        _lbl(r_pt, "Payment Type:", FONTS["body_bold"], "text_muted").pack(side="left")
        self.pay_type_var = tk.StringVar(value="Cash")
        pt_frame = tk.Frame(r_pt, bg=COLORS["card_bg"])
        pt_frame.pack(side="right")
        for txt, val in [("💵 Cash","Cash"),("📱 UPI","UPI"),
                         ("💳 Credit","Credit"),("🏦 Cheque","Cheque")]:
            tk.Radiobutton(pt_frame, text=txt, variable=self.pay_type_var, value=val,
                           font=FONTS["body"], bg=COLORS["card_bg"],
                           fg=COLORS["text_medium"],
                           selectcolor=COLORS["card_bg"],
                           activebackground=COLORS["card_bg"]
                           ).pack(side="left", padx=8)

        # ── Row: Amount Paid ──
        r6 = tk.Frame(inner, bg=COLORS["card_bg"])
        r6.pack(fill="x", pady=4)
        _lbl(r6, "Amount Paid Now (₹):", FONTS["body_bold"], "success").pack(side="left")
        _lbl(r6, "(extra payment allowed)", FONTS["small"], "text_muted").pack(side="left", padx=(8,0))
        self.paid_var = tk.StringVar(value="0")
        self.paid_entry = _entry(r6, self.paid_var, width=14)
        self.paid_entry.pack(side="right", padx=(0,4))
        self.paid_var.trace_add("write", self._recalculate)

        # ── Row: Net Balance ──
        r7 = tk.Frame(inner, bg=COLORS["card_bg"])
        r7.pack(fill="x", pady=6)
        _lbl(r7, "NET BALANCE DUE:", FONTS["subheading"], "danger").pack(side="left")
        self.net_balance_var = tk.StringVar(value="₹  0.00")
        self.net_balance_lbl = tk.Label(r7, textvariable=self.net_balance_var,
                                        font=("Segoe UI", 20, "bold"),
                                        bg=COLORS["card_bg"], fg=COLORS["danger"])
        self.net_balance_lbl.pack(side="right")

        # ── Extra payment note ──
        self.extra_note_var = tk.StringVar(value="")
        tk.Label(inner, textvariable=self.extra_note_var,
                 font=FONTS["body_bold"], bg=COLORS["card_bg"],
                 fg=COLORS["success"]).pack(anchor="e", pady=(2,8))

        # ── Generate Button ──
        tk.Frame(inner, bg=COLORS["divider"], height=2).pack(fill="x", pady=8)

        # ── Print Preview (no save) ──────────────────────────
        tk.Button(inner,
                  text="🖨️   PRINT PREVIEW  (Print Only — Nothing Saved)",
                  font=FONTS["button"],
                  bg="#7D6608", fg="white",
                  relief="flat", pady=10, cursor="hand2",
                  activebackground="#6E5A07",
                  activeforeground="white",
                  command=self._print_preview
                  ).pack(fill="x", pady=(0, 6))

        # ── Main Generate Bill button ────────────────────────
        gen = tk.Button(inner,
                        text="✅   SAVE BILL  (Save + Print + WhatsApp)",
                        font=("Segoe UI", 15, "bold"),
                        bg=COLORS["success"], fg="white",
                        relief="flat", pady=16, cursor="hand2",
                        activebackground="#1E8449",
                        activeforeground="white",
                        command=self._generate_bill)
        gen.pack(fill="x")

        # ── NIL Balance button (below Generate Bill) ──
        tk.Frame(inner, bg=COLORS["card_bg"], height=10).pack()
        nil = tk.Button(inner,
                        text="🔴   NIL Balance  (Close customer's old due to ₹0)",
                        font=FONTS["button"],
                        bg=COLORS["danger"], fg="white",
                        relief="flat", pady=12, cursor="hand2",
                        activebackground="#A93226",
                        activeforeground="white",
                        command=self._nil_balance)
        nil.pack(fill="x")

    # ── Calculations ──────────────────────────────────────
    def _is_number(self, s):
        try: float(s); return True
        except: return False

    def _recalculate(self, *_):
        subtotal = sum(i["amount"] for i in self.items)
        self.subtotal_var.set(f"₹  {subtotal:,.2f}")

        # Transport
        try: transport = float(self.transport_var.get() or 0)
        except: transport = 0.0
        transport = max(0, transport)

        # Discount
        try: disc_pct = float(self.discount_var.get() or 0)
        except: disc_pct = 0.0
        disc_pct = max(0, min(100, disc_pct))
        disc_amt = subtotal * disc_pct / 100
        if disc_pct > 0:
            self.discount_amt_var.set(f"(- ₹{disc_amt:,.2f})")
        else:
            self.discount_amt_var.set("")

        grand = subtotal - disc_amt + transport
        self.grand_total_var.set(f"₹  {grand:,.2f}")

        # Old balance — read from editable entry (auto-filled on customer search,
        # but the user can override it)
        try: old_bal = float(self.old_balance_var.get() or 0)
        except: old_bal = 0.0
        old_bal = max(0, old_bal)

        # Paid
        try: paid = float(self.paid_var.get() or 0)
        except: paid = 0.0
        paid = max(0, paid)

        net = grand + old_bal - paid
        self.net_balance_var.set(f"₹  {abs(net):,.2f}")

        if net < 0:
            self.net_balance_lbl.config(fg=COLORS["success"])
            self.net_balance_var.set(f"₹  {abs(net):,.2f}  (ADVANCE)")
            self.extra_note_var.set(f"✅ Extra payment of ₹{abs(net):,.2f} will be credited to next bill")
        elif net == 0:
            self.net_balance_lbl.config(fg=COLORS["success"])
            self.extra_note_var.set("✅ Fully paid — no balance due")
        else:
            self.net_balance_lbl.config(fg=COLORS["danger"])
            self.extra_note_var.set("")

    def _update_item_amount_preview(self, *_):
        try:
            price = float(self.pprice_var.get() or 0)
            qty = float(self.qty_var.get() or 0)
            self.preview_var.set(f"Amount: ₹{price*qty:,.2f}")
        except:
            self.preview_var.set("Amount: ₹0.00")

    # ── Fetch ─────────────────────────────────────────────
    def _on_type_change(self):
        if self.type_var.get() == "quotation":
            self.paid_var.set("0")
            self.paid_entry.config(state="disabled")
        else:
            self.paid_entry.config(state="normal")

    def _quick_add_customer(self):
        """
        Open a small dialog to add a new customer without leaving the billing screen.
        After saving, auto-fills the billing form with the new customer's details.
        """
        dialog = tk.Toplevel(self)
        dialog.title("➕  Add New Customer")
        dialog.geometry("420x340")
        dialog.configure(bg=COLORS["content_bg"])
        dialog.resizable(False, False)
        dialog.transient(self.winfo_toplevel())
        dialog.grab_set()

        # Header
        hdr = tk.Frame(dialog, bg=COLORS["success"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="➕  Add New Customer",
                 font=FONTS["heading"], bg=COLORS["success"], fg="white"
                 ).pack(side="left", padx=20, pady=12)

        body = tk.Frame(dialog, bg=COLORS["content_bg"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        def _field(label, var, placeholder=""):
            tk.Label(body, text=label, font=FONTS["small_bold"],
                     bg=COLORS["content_bg"], fg=COLORS["text_muted"]
                     ).pack(anchor="w", pady=(8, 2))
            e = tk.Entry(body, textvariable=var, font=FONTS["input"],
                         bg=COLORS["input_bg"], fg="#1A1A2E", relief="flat",
                         highlightbackground=COLORS["input_border"],
                         highlightcolor=COLORS["primary"],
                         highlightthickness=1)
            e.pack(fill="x", ipady=6)
            return e

        name_var    = tk.StringVar()
        phone_var   = tk.StringVar()
        address_var = tk.StringVar()
        ob_var      = tk.StringVar(value="0")

        name_entry = _field("Customer Name *", name_var)
        _field("Phone Number * (10 digits)", phone_var)
        _field("Address (optional)", address_var)
        _field("Opening Balance ₹ (old dues before this system)", ob_var)

        name_entry.focus_set()

        def _save():
            name  = name_var.get().strip()
            phone = phone_var.get().strip()
            addr  = address_var.get().strip()
            try:
                ob = max(0.0, float(ob_var.get().strip() or "0"))
            except ValueError:
                messagebox.showwarning("Error", "Opening balance must be a number.", parent=dialog)
                return
            if not name:
                messagebox.showwarning("Error", "Customer name is required.", parent=dialog)
                return
            if not phone or not phone.isdigit() or len(phone) != 10 or phone[0] not in "6789":
                messagebox.showwarning("Error", "Enter a valid 10-digit Indian phone number.", parent=dialog)
                return
            from database import get_customer, create_customer
            if get_customer(phone):
                messagebox.showwarning("Duplicate", f"A customer with phone {phone} already exists.", parent=dialog)
                return
            try:
                create_customer(name, phone, addr, ob)
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=dialog)
                return
            # Auto-fill billing form with the new customer
            dialog.destroy()
            c = get_customer(phone)
            if c:
                self.current_customer = c
                self._cust_selecting = True
                self._id_search_var.set(str(c.get("id", "")))
                self._name_search_var.set(c["name"])
                self._phone_search_var.set(c["phone"])
                self._cust_selecting = False
                self.name_var.set(c["name"])
                self.name_entry.config(state="readonly", bg=COLORS["card_bg"])
                self.old_balance_var.set(f"{ob:.2f}")
                self.cust_status.config(
                    text=f"✓  New customer saved  |  ID: {c.get('id','')}  |  {name}",
                    fg=COLORS["success"])
                self._recalculate()

        btn_row = tk.Frame(dialog, bg=COLORS["content_bg"])
        btn_row.pack(fill="x", padx=24, pady=(0, 16))
        tk.Button(btn_row, text="✅  Save Customer",
                  font=FONTS["button"], bg=COLORS["success"], fg="white",
                  relief="flat", padx=16, pady=8, cursor="hand2",
                  command=_save).pack(side="right")
        tk.Button(btn_row, text="Cancel",
                  font=FONTS["button"], bg=COLORS["divider"], fg="#1A1A2E",
                  relief="flat", padx=12, pady=8, cursor="hand2",
                  command=dialog.destroy).pack(side="right", padx=(0, 8))

        dialog.bind("<Return>", lambda e: _save())

    def _set_walkin_customer(self):
        """
        Set the billing form to Walk-in / Cash Sale mode.
        No customer account is tracked — invoice is saved to history only.
        Optionally enter a name for the printed bill (e.g. 'Mr. Kumar').
        """
        from database import get_or_create_walkin_customer, WALKIN_PHONE

        # Ask for an optional name to print on the bill
        name_dialog = tk.Toplevel(self)
        name_dialog.title("🚶  Walk-in / Cash Sale")
        name_dialog.geometry("380x200")
        name_dialog.configure(bg=COLORS["content_bg"])
        name_dialog.resizable(False, False)
        name_dialog.transient(self.winfo_toplevel())
        name_dialog.grab_set()

        hdr = tk.Frame(name_dialog, bg=COLORS["warning"])
        hdr.pack(fill="x")
        tk.Label(hdr, text="🚶  Walk-in / Cash Sale",
                 font=FONTS["heading"], bg=COLORS["warning"], fg="white"
                 ).pack(side="left", padx=20, pady=12)

        body = tk.Frame(name_dialog, bg=COLORS["content_bg"])
        body.pack(fill="both", expand=True, padx=24, pady=16)

        tk.Label(body, text="Customer Name for bill (optional)",
                 font=FONTS["small_bold"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]
                 ).pack(anchor="w", pady=(0, 4))
        name_var = tk.StringVar(value="Walk-in Customer")
        name_entry = tk.Entry(body, textvariable=name_var, font=FONTS["input"],
                              bg=COLORS["input_bg"], fg="#1A1A2E", relief="flat",
                              highlightbackground=COLORS["input_border"],
                              highlightcolor=COLORS["primary"],
                              highlightthickness=1)
        name_entry.pack(fill="x", ipady=6)
        name_entry.select_range(0, tk.END)
        name_entry.focus_set()

        def _apply():
            display_name = name_var.get().strip() or "Walk-in Customer"
            c = get_or_create_walkin_customer()
            if not c:
                messagebox.showerror("Error", "Could not create walk-in record.")
                name_dialog.destroy()
                return
            name_dialog.destroy()
            # Fill the billing form
            self.current_customer = c
            self._cust_selecting = True
            self._id_search_var.set("")
            self._name_search_var.set(display_name)
            self._phone_search_var.set(WALKIN_PHONE)
            self._cust_selecting = False
            self.name_var.set(display_name)
            self.name_entry.config(state="normal", bg="#FEF9E7")
            self.old_balance_var.set("0")
            self.cust_status.config(
                text="🚶  Walk-in Sale — invoice saved to history only, no account",
                fg=COLORS["warning"])
            self._recalculate()

        btn_row = tk.Frame(name_dialog, bg=COLORS["content_bg"])
        btn_row.pack(fill="x", padx=24, pady=(0, 14))
        tk.Button(btn_row, text="✅  Start Walk-in Bill",
                  font=FONTS["button"], bg=COLORS["warning"], fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=_apply).pack(side="right")
        tk.Button(btn_row, text="Cancel",
                  font=FONTS["button"], bg=COLORS["divider"], fg="#1A1A2E",
                  relief="flat", padx=12, pady=8, cursor="hand2",
                  command=name_dialog.destroy).pack(side="right", padx=(0, 8))

        name_dialog.bind("<Return>", lambda e: _apply())

    # ── Keyboard navigation helpers ───────────────────────
    def _focus_ref(self):
        """Move focus to the Reference field and select its text."""
        try:
            self._ref_entry.focus_set()
            self._ref_entry.select_range(0, tk.END)
        except Exception:
            pass

    def _focus_product_search(self):
        """Move focus to the Product search box and clear it for new entry."""
        try:
            self._search_entry.focus_set()
            self._search_entry.select_range(0, tk.END)
        except Exception:
            pass

    def _focus_price(self):
        """Move focus to the Price field and select all."""
        try:
            self._price_entry.focus_set()
            self._price_entry.select_range(0, tk.END)
        except Exception:
            pass

    def _focus_qty(self):
        """Move focus to the Qty field, set to 0 and select all."""
        try:
            if self.qty_var.get() in ("0", "1", ""):
                self.qty_var.set("0")
            self._qty_entry.focus_set()
            self._qty_entry.select_range(0, tk.END)
        except Exception:
            pass

    def _ref_enter(self):
        """Handle Enter on Reference field: look up if typed, then move to product search."""
        query = self.ref_search_var.get().strip()
        if query:
            self._fetch_reference()
        self._focus_product_search()

    def _price_enter(self):
        """Handle Enter on Price field: move to Qty."""
        self._focus_qty()

    def _fetch_reference(self):
        """Look up a reference customer by ID, phone or name."""
        query = self.ref_search_var.get().strip()
        if not query:
            return
        c = find_customer(query)
        if c:
            self.ref_phone_var.set(c["phone"])
            self.ref_name_var.set(c["name"])
            cid = c.get("id", "")
            self.ref_status.config(
                text=f"✓  Referred by: [{cid}] {c['name']}  ({c['phone']})",
                fg=COLORS["success"])
        else:
            self.ref_phone_var.set("")
            self.ref_name_var.set("")
            self.ref_status.config(
                text=f"⚠  No customer found for '{query}'",
                fg=COLORS["warning"])

    def _clear_reference(self):
        """Clear the reference selection."""
        self.ref_search_var.set("")
        self.ref_phone_var.set("")
        self.ref_name_var.set("")
        self.ref_status.config(text="No reference selected",
                               fg=COLORS["text_muted"])

    def _hide_cust_suggestions(self):
        """Hide any open customer suggestion dropdown."""
        if self._active_sugg_frame:
            self._active_sugg_frame.pack_forget()
            self._active_sugg_frame = None
        self._cust_sugg_data = []

    def _load_customer(self, customer):
        self.current_customer = customer
        self.name_var.set(customer["name"])
        self.name_entry.config(state="readonly", bg=COLORS["card_bg"])
        due = max(0, customer.get("total_due", 0) or 0)
        self.old_balance_var.set(f"{due:.2f}")
        color = COLORS["danger"] if due > 0 else COLORS["success"]
        cid = customer.get("id", "")
        self.cust_status.config(
            text=f"✓  ID: {cid}  |  {customer['name']}  |  Previous Due: ₹{due:,.2f}",
            fg=color)
        log.debug("Customer loaded: #%d %s", cid, customer["name"])

    def _fetch_customer(self):
        query = (self.phone_var.get() or
                 self._name_search_var.get() or
                 self._id_search_var.get()).strip()
        if not query:
            messagebox.showwarning("Invalid", "Type in any search box to find a customer.")
            return
        self._hide_cust_suggestions()
        customer = find_customer(query)
        if customer:
            self._cust_selecting = True
            self._id_search_var.set(str(customer.get("id", "")))
            self._name_search_var.set(customer["name"])
            self._phone_search_var.set(customer["phone"])
            self._cust_selecting = False
            self._load_customer(customer)
        else:
            self.current_customer = None
            self.name_var.set("")
            self.name_entry.config(state="normal", bg=COLORS["input_bg"])
            self.old_balance_var.set("0")
            self.cust_status.config(
                text="⊕  New customer — type name above",
                fg=COLORS["warning"])
        self._recalculate()

    def _nil_balance(self):
        """
        NIL Balance: auto-fill Paid = (current bill + old balance) so net
        balance becomes ₹0, then run the normal Save + Print + WhatsApp flow.
        """
        phone = self.phone_var.get().strip()
        from database import WALKIN_PHONE
        if not phone or (phone != WALKIN_PHONE and
                         (not phone.isdigit() or len(phone) != 10)):
            messagebox.showwarning("NIL Balance",
                "Select a customer first before using NIL Balance.")
            return

        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("NIL Balance", "Select a customer first.")
            return

        # ── Current bill total ─────────────────────────────
        subtotal = sum(i["amount"] for i in self.items)
        try:    transport = max(0, float(self.transport_var.get() or 0))
        except: transport = 0.0
        try:    disc_pct = max(0, min(100, float(self.discount_var.get() or 0)))
        except: disc_pct = 0.0
        disc_amt = subtotal * disc_pct / 100
        grand    = subtotal - disc_amt + transport

        try:    old_bal = max(0, float(self.old_balance_var.get() or 0))
        except: old_bal = 0.0

        total_to_pay = grand + old_bal

        if total_to_pay <= 0:
            messagebox.showinfo("NIL Balance",
                "Nothing to clear — total is ₹0.00.")
            return

        confirm = messagebox.askyesno(
            "NIL Balance — Confirm",
            f"Customer      : {name}\n"
            f"Bill Amount   : ₹{grand:,.2f}\n"
            f"Old Balance   : ₹{old_bal:,.2f}\n"
            f"─────────────────────────\n"
            f"Total to Pay  : ₹{total_to_pay:,.2f}\n\n"
            f"This amount will be filled in 'Paid'.\n"
            f"Net Balance will become ₹0.00.\n\n"
            f"Save + Print + Send WhatsApp?",
            icon="question"
        )
        if not confirm:
            return

        # ── Fill in Paid and trigger normal Save Bill flow ─
        self.paid_var.set(f"{total_to_pay:.2f}")
        self._recalculate()
        self._generate_bill()

    def _fetch_product(self):
        pid = self.pid_var.get().strip()
        if not pid.isdigit():
            messagebox.showwarning("Invalid", "Product ID must be a number.")
            return
        p = get_product(int(pid))
        if p:
            self.pname_var.set(p["name"])
            self.pprice_var.set(f"{p['price']:.2f}")
            # Auto-advance to Price field
            self.after(30, self._focus_price)
        else:
            self.pname_var.set("")
            self.pprice_var.set("")
            messagebox.showerror("Not Found", f"No product with ID {pid}.")

    def _add_item(self):
        pid = self.pid_var.get().strip()
        if not pid.isdigit():
            messagebox.showwarning("Invalid", "Enter a valid Product ID first.")
            return
        p = get_product(int(pid))
        if not p:
            messagebox.showerror("Not Found", f"No product with ID {pid}.")
            return
        try:
            price = float(self.pprice_var.get().strip())
            if price <= 0: raise ValueError
        except:
            messagebox.showwarning("Invalid", "Enter a valid price.")
            return
        try:
            qty = float(self.qty_var.get().strip())
            if qty <= 0: raise ValueError
        except:
            messagebox.showwarning("Invalid", "Quantity must be a positive number.")
            return

        self.items.append({
            "product_id": p["id"], "product_name": p["name"],
            "unit": p.get("unit", "Nos") or "Nos",
            "qty": qty, "price": price, "amount": price * qty,
        })
        self._refresh_table()
        self.pid_var.set(""); self.pname_var.set("")
        self.pprice_var.set(""); self.qty_var.set("0")
        self.preview_var.set("Amount: ₹0.00")
        # ── Loop back to product search for next item ─────
        self.after(30, self._focus_product_search)

    def _remove_item(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Select", "Select an item to remove.")
            return
        self.items.pop(self.tree.index(sel[0]))
        self._refresh_table()

    def _refresh_table(self):
        self.tree.delete(*self.tree.get_children())
        for i, item in enumerate(self.items, 1):
            tag = "alt" if i % 2 == 0 else ""
            self.tree.insert("", "end", tags=(tag,), values=(
                i, item["product_name"],
                f"{item['qty']:g}",
                f"₹{item['price']:,.2f}",
                f"₹{item['amount']:,.2f}"))
        self.tree.tag_configure("alt", background=COLORS["table_row_alt"])
        self._recalculate()

    # ── Print Preview (no save, no share) ────────────────
    def _print_preview(self):
        """Generate and print a preview PDF — nothing saved to DB."""
        try:
            phone, name, grand, transport, disc_pct, disc_amt, old_bal = \
                self._validate_bill_inputs()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return

        try:
            from pdf_generator import generate_invoice_pdf
            subtotal = sum(i["amount"] for i in self.items)
            pdf_path = generate_invoice_pdf(
                "PREVIEW", name, phone,
                self.items, grand, 0.0, grand,
                type         = self.type_var.get(),
                transport    = transport,
                discount_pct = disc_pct,
                discount_amt = disc_amt,
                old_balance  = old_bal,
                net_balance  = grand + old_bal,
            )
            if not pdf_path:
                raise RuntimeError("PDF generation failed — check reportlab is installed.")
            _open_file(pdf_path)
            _print_file(pdf_path)
            self._preview_printed = True
            messagebox.showinfo("Print Preview",
                "✅ Preview sent to printer.\n\n"
                "When you click SAVE BILL, it will NOT print again.\n"
                "Click SAVE BILL to save, update balance & send WhatsApp.")
        except Exception as e:
            messagebox.showerror("Preview Error", str(e))
            log.error("Print preview failed: %s", e)

    # ── Generate (Full Automated Workflow) ───────────────
    def _generate_bill(self):
        """
        Generate Bill button handler.

        CRITICAL (synchronous, must succeed):
          1. Save invoice to SQLite
          2. Generate invoice PDF

        BACKGROUND (non-blocking threads):
          3. Print PDF
          4. Upload PDF to Supabase Storage
          5. Get public PDF URL
          6-10. Open WhatsApp → customer chat → fill → send

        UI dialog shown immediately after critical steps succeed.
        Background failures are logged only — invoice always saved.
        """
        try:
            phone, name, grand, transport, disc_pct, disc_amt, old_bal = \
                self._validate_bill_inputs()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return

        bill_type = self.type_var.get()

        if bill_type == "quotation":
            paid, balance = 0.0, grand
        else:
            try:
                paid = max(0, float(self.paid_var.get().strip() or "0"))
            except Exception:
                messagebox.showwarning("Error", "Paid amount must be a valid number.")
                return
            balance = max(0, grand - paid)

        net_balance = grand + old_bal - paid

        already_printed = getattr(self, "_preview_printed", False)

        # ── Run the automated workflow ───────────────────────
        invoice_id, pdf_path, error = run_billing_workflow(
            phone            = phone,
            name             = name,
            total            = grand,
            paid             = paid,
            balance          = max(0, balance),
            items            = self.items,
            bill_type        = bill_type,
            transport        = transport,
            discount_pct     = disc_pct,
            discount_amt     = disc_amt,
            old_balance      = old_bal,
            net_balance      = net_balance,
            reference_phone  = self.ref_phone_var.get().strip(),
            reference_name   = self.ref_name_var.get().strip(),
            payment_type     = self.pay_type_var.get(),
            skip_print       = already_printed,
        )

        if invoice_id is None:
            messagebox.showerror("Error", f"Failed to save invoice:\n{error}")
            return

        if error:
            log.warning("Invoice #%d saved but PDF failed: %s", invoice_id, error)

        subtotal = sum(i["amount"] for i in self.items)
        prefix    = "QUO" if bill_type == "quotation" else "INV"
        extra_msg = (f"\nAdvance Credit: ₹{abs(net_balance):,.2f}"
                     if net_balance < 0 else "")
        reprint_note = " (not reprinted — already previewed)" if already_printed else "\n📤 Printing & WhatsApp running in background…"
        messagebox.showinfo("Bill Saved!",
            f"✅ {prefix}-{invoice_id} saved!\n\n"
            f"Bill Amount:  ₹{subtotal:,.2f}\n"
            f"Transport:    ₹{transport:,.2f}\n"
            f"Discount:     ₹{disc_amt:,.2f} ({disc_pct:.1f}%)\n"
            f"Grand Total:  ₹{grand:,.2f}\n"
            f"Old Balance:  ₹{old_bal:,.2f}\n"
            f"Paid Now:     ₹{paid:,.2f}\n"
            f"Net Balance:  ₹{max(0, net_balance):,.2f}{extra_msg}"
            f"{reprint_note}")

        self._preview_printed = False
        self._reset_form()

    # ── Shared validation helper ──────────────────────────
    def _validate_bill_inputs(self):
        """
        Validate common inputs before any bill save.
        Returns (phone, name, grand, transport, disc_pct, disc_amt, old_bal)
        or raises ValueError with a message.
        """
        from database import WALKIN_PHONE
        phone = self.phone_var.get().strip()
        name  = self.name_var.get().strip()
        # Allow walk-in phone to bypass normal mobile number validation
        if phone != WALKIN_PHONE:
            if not phone or not phone.isdigit() or len(phone) != 10 or phone[0] not in "6789":
                raise ValueError("Enter a valid 10-digit Indian mobile number.")
        if not name:
            raise ValueError("Enter customer name.")
        if not self.items:
            raise ValueError("Add at least one item.")

        subtotal = sum(i["amount"] for i in self.items)
        try:
            transport = max(0, float(self.transport_var.get() or 0))
        except Exception:
            transport = 0.0
        try:
            disc_pct = max(0, min(100, float(self.discount_var.get() or 0)))
        except Exception:
            disc_pct = 0.0
        disc_amt = subtotal * disc_pct / 100
        grand    = subtotal - disc_amt + transport
        old_bal  = max(0, float(self.old_balance_var.get() or 0)) \
                   if self._is_number(self.old_balance_var.get()) else 0.0
        return phone, name, grand, transport, disc_pct, disc_amt, old_bal

    # ── Credit Sale — bill now, customer pays later ───────
    def _credit_sale(self):
        """Save invoice with paid=0. Full amount added to customer balance immediately."""
        try:
            phone, name, grand, transport, disc_pct, disc_amt, old_bal = \
                self._validate_bill_inputs()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return
        if not messagebox.askyesno(
            "Credit Sale",
            f"Save CREDIT SALE for {name}?\n\n"
            f"Grand Total  : ₹{grand:,.2f}\n"
            f"Paid Now     : ₹0.00\n"
            f"Credit Added : ₹{grand:,.2f}\n\n"
            "Full amount will be added to customer's balance.\n"
            "Collect payment later via the Payment screen."
        ):
            return
        net_balance = grand + old_bal
        invoice_id, pdf_path, error = run_billing_workflow(
            phone            = phone, name            = name,
            total            = grand, paid            = 0.0,
            balance          = grand, items           = self.items,
            bill_type        = "invoice",
            transport        = transport, discount_pct = disc_pct,
            discount_amt     = disc_amt, old_balance   = old_bal,
            net_balance      = net_balance,
            reference_phone  = self.ref_phone_var.get().strip(),
            reference_name   = self.ref_name_var.get().strip(),
            payment_type     = self.pay_type_var.get(),
        )
        if invoice_id is None:
            messagebox.showerror("Error", f"Failed to save:\n{error}")
            return
        messagebox.showinfo("Credit Sale Saved!",
            f"💳  INV-{invoice_id} saved as CREDIT SALE\n\n"
            f"Grand Total : ₹{grand:,.2f}\n"
            f"Credit Due  : ₹{grand:,.2f}\n\n"
            "PDF printed. Collect payment later via Payment screen.")
        self._reset_form()

    # ── Save Draft — print only, no balance ──────────────
    def _save_draft(self):
        """Save as DRAFT — prints PDF but does NOT add to customer balance."""
        try:
            phone, name, grand, transport, disc_pct, disc_amt, old_bal = \
                self._validate_bill_inputs()
        except ValueError as e:
            messagebox.showwarning("Error", str(e))
            return
        net_balance = grand + old_bal
        invoice_id, pdf_path, error = run_billing_workflow(
            phone            = phone, name            = name,
            total            = grand, paid            = 0.0,
            balance          = grand, items           = self.items,
            bill_type        = "draft",
            transport        = transport, discount_pct = disc_pct,
            discount_amt     = disc_amt, old_balance   = old_bal,
            net_balance      = net_balance,
            reference_phone  = self.ref_phone_var.get().strip(),
            reference_name   = self.ref_name_var.get().strip(),
            payment_type     = self.pay_type_var.get(),
        )
        if invoice_id is None:
            messagebox.showerror("Error", f"Failed to save draft:\n{error}")
            return
        messagebox.showinfo("Draft Saved!",
            f"\U0001f4cb  DRAFT-{invoice_id} saved (no balance added)\n\n"
            f"Grand Total : \u20b9{grand:,.2f}\n\n"
            "PDF printed for reference.\n"
            "Confirm it later via History to add to customer balance.")
        self._reset_form()

    # \u2500\u2500 Reset / Clear form \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    def _reset_form(self):
        """Clear all inputs ready for the next bill."""
        # Customer fields
        self._cust_selecting = True
        self._id_search_var.set("")
        self._name_search_var.set("")
        self._phone_search_var.set("")
        self._cust_selecting = False
        self.name_var.set("")
        self.name_entry.config(state="normal", bg=COLORS["input_bg"])
        self.cust_status.config(
            text="Search for a customer above or add a new one.",
            fg=COLORS["text_muted"])
        self.current_customer = None

        # Reference
        self.ref_search_var.set("")
        self.ref_phone_var.set("")
        self.ref_name_var.set("")
        try:
            self.ref_resolved_lbl.config(text="No reference selected",
                                          fg=COLORS["text_muted"])
        except Exception:
            pass

        # Bill type + Payment type
        self.type_var.set("invoice")
        self.paid_entry.config(state="normal")
        self.pay_type_var.set("Cash")

        # Items
        self.items.clear()
        self._refresh_table()

        # Summary fields
        self.pid_var.set("")
        self.pname_var.set("")
        self.pprice_var.set("")
        self.qty_var.set("0")
        self.preview_var.set("Amount: \u20b90.00")

        self.transport_var.set("0")
        self.discount_var.set("0")
        self.old_balance_var.set("0")
        self.paid_var.set("0")

        self._preview_printed = False
        self._recalculate()
