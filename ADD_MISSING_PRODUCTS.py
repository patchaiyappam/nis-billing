"""
ADD_MISSING_PRODUCTS.py
Run this once to add the 65 missing products from your price list CSV.
Close the billing app first, then double-click this file.
"""
import sqlite3, os, sys

DB = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL", "billing.db")

NEW_PRODUCTS = [
    # Missing thappa
    ('16MM THAPPA', 10.0),
    # TMT Steel - TATA
    ('16MM TMT TATA', 1624.0), ('12MM TMT TATA', 913.0), ('10MM TMT TATA', 646.0),
    ('8MM TMT TATA', 423.0),   ('6MM TMT TATA', 247.0),
    # TMT Steel - JSW
    ('16MM TMT JSW', 79.0), ('12MM TMT JSW', 79.0),
    ('10MM TMT JSW', 82.0), ('8MM TMT JSW', 83.0),
    # TMT Steel - PULKIT
    ('16MM TMT PULKIT', 72.0), ('12MM TMT PILKIT', 72.0),
    ('10MM TMT PULKIT', 72.0), ('8MM TMT PULKIT', 73.0),
    # Pipes
    ('MS PIPE APOLLO', 88.0), ('GI PIPE APL (0.16)', 120.0),
    ('GI PIPE APL (0.20)', 115.0), ('GI PIPE APL(0.22)', 110.0),
    ('MS PIPE BLUE LINE', 74.0),
    # L Angles (price per kg)
    ('1*¼ L angle', 67.0), ('1½* ¼L angle', 67.0),
    ('2*¼ L angle', 67.0), ('2½*¼L angle', 67.0),
    ('1*⅛L angle', 70.0),  ('1¼*⅛ L angle', 67.0),
    # Flats (price per kg)
    ('¾*¼ flats', 67.0), ('1*¼ flats', 67.0),
    ('1¼*¼ flats', 67.0), ('1½*¼ flats', 67.0),
    ('2*¼ flats', 67.0), ('1*⅛ flats', 70.0),
    ('½*¼ flats', 70.0), ('1½*½ flats', 70.0),
    # Welding electrodes
    ('Best Arc(10kg)', 380.0), ('Best Arc(12kg)', 420.0),
    # Wire
    ('Binding wire', 110.0), ('10KG GI WIRE', 100.0), ('12KG GI WIRE', 100.0),
    ('16KG GI WIRE', 130.0), ('18KG GI WIRE', 130.0),
    ('5FT FENCING', 95.0), ('BARBET WIRE', 95.0),
    # Metal sheets (price per kg)
    ('MS SHEET(18kg)', 110.0), ('MS SHEET(20kg)', 115.0),
    ('GI SHEET(18kg)', 125.0), ('GI SHEET(20kg)', 130.0),
    ('GI ROLL SHEET', 150.0), ('DESIGN SHEET', 180.0),
    # Cover blocks
    ('COVER BLOCK', 100.0), ('COVER BLOCK(BIG)', 550.0),
    # Keld pieces & Bold nets
    ('1½" keld piece', 15.0), ('2" keld piece', 20.0),
    ('1½" Bold Net', 10.0), ('2" bold net', 10.0),
    ('2½" bold net', 10.0), ('3" bold net', 10.0),
    # AC Sheets
    ('6FT AC SHEET', 450.0), ('8FT AC SHEET', 540.0),
    ('10FT AC SHEET', 640.0), ('12FT AC SHEET', 880.0),
    # Steel rods
    ('13MM BALISH ROD', 71.0), ('13MM SQ ROD', 67.0),
    ('10MM SQ ROD', 68.0), ('12 ROUND ROD', 68.0), ('16 ROUND ROD', 68.0),
]

try:
    con = sqlite3.connect(DB)
    existing = {r[0].lower() for r in con.execute("SELECT name FROM products").fetchall()}
    to_insert = [(n, p) for n, p in NEW_PRODUCTS if n.lower() not in existing]

    if not to_insert:
        print("All products already exist. Nothing to add.")
    else:
        con.executemany("INSERT INTO products (name, price) VALUES (?, ?)", to_insert)
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        print(f"SUCCESS: Added {len(to_insert)} products. Total now: {total}")
        for n, p in to_insert:
            print(f"  + {n}  Rs.{p}")
    con.close()
    input("\nPress Enter to exit...")
except Exception as e:
    print(f"ERROR: {e}")
    input("\nPress Enter to exit...")
    sys.exit(1)
