"""Trading Coach Agent for ZERO (Milestone M11).

Provides RAG-driven trade review and strategy rule compliance analysis over
historical trades, distinct from the real-time signal-state Trading Agent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.memory.vector_rag import VectorRAGStore


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
    """RAG-powered trading coach that evaluates trade setups and compliance with trading rules."""

    def __init__(self, rag_store: Optional[VectorRAGStore] = None):
        self.rag = rag_store or VectorRAGStore()
        self._trades: Dict[str, TradeLogRecord] = {}
        self._rules: Dict[str, str] = {}

    def ingest_strategy_rule(self, rule_id: str, rule_text: str) -> None:
        """Indexes a trading strategy rule for RAG retrieval."""
        self._rules[rule_id] = rule_text
        self.rag.add_document(
            doc_id=f"rule_{rule_id}",
            text=f"Strategy Rule {rule_id}: {rule_text}",
            metadata={"type": "rule", "rule_id": rule_id},
        )

    def ingest_trade_log(self, record: TradeLogRecord) -> None:
        """Indexes a trade log record for historical setup search."""
        self._trades[record.trade_id] = record
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

    def review_trade(self, trade_id: str) -> str:
        """Generates a structured review of a specific trade against indexed rules."""
        trade = self._trades.get(trade_id)
        if trade is None:
            return f"Trade '{trade_id}' not found in Trading Coach database."

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

    def answer_question(self, query: str) -> str:
        """Answers a trader question using RAG retrieval over rules and trade history."""
        results = self.rag.search(query=query, k=3)
        if not results:
            return (
                f"Trading Coach: No specific historical trades or rules found matching '{query}'. "
                "Ensure trade logs and strategy rules are ingested."
            )

        lines = [f"Trading Coach Analysis for: '{query}'\nRelevant Context Retrieved:"]
        for doc, score in results:
            doc_type = doc.metadata.get("type", "general")
            lines.append(f"  - [{doc_type.upper()}] {doc.text} (Relevance: {score:.2f})")

        return "\n".join(lines)


# Global singleton instance for ZERO runtime execution
DEFAULT_TRADING_COACH = TradingCoachAgent()

# Pre-populate standard SMC trading rules
DEFAULT_TRADING_COACH.ingest_strategy_rule(
    rule_id="R1_MAX_RISK",
    rule_text="Never risk more than 1.5% of account balance per trade.",
)
DEFAULT_TRADING_COACH.ingest_strategy_rule(
    rule_id="R2_HTF_ALIGNMENT",
    rule_text="Always ensure market structure is aligned with Higher Timeframe (4H/1D) trend.",
)
DEFAULT_TRADING_COACH.ingest_strategy_rule(
    rule_id="R3_LIQUIDITY_SWEEP",
    rule_text="Wait for clear buy-side or sell-side liquidity sweep before entering SMC reversal.",
)
