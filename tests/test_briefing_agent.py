from __future__ import annotations

from zero_core.agents.briefing_agent import (
    DEFAULT_BRIEFING_AGENT,
    BriefingAgent,
    DailyBriefingReport,
)
from zero_core.executors import execute
from zero_core.native_agents import BRIEFING_AGENT


def test_briefing_agent_generate_morning_briefing():
    agent = BriefingAgent()
    brief = agent.generate_morning_briefing()

    assert "Daily Executive Briefing" in brief.to_markdown()
    assert "Calendar & Agenda" in brief.to_markdown()
    assert "Inbox Highlights" in brief.to_markdown()
    assert "Trading Bot Signal Status" in brief.to_markdown()
    assert "Personal Finance" in brief.to_markdown()


def test_briefing_agent_executor_dispatch():
    res = execute(spec=BRIEFING_AGENT, task="Give me my morning briefing")
    assert res.spec.slug == "native/briefing-agent"
    assert res.needs_llm is False
    assert "Daily Executive Briefing" in res.answer
