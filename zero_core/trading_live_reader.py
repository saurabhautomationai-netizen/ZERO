"""Strictly READ-ONLY MT5 Live Position & Equity Stream Reader (Priority 4 & ADR-007).

Provides live account balance, equity, margin, floating P&L, and open positions
from the MetaTrader 5 terminal without importing or executing any trading/order-sending
modules.

Security Guarantee:
    This module contains NO order execution logic, order_send calls, or bridge mutations.
    Verified by static AST inspection tests.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.config import load_env

load_env()

try:
    import MetaTrader5 as mt5
    _HAS_MT5 = True
except ImportError:
    mt5 = None
    _HAS_MT5 = False


@dataclass
class MT5PositionRecord:
    """Read-only snapshot of an active MT5 trade position."""
    ticket: int
    symbol: str
    type: str  # 'BUY' or 'SELL'
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    open_time: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class MT5AccountSummary:
    """Read-only account equity, margin, and status summary."""
    login: int
    server: str
    currency: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    floating_profit: float
    open_positions_count: int
    is_live_connected: bool
    positions: List[MT5PositionRecord] = field(default_factory=list)
    error_detail: Optional[str] = None

    def summary(self) -> str:
        status_label = "LIVE CONNECTED" if self.is_live_connected else "OFFLINE / NOT CONNECTED"
        if not self.is_live_connected and self.error_detail:
            status_label = f"OFFLINE / NOT CONNECTED: {self.error_detail}"

        sign = "+" if self.floating_profit >= 0 else "-"
        pnl_fmt = f"{sign}${abs(self.floating_profit):,.2f}"

        lines = [
            f"### MT5 Account Status [{status_label}]",
            f"**Account**: `{self.login}` ({self.server})",
            f"**Balance**: `${self.balance:,.2f} {self.currency}` | **Equity**: `${self.equity:,.2f} {self.currency}`",
            f"**Floating P&L**: `{pnl_fmt}` | **Free Margin**: `${self.free_margin:,.2f}`",
            f"**Open Positions**: {self.open_positions_count}",
        ]
        if self.positions:
            lines.append("\n**Active Open Positions**:")
            for p in self.positions:
                p_sign = "+" if p.profit >= 0 else "-"
                lines.append(
                    f"  - #{p.ticket} | {p.symbol} {p.type} {p.volume} lots @ {p.open_price} "
                    f"-> Current: {p.current_price} | P&L: `{p_sign}${abs(p.profit):,.2f}`"
                )
        return "\n".join(lines)


class MT5ReadOnlyAdapter:
    """Strictly read-only adapter querying live MT5 account statistics."""

    def __init__(self, mock_mode: bool = False):
        self.mock_mode = mock_mode

    def get_account_status(self) -> MT5AccountSummary:
        """Retrieves live account status, falling back cleanly if MT5 is closed or absent."""
        if not _HAS_MT5:
            return self._get_fallback_status(connected=False, error="MetaTrader5 Python module not installed")
        if self.mock_mode:
            return self._get_fallback_status(connected=False, error="Mock mode enabled")

        try:
            # Connect to active MT5 terminal with fast non-blocking timeout
            init_ok = mt5.initialize(timeout=500)
            if not init_ok:
                err = mt5.last_error() if hasattr(mt5, "last_error") else "initialize() returned False"
                return self._get_fallback_status(connected=False, error=f"MT5 Init Error: {err}")

            acc = mt5.account_info()
            if acc is None:
                err = mt5.last_error() if hasattr(mt5, "last_error") else "account_info() is None"
                return self._get_fallback_status(connected=False, error=f"MT5 Account Error: {err}")

            raw_positions = mt5.positions_get() or ()
            positions = []
            for p in raw_positions:
                pos_type = "BUY" if p.type == 0 else "SELL"
                positions.append(
                    MT5PositionRecord(
                        ticket=int(p.ticket),
                        symbol=str(p.symbol),
                        type=pos_type,
                        volume=float(p.volume),
                        open_price=float(p.price_open),
                        current_price=float(p.price_current),
                        sl=float(p.sl),
                        tp=float(p.tp),
                        profit=float(p.profit),
                        open_time=datetime.fromtimestamp(p.time, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                    )
                )

            return MT5AccountSummary(
                login=int(acc.login),
                server=str(acc.server),
                currency=str(acc.currency),
                balance=float(acc.balance),
                equity=float(acc.equity),
                margin=float(acc.margin),
                free_margin=float(acc.margin_free),
                floating_profit=float(acc.profit),
                open_positions_count=len(positions),
                is_live_connected=True,
                positions=positions,
            )
        except Exception as exc:
            return self._get_fallback_status(connected=False, error=str(exc))

    def _get_fallback_status(self, connected: bool = False, error: Optional[str] = None) -> MT5AccountSummary:
        """Safe fallback summary when MT5 terminal is closed or not installed in test environments."""
        return MT5AccountSummary(
            login=0,
            server="MT5-Terminal-Local",
            currency="USD",
            balance=0.0,
            equity=0.0,
            margin=0.0,
            free_margin=0.0,
            floating_profit=0.0,
            open_positions_count=0,
            is_live_connected=connected,
            positions=[],
            error_detail=error,
        )


# Global singleton instance
DEFAULT_MT5_READER = MT5ReadOnlyAdapter()
