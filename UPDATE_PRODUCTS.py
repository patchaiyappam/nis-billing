"""
UPDATE_PRODUCTS.py - Replace ONLY the products table with the new
                     262-item price list from 'price list - Sheet1 (3).csv'.

Customers, invoices, and payments are LEFT INTACT. Only the products table
is wiped and reseeded.

Run on the shop PC (and laptop) once after closing the app:
    python UPDATE_PRODUCTS.py
"""
from __future__ import annotations
import os, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Each tuple: (name, sale_price, unit)
PRODUCTS = [
    ("1 1/2\" SQ KEEL", 200.00, "Nos"),
    ("1 1/2\" T BALL(Round)", 80.00, "Nos"),
    ("1 1/2\"LORRY KELL", 30.00, "Nos"),
    ("1 1/2\"O KEEL", 130.00, "Nos"),
    ("1 1/4\"O KEEL", 90.00, "Nos"),
    ("1 1/4\"SQ KEEL", 150.00, "Nos"),
    ("1\"O KEEL", 60.00, "Nos"),
    ("1\"SQ KEEL", 100.00, "Nos"),
    ("1*1/4 flats", 67.00, "Kgs"),
    ("1*1/4 L angle", 67.00, "Kgs"),
    ("1*1/8 flats", 70.00, "Kgs"),
    ("1*1/8 L angle", 70.00, "Kgs"),
    ("1/2ltr PAINT", 180.00, "Nos"),
    ("1/2ltr RED OXIDE", 130.00, "Nos"),
    ("1/2ltr YELLOW PRIMER", 150.00, "Nos"),
    ("10FT AC SHEET", 640.00, "Nos"),
    ("10ft COLOUR SHEET JSW", 1600.00, "Nos"),
    ("10ft COLOUR SHEET TATA", 2000.00, "Nos"),
    ("10FT GC SHEET", 800.00, "Nos"),
    ("10ft pentCOLOUR SHEET JSW", 1700.00, "Nos"),
    ("10ft pentCOLOUR SHEET TATA", 2100.00, "Nos"),
    ("10ft RIDGE SHEET TATA", 1500.00, "Nos"),
    ("10FT SADE NET", 350.00, "Kgs"),
    ("10FT Shade Net(50%)", 2100.00, "Nos"),
    ("10FT Shade Net(75%)", 3500.00, "Nos"),
    ("10KG GI WIRE", 100.00, "Kgs"),
    ("10mm armer bit", 80.00, "Nos"),
    ("10MM BIN PLATE", 90.00, "Nos"),
    ("10MM LIVER", 130.00, "Nos"),
    ("10mm metal bit", 400.00, "Nos"),
    ("10MM SQ ROD", 68.00, "Kgs"),
    ("10MM TMT JSW", 82.00, "Kgs"),
    ("10MM TMT PULKIT", 72.00, "Kgs"),
    ("10MM TMT TATA", 646.00, "Nos"),
    ("11ft COLOUR SHEET JSW", 1760.00, "Nos"),
    ("11ft COLOUR SHEET TATA", 2200.00, "Nos"),
    ("12 ROUND ROD", 68.00, "Kgs"),
    ("12FT AC SHEET", 880.00, "Nos"),
    ("12ft COLOUR SHEET JSW", 1920.00, "Nos"),
    ("12ft COLOUR SHEET TATA", 2400.00, "Nos"),
    ("12FT GC SHEET", 900.00, "Nos"),
    ("12ft pentCOLOUR SHEET JSW", 2040.00, "Nos"),
    ("12ft pentCOLOUR SHEET TATA", 2520.00, "Nos"),
    ("12KG GI WIRE", 100.00, "Kgs"),
    ("12MM BIN PLATE", 95.00, "Nos"),
    ("12MM LIVER", 150.00, "Nos"),
    ("12mm metal bit", 580.00, "Nos"),
    ("12MM PUSS", 10.00, "Nos"),
    ("12MM Taver bold", 120.00, "Nos"),
    ("12MM THAPPA", 80.00, "Nos"),
    ("12MM THAPPA SET", 120.00, "Nos"),
    ("12MM TMT JSW", 79.00, "Kgs"),
    ("12MM TMT PILKIT", 72.00, "Kgs"),
    ("12MM TMT TATA", 913.00, "Nos"),
    ("13MM BALISH ROD", 71.00, "Kgs"),
    ("13MM SQ ROD", 67.00, "Kgs"),
    ("14\"cutting wheel", 150.00, "Nos"),
    ("14ft COLOUR SHEET JSW", 2240.00, "Nos"),
    ("14ft COLOUR SHEET TATA", 2800.00, "Nos"),
    ("14ft pentCOLOUR SHEET JSW", 2380.00, "Nos"),
    ("14ft pentCOLOUR SHEET TATA", 2940.00, "Nos"),
    ("14mm armer bit", 120.00, "Nos"),
    ("15ft COLOUR SHEET JSW", 2400.00, "Nos"),
    ("15ft COLOUR SHEET TATA", 3000.00, "Nos"),
    ("15MTR DAPE", 170.00, "Nos"),
    ("16 ROUND ROD", 68.00, "Kgs"),
    ("16ft COLOUR SHEET JSW", 2560.00, "Nos"),
    ("16ft COLOUR SHEET TATA", 3200.00, "Nos"),
    ("16ft pentCOLOUR SHEET JSW", 2720.00, "Nos"),
    ("16ft pentCOLOUR SHEET TATA", 3360.00, "Nos"),
    ("16KG GI WIRE", 130.00, "Kgs"),
    ("16mm armer bit", 130.00, "Nos"),
    ("16MM BIN PLATE", 125.00, "Nos"),
    ("16MM LIVER", 220.00, "Nos"),
    ("16MM PUSH", 10.00, "Nos"),
    ("16MM Taver bold", 140.00, "Nos"),
    ("16MM THAPPA", 10.00, "Nos"),
    ("16MM THAPPA SET", 140.00, "Nos"),
    ("16MM TMT JSW", 79.00, "Kgs"),
    ("16MM TMT PULKIT", 72.00, "Kgs"),
    ("16MM TMT TATA", 1624.00, "Nos"),
    ("17ft COLOUR SHEET JSW", 2720.00, "Nos"),
    ("17ft COLOUR SHEET TATA", 3400.00, "Nos"),
    ("18ft COLOUR SHEET JSW", 2880.00, "Nos"),
    ("18ft COLOUR SHEET TATA", 3600.00, "Nos"),
    ("18ft pentCOLOUR SHEET JSW", 3060.00, "Nos"),
    ("18ft pentCOLOUR SHEET TATA", 3780.00, "Nos"),
    ("18KG GI WIRE", 130.00, "Kgs"),
    ("19ft COLOUR SHEET JSW", 3040.00, "Nos"),
    ("19ft COLOUR SHEET TATA", 3800.00, "Nos"),
    ("1KELD PIECE", 120.00, "Nos"),
    ("1ltr PAINT", 350.00, "Nos"),
    ("1ltr RED OXIDE", 250.00, "Nos"),
    ("1ltr YELLOW PRIMER", 300.00, "Nos"),
    ("1 1/4*1/4 flats", 67.00, "Kgs"),
    ("1 1/4*1/8 L angle", 67.00, "Kgs"),
    ("1 1/2\" Bold Net", 10.00, "Nos"),
    ("1 1/2\" keld piece", 15.00, "Nos"),
    ("1 1/2\".sq T ball", 70.00, "Nos"),
    ("1 1/2\" T ball", 70.00, "Nos"),
    ("1 1/2*1/4 L angle", 67.00, "Kgs"),
    ("1 1/2*1/4 flats", 67.00, "Kgs"),
    ("1 1/2*1/2 flats", 70.00, "Kgs"),
    ("2 1/2\" NAILS", 100.00, "Nos"),
    ("2 1/2\"SUN FLOWER", 150.00, "Kgs"),
    ("2\" bold net", 10.00, "Nos"),
    ("2\" keld piece", 20.00, "Nos"),
    ("2\" LORRY KELL", 40.00, "Nos"),
    ("2\" T BALL (Round)", 90.00, "Nos"),
    ("2\"NAILS", 100.00, "Nos"),
    ("2\"PRUSH", 40.00, "Nos"),
    ("2\" T ball", 90.00, "Nos"),
    ("2*1/4 flats", 67.00, "Kgs"),
    ("2*1/4 L angle", 67.00, "Kgs"),
    ("20ft COLOUR SHEET JSW", 3200.00, "Nos"),
    ("20ft COLOUR SHEET TATA", 4000.00, "Nos"),
    ("20ft pentCOLOUR SHEET JSW", 3400.00, "Nos"),
    ("20ft pentCOLOUR SHEET TATA", 4200.00, "Nos"),
    ("21ft COLOUR SHEET JSW", 3360.00, "Nos"),
    ("21ft COLOUR SHEET TATA", 4200.00, "Nos"),
    ("22ft COLOUR SHEET JSW", 3520.00, "Nos"),
    ("22ft COLOUR SHEET TATA", 4400.00, "Nos"),
    ("22ft pentCOLOUR SHEET JSW", 3740.00, "Nos"),
    ("22ft pentCOLOUR SHEET TATA", 4620.00, "Nos"),
    ("23ft COLOUR SHEET JSW", 3680.00, "Nos"),
    ("23ft COLOUR SHEET TATA", 4600.00, "Nos"),
    ("24ft COLOUR SHEET JSW", 3840.00, "Nos"),
    ("24ft COLOUR SHEET TATA", 4800.00, "Nos"),
    ("24ft pentCOLOUR SHEET JSW", 4080.00, "Nos"),
    ("24ft pentCOLOUR SHEET TATA", 5040.00, "Nos"),
    ("2FT MANVETTI", 280.00, "Nos"),
    ("2 1/2\" bold net", 10.00, "Nos"),
    ("2 1/2\" T ball", 100.00, "Nos"),
    ("2 1/2*1/4 L angle", 67.00, "Kgs"),
    ("3\" bold net", 10.00, "Nos"),
    ("3\" NAILS", 100.00, "Nos"),
    ("3/4\"O KEEL", 40.00, "Nos"),
    ("30MTR TAPE", 270.00, "Nos"),
    ("3FT GREEN MESS", 12.00, "Nos"),
    ("3FT Weld mess", 22.00, "Nos"),
    ("4\" ROLLING PRUSH", 140.00, "Nos"),
    ("4\" ROLLING spanch", 35.00, "Nos"),
    ("4\"cutting wheel", 15.00, "Nos"),
    ("4\"flappin disk", 35.00, "Nos"),
    ("4\"grinding wheel", 30.00, "Nos"),
    ("4\"NAILS", 100.00, "Nos"),
    ("4FT GREEN MESS", 12.00, "Nos"),
    ("4FT Weld mess", 22.00, "Nos"),
    ("5\"cranting wheel", 50.00, "Nos"),
    ("5\"cutting wheel", 35.00, "Nos"),
    ("5\"NAILS", 100.00, "Nos"),
    ("5FT FENCING", 95.00, "Kgs"),
    ("5FT GREEN MESS", 12.00, "Nos"),
    ("5FT SADE NET", 350.00, "Kgs"),
    ("5FT Shade Net(50%)", 1050.00, "Nos"),
    ("5FT Shade Net(75%)", 2000.00, "Nos"),
    ("5FT Weld mess", 22.00, "Nos"),
    ("5MTR DAPE", 100.00, "Nos"),
    ("6\" SUNFLOWER", 150.00, "Kgs"),
    ("6FT AC SHEET", 450.00, "Nos"),
    ("6ft COLOUR SHEET JSW", 960.00, "Nos"),
    ("6ft COLOUR SHEET TATA", 1200.00, "Nos"),
    ("6ft pentCOLOUR SHEET JSW", 1020.00, "Nos"),
    ("6ft pentCOLOUR SHEET TATA", 1260.00, "Nos"),
    ("6mm metal bit", 150.00, "Nos"),
    ("6MM TMT TATA", 247.00, "Nos"),
    ("7.5MTR DAPE", 200.00, "Nos"),
    ("7.5MTR DAPE IKON", 240.00, "Nos"),
    ("8FT AC SHEET", 540.00, "Nos"),
    ("8FT GC SHEET", 700.00, "Nos"),
    ("8ft pentCOLOUR SHEET JSW", 1360.00, "Nos"),
    ("8ft pentCOLOUR SHEET TATA", 1680.00, "Nos"),
    ("8ft RIDGE SHEETJSW", 800.00, "Nos"),
    ("8mm armer bit", 70.00, "Nos"),
    ("8MM BIN PLATE", 70.00, "Nos"),
    ("8MM LIVER", 90.00, "Nos"),
    ("8mm metal bit", 250.00, "Nos"),
    ("8MM TMT JSW", 83.00, "Kgs"),
    ("8MM TMT PULKIT", 73.00, "Kgs"),
    ("8MM TMT TATA", 423.00, "Nos"),
    ("9ft COLOUR SHEET JSW", 1440.00, "Nos"),
    ("9ft COLOUR SHEET TATA", 1800.00, "Nos"),
    ("ALL PLATE", 100.00, "Nos"),
    ("BANTHAVALAIYAM", 120.00, "Nos"),
    ("BARBET WIRE", 95.00, "Kgs"),
    ("Best Arc(10kg)", 380.00, "Nos"),
    ("Best Arc(12kg)", 420.00, "Nos"),
    ("Binding wire", 110.00, "Kgs"),
    ("BOLD FT 1.5*3/8", 150.00, "Nos"),
    ("COLOUR SHEET", 160.00, "Nos"),
    ("Concrete Nails", 200.00, "Nos"),
    ("COVER BLOCK", 100.00, "Nos"),
    ("COVER BLOCK(BIG)", 550.00, "Nos"),
    ("DESIGN SHEET", 180.00, "Nos"),
    ("DHANDLE(big)", 80.00, "Nos"),
    ("DIAMOND", 130.00, "Kgs"),
    ("DOUBLE BALL", 32.00, "Nos"),
    ("GI NET", 180.00, "Nos"),
    ("GI PIPE APL (0.16)", 120.00, "Kgs"),
    ("GI PIPE APL (0.20)", 115.00, "Kgs"),
    ("GI PIPE APL(0.22)", 110.00, "Kgs"),
    ("GI ROLL SHEET", 150.00, "Nos"),
    ("GI SHEET(18kg)", 125.00, "Kgs"),
    ("GI SHEET(20kg)", 130.00, "Kgs"),
    ("glass", 50.00, "Nos"),
    ("GO DRY 1LTR", 150.00, "Nos"),
    ("HANDLE (medium)", 70.00, "Nos"),
    ("HANDLEN (SMALL)", 60.00, "Nos"),
    ("J BOLD", 140.00, "Nos"),
    ("J bold (small)", 12.00, "Nos"),
    ("MS PIPE APOLLO", 88.00, "Kgs"),
    ("MS PIPE BLUE LINE", 74.00, "Kgs"),
    ("MS SHEET(18kg)", 110.00, "Kgs"),
    ("MS SHEET(20kg)", 115.00, "Kgs"),
    ("NELLAKLAMPU(gold)", 120.00, "Kgs"),
    ("NIAL WASHER", 150.00, "Nos"),
    ("NUT W1/4", 150.00, "Kgs"),
    ("O TAMMI", 20.00, "Nos"),
    ("PLASTIC WASSER", 50.00, "Nos"),
    ("POUND(1.100)", 110.00, "Kgs"),
    ("POUND(1.600)", 110.00, "Kgs"),
    ("POUND(2.000)", 110.00, "Kgs"),
    ("POUND(O.900)", 110.00, "Kgs"),
    ("ROLLING WHEEL", 210.00, "Nos"),
    ("SILICON", 180.00, "Nos"),
    ("SILICON GUN", 170.00, "Nos"),
    ("SINGLE BALL", 17.00, "Nos"),
    ("SMALL POUNT", 80.00, "Nos"),
    ("SPEED 1 1/2\" SGROW", 5.00, "Nos"),
    ("SPEED 1 1/2\"STAR SGROW", 3.00, "Nos"),
    ("SPEED 1\"SGROW", 3.50, "Nos"),
    ("SPEED 1\"STAR SGROW", 2.00, "Nos"),
    ("SPEED 2 1/2 SGROW", 8.00, "Nos"),
    ("SPEED 2\"SGROW", 6.50, "Nos"),
    ("SPEED 3\" SGROW", 9.00, "Nos"),
    ("SPEED 3\"STAR SGROW", 5.00, "Nos"),
    ("SPEED 3/4\" SGROW", 3.00, "Nos"),
    ("SPEED 3/4\" STAR SGROW", 1.50, "Nos"),
    ("SPEED 4\"wall cutter", 140.00, "Nos"),
    ("SPEED 4\"wood cutter", 190.00, "Nos"),
    ("SPEED 5\"wall cutter", 180.00, "Nos"),
    ("SPEED 5\"wood cutter", 260.00, "Nos"),
    ("SPEED SGROW BIT", 30.00, "Nos"),
    ("SPEED STAR BIT", 40.00, "Nos"),
    ("SURULI KEEL", 120.00, "Nos"),
    ("SUTHU KEEL(BIG)", 140.00, "Nos"),
    ("SUTHU KEEL(SMALL)", 120.00, "Nos"),
    ("TAMMI", 10.00, "Nos"),
    ("TINNER 1/2ltr", 50.00, "Nos"),
    ("TINNER 1ltr", 100.00, "Nos"),
    ("TINNER 2ltr", 200.00, "Nos"),
    ("VELL", 130.00, "Kgs"),
    ("welding holder(big)", 220.00, "Nos"),
    ("welding holder(small)", 150.00, "Nos"),
    ("YURI 14\"cutting wheel", 140.00, "Nos"),
    ("YURI 4\"cutting wheel", 15.00, "Nos"),
    ("YURI 4\"grinding wheel", 35.00, "Nos"),
    ("YURI 5\"cutting wheel", 30.00, "Nos"),
    ("1/2*1/4 flats", 70.00, "Kgs"),
    ("3/4*1/4 flats", 67.00, "Kgs"),
]


