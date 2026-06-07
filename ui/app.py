"""
app.py — Main Application Window
==================================
NEW INDIAN STEEL Billing System — Full Mode only.
"""

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import os, sys, subprocess, threading

from config import (COLORS, FONTS, SHOP_NAME, DB_PATH, BACKUPS_DIR)
from logger import get_logger
from backup_manager import (create_backup, list_backups,
                             restore_backup, safe_restore_backup,
                             is_restore_in_progress)
from supabase_sync import (
    sync_all as background_sync_all,
    is_online, start_auto_sync, stop_auto_sync,
    get_sync_status, STATUS_SYNCED, STATUS_PENDING,
    STATUS_OFFLINE, STATUS_FAILED,
)
from excel_export import (export_products, export_customers,
                           export_pending, OPENPYXL_AVAILABLE)
from ui.billing_frame  import BillingFrame
from ui.payment_frame  import PaymentFrame
from ui.history_frame  import HistoryFrame
from ui.product_frame  import ProductFrame
from ui.dashboard_frame import DashboardFrame
from ui.pending_frame  import PendingFrame

log = get_logger(__name__)

_NAV = [
    ("dashboard", "📊", "Dashboard"),
    ("billing",   "🧾", "New Bill"),
    ("payment",   "💰", "Add Payment"),
    ("history",   "📋", "History"),
    ("pending",   "⏳", "Pending List"),
    ("products",  "📦", "Products"),
]
_TITLES = {
    "dashboard": "📊  Dashboard",
    "billing":   "🧾  Create New Bill",
    "payment":   "💰  Record Payment",
    "history":   "📋  Customer History",
    "pending":   "⏳  Customer Pending List",
    "products":  "📦  Manage Products",
}


