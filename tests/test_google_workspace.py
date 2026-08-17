from __future__ import annotations

from unittest.mock import MagicMock
from zero_core.adapters.google_workspace import (
    CalendarEvent,
    GoogleCalendarLiveAdapter,
    GmailLiveAdapter,
    InboxMessage,
)
from zero_core.agents.calendar_agent import CalendarAgent
from zero_core.agents.email_agent import EmailAgent


def test_google_calendar_fallback_unconfigured():
    adapter = GoogleCalendarLiveAdapter(access_token="")
    assert adapter.is_configured() is False
    assert adapter.get_upcoming_events() == []


def test_gmail_fallback_unconfigured():
    adapter = GmailLiveAdapter(access_token="")
    assert adapter.is_configured() is False
    assert adapter.get_unread_messages() == []


def test_calendar_agent_uses_live_adapter_when_present(monkeypatch):
    mock_adapter = MagicMock()
    mock_adapter.is_configured.return_value = True
    mock_adapter.get_upcoming_events.return_value = [
        CalendarEvent(
            summary="Architecture Sync",
            start_time="2026-08-17T14:00:00Z",
            end_time="2026-08-17T15:00:00Z",
            location="Google Meet",
        )
    ]

    import zero_core.adapters.google_workspace as gw
    monkeypatch.setattr(gw, "DEFAULT_CALENDAR_LIVE_ADAPTER", mock_adapter)

    agent = CalendarAgent()
    summary = agent.summarize_schedule()
    assert "Live Google Calendar" in summary
    assert "Architecture Sync" in summary


def test_email_agent_uses_live_adapter_when_present(monkeypatch):
    mock_adapter = MagicMock()
    mock_adapter.is_configured.return_value = True
    mock_adapter.get_unread_messages.return_value = [
        InboxMessage(
            sender="lead@agency.internal",
            subject="Security Review Completed",
            snippet="Threat model report is attached.",
            received_time="2026-08-17T10:00:00Z",
        )
    ]

    import zero_core.adapters.google_workspace as gw
    monkeypatch.setattr(gw, "DEFAULT_GMAIL_LIVE_ADAPTER", mock_adapter)

    agent = EmailAgent()
    summary = agent.summarize_inbox()
    assert "Live Gmail" in summary
    assert "Security Review Completed" in summary
