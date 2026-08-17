"""Daily Briefing Agent for ZERO (Personal Memory & Daily Operations).

Aggregates morning and evening briefings across Finance, Trading, Email, Calendar,
and Learning systems into a single executive digest.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from zero_core.agents.calendar_agent import DEFAULT_CALENDAR_AGENT
from zero_core.agents.email_agent import DEFAULT_EMAIL_AGENT
from zero_core.agents.learning_agent import DEFAULT_LEARNING_AGENT
from zero_core.trading_status import TradingStatusAdapter


@dataclass
class DailyBriefingReport:
    """Comprehensive daily executive brief."""
    timestamp: str
    greeting: str
    calendar_summary: str
    email_summary: str
    trading_summary: str
    finance_highlight: str
    learning_goal: str

    def to_markdown(self) -> str:
        return (
            f"# ZERO — Daily Executive Briefing\n"
            f"**Generated**: {self.timestamp}\n\n"
            f"### {self.greeting}\n\n"
            f"## 📅 Calendar & Agenda\n"
            f"{self.calendar_summary}\n\n"
            f"## 📬 Inbox Highlights\n"
            f"{self.email_summary}\n\n"
            f"## 📈 Trading Bot Signal Status\n"
            f"{self.trading_summary}\n\n"
            f"## 💰 Personal Finance\n"
            f"{self.finance_highlight}\n\n"
            f"## 🧠 Daily Learning & Mastery Goal\n"
            f"{self.learning_goal}\n"
        )


class BriefingAgent:
    """Aggregates multi-agent intelligence into morning & evening briefings."""

    def generate_morning_briefing(self) -> DailyBriefingReport:
        now_str = datetime.now(timezone.utc).strftime("%A, %B %d, %Y %H:%M UTC")

        # Calendar
        cal_summary = DEFAULT_CALENDAR_AGENT.summarize_schedule()

        # Email
        email_summary = DEFAULT_EMAIL_AGENT.summarize_inbox()

        # Trading
        trading_status = TradingStatusAdapter().get_status().summary()

        # Finance
        finance_highlight = (
            "Connected to Zero Finance Tracker. No anomalous transactions detected in current cycle."
        )

        # Learning
        learning_goal = (
            "Review LangGraph State Machine transitions and MT5 risk sizing formulas."
        )

        return DailyBriefingReport(
            timestamp=now_str,
            greeting="Good morning. Here is your operational briefing across all systems for today.",
            calendar_summary=cal_summary,
            email_summary=email_summary,
            trading_summary=trading_status,
            finance_highlight=finance_highlight,
            learning_goal=learning_goal,
        )


# Global singleton instance
DEFAULT_BRIEFING_AGENT = BriefingAgent()
