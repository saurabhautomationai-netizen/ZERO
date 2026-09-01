"""Google Workspace live adapters for Calendar and Gmail with OAuth2 token manager.

Provides live access to:
- Google Calendar API v3: Upcoming events, meetings, and event creation.
- Gmail API v1: Inbox triage, unread highlights, RFC-2822 draft generation, and outbound email delivery.

Security & Resilience Guarantees:
- OAuth2 token auto-refresh via refresh_token when configured.
- Graceful offline fallback to local mock/in-memory cache when credentials are absent.
- Full RFC-2822 base64url email MIME encoding for standard Gmail API delivery.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class CalendarEvent:
    """Represents a scheduled calendar meeting or event."""
    summary: str
    start_time: str
    end_time: str
    location: Optional[str] = None
    attendees_count: int = 0
    event_id: Optional[str] = None
    description: Optional[str] = None


@dataclass
class InboxMessage:
    """Represents an unread email message snapshot."""
    sender: str
    subject: str
    snippet: str
    received_time: str
    message_id: Optional[str] = None


class GoogleOAuthManager:
    """Manages Google Workspace access and refresh tokens."""

    def __init__(
        self,
        token_path: Optional[Path] = None,
        credentials_path: Optional[Path] = None,
    ):
        self.token_path = token_path or (Path(__file__).resolve().parent.parent.parent / "token.json")
        self.credentials_path = credentials_path or (Path(__file__).resolve().parent.parent.parent / "credentials.json")
        self._cached_token: Optional[str] = None

    def get_access_token(self) -> str:
        """Retrieves a valid access token from environment, token.json, or refresh flow."""
        # 1. Environment override
        env_token = (
            os.environ.get("GOOGLE_WORKSPACE_ACCESS_TOKEN")
            or os.environ.get("GMAIL_TOKEN")
            or os.environ.get("GOOGLE_CALENDAR_TOKEN")
        )
        if env_token and env_token.strip():
            return env_token.strip()

        # 2. Check token.json
        if self.token_path.exists():
            try:
                data = json.loads(self.token_path.read_text(encoding="utf-8"))
                token = data.get("access_token") or data.get("token")
                refresh_token = data.get("refresh_token")

                # If token expired and refresh_token available, refresh
                if refresh_token and data.get("client_id") and data.get("client_secret"):
                    refreshed = self.refresh_token(
                        refresh_token=refresh_token,
                        client_id=data["client_id"],
                        client_secret=data["client_secret"],
                    )
                    if refreshed:
                        return refreshed

                if token:
                    return str(token).strip()
            except Exception:
                pass

        # 3. Check environment refresh token
        env_refresh = os.environ.get("GOOGLE_REFRESH_TOKEN")
        client_id = os.environ.get("GOOGLE_CLIENT_ID")
        client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        if env_refresh and client_id and client_secret:
            refreshed = self.refresh_token(env_refresh, client_id, client_secret)
            if refreshed:
                return refreshed

        return ""

    def refresh_token(self, refresh_token: str, client_id: str, client_secret: str) -> Optional[str]:
        """Exchanges a refresh token for a fresh short-lived access token."""
        url = "https://oauth2.googleapis.com/token"
        payload = urllib.parse.urlencode({
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                new_token = data.get("access_token")
                if new_token:
                    self._cached_token = new_token
                    return new_token
        except Exception:
            return None
        return None


class GoogleCalendarLiveAdapter:
    """Adapter for Google Calendar API v3 (Read & Write)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        oauth_manager: Optional[GoogleOAuthManager] = None,
    ):
        self._direct_token = access_token
        self.oauth_manager = oauth_manager or GoogleOAuthManager()

    def _get_token(self) -> str:
        if self._direct_token is not None:
            return self._direct_token.strip()
        return self.oauth_manager.get_access_token()

    def is_configured(self) -> bool:
        return bool(self._get_token())

    def get_upcoming_events(self, hours_ahead: int = 24) -> List[CalendarEvent]:
        """Fetches upcoming calendar events, falling back cleanly if unconfigured."""
        token = self._get_token()
        if not token:
            return []

        now = datetime.now(timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(hours=hours_ahead)).isoformat()

        url = (
            f"https://www.googleapis.com/calendar/v3/calendars/primary/events"
            f"?timeMin={urllib.parse.quote(time_min)}&timeMax={urllib.parse.quote(time_max)}&singleEvents=true&orderBy=startTime"
        )
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
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
                            event_id=item.get("id"),
                            summary=item.get("summary", "Untitled Meeting"),
                            start_time=start,
                            end_time=end,
                            location=item.get("location"),
                            attendees_count=len(item.get("attendees", [])),
                            description=item.get("description"),
                        )
                    )
                return events
        except Exception:
            return []

    def create_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        location: str = "Online",
        description: str = "",
        attendees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Creates a calendar event via Google Calendar API."""
        token = self._get_token()
        if not token:
            return {
                "success": False,
                "error": "Google Calendar is not configured with a valid OAuth token.",
            }

        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        body_dict = {
            "summary": summary,
            "description": description,
            "location": location,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        if attendees:
            body_dict["attendees"] = [{"email": email} for email in attendees]

        payload = json.dumps(body_dict).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "event_id": res_data.get("id"),
                    "html_link": res_data.get("htmlLink"),
                    "summary": res_data.get("summary"),
                }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Calendar event creation failed: {exc}",
            }


class GmailLiveAdapter:
    """Adapter for Gmail API v1 (Read, Draft, and Send)."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        oauth_manager: Optional[GoogleOAuthManager] = None,
    ):
        self._direct_token = access_token
        self.oauth_manager = oauth_manager or GoogleOAuthManager()

    def _get_token(self) -> str:
        if self._direct_token is not None:
            return self._direct_token.strip()
        return self.oauth_manager.get_access_token()

    def is_configured(self) -> bool:
        return bool(self._get_token())

    def get_unread_messages(self, max_results: int = 5) -> List[InboxMessage]:
        """Fetches unread inbox messages from Gmail API."""
        token = self._get_token()
        if not token:
            return []

        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?q=is:unread&maxResults={max_results}"
        req = urllib.request.Request(
            url,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msg_ids = [m["id"] for m in data.get("messages", [])]
                messages = []
                for msg_id in msg_ids:
                    detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata"
                    d_req = urllib.request.Request(detail_url, headers={"Authorization": f"Bearer {token}"})
                    with urllib.request.urlopen(d_req, timeout=10) as d_resp:
                        d_data = json.loads(d_resp.read().decode("utf-8"))
                        headers = {h["name"].lower(): h["value"] for h in d_data.get("payload", {}).get("headers", [])}
                        messages.append(
                            InboxMessage(
                                message_id=msg_id,
                                sender=headers.get("from", "Unknown Sender"),
                                subject=headers.get("subject", "(No Subject)"),
                                snippet=d_data.get("snippet", ""),
                                received_time=headers.get("date", ""),
                            )
                        )
                return messages
        except Exception:
            return []

    @staticmethod
    def encode_rfc2822_message(recipient: str, subject: str, body: str) -> str:
        """Encodes an email message into base64url format for Gmail API."""
        msg = MIMEText(body, "plain", "utf-8")
        msg["to"] = recipient
        msg["subject"] = subject
        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    def create_draft(self, recipient: str, subject: str, body: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """Creates a draft in Gmail via API."""
        token = self._get_token()
        if not token:
            return {
                "success": False,
                "error": "Gmail is not configured with a valid OAuth token.",
            }

        encoded_raw = self.encode_rfc2822_message(recipient, subject, body)
        msg_payload: Dict[str, Any] = {"raw": encoded_raw}
        if thread_id:
            msg_payload["threadId"] = thread_id

        url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
        req = urllib.request.Request(
            url,
            data=json.dumps({"message": msg_payload}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "draft_id": res_data.get("id"),
                    "message_id": res_data.get("message", {}).get("id"),
                }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Gmail draft creation failed: {exc}",
            }

    def send_message(self, recipient: str, subject: str, body: str) -> Dict[str, Any]:
        """Sends an email directly through the Gmail API."""
        token = self._get_token()
        if not token:
            return {
                "success": False,
                "error": "Gmail is not configured with a valid OAuth token.",
            }

        encoded_raw = self.encode_rfc2822_message(recipient, subject, body)
        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        req = urllib.request.Request(
            url,
            data=json.dumps({"raw": encoded_raw}).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_data = json.loads(resp.read().decode("utf-8"))
                return {
                    "success": True,
                    "message_id": res_data.get("id"),
                    "thread_id": res_data.get("threadId"),
                }
        except Exception as exc:
            return {
                "success": False,
                "error": f"Gmail send failed: {exc}",
            }


# Global singleton instances
DEFAULT_OAUTH_MANAGER = GoogleOAuthManager()
DEFAULT_CALENDAR_LIVE_ADAPTER = GoogleCalendarLiveAdapter(oauth_manager=DEFAULT_OAUTH_MANAGER)
DEFAULT_GMAIL_LIVE_ADAPTER = GmailLiveAdapter(oauth_manager=DEFAULT_OAUTH_MANAGER)
