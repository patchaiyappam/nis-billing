"""
Configuration - NEW INDIAN STEEL Billing System
Dark & Large Font theme — easy for elderly users
"""
import os

# ── Paths ──────────────────────────────────────────────────
BASE_DIR     = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL")
DB_PATH      = os.path.join(BASE_DIR, "billing.db")
INVOICES_DIR = os.path.join(BASE_DIR, "invoices")
EXPORTS_DIR  = os.path.join(BASE_DIR, "exports")
BACKUPS_DIR  = os.path.join(BASE_DIR, "backups")
LOGS_DIR     = os.path.join(BASE_DIR, "logs")
for _d in (INVOICES_DIR, EXPORTS_DIR, BACKUPS_DIR, LOGS_DIR):
    os.makedirs(_d, exist_ok=True)

# ── Auto Sync / Backup Settings ──────────────────────────
AUTO_SYNC_INTERVAL  = 30
AUTO_BACKUP_ENABLED = True

# ── Shop Details ─────────────────────────────────────────
SHOP_NAME    = "NEW INDIAN STEEL"
SHOP_ADDRESS = "Aranthangi Road, Thiruchitrambalam - 614628"
SHOP_PHONE   = "+91 6380903276 / +91 9047312666"
SHOP_GSTIN   = ""
LOGO_PATH    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logo.jpg")

# ── Firebase ──────────────────────────────────────────────
FIREBASE_CRED_PATH = os.path.join(BASE_DIR, "firebase_credentials.json")
FIREBASE_ENABLED   = os.path.exists(FIREBASE_CRED_PATH)

# ── WHITE THEME — NIS Logo Blue, Large Fonts ─────────────
COLORS = {
    "sidebar_bg":        "#1B3A6B",
    "sidebar_hover":     "#234E8C",
    "sidebar_active_bg": "#0F2347",
    "content_bg":        "#F4F6F9",
    "card_bg":           "#FFFFFF",
    "card_border":       "#D0D8E8",
    "card_shadow":       "#F4F6F9",
    "header_bg":         "#1B3A6B",
    "header_border":     "#0F2347",
    "primary":           "#1B3A6B",
    "primary_hover":     "#0F2347",
    "primary_light":     "#E8EEF8",
    "success":           "#1E8449",
    "success_light":     "#EAFAF1",
    "success_border":    "#1E8449",
    "danger":            "#C0392B",
    "danger_light":      "#FDEDEC",
    "danger_border":     "#C0392B",
    "warning":           "#D68910",
    "warning_light":     "#FEF9E7",
    "warning_border":    "#D68910",
    "info":              "#1B3A6B",
    "info_light":        "#E8EEF8",
    "text_dark":         "#1A1A2E",
    "text_medium":       "#2C3E50",
    "text_muted":        "#5D6D7E",
    "text_light":        "#FFFFFF",
    "text_placeholder":  "#95A5A6",
    "table_header_bg":   "#1B3A6B",
    "table_header_fg":   "#FFFFFF",
    "table_row_alt":     "#F0F4FB",
    "table_selected":    "#1B3A6B",
    "table_selected_fg": "#FFFFFF",
    "input_bg":          "#FFFFFF",
    "input_border":      "#AAB8D0",
    "input_focus":       "#1B3A6B",
    "divider":           "#D0D8E8",
}

# ── Large fonts ───────────────────────────────────────────
FONTS = {
    "heading":      ("Segoe UI", 20, "bold"),
    "subheading":   ("Segoe UI", 15, "bold"),
    "body":         ("Segoe UI", 14),
    "body_bold":    ("Segoe UI", 14, "bold"),
    "small":        ("Segoe UI", 12),
    "small_bold":   ("Segoe UI", 12, "bold"),
    "button":       ("Segoe UI", 14, "bold"),
    "input":        ("Segoe UI", 14),
    "sidebar_item": ("Segoe UI", 14),
    "logo":         ("Segoe UI", 16, "bold"),
    "logo_sub":     ("Segoe UI", 11),
    "metric":       ("Segoe UI", 30, "bold"),
    "metric_label": ("Segoe UI", 12),
}

# ── Supabase ──────────────────────────────────────────────
SUPABASE_URL = "https://agffhjgutddcxvrluysv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFnZmZoamd1dGRkY3h2cmx1eXN2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg3NTgwODMsImV4cCI6MjA5NDMzNDA4M30.J9cr-523rowrPLO1ECvLAbdPBGpsnEPg44Rt8kHMbOo"

# ── WhatsApp Sending Method ───────────────────────────────
# "meta" / "twilio" = automatic; "wame" = wa.me deep link (manual click)
WA_METHOD = "wame"

# ── Auto-send WhatsApp after each bill? ───────────────────
# False (default): saving a bill NEVER opens WhatsApp, so billing is never
# interrupted/minimised (best for the shop PC). True only auto-sends with a
# silent method (Meta API); "wame" never auto-fires (it steals focus).
WA_AUTO_SEND = False

# ── Meta WhatsApp Business Cloud API ─────────────────────
WA_META_TOKEN    = ""
WA_META_PHONE_ID = ""

# ── Twilio WhatsApp API (BACKUP) ─────────────────────────
WA_TWILIO_SID   = ""
WA_TWILIO_TOKEN = ""
WA_TWILIO_FROM  = ""

# ── User Mode ─────────────────────────────────────────────
import os as _os
USER_MODE = _os.environ.get("NIS_MODE", "shop")

# ── Mode Switch PIN ───────────────────────────────────────
MODE_PIN = "1216"

# Default startup mode
DEFAULT_MODE = "simple"

# ── Device ID (collision-free cloud IDs) ──────────────────
# Permanent per-install tag so two PCs / the phone can never pick the same
# cloud bill id. A = admin/laptop, S = shop, plus a short random part.
import uuid as _uuid
_DEVICE_ID_FILE = os.path.join(BASE_DIR, "device_id.txt")


def _load_device_id():
    try:
        if os.path.exists(_DEVICE_ID_FILE):
            v = open(_DEVICE_ID_FILE, "r", encoding="utf-8").read().strip()
            if v:
                return v
    except Exception:
        pass
    tag = ("A" if str(USER_MODE).lower() == "admin" else "S") + _uuid.uuid4().hex[:6]
    try:
        with open(_DEVICE_ID_FILE, "w", encoding="utf-8") as f:
            f.write(tag)
    except Exception:
        pass
    return tag


DEVICE_ID = _load_device_id()
