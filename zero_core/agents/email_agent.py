"""Email Agent for ZERO (Milestone M12).

Provides email inbox triage, summarization, search, and draft generation.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class EmailMessage:
    """Represents an email message."""
    message_id: str
    sender: str
    recipient: str
    subject: str
    snippet: str
    body: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    is_read: bool = False
    labels: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EmailAgent:
    """Native Email Agent managing triage, summaries, and drafts."""

    def __init__(self):
        self._inbox: Dict[str, EmailMessage] = {}
        self._drafts: Dict[str, Dict[str, Any]] = {}

    def add_message(self, message: EmailMessage) -> None:
        self._inbox[message.message_id] = message

    def get_unread_messages(self) -> List[EmailMessage]:
        return [m for m in self._inbox.values() if not m.is_read]

    def summarize_inbox(self) -> str:
        """Returns a concise summary of unread messages from Gmail or local inbox."""
        from zero_core.adapters.google_workspace import DEFAULT_GMAIL_LIVE_ADAPTER

        if DEFAULT_GMAIL_LIVE_ADAPTER.is_configured():
            live_msgs = DEFAULT_GMAIL_LIVE_ADAPTER.get_unread_messages(max_results=5)
            if live_msgs:
                lines = [f"Email Agent (Live Gmail): {len(live_msgs)} unread email(s):"]
                for msg in live_msgs:
                    lines.append(f"  - [{msg.sender}] '{msg.subject}' -> {msg.snippet[:80]}...")
                return "\n".join(lines)

        unread = self.get_unread_messages()
        if not unread:
            return "Email Agent: Inbox is clean. No unread messages."

        lines = [f"Email Agent: {len(unread)} unread email(s):"]
        for msg in unread:
            priority = " [URGENT]" if "urgent" in [l.lower() for l in msg.labels] else ""
            lines.append(f"  - [{msg.sender}] '{msg.subject}'{priority} -> {msg.snippet}")
        return "\n".join(lines)

    def triage_inbox(self) -> Dict[str, List[Dict[str, Any]]]:
        """Categorizes inbox into actionable triage buckets."""
        buckets: Dict[str, List[Dict[str, Any]]] = {
            "urgent": [],
            "action_required": [],
            "general": [],
            "newsletter": [],
        }

        for msg in self._inbox.values():
            lower_labels = [l.lower() for l in msg.labels]
            subj_lower = msg.subject.lower()

            if "urgent" in lower_labels or "urgent" in subj_lower:
                buckets["urgent"].append(msg.to_dict())
            elif "action" in lower_labels or "review" in subj_lower:
                buckets["action_required"].append(msg.to_dict())
            elif "newsletter" in lower_labels or "digest" in subj_lower:
                buckets["newsletter"].append(msg.to_dict())
            else:
                buckets["general"].append(msg.to_dict())

        return buckets

    def create_draft(self, reply_to_id: Optional[str], recipient: str, subject: str, body: str) -> Dict[str, Any]:
        """Creates a response draft."""
        draft_id = f"draft_{uuid.uuid4().hex[:8]}"
        draft = {
            "draft_id": draft_id,
            "reply_to_id": reply_to_id,
            "recipient": recipient,
            "subject": subject,
            "body": body,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._drafts[draft_id] = draft
        return draft

    def search(self, query: str) -> List[EmailMessage]:
        """Searches inbox for matching keywords."""
        q = query.lower()
        results = []
        for m in self._inbox.values():
            if q in m.subject.lower() or q in m.body.lower() or q in m.sender.lower():
                results.append(m)
        return results


# Global singleton instance for ZERO runtime execution
DEFAULT_EMAIL_AGENT = EmailAgent()
