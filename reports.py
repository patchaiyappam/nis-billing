"""
Reports Module — Daily Sales Report PDF
========================================
Generates professional PDF reports using reportlab with the NIS brand style.
"""
import os
from datetime import datetime
from config import (INVOICES_DIR, SHOP_NAME, SHOP_ADDRESS,
                    SHOP_PHONE, SHOP_GSTIN, LOGO_PATH)
from logger import get_logger
from database import (
    get_today_sales_summary, get_today_invoices, get_today_payments,
    get_today_payments_total, get_top_products_today, get_pending_customers_today,
)

log = get_logger(__name__)

REPORTS_DIR = os.path.join(os.path.dirname(INVOICES_DIR), "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, Image as RLImage,
                                     HRFlowable, PageBreak)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

# ── Brand colors (same as pdf_generator.py) ──────────────
if REPORTLAB_OK:
    NAVY  = colors.HexColor("#1B3A6B")
    BLUE  = colors.HexColor("#2E5FA3")
    GREY  = colors.HexColor("#6C7A89")
    BLACK = colors.HexColor("#1A1A1A")
    WHITE = colors.white
    LGREY = colors.HexColor("#F5F6FA")
    MGREY = colors.HexColor("#D5D8DC")
    RED   = colors.HexColor("#C0392B")
    GREEN = colors.HexColor("#1E8449")
    AMBER = colors.HexColor("#D97706")


def _ps(name, size=10, bold=False, align=TA_LEFT, color=None, leading=None):
    """Shorthand for ParagraphStyle."""
    if color is None:
        color = BLACK
    kw = dict(fontName="Helvetica-Bold" if bold else "Helvetica",
              fontSize=size, alignment=align, textColor=color)
    if leading:
        kw["leading"] = leading
    return ParagraphStyle(name, **kw)


# ══════════════════════════════════════════════════════════
# DAILY SALES REPORT
# ══════════════════════════════════════════════════════════

