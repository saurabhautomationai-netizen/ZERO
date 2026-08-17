from __future__ import annotations

from pathlib import Path

from zero_core.trading_status import TradingStatusAdapter

VALID_STATE = """{
    "buy_bot_last_candle_time": "2026-08-04 23:50:00",
    "buy_bot_stale_count": 0,
    "active_buy_trade": false,
    "sell_bot_last_candle_time": "2024-01-01 00:00:00"
}"""

SELL_STATE_WITH_SIGNAL_ID = """{
    "buy_bot_last_candle_time": "2026-07-22 17:15:00",
    "buy_bot_stale_count": 0,
    "active_buy_trade": false,
    "last_demo_signal_id": "XAUUSD|SELL|2026-07-29 21:10:00|ZERO_DEMO_SELL_V1"
}"""


def test_get_status_reads_all_present_files(tmp_path):
    (tmp_path / "trade_state.json").write_text(VALID_STATE, encoding="utf-8")
    (tmp_path / "trade_state_buy.json").write_text(VALID_STATE, encoding="utf-8")
    (tmp_path / "trade_state_sell.json").write_text(SELL_STATE_WITH_SIGNAL_ID, encoding="utf-8")
    (tmp_path / "last_signal_time.txt").write_text("2026-07-01 14:15:00", encoding="utf-8")

    status = TradingStatusAdapter(root=tmp_path).get_status()

    assert status.combined is not None
    assert status.buy is not None
    assert status.sell is not None
    assert status.buy.active_buy_trade is False
    assert status.buy.stale_count == 0
    assert status.last_signal_time.isoformat() == "2026-07-01T14:15:00"
    assert status.last_demo_signal_id == "XAUUSD|SELL|2026-07-29 21:10:00|ZERO_DEMO_SELL_V1"


def test_missing_files_degrade_gracefully(tmp_path):
    """No trading files at all must not raise — an empty root is a valid state
    (e.g. a fresh machine before the bot has ever run)."""
    status = TradingStatusAdapter(root=tmp_path).get_status()

    assert status.combined is None
    assert status.buy is None
    assert status.sell is None
    assert status.last_signal_time is None
    assert status.last_demo_signal_id is None
    assert "No trading status files found" in status.summary()


def test_malformed_json_is_skipped_not_raised(tmp_path):
    (tmp_path / "trade_state.json").write_text("{not valid json", encoding="utf-8")
    status = TradingStatusAdapter(root=tmp_path).get_status()
    assert status.combined is None  # skipped, no exception


def test_summary_includes_all_present_snapshots(tmp_path):
    (tmp_path / "trade_state_buy.json").write_text(VALID_STATE, encoding="utf-8")
    status = TradingStatusAdapter(root=tmp_path).get_status()
    summary = status.summary()
    assert "[buy]" in summary
    assert "active_buy_trade=False" in summary


def test_adapter_never_imports_execution_modules():
    """Guardrail: this module must stay read-only. If someone later adds an
    import of mt5_bridge/mt5_executor here, that's a scope change that
    deserves an explicit decision, not a silent diff — this test forces the
    conversation.
    """
    import zero_core.trading_status as mod

    import_lines = [
        line.strip()
        for line in Path(mod.__file__).read_text(encoding="utf-8").splitlines()
        if line.strip().startswith(("import ", "from "))
    ]
    forbidden = ("mt5_bridge", "mt5_executor", "MetaTrader5")
    offending = [ln for ln in import_lines if any(name in ln for name in forbidden)]
    assert not offending, f"found forbidden import(s): {offending}"
