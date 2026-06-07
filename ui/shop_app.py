"""
shop_app.py — Shop Mode (Simple UI for Dad)
============================================
NEW INDIAN STEEL Billing System

Large buttons, only New Bill and Add Payment.
No confusing menus. Clock visible always.
Dark navy sidebar, white content.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import threading

from config import COLORS, FONTS, SHOP_NAME
from logger import get_logger
from ui.billing_frame import BillingFrame
from ui.payment_frame import PaymentFrame
from ui.history_frame import HistoryFrame

log = get_logger(__name__)


class ShopApp(tk.Tk):
    """
    Simplified app for shop PC.
    Only shows: New Bill | Add Payment
    Large fonts, no clutter, easy for elderly users.
    """

    def __init__(self):
        super().__init__()
        self.title(f"{SHOP_NAME} — Billing")
        self.geometry("1280x800")
        self.minsize(900, 600)
        self.configure(bg=COLORS["content_bg"])
        try:
            self.state("zoomed")
        except Exception:
            pass

        self._configure_styles()
        self._build_sidebar()
        self._build_main()
        self._show("billing")
        self._start_sync()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        log.info("ShopApp started (shop/dad mode).")

    # ── Styles ────────────────────────────────────────────
    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            font=FONTS["body"], rowheight=40,
            background=COLORS["card_bg"],
            fieldbackground=COLORS["card_bg"],
            foreground=COLORS["text_dark"],
            borderwidth=0, relief="flat")
        style.configure("Treeview.Heading",
            font=FONTS["body_bold"],
            background=COLORS["table_header_bg"],
            foreground=COLORS["table_header_fg"],
            relief="flat", borderwidth=0)
        style.map("Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", "#FFFFFF")])

    # ── Sidebar ───────────────────────────────────────────
    def _build_sidebar(self):
        self.sidebar = tk.Frame(self, bg=COLORS["sidebar_bg"], width=260)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo area
        logo_frame = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"])
        logo_frame.pack(fill="x")
        tk.Frame(logo_frame, bg=COLORS["primary"], height=5).pack(fill="x")

        inner = tk.Frame(logo_frame, bg=COLORS["sidebar_bg"])
        inner.pack(fill="x", padx=20, pady=18)
        tk.Label(inner, text="⚙", font=("Segoe UI", 32),
                 bg=COLORS["sidebar_bg"], fg="#FFFFFF").pack(anchor="w")
        tk.Label(inner, text=SHOP_NAME,
                 font=("Segoe UI", 17, "bold"),
                 bg=COLORS["sidebar_bg"], fg="#FFFFFF").pack(anchor="w", pady=(6, 0))
        tk.Label(inner, text="Billing System",
                 font=("Segoe UI", 12),
                 bg=COLORS["sidebar_bg"], fg="#A8C4E0").pack(anchor="w")

        tk.Frame(self.sidebar, bg=COLORS["divider"],
                 height=1).pack(fill="x", padx=16, pady=(0, 12))

        # ── Big nav buttons ───────────────────────────────
        self._active = None
        self._nav = {}

        nav_items = [
            ("billing", "🧾", "NEW BILL"),
            ("payment", "💰", "ADD PAYMENT"),
            ("history", "📋", "HISTORY"),
        ]
        for key, icon, label in nav_items:
            self._nav[key] = self._make_nav(key, icon, label)

        # Spacer
        tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"]).pack(fill="both", expand=True)
        tk.Frame(self.sidebar, bg=COLORS["divider"],
                 height=1).pack(fill="x", padx=16, pady=6)

        # Sync status
        self.status_var = tk.StringVar(value="📴  Offline")
        tk.Label(self.sidebar, textvariable=self.status_var,
                 font=("Segoe UI", 12),
                 bg=COLORS["sidebar_bg"], fg="#A8C4E0").pack(pady=(4, 0))

        # Clock — big and clear
        self.clock_var = tk.StringVar()
        tk.Label(self.sidebar, textvariable=self.clock_var,
                 font=("Segoe UI", 13, "bold"),
                 bg=COLORS["sidebar_bg"], fg="#FFFFFF").pack(pady=(4, 16))
        self._tick()

    def _make_nav(self, key, icon, label):
        """Create a large nav button for the sidebar."""
        frame = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"],
                         cursor="hand2")
        frame.pack(fill="x", padx=10, pady=4)

        indicator = tk.Frame(frame, bg=COLORS["sidebar_bg"], width=5)
        indicator.pack(side="left", fill="y")

        inner = tk.Frame(frame, bg=COLORS["sidebar_bg"])
        inner.pack(side="left", fill="both", expand=True,
                   padx=(12, 12), pady=14)

        icon_lbl = tk.Label(inner, text=icon,
                             font=("Segoe UI", 22),
                             bg=COLORS["sidebar_bg"], fg="#A8C4E0")
        icon_lbl.pack(side="left")

        text_lbl = tk.Label(inner, text=label,
                             font=("Segoe UI", 16, "bold"),
                             bg=COLORS["sidebar_bg"], fg="#A8C4E0")
        text_lbl.pack(side="left", padx=(14, 0))

        parts = (frame, indicator, inner, icon_lbl, text_lbl)

        def click(k=key):
            self._show(k)

        def enter(e):
            if self._active != key:
                for w in (frame, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_hover"])

        def leave(e):
            if self._active != key:
                for w in (frame, indicator, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_bg"])
                icon_lbl.config(fg="#A8C4E0")
                text_lbl.config(fg="#A8C4E0")

        for w in (frame, inner, icon_lbl, text_lbl):
            w.bind("<Button-1>", lambda e, k=key: click(k))
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

        return parts

    # ── Main content ──────────────────────────────────────
    def _build_main(self):
        self.main = tk.Frame(self, bg=COLORS["content_bg"])
        self.main.pack(side="right", fill="both", expand=True)

        # Header bar
        hdr = tk.Frame(self.main, bg=COLORS["header_bg"], height=65)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=COLORS["divider"], height=1).place(
            relx=0, rely=1.0, relwidth=1, anchor="sw")

        self.page_title = tk.Label(
            hdr, text="",
            font=("Segoe UI", 20, "bold"),
            bg=COLORS["header_bg"], fg="#FFFFFF")
        self.page_title.pack(side="left", padx=24)

        self.date_lbl = tk.Label(
            hdr, text="",
            font=("Segoe UI", 13),
            bg=COLORS["header_bg"], fg="#FFFFFF")
        self.date_lbl.pack(side="right", padx=24)

        # Content frames
        self.content = tk.Frame(self.main, bg=COLORS["content_bg"])
        self.content.pack(fill="both", expand=True)

        self.frames = {}
        for key, Cls in [
            ("billing", BillingFrame),
            ("payment", PaymentFrame),
            ("history", HistoryFrame),
        ]:
            f = Cls(self.content)
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.frames[key] = f

    # ── Navigation ────────────────────────────────────────
    def _show(self, key):
        self._active = key
        self.frames[key].tkraise()

        titles = {
            "billing": "🧾  Create New Bill",
            "payment": "💰  Record Payment",
            "history": "📋  Customer History",
        }
        self.page_title.config(text=titles.get(key, ""))

        # Highlight active nav
        for k, parts in self._nav.items():
            frame, indicator, inner, icon_lbl, text_lbl = parts
            if k == key:
                for w in (frame, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_active_bg"])
                indicator.config(bg=COLORS["primary"])
                icon_lbl.config(fg="#FFFFFF")
                text_lbl.config(fg="#FFFFFF")
            else:
                for w in (frame, indicator, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_bg"])
                icon_lbl.config(fg="#A8C4E0")
                text_lbl.config(fg="#A8C4E0")

        if hasattr(self.frames[key], "refresh"):
            self.frames[key].refresh()

    # ── Clock ─────────────────────────────────────────────
    def _tick(self):
        now = datetime.now()
        self.clock_var.set(now.strftime("%d %b %Y\n%I:%M %p"))
        if hasattr(self, "date_lbl"):
            self.date_lbl.config(text=now.strftime("%A, %d %B %Y"))
        self.after(1000, self._tick)

    # ── Sync ─────────────────────────────────────────────
    def _start_sync(self):
        # supabase_sync + cloud_pull are started in main.py before the UI
        # launches. This method just wires up the status-bar polling so the
        # ☁ indicator reflects the real (Supabase) sync state.
        try:
            from supabase_sync import (
                get_sync_status,
                STATUS_SYNCED, STATUS_PENDING,
                STATUS_OFFLINE, STATUS_FAILED,
                is_online,
            )
            self.status_var.set("☁  Online" if is_online() else "📴  Offline")

            def _poll():
                status = get_sync_status()
                icons = {
                    STATUS_SYNCED:  "☁  Synced",
                    STATUS_PENDING: "🔄  Syncing...",
                    STATUS_OFFLINE: "📴  Offline",
                    STATUS_FAILED:  "⚠  Sync Error",
                }
                self.status_var.set(icons.get(status, "📴  Offline"))
                self.after(5000, _poll)
            _poll()
        except Exception as e:
            log.warning("Sync start failed: %s", e)
            self.status_var.set("📴  Offline")

    # ── Close ─────────────────────────────────────────────
    def _on_closing(self):
        log.info("ShopApp closing.")
        try:
            from supabase_sync import stop_auto_sync
            stop_auto_sync()
        except Exception:
            pass
        try:
            from backup_manager import create_backup
            create_backup(tag="shutdown")
        except Exception as e:
            log.error("Shutdown backup failed: %s", e)
        self.destroy()
