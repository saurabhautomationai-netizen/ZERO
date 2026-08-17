from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

import zero_core.finance_status as fs
from zero_core.finance_status import (
    FinanceDBUnavailable,
    FinanceStatusAdapter,
)


def _mock_connection(columns: list[str], rows: list[tuple]):
    """Build a MagicMock that behaves like a psycopg2 connection through
    `with conn.cursor() as cur: cur.execute(...); cur.fetchall()`.
    """
    cursor = MagicMock()
    cursor.description = [(c,) for c in columns]  # psycopg2 description is tuples; [0] is name
    cursor.fetchall.return_value = rows
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


def test_missing_dsn_raises_unavailable_not_silent_empty(monkeypatch):
    monkeypatch.delenv("FINANCE_DB_URL", raising=False)
    adapter = FinanceStatusAdapter(dsn=None)
    with pytest.raises(FinanceDBUnavailable, match="FINANCE_DB_URL"):
        adapter.get_recent_transactions()


def test_missing_psycopg2_raises_unavailable(monkeypatch):
    monkeypatch.setattr(fs, "_HAS_PSYCOPG2", False)
    adapter = FinanceStatusAdapter(dsn="postgres://fake")
    with pytest.raises(FinanceDBUnavailable, match="psycopg2 is not installed"):
        adapter.get_recent_transactions()


def test_get_recent_transactions_maps_rows_and_closes_connection(monkeypatch):
    columns = [
        "id", "amount", "type", "transaction_date", "category", "vendor",
        "platform", "product", "currency", "currency_symbol", "source", "notes",
    ]
    rows = [
        ("t1", 499.0, "debit", datetime(2026, 8, 10, 9, 0), "Food", "Zomato",
         "whatsapp", "Order", "INR", "₹", "text", None),
    ]
    conn, cursor = _mock_connection(columns, rows)

    monkeypatch.setattr(fs, "_HAS_PSYCOPG2", True)
    monkeypatch.setattr(fs, "psycopg2", MagicMock(connect=MagicMock(return_value=conn)))

    adapter = FinanceStatusAdapter(dsn="postgres://fake")
    result = adapter.get_recent_transactions(limit=5)

    assert len(result) == 1
    record = result[0]
    assert record.id == "t1"
    assert record.amount == 499.0
    assert record.category == "Food"
    assert record.vendor == "Zomato"

    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args[0]
    assert "FROM transactions" in sql
    assert params == (5,)
    conn.close.assert_called_once()


def test_get_category_totals_without_since(monkeypatch):
    columns = ["category", "total_amount", "transaction_count"]
    rows = [("Food", 1200.5, 4), ("Transport", 300.0, 2)]
    conn, cursor = _mock_connection(columns, rows)

    monkeypatch.setattr(fs, "_HAS_PSYCOPG2", True)
    monkeypatch.setattr(fs, "psycopg2", MagicMock(connect=MagicMock(return_value=conn)))

    adapter = FinanceStatusAdapter(dsn="postgres://fake")
    totals = adapter.get_category_totals()

    assert len(totals) == 2
    assert totals[0].category == "Food"
    assert totals[0].total_amount == 1200.5
    assert totals[0].transaction_count == 4

    sql, params = cursor.execute.call_args[0]
    assert "WHERE" not in sql
    assert params == ()


def test_get_category_totals_with_since_uses_parameterized_query(monkeypatch):
    conn, cursor = _mock_connection(
        ["category", "total_amount", "transaction_count"], []
    )
    monkeypatch.setattr(fs, "_HAS_PSYCOPG2", True)
    monkeypatch.setattr(fs, "psycopg2", MagicMock(connect=MagicMock(return_value=conn)))

    adapter = FinanceStatusAdapter(dsn="postgres://fake")
    since = date(2026, 8, 1)
    adapter.get_category_totals(since=since)

    sql, params = cursor.execute.call_args[0]
    assert "WHERE transaction_date >= %s" in sql
    assert params == (since,)
    # never string-format the date into the query itself
    assert "2026-08-01" not in sql


def test_null_total_amount_becomes_zero_not_crash(monkeypatch):
    conn, cursor = _mock_connection(
        ["category", "total_amount", "transaction_count"],
        [("Uncategorized", None, 0)],
    )
    monkeypatch.setattr(fs, "_HAS_PSYCOPG2", True)
    monkeypatch.setattr(fs, "psycopg2", MagicMock(connect=MagicMock(return_value=conn)))

    adapter = FinanceStatusAdapter(dsn="postgres://fake")
    totals = adapter.get_category_totals()
    assert totals[0].total_amount == 0.0
