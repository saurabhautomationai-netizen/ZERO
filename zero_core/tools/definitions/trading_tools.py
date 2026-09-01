"""Trading domain tools for ZERO Tool Registry."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from zero_core.agents.trading_coach import DEFAULT_TRADING_COACH
from zero_core.tools.base import BaseTool, tool
from zero_core.trading_live_reader import DEFAULT_MT5_READER
from zero_core.trading_status import TradingStatusAdapter


class PreFlightCheckInput(BaseModel):
    symbol: str = Field(default="XAUUSD", description="Market symbol (e.g. 'XAUUSD', 'EURUSD')")
    bias: str = Field(default="BULLISH", description="Higher timeframe bias ('BULLISH' or 'BEARISH')")
    action: str = Field(default="BUY", description="Trade direction ('BUY' or 'SELL')")
    entry_price: Optional[float] = Field(default=None, description="Proposed entry price")
    sl_price: Optional[float] = Field(default=None, description="Proposed stop loss price")
    tp_price: Optional[float] = Field(default=None, description="Proposed take profit price")


class TradingCoachQueryInput(BaseModel):
    query: str = Field(description="Question or command for Trading Coach RAG engine (e.g. 'review', 'leaks', 'rules', or custom question)")


@tool(
    name="trading_mt5_account_status",
    description="Retrieves live read-only MT5 account statistics: balance, equity, margin, free margin, floating P&L, and open positions.",
    risk_level="read_only",
)
def trading_mt5_account_status_tool() -> Dict[str, Any]:
    acc = DEFAULT_MT5_READER.get_account_status()
    return {
        "login": acc.login,
        "server": acc.server,
        "currency": acc.currency,
        "balance": acc.balance,
        "equity": acc.equity,
        "margin": acc.margin,
        "free_margin": acc.free_margin,
        "floating_profit": acc.floating_profit,
        "open_positions_count": acc.open_positions_count,
        "is_live_connected": acc.is_live_connected,
        "positions": [p.to_dict() for p in acc.positions],
        "summary": acc.summary(),
    }


@tool(
    name="trading_bot_signals",
    description="Reads current market sweep, structure shift, setup score, and research/demo signals from local Trading Bot.",
    risk_level="read_only",
)
def trading_bot_signals_tool() -> Dict[str, Any]:
    adapter = TradingStatusAdapter()
    status = adapter.get_status()
    return {
        "last_signal_time": str(status.last_signal_time) if status.last_signal_time else None,
        "last_demo_signal_id": status.last_demo_signal_id,
        "has_buy_state": status.buy is not None,
        "has_sell_state": status.sell is not None,
        "summary": status.summary(),
    }


@tool(
    name="trading_coach_query",
    description="Queries the Trading Coach RAG engine for post-mortems, leak audits, strategy rules, or trade analysis.",
    args_model=TradingCoachQueryInput,
    risk_level="read_only",
)
def trading_coach_query_tool(query: str) -> str:
    return DEFAULT_TRADING_COACH.answer_question(query)


@tool(
    name="trading_preflight_check",
    description="Validates a proposed trade setup against SMC strategy rules, minimum 1.5R, and live MT5 account risk.",
    args_model=PreFlightCheckInput,
    risk_level="read_only",
)
def trading_preflight_check_tool(
    symbol: str = "XAUUSD",
    bias: str = "BULLISH",
    action: str = "BUY",
    entry_price: Optional[float] = None,
    sl_price: Optional[float] = None,
    tp_price: Optional[float] = None,
) -> str:
    return DEFAULT_TRADING_COACH.pre_flight_check(
        symbol=symbol,
        bias=bias,
        action=action,
        entry_price=entry_price,
        sl_price=sl_price,
        tp_price=tp_price,
    )


TRADING_TOOLS: List[BaseTool] = [
    trading_mt5_account_status_tool,
    trading_bot_signals_tool,
    trading_coach_query_tool,
    trading_preflight_check_tool,
]
