"""
UPDATE_PRICES.py — Bulk price update from your latest price list CSV
=====================================================================
NEW INDIAN STEEL Billing System

Reads your price list and:
  1. Updates the price (and unit) for every EXISTING product that matches by name
  2. ADDS any brand-new products not yet in the database
  3. Prints a full report: updated / added / skipped

Run once from the NIS_final folder:
    python UPDATE_PRICES.py

Safe to re-run — uses UPDATE or INSERT, never deletes anything.
"""

import sqlite3
import os
import sys
from datetime import datetime, timezone

# ── DB path ──────────────────────────────────────────────
BASE_DIR = os.path.join(os.path.expanduser("~"), "Documents", "NEW_INDIAN_STEEL")
DB_PATH  = os.path.join(BASE_DIR, "billing.db")

# ══════════════════════════════════════════════════════════
# PRICE LIST  — extracted from your CSV
# Format: (product_name, sale_price, unit)
# unit: "Nos" = per piece/set | "Kgs" = per kilogram
# ══════════════════════════════════════════════════════════

PRICE_LIST = [
    # ── ABRASIVE WHEELS (KING brand) ──────────────────────
    ('4" cutting wheel (King)',         15,     'Nos'),
    ('4" grinding wheel (King)',        30,     'Nos'),
    ('4" flappin disk (King)',          35,     'Nos'),
    ('5" cutting wheel (King)',         35,     'Nos'),
    ('5" cranting wheel (King)',        50,     'Nos'),
    ('14" cutting wheel (King)',        150,    'Nos'),
    # ── ABRASIVE WHEELS (YURI brand) ──────────────────────
    ('4" cutting wheel (Yuri)',         15,     'Nos'),
    ('4" grinding wheel (Yuri)',        35,     'Nos'),
    ('5" cutting wheel (Yuri)',         30,     'Nos'),
    ('14" cutting wheel (Yuri)',        140,    'Nos'),
    # ── ABRASIVE WHEELS (SPEED brand) ─────────────────────
    ('4" wall cutter',                  140,    'Nos'),
    ('5" wall cutter',                  180,    'Nos'),
    ('4" wood cutter',                  190,    'Nos'),
    ('5" wood cutter',                  260,    'Nos'),
    # ── SCREW (SGROW) ─────────────────────────────────────
    ('3/4" SGROW',                      3,      'Nos'),
    ('1" SGROW',                        3.5,    'Nos'),
    ('1 1/2" SGROW',                    5,      'Nos'),
    ('2" SGROW',                        6.5,    'Nos'),
    ('2 1/2" SGROW',                    8,      'Nos'),
    ('3" SGROW',                        9,      'Nos'),
    ('3/4" STAR SGROW',                 1.5,    'Nos'),
    ('1" STAR SGROW',                   2,      'Nos'),
    ('1 1/2" STAR SGROW',               3,      'Nos'),
    ('3" STAR SGROW',                   5,      'Nos'),
    ('SGROW BIT',                       30,     'Nos'),
    ('STAR BIT',                        40,     'Nos'),
    # ── NAILS ─────────────────────────────────────────────
    ('2" NAILS',                        100,    'Kgs'),
    ('2 1/2" NAILS',                    100,    'Kgs'),
    ('3" NAILS',                        100,    'Kgs'),
    ('4" NAILS',                        100,    'Kgs'),
    ('5" NAILS',                        100,    'Kgs'),
    ('Concrete Nails',                  200,    'Kgs'),
    # ── PAINT (INDICUS) ───────────────────────────────────
    ('1ltr PAINT',                      350,    'Nos'),
    ('1ltr YELLOW PRIMER',              300,    'Nos'),
    ('1ltr RED OXIDE',                  250,    'Nos'),
    ('1/2ltr PAINT',                    180,    'Nos'),
    ('1/2ltr YELLOW PRIMER',            150,    'Nos'),
    ('1/2ltr RED OXIDE',                130,    'Nos'),
    ('TINNER 1/2ltr',                   50,     'Nos'),
    ('TINNER 1ltr',                     100,    'Nos'),
    ('TINNER 2ltr',                     200,    'Nos'),
    ('2" BRUSH',                        40,     'Nos'),
    ('4" ROLLING BRUSH',                140,    'Nos'),
    ('4" ROLLING SPONGE',               35,     'Nos'),
    # ── MESH / NET ────────────────────────────────────────
    ('3FT GREEN MESH',                  12,     'Nos'),
    ('4FT GREEN MESH',                  12,     'Nos'),
    ('5FT GREEN MESH',                  12,     'Nos'),
    ('SILICON',                         180,    'Nos'),
    ('SILICON GUN',                     170,    'Nos'),
    # ── FLAT BARS / LIVERS ────────────────────────────────
    ('8MM FLAT BAR',                    90,     'Kgs'),
    ('10MM FLAT BAR',                   130,    'Kgs'),
    ('12MM FLAT BAR',                   150,    'Kgs'),
    ('16MM FLAT BAR',                   220,    'Kgs'),
    # ── BIN PLATE ─────────────────────────────────────────
    ('8MM BIN PLATE',                   70,     'Nos'),
    ('10MM BIN PLATE',                  90,     'Nos'),
    ('12MM BIN PLATE',                  95,     'Nos'),
    ('16MM BIN PLATE',                  125,    'Nos'),
    # ── HOLLOW SECTION (KEEL) ─────────────────────────────
    ('3/4" O KEEL',                     40,     'Nos'),
    ('1" O KEEL',                       60,     'Nos'),
    ('1 1/4" O KEEL',                   90,     'Nos'),
    ('1 1/2" O KEEL',                   130,    'Nos'),
    ('1" SQ KEEL',                      100,    'Nos'),
    ('1 1/4" SQ KEEL',                  150,    'Nos'),
    ('1 1/2" SQ KEEL',                  200,    'Nos'),
    # ── MISCELLANEOUS HARDWARE ────────────────────────────
    ('ALL PLATE',                       100,    'Nos'),
    ('TAMMI',                           10,     'Nos'),
    ('O TAMMI',                         20,     'Nos'),
    ('1" KELD PIECE',                   120,    'Nos'),
    ('J BOLT',                          140,    'Nos'),
    ('BANTHAVALAIYAM',                  120,    'Nos'),
    ('PLASTIC WASHER',                  50,     'Nos'),
    ('1 1/2" LORRY KEEL',               30,     'Nos'),
    ('2" LORRY KEEL',                   40,     'Nos'),
    ('SURULI KEEL',                     120,    'Kgs'),
    ('SINGLE BALL',                     17,     'Nos'),
    ('DOUBLE BALL',                     32,     'Nos'),
    ('12MM PUSS',                       10,     'Nos'),
    ('16MM PUSH',                       10,     'Nos'),
    ('NUT W 1/4',                       150,    'Kgs'),
    ('DIAMOND',                         130,    'Kgs'),
    ('VELL',                            130,    'Kgs'),
    ('2 1/2" SUNFLOWER',                150,    'Kgs'),
    ('6" SUNFLOWER',                    150,    'Kgs'),
    ('HANDLE (SMALL)',                  60,     'Nos'),
    ('HANDLE (MEDIUM)',                 70,     'Nos'),
    ('HANDLE (BIG)',                    80,     'Nos'),
    ('SUTHU KEEL (SMALL)',              120,    'Kgs'),
    ('SUTHU KEEL (BIG)',                140,    'Kgs'),
    ('GLASS',                           50,     'Nos'),
    ('ROLLING WHEEL',                   210,    'Nos'),
    ('1 1/2" T BALL (ROUND)',           80,     'Nos'),
    ('2" T BALL (ROUND)',               90,     'Nos'),
    ('NELLAKLAMPU (GOLD)',              120,    'Kgs'),
    ('5FT SHADE NET',                   350,    'Kgs'),
    ('10FT SHADE NET',                  350,    'Kgs'),
    ('SMALL POUND',                     80,     'Nos'),
    ('POUND 0.900',                     110,    'Kgs'),
    ('POUND 1.100',                     110,    'Kgs'),
    ('POUND 1.600',                     110,    'Kgs'),
    ('POUND 2.000',                     110,    'Kgs'),
    ('2FT MANVETTI',                    280,    'Nos'),
    ('NAIL WASHER',                     150,    'Nos'),
    ('BOLT FT 1.5*3/8',                 150,    'Nos'),
    ('GI NET',                          180,    'Nos'),
    ('5MTR TAPE',                       100,    'Nos'),
    ('7.5MTR TAPE',                     200,    'Nos'),
    ('7.5MTR TAPE IKON',                240,    'Nos'),
    ('15MTR TAPE',                      170,    'Nos'),
    ('30MTR TAPE',                      270,    'Nos'),
    ('WELDING HOLDER (SMALL)',          150,    'Nos'),
    ('WELDING HOLDER (BIG)',            220,    'Nos'),
    # ── DRILL BITS ────────────────────────────────────────
    ('16MM ARMER BIT',                  130,    'Nos'),
    ('14MM ARMER BIT',                  120,    'Nos'),
    ('10MM ARMER BIT',                  80,     'Nos'),
    ('8MM ARMER BIT',                   70,     'Nos'),
    ('12MM METAL BIT',                  580,    'Nos'),
    ('10MM METAL BIT',                  400,    'Nos'),
    ('8MM METAL BIT',                   250,    'Nos'),
    ('6MM METAL BIT',                   150,    'Nos'),
    # ── T BALLS ───────────────────────────────────────────
    ('1 1/2" T BALL',                   70,     'Nos'),
    ('2" T BALL',                       90,     'Nos'),
    ('2 1/2" T BALL',                   100,    'Nos'),
    ('1 1/2" SQ T BALL',                70,     'Nos'),
    # ── SHADE NET ─────────────────────────────────────────
    ('5FT SHADE NET (50%)',             1050,   'Nos'),
    ('10FT SHADE NET (50%)',            2100,   'Nos'),
    ('5FT SHADE NET (75%)',             2000,   'Nos'),
    ('10FT SHADE NET (75%)',            3500,   'Nos'),
    # ── TAVER BOLD / THAPPA ───────────────────────────────
    ('12MM TAVER BOLT',                 120,    'Nos'),
    ('16MM TAVER BOLT',                 140,    'Nos'),
    ('12MM THAPPA',                     80,     'Nos'),
    ('16MM THAPPA',                     10,     'Nos'),
    ('12MM THAPPA SET',                 120,    'Nos'),
    ('16MM THAPPA SET',                 140,    'Nos'),
    # ── WELD MESH ─────────────────────────────────────────
    ('3FT WELD MESH',                   22,     'Nos'),
    ('4FT WELD MESH',                   22,     'Nos'),
    ('5FT WELD MESH',                   22,     'Nos'),
    # ── GC SHEETS (JSW 0.20MM) ────────────────────────────
    ('8FT GC SHEET (JSW 0.20MM)',       500,    'Nos'),
    ('10FT GC SHEET (JSW 0.20MM)',      600,    'Nos'),
    ('12FT GC SHEET (JSW 0.20MM)',      700,    'Nos'),
    # ── GC SHEETS (JSW 0.25MM) ────────────────────────────
    ('8FT GC SHEET (JSW 0.25MM)',       600,    'Nos'),
    ('10FT GC SHEET (JSW 0.25MM)',      700,    'Nos'),
    ('12FT GC SHEET (JSW 0.25MM)',      800,    'Nos'),
    # ── GC SHEETS (JSW 0.30MM) ────────────────────────────
    ('8FT GC SHEET (JSW 0.30MM)',       700,    'Nos'),
    ('10FT GC SHEET (JSW 0.30MM)',      800,    'Nos'),
    ('12FT GC SHEET (JSW 0.30MM)',      900,    'Nos'),
    # ── TMT BARS (TATA) ───────────────────────────────────
    ('6MM TMT TATA',                    247,    'Kgs'),
    ('8MM TMT TATA',                    423,    'Kgs'),
    ('10MM TMT TATA',                   646,    'Kgs'),
    ('12MM TMT TATA',                   913,    'Kgs'),
    ('16MM TMT TATA',                   1624,   'Kgs'),
    # ── TMT BARS (JSW) ────────────────────────────────────
    ('8MM TMT JSW',                     83,     'Kgs'),
    ('10MM TMT JSW',                    82,     'Kgs'),
    ('12MM TMT JSW',                    79,     'Kgs'),
    ('16MM TMT JSW',                    79,     'Kgs'),
    # ── TMT BARS (PULKIT) ─────────────────────────────────
    ('8MM TMT PULKIT',                  73,     'Kgs'),
    ('10MM TMT PULKIT',                 72,     'Kgs'),
    ('12MM TMT PULKIT',                 72,     'Kgs'),
    ('16MM TMT PULKIT',                 72,     'Kgs'),
    # ── PIPES ─────────────────────────────────────────────
    ('MS PIPE APOLLO',                  88,     'Kgs'),
    ('GI PIPE APL (0.16)',               120,    'Kgs'),
    ('GI PIPE APL (0.20)',               115,    'Kgs'),
    ('GI PIPE APL (0.22)',               110,    'Kgs'),
    ('MS PIPE BLUE LINE',               74,     'Kgs'),
    # ── ANGLE / FLAT SECTIONS ─────────────────────────────
    ('1" x 1/4" L ANGLE',              67,     'Kgs'),
    ('1 1/2" x 1/4" L ANGLE',          67,     'Kgs'),
    ('2" x 1/4" L ANGLE',              67,     'Kgs'),
    ('2 1/2" x 1/4" L ANGLE',          67,     'Kgs'),
    ('1" x 1/8" L ANGLE',              70,     'Kgs'),
    ('1 1/4" x 1/8" L ANGLE',          67,     'Kgs'),
    ('3/4" x 1/4" FLAT',               67,     'Kgs'),
    ('1" x 1/4" FLAT',                 67,     'Kgs'),
    ('1 1/4" x 1/4" FLAT',             67,     'Kgs'),
    ('1 1/2" x 1/4" FLAT',             67,     'Kgs'),
    ('2" x 1/4" FLAT',                 67,     'Kgs'),
    ('1" x 1/8" FLAT',                 70,     'Kgs'),
    ('1/2" x 1/4" FLAT',               70,     'Kgs'),
    ('1 1/2" x 1/2" FLAT',             70,     'Kgs'),
    # ── ELECTRODES / WIRE ─────────────────────────────────
    ('BEST ARC ELECTRODE 10KG',         380,    'Nos'),
    ('BEST ARC ELECTRODE 12KG',         420,    'Nos'),
    ('BINDING WIRE',                    110,    'Kgs'),
    ('10KG GI WIRE',                    100,    'Kgs'),
    ('12KG GI WIRE',                    100,    'Kgs'),
    ('16KG GI WIRE',                    130,    'Kgs'),
    ('18KG GI WIRE',                    130,    'Kgs'),
    ('5FT FENCING WIRE',                95,     'Kgs'),
    ('BARBED WIRE',                     95,     'Kgs'),
    # ── SHEETS (MS / GI) ──────────────────────────────────
    ('MS SHEET (18KG)',                 110,    'Kgs'),
    ('MS SHEET (20KG)',                 115,    'Kgs'),
    ('GI SHEET (18KG)',                 125,    'Kgs'),
    ('GI SHEET (20KG)',                 130,    'Kgs'),
    # ── MISC CONSTRUCTION ─────────────────────────────────
    ('COVER BLOCK',                     100,    'Nos'),
    ('COVER BLOCK (BIG)',               550,    'Nos'),
    ('GI ROLL SHEET',                   150,    'Kgs'),
    ('COLOUR SHEET',                    160,    'Kgs'),
    ('DESIGN SHEET',                    180,    'Kgs'),
    ('GO DRY 1LTR',                     150,    'Nos'),
    ('J BOLT (SMALL)',                  12,     'Nos'),
    ('TINNER (1LTR)',                   100,    'Nos'),
    ('TINNER (1/2LTR)',                 50,     'Nos'),
    ('1 1/2" KELD PIECE',               15,     'Nos'),
    ('2" KELD PIECE',                   20,     'Nos'),
    ('1 1/2" BOLD NET',                 10,     'Nos'),
    ('2" BOLD NET',                     10,     'Nos'),
    ('2 1/2" BOLD NET',                 10,     'Nos'),
    ('3" BOLD NET',                     10,     'Nos'),
    # ── AC SHEETS ─────────────────────────────────────────
    ('6FT AC SHEET',                    450,    'Nos'),
    ('8FT AC SHEET',                    540,    'Nos'),
    ('10FT AC SHEET',                   640,    'Nos'),
    ('12FT AC SHEET',                   880,    'Nos'),
    # ── RODS ──────────────────────────────────────────────
    ('13MM ROUND ROD',                  71,     'Kgs'),
    ('13MM SQ ROD',                     67,     'Kgs'),
    ('10MM SQ ROD',                     68,     'Kgs'),
    ('12MM ROUND ROD',                  68,     'Kgs'),
    ('16MM ROUND ROD',                  68,     'Kgs'),
    # ── COLOUR SHEETS (TATA) ──────────────────────────────
    ('6FT COLOUR SHEET TATA',           1200,   'Nos'),
    ('9FT COLOUR SHEET TATA',           1800,   'Nos'),
    ('10FT COLOUR SHEET TATA',          2000,   'Nos'),
    ('11FT COLOUR SHEET TATA',          2200,   'Nos'),
    ('12FT COLOUR SHEET TATA',          2400,   'Nos'),
    ('14FT COLOUR SHEET TATA',          2800,   'Nos'),
    ('15FT COLOUR SHEET TATA',          3000,   'Nos'),
    ('16FT COLOUR SHEET TATA',          3200,   'Nos'),
    ('17FT COLOUR SHEET TATA',          3400,   'Nos'),
    ('18FT COLOUR SHEET TATA',          3600,   'Nos'),
    ('19FT COLOUR SHEET TATA',          3800,   'Nos'),
    ('20FT COLOUR SHEET TATA',          4000,   'Nos'),
    ('21FT COLOUR SHEET TATA',          4200,   'Nos'),
    ('22FT COLOUR SHEET TATA',          4400,   'Nos'),
    ('23FT COLOUR SHEET TATA',          4600,   'Nos'),
    ('24FT COLOUR SHEET TATA',          4800,   'Nos'),
    ('6FT PENT COLOUR SHEET TATA',      1260,   'Nos'),
    ('8FT PENT COLOUR SHEET TATA',      1680,   'Nos'),
    ('10FT PENT COLOUR SHEET TATA',     2100,   'Nos'),
    ('12FT PENT COLOUR SHEET TATA',     2520,   'Nos'),
    ('14FT PENT COLOUR SHEET TATA',     2940,   'Nos'),
    ('16FT PENT COLOUR SHEET TATA',     3360,   'Nos'),
    ('18FT PENT COLOUR SHEET TATA',     3780,   'Nos'),
    ('20FT PENT COLOUR SHEET TATA',     4200,   'Nos'),
    ('22FT PENT COLOUR SHEET TATA',     4620,   'Nos'),
    ('24FT PENT COLOUR SHEET TATA',     5040,   'Nos'),
    ('10FT RIDGE SHEET TATA',           1500,   'Nos'),
    # ── COLOUR SHEETS (JSW) ───────────────────────────────
    ('6FT COLOUR SHEET JSW',            960,    'Nos'),
    ('9FT COLOUR SHEET JSW',            1440,   'Nos'),
    ('10FT COLOUR SHEET JSW',           1600,   'Nos'),
    ('11FT COLOUR SHEET JSW',           1760,   'Nos'),
    ('12FT COLOUR SHEET JSW',           1920,   'Nos'),
    ('14FT COLOUR SHEET JSW',           2240,   'Nos'),
    ('15FT COLOUR SHEET JSW',           2400,   'Nos'),
    ('16FT COLOUR SHEET JSW',           2560,   'Nos'),
    ('17FT COLOUR SHEET JSW',           2720,   'Nos'),
    ('18FT COLOUR SHEET JSW',           2880,   'Nos'),
    ('19FT COLOUR SHEET JSW',           3040,   'Nos'),
    ('20FT COLOUR SHEET JSW',           3200,   'Nos'),
    ('21FT COLOUR SHEET JSW',           3360,   'Nos'),
    ('22FT COLOUR SHEET JSW',           3520,   'Nos'),
    ('23FT COLOUR SHEET JSW',           3680,   'Nos'),
    ('24FT COLOUR SHEET JSW',           3840,   'Nos'),
    ('6FT PENT COLOUR SHEET JSW',       1020,   'Nos'),
    ('8FT PENT COLOUR SHEET JSW',       1360,   'Nos'),
    ('10FT PENT COLOUR SHEET JSW',      1700,   'Nos'),
    ('12FT PENT COLOUR SHEET JSW',      2040,   'Nos'),
    ('14FT PENT COLOUR SHEET JSW',      2380,   'Nos'),
    ('16FT PENT COLOUR SHEET JSW',      2720,   'Nos'),
    ('18FT PENT COLOUR SHEET JSW',      3060,   'Nos'),
    ('20FT PENT COLOUR SHEET JSW',      3400,   'Nos'),
    ('22FT PENT COLOUR SHEET JSW',      3740,   'Nos'),
    ('24FT PENT COLOUR SHEET JSW',      4080,   'Nos'),
    ('8FT RIDGE SHEET JSW',             800,    'Nos'),
]


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════

