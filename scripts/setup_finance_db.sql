-- ==============================================================================
-- ZERO — Personal Finance Tracker Database Setup Script
-- ==============================================================================
-- Purpose: Creates a strictly READ-ONLY PostgreSQL role for ZERO to inspect
-- spending and transactions without write, update, or drop permissions.
--
-- Run this against your Postgres database backing the n8n Finance Tracker:
--   psql -U postgres -d <your_finance_db> -f scripts/setup_finance_db.sql
-- ==============================================================================

-- 1. Create dedicated read-only role with password
CREATE ROLE zero_finance_reader WITH LOGIN PASSWORD 'ChangeMe_SecurePassword123!';

-- 2. Grant connection and schema usage
GRANT CONNECT ON DATABASE current_database() TO zero_finance_reader;
GRANT USAGE ON SCHEMA public TO zero_finance_reader;

-- 3. Grant SELECT-only privileges on transactions and users tables
GRANT SELECT ON TABLE public.transactions TO zero_finance_reader;
GRANT SELECT ON TABLE public.users TO zero_finance_reader;

-- 4. Ensure future tables created in public default to SELECT-only for this user
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO zero_finance_reader;

-- 5. Revoke hazardous mutating capabilities explicitly
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM zero_finance_reader;

\echo 'ZERO read-only database role created successfully.'