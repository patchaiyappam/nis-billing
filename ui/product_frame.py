"""Product Frame — Clean White & Professional redesign"""
import tkinter as tk
from tkinter import ttk, messagebox
from config import COLORS, FONTS
from database import get_all_products, add_product, update_product, delete_product, get_product
from task_queue import add_task


def _card(parent):
    return tk.Frame(parent, bg=COLORS["card_bg"],
                    highlightbackground=COLORS["card_border"],
                    highlightthickness=1)

def _entry(parent, var, width=22, **kw):
    return tk.Entry(parent, textvariable=var, font=FONTS["input"], width=width,
                    bg=COLORS["input_bg"], fg="#1A1A2E",
                    relief="flat",
                    highlightbackground=COLORS["input_border"],
                    highlightcolor=COLORS["primary"],
                    highlightthickness=1, **kw)


class ProductFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=COLORS["content_bg"])
        self._build_ui()
        self._refresh()

    def _build_ui(self):
        outer = tk.Frame(self, bg=COLORS["content_bg"])
        outer.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Form card ─────────────────────────────────────
        c1 = _card(outer)
        c1.pack(fill="x", pady=(0, 12))
        tk.Frame(c1, bg=COLORS["primary"], height=3).pack(fill="x")
        b1 = tk.Frame(c1, bg=COLORS["card_bg"])
        b1.pack(fill="x", padx=16, pady=14)

        tk.Label(b1, text="Add / Edit Product", font=FONTS["subheading"],
                 bg=COLORS["card_bg"], fg="#1A1A2E").pack(anchor="w", pady=(0,12))

        fields = tk.Frame(b1, bg=COLORS["card_bg"])
        fields.pack(fill="x")

        # ID field
        idf = tk.Frame(fields, bg=COLORS["card_bg"])
        idf.pack(side="left")
        tk.Label(idf, text="ID (for edit)", font=FONTS["small"],
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="w")
        self.id_var = tk.StringVar()
        _entry(idf, self.id_var, width=7).pack(pady=4)

        # Name field
        nf = tk.Frame(fields, bg=COLORS["card_bg"])
        nf.pack(side="left", padx=(16,0))
        tk.Label(nf, text="Product Name", font=FONTS["small"],
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="w")
        self.name_var = tk.StringVar()
        _entry(nf, self.name_var, width=32).pack(pady=4)

        # Price field
        pf = tk.Frame(fields, bg=COLORS["card_bg"])
        pf.pack(side="left", padx=(16,0))
        tk.Label(pf, text="Price (Rs.)", font=FONTS["small"],
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="w")
        self.price_var = tk.StringVar()
        _entry(pf, self.price_var, width=12).pack(pady=4)

        # Unit dropdown (Nos / Kgs)
        uf = tk.Frame(fields, bg=COLORS["card_bg"])
        uf.pack(side="left", padx=(16,0))
        tk.Label(uf, text="Unit", font=FONTS["small"],
                 bg=COLORS["card_bg"], fg=COLORS["text_muted"]).pack(anchor="w")
        self.unit_var = tk.StringVar(value="Nos")
        unit_combo = ttk.Combobox(uf, textvariable=self.unit_var,
                                  values=["Nos", "Kgs", "Ft", "Ltr"], width=8,
                                  state="readonly", font=FONTS["input"])
        unit_combo.pack(pady=4)

        # Buttons
        btn_row = tk.Frame(b1, bg=COLORS["card_bg"])
        btn_row.pack(fill="x", pady=(10, 0))

        for txt, color, fg, cmd in [
            ("  + Add New",  "success", "white", self._add),
            ("  ✎ Update",   "primary", "white", self._update),
            ("  🗑 Delete",   "danger",  "white", self._delete),
            ("  ↺ Refresh",  "info",    "white", self._refresh),
        ]:
            tk.Button(btn_row, text=txt, font=FONTS["button"],
                      bg=COLORS[color], fg=fg, relief="flat",
                      padx=14, pady=6, cursor="hand2",
                      command=cmd).pack(side="left", padx=(0,8))

        # ── Products table card ───────────────────────────
        c2 = _card(outer)
        c2.pack(fill="both", expand=True)

        th = tk.Frame(c2, bg=COLORS["table_header_bg"])
        th.pack(fill="x")
        for txt, w in [("ID", 6), ("Product Name", 40), ("Price (Rs.)", 13), ("Unit", 8)]:
            tk.Label(th, text=txt, font=FONTS["small_bold"],
                     bg=COLORS["table_header_bg"],
                     fg=COLORS["table_header_fg"],
                     width=w, anchor="w", pady=8, padx=12).pack(side="left")

        cols = ("id","name","price","unit")
        self.tree = ttk.Treeview(c2, columns=cols, show="headings", height=18)
        self.tree.heading("id",    text="ID");    self.tree.column("id",    width=60,  anchor="center")
        self.tree.heading("name",  text="Product Name"); self.tree.column("name",  width=380)
        self.tree.heading("price", text="Price (Rs.)");  self.tree.column("price", width=120, anchor="e")
        self.tree.heading("unit",  text="Unit");         self.tree.column("unit",  width=70,  anchor="center")

        sb = ttk.Scrollbar(c2, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, p in enumerate(get_all_products()):
            tag = "alt" if i % 2 == 0 else ""
            self.tree.insert("", "end", tags=(tag,),
                             values=(p["id"], p["name"],
                                     f"Rs. {p['price']:,.2f}",
                                     p.get("unit", "Nos") or "Nos"))
        self.tree.tag_configure("alt", background=COLORS["table_row_alt"])

    def _on_select(self, e):
        sel = self.tree.selection()
        if sel:
            v = self.tree.item(sel[0])["values"]
            self.id_var.set(str(v[0]))
            self.name_var.set(v[1])
            self.price_var.set(str(v[2]).replace("Rs. ", "").replace(",", ""))
            self.unit_var.set(str(v[3]) if len(v) > 3 else "Nos")

    def _add(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Error", "Enter product name."); return
        try:
            price = float(self.price_var.get().strip())
            if price <= 0: raise ValueError
        except ValueError:
            messagebox.showwarning("Error", "Enter a valid price."); return
        unit = self.unit_var.get().strip() or "Nos"
        try:
            add_product(name, price, unit)
        except Exception as e:
            messagebox.showerror("Add Failed", f"Could not save product:\n{e}")
            return
        try:
            from database import search_products
            matches = search_products(name)
            new_prod = next((p for p in matches if p["name"] == name), None)
            if new_prod:
                add_task("cloud_sync", {"product_id": new_prod["id"]})
        except Exception:
            pass
        messagebox.showinfo("Added", f"Product '{name}' added!")
        self._clear(); self._refresh()

    def _update(self):
        pid = self.id_var.get().strip()
        if not pid.isdigit():
            messagebox.showwarning("Error", "Select a product to update."); return
        name = self.name_var.get().strip()
        if not name:
            messagebox.showwarning("Error", "Enter product name."); return
        try:
            price = float(self.price_var.get().strip())
        except ValueError:
            messagebox.showwarning("Error", "Enter a valid price."); return
        if not get_product(int(pid)):
            messagebox.showerror("Error", f"Product #{pid} not found."); return
        unit = self.unit_var.get().strip() or "Nos"
        try:
            update_product(int(pid), name, price, unit)
        except Exception as e:
            messagebox.showerror("Update Failed", f"Could not update product:\n{e}")
            return
        try:
            add_task("cloud_sync", {"product_id": int(pid)})
        except Exception:
            pass
        messagebox.showinfo("Updated", f"Product #{pid} updated!")
        self._clear(); self._refresh()

    def _delete(self):
        pid = self.id_var.get().strip()
        if not pid.isdigit():
            messagebox.showwarning("Error", "Select a product to delete."); return
        if not get_product(int(pid)):
            messagebox.showerror("Error", f"Product #{pid} not found."); return
        if messagebox.askyesno("Confirm", f"Delete product #{pid}? This cannot be undone."):
            delete_product(int(pid))
            # Note: deletes are not synced to cloud (cloud_pull would resurrect
            # deleted items). To permanently remove a product from both PCs,
            # delete it via the Supabase dashboard as well.
            messagebox.showinfo("Deleted", "Product removed.")
            self._clear(); self._refresh()

    def _clear(self):
        self.id_var.set(""); self.name_var.set(""); self.price_var.set("")
        self.unit_var.set("Nos")
