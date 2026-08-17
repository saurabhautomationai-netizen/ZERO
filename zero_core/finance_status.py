"""Read-only Finance Tracker adapter — Phase 1.5b.

Backend, confirmed by inspecting the live "Zero Finance Tracker" n8n
workflow (118 nodes) rather than assumed: transactions land in a real
Postgres database, schema `public`, tables `transactions` and `users`.
Most other features of that workflow (credit cards, loans, subscriptions,
reminders, monthly reports, cashflow forecasting) still live in Google
Sheets inside n8n — this adapter does NOT read those; it only reads the
`transactions` table, which is the highest-value, cleanest-to-query slice.

This module never writes. `get_recent_transactions` and
`get_category_totals` are the only two operations, matching the same
"smallest useful slice first" scope as the Trading bot status adapter.
Everything else the n8n workflow already does (budget alerts, anomaly
detection, forecasting) stays there — duplicating it here would be exactly
the mistake the original architecture review warned against.

SECURITY — action required before this is usable:
The DSN this adapter connects with should be a DEDICATED READ-ONLY
Postgres role, not the same credentials the n8n workflow uses to write.
Run this once against your database (adjust the password), then put the
resulting connection string in `.env` as FINANCE_DB_URL — this file does
not create the role for you, on purpose, since that's a privileged DDL
change against your live production database:

    CREATE ROLE zero_finance_reader WITH LOGIN PASSWORD 'choose-a-password';
    GRANT CONNECT ON DATABASE postgres TO zero_finance_reader;
    GRANT USAGE ON SCHEMA public TO zero_finance_reader;
    GRANT SELECT ON public.transactions, public.users TO zero_finance_reader;
    -- keep future tables readable too, without re-granting each time:
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO zero_finance_reader;

If FINANCE_DB_URL is unset, this adapter raises FinanceDBUnavailable with
that message rather than silently returning empty results — a missing
connection should be loud, not look like "you have no transactions."
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from zero_core.config import load_env

load_env()

try:
    import psycopg2
    _HAS_PSYCOPG2 = True
except ImportError:  # pragma: no cover - exercised in envs without psycopg2
    psycopg2 = None
    _HAS_PSYCOPG2 = False


class FinanceDBUnavailable(RuntimeError):
    """Raised when FINANCE_DB_URL is unset or psycopg2 isn't installed."""


@dataclass
class TransactionRecord:
    """Field names match the real `transactions` table columns verbatim —
    not renamed, so this stays honest about what's actually in the DB
    rather than a guessed/idealized shape.
    """
    id: Optional[str]
    amount: Optional[float]
    type: Optional[str]
    transaction_date: Optional[datetime]
    category: Optional[str]
    vendor: Optional[str]
    platform: Optional[str]
    product: Optional[str]
    currency: Optional[str]
    currency_symbol: Optional[str]
    source: Optional[str]
    notes: Optional[str]

    @classmethod
    def from_row(cls, row: dict) -> "TransactionRecord":
        return cls(**{f: row.get(f) for f in cls.__dataclass_fields__})


@dataclass
class CategoryTotal:
    category: Optional[str]
    total_amount: float
    transaction_count: int


def _rows_to_dicts(cursor) -> list[dict]:
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


class FinanceStatusAdapter:
    """Opens a short-lived connection per call rather than pooling — Phase 1
    scope is low call volume (personal use, not a service under load).
    Swap for a real connection pool (psycopg2.pool / SQLAlchemy engine) if
    this ever sits behind the planned FastAPI interface with concurrent
    requests.
    """

    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn if dsn is not None else os.environ.get("FINANCE_DB_URL")

    def _connect(self):
        if not self.dsn:
            raise FinanceDBUnavailable(
                "FINANCE_DB_URL is not set. Set your Supabase or PostgreSQL connection "
                "string in .env as FINANCE_DB_URL=postgresql://postgres.xxx:password@aws-0-ap-south-1.pooler.supabase.com:6543/postgres"
            )
        if not _HAS_PSYCOPG2:
            raise FinanceDBUnavailable(
                "psycopg2 is not installed. Run: pip install psycopg2-binary"
            )

        dsn = self.dsn
        # Auto-append sslmode=require for cloud poolers if not specified
        if ("supabase.com" in dsn or "neon.tech" in dsn) and "sslmode=" not in dsn:
            sep = "&" if "?" in dsn else "?"
            dsn = f"{dsn}{sep}sslmode=require"

        return psycopg2.connect(dsn)

    def get_recent_transactions(self, limit: int = 20) -> list[TransactionRecord]:
        query = (
            "SELECT id, amount, type, transaction_date, category, vendor, "
            "platform, product, currency, currency_symbol, source, notes "
            "FROM transactions ORDER BY transaction_date DESC LIMIT %s"
        )
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, (limit,))
                rows = _rows_to_dicts(cur)
        finally:
            conn.close()
        return [TransactionRecord.from_row(r) for r in rows]

    def get_category_totals(self, since: Optional[date] = None) -> list[CategoryTotal]:
        if since is not None:
            query = (
                "SELECT category, SUM(amount) AS total_amount, COUNT(*) AS transaction_count "
                "FROM transactions WHERE transaction_date >= %s "
                "GROUP BY category ORDER BY total_amount DESC"
            )
            params = (since,)
        else:
            query = (
                "SELECT category, SUM(amount) AS total_amount, COUNT(*) AS transaction_count "
                "FROM transactions GROUP BY category ORDER BY total_amount DESC"
            )
            params = ()

        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = _rows_to_dicts(cur)
        finally:
            conn.close()
        return [
            CategoryTotal(
                category=r["category"],
                total_amount=float(r["total_amount"]) if r["total_amount"] is not None else 0.0,
                transaction_count=r["transaction_count"],
            )
            for r in rows
        ]


if __name__ == "__main__":
    # Manual check once FINANCE_DB_URL is set in your environment:
    #   python -m zero_core.finance_status
    adapter = FinanceStatusAdapter()
    try:
        recent = adapter.get_recent_transactions(limit=5)
        print(f"{len(recent)} recent transaction(s):")
        for t in recent:
            print(f"  {t.transaction_date} | {t.category} | {t.vendor} | {t.amount} {t.currency}")
    except FinanceDBUnavailable as exc:
        print(f"Not configured yet: {exc}")
