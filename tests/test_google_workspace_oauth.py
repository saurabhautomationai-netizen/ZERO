"""Comprehensive Unit Tests for Google Workspace OAuth2 Manager, Live Adapters, and RFC-2822 MIME Encoding."""

import base64
import email
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from zero_core.adapters.google_workspace import (
    GmailLiveAdapter,
    GoogleCalendarLiveAdapter,
    GoogleOAuthManager,
)
from zero_core.agents.calendar_agent import CalendarAgent
from zero_core.agents.email_agent import EmailAgent


def test_oauth_manager_environment_token(monkeypatch):
    monkeypatch.setenv("GMAIL_TOKEN", "mock_oauth_bearer_token_123")
    manager = GoogleOAuthManager()
    token = manager.get_access_token()
    assert token == "mock_oauth_bearer_token_123"


def test_oauth_manager_token_file():
    with TemporaryDirectory() as tmp_dir:
        token_file = Path(tmp_dir) / "token.json"
        token_file.write_text(json.dumps({"access_token": "file_token_456"}), encoding="utf-8")

        manager = GoogleOAuthManager(token_path=token_file)
        token = manager.get_access_token()
        assert token == "file_token_456"


def test_gmail_rfc2822_base64_encoding():
    adapter = GmailLiveAdapter()
    encoded = adapter.encode_rfc2822_message(
        recipient="partner@example.com",
        subject="Project Alpha Status",
        body="All systems are operating as expected.",
    )
    assert isinstance(encoded, str)
    assert len(encoded) > 20

    raw_mime_bytes = base64.urlsafe_b64decode(encoded.encode("ascii"))
    msg = email.message_from_bytes(raw_mime_bytes)
    assert msg["to"] == "partner@example.com"
    assert msg["subject"] == "Project Alpha Status"
    payload_body = msg.get_payload(decode=True).decode("utf-8")
    assert "All systems are operating as expected." in payload_body


def test_gmail_adapter_offline_fallback():
    # Empty manager without tokens
    manager = GoogleOAuthManager(token_path=Path("/non_existent/token.json"))
    adapter = GmailLiveAdapter(oauth_manager=manager)
    assert adapter.is_configured() is False

    # Unread messages return empty list without crash
    unread = adapter.get_unread_messages()
    assert unread == []

    # Create draft returns unconfigured error
    res_draft = adapter.create_draft("test@example.com", "Subj", "Body")
    assert res_draft["success"] is False
    assert "not configured" in res_draft["error"]

    # Send message returns unconfigured error
    res_send = adapter.send_message("test@example.com", "Subj", "Body")
    assert res_send["success"] is False
    assert "not configured" in res_send["error"]


def test_calendar_adapter_offline_fallback():
    manager = GoogleOAuthManager(token_path=Path("/non_existent/token.json"))
    adapter = GoogleCalendarLiveAdapter(oauth_manager=manager)
    assert adapter.is_configured() is False

    # Get events returns empty list without crash
    events = adapter.get_upcoming_events()
    assert events == []

    # Create event returns error safely
    res_create = adapter.create_event(
        summary="Sprint Review",
        start_time="2026-08-20T10:00:00Z",
        end_time="2026-08-20T11:00:00Z",
    )
    assert res_create["success"] is False
    assert "not configured" in res_create["error"]


def test_email_agent_send_and_draft_integration():
    agent = EmailAgent()
    draft = agent.create_draft(
        reply_to_id=None,
        recipient="dev@example.com",
        subject="Bug report",
        body="Fixed in commit 123",
    )
    assert "draft_id" in draft
    assert draft["recipient"] == "dev@example.com"

    res_send = agent.send_email(
        recipient="dev@example.com",
        subject="Bug report",
        body="Fixed in commit 123",
    )
    assert res_send["success"] is True


def test_calendar_agent_schedule_integration():
    agent = CalendarAgent()
    res = agent.schedule_event(
        title="1-on-1 Sync",
        start_time="2026-08-21T14:00:00Z",
        end_time="2026-08-21T14:30:00Z",
        attendees=["colleague@example.com"],
    )
    assert res["success"] is True
    assert res["event"]["title"] == "1-on-1 Sync"
