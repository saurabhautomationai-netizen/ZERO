from __future__ import annotations

import ast
from pathlib import Path

from zero_core.trading_live_reader import (
    DEFAULT_MT5_READER,
    MT5AccountSummary,
    MT5PositionRecord,
    MT5ReadOnlyAdapter,
)


def test_mt5_account_summary_formatting():
    pos = MT5PositionRecord(
        ticket=1001,
        symbol="XAUUSD",
        type="BUY",
        volume=0.1,
        open_price=2340.50,
        current_price=2345.00,
        sl=2335.00,
        tp=2355.00,
        profit=45.00,
        open_time="2026-08-16 12:00:00",
    )
    summary = MT5AccountSummary(
        login=123456,
        server="Demo-Server",
        currency="USD",
        balance=10000.0,
        equity=10045.0,
        margin=234.0,
        free_margin=9811.0,
        floating_profit=45.0,
        open_positions_count=1,
        is_live_connected=True,
        positions=[pos],
    )

    text = summary.summary()
    assert "LIVE CONNECTED" in text
    assert "10,000.00 USD" in text
    assert "+$45.00" in text
    assert "XAUUSD BUY 0.1 lots" in text


def test_mt5_adapter_fallback_mode():
    adapter = MT5ReadOnlyAdapter(mock_mode=True)
    summary = adapter.get_account_status()
    assert summary.is_live_connected is False
    assert summary.open_positions_count == 0
    assert "OFFLINE" in summary.summary()


def test_static_ast_mt5_order_execution_guard():
    """Security Assertion (ADR-007):

    Ensures that zero_core/trading_live_reader.py contains NO order execution logic
    or order_send function calls.
    """
    target_file = Path(__file__).resolve().parent.parent / "zero_core" / "trading_live_reader.py"
    source = target_file.read_text(encoding="utf-8")
    tree = ast.parse(source)

    forbidden_calls = {"order_send", "order_check", "order_calc_margin", "order_calc_profit"}

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr in forbidden_calls:
                raise AssertionError(f"Security Violation: Forbidden MT5 mutating call '{node.func.attr}' found!")
            elif isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                raise AssertionError(f"Security Violation: Forbidden MT5 mutating call '{node.func.id}' found!")