def _norm(name: str) -> str:
    """Normalise name for fuzzy matching: uppercase, collapse spaces, strip punctuation."""
    import re
    n = name.upper().strip()
    n = re.sub(r'["\']', '', n)      # remove quotes
    n = re.sub(r'\s+', ' ', n)       # collapse whitespace
    return n


def _get_conn():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ══════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════

def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: Database not found at {DB_PATH}")
        print("       Make sure you run this on a PC where the app has been set up.")
        sys.exit(1)

    conn = _get_conn()
    now  = datetime.now(timezone.utc).isoformat()

    # Load existing products (id, name) for matching
    existing = {_norm(r["name"]): r["id"]
                for r in conn.execute("SELECT id, name FROM products")}

    updated  = []
    added    = []
    skipped  = []

    try:
        for name, price, unit in PRICE_LIST:
            key = _norm(name)
            if key in existing:
                # Update price, unit, updated_at
                conn.execute(
                    "UPDATE products SET price=?, unit=?, updated_at=? WHERE id=?",
                    (float(price), unit, now, existing[key])
                )
                updated.append((existing[key], name, price, unit))
            else:
                # Add as new product
                conn.execute(
                    "INSERT INTO products (name, price, unit, updated_at) VALUES (?,?,?,?)",
                    (name, float(price), unit, now)
                )
                added.append((name, price, unit))

        conn.commit()
        print()
        print("=" * 60)
        print("  NEW INDIAN STEEL — Price Update Complete")
        print("=" * 60)
        print(f"\n  ✅  Updated  : {len(updated):>4} existing products")
        print(f"  ➕  Added    : {len(added):>4} new products")
        print()

        if updated:
            print("─" * 60)
            print("  UPDATED PRODUCTS:")
            print("─" * 60)
            for pid, name, price, unit in updated:
                print(f"  [{pid:>4}] {name:<45} ₹{price:>8.2f} / {unit}")

        if added:
            print()
            print("─" * 60)
            print("  NEW PRODUCTS ADDED:")
            print("─" * 60)
            for name, price, unit in added:
                print(f"  {'[NEW]':>6} {name:<45} ₹{price:>8.2f} / {unit}")

        print()
        print("  ℹ  Restart the billing app on BOTH PCs to see the changes.")
        print("     The admin laptop will push the updates to the shop PC")
        print("     automatically within 30 seconds via cloud sync.")
        print()
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
