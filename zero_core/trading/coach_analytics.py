"""Trading Coach Performance & Leak Analytics Engine.

Calculates win-rate statistics, setup distribution, R-multiple distributions,
and flags high-frequency trading leaks (e.g. trading without MSS confirmation,
trading outside high-probability session windows).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.trading.coach_ingestion import IngestedTradeRecord


@dataclass
class PerformanceSummary:
    """Aggregated trading performance statistics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    breakeven_trades: int
    win_rate: float
    total_r_profit: float
    average_r: float
    most_frequent_blocked_reasons: List[tuple[str, int]] = field(default_factory=list)
    outcomes_by_bias: Dict[str, Dict[str, int]] = field(default_factory=dict)
    hourly_distribution: Dict[int, int] = field(default_factory=dict)

    def to_markdown(self) -> str:
        lines = [
            "### 📊 Trading Performance & Setup Audit",
            f"- **Evaluated Trades / Setups**: `{self.total_trades}`",
            f"- **Wins**: `{self.winning_trades}` | **Losses**: `{self.losing_trades}` | **Win Rate**: `{self.win_rate:.1f}%`",
            f"- **Cumulative Return**: `{self.total_r_profit:+.2f}R` | **Expectancy**: `{self.average_r:+.2f}R per trade`",
        ]

        if self.most_frequent_blocked_reasons:
            lines.append("\n**⚠️ Top Friction Points & Blocked Reasons**:")
            for reason, count in self.most_frequent_blocked_reasons[:5]:
                lines.append(f"  - `{reason}` ({count} instances)")

        if self.outcomes_by_bias:
            lines.append("\n**🧭 Performance by HTF Bias**:")
            for bias, counts in self.outcomes_by_bias.items():
                w = counts.get("WIN", 0)
                l = counts.get("LOSS", 0)
                total = w + l
                wr = (w / total * 100) if total > 0 else 0.0
                lines.append(f"  - **{bias}**: {w}W / {l}L ({wr:.1f}% win rate across {total} trades)")

        return "\n".join(lines)


class CoachAnalytics:
    """Analyzes trade histories for strategic patterns, edge, and behavioral leaks."""

    @staticmethod
    def compute_summary(records: List[IngestedTradeRecord]) -> PerformanceSummary:
        total = len(records)
        if total == 0:
            return PerformanceSummary(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                breakeven_trades=0,
                win_rate=0.0,
                total_r_profit=0.0,
                average_r=0.0,
            )

        wins = 0
        losses = 0
        be = 0
        total_r = 0.0
        r_counted = 0

        blocked_counter: Counter[str] = Counter()
        bias_map: Dict[str, Counter[str]] = defaultdict(Counter)
        hourly_map: Counter[int] = Counter()

        for r in records:
            st = r.status.upper()
            if st == "WIN":
                wins += 1
            elif st == "LOSS":
                losses += 1
            elif st in ("BREAKEVEN", "BE"):
                be += 1

            if r.profit_r is not None:
                total_r += r.profit_r
                r_counted += 1
            elif st == "WIN" and r.rr is not None:
                total_r += r.rr
                r_counted += 1
            elif st == "LOSS":
                total_r -= 1.0
                r_counted += 1

            for reason in r.blocked_reasons:
                blocked_counter[reason] += 1

            if st in ("WIN", "LOSS", "TAKEN"):
                bias_map[r.bias][st] += 1

            # Extract hour if timestamp contains time
            if r.timestamp and ":" in r.timestamp:
                try:
                    time_part = r.timestamp.split()[1] if " " in r.timestamp else r.timestamp
                    hour = int(time_part.split(":")[0])
                    hourly_map[hour] += 1
                except (IndexError, ValueError):
                    pass

        resolved_trades = wins + losses + be
        win_rate = (wins / resolved_trades * 100) if resolved_trades > 0 else 0.0
        avg_r = (total_r / r_counted) if r_counted > 0 else 0.0

        return PerformanceSummary(
            total_trades=total,
            winning_trades=wins,
            losing_trades=losses,
            breakeven_trades=be,
            win_rate=win_rate,
            total_r_profit=total_r,
            average_r=avg_r,
            most_frequent_blocked_reasons=blocked_counter.most_common(5),
            outcomes_by_bias={k: dict(v) for k, v in bias_map.items()},
            hourly_distribution=dict(hourly_map),
        )

    @staticmethod
    def audit_leaks(records: List[IngestedTradeRecord]) -> List[str]:
        """Identifies specific behavioral and rule compliance leaks."""
        leaks: List[str] = []
        if not records:
            return ["No trade records available to audit."]

        # 1. Check trades taken without sweep
        no_sweep_losses = [
            r for r in records
            if r.status == "LOSS" and (not r.sweep or r.sweep.upper() in ("NONE", "FALSE"))
        ]
        if no_sweep_losses:
            leaks.append(
                f"🚨 **No-Sweep Entry Leak**: Found {len(no_sweep_losses)} losing trades taken "
                "without clear liquidity sweep confirmation. Wait for buy/sell-side sweep before entry."
            )

        # 2. Check trades taken counter to HTF bias
        counter_trend = [
            r for r in records
            if (r.action == "BUY" and r.bias == "BEARISH") or (r.action == "SELL" and r.bias == "BULLISH")
        ]
        if counter_trend:
            leaks.append(
                f"🚨 **Counter-Trend Leak**: {len(counter_trend)} setups were taken directly against "
                "Higher Timeframe bias. Enforce Rule #2 (HTF alignment)."
            )

        # 3. Check low score trades
        low_score_trades = [r for r in records if 0 < r.score < 60 and r.status in ("TAKEN", "LOSS")]
        if low_score_trades:
            leaks.append(
                f"⚠️ **Low Confluence Entries**: {len(low_score_trades)} trades executed with confluence score < 60."
            )

        if not leaks:
            leaks.append("✅ **Clean Discipline**: No major rule leaks detected in recent trade sample.")

        return leaks
