"""
PDF Invoice Generator - matches the NEW INDIAN STEEL printed bill exactly.
=========================================================================

Layout (top to bottom):
  - Centered "ESTIMATE" header + "CREDIT BILL" subtitle
  - Bigger logo top-left, shop info top-right
  - BILL NO + BILL Date row
  - To: <customer> | Checked By / Taken By / PH fields
  - Items table: S.No | Particulars | Qty | Unit | Rate | Amount
  - Two-column summary:
        Left column:   Old Balance | Bill Amount | Total Balance
        Right column:  Bill Amount | Sales Handling Charges | Net Amount
"""
import os
from datetime import datetime
from config import (INVOICES_DIR, SHOP_NAME, SHOP_ADDRESS,
                    SHOP_PHONE, SHOP_GSTIN, LOGO_PATH)
from logger import get_logger

log = get_logger(__name__)

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, A5
    from reportlab.lib.units import mm
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, Image as RLImage,
                                     HRFlowable)
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# Page size for printed bills.
# Set to A5 portrait (148 x 210mm) so it fits half an A4 sheet.
# Switch to A4 here if you ever want a full-page bill.
BILL_PAGESIZE = A5


# Brand colors
NAVY   = colors.HexColor("#1B3A6B")
BLUE   = colors.HexColor("#2E5FA3")
GREY   = colors.HexColor("#6C7A89")
BLACK  = colors.HexColor("#1A1A1A")
WHITE  = colors.white
LGREY  = colors.HexColor("#F5F6FA")
MGREY  = colors.HexColor("#D5D8DC")


def _ps(name, size=10, bold=False, align=TA_LEFT, color=BLACK, leading=None):
    kw = dict(fontName="Helvetica-Bold" if bold else "Helvetica",
              fontSize=size, alignment=align, textColor=color)
    if leading:
        kw["leading"] = leading
    return ParagraphStyle(name, **kw)


def _fmt_qty(v):
    """Show 117.5 as '117.50' and 4 as '4'."""
    try:
        f = float(v)
        return f"{f:.2f}".rstrip("0").rstrip(".") if f == int(f) else f"{f:.2f}"
    except Exception:
        return str(v)


