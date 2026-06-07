"""Payment Frame — live autocomplete search like billing frame"""
import tkinter as tk
from tkinter import ttk, messagebox
from config import COLORS, FONTS
from database import get_customer, create_payment, get_payments_by_phone, get_all_customers
from whatsapp import send_payment_message
from task_queue import add_task
import database as db


def _card(parent):
    return tk.Frame(parent, bg=COLORS["card_bg"],
                    highlightbackground=COLORS["card_border"],
                    highlightthickness=1)

def _label(parent, text, font_key="body", color="text_medium"):
    return tk.Label(parent, text=text, font=FONTS[font_key],
                    bg=parent.cget("bg"), fg=COLORS[color])

def _entry(parent, var, width=18):
    return tk.Entry(parent, textvariable=var, font=FONTS["input"], width=width,
                    bg=COLORS["input_bg"], fg="#1A1A2E",
                    insertbackground="#1B3A6B",
                    relief="flat",
                    highlightbackground=COLORS["input_border"],
                    highlightcolor=COLORS["primary"],
                    highlightthickness=1)


class PaymentFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self._current_phone = None          # resolved phone after customer selected
        self._sugg_data     = []            # autocomplete candidates
        self._selecting     = False         # guard against re-triggering trace
        self._build_ui()

    def _build_ui(self):
        outer = tk.Frame(self, bg=COLORS["content_bg"])
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Search card ───────────────────────────────────────
        c1 = _card(outer)
        c1.pack(fill="x", pady=(0, 10))
        tk.Frame(c1, bg=COLORS["primary"], height=3).pack(fill="x")
        b1 = tk.Frame(c1, bg=COLORS["card_bg"])
        b1.pack(fill="x", padx=16, pady=14)

        _label(b1, "Find Customer", "subheading", "text_dark").pack(anchor="w", pady=(0, 8))

        # Three search boxes side-by-side (ID / Name / Phone) like billing frame
        search_row = tk.Frame(b1, bg=COLORS["card_bg"])
        search_row.pack(fill="x")

        self._id_var    = tk.StringVar()
        self._name_var  = tk.StringVar()
        self._phone_var = tk.StringVar()
        # phone_var alias for record_payment
        self.phone_var  = self._phone_var

        def _make_box(parent, label, var, width, field):
            """One labelled entry with live dropdown."""
            frame = tk.Frame(parent, bg=COLORS["card_bg"])
            _label(frame, label, "small", "text_muted").pack(anchor="w")
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
                if self._selecting:
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
                    matches = [c for c in all_c if str(c.get("id", "")).startswith(q)]
                elif field == "name":
                    matches = [c for c in all_c if q_low in (c.get("name") or "").lower()]
                else:   # phone
                    matches = [c for c in all_c if q in (c.get("phone") or "")]
                matches = matches[:8]
                self._sugg_data = matches
                lb.delete(0, tk.END)
                for c in matches:
                    due = c.get("total_due", 0) or 0
                    lb.insert(tk.END,
                        f"  [{c['id']}]  {c['name'][:22]}  {c['phone']}  Due:₹{due:,.0f}")
                if matches:
                    lb_frame.pack(fill="x", pady=(0, 4))
                    lb.selection_set(0)
                else:
                    lb_frame.pack_forget()

            def on_select(e=None):
                sel = lb.curselection()
                if not sel or not self._sugg_data:
                    return
                c = self._sugg_data[sel[0]]
                self._selecting = True
                self._id_var.set(str(c.get("id", "")))
                self._name_var.set(c["name"])
                self._phone_var.set(c["phone"])
                self._selecting = False
                lb_frame.pack_forget()
                lb.delete(0, tk.END)
                self._load_customer(c)

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

        id_box    = _make_box(search_row, "🔢 Customer ID",    self._id_var,    10, "id")
        name_box  = _make_box(search_row, "👤 Customer Name",  self._name_var,  22, "name")
        phone_box = _make_box(search_row, "📞 Phone Number",   self._phone_var, 16, "phone")
        id_box.pack(side="left",   padx=(0, 16))
        name_box.pack(side="left", padx=(0, 16))
        phone_box.pack(side="left")

        # ── Customer info card ────────────────────────────────
        c2 = _card(outer)
        c2.pack(fill="x", pady=(0, 10))
        b2 = tk.Frame(c2, bg=COLORS["card_bg"])
        b2.pack(fill="x", padx=16, pady=14)

        info_row = tk.Frame(b2, bg=COLORS["card_bg"])
        info_row.pack(fill="x")

        name_box2 = tk.Frame(info_row, bg=COLORS["card_bg"])
        name_box2.pack(side="left")
        _label(name_box2, "Customer Name", "small", "text_muted").pack(anchor="w")
        self.cname_label = tk.Label(name_box2, text="—",
                                     font=("Segoe UI", 13, "bold"),
                                     bg=COLORS["card_bg"], fg="#1A1A2E")
        self.cname_label.pack(anchor="w")

        # Due amount box
        due_box = tk.Frame(info_row, bg=COLORS["danger_light"],
                           highlightbackground=COLORS["danger_border"],
                           highlightthickness=1)
        due_box.pack(side="right", ipadx=20, ipady=10)
        _label(due_box, "TOTAL DUE", "small_bold", "danger").pack()
        self.cdue_label = tk.Label(due_box, text="₹0.00",
                                    font=("Segoe UI", 20, "bold"),
                                    bg=COLORS["danger_light"],
                                    fg=COLORS["danger"])
        self.cdue_label.pack()

        # NIL Balance button — right below the customer info card
        nil_row = tk.Frame(outer, bg=COLORS["content_bg"])
        nil_row.pack(fill="x", pady=(0, 4))
        tk.Button(nil_row,
                  text="🔴  NIL Balance  (Write off entire due to ₹0)",
                  font=FONTS["button"],
                  bg="#7B241C", fg="white",
                  relief="flat", padx=14, pady=8, cursor="hand2",
                  command=self._nil_balance
                  ).pack(side="left")

        # ── Payment entry card ────────────────────────────────
        c3 = _card(outer)
        c3.pack(fill="x", pady=(0, 10))
        tk.Frame(c3, bg=COLORS["success"], height=3).pack(fill="x")
        b3 = tk.Frame(c3, bg=COLORS["card_bg"])
        b3.pack(fill="x", padx=16, pady=14)

        _label(b3, "Enter Payment", "subheading", "text_dark").pack(anchor="w", pady=(0, 10))

        prow = tk.Frame(b3, bg=COLORS["card_bg"])
        prow.pack(anchor="w")
        _label(prow, "Payment Amount (₹)", "small", "text_muted").pack(anchor="w")
        pinp = tk.Frame(prow, bg=COLORS["card_bg"])
        pinp.pack(anchor="w", pady=4)
        self.amount_var = tk.StringVar()
        ae = _entry(pinp, self.amount_var, width=18)
        ae.pack(side="left")
        ae.bind("<Return>", lambda e: self._record_payment())
        tk.Button(pinp, text="  ✓  Record Payment + WhatsApp",
                  font=FONTS["button"],
                  bg=COLORS["success"], fg="white",
                  relief="flat", padx=20, pady=7, cursor="hand2",
                  activebackground="#15803D",
                  command=self._record_payment).pack(side="left", padx=(10, 0))

        # ── Payment history card ──────────────────────────────
        c4 = _card(outer)
        c4.pack(fill="both", expand=True)
        b4 = tk.Frame(c4, bg=COLORS["card_bg"])
        b4.pack(fill="both", expand=True)

        th = tk.Frame(b4, bg=COLORS["table_header_bg"])
        th.pack(fill="x")
        for txt, w in [("#", 6), ("Amount (₹)", 20), ("Date & Time", 30)]:
            tk.Label(th, text=txt, font=FONTS["small_bold"],
                     bg=COLORS["table_header_bg"],
                     fg=COLORS["table_header_fg"],
                     width=w, anchor="w", pady=8, padx=10).pack(side="left")

        cols = ("no", "amount", "date")
        self.tree = ttk.Treeview(b4, columns=cols, show="headings", height=8)
        self.tree.heading("no",     text="#")
        self.tree.heading("amount", text="Amount (₹)")
        self.tree.heading("date",   text="Date & Time")
        self.tree.column("no",     width=50,  anchor="center")
        self.tree.column("amount", width=160, anchor="e")
        self.tree.column("date",   width=220, anchor="center")

        sb = ttk.Scrollbar(b4, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    # ── Helpers ───────────────────────────────────────────────

    def _load_customer(self, c):
        """Populate info panel and payment history for customer dict c."""
        self._current_phone = c["phone"]
        cid  = c.get("id", "")
        due  = c.get("total_due", 0) or 0
        self.cname_label.config(text=f"[{cid}]  {c['name']}")
        self.cdue_label.config(
            text=f"₹{due:,.2f}",
            fg=COLORS["danger"] if due > 0 else COLORS["success"])
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(get_payments_by_phone(c["phone"]), 1):
            self.tree.insert("", "end", values=(
                i, f"₹{p['amount']:,.2f}", p["date"]))

    def _record_payment(self):
        phone = self._current_phone
        if not phone or not phone.isdigit() or len(phone) != 10:
            messagebox.showwarning("Error", "Search and select a customer first.")
            return
        c = get_customer(phone)
        if not c:
            messagebox.showerror("Error", "Customer not found.")
            return
        try:
            amount = float(self.amount_var.get().strip())
            if amount <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Error", "Enter a valid positive amount.")
            return
        if amount > c["total_due"]:
            messagebox.showwarning("Error",
                f"Payment ₹{amount:,.2f} exceeds due ₹{c['total_due']:,.2f}.")
            return
        try:
            payment_id = create_payment(phone, amount)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        remaining = c["total_due"] - amount
        try:
            add_task("cloud_sync", {
                "phone":      phone,
                "payment_id": payment_id,
            })
        except Exception:
            pass

        messagebox.showinfo("Payment Recorded",
            f"Amount: \u20b9{amount:,.2f}\nRemaining: \u20b9{remaining:,.2f}")
        try:
            send_payment_message(phone, c["name"], amount, remaining)
        except Exception:
            pass
        self.amount_var.set("")
        # Refresh display
        updated = get_customer(phone)
        if updated:
            self._load_customer(updated)

    def _nil_balance(self):
        """Zero out the customer's entire outstanding balance (write-off)."""
        phone = self._current_phone
        if not phone or not phone.isdigit() or len(phone) != 10:
            messagebox.showwarning("NIL Balance",
                "Search and select a customer first.")
            return
        c = get_customer(phone)
        if not c:
            messagebox.showerror("NIL Balance", "Customer not found.")
            return
        due = c.get("total_due", 0) or 0
        if due <= 0:
            messagebox.showinfo("NIL Balance",
                "Balance is already \u20b90.00 \u2014 nothing to clear.")
            return
        if not messagebox.askyesno(
            "NIL Balance \u2014 Confirm",
            f"Customer  : {c['name']}\n"
            f"Current Due : \u20b9{due:,.2f}\n\n"
            f"This will set the balance to \u20b90.00 immediately.\n"
            f"A write-off record is saved for audit.\n\n"
            f"Proceed?",
            icon="warning"
        ):
            return
        try:
            payment_id, wiped = db.nil_customer_balance(phone)
            try:
                if payment_id:
                    add_task("cloud_sync", {"phone": phone, "payment_id": payment_id})
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror("NIL Balance Failed", str(e))
            return
        messagebox.showinfo("NIL Balance Done",
            f"\u2705 \u20b9{wiped:,.2f} wiped for {c['name']}.\n"
            f"Balance is now \u20b90.00.")
        # Refresh display
        updated = get_customer(phone)
        if updated:
            self._load_customer(updated)
