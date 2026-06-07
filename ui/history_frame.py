"""
Customer Management Frame — NEW INDIAN STEEL
=============================================
Full customer management: list, search, add, edit, and detail view.

Accounting rule (read-only computed due):
    current_due = opening_balance + SUM(invoice balances) - SUM(payments)

Sections:
  - Top toolbar: Search | Add Customer | All Customers toggle
  - Customer list (scrollable Treeview)
  - Action buttons: Edit | View Details | Export Statement
"""
import tkinter as tk
from tkinter import ttk, messagebox
import os, sys, subprocess, glob

from config import COLORS, FONTS, INVOICES_DIR
from logger import get_logger
import database as db
from pdf_generator import generate_customer_statement_pdf
from whatsapp import send_bill_message_async

log = get_logger(__name__)


# ── Helpers ───────────────────────────────────────────────

def _open_file(path):
    try:
        if sys.platform == "win32":    os.startfile(path)
        elif sys.platform == "darwin": subprocess.run(["open", path])
        else:                          subprocess.run(["xdg-open", path])
    except Exception:
        pass


def _card(parent, **kw):
    return tk.Frame(parent, bg=COLORS["card_bg"],
                    highlightbackground=COLORS["card_border"],
                    highlightthickness=1, **kw)


def _validate_phone(phone):
    """Return (True, '') or (False, error_message)."""
    if not phone:
        return False, "Phone number is required."
    if not phone.isdigit():
        return False, "Phone must contain digits only."
    if len(phone) != 10:
        return False, "Phone must be exactly 10 digits."
    if phone[0] not in "6789":
        return False, "Phone must start with 6, 7, 8, or 9."
    return True, ""


# ══════════════════════════════════════════════════════════
# CUSTOMER FORM DIALOG (Create / Edit)
# ══════════════════════════════════════════════════════════

class CustomerFormDialog(tk.Toplevel):
    """
    Modal dialog for creating or editing a customer.
    On OK → calls on_save(name, phone, address, opening_balance).
    """

    def __init__(self, parent, on_save, customer=None):
        super().__init__(parent)
        self._on_save = on_save
        self._edit = customer  # dict if editing, None if creating

        is_edit = customer is not None
        self.title("Edit Customer" if is_edit else "Add New Customer")
        self.geometry("460x420")
        self.configure(bg=COLORS["content_bg"])
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self._build(is_edit)
        if is_edit:
            self._populate(customer)

    def _build(self, is_edit):
        # Header
        hdr = tk.Frame(self, bg=COLORS["primary"])
        hdr.pack(fill="x")
        icon = "✏️" if is_edit else "➕"
        title = "Edit Customer" if is_edit else "Add New Customer"
        tk.Label(hdr, text=f"{icon}  {title}",
                 font=FONTS["heading"], bg=COLORS["primary"], fg="#FFFFFF"
                 ).pack(side="left", padx=20, pady=14)

        body = tk.Frame(self, bg=COLORS["content_bg"])
        body.pack(fill="both", expand=True, padx=24, pady=20)

        def field(label, var, readonly=False, placeholder=""):
            tk.Label(body, text=label, font=FONTS["small_bold"],
                     bg=COLORS["content_bg"], fg=COLORS["text_muted"]
                     ).pack(anchor="w", pady=(10, 2))
            state = "readonly" if readonly else "normal"
            e = tk.Entry(body, textvariable=var, font=FONTS["input"],
                         bg="#F1F5F9" if readonly else COLORS["input_bg"],
                         fg="#64748B" if readonly else "#1A1A2E",
                         relief="flat",
                         highlightbackground=COLORS["input_border"],
                         highlightcolor=COLORS["primary"],
                         highlightthickness=1,
                         state=state)
            e.pack(fill="x", ipady=6)
            return e

        self.name_var    = tk.StringVar()
        self.phone_var   = tk.StringVar()
        self.address_var = tk.StringVar()
        self.ob_var      = tk.StringVar(value="0")

        field("Customer Name *", self.name_var)
        field("Phone Number * (10 digits)", self.phone_var,
              readonly=is_edit)   # Phone cannot change on edit
        field("Address", self.address_var)

        # Opening Balance — with clear label
        tk.Label(body, text="Opening Balance (₹)  — existing dues before this system",
                 font=FONTS["small_bold"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]
                 ).pack(anchor="w", pady=(10, 2))
        ob_frame = tk.Frame(body, bg=COLORS["content_bg"])
        ob_frame.pack(fill="x")
        tk.Label(ob_frame, text="₹", font=FONTS["input"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]).pack(side="left")
        tk.Entry(ob_frame, textvariable=self.ob_var, font=FONTS["input"],
                 width=16,
                 bg=COLORS["input_bg"], fg="#1A1A2E", relief="flat",
                 highlightbackground=COLORS["input_border"],
                 highlightcolor=COLORS["primary"],
                 highlightthickness=1
                 ).pack(side="left", ipady=6, padx=(4, 0))

        # Buttons
        btn_row = tk.Frame(self, bg=COLORS["content_bg"])
        btn_row.pack(fill="x", padx=24, pady=(0, 18))
        tk.Button(btn_row, text="✅  Save",
                  font=FONTS["button"], bg=COLORS["success"], fg="white",
                  relief="flat", padx=18, pady=8, cursor="hand2",
                  command=self._save).pack(side="right")
        tk.Button(btn_row, text="Cancel",
                  font=FONTS["button"], bg=COLORS["divider"], fg="#1A1A2E",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self.destroy).pack(side="right", padx=(0, 8))

    def _populate(self, c):
        self.name_var.set(c.get("name", ""))
        self.phone_var.set(c.get("phone", ""))
        self.address_var.set(c.get("address", ""))
        self.ob_var.set(str(c.get("opening_balance", 0)))

    def _save(self):
        name    = self.name_var.get().strip()
        phone   = self.phone_var.get().strip()
        address = self.address_var.get().strip()
        ob_raw  = self.ob_var.get().strip()

        # Validate name
        if not name:
            messagebox.showwarning("Validation", "Customer name is required.", parent=self)
            return

        # Validate phone (skip if editing — phone is locked)
        if not self._edit:
            ok, msg = _validate_phone(phone)
            if not ok:
                messagebox.showwarning("Validation", msg, parent=self)
                return
            # Duplicate check
            if db.get_customer(phone):
                messagebox.showwarning("Duplicate",
                    f"A customer with phone {phone} already exists.", parent=self)
                return

        # Validate opening balance
        try:
            ob = float(ob_raw)
            if ob < 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Validation",
                "Opening balance must be a non-negative number.", parent=self)
            return

        self._on_save(name, phone, address, ob)
        self.destroy()


