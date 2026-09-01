"""Comprehensive Unit Tests for Trading Coach RAG Pipeline, Analytics, and Telegram Interface."""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from zero_core.agents.trading_coach import TradingCoachAgent
from zero_core.interfaces.telegram.bot import TelegramBotHandler
from zero_core.memory.vector_rag import VectorRAGStore
from zero_core.trading.coach_analytics import CoachAnalytics
from zero_core.trading.coach_ingestion import (
    CoachIngestionPipeline,
    IngestedTradeRecord,
    StrategyRuleRecord,
)
from zero_core.trading_live_reader import MT5ReadOnlyAdapter


def test_coach_ingestion_standard_rules():
    pipeline = CoachIngestionPipeline()
    rules = pipeline.get_standard_rules()
    assert len(rules) >= 5
    rule_ids = [r.rule_id for r in rules]
    assert "RULE_01_MAX_RISK" in rule_ids
    assert "RULE_02_HTF_BIAS" in rule_ids
    assert "RULE_03_LIQUIDITY_SWEEP" in rule_ids


def test_coach_ingestion_csv_parsing():
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        csv_file = tmp_path / "setup_history.csv"
        csv_file.write_text(
            "time,side,score,bias,sweep,mss_type,fvg_type,trade_taken,blocked_reasons\n"
            "2026-08-01 10:00:00,BUY,75,BULLISH,SELL_SIDE_SWEEP,BULLISH_MSS,BULLISH_FVG,YES,\n"
            "2026-08-01 11:00:00,SELL,40,BEARISH,,,,,No sweep;Score low\n",
            encoding="utf-8",
        )

        pipeline = CoachIngestionPipeline(trading_bot_path=tmp_path)
        records = pipeline.parse_setup_history_csv(csv_file)
        assert len(records) == 2
        assert records[0].action == "BUY"
        assert records[0].status == "TAKEN"
        assert records[0].score == 75.0
        assert records[1].status == "BLOCKED"
        assert len(records[1].blocked_reasons) == 2


def test_coach_ingestion_paper_csv_parsing():
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        paper_csv = tmp_path / "paper_trade_history.csv"
        paper_csv.write_text(
            "time,action,status,bias,sweep,mss_type,fvg_type,entry,tp_price,sl_price,rr,profit_r,close_reason\n"
            "2026-08-02 14:00:00,BUY,WIN,BULLISH,SELL_SIDE_SWEEP,BULLISH_MSS,BULLISH_FVG,2650.0,2660.0,2645.0,2.0,2.0,TP touched\n"
            "2026-08-02 16:00:00,BUY,LOSS,BULLISH,SELL_SIDE_SWEEP,BULLISH_MSS,BULLISH_FVG,2655.0,2665.0,2650.0,2.0,-1.0,SL touched\n",
            encoding="utf-8",
        )

        pipeline = CoachIngestionPipeline(trading_bot_path=tmp_path)
        records = pipeline.parse_paper_trade_csv(paper_csv)
        assert len(records) == 2
        assert records[0].status == "WIN"
        assert records[0].profit_r == 2.0
        assert records[1].status == "LOSS"
        assert records[1].profit_r == -1.0


def test_coach_analytics_summary_and_leaks():
    records = [
        IngestedTradeRecord(
            record_id="t1",
            timestamp="2026-08-01 10:00:00",
            symbol="XAUUSD",
            action="BUY",
            status="WIN",
            bias="BULLISH",
            sweep="SELL_SIDE_SWEEP",
            profit_r=2.0,
            score=80,
        ),
        IngestedTradeRecord(
            record_id="t2",
            timestamp="2026-08-01 11:00:00",
            symbol="XAUUSD",
            action="BUY",
            status="LOSS",
            bias="BEARISH",  # Counter-trend leak!
            sweep=None,       # No sweep leak!
            profit_r=-1.0,
            score=50,
        ),
    ]

    summary = CoachAnalytics.compute_summary(records)
    assert summary.total_trades == 2
    assert summary.winning_trades == 1
    assert summary.losing_trades == 1
    assert summary.win_rate == 50.0
    assert summary.total_r_profit == 1.0

    leaks = CoachAnalytics.audit_leaks(records)
    assert any("No-Sweep Entry" in leak for leak in leaks)
    assert any("Counter-Trend" in leak for leak in leaks)


def test_trading_coach_agent_full_flow():
    rag = VectorRAGStore()
    mt5 = MT5ReadOnlyAdapter(mock_mode=True)
    agent = TradingCoachAgent(rag_store=rag, mt5_reader=mt5)

    # Ingest custom test record
    agent.ingest_trade_record(
        IngestedTradeRecord(
            record_id="test_01",
            timestamp="2026-08-03 15:30:00",
            symbol="XAUUSD",
            action="BUY",
            status="WIN",
            score=85,
            bias="BULLISH",
            sweep="SELL_SIDE_SWEEP",
            mss_type="BULLISH_MSS",
            profit_r=2.5,
        )
    )

    # Status overview
    status = agent.get_status_overview()
    assert "Trading Coach Knowledge Base" in status
    assert "Indexed Strategy Rules" in status

    # Trade reviews
    review = agent.review_recent_trades()
    assert "Recent Trade Post-Mortems" in review
    assert "Trade #test_01" in review

    # Leak audit
    leaks = agent.audit_performance_leaks()
    assert "Trading Performance & Setup Audit" in leaks

    # Pre-flight check (Valid setup)
    pf_valid = agent.pre_flight_check(
        symbol="XAUUSD",
        bias="BULLISH",
        action="BUY",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2660.0,  # 2:1 RR
    )
    assert "APPROVED FOR EXECUTION" in pf_valid

    # Pre-flight check (Counter-trend setup)
    pf_invalid = agent.pre_flight_check(
        symbol="XAUUSD",
        bias="BEARISH",
        action="BUY",
        entry_price=2650.0,
        sl_price=2645.0,
        tp_price=2660.0,
    )
    assert "DO NOT TAKE THIS TRADE" in pf_invalid
    assert "RULE_02_HTF_BIAS" in pf_invalid

    # RAG Semantic Question
    ans = agent.answer_question("What is the rule on liquidity sweep?")
    assert "Trading Coach Analysis" in ans or "Liquidity" in ans


def test_telegram_coach_command():
    bot = TelegramBotHandler()

    # /coach
    res_status = bot.handle_command("/coach", "")
    assert "Trading Coach Knowledge Base" in res_status

    # /coach review
    res_review = bot.handle_command("/coach", "review")
    assert "trade" in res_review.lower() or "post-mortem" in res_review.lower()

    # /coach rules
    res_rules = bot.handle_command("/coach", "rules")
    assert "Active SMC Strategy" in res_rules
    assert "RULE_01_MAX_RISK" in res_rules

    # /coach leaks
    res_leaks = bot.handle_command("/coach", "leaks")
    assert "Trading Performance" in res_leaks or "Leak Diagnostics" in res_leaks

    # /coach custom question
    res_q = bot.handle_command("/coach", "How much risk per trade?")
    assert "Trading Coach" in res_q or "Risk" in res_q
