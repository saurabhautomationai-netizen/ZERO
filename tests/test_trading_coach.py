from __future__ import annotations

from zero_core.agents.trading_coach import (
    DEFAULT_TRADING_COACH,
    TradeLogRecord,
    TradingCoachAgent,
)
from zero_core.executors import execute
from zero_core.native_agents import TRADING_COACH


def test_trading_coach_ingest_and_review():
    coach = TradingCoachAgent()

    coach.ingest_strategy_rule(
        rule_id="RULE_RISK",
        rule_text="Do not risk more than 1% per trade.",
    )

    trade = TradeLogRecord(
        trade_id="TR_101",
        symbol="EURUSD",
        direction="BUY",
        entry_price=1.0850,
        exit_price=1.0820,
        pnl=-300.0,
        setup_type="SMC MSS",
        rule_violations=["Risked 2.5% exceeding 1% limit", "Traded into high impact news"],
        notes="Revenge trade after morning stop out.",
    )
    coach.ingest_trade_log(trade)

    review = coach.review_trade("TR_101")
    assert "TR_101" in review
    assert "EURUSD" in review
    assert "LOSS" in review
    assert "Risked 2.5% exceeding 1% limit" in review
    assert "Revenge trade" in review


def test_trading_coach_answer_question():
    coach = TradingCoachAgent()
    coach.ingest_strategy_rule(
        rule_id="RULE_NEWS",
        rule_text="Never enter positions 15 minutes before NFP or CPI news releases.",
    )

    answer = coach.answer_question("Can I trade during high impact NFP news?")
    assert "Trading Coach Analysis" in answer
    assert "Never enter positions" in answer


def test_trading_coach_executor_integration():
    res = execute(spec=TRADING_COACH, task="What is the rule on higher timeframe structure?")
    assert res.spec.slug == "native/trading-coach"
    assert res.needs_llm is False
    assert "Trading Coach Analysis" in res.answer
    assert "Higher Timeframe" in res.answer