def generate_invoice_pdf(invoice_id, customer_name, customer_phone,
                         items, total, paid, balance,
                         type="invoice",
                         transport=0.0, discount_pct=0.0, discount_amt=0.0,
                         old_balance=0.0, net_balance=0.0,
                         payment_type="Cash"):
    """
    items - list of dicts. Each item should have:
        product_name (str), qty (number), price (number), amount (number)
    Optional per-item key:
        unit (str) - 'Kgs' or 'Nos'. Defaults to 'Nos' if missing.
    """
    if not REPORTLAB_AVAILABLE:
        log.error("PDF generation skipped - reportlab not installed.")
        return None

    log.info("Generating invoice PDF: ID=%s, customer=%s, total=%.2f",
             invoice_id, customer_name, total)

    os.makedirs(INVOICES_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix   = "QUO" if type == "quotation" else "INV"
    filename = f"{prefix}-{invoice_id}_{date_str}.pdf"
    filepath = os.path.join(INVOICES_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=BILL_PAGESIZE,
                            topMargin=5*mm, bottomMargin=5*mm,
                            leftMargin=6*mm, rightMargin=6*mm)
    W = doc.width
    elements = []

    # ============================================================
    # HEADER: logo on left, shop info on right (compact for A5)
    # ============================================================
    # New logo already contains "NEW INDIAN STEEL" text, so we don't
    # repeat it in the header. Logo sits on the left, address + phone
    # on the right. "ESTIMATE" is the title and prints at the top.
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        try:
            logo_cell = RLImage(LOGO_PATH, width=35*mm, height=35*mm)
        except Exception:
            logo_cell = Paragraph(f"<b>{SHOP_NAME}</b>",
                                   _ps("ln", 14, True, color=NAVY))

    shop_info_para = Paragraph(
        f"<font size='10' color='#6C7A89'>{SHOP_ADDRESS}</font><br/>"
        f"<font size='10' color='#6C7A89'>Ph: {SHOP_PHONE}</font>",
        _ps("si", 10, False, TA_LEFT, BLACK, leading=14)
    )

    estimate_title = "QUOTATION" if type == "quotation" else "ESTIMATE"
    title_para = Paragraph(
        f"<b>{estimate_title}</b>",
        _ps("t1", 20, True, TA_RIGHT, NAVY, leading=22),
    )

    header_row = Table(
        [[logo_cell, shop_info_para, title_para]],
        colWidths=[37*mm, W - 37*mm - 42*mm, 42*mm],
    )
    header_row.setStyle(TableStyle([
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING',(0,0), (-1,-1), 0),
    ]))
    elements.append(header_row)
    elements.append(Spacer(1, 1.5*mm))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=NAVY))
    elements.append(Spacer(1, 1.5*mm))

    # ============================================================
    # BILL NO + DATE row
    # ============================================================
    bn_para = Paragraph(
        f"<b>BILL NO :</b> {prefix}-{invoice_id}",
        _ps("bn", 9, False, TA_LEFT, BLACK)
    )
    bd_para = Paragraph(
        f"<b>BILL DATE :</b> {datetime.now().strftime('%d/%m/%Y')}",
        _ps("bd", 9, False, TA_RIGHT, BLACK)
    )
    elements.append(Table(
        [[bn_para, bd_para]],
        colWidths=[W*0.5, W*0.5]
    ))
    elements.append(Spacer(1, 1*mm))

    # ============================================================
    # Customer "To:" block - full width, no Checked/Taken/PH fields
    # ============================================================
    # Customer + payment type on the same row
    pay_label = f"&nbsp;&nbsp;&nbsp;<font size='8' color='#2E5FA3'><b>[ {payment_type} ]</b></font>" if payment_type else ""
    elements.append(Paragraph(
        f"<b>To :</b> "
        f"<font size='11' color='#1B3A6B'><b>{customer_name}</b></font> "
        f"&nbsp;&nbsp;<font size='9' color='#6C7A89'>Ph: {customer_phone}</font>"
        f"{pay_label}",
        _ps("cb", 9, False, TA_LEFT, BLACK, leading=13)
    ))
    elements.append(Spacer(1, 2*mm))

    # ============================================================
    # ITEMS TABLE
    # ============================================================
    table_data = [[
        Paragraph("<b>S.No</b>",         _ps("h", 9, True, TA_CENTER, WHITE)),
        Paragraph("<b>Particulars</b>",  _ps("h", 9, True, TA_LEFT,   WHITE)),
        Paragraph("<b>Qty</b>",          _ps("h", 9, True, TA_RIGHT,  WHITE)),
        Paragraph("<b>Unit</b>",         _ps("h", 9, True, TA_CENTER, WHITE)),
        Paragraph("<b>Rate</b>",         _ps("h", 9, True, TA_RIGHT,  WHITE)),
        Paragraph("<b>Amount</b>",       _ps("h", 9, True, TA_RIGHT,  WHITE)),
    ]]
    for i, item in enumerate(items, 1):
        unit = (item.get("unit") or "Nos").strip() or "Nos"
        table_data.append([
            Paragraph(str(i),                 _ps(f"r{i}a", 9, False, TA_CENTER)),
            Paragraph(item["product_name"],   _ps(f"r{i}b", 9, False, TA_LEFT)),
            Paragraph(_fmt_qty(item["qty"]),  _ps(f"r{i}c", 9, False, TA_RIGHT)),
            Paragraph(unit,                   _ps(f"r{i}d", 9, False, TA_CENTER)),
            Paragraph(f"{float(item['price']):.2f}",  _ps(f"r{i}e", 9, False, TA_RIGHT)),
            Paragraph(f"{float(item['amount']):.2f}", _ps(f"r{i}f", 9, False, TA_RIGHT)),
        ])

    # Pad with blank rows so the bill always looks like a full template
    blank_rows_needed = max(0, 6 - len(items))
    for _ in range(blank_rows_needed):
        table_data.append([" ", " ", " ", " ", " ", " "])

    items_table = Table(
        table_data,
        colWidths=[W*0.08, W*0.40, W*0.13, W*0.10, W*0.13, W*0.16]
    )
    items_table.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  NAVY),
        ('TEXTCOLOR',     (0,0), (-1,0),  WHITE),
        ('FONTNAME',      (0,0), (-1,0),  'Helvetica-Bold'),
        ('GRID',          (0,0), (-1,-1), 0.3, MGREY),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
        ('LEFTPADDING',   (0,0), (-1,-1), 3),
        ('RIGHTPADDING',  (0,0), (-1,-1), 3),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 2*mm))

    # ============================================================
    # SUMMARY: two columns
    #   Left  -> Old Balance / Bill Amount / Total Balance
    #   Right -> Bill Amount / Sales Handling / Net Amount
    # ============================================================
    bill_amt_subtotal = float(total) - float(transport)   # before handling
    sales_handling    = float(transport)
    net_amount        = float(total)
    # LEFT summary mirrors the printed-bill convention: each row is the
    # customer's ledger position. "Bill Amount" here = THIS bill's
    # remaining balance, so Old + Bill = Total cleanly even after a payment.
    invoice_remaining = float(balance)
    total_balance     = float(old_balance) + invoice_remaining

    def _row(label, value, bold=False, color=BLACK):
        font = "Helvetica-Bold" if bold else "Helvetica"
        return [
            Paragraph(f"<font name='{font}'>{label}</font>",
                      _ps("sl", 9, bold, TA_LEFT, color)),
            Paragraph(f"<font name='{font}'>{value}</font>",
                      _ps("sv", 9, bold, TA_RIGHT, color)),
        ]

    # Left summary block (customer ledger view)
    left_summary = Table([
        _row("Old Balance",   f"{float(old_balance):,.2f}"),
        _row("Bill Amount",   f"{invoice_remaining:,.2f}"),
        _row("Total Balance", f"{total_balance:,.2f}", bold=True, color=NAVY),
    ], colWidths=[W*0.20, W*0.20])
    left_summary.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE',     (0,2), (-1,2),  0.5, NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    # Right summary block (this bill's breakdown)
    disc_val     = float(discount_amt)
    disc_pct_val = float(discount_pct)
    right_rows   = []
    if disc_val > 0:
        original_subtotal = bill_amt_subtotal + disc_val
        right_rows.append(_row("Sub Total", f"{original_subtotal:,.2f}"))
        disc_label = f"Discount ({disc_pct_val:.0f}%)" if disc_pct_val > 0 else "Discount"
        right_rows.append(_row(disc_label, f"- {disc_val:,.2f}",
                               color=colors.HexColor("#CC0000")))
    right_rows.append(_row("Bill Amount", f"{bill_amt_subtotal:,.2f}"))
    if sales_handling > 0:
        right_rows.append(_row("Sales Handling Charges", f"{sales_handling:,.2f}"))
    right_rows.append(_row("Net Amount", f"{net_amount:,.2f}", bold=True, color=NAVY))

    right_summary = Table(right_rows, colWidths=[W*0.30, W*0.20])
    right_summary.setStyle(TableStyle([
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('LINEABOVE',     (0,-1), (-1,-1), 0.5, NAVY),
        ('TOPPADDING',    (0,0), (-1,-1), 2),
        ('BOTTOMPADDING', (0,0), (-1,-1), 2),
    ]))

    summary_wrapper = Table(
        [[left_summary, right_summary]],
        colWidths=[W*0.50, W*0.50],
    )
    summary_wrapper.setStyle(TableStyle([
        ('VALIGN',      (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0),
        ('RIGHTPADDING',(0,0), (-1,-1), 0),
    ]))
    elements.append(summary_wrapper)

    # Show "Paid Now" only when there was a payment with this bill
    if float(paid) > 0:
        elements.append(Spacer(1, 1*mm))
        paid_para = Paragraph(
            f"<b>Paid Now:</b> {float(paid):,.2f}",
            _ps("pn", 9, True, TA_RIGHT, NAVY)
        )
        elements.append(paid_para)

    # ============================================================
    # FOOTER
    # ============================================================
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=0.4, color=MGREY))
    elements.append(Spacer(1, 1*mm))
    elements.append(Paragraph(
        f"Thank you for your business! &nbsp;|&nbsp; {SHOP_NAME} &nbsp;|&nbsp; {SHOP_PHONE}",
        _ps("ft", 7, False, TA_CENTER, GREY)
    ))

    # Build
    doc.build(elements)
    log.info("PDF generated: %s", filepath)

    # Auto-generate JPG alongside PDF for WhatsApp image sharing
    try:
        import fitz  # pymupdf
        doc_mupdf = fitz.open(filepath)
        page = doc_mupdf[0]
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2× scale for clarity
        jpg_path = filepath.replace(".pdf", ".jpg")
        pix.save(jpg_path)
        doc_mupdf.close()
        log.info("JPG generated for WhatsApp sharing: %s", os.path.basename(jpg_path))
    except ImportError:
        log.debug("pymupdf not installed — JPG skipped. Run: pip install pymupdf")
    except Exception as _e:
        log.debug("JPG generation failed (non-fatal): %s", _e)

    return filepath


