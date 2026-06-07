-- =============================================================
-- Supabase PostgreSQL — NEW INDIAN STEEL Cloud Tables
-- =============================================================
-- Run this entire file in the Supabase Dashboard:
--   Project → SQL Editor → New Query → Paste → Run
--
-- These tables mirror the SQLite schema and add a  pdf_url  column
-- for the Supabase Storage download link.
-- =============================================================


-- ── customers ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS customers (
    id        TEXT PRIMARY KEY,   -- matches SQLite INTEGER id (stored as text)
    phone     TEXT NOT NULL,
    name      TEXT NOT NULL,
    address   TEXT DEFAULT '',
    total_due NUMERIC DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── invoices ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invoices (
    id               TEXT PRIMARY KEY,
    customer_phone   TEXT NOT NULL,
    customer_name    TEXT NOT NULL,
    total            NUMERIC DEFAULT 0,
    paid             NUMERIC DEFAULT 0,
    balance          NUMERIC DEFAULT 0,
    type             TEXT DEFAULT 'invoice',
    date             TEXT,
    pdf_url          TEXT DEFAULT '',      -- Supabase Storage public URL
    pdf_filename     TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── invoice_items ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS invoice_items (
    id           BIGSERIAL PRIMARY KEY,
    invoice_id   TEXT REFERENCES invoices(id) ON DELETE CASCADE,
    product_name TEXT NOT NULL,
    qty          NUMERIC DEFAULT 0,
    price        NUMERIC DEFAULT 0,
    amount       NUMERIC DEFAULT 0,
    UNIQUE (invoice_id, product_name)
);

-- ── payments ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS payments (
    id               TEXT PRIMARY KEY,
    customer_phone   TEXT NOT NULL,
    amount           NUMERIC DEFAULT 0,
    date             TEXT,
    note             TEXT DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ── statements ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS statements (
    id           BIGSERIAL PRIMARY KEY,
    customer_phone TEXT NOT NULL,
    pdf_url      TEXT DEFAULT '',
    pdf_filename TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── daily_reports ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_reports (
    id           BIGSERIAL PRIMARY KEY,
    report_date  TEXT NOT NULL,
    pdf_url      TEXT DEFAULT '',
    pdf_filename TEXT DEFAULT '',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);


-- =============================================================
-- Row Level Security (optional but recommended)
-- Run AFTER creating tables if you want per-user isolation.
-- For a single-shop app, you can leave RLS disabled and use the
-- anon key — just keep it private.
-- =============================================================

-- ALTER TABLE customers   ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE invoices    ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE invoice_items ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE payments    ENABLE ROW LEVEL SECURITY;

-- Example open policy (allows all operations from your service key):
-- CREATE POLICY "allow_all" ON customers FOR ALL USING (true);
-- (Repeat for each table)
