"""Google Workspace live read-only adapters for Calendar and Gmail (Milestone Expansion).

Provides read-only access to:
- Google Calendar API: Upcoming 24-hour events, meetings, and agendas.
- Gmail API: Unread inbox highlights, senders, and high-priority subjects.

Security Guarantee:
- Read-only scopes (no email sending or event deletion).
- Graceful offline fallback when OAuth credentials are absent.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


@dataclass
class CalendarEvent:
    """Represents a scheduled calendar meeting or event."""
    summary: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    attendees_count: int = 0


@dataclass
class InboxMessage:
    """Represents an unread email message snapshot."""
    sender: str
    subject: str
    snippet: str
    received_time: str


class GoogleCalendarLiveAdapter:
    """Read-only adapter for Google Calendar API v3."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.environ.get("GOOGLE_CALENDAR_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.access_token.strip())

    def get_upcoming_events(self, hours_ahead: int = 24) -> List[CalendarEvent]:
        """Fetches upcoming calendar events, falling back gracefully if unconfigured."""
        if not self.is_configured():
            return []

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(hours=hours_ahead)).isoformat()

        url = (
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events"
            f"?timeMin={time_min}&timeMax={time_max}&singleEvents=true&orderBy=startTime"
        )
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                items = data.get("items", [])
                events = []
                for item in items:
                    start = item.get("start", {}).get("dateTime") or item.get("start", {}).get("date", "")
                    end = item.get("end", {}).get("dateTime") or item.get("end", {}).get("date", "")
                    events.append(
                        CalendarEvent(
                            summary=item.get("summary", "Untitled Meeting"),
                            start_time=start,
                            end_time=end,
                            location=item.get("location"),
                            attendees_count=len(item.get("attendees", [])),
                        )
                    )
                return events
        except Exception:
            return []


class GmailLiveAdapter:
    """Read-only adapter for Gmail API v1."""

    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.environ.get("GMAIL_TOKEN", "")

    def is_configured(self) -> bool:
        return bool(self.access_token.strip())

    def get_unread_messages(self, max_results: int = 5) -> List[InboxMessage]:
        """Fetches unread inbox messages, falling back cleanly if offline."""
        if not self.is_configured():
            return []

        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults={max_results}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {self.access_token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg_ids = [m["id"] for m in data.get("messages", [])]
                messages = []
                for msg_id in msg_ids:
                    detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata"
                    d_req = urllib.request.Request(detail_url, headers={"Authorization": f"Bearer {self.access_token}"})
                    with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                        d_data = json.loads(d_resp.read().decode("utf-8"))
                        headers = {h["name"].lower(): h["value"] for h in d_data.get("payload", {}).get("headers", [])}
                        messages.append(
                            InboxMessage(
                                sender=headers.get("from", "Unknown Sender"),
                                subject=headers.get("subject", "(No Subject)"),
                                snippet=d_data.get("snippet", ""),
                                received_time=headers.get("date", ""),
                            )
                        )
                return messages
        except Exception:
            return []


# Global singleton instances
DEFAULT_CALENDAR_LIVE_ADAPTER = GoogleCalendarLiveAdapter()
DEFAULT_GMAIL_LIVE_ADAPTER = GmailLiveAdapter()