def generate_daily_report():
    """
    Generate a daily sales report PDF for today.
    Returns (filepath, error_message).
    - On success: (path, None)
    - On failure: (None, error_string)
    """
    if not REPORTLAB_OK:
        return None, "reportlab is not installed."

    log.info("Generating daily sales report...")

    today_str = datetime.now().strftime("%Y%m%d")
    today_display = datetime.now().strftime("%d %B %Y (%A)")
    time_display = datetime.now().strftime("%I:%M %p")
    filename = f"DailyReport_{today_str}.pdf"
    filepath = os.path.join(REPORTS_DIR, filename)

    # ── Fetch data ────────────────────────────────────
    summary = get_today_sales_summary()
    invoices = get_today_invoices()
    payments = get_today_payments()
    payments_total = get_today_payments_total()
    top_products = get_top_products_today(10)
    pending = get_pending_customers_today()

    total_pending = sum(c["total_due"] for c in pending)

    try:
        doc = SimpleDocTemplate(filepath, pagesize=A4,
                                topMargin=12*mm, bottomMargin=12*mm,
                                leftMargin=12*mm, rightMargin=12*mm)
        W = doc.width
        elements = []

        # ══════════════════════════════════════════════
        # HEADER
        # ══════════════════════════════════════════════
        logo_cell = ""
        if os.path.exists(LOGO_PATH):
            try:
                logo_cell = RLImage(LOGO_PATH, width=30*mm, height=30*mm)
            except Exception:
                logo_cell = ""

        hdr = Table([[
            logo_cell,
            Paragraph(f"<b>{SHOP_NAME}</b><br/>"
                      f"<font size=9 color='#6C7A89'>{SHOP_ADDRESS}</font><br/>"
                      f"<font size=9 color='#6C7A89'>Ph: {SHOP_PHONE}  |  GSTIN: {SHOP_GSTIN}</font>",
                      _ps("h1", 14, True, color=NAVY)),
            Paragraph(f"<b>DAILY SALES REPORT</b><br/>"
                      f"<font size=9>{today_display}</font><br/>"
                      f"<font size=9>Generated: {time_display}</font>",
                      _ps("h2", 13, True, TA_RIGHT, NAVY)),
        ]], colWidths=[W*0.12, W*0.52, W*0.36])
        hdr.setStyle(TableStyle([
            ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',    (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]))
        elements.append(hdr)
        elements.append(HRFlowable(width="100%", thickness=3, color=BLUE, spaceAfter=4*mm))

        # ══════════════════════════════════════════════
        # SUMMARY METRICS
        # ══════════════════════════════════════════════
        elements.append(Paragraph("<b>TODAY'S SUMMARY</b>", _ps("s0", 12, True, color=NAVY)))
        elements.append(Spacer(1, 3*mm))

        metrics = Table([[
            Paragraph(f"<b>Total Sales</b><br/><font size=14 color='#1B3A6B'>Rs. {summary['total_sales']:,.2f}</font>",
                      _ps("m1", 9, color=GREY, leading=18)),
            Paragraph(f"<b>Collected</b><br/><font size=14 color='#1E8449'>Rs. {summary['total_paid']:,.2f}</font>",
                      _ps("m2", 9, color=GREY, leading=18)),
            Paragraph(f"<b>Payments Today</b><br/><font size=14 color='#2E5FA3'>Rs. {payments_total:,.2f}</font>",
                      _ps("m3", 9, color=GREY, leading=18)),
            Paragraph(f"<b>Invoices</b><br/><font size=14 color='#D97706'>{summary['invoice_count']}</font>",
                      _ps("m4", 9, color=GREY, leading=18)),
            Paragraph(f"<b>Pending Due</b><br/><font size=14 color='#C0392B'>Rs. {summary['total_balance']:,.2f}</font>",
                      _ps("m5", 9, color=GREY, leading=18)),
        ]], colWidths=[W*0.20]*5)
        metrics.setStyle(TableStyle([
            ('BOX',           (0,0), (-1,-1), 1, MGREY),
            ('INNERGRID',     (0,0), (-1,-1), 0.5, MGREY),
            ('BACKGROUND',    (0,0), (-1,-1), LGREY),
            ('VALIGN',        (0,0), (-1,-1), 'TOP'),
            ('TOPPADDING',    (0,0), (-1,-1), 8),
            ('BOTTOMPADDING', (0,0), (-1,-1), 8),
            ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ]))
        elements.append(metrics)
        elements.append(Spacer(1, 5*mm))

        # ══════════════════════════════════════════════
        # INVOICES TABLE
        # ══════════════════════════════════════════════
        elements.append(Paragraph("<b>TODAY'S INVOICES</b>", _ps("s1", 11, True, color=NAVY)))
        elements.append(Spacer(1, 2*mm))

        inv_header = [Paragraph(h, _ps(f"ih{i}", 9, True, TA_CENTER, WHITE))
                      for i, h in enumerate(["#", "Invoice", "Customer", "Time", "Total", "Paid", "Balance"])]
        inv_rows = [inv_header]

        for i, inv in enumerate(invoices, 1):
            prefix = "QUO" if inv.get("type", "invoice").lower() == "quotation" else "INV"
            time_str = inv["date"][11:16] if len(inv["date"]) > 11 else ""
            inv_rows.append([
                str(i),
                f"{prefix}-{inv['id']}",
                (inv.get("customer_name") or inv["customer_phone"])[:20],
                time_str,
                f"Rs.{inv['total']:,.2f}",
                f"Rs.{inv['paid']:,.2f}",
                f"Rs.{inv['balance']:,.2f}",
            ])

        if not invoices:
            inv_rows.append(["", "", "No invoices today", "", "", "", ""])

        inv_t = Table(inv_rows, colWidths=[W*w for w in [0.05, 0.10, 0.25, 0.10, 0.17, 0.17, 0.16]])
        inv_style = [
            ('BACKGROUND',  (0,0), (-1,0), NAVY),
            ('TEXTCOLOR',   (0,0), (-1,0), WHITE),
            ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,-1), 9),
            ('ALIGN',       (0,0), (1,-1), 'CENTER'),
            ('ALIGN',       (3,0), (3,-1), 'CENTER'),
            ('ALIGN',       (4,1), (-1,-1), 'RIGHT'),
            ('GRID',        (0,0), (-1,-1), 0.5, MGREY),
            ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ]
        for r in range(1, len(inv_rows)):
            if r % 2 == 0:
                inv_style.append(('BACKGROUND', (0,r), (-1,r), LGREY))
        inv_t.setStyle(TableStyle(inv_style))
        elements.append(inv_t)
        elements.append(Spacer(1, 5*mm))

        # ══════════════════════════════════════════════
        # PAYMENTS TABLE
        # ══════════════════════════════════════════════
        elements.append(Paragraph("<b>TODAY'S PAYMENTS</b>", _ps("s2", 11, True, color=NAVY)))
        elements.append(Spacer(1, 2*mm))

        pay_header = [Paragraph(h, _ps(f"ph{i}", 9, True, TA_CENTER, WHITE))
                      for i, h in enumerate(["#", "Payment ID", "Customer", "Time", "Amount"])]
        pay_rows = [pay_header]

        for i, pay in enumerate(payments, 1):
            time_str = pay["date"][11:16] if len(pay["date"]) > 11 else ""
            pay_rows.append([
                str(i),
                f"PAY-{pay['id']}",
                (pay.get("customer_name") or pay["customer_phone"])[:20],
                time_str,
                f"Rs.{pay['amount']:,.2f}",
            ])

        if not payments:
            pay_rows.append(["", "", "No payments today", "", ""])

        # Total row
        pay_rows.append(["", "", "", "TOTAL", f"Rs.{payments_total:,.2f}"])

        pay_t = Table(pay_rows, colWidths=[W*w for w in [0.06, 0.16, 0.38, 0.15, 0.25]])
        pst = [
            ('BACKGROUND',  (0,0), (-1,0), NAVY),
            ('TEXTCOLOR',   (0,0), (-1,0), WHITE),
            ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE',    (0,0), (-1,-1), 9),
            ('ALIGN',       (0,0), (1,-1), 'CENTER'),
            ('ALIGN',       (3,0), (3,-1), 'CENTER'),
            ('ALIGN',       (4,1), (4,-1), 'RIGHT'),
            ('GRID',        (0,0), (-1,-1), 0.5, MGREY),
            ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',  (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',(0,0), (-1,-1), 4),
            ('FONTNAME',    (0,-1), (-1,-1), 'Helvetica-Bold'),
            ('BACKGROUND',  (0,-1), (-1,-1), LGREY),
        ]
        pay_t.setStyle(TableStyle(pst))
        elements.append(pay_t)
        elements.append(Spacer(1, 5*mm))

        # ══════════════════════════════════════════════
        # TOP PRODUCTS
        # ══════════════════════════════════════════════
        if top_products:
            elements.append(Paragraph("<b>TOP SELLING PRODUCTS (TODAY)</b>",
                                      _ps("s3", 11, True, color=NAVY)))
            elements.append(Spacer(1, 2*mm))

            prod_header = [Paragraph(h, _ps(f"prh{i}", 9, True, TA_CENTER, WHITE))
                           for i, h in enumerate(["#", "Product", "Qty Sold", "Revenue"])]
            prod_rows = [prod_header]
            for i, p in enumerate(top_products, 1):
                prod_rows.append([
                    str(i), p["name"],
                    f"{p['total_qty']:g}",
                    f"Rs.{p['total_amount']:,.2f}",
                ])

            prod_t = Table(prod_rows, colWidths=[W*w for w in [0.06, 0.50, 0.18, 0.26]])
            prod_style = [
                ('BACKGROUND',  (0,0), (-1,0), NAVY),
                ('TEXTCOLOR',   (0,0), (-1,0), WHITE),
                ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',    (0,0), (-1,-1), 9),
                ('ALIGN',       (0,0), (0,-1), 'CENTER'),
                ('ALIGN',       (2,0), (2,-1), 'CENTER'),
                ('ALIGN',       (3,1), (3,-1), 'RIGHT'),
                ('GRID',        (0,0), (-1,-1), 0.5, MGREY),
                ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING',  (0,0), (-1,-1), 4),
                ('BOTTOMPADDING',(0,0), (-1,-1), 4),
            ]
            for r in range(1, len(prod_rows)):
                if r % 2 == 0:
                    prod_style.append(('BACKGROUND', (0,r), (-1,r), LGREY))
            prod_t.setStyle(TableStyle(prod_style))
            elements.append(prod_t)
            elements.append(Spacer(1, 5*mm))

        # ══════════════════════════════════════════════
        # PENDING CUSTOMERS
        # ══════════════════════════════════════════════
        if pending:
            elements.append(Paragraph(f"<b>PENDING CUSTOMERS ({len(pending)})</b>",
                                      _ps("s4", 11, True, color=NAVY)))
            elements.append(Spacer(1, 2*mm))

            pend_header = [Paragraph(h, _ps(f"pdh{i}", 9, True, TA_CENTER, WHITE))
                           for i, h in enumerate(["#", "Customer", "Phone", "Amount Due"])]
            pend_rows = [pend_header]
            for i, c in enumerate(pending[:20], 1):  # limit to top 20
                pend_rows.append([
                    str(i), c["name"], c["phone"],
                    f"Rs.{c['total_due']:,.2f}",
                ])
            # Total row
            pend_rows.append(["", "", "TOTAL", f"Rs.{total_pending:,.2f}"])

            pend_t = Table(pend_rows, colWidths=[W*w for w in [0.06, 0.38, 0.26, 0.30]])
            pdst = [
                ('BACKGROUND',  (0,0), (-1,0), NAVY),
                ('TEXTCOLOR',   (0,0), (-1,0), WHITE),
                ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE',    (0,0), (-1,-1), 9),
                ('ALIGN',       (0,0), (0,-1), 'CENTER'),
                ('ALIGN',       (2,0), (2,-1), 'CENTER'),
                ('ALIGN',       (3,1), (3,-1), 'RIGHT'),
                ('GRID',        (0,0), (-1,-1), 0.5, MGREY),
                ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
                ('TOPPADDING',  (0,0), (-1,-1), 4),
                ('BOTTOMPADDING',(0,0), (-1,-1), 4),
                ('FONTNAME',    (0,-1), (-1,-1), 'Helvetica-Bold'),
                ('BACKGROUND',  (0,-1), (-1,-1), LGREY),
                ('LINEABOVE',   (0,-1), (-1,-1), 1, NAVY),
            ]
            pend_t.setStyle(TableStyle(pdst))
            elements.append(pend_t)
            elements.append(Spacer(1, 5*mm))

        # ══════════════════════════════════════════════
        # FOOTER
        # ══════════════════════════════════════════════
        elements.append(HRFlowable(width="100%", thickness=1, color=BLUE))
        elements.append(Spacer(1, 2*mm))
        elements.append(Paragraph(
            f"Generated: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}  |  "
            f"{SHOP_NAME}  |  {SHOP_PHONE}",
            _ps("ft", 9, False, TA_CENTER, GREY)))

        doc.build(elements)
        size_kb = os.path.getsize(filepath) / 1024
        log.info("Daily report created: %s (%.1f KB)", filename, size_kb)
        return filepath, None

    except Exception as e:
        log.error("Daily report generation failed: %s", e, exc_info=True)
        return None, str(e)
