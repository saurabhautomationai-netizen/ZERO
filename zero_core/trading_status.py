"""Read-only Trading bot status adapter.

Reads trade_state.json / trade_state_buy.json / trade_state_sell.json / last_signal_time.txt.
Maintains pure file-based read-only architecture without importing MT5.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from zero_core import config

logger = logging.getLogger("zero_core.trading_status")

_CANDLE_TIME_FMT = "%Y-%m-%d %H:%M:%S"


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(value, _CANDLE_TIME_FMT)
    except ValueError:
        logger.warning("Could not parse timestamp %r", value)
        return None


@dataclass
class BotStateSnapshot:
    source_file: str
    last_candle_time: Optional[datetime]
    stale_count: Optional[int]
    active_buy_trade: Optional[bool]
    raw: dict


@dataclass
class TradingStatus:
    combined: Optional[BotStateSnapshot]   # trade_state.json
    buy: Optional[BotStateSnapshot]         # trade_state_buy.json
    sell: Optional[BotStateSnapshot]         # trade_state_sell.json
    last_signal_time: Optional[datetime]      # last_signal_time.txt
    last_demo_signal_id: Optional[str]         # sell file's last_demo_signal_id, if present

    def summary(self) -> str:
        lines: list[str] = []
        if self.last_signal_time:
            lines.append(f"Last signal: {self.last_signal_time}")
        if self.last_demo_signal_id:
            lines.append(f"Last demo signal id: {self.last_demo_signal_id}")
        for label, snap in [("buy", self.buy), ("sell", self.sell), ("combined", self.combined)]:
            if snap is None:
                continue
            lines.append(
                f"[{label}] last_candle={snap.last_candle_time}, "
                f"stale_count={snap.stale_count}, active_buy_trade={snap.active_buy_trade}"
            )
        return "\n".join(lines) if lines else "No trading status files found or readable."


class TradingStatusAdapter:
    def __init__(self, root: Path = config.SIBLING_PROJECTS["trading_bot"]):
        self.root = Path(root)

    def _read_json(self, filename: str) -> Optional[dict]:
        path = self.root / filename
        if not path.exists():
            logger.info("%s not found at %s", filename, path)
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Could not read/parse %s: %s", path, exc)
            return None

    def _read_text(self, filename: str) -> Optional[str]:
        path = self.root / filename
        if not path.exists():
            return None
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return None

    def _snapshot(self, filename: str) -> Optional[BotStateSnapshot]:
        data = self._read_json(filename)
        if data is None:
            return None
        return BotStateSnapshot(
            source_file=filename,
            last_candle_time=_parse_dt(data.get("buy_bot_last_candle_time")),
            stale_count=data.get("buy_bot_stale_count"),
            active_buy_trade=data.get("active_buy_trade"),
            raw=data,
        )

    def get_status(self) -> TradingStatus:
        combined = self._snapshot("trade_state.json")
        buy = self._snapshot("trade_state_buy.json")
        sell = self._snapshot("trade_state_sell.json")

        last_signal_time = _parse_dt(self._read_text("last_signal_time.txt"))
        last_demo_signal_id = sell.raw.get("last_demo_signal_id") if sell else None

        return TradingStatus(
            combined=combined,
            buy=buy,
            sell=sell,
            last_signal_time=last_signal_time,
            last_demo_signal_id=last_demo_signal_id,
        )
