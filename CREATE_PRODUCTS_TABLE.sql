-- ============================================================
-- Run this once in your Supabase dashboard:
-- https://supabase.com/dashboard/project/agffhjgutddcxvrluysv/sql/new
-- ============================================================

CREATE TABLE IF NOT EXISTS products (
    id         BIGINT PRIMARY KEY,
    name       TEXT   NOT NULL,
    price      NUMERIC(12,2) NOT NULL DEFAULT 0,
    unit       TEXT   NOT NULL DEFAULT 'Nos',
    updated_at TIMESTAMPTZ
);

-- Row Level Security (same as customers/invoices/payments tables)
ALTER TABLE products ENABLE ROW LEVEL SECURITY;

CREATE POLICY IF NOT EXISTS "Allow anon select" ON products FOR SELECT USING (true);
CREATE POLICY IF NOT EXISTS "Allow anon insert" ON products FOR INSERT WITH CHECK (true);
CREATE POLICY IF NOT EXISTS "Allow anon update" ON products FOR UPDATE USING (true);
CREATE POLICY IF NOT EXISTS "Allow anon delete" ON products FOR DELETE USING (true);
