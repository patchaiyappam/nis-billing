"""
WIPE_AND_RESEED.py - Reset for real-invoice mode
================================================

Wipes test data and replaces it with the real customer + product lists
exported from Khatabook on 15 May 2026:
  - 79 customers (with opening balances from Khatabook)
  - 197 products

What it deletes from the LOCAL SQLite DB
  ~/Documents/NEW_INDIAN_STEEL/billing.db
  - All rows from invoices, invoice_items, payments
  - All rows from customers, products
  - All rows from pending_syncs, background_tasks (queues)

What it creates
  - 79 customers, with opening_balance set to their Khatabook balance
    (Dr accounts only; the one Cr account is loaded as opening_balance=0
    and a separate payment row so its computed_due comes out negative.)
  - 197 products with current prices
  - A timestamped backup of your old DB next to it (just in case)

Safe to run multiple times; it always starts from a clean state.

Usage (on the shop PC):
    python WIPE_AND_RESEED.py
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# ============================================================
# CUSTOMER DATA  (Khatabook export, 15 May 2026)
#   (phone, name, opening_balance, kind)
#   kind: "Dr" = customer owes us; "Cr" = we owe customer
# ============================================================
CUSTOMERS = [
    ("9944020898", "Vetri Seruvai Velting",            61545.00, "Dr"),
    ("9655772030", "Elango",                            49735.00, "Dr"),
    ("9688776342", "Er.kannathasan",                    48532.00, "Dr"),
    ("9786057759", "Radhakrishnan Contractor",          43146.00, "Dr"),
    ("9176065355", "Karthi velting Tcbm",               42231.00, "Dr"),
    ("9443128620", "Panneerselvam Contractors",         40428.00, "Dr"),
    ("7639937939", "mogan son",                         40014.00, "Dr"),
    ("8667880788", "Kishore Manamudi Auto",             38712.00, "Dr"),
    ("9585684063", "Karikalan Rk Constructions",        31700.00, "Dr"),
    ("9943755084", "Natimuthu Canrecter",               29096.00, "Dr"),
    ("9677344821", "Dr.Stalin Tcbm",                    27080.00, "Dr"),
    ("7708540720", "Er Ramamoorthi",                    26250.00, "Dr"),
    ("7358475302", "Mathi Appa Kolaikkatu",             25298.00, "Dr"),
    ("7339556806", "Sakthivel Contrect",                23218.00, "Dr"),
    ("6383565127", "Jana Velting",                      22000.00, "Dr"),
    ("9715037108", "Maniyan Steel",                     21933.00, "Dr"),
    ("6382655245", "Divya MKP",                         20418.00, "Dr"),
    ("9944144568", "Er. China Mani",                    20190.00, "Dr"),
    ("7339605009", "Er.Varatharajan",                   19691.00, "Dr"),
    ("9751488173", "Mukkottukollai Alakar Arumuham",    17006.00, "Dr"),
    ("8122674768", "Er .Manikandan B",                  16207.00, "Dr"),
    ("8838608033", "Kumar Kurmpivayal",                 15500.00, "Dr"),
    ("9600045520", "Er. Lakshmanan",                    15000.00, "Dr"),
    ("9344986683", "Parthiban Welder",                  14197.00, "Dr"),
    ("9942087423", "Kannan Velting",                    13504.00, "Dr"),
    ("9047187656", "Pal Punalvasal",                    13044.00, "Dr"),
    ("9080133545", "AAA Welding",                       13042.00, "Dr"),
    ("9791468094", "Nagamuthu",                         12430.00, "Dr"),
    ("7812828343", "Suthagar Contracter",               12372.00, "Dr"),
    ("9042567353", "Mokan Thalaivar Tcbm",              11701.00, "Dr"),
    ("8667836711", "Er. Linfo Construction",            11439.00, "Dr"),
    ("9788861159", "Yovan",                              9740.00, "Dr"),
    ("9043490806", "Palanivel",                          9580.00, "Dr"),
    ("9047377281", "Rajenthiran Kvr",                    9381.00, "Dr"),
    ("8270659214", "E B Murugesan",                      9118.00, "Dr"),
    ("8940853649", "Nagoor Andavar Tcbm",                8769.00, "Dr"),
    ("8220080082", "Nathan Welding",                     8086.00, "Dr"),
    ("9087354583", "Raja kurupivayal",                   7901.00, "Dr"),
    ("8675409174", "Karthi kalathoor",                   7705.00, "Dr"),
    ("9176391170", "Jeyaprakash",                        7625.00, "Dr"),
    ("9787656243", "Saravanan",                          7222.00, "Dr"),
    ("9884000406", "Nvs Tcbm",                           6958.00, "Dr"),
    ("9942173372", "Alagar (kurumpivayal)",              6019.00, "Dr"),
    ("9842161886", "Madasamy",                           5742.00, "Dr"),
    ("8940425272", "Er. Mohamed Shrek Avanam",           5580.00, "Dr"),
    ("8248266871", "Mahendran Contrecter",               5558.00, "Dr"),
    ("8807344243", "Manikandan",                         4720.00, "Dr"),
    ("9500571794", "Vicky Contactor",                    4712.00, "Dr"),
    ("8015360927", "Kalathoor",                          4681.00, "Dr"),
    ("8681983713", "Sesu Raj 2",                         4648.00, "Dr"),
    ("9566469652", "Cinnu Flux",                         4616.00, "Dr"),
    ("9443265142", "Dakshinamoorthy Neduvai",            4558.00, "Dr"),
    ("9500452089", "Kavi Anna Palanimurugan",            4312.00, "Dr"),
    ("9443751984", "Pabu Anavayal",                      4087.00, "Dr"),
    ("9629572569", "Maheshwari Flower Tcbm",             3596.00, "Dr"),
    ("8220077587", "Saravanan Halo Block",               3544.00, "Dr"),
    ("9360706034", "Er.Laksmikanthan",                   3542.00, "Dr"),
    ("9790455895", "Vinayaga Computer",                  3370.00, "Dr"),
    ("9080828451", "Karthik Velting Kuruchi",            3337.00, "Dr"),
    ("9524247297", "Pothi kurumbivayal",                 3202.00, "Dr"),
    ("9047187641", "Baskar",                             3000.00, "Dr"),
    ("9751850234", "Kumar T.C.B.M",                      3000.00, "Dr"),
    ("7010583500", "senthil karukkakuruchi",             2912.00, "Dr"),
    ("9750814320", "Ayyappan Ayyappan",                  2566.00, "Dr"),
    ("7448585684", "Ayya Durai Karukka Kuruchi",         2425.00, "Dr"),
    ("6381940407", "Kumar welding",                      2406.00, "Dr"),
    ("9789667972", "Dinesh Amman Block",                 2402.00, "Dr"),
    ("9965183640", "Abdulla",                            2365.00, "Dr"),
    ("8072362600", "Bala Krishnan Welding",              2336.00, "Dr"),
    ("7094811061", "Senthil(auto)",                      1863.00, "Dr"),
    ("8524012341", "Vinoth Welding",                     1704.00, "Dr"),
    ("9095346019", "Amman Welding",                      1411.00, "Dr"),
    ("7200118288", "Kamaraj Contractor",                 1393.00, "Dr"),
    ("9677509185", "Ramesh nallandarkkollai",            1000.00, "Dr"),
    ("9944926092", "Raju Mesthiri",                       696.00, "Dr"),
    ("8056551763", "Apnathan",                            444.00, "Dr"),
    ("9626428176", "Thangam Palporul Angadi",             280.00, "Dr"),
    ("9003321220", "Selvaraj Kalathoor",                    3.00, "Dr"),
    ("9655961034", "Jj Traders",                        28850.00, "Cr"),
]

# ============================================================
# PRODUCT DATA
# ============================================================
PRODUCTS = [
    ("KING 4\"cutting wheel", 15.00),
    ("KING 4\"grinding wheel", 30.00),
    ("KING 4\"flappin disk", 35.00),
    ("KING 5\"cutting wheel", 35.00),
    ("KING 5\"cranting wheel", 50.00),
    ("KING 14\"cutting wheel", 150.00),
    ("YURI 4\"cutting wheel", 15.00),
    ("YURI 4\"grinding wheel", 35.00),
    ("YURI 5\"cutting wheel", 30.00),
    ("YURI 14\"cutting wheel", 140.00),
    ("SPEED 4\"wall cutter", 140.00),
    ("SPEED 5\"wall cutter", 180.00),
    ("SPEED 4\"wood cutter", 190.00),
    ("SPEED 5\"wood cutter", 260.00),
    ("SPEED 3/4\" SGROW", 3.00),
    ("SPEED 1\"SGROW", 3.50),
    ("SPEED 1 1/2\" SGROW", 5.00),
    ("SPEED 2\"SGROW", 6.50),
    ("SPEED 2 1/2 SGROW", 8.00),
    ("SPEED 3\" SGROW", 9.00),
    ("SPEED 3/4\" STAR SGROW", 1.50),
    ("SPEED 1\"STAR SGROW", 2.00),
    ("SPEED 1 1/2\"STAR SGROW", 3.00),
    ("SPEED 3\"STAR SGROW", 5.00),
    ("SPEED SGROW BIT", 30.00),
    ("STAR BIT", 40.00),
    ("2\"NAILS", 100.00),
    ("2 1/2\" NAILS", 100.00),
    ("3\" NAILS", 100.00),
    ("4\"NAILS", 100.00),
    ("5\"NAILS", 100.00),
    ("Concrete Nails", 200.00),
    ("1ltr PAINT", 350.00),
    ("1ltr YELLOW PRIMER", 300.00),
    ("1ltr RED OXIDE", 250.00),
    ("1/2ltr PAINT", 180.00),
    ("1/2ltr YELLOW PRIMER", 150.00),
    ("1/2ltr RED OXIDE", 130.00),
    ("TINNER 1/2ltr", 50.00),
    ("TINNER 1ltr", 100.00),
    ("TINNER 2ltr", 200.00),
    ("2\"PRUSH", 40.00),
    ("4\" ROLLING PRUSH", 140.00),
    ("3FT GREEN MESS", 12.00),
    ("4FT GREEN MESS", 12.00),
    ("5FT GREEN MESS", 12.00),
    ("SILICON", 180.00),
    ("SILICON GUN", 170.00),
    ("8MM LIVER", 90.00),
    ("10MM LIVER", 130.00),
    ("12MM LIVER", 150.00),
    ("16MM LIVER", 220.00),
    ("8MM BIN PLATE", 70.00),
    ("10MM BIN PLATE", 90.00),
    ("12MM BIN PLATE", 95.00),
    ("16MM BIN PLATE", 125.00),
    ("3/4\"O KEEL", 40.00),
    ("1\"O KEEL", 60.00),
    ("1 1/4\"O KEEL", 90.00),
    ("1 1/2\"O KEEL", 130.00),
    ("1\"SQ KEEL", 100.00),
    ("1 1/4\"SQ KEEL", 150.00),
    ("1 1/2\" SQ KEEL", 200.00),
    ("ALL PLATE", 100.00),
    ("TAMMI", 10.00),
    ("O TAMMI", 20.00),
    ("1KELD PIECE", 120.00),
    ("J BOLD", 140.00),
    ("BANTHAVALAIYAM", 120.00),
    ("PLASTIC WASSER", 50.00),
    ("1 1/2\"LORRY KELL", 30.00),
    ("2\" LORRY KELL", 40.00),
    ("SURULI KEEL", 120.00),
    ("SINGLE BALL", 17.00),
    ("DOUBLE BALL", 32.00),
    ("12MM PUSS", 10.00),
    ("16MM PUSH", 10.00),
    ("NUT W1/4", 150.00),
    ("DIAMOND", 130.00),
    ("VELL", 130.00),
    ("2 1/2\"SUN FLOWER", 150.00),
    ("6\" SUNFLOWER", 150.00),
    ("HANDLEN (SMALL)", 60.00),
    ("HANDLE (medium)", 70.00),
    ("DHANDLE(big)", 80.00),
    ("SUTHU KEEL(SMALL)", 120.00),
    ("SUTHU KEEL(BIG)", 140.00),
    ("glass", 50.00),
    ("SPEED ROLLING WHEEL", 210.00),
    ("1 1/2\" T BALL(Round)", 80.00),
    ("2\" T BALL (Round)", 90.00),
    ("NELLAKLAMPU(gold)", 120.00),
    ("5FT SADE NET", 350.00),
    ("10FT SADE NET", 350.00),
    ("SMALL POUNT", 80.00),
    ("POUND(O.900)", 110.00),
    ("POUND(1.100)", 110.00),
    ("POUND(1.600)", 110.00),
    ("POUND(2.000)", 110.00),
    ("2FT MANVETTI", 280.00),
    ("NIAL WASHER", 150.00),
    ("BOLD FT 1.5*3/8", 150.00),
    ("GI NET", 180.00),
    ("5MTR DAPE", 100.00),
    ("7.5MTR DAPE", 200.00),
    ("7.5MTR DAPE IKON", 240.00),
    ("15MTR DAPE", 170.00),
    ("30MTR TAPE", 270.00),
    ("welding holder(small)", 150.00),
    ("welding holder(big)", 220.00),
    ("16mm armer bit", 130.00),
    ("14mm armer bit", 120.00),
    ("10mm armer bit", 80.00),
    ("8mm armer bit", 70.00),
    ("12mm metal bit", 580.00),
    ("10mm metal bit", 400.00),
    ("8mm metal bit", 250.00),
    ("6mm metal bit", 150.00),
    ("1½\" T ball", 70.00),
    ("2\" T ball", 90.00),
    ("2½\" T ball", 100.00),
    ("1½\".sq T ball", 70.00),
    ("5FT Shade Net(50%)", 1050.00),
    ("10FT Shade Net(50%)", 2100.00),
    ("5FT Shade Net(75%)", 2000.00),
    ("10FT Shade Net(75%)", 3500.00),
    ("12MM Taver bold", 120.00),
    ("16MM Taver bold", 140.00),
    ("12MM THAPPA", 80.00),
    ("12MM THAPPA SET", 120.00),
    ("16MM THAPPA SET", 140.00),
    ("3FT Weld mess", 22.00),
    ("4FT Weld mess", 22.00),
    ("5FT Weld mess", 22.00),
    ("JSW 0.20MM 8FT GC SHEET", 500.00),
    ("JSW 0.20MM 10FT GC SHEET", 600.00),
    ("JSW 0.20MM 12FT GC SHEET", 700.00),
    ("JSW 0.25MM 8FT GC SHEET", 600.00),
    ("JSW 0.25MM 10FT GC SHEET", 700.00),
    ("JSW 0.25MM 12FT GC SHEET", 800.00),
    ("JSW 0.30MM 8FT GC SHEET", 700.00),
    ("JSW 0.30MM 10FT GC SHEET", 800.00),
    ("JSW 0.30MM 12FT GC SHEET", 900.00),
    ("6ft COLOUR SHEET TATA", 1200.00),
    ("9ft COLOUR SHEET TATA", 1800.00),
    ("10ft COLOUR SHEET TATA", 2000.00),
    ("11ft COLOUR SHEET TATA", 2200.00),
    ("12ft COLOUR SHEET TATA", 2400.00),
    ("14ft COLOUR SHEET TATA", 2800.00),
    ("15ft COLOUR SHEET TATA", 3000.00),
    ("16ft COLOUR SHEET TATA", 3200.00),
    ("17ft COLOUR SHEET TATA", 3400.00),
    ("18ft COLOUR SHEET TATA", 3600.00),
    ("19ft COLOUR SHEET TATA", 3800.00),
    ("20ft COLOUR SHEET TATA", 4000.00),
    ("21ft COLOUR SHEET TATA", 4200.00),
    ("22ft COLOUR SHEET TATA", 4400.00),
    ("23ft COLOUR SHEET TATA", 4600.00),
    ("24ft COLOUR SHEET TATA", 4800.00),
    ("6ft PENTCOLOUR SHEET TATA", 1260.00),
    ("8ft PENTCOLOUR SHEET TATA", 1680.00),
    ("10ft PENTCOLOUR SHEET TATA", 2100.00),
    ("12ft PENTCOLOUR SHEET TATA", 2520.00),
    ("14ft PENTCOLOUR SHEET TATA", 2940.00),
    ("16ft PENTCOLOUR SHEET TATA", 3360.00),
    ("18ft PENTCOLOUR SHEET TATA", 3780.00),
    ("20ft PENTCOLOUR SHEET TATA", 4200.00),
    ("22ft PENTCOLOUR SHEET TATA", 4620.00),
    ("24ft PENTCOLOUR SHEET TATA", 5040.00),
    ("10ft RIDGE SHEET TATA", 1500.00),
    ("6ft COLOUR SHEET JSW", 960.00),
    ("9ft COLOUR SHEET JSW", 1440.00),
    ("10ft COLOUR SHEET JSW", 1600.00),
    ("11ft COLOUR SHEET JSW", 1760.00),
    ("12ft COLOUR SHEET JSW", 1920.00),
    ("14ft COLOUR SHEET JSW", 2240.00),
    ("15ft COLOUR SHEET JSW", 2400.00),
    ("16ft COLOUR SHEET JSW", 2560.00),
    ("17ft COLOUR SHEET JSW", 2720.00),
    ("18ft COLOUR SHEET JSW", 2880.00),
    ("19ft COLOUR SHEET JSW", 3040.00),
    ("20ft COLOUR SHEET JSW", 3200.00),
    ("21ft COLOUR SHEET JSW", 3360.00),
    ("22ft COLOUR SHEET JSW", 3520.00),
    ("23ft COLOUR SHEET JSW", 3680.00),
    ("24ft COLOUR SHEET JSW", 3840.00),
    ("6ft PENTCOLOUR SHEET JSW", 1020.00),
    ("8ft PENTCOLOUR SHEET JSW", 1360.00),
    ("10ft PENTCOLOUR SHEET JSW", 1700.00),
    ("12ft PENTCOLOUR SHEET JSW", 2040.00),
    ("14ft PENTCOLOUR SHEET JSW", 2380.00),
    ("16ft PENTCOLOUR SHEET JSW", 2720.00),
    ("18ft PENTCOLOUR SHEET JSW", 3060.00),
    ("20ft PENTCOLOUR SHEET JSW", 3400.00),
    ("22ft PENTCOLOUR SHEET JSW", 3740.00),
    ("24ft PENTCOLOUR SHEET JSW", 4080.00),
    ("8ft RIDGE SHEETJSW", 800.00),
]


def main() -> int:
    db_path = Path.home() / "Documents" / "NEW_INDIAN_STEEL" / "billing.db"
    if not db_path.exists():
        print(f"ERROR: live DB not found at {db_path}")
        print("       Run the app once to initialize it, then re-run this.")
        return 1

    # ------------------------------------------------------------
    # Backup first
    # ------------------------------------------------------------
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = db_path.with_name(f"billing.db.before_reseed_{ts}.bak")
    shutil.copy2(db_path, backup)
    for ext in ("-wal", "-shm"):
        side = db_path.with_suffix(db_path.suffix + ext)
        if side.exists():
            shutil.copy2(side, backup.with_suffix(backup.suffix + ext))
    print(f"[backup] saved old DB to: {backup}")

    # ------------------------------------------------------------
    # Apply migrations first so the schema is current
    # ------------------------------------------------------------
    from database import init_database
    from migrations import run_migrations
    init_database()
    run_migrations()

    # ------------------------------------------------------------
    # Wipe + reseed in a single transaction
    # ------------------------------------------------------------
    conn = sqlite3.connect(str(db_path))
    try:
        c = conn.cursor()

        print("[wipe] clearing test data...")
        c.execute("DELETE FROM invoice_items")
        c.execute("DELETE FROM invoices")
        c.execute("DELETE FROM payments")
        c.execute("DELETE FROM customers")
        c.execute("DELETE FROM products")
        # Clear retry queues so nothing tries to re-sync the deleted rows
        try: c.execute("DELETE FROM pending_syncs")
        except sqlite3.OperationalError: pass
        try: c.execute("DELETE FROM background_tasks")
        except sqlite3.OperationalError: pass
        # Reset AUTOINCREMENT counters so IDs start at 1
        try: c.execute("DELETE FROM sqlite_sequence")
        except sqlite3.OperationalError: pass

        print(f"[seed] inserting {len(PRODUCTS)} products...")
        c.executemany(
            "INSERT INTO products (name, price) VALUES (?, ?)",
            PRODUCTS,
        )

        print(f"[seed] inserting {len(CUSTOMERS)} customers...")
        dr_count = cr_count = 0
        cr_payments = []   # list of (phone, amount) for Cr accounts
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for phone, name, balance, kind in CUSTOMERS:
            if kind == "Dr":
                # Customer owes us this amount
                c.execute(
                    "INSERT INTO customers (name, phone, address, opening_balance, total_due) "
                    "VALUES (?, ?, '', ?, ?)",
                    (name, phone, balance, balance),
                )
                dr_count += 1
            else:
                # We owe customer; store as a negative computed_due
                # via a payment row, with opening_balance=0.
                c.execute(
                    "INSERT INTO customers (name, phone, address, opening_balance, total_due) "
                    "VALUES (?, ?, '', 0, ?)",
                    (name, phone, -balance),
                )
                cr_payments.append((phone, balance))
                cr_count += 1

        for phone, amount in cr_payments:
            c.execute(
                "INSERT INTO payments (customer_phone, amount, date) VALUES (?, ?, ?)",
                (phone, amount, now),
            )

        conn.commit()
        print(f"[done] {dr_count} Dr customers, {cr_count} Cr customers, "
              f"{len(PRODUCTS)} products.")

        # ------------------------------------------------------------
        # Verify
        # ------------------------------------------------------------
        cust_n = c.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        prod_n = c.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        inv_n  = c.execute("SELECT COUNT(*) FROM invoices").fetchone()[0]
        sum_ob = c.execute(
            "SELECT COALESCE(SUM(opening_balance),0) FROM customers"
        ).fetchone()[0]
        sum_pay = c.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments"
        ).fetchone()[0]
        net_due = sum_ob - sum_pay
        print()
        print(f"[verify] customers   : {cust_n}")
        print(f"[verify] products    : {prod_n}")
        print(f"[verify] invoices    : {inv_n}  (should be 0)")
        print(f"[verify] sum opening : {sum_ob:>12,.2f}")
        print(f"[verify] sum payments: {sum_pay:>12,.2f}  (Cr balances)")
        print(f"[verify] net due     : {net_due:>12,.2f}  "
              f"(should be 971,924.00 per Khatabook)")

    except Exception as e:
        conn.rollback()
        print(f"FAIL: {e}")
        print(f"Old DB still safe at: {backup}")
        return 2
    finally:
        conn.close()

    print()
    print("Reseed complete. Next time the app opens, sync_all() will push")
    print("the fresh data to Supabase automatically.")
    print()
    print(f"If something looks wrong, restore the backup:")
    print(f"  copy /Y \"{backup}\" \"{db_path}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