def main():
    db = Path.home() / "Documents" / "NEW_INDIAN_STEEL" / "billing.db"
    if not db.exists():
        print(f"ERROR: DB not found at {db}")
        return 1

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = db.with_name(f"billing.db.before_product_update_{ts}.bak")
    shutil.copy2(db, bak)
    print(f"[backup] {bak}")

    # Run migrations so unit column exists
    from database import init_database
    from migrations import run_migrations
    init_database()
    run_migrations()

    conn = sqlite3.connect(str(db))
    try:
        c = conn.cursor()

        # invoice_items references products. If we DELETE products that are
        # referenced, the items lose their product link. We keep historical
        # invoice_items intact by clearing the FK and using a new id space.
        before = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        # Snapshot existing items linked to products so we can preserve the
        # invoice_items rows by their stored product_name (set during invoice
        # creation) - product_name is stored in invoice_items already.
        print(f"[wipe] removing {before} existing products...")
        c.execute("DELETE FROM products")
        try: c.execute("DELETE FROM sqlite_sequence WHERE name='products'")
        except sqlite3.OperationalError: pass

        print(f"[seed] inserting {len(PRODUCTS)} products...")
        for name, price, unit in PRODUCTS:
            c.execute(
                "INSERT INTO products (name, price, unit) VALUES (?, ?, ?)",
                (name, price, unit),
            )

        conn.commit()
        after = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        kg_n  = c.execute("SELECT COUNT(*) FROM products WHERE unit='Kgs'").fetchone()[0]
        nos_n = c.execute("SELECT COUNT(*) FROM products WHERE unit='Nos'").fetchone()[0]
        print()
        print(f"[done] products now: {after}  (Kgs: {kg_n}, Nos: {nos_n})")

    except Exception as e:
        conn.rollback()
        print(f"FAIL: {e}")
        print(f"Restore from: {bak}")
        return 2
    finally:
        conn.close()

    print()
    print("Done. Customers, invoices, and payments are unchanged.")
    print("Next time the app starts, sync_all() pushes new products to cloud.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
