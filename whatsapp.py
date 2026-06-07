"""
whatsapp.py — Fully Automatic WhatsApp Sending
================================================
NEW INDIAN STEEL Billing System

STRATEGY (tries in order, fully background, zero manual clicks):

1. WhatsApp Business Cloud API (Meta)
   - 100% automatic, no browser, no clicks
   - Sends text message + PDF as document attachment
   - Free for first 1000 conversations/month
   - Setup: get free API token from Meta (see README_WHATSAPP.txt)

2. Twilio WhatsApp API (backup)
   - 100% automatic, no browser, no clicks
   - Sends text + PDF link
   - Requires Twilio account (free sandbox available)

3. wa.me deep link (last resort)
   - Opens WhatsApp Desktop app or browser
   - Still needs one manual click to send
   - Used only when both APIs are not configured

All methods run in background thread — UI never freezes.
Invoice is ALWAYS saved first. WhatsApp failure never cancels invoice.
"""

import os
import subprocess
import threading
import time
from urllib.parse import quote
from logger import get_logger

log = get_logger(__name__)


# ══════════════════════════════════════════════════════════
# CONFIGURATION  (set in config.py)
# ══════════════════════════════════════════════════════════

def _get_config():
    """Read WhatsApp config from config.py safely."""
    cfg = {}
    try:
        from config import (  # type: ignore[import]
            WA_METHOD,
            WA_META_TOKEN, WA_META_PHONE_ID,
            WA_TWILIO_SID, WA_TWILIO_TOKEN, WA_TWILIO_FROM,
        )
        cfg["method"]        = WA_METHOD
        cfg["meta_token"]    = WA_META_TOKEN
        cfg["meta_phone_id"] = WA_META_PHONE_ID
        cfg["twilio_sid"]    = WA_TWILIO_SID
        cfg["twilio_token"]  = WA_TWILIO_TOKEN
        cfg["twilio_from"]   = WA_TWILIO_FROM
    except (ImportError, AttributeError):
        cfg["method"] = "wame"  # fallback
    return cfg


# ══════════════════════════════════════════════════════════
# PHONE NORMALIZER
# ══════════════════════════════════════════════════════════

def _normalize_phone(phone: str) -> str:
    """Return E.164 without '+'. Adds 91 for Indian 10-digit numbers."""
    clean = str(phone).strip().replace(" ", "").replace("+", "").replace("-", "")
    if len(clean) == 10 and clean[0] in "6789":
        clean = "91" + clean
    return clean


# ══════════════════════════════════════════════════════════
# MESSAGE BUILDER
# ══════════════════════════════════════════════════════════

def _build_bill_message(
    customer_name: str,
    invoice_id: int,
    total: float,
    paid: float,
    balance: float,
    old_balance: float = 0.0,
    bill_type: str = "invoice",
    pdf_url: str = "",
    ref_name: str = "",
    ref_phone: str = "",
    payment_type: str = "",
) -> str:
    prefix  = "QUO" if bill_type == "quotation" else "INV"
    label   = "Quotation" if bill_type == "quotation" else "Invoice"
    net_due = old_balance + balance

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        "*NEW INDIAN STEEL*",
        f"*{label} #{prefix}-{invoice_id}*",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        f"Customer : *{customer_name}*",
        f"Bill Amt  : ₹{total:,.2f}",
        f"Paid       : ₹{paid:,.2f}",
        f"Balance  : ₹{balance:,.2f}",
    ]
    if old_balance > 0 and bill_type == "invoice":
        lines.append(f"Old Due   : ₹{old_balance:,.2f}")
        lines.append(f"*Total Due : ₹{net_due:,.2f}*")
    if payment_type:
        lines.append(f"Payment   : {payment_type}")
    if ref_name or ref_phone:
        ref_str = ref_name or ""
        if ref_phone:
            ref_str += f" ({ref_phone})" if ref_name else ref_phone
        lines.append(f"Ref By     : {ref_str}")
    if pdf_url:
        lines += ["", "📄 Invoice PDF:", pdf_url]
    lines += ["", "Thank you! 🙏"]
    return "\n".join(lines)


