"""Trading Coach Data Ingestion Pipeline for ZERO.

Scans and ingests data from sibling Trading Bot artifacts:
- Setup history CSVs (setup_history.csv, setup_history_buy.csv, setup_history_sell.csv)
- Paper trade history CSVs (paper_trade_history.csv, paper_trade_history_buy.csv)
- Terminal execution logs & evaluation snapshots (buy_tail.txt, sell_tail.txt, buy/sell_terminal.log)
- Core SMC strategy rules and risk parameters
"""

from __future__ import annotations

import csv
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class IngestedTradeRecord:
    """Represents a normalized trade or setup evaluation record."""
    record_id: str
    timestamp: str
    symbol: str
    action: str  # 'BUY' or 'SELL'
    status: str  # 'WIN', 'LOSS', 'BLOCKED', 'PENDING', 'TAKEN'
    score: float = 0.0
    bias: str = "NEUTRAL"
    sweep: Optional[str] = None
    mss_type: Optional[str] = None
    fvg_type: Optional[str] = None
    entry_price: Optional[float] = None
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    rr: Optional[float] = None
    profit_r: Optional[float] = None
    close_reason: Optional[str] = None
    blocked_reasons: List[str] = field(default_factory=list)
    source_file: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_rag_text(self) -> str:
        """Converts trade record into concise semantic text for vector search."""
        outcome = self.status
        r_str = f", Profit: {self.profit_r:+.2f}R" if self.profit_r is not None else ""
        sweep_str = f", Sweep: {self.sweep}" if self.sweep else ""
        mss_str = f", MSS: {self.mss_type}" if self.mss_type else ""
        fvg_str = f", FVG: {self.fvg_type}" if self.fvg_type else ""
        reasons_str = f", Blocked by: {'; '.join(self.blocked_reasons)}" if self.blocked_reasons else ""
        return (
            f"Trade Setup [{self.timestamp}] {self.symbol} {self.action} -> Outcome: {outcome}{r_str} "
            f"(Score: {self.score}, Bias: {self.bias}{sweep_str}{mss_str}{fvg_str}{reasons_str})"
        )


@dataclass
class StrategyRuleRecord:
    """Represents an SMC trading strategy rule."""
    rule_id: str
    category: str  # 'Risk', 'Structure', 'Liquidity', 'Execution', 'Filter'
    name: str
    rule_text: str
    penalty_points: int = 20

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def to_rag_text(self) -> str:
        return f"SMC Strategy Rule [{self.rule_id}] {self.name} ({self.category}): {self.rule_text}"


@dataclass
class LogEventRecord:
    """Represents an execution event or warning extracted from bot logs."""
    timestamp: str
    direction: str
    event_type: str  # 'ERROR', 'WARN', 'SIGNAL', 'EVALUATION'
    message: str
    source_file: str = ""

    def to_rag_text(self) -> str:
        return f"Log Event [{self.timestamp}] [{self.direction}] {self.event_type}: {self.message}"