# ============================================================
# CUSTOMER STATEMENT PDF (used by History "Export Statement" button)
# ============================================================

def generate_customer_statement_pdf(customer_name, customer_phone,
                                     invoices, payments, computed_due):
    """Generate a per-customer ledger PDF showing all invoices + payments.

    Args:
        customer_name   - str
        customer_phone  - str
        invoices        - list of sqlite3.Row or dict with keys
                          id, date, total, paid, balance, type
        payments        - list of sqlite3.Row or dict with keys
                          id, date, amount
        computed_due    - float (the customer's running balance)

    Returns the absolute path to the generated PDF, or None on failure.
    """
    if not REPORTLAB_AVAILABLE:
        log.error("Statement PDF skipped - reportlab not installed.")
        return None

    os.makedirs(INVOICES_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_phone = "".join(ch for ch in str(customer_phone) if ch.isdigit()) or "x"
    filename = f"STATEMENT-{safe_phone}_{ts}.pdf"
    filepath = os.path.join(INVOICES_DIR, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4,
                            topMargin=10*mm, bottomMargin=10*mm,
                            leftMargin=10*mm, rightMargin=10*mm)
    W = doc.width
    elements = []

    # Header
    logo_cell = ""
    if os.path.exists(LOGO_PATH):
        try:
            logo_cell = RLImage(LOGO_PATH, width=24*mm, height=24*mm)
        except Exception:
            pass
    shop_para = Paragraph(
        f"<b><font size='16' color='#1B3A6B'>{SHOP_NAME}</font></b><br/>"
        f"<font size='9' color='#6C7A89'>{SHOP_ADDRESS}</font><br/>"
        f"<font size='9' color='#6C7A89'>Ph: {SHOP_PHONE}</font>",
        _ps("si", 9, False, TA_LEFT, BLACK, leading=12),
    )
    elements.append(Table([[logo_cell, shop_para]],
                          colWidths=[26*mm, W - 26*mm]))
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph("<b>CUSTOMER STATEMENT</b>",
                              _ps("t1", 16, True, TA_CENTER, NAVY)))
    elements.append(Spacer(1, 2*mm))
    elements.append(HRFlowable(width="100%", thickness=0.6, color=NAVY))
    elements.append(Spacer(1, 3*mm))

    # Customer info
    elements.append(Paragraph(
        f"<b>To :</b> <font size='12' color='#1B3A6B'><b>{customer_name}</b></font> "
        f"&nbsp;&nbsp; <font color='#6C7A89'>Ph: {customer_phone}</font> "
        f"&nbsp;&nbsp; <font color='#6C7A89'>As on: {datetime.now().strftime('%d/%m/%Y')}</font>",
        _ps("ci", 10, False, TA_LEFT, BLACK, leading=14),
    ))
    elements.append(Spacer(1, 4*mm))

    # Build a combined chronological ledger
    def _row(d):
        # accept Row or dict
        try:
            return dict(d)
        except Exception:
            return d

    rows = []
    for inv in invoices:
        d = _row(inv)
        rows.append({
            "date":  d.get("date", ""),
            "ref":   f"INV-{d.get('id','')}",
            "kind":  (d.get("type") or "invoice").title(),
            "debit": float(d.get("total", 0) or 0),
            "credit": float(d.get("paid", 0) or 0),
        })
    for pay in payments:
        d = _row(pay)
        rows.append({
            "date":  d.get("date", ""),
            "ref":   f"PAY-{d.get('id','')}",
            "kind":  "Payment",
            "debit":  0.0,
            "credit": float(d.get("amount", 0) or 0),
        })
    rows.sort(key=lambda r: r.get("date", ""))

    # Items table
    header = [
        Paragraph("<b>Date</b>",   _ps("h", 10, True, TA_LEFT,   WHITE)),
        Paragraph("<b>Ref</b>",    _ps("h", 10, True, TA_LEFT,   WHITE)),
        Paragraph("<b>Type</b>",   _ps("h", 10, True, TA_LEFT,   WHITE)),
        Paragraph("<b>Debit</b>",  _ps("h", 10, True, TA_RIGHT,  WHITE)),
        Paragraph("<b>Credit</b>", _ps("h", 10, True, TA_RIGHT,  WHITE)),
    ]
    table_data = [header]
    total_debit = total_credit = 0.0
    for r in rows:
        total_debit  += r["debit"]
        total_credit += r["credit"]
        table_data.append([
            Paragraph(str(r["date"]),  _ps("c", 9, False, TA_LEFT)),
            Paragraph(str(r["ref"]),   _ps("c", 9, False, TA_LEFT)),
            Paragraph(str(r["kind"]),  _ps("c", 9, False, TA_LEFT)),
            Paragraph(f"{r['debit']:,.2f}"  if r["debit"]  else "",
                      _ps("c", 9, False, TA_RIGHT)),
            Paragraph(f"{r['credit']:,.2f}" if r["credit"] else "",
                      _ps("c", 9, False, TA_RIGHT)),
        ])
    table_data.append([
        "", "",
        Paragraph("<b>TOTAL</b>", _ps("c", 10, True, TA_RIGHT, NAVY)),
        Paragraph(f"<b>{total_debit:,.2f}</b>",
                  _ps("c", 10, True, TA_RIGHT, NAVY)),
        Paragraph(f"<b>{total_credit:,.2f}</b>",
                  _ps("c", 10, True, TA_RIGHT, NAVY)),
    ])

    t = Table(table_data,
              colWidths=[W*0.22, W*0.18, W*0.18, W*0.21, W*0.21])
    t.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (-1,0),  NAVY),
        ('TEXTCOLOR',     (0,0), (-1,0),  WHITE),
        ('GRID',          (0,0), (-1,-1), 0.4, MGREY),
        ('VALIGN',        (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING',    (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LINEABOVE',     (0,-1), (-1,-1), 0.8, NAVY),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))

    # Final due
    elements.append(HRFlowable(width="100%", thickness=0.6, color=NAVY))
    elements.append(Spacer(1, 2*mm))
    elements.append(Paragraph(
        f"<b>Running Balance Due:</b> "
        f"<font color='#1B3A6B'>{float(computed_due):,.2f}</font>",
        _ps("rb", 13, True, TA_RIGHT, BLACK),
    ))

    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        f"Thank you for your business! &nbsp;|&nbsp; {SHOP_NAME} &nbsp;|&nbsp; {SHOP_PHONE}",
        _ps("ft", 9, False, TA_CENTER, GREY),
    ))

    doc.build(elements)
    log.info("Statement PDF generated: %s", filepath)
    return filepath
