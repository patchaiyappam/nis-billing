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
AUTO_SYNC_INTERVAL  = 30        # seconds between full Supabase push-all (safety net)
AUTO_BACKUP_ENABLED = True      # daily backup on startup

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
    # Sidebar — dark navy (logo color)
    "sidebar_bg":        "#1B3A6B",
    "sidebar_hover":     "#234E8C",
    "sidebar_active_bg": "#0F2347",

    # Content area — clean white
    "content_bg":        "#F4F6F9",
    "card_bg":           "#FFFFFF",
    "card_border":       "#D0D8E8",
    "card_shadow":       "#F4F6F9",

    # Header
    "header_bg":         "#1B3A6B",
    "header_border":     "#0F2347",

    # Primary — NIS logo blue
    "primary":           "#1B3A6B",
    "primary_hover":     "#0F2347",
    "primary_light":     "#E8EEF8",

    # Semantic
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

    # Text — dark for white background
    "text_dark":         "#1A1A2E",
    "text_medium":       "#2C3E50",
    "text_muted":        "#5D6D7E",
    "text_light":        "#FFFFFF",
    "text_placeholder":  "#95A5A6",

    # Table
    "table_header_bg":   "#1B3A6B",
    "table_header_fg":   "#FFFFFF",
    "table_row_alt":     "#F0F4FB",
    "table_selected":    "#1B3A6B",
    "table_selected_fg": "#FFFFFF",

    # Input — white with dark text
    "input_bg":          "#FFFFFF",
    "input_border":      "#AAB8D0",
    "input_focus":       "#1B3A6B",

    # Divider
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
# 1. Go to https://supabase.com → create a project
# 2. Project Settings → API → copy URL and anon key below
# Leave both empty to run fully offline (no errors)
SUPABASE_URL = "https://agffhjgutddcxvrluysv.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFnZmZoamd1dGRkY3h2cmx1eXN2Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg3NTgwODMsImV4cCI6MjA5NDMzNDA4M30.J9cr-523rowrPLO1ECvLAbdPBGpsnEPg44Rt8kHMbOo"

# ── WhatsApp Sending Method ───────────────────────────────
# "meta"   → Meta WhatsApp Business Cloud API (100% automatic, free)
# "twilio" → Twilio WhatsApp API (100% automatic, paid)
# "wame"   → wa.me deep link (needs one manual click)
WA_METHOD = "wame"   # ← change to "meta" after setup below

# ── Meta WhatsApp Business Cloud API (RECOMMENDED - FREE) ─
# Setup: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
# Step 1: Go to developers.facebook.com → Create App → WhatsApp
# Step 2: Get your Token and Phone Number ID from the dashboard
WA_META_TOKEN    = ""   # ← paste your Meta API token here
WA_META_PHONE_ID = ""   # ← paste your Phone Number ID here

# ── Twilio WhatsApp API (BACKUP) ─────────────────────────
# Setup: https://www.twilio.com/whatsapp
WA_TWILIO_SID   = ""   # ← your Twilio Account SID
WA_TWILIO_TOKEN = ""   # ← your Twilio Auth Token
WA_TWILIO_FROM  = ""   # ← e.g. "whatsapp:+14155238886"

# ── User Mode ─────────────────────────────────────────────
# "shop"  → Simple mode for shop PC (dad) — only Bill + Payment
# "admin" → Full access mode (your laptop) — everything
# Set automatically by launcher bat, or change manually here
import os as _os
USER_MODE = _os.environ.get("NIS_MODE", "shop")

# ── Mode Switch PIN ───────────────────────────────────────
# PIN to unlock Full Mode from Simple Mode
# Change this to any 4-digit number you want
MODE_PIN = "1216"

# Default startup mode: "simple" or "full"
# "simple" = dad's mode on startup (safe default)
# "full"   = your mode on startup (set on your laptop)
DEFAULT_MODE = "simple"