class CoachIngestionPipeline:
    """Ingests historical CSVs, logs, and strategy definitions from Trading bot folder."""

    def __init__(self, trading_bot_path: Optional[Path] = None):
        self.bot_dir = self._resolve_bot_dir(trading_bot_path)

    @staticmethod
    def _resolve_bot_dir(explicit_path: Optional[Path] = None) -> Optional[Path]:
        if explicit_path and explicit_path.exists():
            return explicit_path

        env_path = os.environ.get("TRADING_BOT_PATH")
        if env_path:
            p = Path(env_path).resolve()
            if p.exists():
                return p

        # Default sibling folder resolution: ../Trading bot (relative to Zero root or zero_core)
        for parent_level in (
            Path(__file__).resolve().parent.parent.parent.parent / "Trading bot",
            Path(__file__).resolve().parent.parent.parent / "Trading bot",
            Path.cwd().parent / "Trading bot",
            Path.cwd() / "Trading bot",
        ):
            candidate = parent_level.resolve()
            if candidate.exists() and candidate.is_dir():
                return candidate

        return None

    def get_standard_rules(self) -> List[StrategyRuleRecord]:
        """Returns the core baseline SMC rules for trading evaluation."""
        return [
            StrategyRuleRecord(
                rule_id="RULE_01_MAX_RISK",
                category="Risk",
                name="Strict Account Risk Limit",
                rule_text="Never risk more than 1.0% to 1.5% of account balance on a single trade. Stop-loss must always be defined.",
                penalty_points=30,
            ),
            StrategyRuleRecord(
                rule_id="RULE_02_HTF_BIAS",
                category="Structure",
                name="Higher Timeframe Bias Alignment",
                rule_text="Trades must align with the 4H/1H market structure and bias. Do not trade long in a confirmed bearish HTF trend.",
                penalty_points=25,
            ),
            StrategyRuleRecord(
                rule_id="RULE_03_LIQUIDITY_SWEEP",
                category="Liquidity",
                name="Liquidity Sweep Requirement",
                rule_text="Every valid SMC setup must sweep prior session high/low or equal highs/lows before reversal entry.",
                penalty_points=20,
            ),
            StrategyRuleRecord(
                rule_id="RULE_04_DISPLACEMENT_MSS",
                category="Structure",
                name="Market Structure Shift with Displacement",
                rule_text="Reversal requires clear displacement candle breaking internal swing structure, creating an imbalance/FVG.",
                penalty_points=20,
            ),
            StrategyRuleRecord(
                rule_id="RULE_05_FVG_RETEST",
                category="Entry",
                name="Fair Value Gap (FVG) Retest Entry",
                rule_text="Enter only on the retest or mitigation of the identified Fair Value Gap zone, not at the extreme candle wick.",
                penalty_points=15,
            ),
            StrategyRuleRecord(
                rule_id="RULE_06_NEWS_FILTER",
                category="Filter",
                name="High-Impact News Quarantine",
                rule_text="No trade execution within 15 minutes before or after high-impact USD/Gold macroeconomic releases (CPI, NFP, FOMC).",
                penalty_points=30,
            ),
            StrategyRuleRecord(
                rule_id="RULE_07_MIN_RR",
                category="Risk",
                name="Minimum Risk-to-Reward Ratio",
                rule_text="Target minimum 1:2 Risk-to-Reward (R:R). Reject setups where target liquidity offers less than 1.5R.",
                penalty_points=15,
            ),
        ]

    def parse_setup_history_csv(self, file_path: Path, max_records: int = 500) -> List[IngestedTradeRecord]:
        """Parses setup_history*.csv files into IngestedTradeRecord objects."""
        if not file_path.exists():
            return []

        records: List[IngestedTradeRecord] = []
        try:
            with open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    if i >= max_records:
                        break

                    time_val = (row.get("time") or "").strip()
                    if not time_val:
                        continue

                    side = (row.get("side") or (row.get("action") or "BUY")).strip().upper()
                    raw_score = (row.get("score") or "0").strip()
                    try:
                        score = float(raw_score)
                    except ValueError:
                        score = 0.0

                    bias = (row.get("bias") or "NEUTRAL").strip().upper()
                    sweep = (row.get("sweep") or "").strip() or None
                    mss = (row.get("mss_type") or "").strip() or None
                    fvg = (row.get("fvg_type") or "").strip() or None
                    trade_taken = (row.get("trade_taken") or "").strip().upper()
                    
                    status = "TAKEN" if trade_taken in ("YES", "TRUE", "1") else "BLOCKED"
                    if not trade_taken:
                        status = "BLOCKED" if score < 60 else "EVALUATED"

                    raw_blocked = (row.get("blocked_reasons") or "").strip()
                    blocked_reasons = [r.strip() for r in raw_blocked.split(";") if r.strip()] if raw_blocked else []

                    rec = IngestedTradeRecord(
                        record_id=f"setup_{file_path.stem}_{i}",
                        timestamp=time_val,
                        symbol="XAUUSD",
                        action=side,
                        status=status,
                        score=score,
                        bias=bias,
                        sweep=sweep,
                        mss_type=mss,
                        fvg_type=fvg,
                        blocked_reasons=blocked_reasons,
                        source_file=file_path.name,
                    )
                    records.append(rec)
        except Exception:
            return []

        return records

    def parse_paper_trade_csv(self, file_path: Path) -> List[IngestedTradeRecord]:
        """Parses paper_trade_history*.csv files with actual WIN/LOSS outcomes."""
        if not file_path.exists():
            return []

        records: List[IngestedTradeRecord] = []
        try:
            with open(file_path, mode="r", encoding="utf-8", errors="ignore") as f:
                reader = csv.DictReader(f)
                for i, row in enumerate(reader):
                    time_val = (row.get("time") or "").strip()
                    if not time_val:
                        continue

                    action = (row.get("action") or "BUY").strip().upper()
                    status = (row.get("status") or "PENDING").strip().upper()
                    bias = (row.get("bias") or "NEUTRAL").strip().upper()
                    sweep = (row.get("sweep") or "").strip() or None
                    mss = (row.get("mss_type") or "").strip() or None
                    fvg = (row.get("fvg_type") or "").strip() or None

                    def _safe_float(k: str) -> Optional[float]:
                        v = (row.get(k) or "").strip()
                        try:
                            return float(v) if v else None
                        except ValueError:
                            return None

                    entry = _safe_float("entry")
                    tp = _safe_float("tp_price")
                    sl = _safe_float("sl_price")
                    rr = _safe_float("rr")
                    profit_r = _safe_float("profit_r")
                    close_reason = (row.get("close_reason") or "").strip() or None

                    rec = IngestedTradeRecord(
                        record_id=f"paper_{file_path.stem}_{i}",
                        timestamp=time_val,
                        symbol="XAUUSD",
                        action=action,
                        status=status,
                        bias=bias,
                        sweep=sweep,
                        mss_type=mss,
                        fvg_type=fvg,
                        entry_price=entry,
                        tp_price=tp,
                        sl_price=sl,
                        rr=rr,
                        profit_r=profit_r,
                        close_reason=close_reason,
                        source_file=file_path.name,
                    )
                    records.append(rec)
        except Exception:
            return []

        return records

    def parse_terminal_tail(self, file_path: Path) -> List[LogEventRecord]:
        """Parses buy_tail.txt / sell_tail.txt into recent diagnostic log events."""
        if not file_path.exists():
            return []

        events: List[LogEventRecord] = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            direction = "BUY" if "buy" in file_path.name.lower() else "SELL"

            current_time = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            for line in lines[-30:]:
                if "No valid" in line or "No BUY" in line or "No SELL" in line:
                    events.append(LogEventRecord(timestamp=current_time, direction=direction, event_type="SIGNAL", message=line, source_file=file_path.name))
                elif "Score Reasons:" in line or "Setup Score:" in line:
                    events.append(LogEventRecord(timestamp=current_time, direction=direction, event_type="EVALUATION", message=line, source_file=file_path.name))
                elif "MT5 initialize failed" in line or "Error:" in line:
                    events.append(LogEventRecord(timestamp=current_time, direction=direction, event_type="ERROR", message=line, source_file=file_path.name))
        except Exception:
            return []

        return events

    def ingest_all(self) -> Dict[str, Any]:
        """Scans and ingests all available trading bot assets."""
        rules = self.get_standard_rules()
        trades: List[IngestedTradeRecord] = []
        logs: List[LogEventRecord] = []

        if self.bot_dir and self.bot_dir.exists():
            # Setup CSVs
            for csv_name in ("setup_history.csv", "setup_history_buy.csv", "setup_history_sell.csv"):
                p = self.bot_dir / csv_name
                if p.exists():
                    trades.extend(self.parse_setup_history_csv(p, max_records=200))

            # Paper trades
            for paper_csv in ("paper_trade_history.csv", "paper_trade_history_buy.csv"):
                p = self.bot_dir / paper_csv
                if p.exists():
                    trades.extend(self.parse_paper_trade_csv(p))

            # Tails / logs
            for tail_name in ("buy_tail.txt", "sell_tail.txt"):
                p = self.bot_dir / tail_name
                if p.exists():
                    logs.extend(self.parse_terminal_tail(p))

        return {
            "rules": rules,
            "trades": trades,
            "logs": logs,
            "trade_count": len(trades),
            "log_count": len(logs),
            "rule_count": len(rules),
            "bot_dir_found": bool(self.bot_dir and self.bot_dir.exists()),
        }


# Global singleton ingestion instance
DEFAULT_COACH_INGESTION = CoachIngestionPipeline()