class BillingApp(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title(f"{SHOP_NAME} — Billing System")
        self.geometry("1280x800")
        self.minsize(1000, 650)
        self.configure(bg=COLORS["content_bg"])
        try:
            self.state("zoomed")
        except Exception:
            pass

        self._configure_styles()
        self._build_main_area()
        self._build_sidebar()
        self._show_frame("dashboard")
        self._try_sync()
        self._start_sync_status_poll()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self.report_callback_exception = self._handle_tk_exception
        log.info("BillingApp started.")

    # ══════════════════════════════════════════════════════
    # STYLES
    # ══════════════════════════════════════════════════════

    def _configure_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Treeview",
            font=FONTS["body"], rowheight=38,
            background=COLORS["card_bg"],
            fieldbackground=COLORS["card_bg"],
            foreground=COLORS["text_dark"],
            borderwidth=0, relief="flat")
        style.configure("Treeview.Heading",
            font=FONTS["small_bold"],
            background=COLORS["table_header_bg"],
            foreground=COLORS["table_header_fg"],
            relief="flat", borderwidth=0)
        style.map("Treeview",
            background=[("selected", COLORS["primary"])],
            foreground=[("selected", "#FFFFFF")])
        style.configure("Vertical.TScrollbar",
            background=COLORS["divider"],
            troughcolor=COLORS["content_bg"],
            borderwidth=0, arrowsize=14)

    # ══════════════════════════════════════════════════════
    # MAIN CONTENT AREA  (built once — frames persist)
    # ══════════════════════════════════════════════════════

    def _build_main_area(self):
        self.main = tk.Frame(self, bg=COLORS["content_bg"])
        self.main.pack(side="right", fill="both", expand=True)

        # Header bar
        hdr = tk.Frame(self.main, bg=COLORS["header_bg"], height=60)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Frame(hdr, bg=COLORS["divider"], height=1).place(
            relx=0, rely=1.0, relwidth=1, anchor="sw")

        self.page_title = tk.Label(
            hdr, text="",
            font=FONTS["heading"],
            bg=COLORS["header_bg"], fg="#FFFFFF")
        self.page_title.pack(side="left", padx=24)

        self.date_label = tk.Label(
            hdr, text="",
            font=FONTS["body"],
            bg=COLORS["header_bg"], fg="#FFFFFF")
        self.date_label.pack(side="right", padx=24)

        # Content frames — all built once
        self.content = tk.Frame(self.main, bg=COLORS["content_bg"])
        self.content.pack(fill="both", expand=True)

        self.frames = {}
        for key, Cls in [
            ("dashboard", DashboardFrame),
            ("billing",   BillingFrame),
            ("payment",   PaymentFrame),
            ("history",   HistoryFrame),
            ("pending",   PendingFrame),
            ("products",  ProductFrame),
        ]:
            f = Cls(self.content)
            f.place(relx=0, rely=0, relwidth=1, relheight=1)
            self.frames[key] = f

    # ══════════════════════════════════════════════════════
    # SIDEBAR
    # ══════════════════════════════════════════════════════

    def _build_sidebar(self):
        self.sidebar = tk.Frame(self, bg=COLORS["sidebar_bg"], width=230)
        self.sidebar.pack(side="left", fill="y", before=self.main)
        self.sidebar.pack_propagate(False)
        self._active = None
        self.nav_buttons = {}
        self._populate_sidebar()

    def _populate_sidebar(self):
        """Fill sidebar contents."""
        for w in self.sidebar.winfo_children():
            w.destroy()
        self.nav_buttons = {}

        # ── Logo ──────────────────────────────────────────
        logo = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"])
        logo.pack(fill="x")
        tk.Frame(logo, bg=COLORS["primary"], height=4).pack(fill="x")
        inner = tk.Frame(logo, bg=COLORS["sidebar_bg"])
        inner.pack(fill="x", padx=18, pady=14)
        tk.Label(inner, text="⚙",
                 font=("Segoe UI", 26),
                 bg=COLORS["sidebar_bg"], fg="#FFFFFF").pack(anchor="w")
        tk.Label(inner, text=SHOP_NAME,
                 font=FONTS["logo"],
                 bg=COLORS["sidebar_bg"], fg="#FFFFFF").pack(anchor="w", pady=(4, 0))
        tk.Label(inner, text="Billing & Credit System",
                 font=FONTS["logo_sub"],
                 bg=COLORS["sidebar_bg"], fg="#A8C4E0").pack(anchor="w")

        tk.Frame(self.sidebar, bg=COLORS["divider"],
                 height=1).pack(fill="x", padx=14, pady=(0, 6))

        # ── Nav items ─────────────────────────────────────
        for key, icon, label in _NAV:
            self.nav_buttons[key] = self._make_nav(key, icon, label)

        # ── Spacer ────────────────────────────────────────
        tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"]).pack(
            fill="both", expand=True)
        tk.Frame(self.sidebar, bg=COLORS["divider"],
                 height=1).pack(fill="x", padx=14, pady=4)

        # ── Tools ────────────────────────────────────────
        tools = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"])
        tools.pack(fill="x", padx=10, pady=(0, 2))

        def _tbtn(txt, bg_key, cmd):
            tk.Button(
                tools, text=txt, font=FONTS["small"],
                bg=COLORS[bg_key], fg="#FFFFFF",
                relief="flat", pady=7, cursor="hand2",
                command=cmd,
                activeforeground="#FFFFFF",
                activebackground=COLORS[bg_key]
            ).pack(fill="x", pady=2)

        _tbtn("☁  Sync to Cloud",  "info",    self._try_sync)
        _tbtn("💾  Backup Data",    "primary",  self._backup_db)
        _tbtn("🔄  Restore Backup", "primary",  self._restore_db)

        exp = tk.Frame(tools, bg=COLORS["sidebar_bg"])
        exp.pack(fill="x", pady=2)
        for lbl, kind in [("Products","products"),
                           ("Customers","customers"),
                           ("Pending","pending")]:
            tk.Button(
                exp, text=lbl, font=FONTS["small"],
                bg="#2A2A3E", fg="#FFFFFF",
                relief="flat", pady=6, cursor="hand2",
                command=lambda k=kind: self._export(k)
            ).pack(side="left", expand=True, fill="x", padx=1)

        tk.Frame(self.sidebar, bg=COLORS["divider"],
                 height=1).pack(fill="x", padx=14, pady=4)

        # ── Update App button ─────────────────────────────
        tk.Button(
            self.sidebar,
            text="🔄  Update App",
            font=FONTS["small"],
            bg="#1E3A5F", fg="#FFFFFF",
            relief="flat", pady=7, cursor="hand2",
            command=self._update_app,
            activeforeground="#FFFFFF",
            activebackground="#1E3A5F"
        ).pack(fill="x", padx=10, pady=(0, 4))

        # ── Status + Clock ────────────────────────────────
        self.status_var = tk.StringVar(value="")
        tk.Label(
            self.sidebar, textvariable=self.status_var,
            font=FONTS["small"],
            bg=COLORS["sidebar_bg"], fg="#A8C4E0"
        ).pack(pady=(4, 0))

        self.clock_var = tk.StringVar()
        tk.Label(
            self.sidebar, textvariable=self.clock_var,
            font=FONTS["small"],
            bg=COLORS["sidebar_bg"], fg="#FFFFFF"
        ).pack(pady=(2, 10))

        self._tick()

    def _make_nav(self, key, icon, label):
        frame = tk.Frame(self.sidebar, bg=COLORS["sidebar_bg"],
                         cursor="hand2")
        frame.pack(fill="x", padx=8, pady=2)

        indicator = tk.Frame(frame, bg=COLORS["sidebar_bg"], width=4)
        indicator.pack(side="left", fill="y")

        inner = tk.Frame(frame, bg=COLORS["sidebar_bg"])
        inner.pack(side="left", fill="both", expand=True,
                   padx=(10, 10), pady=8)

        icon_font = ("Segoe UI", 16)
        text_font = FONTS["sidebar_item"]

        icon_lbl = tk.Label(inner, text=icon, font=icon_font,
                            bg=COLORS["sidebar_bg"], fg="#A8C4E0")
        icon_lbl.pack(side="left")

        text_lbl = tk.Label(inner, text=label, font=text_font,
                            bg=COLORS["sidebar_bg"], fg="#A8C4E0")
        text_lbl.pack(side="left", padx=(12, 0))

        parts = (frame, indicator, inner, icon_lbl, text_lbl)

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
            w.bind("<Button-1>", lambda e, k=key: self._show_frame(k))
            w.bind("<Enter>", enter)
            w.bind("<Leave>", leave)

        return parts

    # ══════════════════════════════════════════════════════
    # FRAME NAVIGATION
    # ══════════════════════════════════════════════════════

    def _show_frame(self, key: str):
        self._active = key
        self.frames[key].tkraise()
        self.page_title.config(text=_TITLES.get(key, key))

        for k, parts in self.nav_buttons.items():
            frame, indicator, inner, icon_lbl, text_lbl = parts
            if k == key:
                for w in (frame, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_active_bg"])
                indicator.config(bg=COLORS["primary"])
                icon_lbl.config(fg="#FFFFFF")
                text_lbl.config(fg="#FFFFFF", font=FONTS["button"])
            else:
                for w in (frame, indicator, inner, icon_lbl, text_lbl):
                    w.config(bg=COLORS["sidebar_bg"])
                icon_lbl.config(fg="#A8C4E0")
                text_lbl.config(fg="#A8C4E0", font=FONTS["sidebar_item"])

        if hasattr(self.frames[key], "refresh"):
            self.frames[key].refresh()

    # ══════════════════════════════════════════════════════
    # CLOCK
    # ══════════════════════════════════════════════════════

    def _tick(self):
        now = datetime.now()
        try:
            self.clock_var.set(now.strftime("%d %b %Y  %I:%M %p"))
        except Exception:
            pass
        try:
            self.date_label.config(text=now.strftime("%A, %d %B %Y"))
        except Exception:
            pass
        self.after(1000, self._tick)

    # ══════════════════════════════════════════════════════
    # SYNC
    # ══════════════════════════════════════════════════════

    def _try_sync(self):
        if is_online():
            self.status_var.set("☁  Syncing...")
            background_sync_all()
            start_auto_sync()
        else:
            self.status_var.set("📴  Offline Mode")

    def _start_sync_status_poll(self):
        status = get_sync_status()
        icons = {
            STATUS_SYNCED:  "☁  Synced",
            STATUS_PENDING: "🔄  Syncing...",
            STATUS_OFFLINE: "📴  Offline Mode",
            STATUS_FAILED:  "⚠  Sync Failed",
        }
        try:
            self.status_var.set(icons.get(status, "📴  Offline Mode"))
        except Exception:
            pass
        self.after(5000, self._start_sync_status_poll)

    # ══════════════════════════════════════════════════════
    # TOOLS (full mode only)
    # ══════════════════════════════════════════════════════

    def _backup_db(self):
        dest = create_backup(tag="manual")
        if dest:
            messagebox.showinfo(
                "Backup",
                f"Backup saved!\n\n{os.path.basename(dest)}")
        else:
            messagebox.showerror("Backup Error", "Could not create backup.")

    def _restore_db(self):
        if is_restore_in_progress():
            messagebox.showwarning("Restore",
                "A restore is already in progress.")
            return
        backups = list_backups()
        if not backups:
            messagebox.showinfo("Restore", "No backups found.")
            return

        popup = tk.Toplevel(self)
        popup.title("Restore Backup")
        popup.geometry("620x480")
        popup.configure(bg=COLORS["content_bg"])
        popup.transient(self)
        popup.grab_set()

        tk.Label(popup, text="🔄  Restore Backup",
                 font=FONTS["heading"],
                 bg=COLORS["content_bg"],
                 fg=COLORS["text_dark"]).pack(pady=(16, 4))
        tk.Label(popup,
                 text="Select a backup to restore.\n"
                      "A safety backup is created first.",
                 font=FONTS["small"],
                 bg=COLORS["content_bg"],
                 fg=COLORS["text_muted"]).pack(pady=(0, 12))

        cols = ("filename", "size", "date")
        tree = ttk.Treeview(popup, columns=cols,
                             show="headings", height=12)
        tree.heading("filename", text="Backup File")
        tree.heading("size",     text="Size")
        tree.heading("date",     text="Date")
        tree.column("filename", width=280)
        tree.column("size",     width=80,  anchor="e")
        tree.column("date",     width=180, anchor="center")

        for b in backups:
            tree.insert("", "end", values=(
                b["filename"],
                f"{b['size_kb']:.0f} KB",
                b["date_str"]))

        sb = ttk.Scrollbar(popup, orient="vertical",
                            command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True,
                  padx=(12, 0), pady=(0, 12))
        sb.pack(side="right", fill="y",
                pady=(0, 12), padx=(0, 12))

        btn = tk.Frame(popup, bg=COLORS["content_bg"])
        btn.pack(fill="x", padx=12, pady=(0, 12))

        def do_restore():
            sel = tree.selection()
            if not sel:
                messagebox.showwarning("Select",
                    "Select a backup first.", parent=popup)
                return
            fname = tree.item(sel[0])["values"][0]
            fpath = os.path.join(BACKUPS_DIR, fname)
            if not messagebox.askyesno(
                    "Confirm Restore",
                    f"Restore from:\n{fname}\n\n"
                    "⚠️ This will REPLACE your current data.\n"
                    "The app will restart automatically.\n\nContinue?",
                    parent=popup):
                return
            popup.destroy()

            def _run():
                def _restart():
                    try:
                        subprocess.Popen([sys.executable] + sys.argv)
                        self.after(500, self.destroy)
                    except Exception as e:
                        log.error("Auto-restart failed: %s", e)
                        self.after(0, lambda: messagebox.showinfo(
                            "Restart Required",
                            "Please close and reopen the app."))

                ok, msg = safe_restore_backup(
                    fpath,
                    stop_sync_fn=stop_auto_sync,
                    restart_fn=lambda: self.after(0, _restart))
                if not ok:
                    self.after(0, lambda: messagebox.showerror(
                        "Restore Failed", msg))

            threading.Thread(target=_run, daemon=True,
                              name="safe-restore").start()

        tk.Button(btn, text="✅  Restore Selected",
                  font=FONTS["button"],
                  bg=COLORS["success"], fg="white",
                  relief="flat", padx=16, pady=8,
                  cursor="hand2",
                  command=do_restore).pack(side="right")
        tk.Button(btn, text="Cancel",
                  font=FONTS["button"],
                  bg=COLORS["divider"],
                  fg=COLORS["text_dark"],
                  relief="flat", padx=16, pady=8,
                  cursor="hand2",
                  command=popup.destroy).pack(side="right", padx=(0, 8))

    def _export(self, kind):
        if not OPENPYXL_AVAILABLE:
            messagebox.showwarning("Missing", "Run: pip install openpyxl")
            return
        try:
            funcs = {"products": export_products,
                     "customers": export_customers,
                     "pending":   export_pending}
            fp = funcs[kind]()
            if fp:
                messagebox.showinfo("Exported", f"Saved:\n{fp}")
                if sys.platform == "win32":
                    os.startfile(fp)
                elif sys.platform == "darwin":
                    subprocess.run(["open", fp])
                else:
                    subprocess.run(["xdg-open", fp])
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    # ══════════════════════════════════════════════════════
    # UPDATE APP (git pull from GitHub)
    # ══════════════════════════════════════════════════════

    def _update_app(self):
        """Pull latest code from GitHub and prompt to restart."""
        import shutil

        # Check git is available
        if not shutil.which("git"):
            messagebox.showerror(
                "Git Not Found",
                "Git is not installed on this PC.\n\n"
                "Download from: https://git-scm.com/download/win\n"
                "Then run SETUP_GITHUB.bat in the app folder."
            )
            return

        # Check this folder is a git repo
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        git_dir = os.path.join(app_dir, ".git")
        if not os.path.isdir(git_dir):
            messagebox.showerror(
                "Not Set Up",
                "GitHub sync is not configured yet.\n\n"
                "On your DEV PC: run SETUP_GITHUB.bat\n"
                "On this laptop: run GET_UPDATE.bat"
            )
            return

        if not messagebox.askyesno(
            "Update App",
            "This will download the latest code from GitHub\n"
            "and restart the app.\n\n"
            "Your billing data is safe (it is never changed by updates).\n\n"
            "Proceed?",
            icon="question"
        ):
            return

        # Run git pull in background thread
        self.status_var.set("\U0001f504  Updating...")
        self.update_idletasks()

        def _do_pull():
            try:
                result = subprocess.run(
                    ["git", "fetch", "origin", "main"],
                    cwd=app_dir, capture_output=True, text=True, timeout=30
                )
                if result.returncode != 0:
                    raise RuntimeError(result.stderr.strip() or "fetch failed")
                result2 = subprocess.run(
                    ["git", "reset", "--hard", "origin/main"],
                    cwd=app_dir, capture_output=True, text=True, timeout=30
                )
                if result2.returncode != 0:
                    raise RuntimeError(result2.stderr.strip() or "reset failed")
                log_result = subprocess.run(
                    ["git", "log", "--oneline", "-3"],
                    cwd=app_dir, capture_output=True, text=True
                )
                log_lines = log_result.stdout.strip() or "(no log)"
                self.after(0, lambda: self._update_done(True, log_lines))
            except Exception as e:
                self.after(0, lambda: self._update_done(False, str(e)))

        threading.Thread(target=_do_pull, daemon=True).start()

    def _update_done(self, success: bool, detail: str):
        if not success:
            self.status_var.set("\u26a0  Update failed")
            messagebox.showerror(
                "Update Failed",
                f"Could not download update:\n\n{detail}\n\n"
                "Check your internet connection and try again."
            )
            return
        self.status_var.set("\u2601  Updated!")
        if messagebox.askyesno(
            "Update Complete",
            f"App updated!\n\nLatest changes:\n{detail}\n\n"
            "Restart now to apply?",
            icon="info"
        ):
            python = sys.executable
            script = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "main.py"
            )
            self.destroy()
            os.execv(python, [python, script])

    # ======================================================
    # CLOSE
    # ======================================================

    def _handle_tk_exception(self, exc_type, exc_value, exc_tb):
        """Catch any unhandled exception in a Tkinter callback."""
        import traceback
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log.error("Unhandled UI exception:\n%s", msg)
        try:
            messagebox.showerror(
                "Unexpected Error",
                f"Something went wrong:\n\n{exc_value}\n\n"
                "Your data has been saved.",
                parent=self
            )
        except Exception:
            pass

    def _on_closing(self):
        log.info("Application closing.")
        stop_auto_sync()
        try:
            import sqlite3
            from config import DB_PATH
            conn = sqlite3.connect(DB_PATH, timeout=5)
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.close()
            log.info("WAL checkpoint complete.")
        except Exception as e:
            log.warning("WAL checkpoint failed: %s", e)
        try:
            create_backup(tag="shutdown")
        except Exception as e:
            log.error("Shutdown backup failed: %s", e)
        self.destroy()
