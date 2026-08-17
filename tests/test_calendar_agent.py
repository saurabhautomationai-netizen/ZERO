from __future__ import annotations

from zero_core.agents.calendar_agent import (
    DEFAULT_CALENDAR_AGENT,
    CalendarAgent,
    CalendarEvent,
)
from zero_core.executors import execute
from zero_core.native_agents import CALENDAR_AGENT


def test_calendar_agent_empty_schedule():
    agent = CalendarAgent()
    summary = agent.summarize_schedule()
    assert "No upcoming meetings scheduled" in summary


def test_calendar_agent_schedule_and_conflict_detection():
    agent = CalendarAgent()

    # Schedule first event: 10:00 to 11:00
    res1 = agent.schedule_event(
        title="Sprint Planning",
        start_time="2026-08-17T10:00:00Z",
        end_time="2026-08-17T11:00:00Z",
        attendees=["team@example.com"],
        location="Room A",
    )
    assert res1["success"] is True
    assert res1["has_conflicts"] is False

    # Schedule overlapping event: 10:30 to 11:30
    res2 = agent.schedule_event(
        title="1-on-1 Sync",
        start_time="2026-08-17T10:30:00Z",
        end_time="2026-08-17T11:30:00Z",
        attendees=["manager@example.com"],
    )
    assert res2["success"] is True
    assert res2["has_conflicts"] is True
    assert len(res2["conflicting_events"]) == 1
    assert res2["conflicting_events"][0]["title"] == "Sprint Planning"


def test_calendar_agent_meeting_brief():
    agent = CalendarAgent()
    ev = CalendarEvent(
        event_id="evt_demo",
        title="Architecture Review",
        start_time="2026-08-17T14:00:00Z",
        end_time="2026-08-17T15:00:00Z",
        attendees=["lead_architect@example.com"],
        location="Google Meet",
        description="Review M11-M13 milestone progress.",
    )
    agent.add_event(ev)

    brief = agent.prepare_meeting_brief("evt_demo")
    assert "Architecture Review" in brief
    assert "Google Meet" in brief
    assert "lead_architect@example.com" in brief
    assert "M11-M13" in brief


def test_calendar_agent_executor_dispatch():
    res = execute(spec=CALENDAR_AGENT, task="What is on my schedule today?")
    assert res.spec.slug == "native/calendar-agent"
    assert res.needs_llm is False
    assert "Calendar Agent:" in res.answer