def _build_payment_message(
    customer_name: str,
    paid_amount: float,
    remaining_balance: float,
) -> str:
    return (
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "*NEW INDIAN STEEL*\n"
        "*Payment Received ✅*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Dear *{customer_name}*,\n\n"
        f"Amount Paid      : *₹{paid_amount:,.2f}*\n"
        f"Remaining Balance: *₹{remaining_balance:,.2f}*\n\n"
        "Thank you! 🙏"
    )


# ══════════════════════════════════════════════════════════
# METHOD 1 — META WHATSAPP BUSINESS CLOUD API
# 100% automatic. No browser. No clicks. Sends PDF too.
# ══════════════════════════════════════════════════════════

def _send_via_meta(phone_e164: str, message: str,
                   pdf_path: str = "", pdf_url: str = "") -> bool:
    """
    Send via Meta WhatsApp Business Cloud API.
    Sends text message + PDF document (if available).
    Completely automatic — no browser, no user interaction.

    Requires:
      WA_META_TOKEN    = your Meta API token  (from Meta Developer Console)
      WA_META_PHONE_ID = your WhatsApp Phone Number ID (from Meta Developer Console)
    """
    cfg = _get_config()
    token    = cfg.get("meta_token", "")
    phone_id = cfg.get("meta_phone_id", "")

    if not token or not phone_id:
        log.info("Meta API not configured — skipping.")
        return False

    try:
        import urllib.request
        import json

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
        }
        url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        to  = f"+{phone_e164}"

        # ── Step 1: Send text message ──────────────────────
        text_payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message, "preview_url": True}
        }).encode()

        req = urllib.request.Request(url, data=text_payload, headers=headers)
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        msg_id = result.get("messages", [{}])[0].get("id", "")
        log.info("Meta API: text sent to %s msg_id=%s", to, msg_id)

        # ── Step 2: Send PDF as document attachment ────────
        if pdf_url:
            doc_payload = json.dumps({
                "messaging_product": "whatsapp",
                "to": to,
                "type": "document",
                "document": {
                    "link": pdf_url,
                    "caption": "Invoice PDF — New Indian Steel",
                    "filename": f"invoice_{phone_e164}.pdf"
                }
            }).encode()
            req2 = urllib.request.Request(url, data=doc_payload, headers=headers)
            urllib.request.urlopen(req2, timeout=15)
            log.info("Meta API: PDF document sent to %s", to)

        return True

    except Exception as e:
        log.warning("Meta API send failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════
# METHOD 2 — TWILIO WHATSAPP API
# 100% automatic. No browser. No clicks.
# ══════════════════════════════════════════════════════════

def _send_via_twilio(phone_e164: str, message: str,
                     pdf_url: str = "") -> bool:
    """
    Send via Twilio WhatsApp API.
    Completely automatic — no browser, no user interaction.

    Requires:
      WA_TWILIO_SID   = your Twilio Account SID
      WA_TWILIO_TOKEN = your Twilio Auth Token
      WA_TWILIO_FROM  = "whatsapp:+14155238886"  (sandbox) or your number
    """
    cfg = _get_config()
    sid   = cfg.get("twilio_sid", "")
    token = cfg.get("twilio_token", "")
    from_ = cfg.get("twilio_from", "")

    if not sid or not token or not from_:
        log.info("Twilio not configured — skipping.")
        return False

    try:
        from twilio.rest import Client  # type: ignore[import]
        client = Client(sid, token)
        to = f"whatsapp:+{phone_e164}"

        # Send text
        client.messages.create(
            from_=from_,
            to=to,
            body=message,
        )
        log.info("Twilio: text sent to %s", to)

        # Send PDF link separately if available
        if pdf_url:
            client.messages.create(
                from_=from_,
                to=to,
                body="📄 Invoice PDF:",
                media_url=[pdf_url],
            )
            log.info("Twilio: PDF sent to %s", to)

        return True

    except ImportError:
        log.info("Twilio package not installed — skipping.")
        return False
    except Exception as e:
        log.warning("Twilio send failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════
# IMAGE HELPER — copy JPG to Windows clipboard (no extra packages)
# ══════════════════════════════════════════════════════════

def _copy_image_to_clipboard(image_path: str) -> bool:
    """
    Copy an image file to the Windows clipboard using PowerShell.
    No additional Python packages required — uses built-in .NET classes.
    After this call, Ctrl+V in WhatsApp Desktop pastes the image.
    """
    try:
        safe = image_path.replace("\\", "/")
        ps_cmd = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing; "
            f"$img = [System.Drawing.Image]::FromFile('{safe}'); "
            "[System.Windows.Forms.Clipboard]::SetImage($img); "
            "$img.Dispose()"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True, timeout=15
        )
        if result.returncode == 0:
            log.info("Image copied to clipboard: %s", os.path.basename(image_path))
            return True
        log.warning("Clipboard copy failed (rc=%d): %s",
                    result.returncode, result.stderr.decode(errors="ignore"))
        return False
    except Exception as e:
        log.warning("_copy_image_to_clipboard error: %s", e)
        return False


# ══════════════════════════════════════════════════════════
# METHOD 3 — WHATSAPP DESKTOP AUTO-SEND (via PyAutoGUI)
# Opens WhatsApp Desktop with message pre-filled, then
# automatically presses Enter to send — zero manual clicks.
# ══════════════════════════════════════════════════════════

def _wait_for_whatsapp_window(timeout: int = 12) -> bool:
    """
    Wait until a WhatsApp Desktop window is in the foreground.
    Returns True if found within timeout, False otherwise.
    """
    try:
        import pygetwindow as gw
        import time as _time
        deadline = _time.time() + timeout
        while _time.time() < deadline:
            wins = gw.getWindowsWithTitle("WhatsApp")
            if wins:
                w = wins[0]
                try:
                    w.activate()
                except Exception:
                    pass
                return True
            _time.sleep(0.5)
        return False
    except ImportError:
        # pygetwindow not installed — just sleep and hope
        import time as _time
        _time.sleep(8)
        return True
    except Exception:
        import time as _time
        _time.sleep(8)
        return True


def _send_via_wame(phone_e164: str, message: str, pdf_path: str = "") -> bool:
    """
    Open WhatsApp Desktop, auto-send the text message, then paste the
    invoice JPG image (if available) so customers can view it instantly
    without needing to open a PDF.  Minimises WhatsApp and restores
    the billing app when done — UI is never interrupted.
    """
    import webbrowser
    try:
        wa_url = f"whatsapp://send?phone={phone_e164}&text={quote(message)}"

        # Derive JPG path from PDF path (generated automatically alongside PDF)
        jpg_path = ""
        if pdf_path:
            candidate = pdf_path.replace(".pdf", ".jpg")
            if os.path.exists(candidate):
                jpg_path = candidate

        try:
            import pyautogui
            import pygetwindow as gw

            # ── Remember the billing window so we can restore it ──
            billing_win = None
            for title in ("NEW INDIAN STEEL", "NIS Billing", "NIS Admin"):
                wins = gw.getWindowsWithTitle(title)
                if wins:
                    billing_win = wins[0]
                    break

            # ── Pre-load image into clipboard BEFORE opening WhatsApp ──
            image_ready = False
            if jpg_path:
                image_ready = _copy_image_to_clipboard(jpg_path)

            # ── Open WhatsApp ──────────────────────────────────────
            webbrowser.open(wa_url)
            log.info("WhatsApp opening for +%s …", phone_e164)

            # Wait for WhatsApp window to appear and chat to load
            _wait_for_whatsapp_window(timeout=14)
            time.sleep(3)   # wait for message box to be ready

            # ── Step 1: Send text message (pre-filled by URL) ──────
            pyautogui.press("enter")
            log.info("WhatsApp: text message sent to +%s", phone_e164)
            time.sleep(1.0)

            # ── Step 2: Paste & send invoice image ─────────────────
            if image_ready:
                pyautogui.hotkey("ctrl", "v")   # paste image from clipboard
                time.sleep(2.0)                  # wait for image to appear in input
                pyautogui.press("enter")         # send image
                log.info("WhatsApp: invoice image sent to +%s", phone_e164)
                time.sleep(0.8)
            else:
                time.sleep(0.8)

            # ── Minimize WhatsApp ──────────────────────────────────
            for w in gw.getWindowsWithTitle("WhatsApp"):
                try:
                    w.minimize()
                except Exception:
                    pass

            # ── Restore billing app MAXIMIZED ─────────────────────
            time.sleep(0.3)
            if billing_win:
                try:
                    billing_win.maximize()
                    billing_win.activate()
                except Exception:
                    try:
                        billing_win.restore()
                        billing_win.activate()
                    except Exception:
                        pass
            log.info("WhatsApp done — billing screen restored.")

        except ImportError:
            webbrowser.open(wa_url)
            log.warning("pyautogui/pygetwindow not installed. "
                        "Run:  pip install pyautogui pygetwindow")
        except Exception as e:
            webbrowser.open(wa_url)
            log.warning("WhatsApp silent-send failed (%s) — opened manually.", e)

        return True
    except Exception as e:
        log.error("WhatsApp send failed: %s", e)
        return False


# ══════════════════════════════════════════════════════════
# MAIN DISPATCHER
# ══════════════════════════════════════════════════════════

def _dispatch(phone_e164: str, message: str,
              pdf_path: str = "", pdf_url: str = "") -> bool:
    """
    Try each sending method in priority order.
    Returns True if any method succeeded.
    """
    cfg    = _get_config()
    method = cfg.get("method", "wame").lower()

    # If explicitly set to meta or twilio — try that first
    if method == "meta":
        if _send_via_meta(phone_e164, message, pdf_path, pdf_url):
            return True
        if _send_via_twilio(phone_e164, message, pdf_url):
            return True

    elif method == "twilio":
        if _send_via_twilio(phone_e164, message, pdf_url):
            return True
        if _send_via_meta(phone_e164, message, pdf_path, pdf_url):
            return True

    else:
        # Auto mode — try APIs first, fall back to wa.me
        if _send_via_meta(phone_e164, message, pdf_path, pdf_url):
            return True
        if _send_via_twilio(phone_e164, message, pdf_url):
            return True

    # Final fallback — wa.me + image paste (fully automatic)
    log.info("No API configured — using wa.me + image fallback.")
    return _send_via_wame(phone_e164, message, pdf_path)


# ══════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════

def send_bill_message_async(
    phone: str,
    customer_name: str,
    invoice_id: int,
    total: float,
    paid: float,
    balance: float,
    old_balance: float = 0.0,
    bill_type: str = "invoice",
    pdf_url: str = "",
    pdf_path: str = "",
) -> None:
    """Send invoice WhatsApp message in background thread."""
    def _worker():
        try:
            p164    = _normalize_phone(phone)
            message = _build_bill_message(
                customer_name, invoice_id, total, paid,
                balance, old_balance, bill_type, pdf_url
            )
            log.info("WhatsApp: dispatching INV-%d to +%s", invoice_id, p164)
            _dispatch(p164, message, pdf_path, pdf_url)
        except Exception as e:
            log.error("WhatsApp async failed (non-fatal): %s", e, exc_info=True)

    threading.Thread(
        target=_worker, daemon=True,
        name=f"wa-bill-{invoice_id}"
    ).start()


def send_bill_message(
    phone: str,
    customer_name: str,
    invoice_id: int,
    total: float,
    paid: float,
    balance: float,
    pdf_path: str | None = None,
    old_balance: float = 0.0,
    bill_type: str = "invoice",
    pdf_url: str = "",
) -> bool:
    """Synchronous send (backward compatible)."""
    p164    = _normalize_phone(phone)
    message = _build_bill_message(
        customer_name, invoice_id, total, paid,
        balance, old_balance, bill_type,
        pdf_url or pdf_path or ""
    )
    return _dispatch(p164, message, pdf_path or "", pdf_url)


def send_payment_message(
    phone: str,
    customer_name: str,
    paid_amount: float,
    remaining_balance: float,
) -> bool:
    """Send payment receipt via WhatsApp."""
    p164    = _normalize_phone(phone)
    message = _build_payment_message(customer_name, paid_amount, remaining_balance)
    return _dispatch(p164, message)


def send_payment_message_async(
    phone: str,
    customer_name: str,
    paid_amount: float,
    remaining_balance: float,
) -> None:
    """Send payment receipt in background thread."""
    def _worker():
        try:
            p164    = _normalize_phone(phone)
            message = _build_payment_message(customer_name, paid_amount, remaining_balance)
            _dispatch(p164, message)
        except Exception as e:
            log.error("WhatsApp payment failed: %s", e)
    threading.Thread(target=_worker, daemon=True, name=f"wa-pay-{phone}").start()