# ══════════════════════════════════════════════════════════
# INVOICE DETAIL POPUP
# ══════════════════════════════════════════════════════════

class InvoiceDetailPopup(tk.Toplevel):
    """
    Full detail view for a single invoice.
    Shows every line item (product, qty, unit, rate, amount),
    the summary totals, and action buttons: View PDF | Reprint | Delete.
    """

    def __init__(self, parent, invoice_id: int, on_delete=None):
        super().__init__(parent)
        self._invoice_id = invoice_id
        self._on_delete  = on_delete   # callback after successful delete

        inv = db.get_invoice(invoice_id)
        if not inv:
            messagebox.showerror("Not Found", f"Invoice #{invoice_id} not found.")
            self.destroy()
            return

        customer = db.get_customer(inv.get("customer_phone", ""))
        cname    = customer["name"] if customer else inv.get("customer_phone", "—")

        prefix   = "QUO" if (inv.get("type") or "").lower() == "quotation" else "INV"
        self.title(f"{prefix}-{invoice_id}  —  {cname}")
        self.geometry("800x680")
        self.configure(bg=COLORS["content_bg"])
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._inv      = inv
        self._cname    = cname
        self._prefix   = prefix

        self._build(inv, cname, prefix)

    def _build(self, inv, cname, prefix):
        # ── Header strip ─────────────────────────────────────
        hdr = tk.Frame(self, bg=COLORS["primary"])
        hdr.pack(fill="x")
        tk.Label(hdr,
                 text=f"🧾  {prefix}-{self._invoice_id}  |  {cname}",
                 font=FONTS["heading"], bg=COLORS["primary"], fg="#FFFFFF"
                 ).pack(side="left", padx=20, pady=14)
        tk.Button(hdr, text="✕ Close", font=FONTS["small"],
                  bg=COLORS["primary"], fg="#BFDBFE", relief="flat",
                  cursor="hand2", command=self.destroy
                  ).pack(side="right", padx=16)

        # ── Meta row: date, type, phone, reference ─────────────
        meta = tk.Frame(self, bg="#EFF6FF")
        meta.pack(fill="x")
        inv_date  = (inv.get("date") or "")[:16]
        inv_type  = (inv.get("type") or "invoice").title()
        phone     = inv.get("customer_phone", "")
        ref_phone = (inv.get("reference_phone") or "").strip()
        # Resolve reference name
        ref_label = "—"
        if ref_phone:
            ref_cust = db.get_customer(ref_phone)
            if ref_cust:
                ref_label = f"{ref_cust['name']}  ({ref_phone})"
            else:
                ref_label = ref_phone
        meta_items = [
            ("Date",         inv_date),
            ("Type",         inv_type),
            ("Phone",        phone),
            ("Referred By",  ref_label),
        ]
        for label, value in meta_items:
            cell = tk.Frame(meta, bg="#EFF6FF")
            cell.pack(side="left", padx=16, pady=8)
            tk.Label(cell, text=label, font=FONTS["small"],
                     bg="#EFF6FF", fg=COLORS["text_muted"]).pack(anchor="w")
            color = COLORS["success"] if label == "Referred By" and ref_phone else COLORS["text_dark"]
            tk.Label(cell, text=value, font=FONTS["body_bold"],
                     bg="#EFF6FF", fg=color).pack(anchor="w")

        # ── Items table ───────────────────────────────────────
        tbl_frame = tk.Frame(self, bg=COLORS["card_bg"],
                             highlightbackground=COLORS["card_border"],
                             highlightthickness=1)
        tbl_frame.pack(fill="both", expand=True, padx=16, pady=(12, 4))

        # Header row
        hdr_row = tk.Frame(tbl_frame, bg=COLORS["table_header_bg"])
        hdr_row.pack(fill="x")
        for txt, w, anchor in [
            ("#",        4,  "center"),
            ("Product", 28,  "w"),
            ("Qty",      8,  "e"),
            ("Unit",     8,  "center"),
            ("Rate",    12,  "e"),
            ("Amount",  12,  "e"),
        ]:
            tk.Label(hdr_row, text=txt, width=w, anchor=anchor,
                     font=FONTS["small_bold"],
                     bg=COLORS["table_header_bg"],
                     fg=COLORS["table_header_fg"],
                     pady=7, padx=6
                     ).pack(side="left")

        # Scrollable items area
        canvas  = tk.Canvas(tbl_frame, bg=COLORS["card_bg"],
                            highlightthickness=0)
        scrollb = ttk.Scrollbar(tbl_frame, orient="vertical",
                                command=canvas.yview)
        inner   = tk.Frame(canvas, bg=COLORS["card_bg"])
        inner.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollb.set)
        scrollb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        items = db.get_invoice_items(self._invoice_id)
        for i, item in enumerate(items, 1):
            bg = COLORS["table_row_alt"] if i % 2 == 0 else COLORS["card_bg"]
            row = tk.Frame(inner, bg=bg)
            row.pack(fill="x")
            qty    = item.get("qty", 0)
            price  = float(item.get("price", 0))
            amount = float(item.get("amount", 0))
            unit   = item.get("unit") or "Nos"
            qty_str = str(int(qty)) if float(qty) == int(float(qty)) else f"{float(qty):.2f}"
            for txt, w, anchor in [
                (str(i),                     4,  "center"),
                (item.get("product_name","—"),28,  "w"),
                (qty_str,                    8,  "e"),
                (unit,                       8,  "center"),
                (f"₹{price:,.2f}",          12,  "e"),
                (f"₹{amount:,.2f}",         12,  "e"),
            ]:
                tk.Label(row, text=txt, width=w, anchor=anchor,
                         font=FONTS["body"], bg=bg,
                         fg=COLORS["text_dark"],
                         pady=5, padx=6
                         ).pack(side="left")

        if not items:
            tk.Label(inner,
                     text="No items found for this invoice.",
                     font=FONTS["body"], bg=COLORS["card_bg"],
                     fg=COLORS["text_muted"], pady=16
                     ).pack()

        # ── Summary strip ─────────────────────────────────────
        summ = tk.Frame(self, bg="#F8FAFC",
                        highlightbackground=COLORS["card_border"],
                        highlightthickness=1)
        summ.pack(fill="x", padx=16, pady=(0, 8))
        total   = float(inv.get("total",   0))
        paid    = float(inv.get("paid",    0))
        balance = float(inv.get("balance", 0))
        for label, value, color in [
            ("Bill Total",    f"₹{total:,.2f}",   COLORS["text_dark"]),
            ("Paid Now",      f"₹{paid:,.2f}",    COLORS["success"]),
            ("Balance Due",   f"₹{balance:,.2f}", COLORS["danger"] if balance > 0 else COLORS["success"]),
        ]:
            cell = tk.Frame(summ, bg="#F8FAFC")
            cell.pack(side="left", padx=24, pady=10)
            tk.Label(cell, text=label, font=FONTS["small"],
                     bg="#F8FAFC", fg=COLORS["text_muted"]).pack(anchor="w")
            tk.Label(cell, text=value, font=("Segoe UI", 15, "bold"),
                     bg="#F8FAFC", fg=color).pack(anchor="w")

        # ── Action buttons (shown BEFORE items so always visible) ────
        inv_type = (inv.get("type") or "invoice").lower()
        act = tk.Frame(self, bg=COLORS["content_bg"])
        act.pack(fill="x", padx=16, pady=(6, 6))

        tk.Button(act, text="🖨 Print PDF",
                  font=FONTS["button"], bg=COLORS["primary"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._view_pdf
                  ).pack(side="left", padx=(0, 6))

        tk.Button(act, text="📲 WhatsApp",
                  font=FONTS["button"], bg="#25D366", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._share_whatsapp
                  ).pack(side="left", padx=(0, 6))

        tk.Button(act, text="✏️ Edit & Resave",
                  font=FONTS["button"], bg="#7D3C98", fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._edit_invoice
                  ).pack(side="left", padx=(0, 6))

        tk.Button(act, text="🗑 Delete",
                  font=FONTS["button"], bg=COLORS["danger"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._delete_invoice
                  ).pack(side="right")

        if inv_type == "draft":
            tk.Button(act, text="✅ Confirm→Invoice",
                      font=FONTS["button"], bg="#1E8449", fg="white",
                      relief="flat", padx=12, pady=6, cursor="hand2",
                      command=self._confirm_draft
                      ).pack(side="right", padx=(0, 6))

        # ── Draft banner ──────────────────────────────────────
        if inv_type == "draft":
            banner = tk.Frame(self, bg="#FEF3C7",
                              highlightbackground="#D68910", highlightthickness=1)
            banner.pack(fill="x", padx=16, pady=(0, 4))
            tk.Label(banner,
                     text="⚠  DRAFT — Not added to customer balance yet.",
                     font=FONTS["body_bold"], bg="#FEF3C7", fg="#92400E",
                     pady=6, padx=12).pack(side="left")

        # (buttons already added above)

    def _confirm_draft(self):
        """Confirm a draft invoice: change to real invoice and add balance to customer."""
        balance = float(self._inv.get("balance", 0))
        if not messagebox.askyesno(
            "Confirm Draft",
            f"Convert DRAFT-{self._invoice_id} to a real Invoice?\n\n"
            f"Amount : ₹{balance:,.2f}\n\n"
            f"✅  ₹{balance:,.2f} will be added to {self._cname}'s balance.\n"
            f"This cannot be undone.",
            icon="question"
        ):
            return
        ok, msg = db.confirm_draft_invoice(self._invoice_id)
        if ok:
            # Queue cloud sync for updated invoice + customer
            try:
                from task_queue import add_task
                add_task("cloud_sync", {
                    "phone":      self._inv.get("customer_phone", ""),
                    "invoice_id": self._invoice_id,
                })
            except Exception:
                pass
            messagebox.showinfo("Confirmed!", f"✅  {msg}")
            if self._on_delete:   # reuse callback to refresh parent
                self._on_delete()
            self.destroy()
        else:
            messagebox.showerror("Error", msg)

    def _find_local_pdf(self):
        """Search INVOICES_DIR for a PDF file matching this invoice id."""
        prefix = self._prefix
        pattern = os.path.join(INVOICES_DIR, f"{prefix}-{self._invoice_id}_*.pdf")
        matches = sorted(glob.glob(pattern), reverse=True)
        if matches:
            return matches[0]
        return None

    def _view_pdf(self):
        """Open the existing saved PDF for this invoice."""
        path = self._find_local_pdf()
        if path and os.path.exists(path):
            _open_file(path)
        else:
            # Try cloud URL
            url = self._inv.get("pdf_url", "")
            if url:
                import webbrowser
                webbrowser.open(url)
            else:
                messagebox.showinfo(
                    "PDF Not Found",
                    f"The original PDF for {self._prefix}-{self._invoice_id} was not found "
                    f"on this PC.\n\nUse 'Reprint PDF' to generate a fresh copy."
                )

    def _reprint_pdf(self):
        """Re-generate and open the PDF using current DB data."""
        from pdf_generator import generate_invoice_pdf
        inv     = self._inv
        items   = db.get_invoice_items(self._invoice_id)
        cphone  = inv.get("customer_phone", "")
        cust    = db.get_customer(cphone)
        cname   = cust["name"] if cust else self._cname
        try:
            pdf_path = generate_invoice_pdf(
                self._invoice_id, cname, cphone,
                items,
                float(inv.get("total",   0)),
                float(inv.get("paid",    0)),
                float(inv.get("balance", 0)),
                type=inv.get("type", "invoice"),
            )
            if pdf_path and os.path.exists(pdf_path):
                _open_file(pdf_path)
                messagebox.showinfo("Reprinted",
                    f"PDF regenerated and opened:\n{os.path.basename(pdf_path)}")
            else:
                messagebox.showerror("Error", "PDF generation failed.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not generate PDF:\n{e}")


    def _share_whatsapp(self):
        """Share invoice PDF via WhatsApp to the customer's phone number."""
        inv   = self._inv
        phone = inv.get("customer_phone", "")
        if not phone:
            messagebox.showwarning("No Phone",
                "This customer has no phone number on record.")
            return

        # Find existing PDF or regenerate
        pdf_path = self._find_local_pdf()
        if not pdf_path or not os.path.exists(pdf_path):
            from pdf_generator import generate_invoice_pdf
            items = db.get_invoice_items(self._invoice_id)
            try:
                pdf_path = generate_invoice_pdf(
                    self._invoice_id, self._cname, phone, items,
                    float(inv.get("total",   0)),
                    float(inv.get("paid",    0)),
                    float(inv.get("balance", 0)),
                    type=inv.get("type", "invoice"),
                )
            except Exception as e:
                messagebox.showerror("Error", f"Could not generate PDF:\n{e}")
                return

        send_bill_message_async(
            phone         = phone,
            customer_name = self._cname,
            invoice_id    = self._invoice_id,
            total         = float(inv.get("total",   0)),
            paid          = float(inv.get("paid",    0)),
            balance       = float(inv.get("balance", 0)),
            pdf_path      = pdf_path or "",
            pdf_url       = inv.get("pdf_url", "") or "",
        )
        messagebox.showinfo(
            "WhatsApp",
            f"📲 Sharing invoice to {self._cname} ({phone})…\n\n"
            f"WhatsApp will open shortly."
        )

    def _edit_invoice(self):
        """Open an edit dialog to modify items and resave this invoice."""
        inv    = self._inv
        inv_id = self._invoice_id
        items  = db.get_invoice_items(inv_id)

        win = tk.Toplevel(self)
        win.title(f"Edit Invoice #{inv_id}")
        win.geometry("820x600")
        win.configure(bg=COLORS["content_bg"])
        win.grab_set()

        tk.Label(win, text=f"✏️  Edit Invoice #{inv_id}  —  {self._cname}",
                 font=FONTS["subheading"], bg=COLORS["content_bg"],
                 fg=COLORS["text_dark"]).pack(pady=(14, 4))
        tk.Label(win, text="Add/remove items, adjust price. Invoice number and date stay the same.",
                 font=FONTS["small"], bg=COLORS["content_bg"],
                 fg=COLORS["text_muted"]).pack()

        # ── Items list (editable) ──────────────────────────
        cols = ("no","product","qty","price","amount")
        frm = tk.Frame(win, bg=COLORS["content_bg"])
        frm.pack(fill="both", expand=True, padx=16, pady=8)

        tree = ttk.Treeview(frm, columns=cols, show="headings", height=10)
        for col, lbl, w in [("no","#",40),("product","Product",280),
                              ("qty","Qty",60),("price","Price ₹",100),("amount","Amount ₹",110)]:
            tree.heading(col, text=lbl)
            tree.column(col, width=w, anchor="center" if col!="product" else "w")
        tree.pack(fill="both", expand=True)

        edit_items = [{"product_name": r["product_name"],
                       "qty": r["qty"], "price": r["price"],
                       "amount": r["amount"]} for r in items]

        def _refresh_tree():
            tree.delete(*tree.get_children())
            for i, it in enumerate(edit_items, 1):
                tree.insert("", "end", values=(
                    i, it["product_name"], it["qty"],
                    f"₹{it['price']:.2f}", f"₹{it['amount']:.2f}"))

        _refresh_tree()

        # ── Controls row ──────────────────────────────────
        ctrl = tk.Frame(win, bg=COLORS["content_bg"])
        ctrl.pack(fill="x", padx=16, pady=(0, 6))

        prod_var  = tk.StringVar()
        qty_var   = tk.StringVar(value="1")
        price_var = tk.StringVar()

        tk.Label(ctrl, text="Product:", font=FONTS["small"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]).pack(side="left")
        tk.Entry(ctrl, textvariable=prod_var, width=22,
                 font=FONTS["input"]).pack(side="left", padx=4)
        tk.Label(ctrl, text="Qty:", font=FONTS["small"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]).pack(side="left")
        tk.Entry(ctrl, textvariable=qty_var, width=6,
                 font=FONTS["input"]).pack(side="left", padx=4)
        tk.Label(ctrl, text="Price:", font=FONTS["small"],
                 bg=COLORS["content_bg"], fg=COLORS["text_muted"]).pack(side="left")
        tk.Entry(ctrl, textvariable=price_var, width=8,
                 font=FONTS["input"]).pack(side="left", padx=4)

        def _add_item():
            name = prod_var.get().strip()
            if not name:
                return
            try:
                qty   = float(qty_var.get())
                price = float(price_var.get())
            except ValueError:
                messagebox.showwarning("Error", "Qty and Price must be numbers.", parent=win)
                return
            edit_items.append({"product_name": name, "qty": qty,
                               "price": price, "amount": round(qty*price, 2)})
            _refresh_tree()
            prod_var.set(""); qty_var.set("1"); price_var.set("")

        def _remove_item():
            sel = tree.selection()
            if not sel:
                return
            idx = tree.index(sel[0])
            if 0 <= idx < len(edit_items):
                edit_items.pop(idx)
                _refresh_tree()

        tk.Button(ctrl, text="➕ Add", font=FONTS["button"],
                  bg=COLORS["success"], fg="white", relief="flat",
                  padx=10, pady=6, cursor="hand2",
                  command=_add_item).pack(side="left", padx=(8,2))
        tk.Button(ctrl, text="🗑 Remove", font=FONTS["button"],
                  bg=COLORS["danger"], fg="white", relief="flat",
                  padx=10, pady=6, cursor="hand2",
                  command=_remove_item).pack(side="left", padx=2)

        # ── Save button ────────────────────────────────────
        def _do_resave():
            if not edit_items:
                messagebox.showwarning("Error", "No items.", parent=win)
                return
            try:
                new_total = sum(it["amount"] for it in edit_items)
                old_total = float(inv.get("total", 0))
                old_paid  = float(inv.get("paid", 0))
                diff      = new_total - old_total

                conn = db.get_conn()
                with db._write_lock:
                    # Update invoice total & balance
                    conn.execute(
                        "UPDATE invoices SET total=?, balance=? WHERE id=?",
                        (new_total, max(0, new_total - old_paid), inv_id))
                    # Replace items
                    conn.execute("DELETE FROM invoice_items WHERE invoice_id=?", (inv_id,))
                    for it in edit_items:
                        # resolve product_id
                        row = conn.execute(
                            "SELECT id FROM products WHERE LOWER(name)=LOWER(?)",
                            (it["product_name"],)).fetchone()
                        pid = row[0] if row else 0
                        conn.execute(
                            "INSERT INTO invoice_items "
                            "(invoice_id,product_id,qty,price,amount) VALUES (?,?,?,?,?)",
                            (inv_id, pid, it["qty"], it["price"], it["amount"]))
                    # Adjust customer due
                    if diff != 0 and inv.get("type","invoice") != "draft":
                        conn.execute(
                            "UPDATE customers SET total_due=total_due+? WHERE phone=?",
                            (diff, inv.get("customer_phone","")))
                    conn.commit()
                    conn.close()

                messagebox.showinfo("Saved",
                    f"Invoice #{inv_id} updated.\n"
                    f"New total: ₹{new_total:,.2f}", parent=win)
                win.destroy()
                self.destroy()   # close detail popup too; parent will refresh
                if self._on_delete:
                    self._on_delete()
            except Exception as ex:
                messagebox.showerror("Error", str(ex), parent=win)

        tk.Button(win, text="💾  SAVE CHANGES (same invoice number & date)",
                  font=("Segoe UI", 12, "bold"),
                  bg=COLORS["success"], fg="white",
                  relief="flat", pady=12, cursor="hand2",
                  command=_do_resave).pack(fill="x", padx=16, pady=(0, 16))

    def _delete_invoice(self):
        """Delete this invoice with confirmation, reverse customer due."""
        ref = f"{self._prefix}-{self._invoice_id}"
        inv = self._inv
        total   = float(inv.get("total",   0))
        balance = float(inv.get("balance", 0))
        if not messagebox.askyesno(
            "Delete Invoice",
            f"Permanently delete {ref}?\n\n"
            f"Bill Total : ₹{total:,.2f}\n"
            f"Balance    : ₹{balance:,.2f}\n\n"
            f"⚠ The customer's running due will be reduced by ₹{balance:,.2f}.\n"
            f"This cannot be undone.",
            icon="warning"
        ):
            return
        if db.delete_invoice(self._invoice_id):
            messagebox.showinfo("Deleted", f"{ref} has been removed.")
            if self._on_delete:
                self._on_delete()
            self.destroy()
        else:
            messagebox.showerror("Error", f"Could not delete {ref}.")


# ══════════════════════════════════════════════════════════
# CUSTOMER DETAIL POPUP
# ══════════════════════════════════════════════════════════

class CustomerDetailPopup(tk.Toplevel):
    """
    Shows full detail for one customer:
    - Summary bar (opening balance, computed due)
    - Invoice history table
    - Payment history table
    """

    def __init__(self, parent, phone):
        super().__init__(parent)
        self.phone = phone
        customer = db.get_customer(phone)
        if not customer:
            messagebox.showerror("Not Found", f"Customer {phone} not found.")
            self.destroy()
            return

        self.title(f"Customer: {customer['name']} ({phone})")
        self.geometry("900x620")
        self.configure(bg=COLORS["content_bg"])
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self._build(customer)

    def _build(self, c):
        computed_due = db.get_computed_due(self.phone)

        # ── Header ──────────────────────────────────────────
        hdr = tk.Frame(self, bg=COLORS["primary"])
        hdr.pack(fill="x")
        tk.Label(hdr, text=f"👤  {c['name']}",
                 font=FONTS["heading"], bg=COLORS["primary"], fg="#FFFFFF"
                 ).pack(side="left", padx=20, pady=14)
        tk.Button(hdr, text="✕ Close", font=FONTS["small"],
                  bg=COLORS["primary"], fg="#BFDBFE", relief="flat",
                  cursor="hand2", command=self.destroy
                  ).pack(side="right", padx=16)

        # ── Summary strip ────────────────────────────────────
        ob  = c.get("opening_balance", 0) or 0
        due_color = COLORS["danger"] if computed_due > 0 else COLORS["success"]
        summary = tk.Frame(self, bg="#EFF6FF")
        summary.pack(fill="x")

        for label, value, color in [
            ("Phone",            c["phone"],                   COLORS["text_dark"]),
            ("Address",          c.get("address","") or "—",   COLORS["text_muted"]),
            ("Opening Balance",  f"₹{ob:,.2f}",                COLORS["primary"]),
            ("Current Due",      f"₹{computed_due:,.2f}",      due_color),
        ]:
            cell = tk.Frame(summary, bg="#EFF6FF")
            cell.pack(side="left", padx=20, pady=10)
            tk.Label(cell, text=label, font=FONTS["small"],
                     bg="#EFF6FF", fg=COLORS["text_muted"]).pack(anchor="w")
            tk.Label(cell, text=value, font=FONTS["body_bold"],
                     bg="#EFF6FF", fg=color).pack(anchor="w")

        # ── Accounting breakdown ─────────────────────────────
        inv_bal = sum(i["balance"] for i in db.get_invoices_by_phone(self.phone)
                      if i.get("type", "invoice").lower() == "invoice")
        pay_sum = sum(p["amount"] for p in db.get_payments_by_phone(self.phone))
        breakdown = tk.Frame(self, bg="#F8FAFC")
        breakdown.pack(fill="x")
        tk.Label(breakdown,
                 text=(f"  Opening Balance ₹{ob:,.2f}  +  "
                       f"Invoice Balances ₹{inv_bal:,.2f}  −  "
                       f"Payments ₹{pay_sum:,.2f}  =  "
                       f"Current Due ₹{computed_due:,.2f}"),
                 font=FONTS["small"], bg="#F8FAFC",
                 fg=COLORS["text_muted"]
                 ).pack(anchor="w", padx=16, pady=6)

        # ── Two-column: invoices + payments ─────────────────
        cols_frame = tk.Frame(self, bg=COLORS["content_bg"])
        cols_frame.pack(fill="both", expand=True, padx=16, pady=12)
        cols_frame.columnconfigure(0, weight=3)
        cols_frame.columnconfigure(1, weight=2)

        # Invoices table
        inv_card = _card(cols_frame)
        inv_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(inv_card, text="🧾  Invoice History", font=FONTS["subheading"],
                 bg=COLORS["card_bg"], fg=COLORS["text_dark"]
                 ).pack(anchor="w", padx=14, pady=(12, 6))

        self.inv_tree = inv_tree = ttk.Treeview(inv_card,
                                columns=("inv","date","total","paid","bal"),
                                show="headings", height=10)
        for col, hd, w, anch in [
            ("inv",  "Invoice", 90,  "center"),
            ("date", "Date",    120, "center"),
            ("total","Total",   100, "e"),
            ("paid", "Paid",    100, "e"),
            ("bal",  "Balance", 100, "e"),
        ]:
            inv_tree.heading(col, text=hd)
            inv_tree.column(col, width=w, anchor=anch, stretch=True)
        inv_tree.tag_configure("paid",    background="#F0FDF4", foreground="#16A34A")
        inv_tree.tag_configure("partial", background="#FFFBEB", foreground="#D97706")
        inv_tree.tag_configure("unpaid",  background="#FEF2F2", foreground="#DC2626")
        inv_tree.tag_configure("draft",   background="#FEF9E7", foreground="#B7770D")

        # Double-click an invoice row to open the full detail popup
        inv_tree.bind("<Double-1>", lambda e: self._open_invoice_detail())

        isb = ttk.Scrollbar(inv_card, orient="vertical", command=inv_tree.yview)
        inv_tree.configure(yscrollcommand=isb.set)
        inv_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 12))
        isb.pack(side="right", fill="y", pady=(0, 12), padx=(0, 6))

        for inv in db.get_invoices_by_phone(self.phone):
            b, p  = inv["balance"], inv["paid"]
            kind  = (inv.get("type") or "invoice").lower()
            if kind == "draft":
                tag = "draft"
                pfx = "DRAFT"
            elif kind == "quotation":
                tag = "partial"
                pfx = "QUO"
            else:
                tag = "paid" if b <= 0 else ("partial" if p > 0 else "unpaid")
                pfx = "INV"
            inv_tree.insert("", "end", tags=(tag,), values=(
                f"{pfx}-{inv['id']}",
                inv["date"][:16],
                f"₹{inv['total']:,.2f}",
                f"₹{inv['paid']:,.2f}",
                f"₹{inv['balance']:,.2f}",
            ))

        # Payments table
        pay_card = _card(cols_frame)
        pay_card.grid(row=0, column=1, sticky="nsew")
        tk.Label(pay_card, text="💰  Payment History", font=FONTS["subheading"],
                 bg=COLORS["card_bg"], fg=COLORS["text_dark"]
                 ).pack(anchor="w", padx=14, pady=(12, 6))

        self.pay_tree = pay_tree = ttk.Treeview(pay_card,
                                columns=("id","amount","date"),
                                show="headings", height=10)
        for col, hd, w, anch in [
            ("id",     "#",       60,  "center"),
            ("amount", "Amount",  110, "e"),
            ("date",   "Date",    140, "center"),
        ]:
            pay_tree.heading(col, text=hd)
            pay_tree.column(col, width=w, anchor=anch, stretch=True)

        psb = ttk.Scrollbar(pay_card, orient="vertical", command=pay_tree.yview)
        pay_tree.configure(yscrollcommand=psb.set)
        pay_tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 12))
        psb.pack(side="right", fill="y", pady=(0, 12), padx=(0, 6))

        for pay in db.get_payments_by_phone(self.phone):
            pay_tree.insert("", "end", values=(
                f"P-{pay['id']}",
                f"₹{pay['amount']:,.2f}",
                pay["date"][:16],
            ))

        # ── Referenced Bills section ─────────────────────────
        # Shows all invoices where Bala was the reference customer.
        ref_bills = db.get_invoices_by_reference(self.phone)
        if ref_bills:
            ref_card = _card(self)
            ref_card.pack(fill="x", padx=16, pady=(8, 0))
            tk.Label(ref_card,
                     text=f"🤝  Referred Bills  ({len(ref_bills)} customers sent by this person)",
                     font=FONTS["subheading"],
                     bg=COLORS["card_bg"], fg=COLORS["text_dark"]
                     ).pack(anchor="w", padx=14, pady=(10, 4))

            ref_tree = ttk.Treeview(ref_card,
                                    columns=("inv", "customer", "date", "total", "bal"),
                                    show="headings", height=min(5, len(ref_bills)))
            for col, hd, w, anch in [
                ("inv",      "Invoice",       90,  "center"),
                ("customer", "Customer",      160, "w"),
                ("date",     "Date",          110, "center"),
                ("total",    "Total",         90,  "e"),
                ("bal",      "Balance",       90,  "e"),
            ]:
                ref_tree.heading(col, text=hd)
                ref_tree.column(col, width=w, anchor=anch, stretch=True)

            ref_total = 0.0
            for inv in ref_bills:
                pfx = "QUO" if (inv.get("type") or "").lower() == "quotation" else "INV"
                ref_total += float(inv.get("total", 0))
                ref_tree.insert("", "end", values=(
                    f"{pfx}-{inv['id']}",
                    inv.get("customer_name", inv.get("customer_phone", "—")),
                    (inv.get("date") or "")[:10],
                    f"₹{float(inv.get('total', 0)):,.2f}",
                    f"₹{float(inv.get('balance', 0)):,.2f}",
                ))
            ref_tree.pack(fill="x", padx=10, pady=(0, 4))
            tk.Label(ref_card,
                     text=f"Total business referred: ₹{ref_total:,.2f}",
                     font=FONTS["small_bold"],
                     bg=COLORS["card_bg"], fg=COLORS["success"]
                     ).pack(anchor="e", padx=14, pady=(0, 8))

        # ── Action buttons ──────────────────────────────────
        act = tk.Frame(self, bg=COLORS["content_bg"])
        act.pack(fill="x", padx=16, pady=(0, 12))

        tk.Button(act, text="📋  View Invoice",
                  font=FONTS["button"], bg=COLORS["primary"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._open_invoice_detail
                  ).pack(side="left", padx=(0, 10))
        tk.Button(act, text="🗑  Delete Selected Bill",
                  font=FONTS["button"], bg=COLORS["danger"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._delete_selected_invoice
                  ).pack(side="left", padx=(0, 10))
        tk.Button(act, text="🗑  Delete Selected Payment",
                  font=FONTS["button"], bg=COLORS["danger"], fg="white",
                  relief="flat", padx=12, pady=6, cursor="hand2",
                  command=self._delete_selected_payment
                  ).pack(side="left")

    def _get_selected_invoice_id(self):
        """Return (invoice_id, ref_string) from selected inv_tree row, or (None, None)."""
        sel = self.inv_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Pick an invoice row first.")
            return None, None
        v   = self.inv_tree.item(sel[0])["values"]
        ref = str(v[0])                                       # e.g. "INV-12"
        try:
            invoice_id = int(ref.split("-")[1])
            return invoice_id, ref
        except (IndexError, ValueError):
            messagebox.showerror("Error", f"Cannot parse invoice id: {ref}")
            return None, None

    def _open_invoice_detail(self):
        """Open the full InvoiceDetailPopup for the selected invoice."""
        invoice_id, _ = self._get_selected_invoice_id()
        if invoice_id is None:
            return
        InvoiceDetailPopup(
            self, invoice_id,
            on_delete=self.destroy   # close this popup too after delete
        )

    def _delete_selected_invoice(self):
        invoice_id, ref = self._get_selected_invoice_id()
        if invoice_id is None:
            return
        v = self.inv_tree.item(self.inv_tree.selection()[0])["values"]
        if not messagebox.askyesno(
            "Delete bill",
            f"Delete {ref}?\n\n"
            f"Total {v[2]}, Balance {v[4]}.\n"
            f"This reverses the customer's running due\n"
            f"and pushes the delete to the cloud."
        ):
            return
        if db.delete_invoice(invoice_id):
            messagebox.showinfo("Deleted", f"{ref} removed.")
            self.destroy()
        else:
            messagebox.showerror("Error", f"Could not delete {ref}.")

    def _delete_selected_payment(self):
        sel = self.pay_tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Pick a payment row first.")
            return
        v = self.pay_tree.item(sel[0])["values"]
        ref = str(v[0])                                       # e.g. "P-5"
        try:
            payment_id = int(ref.split("-")[1])
        except (IndexError, ValueError):
            messagebox.showerror("Error", f"Cannot parse payment id: {ref}")
            return
        if not messagebox.askyesno(
            "Delete payment",
            f"Delete {ref} of {v[1]}?\n\n"
            f"The amount will be added back to the customer's running due."
        ):
            return
        if db.delete_payment(payment_id):
            messagebox.showinfo("Deleted", f"{ref} removed.")
            self.destroy()
        else:
            messagebox.showerror("Error", f"Could not delete {ref}.")


# ══════════════════════════════════════════════════════════
# MAIN FRAME
# ══════════════════════════════════════════════════════════

class HistoryFrame(tk.Frame):
    """Invoice History Screen — shows all invoices, search by name/phone/id."""

    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self._build_ui()

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────
        toolbar = tk.Frame(self, bg=COLORS["primary"])
        toolbar.pack(fill="x")

        tk.Label(toolbar, text="🧾  Invoice History",
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["primary"], fg="#FFFFFF"
                 ).pack(side="left", padx=20, pady=14)

        # Search
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._load())
        se = tk.Entry(toolbar, textvariable=self.search_var,
                      font=FONTS["input"], width=26,
                      bg="white", fg="#1A1A2E", relief="flat",
                      highlightbackground="#CBD5E1", highlightthickness=1)
        se.pack(side="left", ipady=5, padx=(0,4), pady=10)
        tk.Label(toolbar, text="🔍 Search customer / invoice",
                 font=FONTS["small"], bg=COLORS["primary"], fg="#BFDBFE"
                 ).pack(side="left")

        tk.Button(toolbar, text="👥  Customers",
                  font=FONTS["button"], bg=COLORS["success"], fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self._open_customers
                  ).pack(side="right", padx=(0,12), pady=10)

        # ── Invoice list ──────────────────────────────────────
        list_card = _card(self)
        list_card.pack(fill="both", expand=True, padx=20, pady=(16,0))
        tk.Frame(list_card, bg=COLORS["primary"], height=3).pack(fill="x")

        hdr = tk.Frame(list_card, bg=COLORS["card_bg"])
        hdr.pack(fill="x", padx=16, pady=(10,4))
        self.count_lbl = tk.Label(hdr, text="All Invoices",
                                  font=FONTS["subheading"],
                                  bg=COLORS["card_bg"], fg="#1A1A2E")
        self.count_lbl.pack(side="left")
        tk.Label(hdr, text="Double-click to open  |  Click once to select",
                 font=FONTS["small"], bg=COLORS["card_bg"],
                 fg=COLORS["text_muted"]).pack(side="right")

        cols = ("inv","customer","date","total","paid","balance","status")
        self.tree = ttk.Treeview(list_card, columns=cols, show="headings", height=18)
        for col, hd, w, anch in [
            ("inv",      "Invoice",  90,  "center"),
            ("customer", "Customer", 200, "w"),
            ("date",     "Date",     130, "center"),
            ("total",    "Total ₹",  110, "e"),
            ("paid",     "Paid ₹",   100, "e"),
            ("balance",  "Balance ₹",110, "e"),
            ("status",   "Status",   80,  "center"),
        ]:
            self.tree.heading(col, text=hd)
            self.tree.column(col, width=w, anchor=anch)

        self.tree.tag_configure("paid",    background="#F0FDF4", foreground="#16A34A")
        self.tree.tag_configure("partial", background="#FFFBEB", foreground="#D97706")
        self.tree.tag_configure("unpaid",  background="#FEF2F2", foreground="#DC2626")
        self.tree.tag_configure("draft",   background="#FEF9E7", foreground="#B7770D")
        self.tree.tag_configure("quotation",background="#F0F4FF",foreground="#3B4FD0")

        sb = ttk.Scrollbar(list_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(16,0), pady=(0,12))
        sb.pack(side="right", fill="y", pady=(0,12), padx=(0,6))

        self.tree.bind("<Double-1>", lambda e: self._open_detail())
        self.tree.bind("<Return>",   lambda e: self._open_detail())

        # ── Bottom action bar ─────────────────────────────────
        act = tk.Frame(self, bg=COLORS["content_bg"])
        act.pack(fill="x", padx=20, pady=(6,12))
        tk.Button(act, text="📋  Open Invoice",
                  font=FONTS["button"], bg=COLORS["primary"], fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self._open_detail
                  ).pack(side="left", padx=(0,8))

        self._load()

    def refresh(self):
        """Called by app when this tab is shown — reload fresh data."""
        self._load()

    def _load(self):
        q = self.search_var.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        try:
            invoices = db.get_all_invoices()
        except Exception as e:
            return
        # enrich with customer name
        results = []
        for inv in invoices:
            phone = inv.get("customer_phone","")
            cust  = db.get_customer(phone)
            cname = cust["name"] if cust else phone
            inv["_cname"] = cname
            results.append(inv)

        if q:
            results = [i for i in results if
                       q in i["_cname"].lower() or
                       q in (i.get("customer_phone","")) or
                       q in str(i["id"])]

        self.count_lbl.config(text=f"{len(results)} Invoice(s)")
        for inv in results:
            kind = (inv.get("type") or "invoice").lower()
            b, p = float(inv.get("balance",0)), float(inv.get("paid",0))
            if kind == "draft":
                tag, pfx, status = "draft",     "DRAFT", "Draft"
            elif kind == "quotation":
                tag, pfx, status = "quotation", "QUO",   "Quote"
            elif b <= 0:
                tag, pfx, status = "paid",      "INV",   "Paid"
            elif p > 0:
                tag, pfx, status = "partial",   "INV",   "Partial"
            else:
                tag, pfx, status = "unpaid",    "INV",   "Unpaid"

            self.tree.insert("", "end",
                iid=str(inv["id"]), tags=(tag,),
                values=(
                    f"{pfx}-{inv['id']}",
                    inv["_cname"],
                    str(inv.get("date",""))[:16],
                    f"₹{float(inv.get('total',0)):,.2f}",
                    f"₹{p:,.2f}",
                    f"₹{b:,.2f}",
                    status,
                ))

    def _open_detail(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select", "Click an invoice first.")
            return
        inv_id = int(sel[0])
        InvoiceDetailPopup(self, inv_id, on_delete=self._load)

    def _open_customers(self):
        """Open the customer management window."""
        win = tk.Toplevel(self)
        win.title("Customer Management")
        win.geometry("900x600")
        win.configure(bg=COLORS["content_bg"])
        _CustomerMgmtPanel(win)
        win.grab_set()


class _CustomerMgmtPanel(tk.Frame):
    """Standalone customer list — shown inside a Toplevel."""
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self.pack(fill="both", expand=True)
        self._build()

    def _build(self):
        toolbar = tk.Frame(self, bg=COLORS["primary"])
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="👥  Customer Management",
                 font=("Segoe UI",12,"bold"),
                 bg=COLORS["primary"], fg="white").pack(side="left", padx=16, pady=12)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._load(self.search_var.get()))
        se = tk.Entry(toolbar, textvariable=self.search_var,
                      font=FONTS["input"], width=22,
                      bg="white", fg="#1A1A2E", relief="flat",
                      highlightbackground="#CBD5E1", highlightthickness=1)
        se.pack(side="left", ipady=5, padx=4, pady=10)
        for txt, cmd, col in [
            ("➕ Add",  self._add,  COLORS["success"]),
            ("✏️ Edit", self._edit, COLORS["info"]),
            ("📋 View", self._view, COLORS["primary"]),
        ]:
            tk.Button(toolbar, text=txt, font=FONTS["button"],
                      bg=col, fg="white", relief="flat",
                      padx=10, pady=6, cursor="hand2",
                      command=cmd).pack(side="right", padx=(0,8), pady=10)

        cols = ("id","name","phone","address","due")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for col, hd, w, anch in [
            ("id",      "ID",      55,  "center"),
            ("name",    "Name",    220, "w"),
            ("phone",   "Phone",   130, "center"),
            ("address", "Address", 200, "w"),
            ("due",     "Due ₹",   110, "e"),
        ]:
            self.tree.heading(col, text=hd)
            self.tree.column(col, width=w, anchor=anch)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(16,0), pady=12)
        sb.pack(side="right", fill="y", pady=12, padx=(0,6))
        self.tree.bind("<Double-1>", lambda e: self._view())
        self._load()

    def _load(self, q=""):
        self.tree.delete(*self.tree.get_children())
        custs = db.get_all_customers()
        if q:
            ql = q.lower()
            custs = [c for c in custs if ql in (c.get("name","")).lower()
                     or ql in (c.get("phone",""))]
        for c in custs:
            due = c.get("total_due",0) or 0
            tag = "red" if due > 0 else ""
            self.tree.insert("","end", iid=str(c["id"]), tags=(tag,),
                values=(c["id"], c.get("name",""), c.get("phone",""),
                        c.get("address","") or "", f"₹{due:,.2f}"))
        self.tree.tag_configure("red", foreground=COLORS["danger"])

    def _selected_cust(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Select","Click a customer first.")
            return None
        return db.get_customer_by_id(int(sel[0]))

    def _view(self):
        c = self._selected_cust()
        if c:
            CustomerDetailPopup(self, c["phone"])

    def _add(self):
        def save(name, phone, address, ob):
            db.create_customer(name, phone, address, ob)
            self._load()
        CustomerFormDialog(self, on_save=save)

    def _edit(self):
        c = self._selected_cust()
        if not c:
            return
        def save(name, phone, address, ob):
            db.update_customer(c["phone"], name, address, ob)
            self._load()
        CustomerFormDialog(self, on_save=save, customer=c)
