"""Trading Coach Agent for ZERO (Milestone M11 & Trading Coach RAG Pipeline).

Provides RAG-driven trade review, rule compliance analysis over historical trades,
pre-flight trade validation, session leak audits, and live MT5 account status context.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Union

from zero_core.memory.vector_rag import VectorRAGStore
from zero_core.trading.coach_analytics import CoachAnalytics, PerformanceSummary
from zero_core.trading.coach_ingestion import (
    CoachIngestionPipeline,
    DEFAULT_COACH_INGESTION,
    IngestedTradeRecord,
    StrategyRuleRecord,
)
from zero_core.trading_live_reader import DEFAULT_MT5_READER, MT5ReadOnlyAdapter


@dataclass
class TradeLogRecord:
    """Represents a completed trade review record."""
    trade_id: str
    symbol: str
    direction: str  # 'BUY' or 'SELL'
    entry_price: float
    exit_price: float
    pnl: float
    setup_type: str  # e.g., 'SMC Liquidity Sweep', 'Fair Value Gap', 'Break of Structure'
    rule_violations: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TradingCoachAgent:
    """RAG-powered trading coach that evaluates setups, rules, and live performance."""

    def __init__(
        self,
        rag_store: Optional[VectorRAGStore] = None,
        ingestion: Optional[CoachIngestionPipeline] = None,
        mt5_reader: Optional[MT5ReadOnlyAdapter] = None,
    ):
        self.rag = rag_store or VectorRAGStore()
        self.ingestion = ingestion or DEFAULT_COACH_INGESTION
        self.mt5_reader = mt5_reader or DEFAULT_MT5_READER
        self._trades: Dict[str, IngestedTradeRecord] = {}
        self._legacy_trades: Dict[str, TradeLogRecord] = {}
        self._rules: Dict[str, StrategyRuleRecord] = {}

        # Auto-ingest baseline rules and available bot artifacts
        self.sync_knowledge_base()

    def sync_knowledge_base(self) -> Dict[str, int]:
        """Ingests available trading bot CSVs, execution logs, and SMC strategy rules."""
        data = self.ingestion.ingest_all()

        # Ingest rules
        for rule in data["rules"]:
            self.ingest_strategy_rule(rule)

        # Ingest trades
        for trade in data["trades"]:
            self.ingest_trade_record(trade)

        # Ingest log events
        for log_evt in data["logs"]:
            self.rag.add_document(
                doc_id=f"log_{abs(hash(log_evt.message)) % 1000000}",
                text=log_evt.to_rag_text(),
                metadata={"type": "log_event", "direction": log_evt.direction},
            )

        return {
            "rules_indexed": len(self._rules),
            "trades_indexed": len(self._trades),
            "total_documents": self.rag.count(),
        }

    def ingest_strategy_rule(
        self,
        rule_or_id: Optional[Union[StrategyRuleRecord, str]] = None,
        rule_text: Optional[str] = None,
        name: Optional[str] = None,
        category: str = "Strategy",
        penalty_points: int = 20,
        rule_id: Optional[str] = None,
    ) -> None:
        """Indexes an SMC strategy rule for RAG retrieval."""
        if isinstance(rule_or_id, StrategyRuleRecord):
            rule = rule_or_id
        else:
            actual_id = str(rule_id or rule_or_id or "RULE_CUSTOM")
            rule = StrategyRuleRecord(
                rule_id=actual_id,
                category=category,
                name=name or actual_id.replace("_", " ").title(),
                rule_text=rule_text or "",
                penalty_points=penalty_points,
            )

        self._rules[rule.rule_id] = rule
        self.rag.add_document(
            doc_id=f"rule_{rule.rule_id}",
            text=rule.to_rag_text(),
            metadata={
                "type": "rule",
                "rule_id": rule.rule_id,
                "category": rule.category,
                "name": rule.name,
            },
        )

    def ingest_trade_log(self, record: TradeLogRecord) -> None:
        """Indexes a legacy TradeLogRecord for backward-compatibility and post-mortem evaluation."""
        self._legacy_trades[record.trade_id] = record
        violations = ", ".join(record.rule_violations) if record.rule_violations else "None"
        summary = (
            f"Trade {record.trade_id} on {record.symbol} ({record.direction}): "
            f"Setup: {record.setup_type}, PnL: {record.pnl}, "
            f"Violations: {violations}. Notes: {record.notes}"
        )
        self.rag.add_document(
            doc_id=f"trade_{record.trade_id}",
            text=summary,
            metadata={
                "type": "trade_log",
                "trade_id": record.trade_id,
                "symbol": record.symbol,
                "pnl": record.pnl,
            },
        )

    def ingest_trade_record(self, record: IngestedTradeRecord) -> None:
        """Indexes a trade or setup record for historical setup search."""
        self._trades[record.record_id] = record
        self.rag.add_document(
            doc_id=f"trade_{record.record_id}",
            text=record.to_rag_text(),
            metadata={
                "type": "trade_log",
                "record_id": record.record_id,
                "symbol": record.symbol,
                "action": record.action,
                "status": record.status,
                "score": record.score,
            },
        )

    def get_status_overview(self) -> str:
        """Combines live MT5 account statistics with Coach knowledge stats."""
        acc = self.mt5_reader.get_account_status()
        acc_summary = acc.summary()

        perf = CoachAnalytics.compute_summary(list(self._trades.values()))
        lines = [
            acc_summary,
            "",
            f"### 🧠 Trading Coach Knowledge Base",
            f"- **Indexed Strategy Rules**: `{len(self._rules)}`",
            f"- **Indexed Trade Records / Setups**: `{len(self._trades)}`",
            f"- **Vector Index Chunks**: `{self.rag.count()}`",
            f"- **Historical Win Rate**: `{perf.win_rate:.1f}%` ({perf.winning_trades}W / {perf.losing_trades}L)",
            f"- **Cumulative Realized**: `{perf.total_r_profit:+.2f}R`",
        ]
        return "\n".join(lines)

    def review_trade(self, trade_id: str) -> str:
        """Generates a structured review of a specific trade by trade_id."""
        if trade_id in self._legacy_trades:
            trade = self._legacy_trades[trade_id]
            outcome = "WIN" if trade.pnl > 0 else ("LOSS" if trade.pnl < 0 else "BREAKEVEN")
            lines = [
                f"=== Trade Review: {trade.trade_id} ({trade.symbol}) ===",
                f"Direction: {trade.direction} | Setup: {trade.setup_type} | Outcome: {outcome} (${trade.pnl:.2f})",
                f"Entry: {trade.entry_price} -> Exit: {trade.exit_price}",
            ]
            if trade.rule_violations:
                lines.append("Rule Violations Detected:")
                for v in trade.rule_violations:
                    lines.append(f"  - [VIOLATION] {v}")
            else:
                lines.append("Compliance: 100% compliant with trading rules.")
            if trade.notes:
                lines.append(f"Trader Notes: {trade.notes}")
            return "\n".join(lines)

        if trade_id in self._trades:
            t = self._trades[trade_id]
            lines = [
                f"=== Trade Review: {t.record_id} ({t.symbol}) ===",
                f"Action: {t.action} | Status: {t.status} | Score: {t.score}",
                f"Timestamp: {t.timestamp}",
            ]
            if t.blocked_reasons:
                lines.append(f"Violations / Blocked Reasons: {', '.join(t.blocked_reasons)}")
            return "\n".join(lines)

        return f"Trade '{trade_id}' not found in Trading Coach database."

    def review_recent_trades(self, limit: int = 5) -> str:
        """Generates a structured post-mortem review of recent trades."""
        if not self._trades and not self._legacy_trades:
            return (
                "Trading Coach: No trade records indexed yet. "
                "Ensure `Trading bot/setup_history.csv` or `paper_trade_history.csv` is populated."
            )

        trades_list = list(self._trades.values())[-limit:] if self._trades else []
        lines = [f"### 📋 Recent Trade Post-Mortems (Last {len(trades_list)})"]

        for t in reversed(trades_list):
            status_icon = "🟢 WIN" if t.status == "WIN" else ("🔴 LOSS" if t.status == "LOSS" else f"⚪ {t.status}")
            r_info = f" ({t.profit_r:+.2f}R)" if t.profit_r is not None else ""
            lines.append(f"\n**Trade #{t.record_id}**: {t.symbol} {t.action} | {status_icon}{r_info}")
            lines.append(f"  - **Timestamp**: `{t.timestamp}` | **Confluence Score**: `{t.score}/100`")
            if t.sweep or t.mss_type or t.fvg_type:
                lines.append(f"  - **SMC Triggers**: Sweep=`{t.sweep or 'None'}` | MSS=`{t.mss_type or 'None'}` | FVG=`{t.fvg_type or 'None'}`")
            if t.blocked_reasons:
                lines.append(f"  - **Friction / Violations**: {', '.join(t.blocked_reasons)}")
            if t.close_reason:
                lines.append(f"  - **Close Reason**: `{t.close_reason}`")

        return "\n".join(lines)

    def audit_performance_leaks(self) -> str:
        """Audits trade records for session and behavioral leaks."""
        trades = list(self._trades.values())
        summary = CoachAnalytics.compute_summary(trades)
        leaks = CoachAnalytics.audit_leaks(trades)

        lines = [
            summary.to_markdown(),
            "",
            "### 🔍 Behavioral & Execution Leak Diagnostics",
        ]
        for leak in leaks:
            lines.append(f"- {leak}")

        return "\n".join(lines)

    def list_rules(self) -> str:
        """Returns formatted list of all active SMC trading strategy rules."""
        if not self._rules:
            return "Trading Coach: No rules indexed."

        lines = ["### 📜 Active SMC Strategy & Risk Rules"]
        for rule in self._rules.values():
            lines.append(f"- **[{rule.rule_id}] {rule.name}** ({rule.category})")
            lines.append(f"  _{rule.rule_text}_ (Violation penalty: -{rule.penalty_points} pts)")
        return "\n".join(lines)

    def pre_flight_check(
        self,
        symbol: str = "XAUUSD",
        bias: str = "BULLISH",
        action: str = "BUY",
        entry_price: Optional[float] = None,
        sl_price: Optional[float] = None,
        tp_price: Optional[float] = None,
    ) -> str:
        """Validates a proposed trade setup against strategy rules and risk limits."""
        lines = [f"### 🛡️ Pre-Flight Setup Check: {symbol} {action}"]
        violations: List[str] = []
        cautions: List[str] = []

        # 1. Check Bias alignment
        if (action == "BUY" and bias == "BEARISH") or (action == "SELL" and bias == "BULLISH"):
            violations.append("RULE_02_HTF_BIAS: Action contradicts Higher Timeframe bias.")

        # 2. Check R:R ratio if SL and TP provided
        if entry_price and sl_price and tp_price:
            risk = abs(entry_price - sl_price)
            reward = abs(tp_price - entry_price)
            if risk > 0:
                rr = reward / risk
                if rr < 1.5:
                    violations.append(f"RULE_07_MIN_RR: Reward-to-Risk ratio is {rr:.2f}R (Minimum requirement: 1.50R).")
                else:
                    lines.append(f"- **R:R Ratio**: `{rr:.2f}R` ✅")

        # 3. Check MT5 live equity
        acc = self.mt5_reader.get_account_status()
        if acc.is_live_connected:
            lines.append(f"- **Account Balance**: `${acc.balance:,.2f}` | **Free Margin**: `${acc.free_margin:,.2f}`")
            if acc.open_positions_count >= 2:
                cautions.append(f"Account already has {acc.open_positions_count} open positions.")
        else:
            cautions.append("MT5 terminal offline — live margin and position guard unverified.")

        if violations:
            lines.append("\n**⛔ Execution Blocked / Rule Violations**:")
            for v in violations:
                lines.append(f"  - [VIOLATION] {v}")
            lines.append("\n**Verdict**: ❌ **DO NOT TAKE THIS TRADE** until criteria are satisfied.")
        else:
            lines.append("\n**Verdict**: ✅ **APPROVED FOR EXECUTION** (Follow planned SL strictly).")

        if cautions:
            lines.append("\n**⚠️ Cautions**:")
            for c in cautions:
                lines.append(f"  - {c}")

        return "\n".join(lines)

    def explain_live_bot_status(self, task: str = "") -> str:
        """Generates a human-friendly, contextual explanation of live bot status and blockers."""
        import os
        import pandas as pd
        from zero_core.trading_status import TradingStatusAdapter

        status = TradingStatusAdapter().get_status()
        acc = self.mt5_reader.get_account_status()

        # Check last setup history entries to determine blocked reasons
        trading_bot_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Trading bot")
        buy_setup_csv = os.path.join(trading_bot_dir, "setup_history_buy.csv")
        sell_setup_csv = os.path.join(trading_bot_dir, "setup_history_sell.csv")

        latest_setup = None
        for path in (buy_setup_csv, sell_setup_csv):
            if os.path.exists(path):
                try:
                    df = pd.read_csv(path)
                    if not df.empty:
                        last_row = df.iloc[-1].to_dict()
                        row_time = str(last_row.get("time") or last_row.get("timestamp") or "")
                        if latest_setup is None or row_time > str(latest_setup.get("time") or latest_setup.get("timestamp") or ""):
                            latest_setup = last_row
                except Exception:
                    pass

        lines = ["### 🤖 Trading Bot Live Status & Intelligence Report\n"]

        # 1. Active Position State
        is_active = False
        if hasattr(status, "buy") and status.buy and getattr(status.buy, "active_buy_trade", False):
            is_active = True
        elif hasattr(status, "combined") and status.combined and getattr(status.combined, "active_buy_trade", False):
            is_active = True
        elif getattr(status, "active_buy_trade", False):
            is_active = True

        if is_active:
            lines.append("🟢 **Active Position**: **BUY Trade Currently OPEN**")
        else:
            lines.append("⚪ **Active Position**: **FLAT (No Open Trades)** — Zero risk currently active.")

        # 2. Account Status if available
        if acc.is_live_connected:
            lines.append(f"💰 **MT5 Account**: Balance `${acc.balance:,.2f}` | Equity `${acc.equity:,.2f}` | Open Positions: `{acc.open_positions_count}`")

        # 3. Market Scan Telemetry
        last_candle = None
        if hasattr(status, "buy") and status.buy and status.buy.last_candle_time:
            last_candle = str(status.buy.last_candle_time)
        elif hasattr(status, "combined") and status.combined and status.combined.last_candle_time:
            last_candle = str(status.combined.last_candle_time)
        else:
            last_candle = getattr(status, "last_signal_time", "Recent")
        lines.append(f"⏱️ **Last Scanned Candle**: `{last_candle}` (M5 timeframe)")

        # 4. Setup Evaluation & Blocked Reasons
        if latest_setup:
            score = latest_setup.get("score") or latest_setup.get("setup_score", "N/A")
            bias = latest_setup.get("bias", "NEUTRAL")
            direction = latest_setup.get("side") or latest_setup.get("direction", "BUY")
            reasons = str(latest_setup.get("blocked_reasons") or latest_setup.get("reasons", "")).strip()

            lines.append(f"\n📊 **Latest Setup Detected**: `{direction}` | Confluence Score: `{score}/100` | Bias: `{bias}`")

            if reasons and reasons.lower() != "nan" and reasons != "":
                clean_reasons = [r.strip() for r in reasons.split("|") if r.strip()]
                lines.append("\n🛡️ **Why No Trade Was Taken (Execution Filters & Blockers)**:")
                for r in clean_reasons:
                    if "outside active session" in r.lower() or "dead_zone" in r.lower():
                        lines.append(f"  • **Session Filter**: `{r}` — Market is outside London/NY active volatility windows. Protected against low liquidity & wide spreads.")
                    elif "not retesting" in r.lower() or "fvg" in r.lower():
                        lines.append(f"  • **SMC Entry Filter**: `{r}` — Price has not pulled back inside the Fair Value Gap zone to secure a high Reward-to-Risk entry.")
                    elif "bias is not" in r.lower():
                        lines.append(f"  • **HTF Bias Filter**: `{r}` — Higher timeframe trend alignment not yet fully confirmed.")
                    elif "score too low" in r.lower():
                        lines.append(f"  • **Confluence Threshold**: `{r}` — Minimum 80/100 score required to trigger order.")
                    else:
                        lines.append(f"  • **Risk Guard**: `{r}`")
            else:
                lines.append("\n✅ Setup criteria are actively monitored; awaiting next high-probability trigger.")
        else:
            lines.append(f"\nℹ️ Signal memory: `{status.summary()}`")

        lines.append("\n💡 **Summary**: The bot is operating normally. Capital preservation filters are strictly guarding against entering low-probability conditions.")
        return "\n".join(lines)

    def answer_question(self, query: str) -> str:
        """Answers a trader question using RAG retrieval over rules, setups, and trade history."""
        q_lower = query.strip().lower()

        # Handle specific explicit short commands & live bot inquiries
        if any(k in q_lower for k in ("status", "did trading bot", "did it trade", "what happen", "what stopped", "what stoppe", "why didn't", "why no trade", "why did", "how is trading", "take any trade", "took any trade", "current signal")):
            return self.explain_live_bot_status(query)
        if q_lower in ("leaks", "audit leaks", "show leaks", "mistakes"):
            return self.audit_performance_leaks()
        if q_lower in ("review", "recent reviews", "show reviews", "post-mortem"):
            return self.review_recent_trades()
        if q_lower in ("rules", "list rules", "show rules", "playbook"):
            return self.list_rules()

        results = self.rag.search(query=query, k=8)
        if not results:
            return self.explain_live_bot_status(query)

        lines = [f"Trading Coach Analysis for: '{query}'\nRelevant Context Retrieved:"]
        for doc, score in results:
            doc_type = doc.metadata.get("type", "general")
            lines.append(f"  - [{doc_type.upper()}] {doc.text} (Relevance: {score:.2f})")

        return "\n".join(lines)


# Global singleton instance for ZERO runtime execution
DEFAULT_TRADING_COACH = TradingCoachAgent()

